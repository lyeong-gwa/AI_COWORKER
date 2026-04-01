"""로그 출력 노드 핸들러"""
from typing import Any, Dict

from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class OutputLogHandler(NodeHandler):
    node_type = "output-log"
    category = "output"
    display_name = "로그 출력"
    description = "로그를 출력합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config
        message = ctx.render_template(config.get('message', ''), input_data)
        return {"logged": True, "message": message}
