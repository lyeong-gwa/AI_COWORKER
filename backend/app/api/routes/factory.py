"""
Factory Map API Routes - Factorio-style singleton factory map
"""

from typing import Optional, AsyncGenerator, List
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
import uuid
import json
import asyncio

from ...core.database import get_db
from ...models.workflow import (
    Workflow, WorkflowNode, WorkflowConnection, WorkflowExecution,
    WorkflowStatus, ExecutionStatus, WarehouseEntry,
    NodeQueueItem, QueueItemStatus,
)
from ...schemas.workflow import (
    FactoryMapUpdate, ExecutionCreate,
)
from ...services.workflow_engine import execute_workflow

router = APIRouter()

FACTORY_MAP_ID = "factory-main"


class DeleteEntriesBody(BaseModel):
    """창고 항목 선택 삭제 요청 바디"""
    entryIds: List[str]


# ─────────────────────────────────────────────────────────────────────────────
# Serializers (reused from workflows.py pattern)
# ─────────────────────────────────────────────────────────────────────────────

def workflow_node_to_camel(node: WorkflowNode) -> dict:
    """WorkflowNode ORM -> camelCase dict"""
    return {
        "id": node.id,
        "nodeId": node.node_id,
        "definitionType": node.definition_type,
        "aiNodeId": node.ai_node_id,
        "config": node.config,
        "name": node.name,
        "orderIndex": node.order_index,
        "configOverrides": node.config_overrides,
        "inputMapping": node.input_mapping,
    }


def workflow_connection_to_camel(conn: WorkflowConnection) -> dict:
    """WorkflowConnection ORM -> camelCase dict"""
    return {
        "id": conn.id,
        "sourceNodeId": conn.source_node_id,
        "targetNodeId": conn.target_node_id,
        "sourceHandle": conn.source_handle,
        "targetHandle": conn.target_handle,
        "condition": conn.condition,
    }


def factory_map_to_camel(wf: Workflow) -> dict:
    """Factory map ORM -> camelCase dict"""
    return {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description,
        "status": wf.status.value if wf.status else None,
        "tags": wf.tags,
        "trigger": wf.trigger,
        "variables": wf.variables,
        "createdBy": wf.created_by,
        "nodes": [workflow_node_to_camel(n) for n in wf.nodes],
        "connections": [workflow_connection_to_camel(c) for c in wf.connections],
        "createdAt": wf.created_at.isoformat() if wf.created_at else None,
        "updatedAt": wf.updated_at.isoformat() if wf.updated_at else None,
    }


def execution_to_camel(ex: WorkflowExecution) -> dict:
    """WorkflowExecution ORM -> camelCase dict"""
    return {
        "id": ex.id,
        "workflowId": ex.workflow_id,
        "status": ex.status.value if ex.status else None,
        "inputData": ex.input_data,
        "outputData": ex.output_data,
        "nodeResults": ex.node_results,
        "errorMessage": ex.error_message,
        "errorNodeId": ex.error_node_id,
        "startedAt": ex.started_at.isoformat() if ex.started_at else None,
        "completedAt": ex.completed_at.isoformat() if ex.completed_at else None,
        "createdAt": ex.created_at.isoformat() if ex.created_at else None,
    }


def warehouse_entry_to_camel(entry: WarehouseEntry) -> dict:
    """WarehouseEntry ORM -> camelCase dict"""
    return {
        "id": entry.id,
        "nodeInstanceId": entry.node_instance_id,
        "executionId": entry.execution_id,
        "data": entry.data,
        "createdAt": entry.created_at.isoformat() if entry.created_at else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Factory Map (Singleton)
# ─────────────────────────────────────────────────────────────────────────────

async def _get_or_create_factory(db: AsyncSession) -> Workflow:
    """싱글톤 팩토리 맵 조회 (없으면 자동 생성)"""
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.nodes), selectinload(Workflow.connections))
        .where(Workflow.id == FACTORY_MAP_ID)
    )
    wf = result.scalar_one_or_none()

    if not wf:
        wf = Workflow(
            id=FACTORY_MAP_ID,
            name="공장 맵",
            description="Factorio 스타일 싱글톤 공장 맵",
            status=WorkflowStatus.ACTIVE,
            trigger={"type": "manual", "config": {}},
            variables={},
            tags=[],
            created_by="cli",
        )
        db.add(wf)
        await db.commit()
        # Reload with relationships
        result = await db.execute(
            select(Workflow)
            .options(selectinload(Workflow.nodes), selectinload(Workflow.connections))
            .where(Workflow.id == FACTORY_MAP_ID)
        )
        wf = result.scalar_one()

    return wf


