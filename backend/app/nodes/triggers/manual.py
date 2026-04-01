"""트리거 노드 핸들러 — manual, schedule, webhook, form (패스스루)"""
from typing import Any, Dict

from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class ManualHandler(NodeHandler):
    node_type = "manual"
    category = "trigger"
    display_name = "수동 실행"
    description = "수동으로 워크플로우를 시작합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        return input_data


# 동일 핸들러를 다른 타입으로 등록
for _type in ["schedule", "webhook", "form"]:
    _cls = type(
        f"{_type.title()}Handler",
        (ManualHandler,),
        {"node_type": _type, "display_name": _type},
    )
    NodeHandlerRegistry.register(_cls)
