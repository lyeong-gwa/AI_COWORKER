"""JSON 파싱 노드 핸들러"""
import json
from typing import Any, Dict

from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class JsonParseHandler(NodeHandler):
    node_type = "json-parse"
    category = "transform"
    display_name = "JSON 파싱"
    description = "JSON 문자열을 파싱합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config
        source = config.get('source', '')
        value = ctx.get_nested_value(input_data, source)

        if isinstance(value, str):
            return json.loads(value)
        return value
