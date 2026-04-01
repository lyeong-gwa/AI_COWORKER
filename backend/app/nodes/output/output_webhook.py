"""웹훅 출력 노드 핸들러"""
from typing import Any, Dict

import httpx

from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class OutputWebhookHandler(NodeHandler):
    node_type = "output-webhook"
    category = "output"
    display_name = "웹훅 출력"
    description = "웹훅으로 데이터를 전송합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config
        url = ctx.render_template(config.get('url', ''), input_data)
        payload = input_data

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload)
            return {"status": response.status_code, "sent": True}
