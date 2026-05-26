"""
Ops Routes - ITO 운영 대시보드 집계 API
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...core.database import get_db
from ...models.workflow import Workflow, WorkflowExecution, WorkflowStatus, ExecutionStatus
from ...models.ticket import Ticket
from ...models.audit_log import AuditLog

router = APIRouter()


def _dt_iso(dt):
    return dt.isoformat() if dt else None


@router.get("/dashboard")
async def ops_dashboard(db: AsyncSession = Depends(get_db)):
    """ITO 운영 대시보드 통합 집계 (최근 7일 기준)"""
    now = datetime.utcnow()
    period_from = now - timedelta(days=7)

    # ── 워크플로우 집계 ─────────────────────────────
    workflows = (await db.execute(select(Workflow))).scalars().all()
    wf_total = len(workflows)
    wf_active = sum(1 for w in workflows if w.status == WorkflowStatus.ACTIVE)
    wf_name_map = {w.id: w.name for w in workflows}

    # 실행 (최근 7일)
    exec_query = select(WorkflowExecution).where(WorkflowExecution.created_at >= period_from)
    executions_7d = (await db.execute(exec_query)).scalars().all()

    exec_count = len(executions_7d)
    completed = [e for e in executions_7d if e.status == ExecutionStatus.COMPLETED]
    failed = [e for e in executions_7d if e.status == ExecutionStatus.FAILED]
    success_rate = (len(completed) / exec_count) if exec_count > 0 else 0.0

    # 평균 실행 시간
    durations = []
    for e in executions_7d:
        if e.started_at and e.completed_at:
            durations.append((e.completed_at - e.started_at).total_seconds())
    avg_duration = (sum(durations) / len(durations)) if durations else 0.0

    # Top 워크플로우 (실행 횟수 기준)
    wf_exec_counts: dict = {}
    wf_fail_counts: dict = {}
    for e in executions_7d:
        wf_exec_counts[e.workflow_id] = wf_exec_counts.get(e.workflow_id, 0) + 1
        if e.status == ExecutionStatus.FAILED:
            wf_fail_counts[e.workflow_id] = wf_fail_counts.get(e.workflow_id, 0) + 1

    top_sorted = sorted(wf_exec_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_workflows = [
        {
            "id": wid,
            "name": wf_name_map.get(wid, wid),
            "count": cnt,
            "failureRate": (wf_fail_counts.get(wid, 0) / cnt) if cnt > 0 else 0.0,
        }
        for wid, cnt in top_sorted
    ]

    # 최근 실행 20건 (전체 기간)
    recent_exec_query = (
        select(WorkflowExecution)
        .order_by(WorkflowExecution.created_at.desc())
        .limit(20)
    )
    recent_execs = (await db.execute(recent_exec_query)).scalars().all()
    recent_executions = []
    for e in recent_execs:
        dur = None
        if e.started_at and e.completed_at:
            dur = (e.completed_at - e.started_at).total_seconds()
        recent_executions.append({
            "id": e.id,
            "workflowId": e.workflow_id,
            "workflowName": wf_name_map.get(e.workflow_id, e.workflow_id),
            "status": e.status.value if hasattr(e.status, "value") else str(e.status),
            "startedAt": _dt_iso(e.started_at),
            "completedAt": _dt_iso(e.completed_at),
            "createdAt": _dt_iso(e.created_at),
            "duration": dur,
            "errorMessage": e.error_message,
        })

    # ── 티켓 집계 ────────────────────────────────
    tickets = (await db.execute(select(Ticket))).scalars().all()
    by_cat: dict = {}
    by_status: dict = {}
    by_priority: dict = {}
    sla_breach = 0
    open_count = 0

    for t in tickets:
        by_cat[t.category] = by_cat.get(t.category, 0) + 1
        by_status[t.status] = by_status.get(t.status, 0) + 1
        by_priority[t.priority] = by_priority.get(t.priority, 0) + 1
        if t.status not in ("resolved", "closed"):
            open_count += 1
        if t.sla_due_at and t.sla_due_at < now and t.status not in ("resolved", "closed"):
            sla_breach += 1

    recent_tickets_query = (
        select(Ticket).order_by(Ticket.created_at.desc()).limit(10)
    )
    recent_tickets_rows = (await db.execute(recent_tickets_query)).scalars().all()
    recent_tickets = [
        {
            "id": t.id,
            "title": t.title,
            "category": t.category,
            "priority": t.priority,
            "status": t.status,
            "requester": t.requester,
            "assignee": t.assignee,
            "slaDueAt": _dt_iso(t.sla_due_at),
            "createdAt": _dt_iso(t.created_at),
        }
        for t in recent_tickets_rows
    ]

    return {
        "period": {"from": _dt_iso(period_from), "to": _dt_iso(now)},
        "workflows": {
            "total": wf_total,
            "active": wf_active,
            "executionsLast7d": exec_count,
            "successRate": round(success_rate, 4),
            "failureCount": len(failed),
            "avgDurationSec": round(avg_duration, 2),
            "topWorkflows": top_workflows,
        },
        "tickets": {
            "total": len(tickets),
            "byStatus": by_status,
            "byCategory": by_cat,
            "byPriority": by_priority,
            "slaBreach": sla_breach,
            "openCount": open_count,
        },
        "recentExecutions": recent_executions,
        "recentTickets": recent_tickets,
    }


@router.get("/audit")
async def list_audit(
    limit: int = Query(100, ge=1, le=1000),
    action: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """감사 로그 최근 N건 조회"""
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action == action)
    q = q.order_by(AuditLog.ts.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": r.id,
            "ts": _dt_iso(r.ts),
            "actor": r.actor,
            "action": r.action,
            "targetType": r.target_type,
            "targetId": r.target_id,
            "details": r.details,
        }
        for r in rows
    ]


@router.get("/scheduler/jobs")
async def list_scheduler_jobs():
    """현재 등록된 스케줄러 job 목록"""
    from ...core.scheduler import get_scheduler
    sch = get_scheduler()
    if sch is None:
        return {"running": False, "jobs": []}
    jobs = []
    for j in sch.get_jobs():
        jobs.append({
            "id": j.id,
            "name": j.name,
            "nextRunTime": _dt_iso(j.next_run_time) if j.next_run_time else None,
            "trigger": str(j.trigger),
        })
    return {"running": sch.running, "jobs": jobs}


@router.post("/scheduler/reload")
async def reload_scheduler():
    """스케줄러 job 재로드"""
    from ...core.scheduler import reload_jobs
    return await reload_jobs()


@router.post("/scheduler/trigger/{workflow_id}")
async def trigger_scheduler_now(workflow_id: str):
    """스케줄 대기 없이 즉시 1회 실행 (수동 시뮬레이션)"""
    from ...core.scheduler import trigger_now
    return await trigger_now(workflow_id)