@router.get("")
async def get_factory_map(db: AsyncSession = Depends(get_db)):
    """싱글톤 팩토리 맵 조회 (없으면 자동 생성)"""
    wf = await _get_or_create_factory(db)
    return factory_map_to_camel(wf)


@router.patch("")
async def update_factory_map(
    data: FactoryMapUpdate,
    db: AsyncSession = Depends(get_db),
):
    """팩토리 맵 저장 (노드, 연결)"""
    wf = await _get_or_create_factory(db)

    # 노드 업데이트 (전체 교체)
    if data.nodes is not None:
        for node in wf.nodes:
            await db.delete(node)

        for idx, node_data in enumerate(data.nodes):
            node = WorkflowNode(
                id=node_data.id,
                workflow_id=FACTORY_MAP_ID,
                node_id=node_data.nodeId,
                definition_type=node_data.definitionType,
                ai_node_id=node_data.aiNodeId,
                config=node_data.config,
                name=node_data.name,
                order_index=node_data.orderIndex if node_data.orderIndex else idx,
                config_overrides=node_data.configOverrides,
                input_mapping=node_data.inputMapping,
            )
            db.add(node)

    # 연결선 업데이트 (전체 교체)
    if data.connections is not None:
        for conn in wf.connections:
            await db.delete(conn)

        for conn_data in data.connections:
            conn = WorkflowConnection(
                id=conn_data.id,
                workflow_id=FACTORY_MAP_ID,
                source_node_id=conn_data.sourceNodeId,
                target_node_id=conn_data.targetNodeId,
                source_handle=conn_data.sourceHandle,
                target_handle=conn_data.targetHandle,
                condition=conn_data.condition.model_dump() if conn_data.condition else None,
            )
            db.add(conn)

    await db.commit()

    # 다시 조회
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.nodes), selectinload(Workflow.connections))
        .where(Workflow.id == FACTORY_MAP_ID)
    )
    wf = result.scalar_one()
    return factory_map_to_camel(wf)


