"""변수 설정 노드 핸들러"""
from typing import Any, Dict

from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class SetVariableHandler(NodeHandler):
    node_type = "set-variable"
    category = "transform"
    display_name = "변수 설정"
    description = "변수를 설정합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config
        variables = config.get('variables', [])
        result = {}

        for var in variables:
            name = var.get('name', '')
            value = var.get('value', '')

            # 템플릿 렌더링
            rendered = ctx.render_template(value, input_data)
            result[name] = rendered

        return result
