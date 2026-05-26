"""인스턴스DB 조회 노드 핸들러 — 파일시스템 저장 (재설계 후).

설계서: ``docs/instance-db-fs-redesign.md``.

config:
    instanceDbId: str (필수) — 대상 InstanceDB id (idb-...)
    filterTemplate: dict (선택) — 비어있거나 None 이면 모두 매칭.
                    각 값을 ``{{var}}`` 치환한 뒤 record.data 와 dot-path 동등 비교.
    limit: int (default 10)

출력:
    {
        "found": bool,                # count > 0
        "count": int,                 # 매칭 개수
        "record": dict | None,        # 첫 매칭 record.data
        "records": list[dict],        # 매칭 record.data 배열
        "instanceDbId": str,
    }

제거된 기능 (구 설계):
- by_key 모드 + keyTemplate + compute_dedup_key (filter 만 남음)

동작:
1. 폴더 존재 확인 (없으면 ValueError)
2. filterTemplate 렌더 (없거나 빈 dict면 모두 매칭)
3. store.list_records() 로 createdAt 내림차순 record 들을 받아
   in-memory AND 매칭 + limit 적용
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...services.instance_db_store import get_instance_db_store
from ..base import ExecutionContext, NodeHandler
from ..common import render_object, resolve_path
from ..registry import NodeHandlerRegistry


def _matches_filter(record_data: Any, filter_obj: Dict[str, Any]) -> bool:
    """filter_obj 의 모든 (key, value) 쌍이 record_data 와 매칭되는지 AND 평가.

    key 는 dot-path 로 해석 (``a.b.c``). 값은 단순 동등 비교 (==).
    record_data 가 dict 이 아니면 항상 미매칭.
    """
    if not isinstance(record_data, dict):
        return False
    for path, expected in filter_obj.items():
        actual = resolve_path(record_data, path)
        if actual != expected:
            return False
    return True


@NodeHandlerRegistry.register
class InstanceDBLookupHandler(NodeHandler):
    """인스턴스DB 조회 핸들러 — filter 다건 (in-memory AND)."""

    node_type = "instance-db-lookup"
    category = "action"
    display_name = "인스턴스DB 조회"
    description = "지정 InstanceDB 에서 filterTemplate 동등 비교로 record 다건 조회."

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config or {}

        instance_db_id = config.get("instanceDbId")
        if not instance_db_id:
            raise ValueError("instance-db-lookup: config.instanceDbId 가 필수입니다")

        store = get_instance_db_store()

        # 1. 폴더 존재 확인
        meta = await store.get_meta(instance_db_id)
        if meta is None:
            raise ValueError(f"InstanceDB not found: {instance_db_id}")

        # 2. filterTemplate 처리
        filter_template = config.get("filterTemplate")
        if filter_template is None:
            filter_template = {}
        if not isinstance(filter_template, dict):
            raise ValueError(
                "instance-db-lookup: filterTemplate 은 객체(dict)여야 합니다"
            )

        rendered_filter = render_object(filter_template, input_data, ctx.render_template)
        if not isinstance(rendered_filter, dict):
            # render_object 는 dict 입력에 dict 를 반환하므로 사실상 도달 불가
            raise ValueError(
                "instance-db-lookup: filterTemplate 렌더 결과가 객체가 아닙니다"
            )

        # 3. limit
        limit_raw = config.get("limit", 10)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 10
        if limit <= 0:
            limit = 10

        # 4. 폴더 전체 records 로드 (createdAt 내림차순) + AND 매칭
        # in-memory limit 만 적용 — store list_records 의 limit/offset 은 사용하지 않음
        # (필터링 후 개수가 limit 미만이 될 수 있으므로 전체 로드 후 매칭).
        all_records, _total = await store.list_records(
            instance_db_id, limit=10**9, offset=0
        )

        matched: List[Dict[str, Any]] = []
        for rec in all_records:
            data = rec.get("data")
            if not isinstance(data, dict):
                data_dict = {"value": data}
            else:
                data_dict = data
            if _matches_filter(data_dict, rendered_filter):
                matched.append(data_dict)
                if len(matched) >= limit:
                    break

        first = matched[0] if matched else None
        return {
            "found": len(matched) > 0,
            "count": len(matched),
            "record": first,
            "records": matched,
            "instanceDbId": instance_db_id,
        }
