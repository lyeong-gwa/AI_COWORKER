"""폼 시작 노드 핸들러"""
from typing import Any, Dict

from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class FormStartHandler(NodeHandler):
    node_type = "form-start"
    category = "trigger"
    display_name = "폼 시작"
    description = "폼 데이터로 워크플로우를 시작합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        return input_data


# Legacy "form" 타입도 동일 핸들러로 등록
_legacy = type(
    "FormLegacyHandler",
    (FormStartHandler,),
    {"node_type": "form", "display_name": "폼 (레거시)"},
)
NodeHandlerRegistry.register(_legacy)
