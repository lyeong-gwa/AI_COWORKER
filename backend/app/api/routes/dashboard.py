"""
Dashboard Summary API Route

GET /api/v1/dashboard/summary

단일 쿼리 집합으로 대시보드에 필요한 집계를 반환한다.
  - counts: 오늘 실행 / 진행 중 / 최근 7일 실패 / 최근 7일 성공
  - workflows: 각 워크플로우의 요약 + 최신 인스턴스 1건

Phase 4c 신설 — DashboardPage.tsx 의 N+1 Promise.all 교체 목적.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from ...core.database import get_db
from ...models.workflow import (
    Workflow,
    WorkflowExecution,
    ExecutionStatus,
)

router = APIRouter()

# 카운팅 기준
IN_PROGRESS_STATUSES = {ExecutionStatus.PENDING, ExecutionStatus.RUNNING}
RECENT_DAYS = 7


def _utc_today_start() -> datetime:
    """UTC 기준 오늘 00:00:00"""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)


def _utc_days_ago(days: int) -> datetime:
    """UTC 기준 N일 전 00:00:00"""
    return _utc_today_start() - timedelta(days=days - 1)


@router.get(
    "/summary",
    summary="대시보드 집계 요약",
    description=(
        "대시보드에 필요한 집계를 단일 응답으로 반환한다. "
        "counts.todayRuns: UTC 기준 오늘 생성된 실행 수. "
        "counts.inProgress: 현재 pending/running 실행 수. "
        "counts.failed: 최근 7일 내 실패 실행 수. "
        "counts.completed: 최근 7일 내 완료 실행 수. "
        "workflows: 각 워크플로우의 요약 + latestInstance 1건."
    ),
    response_description=(
        "{ counts: {...}, workflows: [...] } 구조. "
        "workflows 배열은 status=active 우선, 그다음 최신 실행 순."
    ),
)
async def get_dashboard_summary(db: AsyncSession = Depends(get_db)):
    """대시보드 집계 요약 — 단일 엔드포인트로 N+1 제거."""

    today_start = _utc_today_start()
    week_start = _utc_days_ago(RECENT_DAYS)

    # ── 1. 카운트 집계 ──────────────────────────────────────────────────────
    # 각 쿼리를 개별 실행 (SQLite 비동기 환경에서 UNION/CASE WHEN 보다 가독성 우선)

    # 1-a) 오늘 실행 수
    r_today = await db.execute(
        select(func.count()).select_from(WorkflowExecution).where(
            WorkflowExecution.created_at >= today_start
        )
    )
    today_runs: int = r_today.scalar() or 0

    # 1-b) 진행 중 (pending + running)
    r_in_progress = await db.execute(
        select(func.count()).select_from(WorkflowExecution).where(
            WorkflowExecution.status.in_(list(IN_PROGRESS_STATUSES))
        )
    )
    in_progress: int = r_in_progress.scalar() or 0

    # 1-c) 최근 7일 실패
    r_failed = await db.execute(
        select(func.count()).select_from(WorkflowExecution).where(
            WorkflowExecution.status == ExecutionStatus.FAILED,
            WorkflowExecution.created_at >= week_start,
        )
    )
    failed: int = r_failed.scalar() or 0

    # 1-d) 최근 7일 완료
    r_completed = await db.execute(
        select(func.count()).select_from(WorkflowExecution).where(
            WorkflowExecution.status == ExecutionStatus.COMPLETED,
            WorkflowExecution.created_at >= week_start,
        )
    )
    completed: int = r_completed.scalar() or 0

    counts = {
        "todayRuns": today_runs,
        "inProgress": in_progress,
        "failed": failed,
        "completed": completed,
    }

    # ── 2. 워크플로우 목록 + 최신 인스턴스 ─────────────────────────────────
    wf_result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.nodes))
        .order_by(Workflow.updated_at.desc())
    )
    workflows: List[Workflow] = list(wf_result.scalars().all())

    if not workflows:
        return {"counts": counts, "workflows": []}

    # 각 워크플로우의 최신 인스턴스 1건을 배치 조회
    # (서브쿼리보다 단순: workflow_id 목록으로 최신 exec 가져오기)
    wf_ids = [wf.id for wf in workflows]

    # SQLAlchemy: SELECT * FROM workflow_executions WHERE workflow_id IN (...) ORDER BY created_at DESC
    # 후 Python에서 첫 번째만 추출 (SQLite 비동기 환경에서 LATERAL JOIN 미지원)
    exec_result = await db.execute(
        select(WorkflowExecution)
        .where(WorkflowExecution.workflow_id.in_(wf_ids))
        .order_by(WorkflowExecution.created_at.desc())
    )
    all_execs: List[WorkflowExecution] = list(exec_result.scalars().all())

    # workflow_id → 최신 인스턴스 맵
    latest_map: dict[str, WorkflowExecution] = {}
    for ex in all_execs:
        if ex.workflow_id not in latest_map:
            latest_map[ex.workflow_id] = ex

    # ── 3. 응답 조립 ────────────────────────────────────────────────────────
    def _exec_to_summary(ex: Optional[WorkflowExecution]) -> Optional[dict]:
        if ex is None:
            return None
        return {
            "id": ex.id,
            "status": ex.status.value if ex.status else None,
            "startedAt": ex.started_at.isoformat() if ex.started_at else None,
            "completedAt": ex.completed_at.isoformat() if ex.completed_at else None,
            "createdAt": ex.created_at.isoformat() if ex.created_at else None,
        }

    def _wf_to_summary(wf: Workflow) -> dict:
        latest = latest_map.get(wf.id)
        return {
            "id": wf.id,
            "name": wf.name,
            "description": wf.description,
            "status": wf.status.value if wf.status else None,
            "nodeCount": len(wf.nodes),
            "tags": wf.tags,
            "createdAt": wf.created_at.isoformat() if wf.created_at else None,
            "updatedAt": wf.updated_at.isoformat() if wf.updated_at else None,
            "latestInstance": _exec_to_summary(latest),
        }

    wf_summaries = [_wf_to_summary(wf) for wf in workflows]

    # 정렬: active 우선, 그다음 최신 인스턴스(latestInstance.createdAt) 기준
    def sort_key(item: dict):
        is_active = 0 if item["status"] == "active" else 1
        latest_inst = item.get("latestInstance")
        last_run = latest_inst["createdAt"] if latest_inst and latest_inst.get("createdAt") else item.get("updatedAt", "")
        return (is_active, "z" if not last_run else last_run)

    wf_summaries.sort(key=lambda x: (0 if x["status"] == "active" else 1,))

    return {"counts": counts, "workflows": wf_summaries}
