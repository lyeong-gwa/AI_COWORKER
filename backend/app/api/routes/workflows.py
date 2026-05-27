"""
Workflow API Routes
"""

from datetime import datetime
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
from ...core.exceptions import NotFoundError, ValidationError
from ...models.workflow import (
    Workflow, WorkflowNode, WorkflowConnection, WorkflowExecution,
    WorkflowStatus, ExecutionStatus, WarehouseEntry,
)
from ...schemas.workflow import (
    WorkflowCreate, WorkflowUpdate,
    ExecutionCreate, ScheduleConfigUpdate,
)
from ...services.workflow_engine import execute_workflow
from ...services.audit import log as audit_log

router = APIRouter()


async def _safe_reload_jobs():
    try:
        from ...core.scheduler import reload_jobs
        await reload_jobs()
    except Exception:
        pass


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


_DEFAULT_SCHEDULE_CONFIG = {
    "enabled": False,
    "cronExpr": "0 * * * *",
    "timezone": "Asia/Seoul",
}


def _schedule_config_or_default(wf: Workflow) -> dict:
    """schedule_config 가 None/누락이면 default 반환 (안전한 응답 직렬화용)."""
    cfg = getattr(wf, "schedule_config", None)
    if not isinstance(cfg, dict):
        return dict(_DEFAULT_SCHEDULE_CONFIG)
    return cfg


def workflow_to_camel(wf: Workflow) -> dict:
    """Workflow ORM -> camelCase dict (full detail)"""
    return {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description,
        "status": wf.status.value if wf.status else None,
        "tags": wf.tags,
        "trigger": wf.trigger,
        "variables": wf.variables,
        "scheduleConfig": _schedule_config_or_default(wf),
        "createdBy": wf.created_by,
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
        "scheduleConfig": _schedule_config_or_default(wf),
        "createdBy": wf.created_by,
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

@router.get(
    "",
    summary="워크플로우 목록 조회",
    description=(
        "등록된 워크플로우의 요약 정보 목록을 반환한다. "
        "CLI가 기존 자동화 파이프라인을 파악할 때 첫 번째로 호출하는 엔드포인트. "
        "``status``, ``q`` 필터와 ``skip``/``limit`` 페이지네이션을 지원한다."
    ),
    response_description="camelCase 요약 리스트 (id, name, status, nodeCount 등)",
)
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


@router.get(
    "/{workflow_id}",
    summary="워크플로우 상세 조회",
    description=(
        "노드·연결선까지 포함한 워크플로우 전체 구조를 반환한다. "
        "CLI가 기존 워크플로우를 수정·복제할 때 조회용으로 사용."
    ),
)
async def get_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    """워크플로우 상세 조회"""
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.nodes), selectinload(Workflow.connections))
        .where(Workflow.id == workflow_id)
    )
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise NotFoundError(
            "워크플로우를 찾을 수 없습니다",
            details={"workflowId": workflow_id},
        )

    return workflow_to_camel(workflow)


