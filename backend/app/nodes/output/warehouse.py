"""결과/마크다운 뷰어 노드 핸들러 — pass-through + 창고에 축적"""
import uuid
from typing import Any, Dict

from ...models.workflow import WarehouseEntry
from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class WarehouseHandler(NodeHandler):
    node_type = "result"
    category = "output"
    display_name = "결과"
    description = "결과를 저장합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        output = input_data

        # 창고에 축적
        try:
            entry = WarehouseEntry(
                id=f"wh-{uuid.uuid4().hex[:8]}",
                node_instance_id=node.id,
                execution_id=ctx.execution_id,
                data=output if isinstance(output, dict) else {"value": output},
            )
            ctx.db.add(entry)
        except Exception:
            pass  # 창고 저장 실패해도 실행은 계속

        return output


# markdown-viewer도 동일 핸들러로 등록
_cls = type(
    "MarkdownViewerHandler",
    (WarehouseHandler,),
    {"node_type": "markdown-viewer", "display_name": "마크다운 뷰어"},
)
NodeHandlerRegistry.register(_cls)
