"""스위치 노드 핸들러"""
from typing import Any, Dict

from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class SwitchHandler(NodeHandler):
    node_type = "switch"
    category = "logic"
    display_name = "스위치"
    description = "값에 따라 분기합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config
        switch_field = config.get('switchField', '')
        cases = config.get('cases', [])

        value = ctx.get_nested_value(input_data, switch_field)

        for case in cases:
            if case.get('value') == value:
                return {"matched": True, "case": case.get('value')}

        return {"matched": False, "case": "default"}
