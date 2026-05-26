"""Phase 4b — 서버 재시작 시 stale instance 복원 검증.

``app.main._cleanup_zombie_state`` 가 다음을 수행해야 한다:
1. ``workflow_executions.status`` 가 ``RUNNING`` 또는 ``PENDING`` 인 모든 행을
   ``FAILED`` 로 마킹.
2. ``error_message`` 에 재시작 안내 문구 기록.
3. ``completed_at`` 이 비어있다면 현재 시각으로 세팅.
4. 이미 종료된 상태(``COMPLETED``/``FAILED``/``CANCELLED``) 는 건드리지 않음.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.database import async_session_maker
from app.main import _cleanup_zombie_state
from app.models.workflow import (
    ExecutionStatus,
    Workflow,
    WorkflowExecution,
    WorkflowStatus,
)


async def _create_wf_with_executions(
    status_map: dict[str, ExecutionStatus],
) -> tuple[str, dict[str, str]]:
    wf_id = f"wf-stale-{uuid.uuid4().hex[:6]}"
    async with async_session_maker() as db:
        db.add(
            Workflow(
                id=wf_id,
                name="stale-test-wf",
                status=WorkflowStatus.ACTIVE,
                tags=[],
                trigger={"type": "manual", "config": {}},
                variables={},
                created_by="test",
            )
        )
        ids: dict[str, str] = {}
        for label, status in status_map.items():
            ex_id = f"exec-stale-{label}-{uuid.uuid4().hex[:4]}"
            db.add(
                WorkflowExecution(
                    id=ex_id,
                    workflow_id=wf_id,
                    status=status,
                    input_data={},
                )
            )
            ids[label] = ex_id
        await db.commit()
    return wf_id, ids


async def _cleanup(wf_id: str, ex_ids: list[str]) -> None:
    async with async_session_maker() as db:
        for ex_id in ex_ids:
            ex = (
                await db.execute(
                    select(WorkflowExecution).where(WorkflowExecution.id == ex_id)
                )
            ).scalar_one_or_none()
            if ex is not None:
                await db.delete(ex)
        wf = (
            await db.execute(select(Workflow).where(Workflow.id == wf_id))
        ).scalar_one_or_none()
        if wf is not None:
            await db.delete(wf)
        await db.commit()


@pytest.mark.asyncio
async def test_cleanup_marks_running_and_pending_as_failed():
    """RUNNING 과 PENDING 두 개가 각각 FAILED 로 전환되고, 종료된 건은 그대로."""
    wf_id, ids = await _create_wf_with_executions(
        {
            "running": ExecutionStatus.RUNNING,
            "pending": ExecutionStatus.PENDING,
            "done": ExecutionStatus.COMPLETED,
            "dead": ExecutionStatus.FAILED,
            "cancelled": ExecutionStatus.CANCELLED,
        }
    )
    try:
        await _cleanup_zombie_state()

        async with async_session_maker() as db:
            for label in ("running", "pending"):
                row = (
                    await db.execute(
                        select(WorkflowExecution).where(
                            WorkflowExecution.id == ids[label]
                        )
                    )
                ).scalar_one()
                assert row.status == ExecutionStatus.FAILED, (
                    f"{label} 가 FAILED 가 아님: status={row.status}"
                )
                assert (
                    row.error_message and "서버 재시작" in row.error_message
                ), f"{label} error_message 누락: {row.error_message}"
                assert row.completed_at is not None, (
                    f"{label} completed_at 이 비어있음"
                )

            # 이미 종료된 행들은 변화 없음
            for label, expected_status in (
                ("done", ExecutionStatus.COMPLETED),
                ("dead", ExecutionStatus.FAILED),
                ("cancelled", ExecutionStatus.CANCELLED),
            ):
                row = (
                    await db.execute(
                        select(WorkflowExecution).where(
                            WorkflowExecution.id == ids[label]
                        )
                    )
                ).scalar_one()
                assert row.status == expected_status, (
                    f"{label} 상태가 바뀜: {row.status} (기대: {expected_status})"
                )
    finally:
        await _cleanup(wf_id, list(ids.values()))


@pytest.mark.asyncio
async def test_cleanup_is_idempotent():
    """정리 루틴을 두 번 연속 호출해도 부작용이 없다 (이미 FAILED 로 바뀐 행은 재터치 X)."""
    wf_id, ids = await _create_wf_with_executions(
        {"running": ExecutionStatus.RUNNING}
    )
    try:
        await _cleanup_zombie_state()

        async with async_session_maker() as db:
            first = (
                await db.execute(
                    select(WorkflowExecution).where(
                        WorkflowExecution.id == ids["running"]
                    )
                )
            ).scalar_one()
            first_completed_at = first.completed_at
            first_error = first.error_message

        # 두 번째 호출
        await _cleanup_zombie_state()

        async with async_session_maker() as db:
            second = (
                await db.execute(
                    select(WorkflowExecution).where(
                        WorkflowExecution.id == ids["running"]
                    )
                )
            ).scalar_one()
            # 이미 FAILED 였으므로 completed_at 이 변하지 않아야 함
            assert second.completed_at == first_completed_at
            assert second.error_message == first_error
            assert second.status == ExecutionStatus.FAILED
    finally:
        await _cleanup(wf_id, list(ids.values()))
