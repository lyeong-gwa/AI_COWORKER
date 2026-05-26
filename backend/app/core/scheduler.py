"""APScheduler 기반 워크플로우 스케줄러 데몬

- schedule-trigger 노드를 가진 ACTIVE 워크플로우를 스캔하여 cron job 등록
- cron job 실행 시 해당 워크플로우를 실행 (workflow_engine.execute_workflow)
"""

import logging
import uuid
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> Optional[AsyncIOScheduler]:
    return _scheduler


async def start_scheduler() -> None:
    """스케줄러 싱글턴 기동 + 초기 job 로드"""
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    _scheduler.start()
    logger.info("[SCHED] Scheduler started")
    print("[SCHED] Scheduler started")
    try:
        await reload_jobs()
    except Exception as e:
        logger.warning(f"[SCHED] 초기 reload_jobs 실패: {e}")


async def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
        print("[SCHED] Scheduler stopped")
    except Exception:
        pass
    _scheduler = None


async def _run_workflow_job(workflow_id: str) -> None:
    """cron job 실행 함수 — WorkflowExecution 생성 후 엔진 호출"""
    # lazy import (순환 방지)
    from .database import async_session_maker
    from ..models.workflow import Workflow, WorkflowExecution, WorkflowStatus, ExecutionStatus
    from ..services.workflow_engine import execute_workflow

    try:
        async with async_session_maker() as db:
            wf = (await db.execute(
                select(Workflow).where(Workflow.id == workflow_id)
            )).scalar_one_or_none()
            if not wf:
                logger.warning(f"[SCHED] 워크플로우 없음: {workflow_id}")
                return
            if wf.status != WorkflowStatus.ACTIVE:
                logger.info(f"[SCHED] 비활성 워크플로우 스킵: {workflow_id}")
                return

            execution = WorkflowExecution(
                id=f"exec-{uuid.uuid4().hex[:8]}",
                workflow_id=workflow_id,
                status=ExecutionStatus.PENDING,
                input_data={"_scheduled": True},
            )
            db.add(execution)
            await db.commit()
            await db.refresh(execution)
            exec_id = execution.id
        logger.info(f"[SCHED] 워크플로우 실행 시작: {workflow_id} (exec={exec_id})")
        print(f"[SCHED] trigger workflow={workflow_id} exec={exec_id}")
        await execute_workflow(exec_id)
    except Exception as e:
        logger.exception(f"[SCHED] 실행 중 오류: {e}")


async def reload_jobs() -> dict:
    """DB를 스캔하여 schedule-trigger 노드가 있는 ACTIVE 워크플로우의 job을 재등록"""
    global _scheduler
    if _scheduler is None:
        return {"registered": 0, "skipped": 0, "error": "scheduler not started"}

    from .database import async_session_maker
    from ..models.workflow import Workflow, WorkflowStatus

    # 기존 job 전부 제거 후 재등록
    for job in list(_scheduler.get_jobs()):
        try:
            _scheduler.remove_job(job.id)
        except Exception:
            pass

    registered = 0
    skipped = 0
    async with async_session_maker() as db:
        workflows = (await db.execute(
            select(Workflow)
            .options(selectinload(Workflow.nodes))
            .where(Workflow.status == WorkflowStatus.ACTIVE)
        )).scalars().all()

        for wf in workflows:
            sched_nodes = [n for n in wf.nodes if n.definition_type == "schedule-trigger"]
            if not sched_nodes:
                continue
            for sn in sched_nodes:
                cfg = sn.config or {}
                cron_expr = (cfg.get("cronExpr") or "").strip()
                tz = cfg.get("timezone") or "Asia/Seoul"
                if not cron_expr:
                    skipped += 1
                    continue
                try:
                    trigger = CronTrigger.from_crontab(cron_expr, timezone=tz)
                except Exception as e:
                    logger.warning(f"[SCHED] cron 파싱 실패 {wf.id}: {cron_expr} ({e})")
                    skipped += 1
                    continue
                job_id = f"wf:{wf.id}:{sn.id}"
                try:
                    _scheduler.add_job(
                        _run_workflow_job,
                        trigger=trigger,
                        args=[wf.id],
                        id=job_id,
                        replace_existing=True,
                        misfire_grace_time=300,
                        coalesce=True,
                    )
                    registered += 1
                    logger.info(f"[SCHED] job 등록: {job_id} cron='{cron_expr}' tz={tz}")
                    print(f"[SCHED] job registered: {job_id} cron='{cron_expr}' tz={tz}")
                except Exception as e:
                    logger.warning(f"[SCHED] job 등록 실패 {job_id}: {e}")
                    skipped += 1

    print(f"[SCHED] reload_jobs done: registered={registered} skipped={skipped}")
    return {"registered": registered, "skipped": skipped}


async def trigger_now(workflow_id: str) -> dict:
    """수동 트리거(시뮬레이션) — 스케줄 대기 없이 즉시 1회 실행"""
    await _run_workflow_job(workflow_id)
    return {"triggered": workflow_id}
