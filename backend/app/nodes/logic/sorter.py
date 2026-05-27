"""분류기 노드 핸들러 — 조건 분기 + 창고 보관 + 중복 필터.

확장: 각 rule 에 ``dataSource: 'input' | 'instance-db'`` 옵션.
- ``dataSource`` 미지정 또는 ``'input'`` → 기존 동작 (입력 dict 의 field 평가)
- ``dataSource: 'instance-db'`` → instanceDbId 에서 ``filterTemplate`` 동등 비교로
  매칭 record 존재 여부 확인 후 ``condition: 'exists' | 'not_exists'`` 로 분기.

(2026-05-12 재설계) InstanceDB 가 파일시스템으로 이동하면서 dedup_key 기반의
``lookupKeyTemplate`` 매칭은 폐기되었다. 신규 rule 은 ``filterTemplate`` 을
사용한다. ``filterTemplate`` 가 비어있으면 instance_db 의 record 존재 여부만
체크 (1건이라도 있으면 exists 매칭).

후방 호환성:
- 기존 ``{id, field, operator, value}`` 형식(input rule)은 그대로 동작.
- 출력 handle id 형식(``rule-<id>`` / ``default`` / ``__skip__``) 동일.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select as sa_select

from ...core.constants import BeltKey
from ...models.workflow import WarehouseEntry
from ...services.instance_db_store import get_instance_db_store
from ..base import ExecutionContext, NodeHandler
from ..common import render_object, resolve_path
from ..registry import NodeHandlerRegistry


def _matches_filter(record_data: Any, filter_obj: Dict[str, Any]) -> bool:
    if not isinstance(record_data, dict):
        return False
    for path, expected in filter_obj.items():
        if resolve_path(record_data, path) != expected:
            return False
    return True


@NodeHandlerRegistry.register
class SorterHandler(NodeHandler):
    node_type = "sorter"
    category = "logic"
    display_name = "분류기"
    description = "조건 규칙에 따라 데이터를 분류합니다 (입력 평가 / 인스턴스DB lookup 분기)."

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config
        original = input_data

        # ── 중복 필터 (dedup) — warehouse 기반 ─────────────────────────
        dedup_cfg = config.get("dedup", {})
        if dedup_cfg.get("enabled") and dedup_cfg.get("warehouseNodeId") and dedup_cfg.get("matchField"):
            warehouse_node_id = dedup_cfg["warehouseNodeId"]
            match_field = dedup_cfg["matchField"]
            incoming_val = ctx.get_nested_value(original, match_field)

            if incoming_val is not None:
                result = await ctx.db.execute(
                    sa_select(WarehouseEntry).where(
                        WarehouseEntry.node_instance_id == warehouse_node_id
                    )
                )
                existing_entries = result.scalars().all()
                already_exists = any(
                    ctx.get_nested_value(e.data, match_field) == incoming_val
                    for e in existing_entries
                    if isinstance(e.data, dict)
                )
                if already_exists:
                    return {BeltKey.SORTER_HANDLE: "__skip__"}

        # 규칙 순차 평가
        rules = config.get("rules", [])
        matched_handle = "default"
        matched_rule_id: Optional[str] = None
        # (instanceDbId, frozen filter) → 매칭 record 존재 여부. 동일 sorter 실행 내 캐시.
        idb_cache: Dict[Tuple[str, Tuple[Tuple[str, Any], ...]], bool] = {}

        for rule in rules:
            data_source = (rule.get("dataSource") or "input").lower()
            if data_source == "instance-db":
                hit = await self._evaluate_instance_db_rule(
                    rule, original, ctx, idb_cache
                )
            else:
                field = rule.get("field", "")
                operator = rule.get("operator", "equals")
                value = rule.get("value", "")
                actual = ctx.get_nested_value(original, field) if field else None
                hit = self._evaluate_sorter_rule(actual, operator, value)

            if hit:
                matched_handle = f"rule-{rule.get('id', '')}"
                matched_rule_id = rule.get("id") or None
                break

        # 창고에 축적 (분기 결정 후 — __sorterHandle 메타 포함)
        try:
            base = original if isinstance(original, dict) else {"value": original}
            data_payload = {
                **base,
                "__sorterHandle": matched_handle,
                "__matchedRuleId": matched_rule_id,
            }
            entry = WarehouseEntry(
                id=f"wh-{uuid.uuid4().hex[:8]}",
                node_instance_id=node.id,
                execution_id=ctx.execution_id,
                data=data_payload,
            )
            ctx.db.add(entry)
        except Exception:
            pass

        return {BeltKey.SORTER_HANDLE: matched_handle}

    # ── instance-db lookup 평가 ────────────────────────────────────────

    async def _evaluate_instance_db_rule(
        self,
        rule: Dict[str, Any],
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
        idb_cache: Optional[
            Dict[Tuple[str, Tuple[Tuple[str, Any], ...]], bool]
        ] = None,
    ) -> bool:
        """``dataSource: 'instance-db'`` rule 의 매칭 여부 결정.

        필요 필드:
        - instanceDbId: 필수 (빈 문자열/None 이면 rule 무효 — 매칭 실패)
        - filterTemplate: 선택 (없거나 빈 dict 이면 "records 가 1건이라도 있으면 exists")
        - condition: 'exists' (default) | 'not_exists'

        규칙이 잘못 구성된 경우(필드 누락 등)는 매칭 실패로 처리하여 다음 rule /
        default handle 로 흐르게 한다 (예외 미발생).

        파일시스템 store 의존: InstanceDB 폴더 자체가 없으면 record 도 없으므로
        - 'exists' → 미매칭 (False)
        - 'not_exists' → 매칭 (True)
        와 같이 일관 동작.
        """
        instance_db_id = rule.get("instanceDbId")
        condition = (rule.get("condition") or "exists").lower()

        if not instance_db_id or not isinstance(instance_db_id, str):
            return False
        if condition not in ("exists", "not_exists"):
            return False

        filter_template = rule.get("filterTemplate")
        if filter_template is None:
            filter_template = {}
        if not isinstance(filter_template, dict):
            return False

        # 템플릿 값 렌더 (단일 {{var}} → 타입 보존)
        rendered_filter = render_object(filter_template, input_data, ctx.render_template)
        if not isinstance(rendered_filter, dict):
            return False

        # 캐시 키 — 동일 sorter 내 동일 rule 반복 호출 (없지만 방어적)
        try:
            cache_key = (
                instance_db_id,
                tuple(sorted(rendered_filter.items(), key=lambda kv: kv[0])),
            )
        except TypeError:
            cache_key = None  # 값이 hashable 하지 않으면 캐시 미적용

        if cache_key is not None and idb_cache is not None and cache_key in idb_cache:
            record_exists = idb_cache[cache_key]
        else:
            record_exists = await self._has_matching_record(
                instance_db_id, rendered_filter
            )
            if cache_key is not None and idb_cache is not None:
                idb_cache[cache_key] = record_exists

        return record_exists if condition == "exists" else (not record_exists)

    async def _has_matching_record(
        self, instance_db_id: str, rendered_filter: Dict[str, Any]
    ) -> bool:
        """파일시스템 store 에서 매칭 record 1건이라도 있는지 확인.

        InstanceDB 폴더 자체가 없으면 ``KeyError`` → False 반환 (record 없음 동일).
        """
        store = get_instance_db_store()
        try:
            records, _total = await store.list_records(
                instance_db_id, limit=10**9, offset=0
            )
        except KeyError:
            return False
        for rec in records:
            data = rec.get("data")
            if isinstance(data, dict) and _matches_filter(data, rendered_filter):
                return True
            elif not isinstance(data, dict) and _matches_filter({"value": data}, rendered_filter):
                return True
        return False

    # ── 입력 평가(기존) ────────────────────────────────────────────────

    def _evaluate_sorter_rule(self, actual: Any, operator: str, value: str) -> bool:
        """분류기 규칙 평가 (입력 dict 기반)."""
        if operator == "exists":
            return actual is not None
        if operator == "notExists":
            return actual is None

        if actual is None:
            return False

        actual_str = str(actual)

        if operator == "equals":
            return actual_str == value or actual == value
        elif operator == "notEquals":
            return actual_str != value and actual != value
        elif operator == "contains":
            return value in actual_str
        elif operator == "startsWith":
            return actual_str.startswith(value)
        elif operator == "endsWith":
            return actual_str.endswith(value)
        elif operator == "greaterThan":
            try:
                return float(actual) > float(value)
            except (ValueError, TypeError):
                return False
        elif operator == "lessThan":
            try:
                return float(actual) < float(value)
            except (ValueError, TypeError):
                return False
        elif operator == "regex":
            try:
                return bool(re.search(value, actual_str))
            except re.error:
                return False

        return False
