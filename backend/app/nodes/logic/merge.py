"""병합 노드 핸들러"""
from typing import Any, Dict

from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class MergeHandler(NodeHandler):
    node_type = "merge"
    category = "logic"
    display_name = "병합"
    description = "여러 입력을 하나로 병합합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        merged = {}
        for key, value in input_data.items():
            if key != "trigger":
                if isinstance(value, dict):
                    merged.update(value)
                else:
                    merged[key] = value
        return merged