@router.post(
    "",
    status_code=201,
    summary="워크플로우 생성",
    description=(
        "CLI가 새로운 업무자동화 워크플로우를 등록한다. "
        "``nodes``는 카탈로그(`GET /nodes/catalog`)의 defType 을 참조하며, "
        "``connections``는 nodeId 간의 DAG 연결을 정의한다. "
        "position/viewport 필드는 존재하지 않으며 UI는 자동 레이아웃을 사용한다."
    ),
)
async def create_workflow(data: WorkflowCreate, db: AsyncSession = Depends(get_db)):
    """워크플로우 생성"""
    workflow_id = f"wf-{uuid.uuid4().hex[:8]}"

    workflow = Workflow(
        id=workflow_id,
        name=data.name,
        description=data.description,
        tags=data.tags,
        created_by=data.createdBy,
    )
    db.add(workflow)

    # 노드 생성
    for idx, node_data in enumerate(data.nodes):
        node = WorkflowNode(
            id=node_data.id,
            workflow_id=workflow_id,
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

    # 연결선 생성
    for conn_data in data.connections:
        conn = WorkflowConnection(
            id=conn_data.id,
            workflow_id=workflow_id,
            source_node_id=conn_data.sourceNodeId,
            target_node_id=conn_data.targetNodeId,
            source_handle=conn_data.sourceHandle,
            target_handle=conn_data.targetHandle,
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
    await audit_log(db, "system", "workflow.create", "workflow", workflow.id, {"name": workflow.name})
    await _safe_reload_jobs()
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
        raise NotFoundError(
            "워크플로우를 찾을 수 없습니다",
            details={"workflowId": workflow_id},
        )

    # 기본 필드 업데이트
    if data.name is not None:
        workflow.name = data.name
    if data.description is not None:
        workflow.description = data.description
    if data.status is not None:
        workflow.status = data.status
    if data.tags is not None:
        workflow.tags = data.tags
    if data.trigger is not None:
        workflow.trigger = data.trigger.model_dump()
    if data.variables is not None:
        workflow.variables = data.variables

    # 노드 업데이트 (전체 교체)
    if data.nodes is not None:
        # 기존 노드 삭제
        for node in workflow.nodes:
            await db.delete(node)

        # 새 노드 생성
        for idx, node_data in enumerate(data.nodes):
            node = WorkflowNode(
                id=node_data.id,
                workflow_id=workflow_id,
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
        .where(Workflow.id == workflow_id)
    )
    workflow = result.scalar_one()
    await _safe_reload_jobs()
    return workflow_to_camel(workflow)


# ─────────────────────────────────────────────────────────────────────────────
# Workflow Schedule (UI 토글 + cron 표현식)
# ─────────────────────────────────────────────────────────────────────────────


def _validate_cron_expr(expr: str, tz: str) -> None:
    """cron 표현식 유효성 검증. 실패 시 ValidationError(422) 발생."""
    try:
        CronTriggerImport = _import_cron_trigger()
        CronTriggerImport.from_crontab(expr, timezone=tz)
    except Exception as e:
        raise ValidationError(
            "유효하지 않은 cron 표현식입니다",
            code="INVALID_CRON_EXPR",
            status_code=422,
            details={"cronExpr": expr, "timezone": tz, "reason": str(e)},
        )


def _import_cron_trigger():
    # lazy 로 import 하여 테스트 콜드스타트 영향 최소화
    from apscheduler.triggers.cron import CronTrigger  # noqa: WPS433
    return CronTrigger


@router.patch(
    "/{workflow_id}/schedule",
    summary="워크플로우 스케줄 설정 갱신 (토글 + cron)",
    description=(
        "워크플로우의 `schedule_config` 를 갱신하고 APScheduler job 을 자동으로 reload 한다. "
        "cron 표현식은 5-field 표준이며 검증 실패 시 422 반환. "
        "응답에는 갱신된 scheduleConfig 와 (등록된 경우) 다음 실행 시각이 포함된다."
    ),
)
async def update_workflow_schedule(
    workflow_id: str,
    data: ScheduleConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """schedule_config 갱신 + reload_jobs 자동 호출."""
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id)
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise NotFoundError(
            "워크플로우를 찾을 수 없습니다",
            details={"workflowId": workflow_id},
        )

    tz = data.timezone or "Asia/Seoul"
    # cron 표현식 유효성 검증 (활성/비활성 무관 — 잘못된 표현식 저장 방지)
    _validate_cron_expr(data.cronExpr, tz)

    new_cfg = {
        "enabled": bool(data.enabled),
        "cronExpr": data.cronExpr.strip(),
        "timezone": tz,
    }
    workflow.schedule_config = new_cfg
    # JSON 컬럼 in-place 변경 트래킹 위해 flag 보장
    try:
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(workflow, "schedule_config")
    except Exception:
        pass

    await db.commit()
    await db.refresh(workflow)

    # 스케줄러 reload (best-effort) — 동기적으로 호출하여 즉시 반영
    try:
        from ...core.scheduler import reload_jobs
        await reload_jobs()
    except Exception:
        pass

    # 다음 실행 시각 계산
    next_run_iso: Optional[str] = None
    try:
        from ...core.scheduler import get_scheduler
        sch = get_scheduler()
        if sch is not None:
            job = sch.get_job(f"wf:{workflow_id}")
            if job and job.next_run_time:
                next_run_iso = job.next_run_time.isoformat()
    except Exception:
        pass

    await audit_log(
        db,
        "system",
        "workflow.schedule.update",
        "workflow",
        workflow_id,
        {
            "enabled": new_cfg["enabled"],
            "cronExpr": new_cfg["cronExpr"],
            "timezone": new_cfg["timezone"],
        },
    )

    return {
        "workflowId": workflow_id,
        "scheduleConfig": new_cfg,
        "nextRunTime": next_run_iso,
    }


@router.get(
    "/{workflow_id}/schedule/next-run",
    summary="워크플로우의 다음 스케줄 실행 시각 조회",
    description=(
        "APScheduler 에 등록된 job 의 next_run_time 을 반환한다. "
        "등록되지 않은 경우 `registered=false`, `nextRunTime=null` 반환."
    ),
)
async def get_workflow_schedule_next_run(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
):
    """등록된 job 의 next_run_time 1건 조회."""
    # 워크플로우 존재 확인
    wf = (await db.execute(
        select(Workflow).where(Workflow.id == workflow_id)
    )).scalar_one_or_none()
    if not wf:
        raise NotFoundError(
            "워크플로우를 찾을 수 없습니다",
            details={"workflowId": workflow_id},
        )

    next_run_iso: Optional[str] = None
    registered = False
    try:
        from ...core.scheduler import get_scheduler
        sch = get_scheduler()
        if sch is not None:
            job = sch.get_job(f"wf:{workflow_id}")
            if job is not None:
                registered = True
                if job.next_run_time:
                    next_run_iso = job.next_run_time.isoformat()
    except Exception:
        pass

    return {
        "workflowId": workflow_id,
        "nextRunTime": next_run_iso,
        "registered": registered,
    }


@router.get(
    "/{workflow_id}/delete-preview",
    summary="워크플로우 삭제 영향 미리보기",
    description=(
        "실제 삭제 전 cascade 로 함께 사라질 데이터의 카운트만 반환한다. "
        "운영자가 web UI 의 confirm 모달에서 영향 범위를 확인할 때 사용한다."
    ),
)
async def workflow_delete_preview(workflow_id: str, db: AsyncSession = Depends(get_db)):
    """워크플로우 삭제 시 cascade 로 삭제될 항목 카운트 조회."""
    from sqlalchemy import func

    # workflow 존재 확인
    wf_result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id)
    )
    workflow = wf_result.scalar_one_or_none()
    if not workflow:
        raise NotFoundError(
            "워크플로우를 찾을 수 없습니다",
            details={"workflowId": workflow_id},
        )

    # 실행 인스턴스 카운트
    instance_count_q = select(func.count(WorkflowExecution.id)).where(
        WorkflowExecution.workflow_id == workflow_id
    )
    instance_count = int((await db.execute(instance_count_q)).scalar() or 0)

    # 노드별 결과 카운트 — node_results JSON 의 key 합산 (executions.node_results 안에 누적)
    node_result_total = 0
    if instance_count > 0:
        nr_q = select(WorkflowExecution.node_results).where(
            WorkflowExecution.workflow_id == workflow_id
        )
        for row in (await db.execute(nr_q)).scalars().all():
            if isinstance(row, dict):
                node_result_total += len(row)

    # 워크플로우 소속 실행 인스턴스 id 들 → warehouse_entries 카운트
    warehouse_count = 0
    if instance_count > 0:
        exec_ids_q = select(WorkflowExecution.id).where(
            WorkflowExecution.workflow_id == workflow_id
        )
        exec_ids = [r for r in (await db.execute(exec_ids_q)).scalars().all()]
        if exec_ids:
            we_count_q = select(func.count(WarehouseEntry.id)).where(
                WarehouseEntry.execution_id.in_(exec_ids)
            )
            warehouse_count = int((await db.execute(we_count_q)).scalar() or 0)

    return {
        "workflowId": workflow_id,
        "workflowName": workflow.name,
        "instanceCount": instance_count,
        "warehouseEntryCount": warehouse_count,
        "nodeResultCount": node_result_total,
        "willCascadeDelete": True,
    }


