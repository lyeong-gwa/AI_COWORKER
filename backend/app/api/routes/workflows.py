"""
Workflow API Routes
"""

from typing import List, Optional, AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import uuid
import json
import asyncio

from ...core.database import get_db
from ...models.workflow import (
    Workflow, WorkflowNode, WorkflowConnection, WorkflowExecution,
    WorkflowStatus, ExecutionStatus,
)
from ...schemas.workflow import (
    WorkflowCreate, WorkflowUpdate,
    ExecutionCreate,
)
from ...services.workflow_engine import execute_workflow

router = APIRouter()


def workflow_node_to_camel(node: WorkflowNode) -> dict:
    """WorkflowNode ORM -> camelCase dict"""
    return {
        "id": node.id,
        "nodeId": node.node_id,
        "name": node.name,
        "position": node.position,
        "configOverrides": node.config_overrides,
        "inputMapping": node.input_mapping,
    }


def workflow_connection_to_camel(conn: WorkflowConnection) -> dict:
    """WorkflowConnection ORM -> camelCase dict"""
    return {
        "id": conn.id,
        "sourceNodeId": conn.source_node_id,
        "targetNodeId": conn.target_node_id,
        "condition": conn.condition,
    }


def workflow_to_camel(wf: Workflow) -> dict:
    """Workflow ORM -> camelCase dict (full detail)"""
    return {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description,
        "status": wf.status.value if wf.status else None,
        "tags": wf.tags,
        "viewport": wf.viewport,
        "trigger": wf.trigger,
        "variables": wf.variables,
        "nodes": [workflow_node_to_camel(n) for n in wf.nodes],
        "connections": [workflow_connection_to_camel(c) for c in wf.connections],
        "createdAt": wf.created_at.isoformat() if wf.created_at else None,
        "updatedAt": wf.updated_at.isoformat() if wf.updated_at else None,
    }


def workflow_summary_to_camel(wf: Workflow) -> dict:
    """Workflow ORM -> camelCase summary dict"""
    return {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description,
        "status": wf.status.value if wf.status else None,
        "tags": wf.tags,
        "nodeCount": len(wf.nodes),
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


# ─────────────────────────────────────────────────────────────────────────────
# Workflow CRUD
# ─────────────────────────────────────────────────────────────────────────────

@router.get("")
async def list_workflows(
    status: Optional[WorkflowStatus] = Query(None, description="상태 필터"),
    q: Optional[str] = Query(None, description="검색어 (이름, 설명)"),
    skip: int = Query(0, ge=0, description="건너뛸 항목 수"),
    limit: int = Query(100, ge=1, le=500, description="최대 항목 수"),
    db: AsyncSession = Depends(get_db),
):
    """워크플로우 목록 조회"""
    query = select(Workflow).options(selectinload(Workflow.nodes))

    if status:
        query = query.where(Workflow.status == status)
    if q:
        query = query.where(
            (Workflow.name.ilike(f"%{q}%")) | (Workflow.description.ilike(f"%{q}%"))
        )

    query = query.order_by(Workflow.updated_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    workflows = result.scalars().all()

    return [workflow_summary_to_camel(w) for w in workflows]


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    """워크플로우 상세 조회"""
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.nodes), selectinload(Workflow.connections))
        .where(Workflow.id == workflow_id)
    )
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다")

    return workflow_to_camel(workflow)


@router.post("", status_code=201)
async def create_workflow(data: WorkflowCreate, db: AsyncSession = Depends(get_db)):
    """워크플로우 생성"""
    workflow_id = f"wf-{uuid.uuid4().hex[:8]}"

    workflow = Workflow(
        id=workflow_id,
        name=data.name,
        description=data.description,
        tags=data.tags,
        viewport=data.viewport.model_dump() if data.viewport else {"x": 0, "y": 0, "zoom": 1},
    )
    db.add(workflow)

    # 노드 생성
    for node_data in data.nodes:
        node = WorkflowNode(
            id=node_data.id,
            workflow_id=workflow_id,
            node_id=node_data.nodeId,
            name=node_data.name,
            position={"x": node_data.position.x, "y": node_data.position.y},
            config_overrides=node_data.configOverrides,
            input_mapping=node_data.inputMapping,
        )
        db.add(node)

    # 연결선 생성
    for conn_data in data.connections:
        conn = WorkflowConnection(
            id=conn_data.id,
            workflow_id=workflow_id,
            source_node_id=conn_data.sourceNodeId,
            target_node_id=conn_data.targetNodeId,
            condition=conn_data.condition.model_dump() if conn_data.condition else None,
        )
        db.add(conn)

    await db.commit()

    # 관계 포함해서 다시 조회
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.nodes), selectinload(Workflow.connections))
        .where(Workflow.id == workflow_id)
    )
    workflow = result.scalar_one()
    return workflow_to_camel(workflow)


