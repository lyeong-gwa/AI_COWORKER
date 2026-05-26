"""창고 조회 노드 — 이전 워크플로우 실행에서 저장된 WarehouseEntry를 조회."""
from typing import Any, Dict

from sqlalchemy import select

from ...models.workflow import WarehouseEntry
from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext
from ..common import compute_dedup_key


def _entry_to_dict(e: WarehouseEntry) -> Dict[str, Any]:
    return {
        "id": e.id,
        "nodeInstanceId": e.node_instance_id,
        "executionId": e.execution_id,
        "dedupKey": e.dedup_key,
        "data": e.data,
        "createdAt": e.created_at.isoformat() if e.created_at else None,
    }


@NodeHandlerRegistry.register
class WarehouseQueryHandler(NodeHandler):
    node_type = "warehouse-query"
    category = "action"
    display_name = "창고 조회"
    description = "이전 실행 결과(창고)에서 dedupKey 기반 중복 여부를 확인합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config or {}
        source_node_id = config.get("sourceNodeId")
        dedup_template = config.get("dedupKey")
        mode = config.get("mode", "exists")
        limit = int(config.get("limit", 10) or 10)

        hashed = compute_dedup_key(dedup_template, input_data, ctx.render_template)

        if not hashed:
            # 키가 없으면 조회 의미 없음 → exists=false로 처리
            if mode == "list":
                return {"exists": False, "existsFlag": "miss", "entries": [], "count": 0}
            return {"exists": False, "existsFlag": "miss", "entry": None}

        stmt = select(WarehouseEntry).where(WarehouseEntry.dedup_key == hashed)
        if source_node_id:
            stmt = stmt.where(WarehouseEntry.node_instance_id == source_node_id)
        stmt = stmt.order_by(WarehouseEntry.created_at.desc())

        if mode == "list":
            stmt = stmt.limit(limit)
            rows = (await ctx.db.execute(stmt)).scalars().all()
            entries = [_entry_to_dict(e) for e in rows]
            exists = len(entries) > 0
            return {
                "exists": exists,
                "existsFlag": "hit" if exists else "miss",
                "entries": entries,
                "count": len(entries),
            }

        # exists / latest
        row = (await ctx.db.execute(stmt.limit(1))).scalars().first()
        if row is None:
            return {"exists": False, "existsFlag": "miss", "entry": None}

        entry_dict = _entry_to_dict(row)
        result: Dict[str, Any] = {
            "exists": True,
            "existsFlag": "hit",
            "entry": entry_dict,
        }

        if mode == "latest" and isinstance(row.data, dict):
            # data의 키들을 최상위로도 풀어서 다운스트림에서 참조 용이
            for k, v in row.data.items():
                if k not in result:
                    result[k] = v

        return result
