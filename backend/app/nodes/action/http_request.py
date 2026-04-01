"""HTTP 요청 노드 핸들러"""
from typing import Any, Dict

import httpx

from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class HttpRequestHandler(NodeHandler):
    node_type = "http-request"
    category = "action"
    display_name = "HTTP 요청"
    description = "HTTP 요청을 실행합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config
        method = config.get('method', 'GET')
        url = ctx.render_template(config.get('url', ''), input_data)
        headers = {
            k: ctx.render_template(v, input_data)
            for k, v in config.get('headers', {}).items()
        }
        body = ctx.render_template(config.get('body', ''), input_data) if config.get('body') else None

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                content=body,
            )

            try:
                return {"status": response.status_code, "data": response.json()}
            except Exception:
                return {"status": response.status_code, "data": response.text}