@router.delete("/nodes/{node_id}", status_code=204)
async def delete_factory_node(node_id: str, db: AsyncSession = Depends(get_db)):
    """팩토리 맵에서 노드 삭제"""
    result = await db.execute(
        select(WorkflowNode).where(
            WorkflowNode.id == node_id,
            WorkflowNode.workflow_id == FACTORY_MAP_ID,
        )
    )
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="노드를 찾을 수 없습니다")

    # 관련 연결선도 삭제
    conn_result = await db.execute(
        select(WorkflowConnection).where(
            WorkflowConnection.workflow_id == FACTORY_MAP_ID,
            (WorkflowConnection.source_node_id == node_id) | (WorkflowConnection.target_node_id == node_id),
        )
    )
    for conn in conn_result.scalars().all():
        await db.delete(conn)

    await db.delete(node)
    await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Factory Execution
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/execute")
async def execute_factory(
    request: ExecutionCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """팩토리 맵 전체 실행"""
    wf = await _get_or_create_factory(db)

    if not wf.nodes:
        raise HTTPException(status_code=400, detail="실행할 노드가 없습니다")

    # 실행 레코드 생성
    execution = WorkflowExecution(
        id=f"exec-{uuid.uuid4().hex[:8]}",
        workflow_id=FACTORY_MAP_ID,
        status=ExecutionStatus.PENDING,
        input_data=request.inputData,
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    # 백그라운드에서 실행
    background_tasks.add_task(execute_workflow, execution.id)

    return execution_to_camel(execution)


@router.get("/executions")
async def list_factory_executions(
    status: Optional[ExecutionStatus] = Query(None),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """팩토리 실행 이력"""
    query = select(WorkflowExecution).where(
        WorkflowExecution.workflow_id == FACTORY_MAP_ID
    )

    if status:
        query = query.where(WorkflowExecution.status == status)

    query = query.order_by(WorkflowExecution.created_at.desc()).limit(limit)
    result = await db.execute(query)

    executions = result.scalars().all()
    return [execution_to_camel(ex) for ex in executions]


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: str, db: AsyncSession = Depends(get_db)):
    """실행 상세 조회"""
    result = await db.execute(
        select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
    )
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(status_code=404, detail="실행 기록을 찾을 수 없습니다")

    return execution_to_camel(execution)


@router.get("/executions/{execution_id}/stream")
async def stream_execution(execution_id: str, db: AsyncSession = Depends(get_db)):
    """실행 로그 스트리밍 (SSE)"""
    result = await db.execute(
        select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
    )
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(status_code=404, detail="실행 기록을 찾을 수 없습니다")

    async def event_generator() -> AsyncGenerator[str, None]:
        """SSE 이벤트 생성기"""
        while True:
            db.expire_all()
            result = await db.execute(
                select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
            )
            current = result.scalar_one_or_none()

            if not current:
                break

            event_data = {
                "status": current.status.value,
                "nodeResults": current.node_results,
            }
            yield f"data: {json.dumps(event_data, default=str)}\n\n"

            if current.status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED]:
                final_data = {
                    "status": current.status.value,
                    "output": current.output_data,
                    "error": current.error_message,
                }
                yield f"data: {json.dumps(final_data, default=str)}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(execution_id: str, db: AsyncSession = Depends(get_db)):
    """실행 취소"""
    result = await db.execute(
        select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
    )
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(status_code=404, detail="실행 기록을 찾을 수 없습니다")

    if execution.status not in [ExecutionStatus.PENDING, ExecutionStatus.RUNNING]:
        raise HTTPException(status_code=400, detail="취소할 수 없는 상태입니다")

    execution.status = ExecutionStatus.CANCELLED
    await db.commit()

    return {"message": "실행이 취소되었습니다"}


# ─────────────────────────────────────────────────────────────────────────────
# Warehouse (창고 데이터)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/warehouse/{node_id}")
async def get_warehouse_data(
    node_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    execution_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """특정 결과 노드(창고)의 축적 데이터 조회.

    execution_id 가 주어지면 해당 실행분만 필터링 (1실행 1결과 원칙).
    주어지지 않으면 기존 동작(누적 전체) 유지.
    """
    base_filter = WarehouseEntry.node_instance_id == node_id
    if execution_id is not None:
        from sqlalchemy import and_
        base_filter = and_(base_filter, WarehouseEntry.execution_id == execution_id)

    # 총 개수 조회 (동일 필터 적용)
    count_result = await db.execute(
        select(func.count()).where(base_filter)
    )
    total = count_result.scalar() or 0

    # 데이터 조회
    query = (
        select(WarehouseEntry)
        .where(base_filter)
        .order_by(WarehouseEntry.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    entries = result.scalars().all()

    return {
        "items": [warehouse_entry_to_camel(e) for e in entries],
        "total": total,
        "nodeInstanceId": node_id,
    }


@router.delete("/warehouse/{node_id}", status_code=204)
async def clear_warehouse(
    node_id: str,
    execution_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """창고 비우기.

    execution_id 가 주어지면 해당 실행분만 삭제, 없으면 전체 삭제.
    """
    base_filter = WarehouseEntry.node_instance_id == node_id
    if execution_id is not None:
        from sqlalchemy import and_
        base_filter = and_(base_filter, WarehouseEntry.execution_id == execution_id)

    result = await db.execute(
        select(WarehouseEntry).where(base_filter)
    )
    entries = result.scalars().all()

    for entry in entries:
        await db.delete(entry)

    await db.commit()


@router.delete("/warehouse/{node_id}/entries", status_code=204)
async def delete_warehouse_entries(
    node_id: str,
    body: DeleteEntriesBody = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """창고 항목 선택 삭제.

    요청 바디: {"entryIds": ["wh-xxx", "wh-yyy", ...]}
    응답: 204 No Content
    """
    result = await db.execute(
        select(WarehouseEntry).where(
            WarehouseEntry.node_instance_id == node_id,
            WarehouseEntry.id.in_(body.entryIds),
        )
    )
    entries = result.scalars().all()

    for entry in entries:
        await db.delete(entry)

    await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Node Queue (공장 노드 입력 큐)
# ─────────────────────────────────────────────────────────────────────────────

def queue_item_to_camel(item: NodeQueueItem) -> dict:
    """NodeQueueItem ORM -> camelCase dict"""
    return {
        "id": item.id,
        "nodeInstanceId": item.node_instance_id,
        "executionId": item.execution_id,
        "data": item.data,
        "status": item.status.value if item.status else "pending",
        "result": item.result,
        "error": item.error,
        "createdAt": item.created_at.isoformat() if item.created_at else None,
        "processedAt": item.processed_at.isoformat() if item.processed_at else None,
    }


@router.get("/queue/{node_id}")
async def get_node_queue(
    node_id: str,
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """공장 노드의 입력 큐 조회"""
    base_filter = NodeQueueItem.node_instance_id == node_id

    # 총 개수
    count_q = select(func.count()).where(base_filter)
    total = (await db.execute(count_q)).scalar() or 0

    # pending 개수
    pending_q = select(func.count()).where(base_filter, NodeQueueItem.status == QueueItemStatus.PENDING)
    pending = (await db.execute(pending_q)).scalar() or 0

    # processing 개수
    processing_q = select(func.count()).where(base_filter, NodeQueueItem.status == QueueItemStatus.PROCESSING)
    processing = (await db.execute(processing_q)).scalar() or 0

    # 데이터 조회
    query = select(NodeQueueItem).where(base_filter)
    if status:
        query = query.where(NodeQueueItem.status == status)
    query = query.order_by(NodeQueueItem.created_at.asc()).offset(skip).limit(limit)

    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [queue_item_to_camel(item) for item in items],
        "total": total,
        "pending": pending,
        "processing": processing,
        "nodeInstanceId": node_id,
    }


@router.delete("/queue/{node_id}", status_code=204)
async def clear_node_queue(
    node_id: str,
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """공장 노드 큐 비우기 (선택적 상태 필터)"""
    query = select(NodeQueueItem).where(NodeQueueItem.node_instance_id == node_id)
    if status:
        query = query.where(NodeQueueItem.status == status)

    result = await db.execute(query)
    for item in result.scalars().all():
        await db.delete(item)
    await db.commit()


@router.get("/queue/{node_id}/count")
async def get_node_queue_count(
    node_id: str,
    db: AsyncSession = Depends(get_db),
):
    """공장 노드 큐 카운트 (빠른 조회용)"""
    base_filter = NodeQueueItem.node_instance_id == node_id

    pending_q = select(func.count()).where(base_filter, NodeQueueItem.status == QueueItemStatus.PENDING)
    pending = (await db.execute(pending_q)).scalar() or 0

    processing_q = select(func.count()).where(base_filter, NodeQueueItem.status == QueueItemStatus.PROCESSING)
    processing = (await db.execute(processing_q)).scalar() or 0

    total_q = select(func.count()).where(base_filter)
    total = (await db.execute(total_q)).scalar() or 0

    return {"nodeInstanceId": node_id, "total": total, "pending": pending, "processing": processing}