@router.patch("/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    data: WorkflowUpdate,
    db: AsyncSession = Depends(get_db),
):
    """워크플로우 수정"""
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.nodes), selectinload(Workflow.connections))
        .where(Workflow.id == workflow_id)
    )
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다")

    # 기본 필드 업데이트
    if data.name is not None:
        workflow.name = data.name
    if data.description is not None:
        workflow.description = data.description
    if data.status is not None:
        workflow.status = data.status
    if data.tags is not None:
        workflow.tags = data.tags
    if data.viewport is not None:
        workflow.viewport = data.viewport.model_dump()

    # 노드 업데이트 (전체 교체)
    if data.nodes is not None:
        # 기존 노드 삭제
        for node in workflow.nodes:
            await db.delete(node)

        # 새 노드 생성
        for node_data in data.nodes:
            node = WorkflowNode(
                id=node_data.id,
                workflow_id=workflow_id,
                node_id=node_data.nodeId,
                name=node_data.name,
                position={"x": node_data.position.x, "y": node_data.position.y},
                config_overrides=node_data.configOverrides,
                input_mapping=node_data.inputMapping,
            )
            db.add(node)

    # 연결선 업데이트 (전체 교체)
    if data.connections is not None:
        # 기존 연결선 삭제
        for conn in workflow.connections:
            await db.delete(conn)

        # 새 연결선 생성
        for conn_data in data.connections:
            conn = WorkflowConnection(
                id=conn_data.id,
                workflow_id=workflow_id,
                source_node_id=conn_data.sourceNodeId,
                target_node_id=conn_data.targetNodeId,
                condition=conn_data.condition.model_dump() if conn_data.condition else None,
            )
            db.add(conn)

    await db.commit()

    # 다시 조회
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.nodes), selectinload(Workflow.connections))
        .where(Workflow.id == workflow_id)
    )
    workflow = result.scalar_one()
    return workflow_to_camel(workflow)


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    """워크플로우 삭제"""
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다")

    await db.delete(workflow)
    await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Workflow Execution
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{workflow_id}/execute")
async def execute_workflow_endpoint(
    workflow_id: str,
    request: ExecutionCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """워크플로우 실행"""
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.nodes), selectinload(Workflow.connections))
        .where(Workflow.id == workflow_id)
    )
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다")

    if workflow.status != WorkflowStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="비활성 워크플로우는 실행할 수 없습니다")

    # 실행 레코드 생성
    execution = WorkflowExecution(
        id=f"exec-{uuid.uuid4().hex[:8]}",
        workflow_id=workflow_id,
        status=ExecutionStatus.PENDING,
        input_data=request.input_data,
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    # 백그라운드에서 실행
    background_tasks.add_task(execute_workflow, execution.id)

    return execution_to_camel(execution)


@router.get("/{workflow_id}/executions")
async def list_executions(
    workflow_id: str,
    status: Optional[ExecutionStatus] = Query(None),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """워크플로우 실행 이력"""
    query = select(WorkflowExecution).where(
        WorkflowExecution.workflow_id == workflow_id
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
            # 실행 상태 조회
            result = await db.execute(
                select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
            )
            current = result.scalar_one_or_none()

            if not current:
                break

            # 상태 이벤트 전송
            event_data = {
                "status": current.status.value,
                "nodeResults": current.node_results,
            }
            yield f"data: {json.dumps(event_data, default=str)}\n\n"

            # 완료/실패시 종료
            if current.status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED]:
                final_data = {
                    "status": current.status.value,
                    "output": current.output_data,
                    "error": current.error_message,
                }
                yield f"data: {json.dumps(final_data, default=str)}\n\n"
                break

            await asyncio.sleep(0.5)  # 0.5초마다 폴링

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
