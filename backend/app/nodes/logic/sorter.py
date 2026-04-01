"""분류기 노드 핸들러 — 조건 분기 + 창고 보관 + 중복 필터"""
import re
import uuid
from typing import Any, Dict

from sqlalchemy import select as sa_select

from ...core.constants import BeltKey
from ...models.workflow import WarehouseEntry
from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class SorterHandler(NodeHandler):
    node_type = "sorter"
    category = "logic"
    display_name = "분류기"
    description = "조건 규칙에 따라 데이터를 분류합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config
        original = input_data

        # ── 중복 필터 (dedup) ──────────────────────────────────────────
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

        # 창고에 축적
        try:
            entry = WarehouseEntry(
                id=f"wh-{uuid.uuid4().hex[:8]}",
                node_instance_id=node.id,
                execution_id=ctx.execution_id,
                data=original if isinstance(original, dict) else {"value": original},
            )
            ctx.db.add(entry)
        except Exception:
            pass

        # 규칙 순차 평가
        rules = config.get("rules", [])
        matched_handle = "default"

        for rule in rules:
            field = rule.get("field", "")
            operator = rule.get("operator", "equals")
            value = rule.get("value", "")
            actual = ctx.get_nested_value(original, field) if field else None

            if self._evaluate_sorter_rule(actual, operator, value):
                matched_handle = f"rule-{rule.get('id', '')}"
                break

        return {BeltKey.SORTER_HANDLE: matched_handle}

    def _evaluate_sorter_rule(self, actual: Any, operator: str, value: str) -> bool:
        """분류기 규칙 평가"""
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
