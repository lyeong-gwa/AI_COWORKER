"""루프 노드 핸들러"""
from typing import Any, Dict, List

from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class LoopHandler(NodeHandler):
    node_type = "loop"
    category = "logic"
    display_name = "루프"
    description = "반복 실행합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        # TODO: 루프 구현
        return []
