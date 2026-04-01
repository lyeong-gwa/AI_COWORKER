"""코드 실행 노드 핸들러"""
from typing import Any, Dict

from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class CodeHandler(NodeHandler):
    node_type = "code"
    category = "transform"
    display_name = "코드"
    description = "코드를 실행합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        from ...sandbox import execute_code

        config = node.config
        code = config.get('code', '')
        result = execute_code(code, input_data, 'result')

        if result.success:
            return result.output
        else:
            raise RuntimeError(f"코드 실행 실패: {result.error}")