@router.delete(
    "/{workflow_id}",
    summary="워크플로우 삭제 (cascade)",
    description=(
        "워크플로우와 관련 모든 데이터(노드·연결선·실행이력·창고 항목)를 "
        "단일 트랜잭션으로 삭제한다. "
        "`warehouse_entries` 는 FK 가 없으므로 명시 DELETE 로 정리한다. "
        "응답에 cascade 카운트가 포함된다."
    ),
)
async def delete_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    """워크플로우 cascade 삭제 — workflow + nodes + connections + executions + warehouse_entries."""
    from sqlalchemy import delete as sql_delete

    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise NotFoundError(
            "워크플로우를 찾을 수 없습니다",
            details={"workflowId": workflow_id},
        )

    # 워크플로우 소속 실행 인스턴스 id 들 (warehouse 삭제용)
    exec_ids_q = select(WorkflowExecution.id).where(
        WorkflowExecution.workflow_id == workflow_id
    )
    exec_ids = [r for r in (await db.execute(exec_ids_q)).scalars().all()]
    instance_count = len(exec_ids)

    # node_results 카운트 (응답용)
    node_result_total = 0
    if exec_ids:
        nr_q = select(WorkflowExecution.node_results).where(
            WorkflowExecution.workflow_id == workflow_id
        )
        for row in (await db.execute(nr_q)).scalars().all():
            if isinstance(row, dict):
                node_result_total += len(row)

    # warehouse_entries 명시 삭제 (FK 부재로 ORM cascade 가 닿지 않음)
    warehouse_deleted = 0
    if exec_ids:
        we_result = await db.execute(
            sql_delete(WarehouseEntry)
            .where(WarehouseEntry.execution_id.in_(exec_ids))
            .returning(WarehouseEntry.id)
        )
        warehouse_deleted = len(we_result.all())

    # 본체 삭제 — ORM cascade 로 nodes / connections / executions 가 함께 사라진다
    try:
        await db.delete(workflow)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    # 감사 로그 (best-effort, 트랜잭션 외부)
    try:
        await audit_log(
            db,
            "system",
            "workflow.delete",
            "workflow",
            workflow_id,
            {
                "workflowId": workflow_id,
                "name": workflow.name,
                "instanceCount": instance_count,
                "warehouseEntriesDeleted": warehouse_deleted,
                "nodeResultCount": node_result_total,
            },
        )
    except Exception:
        pass

    return {
        "deleted": True,
        "workflowId": workflow_id,
        "cascadeCounts": {
            "instances": instance_count,
            "warehouseEntries": warehouse_deleted,
            "nodeResults": node_result_total,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Workflow Execution
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/{workflow_id}/execute",
    summary="워크플로우 실행 (레거시 호환)",
    description=(
        "기존 UI/코드 호환 경로. Phase 2b에서 신설한 "
        "``POST /{workflow_id}/run`` 과 동일하게 백그라운드 실행을 스케줄하고 "
        "전체 실행 레코드(camelCase)를 즉시 반환한다."
    ),
)
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
        raise NotFoundError(
            "워크플로우를 찾을 수 없습니다",
            details={"workflowId": workflow_id},
        )

    if workflow.status != WorkflowStatus.ACTIVE:
        raise ValidationError(
            "비활성 워크플로우는 실행할 수 없습니다",
            code="WORKFLOW_NOT_ACTIVE",
            status_code=400,
            details={"workflowId": workflow_id, "status": workflow.status.value},
        )

    # 실행 레코드 생성
    execution = WorkflowExecution(
        id=f"exec-{uuid.uuid4().hex[:8]}",
        workflow_id=workflow_id,
        status=ExecutionStatus.PENDING,
        input_data=request.inputData,
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    # 감사 로그
    await audit_log(db, "system", "workflow.execute", "workflow", workflow_id, {"executionId": execution.id})

    # 백그라운드에서 실행
    background_tasks.add_task(execute_workflow, execution.id)

    return execution_to_camel(execution)


# ── Phase 2b: CLI 친화 /run 엔드포인트 ─────────────────────────────────────
# 설계서 섹션 5.2 기준으로 CLI는 instanceId 만 즉시 받고 SSE 스트림 또는
# 인스턴스 조회 엔드포인트로 후속 상태를 관찰한다.

@router.post(
    "/{workflow_id}/run",
    status_code=202,
    summary="워크플로우 백그라운드 실행 시작",
    description=(
        "CLI가 워크플로우를 비동기 실행하는 표준 진입점. "
        "실제 실행은 FastAPI BackgroundTasks 로 스케줄되고, 응답은 "
        "``{instanceId, workflowId, status:\"queued\", createdAt}`` 을 즉시 반환한다. "
        "진행 상황은 ``GET /api/v1/warehouse/instances/{instanceId}/stream`` "
        "(SSE) 또는 ``GET /api/v1/workflows/executions/{instanceId}`` 로 관찰한다. "
        "HTTP 202 Accepted."
    ),
    response_description=(
        "접수 확인. status 는 항상 ``queued`` 로 반환되며, 실행 엔진이 "
        "DB에 ``running``/``completed``/``failed`` 로 갱신한다."
    ),
)
async def run_workflow(
    workflow_id: str,
    request: ExecutionCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """워크플로우 백그라운드 실행 시작 — instanceId 즉시 반환."""
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.nodes), selectinload(Workflow.connections))
        .where(Workflow.id == workflow_id)
    )
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise NotFoundError(
            "워크플로우를 찾을 수 없습니다",
            details={"workflowId": workflow_id},
        )

    if workflow.status != WorkflowStatus.ACTIVE:
        raise ValidationError(
            "비활성 워크플로우는 실행할 수 없습니다",
            code="WORKFLOW_NOT_ACTIVE",
            status_code=400,
            details={"workflowId": workflow_id, "status": workflow.status.value},
        )

    instance_id = f"exec-{uuid.uuid4().hex[:8]}"
    execution = WorkflowExecution(
        id=instance_id,
        workflow_id=workflow_id,
        status=ExecutionStatus.PENDING,
        input_data=request.inputData or {},
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    await audit_log(
        db,
        "cli",
        "workflow.run",
        "workflow",
        workflow_id,
        {"instanceId": instance_id},
    )

    # 백그라운드 실행 스케줄 — 엔진 내부는 수정하지 않는다.
    background_tasks.add_task(execute_workflow, instance_id)

    # 설계서 지정 페이로드 — 최소 형태로 즉시 반환.
    # DB의 ExecutionStatus.PENDING 을 CLI 계약상 "queued" 로 alias.
    return {
        "instanceId": instance_id,
        "workflowId": workflow_id,
        "status": "queued",
        "createdAt": execution.created_at.isoformat() if execution.created_at else None,
    }


@router.get(
    "/{workflow_id}/executions",
    summary="워크플로우 실행 이력 (레거시 경로)",
    description=(
        "``GET /{workflow_id}/instances`` 의 동의어. 최근 실행 레코드를 "
        "``createdAt`` 내림차순으로 반환한다."
    ),
)
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


@router.get(
    "/{workflow_id}/instances",
    summary="워크플로우 인스턴스 목록",
    description=(
        "CLI 계약용 별칭. 동일한 데이터를 반환하나 '인스턴스' 용어를 사용하는 "
        "설계서 섹션 5.2 와 정합을 맞춘다."
    ),
)
async def list_instances(
    workflow_id: str,
    status: Optional[ExecutionStatus] = Query(None),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """워크플로우 인스턴스 목록 (executions 와 동일 데이터)."""
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
        raise NotFoundError(
            "실행 기록을 찾을 수 없습니다",
            details={"executionId": execution_id},
        )

    return execution_to_camel(execution)


@router.get("/executions/{execution_id}/stream")
async def stream_execution(execution_id: str, db: AsyncSession = Depends(get_db)):
    """실행 로그 스트리밍 (SSE)"""
    result = await db.execute(
        select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
    )
    execution = result.scalar_one_or_none()

    if not execution:
        raise NotFoundError(
            "실행 기록을 찾을 수 없습니다",
            details={"executionId": execution_id},
        )

    async def event_generator() -> AsyncGenerator[str, None]:
        """SSE 이벤트 생성기"""
        while True:
            # 세션 캐시 만료 → 백그라운드 태스크의 최신 커밋 반영
            db.expire_all()
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


@router.delete(
    "/executions/{execution_id}",
    summary="실행 기록 단건 삭제",
    description=(
        "완료·실패·취소된 실행 기록 1건과 관련 창고(warehouse_entries)를 "
        "한 트랜잭션으로 삭제한다. RUNNING/PENDING/QUEUED 상태는 409로 차단. "
        "``?force=true`` 쿼리로 상태 검사를 우회할 수 있다."
    ),
)
async def delete_execution(
    execution_id: str,
    force: bool = Query(False, description="상태 검사 우회"),
    db: AsyncSession = Depends(get_db),
):
    """실행 기록 단건 삭제 (cascade: warehouse_entries)"""
    from sqlalchemy import delete as sql_delete

    result = await db.execute(
        select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
    )
    execution = result.scalar_one_or_none()

    if not execution:
        raise NotFoundError(
            "실행 기록을 찾을 수 없습니다",
            details={"executionId": execution_id},
        )

    if not force and execution.status in [
        ExecutionStatus.PENDING,
        ExecutionStatus.RUNNING,
    ]:
        raise ValidationError(
            "실행 중인 기록은 삭제할 수 없습니다. ?force=true 로 우회 가능합니다.",
            code="EXECUTION_RUNNING",
            status_code=409,
            details={"executionId": execution_id, "status": execution.status.value},
        )

    # warehouse_entries 먼저 삭제 (명시 DELETE, cascade 의존 X)
    await db.execute(
        sql_delete(WarehouseEntry).where(WarehouseEntry.execution_id == execution_id)
    )
    # 본체 삭제
    await db.delete(execution)
    await db.commit()

    await audit_log(
        db,
        "system",
        "workflow.execution.delete",
        "workflow_execution",
        execution_id,
        {"executionId": execution_id, "force": force},
    )

    return {"message": "삭제되었습니다", "id": execution_id}


@router.post(
    "/{workflow_id}/executions/cleanup",
    summary="워크플로우 실행 기록 일괄 정리",
    description=(
        "지정한 워크플로우의 실행 기록을 조건에 따라 일괄 삭제한다. "
        "``dryRun=true`` 이면 카운트만 반환, 실제 삭제하지 않는다."
    ),
)
async def cleanup_executions(
    workflow_id: str,
    olderThanDays: int = Query(30, ge=0, description="N일 이전 created_at 대상"),
    status: Optional[str] = Query(
        "completed,failed,cancelled",
        description="대상 상태 (comma-separated)",
    ),
    dryRun: bool = Query(False, description="true면 카운트만 반환, 실제 삭제 안 함"),
    db: AsyncSession = Depends(get_db),
):
    """워크플로우 실행 기록 일괄 정리."""
    from datetime import timedelta
    from sqlalchemy import delete as sql_delete

    # workflow 존재 확인
    wf_result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id)
    )
    if not wf_result.scalar_one_or_none():
        raise NotFoundError(
            "워크플로우를 찾을 수 없습니다",
            details={"workflowId": workflow_id},
        )

    cutoff = datetime.utcnow() - timedelta(days=olderThanDays)

    # 대상 상태 파싱
    raw_statuses = [s.strip() for s in (status or "").split(",") if s.strip()]
    target_statuses: list[ExecutionStatus] = []
    for s in raw_statuses:
        try:
            target_statuses.append(ExecutionStatus(s))
        except ValueError:
            pass
    if not target_statuses:
        target_statuses = [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED]

    # 대상 execution ID 조회
    q = (
        select(WorkflowExecution.id)
        .where(WorkflowExecution.workflow_id == workflow_id)
        .where(WorkflowExecution.created_at < cutoff)
        .where(WorkflowExecution.status.in_(target_statuses))
    )
    rows = (await db.execute(q)).scalars().all()
    candidate_ids = list(rows)
    candidate_count = len(candidate_ids)

    deleted_count = 0
    warehouse_deleted = 0

    if not dryRun and candidate_ids:
        # warehouse_entries 먼저 삭제
        we_result = await db.execute(
            sql_delete(WarehouseEntry)
            .where(WarehouseEntry.execution_id.in_(candidate_ids))
            .returning(WarehouseEntry.id)
        )
        warehouse_deleted = len(we_result.all())

        # executions 삭제
        ex_result = await db.execute(
            sql_delete(WorkflowExecution)
            .where(WorkflowExecution.id.in_(candidate_ids))
            .returning(WorkflowExecution.id)
        )
        deleted_count = len(ex_result.all())
        await db.commit()

        await audit_log(
            db,
            "system",
            "workflow.executions.cleanup",
            "workflow",
            workflow_id,
            {
                "deletedCount": deleted_count,
                "warehouseEntriesDeleted": warehouse_deleted,
                "olderThanDays": olderThanDays,
                "statuses": [s.value for s in target_statuses],
                "dryRun": dryRun,
            },
        )

    return {
        "candidateCount": candidate_count,
        "deletedCount": deleted_count,
        "warehouseEntriesDeleted": warehouse_deleted,
        "dryRun": dryRun,
        "olderThanDays": olderThanDays,
        "statuses": [s.value for s in target_statuses],
    }


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(execution_id: str, db: AsyncSession = Depends(get_db)):
    """실행 취소"""
    result = await db.execute(
        select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
    )
    execution = result.scalar_one_or_none()

    if not execution:
        raise NotFoundError(
            "실행 기록을 찾을 수 없습니다",
            details={"executionId": execution_id},
        )

    if execution.status not in [ExecutionStatus.PENDING, ExecutionStatus.RUNNING]:
        raise ValidationError(
            "취소할 수 없는 상태입니다",
            code="INVALID_STATE_TRANSITION",
            status_code=400,
            details={"executionId": execution_id, "status": execution.status.value},
        )

    execution.status = ExecutionStatus.CANCELLED
    await db.commit()

    return {"message": "실행이 취소되었습니다"}
