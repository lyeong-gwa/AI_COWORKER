"""매퍼 노드 핸들러 — 창고 데이터에서 매칭 키로 관련 항목을 조회하여 병합"""
from typing import Any, Dict, List

from sqlalchemy import select

from ...models.workflow import WarehouseEntry
from ...core.constants import BeltKey
from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class MapperHandler(NodeHandler):
    node_type = "mapper"
    category = "logic"
    display_name = "매퍼"
    description = "창고 데이터에서 동일한 키 값을 가진 항목을 조회하여 입력에 병합합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config or {}
        warehouse_node_id = config.get("warehouseNodeId", "")
        match_key = config.get("matchKey", "")
        output_field = config.get("outputField", "matchedItems")

        if not warehouse_node_id:
            raise ValueError("매퍼: 창고 노드가 설정되지 않았습니다")
        if not match_key:
            raise ValueError("매퍼: 매칭 키가 설정되지 않았습니다")

        # 입력 데이터에서 매칭 키 값 추출 (dot path 지원)
        match_value = ctx.get_nested_value(input_data, match_key)
        if match_value is None:
            # 매칭 값이 없으면 빈 배열로 반환
            return {**input_data, output_field: []}

        # 창고에서 해당 노드의 모든 데이터 조회
        result = await ctx.db.execute(
            select(WarehouseEntry)
            .where(WarehouseEntry.node_instance_id == warehouse_node_id)
            .order_by(WarehouseEntry.created_at.desc())
        )
        entries: List[WarehouseEntry] = list(result.scalars().all())

        # 매칭 키로 필터링
        matched: List[Dict[str, Any]] = []
        for entry in entries:
            entry_data = entry.data or {}
            entry_value = _get_nested(entry_data, match_key)
            if entry_value is not None and entry_value == match_value:
                matched.append(entry_data)

        # 원본 입력에 매칭 결과 병합
        output = {**input_data, output_field: matched, "matchedCount": len(matched)}
        return output


def _get_nested(data: dict, path: str) -> Any:
    """점 구분 경로로 중첩 dict에서 값 추출"""
    value = data
    for key in path.split("."):
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return None
    return value
