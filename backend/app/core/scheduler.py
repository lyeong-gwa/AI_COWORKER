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
    """cron job 실행 함수 — WorkflowExecution 생성 후 엔진 호출.

    `schedule_config.payload` 가 dict 이면 트리거 입력값으로 input_data 에 병합한다.
    예: payload={"status": "신규"} → input_data={"_scheduled": True, "status": "신규"}.
    `_scheduled` 메타 키는 항상 포함되며, payload 의 동일 키와 충돌 시 payload 가 우선한다.
    """
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

            schedule_config = wf.schedule_config or {}
            payload = schedule_config.get("payload") if isinstance(schedule_config, dict) else None
            if not isinstance(payload, dict):
                payload = {}
            input_data = {"_scheduled": True, **payload}

            execution = WorkflowExecution(
                id=f"exec-{uuid.uuid4().hex[:8]}",
                workflow_id=workflow_id,
                status=ExecutionStatus.PENDING,
                input_data=input_data,
            )
            db.add(execution)
            await db.commit()
            await db.refresh(execution)
            exec_id = execution.id
        logger.info(
            f"[SCHED] 워크플로우 실행 시작: {workflow_id} (exec={exec_id}) "
            f"payloadKeys={sorted(list(payload.keys()))}"
        )
        print(f"[SCHED] trigger workflow={workflow_id} exec={exec_id}")
        await execute_workflow(exec_id)
    except Exception as e:
        logger.exception(f"[SCHED] 실행 중 오류: {e}")


async def reload_jobs() -> dict:
    """DB를 스캔하여 cron job 을 재등록.

    두 가지 소스를 병합하여 ACTIVE 워크플로우의 cron 을 추출한다 (중복 방지: job_id=`wf:{id}` 통일).
    1. (신규) workflow.schedule_config.enabled = true — UI 토글 기반
    2. (기존) 첫 노드가 schedule-trigger 인 워크플로우 — 노드 기반

    동일 워크플로가 양쪽 조건 모두 만족 시 schedule_config 가 우선한다.
    """
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
            # ── 소스 1: schedule_config (UI 토글, 우선순위 높음) ─────────
            sched_cfg = wf.schedule_config or {}
            cfg_cron = None
            cfg_tz = "Asia/Seoul"
            if isinstance(sched_cfg, dict) and sched_cfg.get("enabled") is True:
                cfg_cron = (sched_cfg.get("cronExpr") or "").strip() or None
                cfg_tz = sched_cfg.get("timezone") or "Asia/Seoul"

            # ── 소스 2: schedule-trigger 노드 (레거시) ─────────────────
            sched_nodes = [n for n in wf.nodes if n.definition_type == "schedule-trigger"]

            # 우선순위: schedule_config > 첫 schedule-trigger 노드
            chosen_cron = cfg_cron
            chosen_tz = cfg_tz
            chosen_source = "schedule_config" if cfg_cron else None

            if not chosen_cron and sched_nodes:
                # 가장 먼저 발견된 schedule-trigger 노드의 cron 사용
                for sn in sched_nodes:
                    ncfg = sn.config or {}
                    ncron = (ncfg.get("cronExpr") or "").strip()
                    if ncron:
                        chosen_cron = ncron
                        chosen_tz = ncfg.get("timezone") or "Asia/Seoul"
                        chosen_source = f"schedule-trigger:{sn.id}"
                        break

            if not chosen_cron:
                # 등록할 cron 없음 — 다음 워크플로우로
                continue

            try:
                trigger = CronTrigger.from_crontab(chosen_cron, timezone=chosen_tz)
            except Exception as e:
                logger.warning(f"[SCHED] cron 파싱 실패 {wf.id}: {chosen_cron} ({e})")
                skipped += 1
                continue

            # 중복 방지: 워크플로우당 단일 job_id
            job_id = f"wf:{wf.id}"
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
                logger.info(
                    f"[SCHED] job 등록: {job_id} cron='{chosen_cron}' tz={chosen_tz} src={chosen_source}"
                )
                print(
                    f"[SCHED] job registered: {job_id} cron='{chosen_cron}' tz={chosen_tz} src={chosen_source}"
                )
            except Exception as e:
                logger.warning(f"[SCHED] job 등록 실패 {job_id}: {e}")
                skipped += 1

    print(f"[SCHED] reload_jobs done: registered={registered} skipped={skipped}")
    return {"registered": registered, "skipped": skipped}


async def trigger_now(workflow_id: str) -> dict:
    """수동 트리거(시뮬레이션) — 스케줄 대기 없이 즉시 1회 실행"""
    await _run_workflow_job(workflow_id)
    return {"triggered": workflow_id}
