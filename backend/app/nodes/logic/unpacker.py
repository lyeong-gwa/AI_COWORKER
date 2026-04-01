"""언패커 노드 핸들러 — 배열을 개별 객체로 분해"""
from typing import Any, Dict

from ...core.constants import BeltKey
from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class UnpackerHandler(NodeHandler):
    node_type = "unpacker"
    category = "logic"
    display_name = "언패커"
    description = "배열 필드를 개별 객체로 분해합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config
        array_field = config.get("arrayField", "")

        if not array_field:
            raise ValueError("언패커: arrayField가 설정되지 않았습니다")

        # Resolve array from input data
        value = ctx.get_nested_value(input_data, array_field)

        if not isinstance(value, list):
            raise ValueError(
                f"언패커: '{array_field}' 필드가 배열이 아닙니다 (타입: {type(value).__name__})"
            )

        return {
            "items": value,
            "count": len(value),
            BeltKey.UNPACK_ITEMS: value,
        }
