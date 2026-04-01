"""이메일 발송 노드 핸들러"""
from typing import Any, Dict

from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class SendEmailHandler(NodeHandler):
    node_type = "send-email"
    category = "action"
    display_name = "이메일 발송"
    description = "이메일을 발송합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        # TODO: 이메일 발송 구현
        return {"sent": False, "message": "이메일 발송 기능이 구현되지 않았습니다"}
