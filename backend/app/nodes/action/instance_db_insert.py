"""인스턴스DB 적재 노드 핸들러 — 파일시스템 저장 (재설계 후).

설계서: ``docs/instance-db-fs-redesign.md``.

config:
    instanceDbId: str (필수) — 대상 InstanceDB id (idb-...)
    sourceMode: 'warehouse' | 'input' | 'auto' (default 'auto')
        warehouse: 입력의 warehouseEntryId/entryId 가 가리키는 WarehouseEntry.data 를
                   record 본체로 사용
        input:     dataTemplate({{var}} 치환) 결과를 record 본체로 사용.
                   없으면 입력 dict 자체.
        auto:      입력에 warehouseEntryId/entryId 가 있으면 warehouse, 없으면 input.
    dataTemplate: dict (선택) — input 모드의 record 본체 템플릿

출력:
    {
        "recordId": str,
        "instanceDbId": str,
    }

제거된 기능 (구 설계):
- JSON Schema 검증 (자유 JSON)
- dedupKeyTemplate / skipOnDuplicate (중복 차단은 노드/사용자 책임)

동작:
1. InstanceDB 폴더 존재 확인 (없으면 ValueError)
2. sourceMode 분기로 record_data 결정
3. ``_source = {workflowId, executionId, warehouseId}`` 구성
4. store.insert_record() 호출 — ``rec-{8hex}.json`` 원자적 생성
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import select

from ...models.workflow import WarehouseEntry
from ...services.instance_db_store import get_instance_db_store
from ..base import ExecutionContext, NodeHandler
from ..common import render_object, resolve_warehouse_entry_id
from ..registry import NodeHandlerRegistry


@NodeHandlerRegistry.register
class InstanceDBInsertHandler(NodeHandler):
    """인스턴스DB 적재 핸들러 — 파일시스템 store 의존."""

    node_type = "instance-db-insert"
    category = "action"
    display_name = "인스턴스DB 적재"
    description = "지정 InstanceDB 폴더에 record(JSON 파일)를 적재한다."

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config or {}

        instance_db_id = config.get("instanceDbId")
        if not instance_db_id:
            raise ValueError("instance-db-insert: config.instanceDbId 가 필수입니다")

        store = get_instance_db_store()

        # 1. InstanceDB 메타 폴더 존재 확인
        meta = await store.get_meta(instance_db_id)
        if meta is None:
            raise ValueError(f"InstanceDB not found: {instance_db_id}")

        source_mode = (config.get("sourceMode") or "auto").lower()
        if source_mode not in ("warehouse", "input", "auto"):
            raise ValueError(
                f"instance-db-insert: 알 수 없는 sourceMode={source_mode!r} "
                "(warehouse|input|auto 중 하나)"
            )

        # 2. record 본체 결정
        warehouse_entry_id: Optional[str] = None
        record_data: Dict[str, Any]

        if source_mode == "auto":
            entry_id = resolve_warehouse_entry_id(input_data)
            effective_mode = "warehouse" if entry_id else "input"
        else:
            effective_mode = source_mode

        if effective_mode == "warehouse":
            entry_id = resolve_warehouse_entry_id(input_data)
            if not entry_id:
                raise ValueError(
                    "instance-db-insert: warehouse 모드에는 입력의 warehouseEntryId "
                    "또는 entryId 가 필요합니다"
                )
            we_row = await ctx.db.execute(
                select(WarehouseEntry).where(WarehouseEntry.id == entry_id)
            )
            warehouse_entry: Optional[WarehouseEntry] = we_row.scalar_one_or_none()
            if warehouse_entry is None:
                raise ValueError(
                    f"instance-db-insert: WarehouseEntry not found: {entry_id}"
                )
            record_data = (
                warehouse_entry.data
                if isinstance(warehouse_entry.data, dict)
                else {"value": warehouse_entry.data}
            )
            warehouse_entry_id = entry_id
        else:
            # input 모드
            data_template = config.get("dataTemplate")
            if data_template:
                rendered = render_object(data_template, input_data, ctx.render_template)
                if not isinstance(rendered, dict):
                    raise ValueError(
                        "instance-db-insert: dataTemplate 렌더 결과가 객체가 아닙니다"
                    )
                record_data = rendered
            else:
                if not isinstance(input_data, dict):
                    raise ValueError(
                        "instance-db-insert: input 모드에서 dataTemplate 가 없으면 "
                        "입력이 dict 여야 합니다"
                    )
                record_data = dict(input_data)

        # 3. _source 구성 — workflowId 는 node.workflow_id, executionId 는 ctx
        source = {
            "workflowId": getattr(node, "workflow_id", None),
            "executionId": ctx.execution_id,
            "warehouseId": warehouse_entry_id,
        }

        # 4. 파일시스템에 적재 (원자적 write-then-rename)
        record = await store.insert_record(
            instance_db_id, data=record_data, source=source
        )

        return {
            "recordId": record["id"],
            "instanceDbId": instance_db_id,
        }
