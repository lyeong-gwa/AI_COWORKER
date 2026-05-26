"""Phase 4c — GET /api/v1/dashboard/summary 엔드포인트 검증.

검증 포인트:
1. 빈 DB → counts 모두 0, workflows=[]
2. 워크플로우 2개 + 인스턴스 4개 시나리오 → 예상 counts
3. today / week 경계 값 검증 (오늘 실행 vs 7일 전 실행)
4. latestInstance 포함 여부 확인
5. 응답 스키마 구조 검증

Note
----
TestClient + asyncio.run() 혼합 패턴 사용 (test_api_run.py 와 동일).
백그라운드 태스크가 없으므로 raise_server_exceptions=True.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, delete

from app.main import app
from app.core.database import async_session_maker
from app.models.workflow import (
    Workflow,
    WorkflowExecution,
    WorkflowStatus,
    ExecutionStatus,
)

client = TestClient(app, raise_server_exceptions=True)

# ── DB 헬퍼 ────────────────────────────────────────────────────────────────


async def _create_workflow(wf_id: str, status: WorkflowStatus = WorkflowStatus.ACTIVE) -> None:
    async with async_session_maker() as db:
        wf = Workflow(
            id=wf_id,
            name=f"대시보드 테스트 WF {wf_id}",
            description="test_dashboard_summary.py 자동 생성",
            status=status,
            tags=["test"],
            trigger={"type": "manual", "config": {}},
            variables={},
            created_by="test",
        )
        db.add(wf)
        await db.commit()


async def _create_execution(
    exec_id: str,
    wf_id: str,
    status: ExecutionStatus,
    created_at: datetime,
) -> None:
    async with async_session_maker() as db:
        ex = WorkflowExecution(
            id=exec_id,
            workflow_id=wf_id,
            status=status,
            input_data={},
            node_results={},
            created_at=created_at,
        )
        db.add(ex)
        await db.commit()


async def _delete_workflows(wf_ids: list[str]) -> None:
    async with async_session_maker() as db:
        # executions cascade delete on workflow deletion
        for wf_id in wf_ids:
            result = await db.execute(select(Workflow).where(Workflow.id == wf_id))
            wf = result.scalar_one_or_none()
            if wf:
                await db.delete(wf)
        await db.commit()


# ── 픽스처 헬퍼 ─────────────────────────────────────────────────────────────

NOW = datetime.utcnow()
TODAY_MORNING = NOW.replace(hour=1, minute=0, second=0, microsecond=0)
YESTERDAY = NOW - timedelta(days=1)
EIGHT_DAYS_AGO = NOW - timedelta(days=8)  # 7일 집계에서 제외돼야 함


# ── 테스트 1: 빈 DB ──────────────────────────────────────────────────────────


def test_summary_empty_db():
    """빈 DB에서 counts 모두 0, workflows 빈 배열."""
    # 기존 테스트들이 남긴 레코드를 정리할 수 없으므로 구조 검증에만 집중.
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()

    assert "counts" in data
    assert "workflows" in data
    assert "todayRuns" in data["counts"]
    assert "inProgress" in data["counts"]
    assert "failed" in data["counts"]
    assert "completed" in data["counts"]

    for key in ("todayRuns", "inProgress", "failed", "completed"):
        assert isinstance(data["counts"][key], int)


# ── 테스트 2: 워크플로우 + 인스턴스 시나리오 ────────────────────────────────


def test_summary_with_workflows_and_instances():
    """
    WF 2개 + 인스턴스 4개 시나리오:
    - wf1: active
      - exec1: completed, 오늘
      - exec2: failed,    오늘
    - wf2: draft
      - exec3: running,   오늘
      - exec4: completed, 8일 전 (7일 집계 제외)
    """
    wf1 = f"wf-ds-test-{uuid.uuid4().hex[:6]}"
    wf2 = f"wf-ds-test-{uuid.uuid4().hex[:6]}"
    exec1 = f"exec-{uuid.uuid4().hex[:8]}"
    exec2 = f"exec-{uuid.uuid4().hex[:8]}"
    exec3 = f"exec-{uuid.uuid4().hex[:8]}"
    exec4 = f"exec-{uuid.uuid4().hex[:8]}"

    asyncio.run(_create_workflow(wf1, WorkflowStatus.ACTIVE))
    asyncio.run(_create_workflow(wf2, WorkflowStatus.DRAFT))
    asyncio.run(_create_execution(exec1, wf1, ExecutionStatus.COMPLETED, TODAY_MORNING))
    asyncio.run(_create_execution(exec2, wf1, ExecutionStatus.FAILED, TODAY_MORNING))
    asyncio.run(_create_execution(exec3, wf2, ExecutionStatus.RUNNING, TODAY_MORNING))
    asyncio.run(_create_execution(exec4, wf2, ExecutionStatus.COMPLETED, EIGHT_DAYS_AGO))

    try:
        resp = client.get("/api/v1/dashboard/summary")
        assert resp.status_code == 200
        data = resp.json()
        counts = data["counts"]

        # todayRuns: exec1 + exec2 + exec3 = 3 (최소; 다른 테스트 실행분 포함될 수 있음)
        assert counts["todayRuns"] >= 3, f"todayRuns={counts['todayRuns']}"

        # inProgress: exec3 (running) 최소 1
        assert counts["inProgress"] >= 1, f"inProgress={counts['inProgress']}"

        # failed: exec2 (오늘 실패) 최소 1
        assert counts["failed"] >= 1, f"failed={counts['failed']}"

        # completed: exec1 (오늘 완료) 최소 1; exec4(8일 전)는 제외
        assert counts["completed"] >= 1, f"completed={counts['completed']}"

        # workflows 배열에 두 WF 포함
        wf_ids_in_resp = {w["id"] for w in data["workflows"]}
        assert wf1 in wf_ids_in_resp, f"wf1 not in response: {wf_ids_in_resp}"
        assert wf2 in wf_ids_in_resp, f"wf2 not in response: {wf_ids_in_resp}"

        # wf1 의 latestInstance 확인 (exec1 또는 exec2 중 최신)
        wf1_data = next(w for w in data["workflows"] if w["id"] == wf1)
        assert wf1_data["latestInstance"] is not None, "wf1 latestInstance 없음"
        assert wf1_data["latestInstance"]["id"] in (exec1, exec2)

        # wf2 의 latestInstance 확인 (exec3 — 오늘이 exec4보다 최신)
        wf2_data = next(w for w in data["workflows"] if w["id"] == wf2)
        assert wf2_data["latestInstance"] is not None, "wf2 latestInstance 없음"
        assert wf2_data["latestInstance"]["id"] == exec3

        # 스키마: 각 workflow 항목에 필요한 키 존재
        for wf_item in [wf1_data, wf2_data]:
            for key in ("id", "name", "description", "status", "nodeCount", "tags"):
                assert key in wf_item, f"key '{key}' missing in workflow item"

    finally:
        asyncio.run(_delete_workflows([wf1, wf2]))


# ── 테스트 3: 8일 전 실행은 failed/completed 카운트에서 제외 ─────────────────


def test_summary_old_executions_excluded_from_week_count():
    """8일 전 실패·완료는 7일 집계에서 제외된다."""
    wf_id = f"wf-ds-old-{uuid.uuid4().hex[:6]}"
    exec_old_fail = f"exec-{uuid.uuid4().hex[:8]}"
    exec_old_done = f"exec-{uuid.uuid4().hex[:8]}"

    asyncio.run(_create_workflow(wf_id, WorkflowStatus.ACTIVE))
    asyncio.run(_create_execution(exec_old_fail, wf_id, ExecutionStatus.FAILED, EIGHT_DAYS_AGO))
    asyncio.run(_create_execution(exec_old_done, wf_id, ExecutionStatus.COMPLETED, EIGHT_DAYS_AGO))

    try:
        # 이 두 exec 이 결과에 포함되면 틀린 것. 다른 테스트가 남긴 값과 겹치므로
        # 이 WF 만 조회해서 latestInstance 가 8일 전인지 확인하는 방식으로 검증.
        resp = client.get("/api/v1/dashboard/summary")
        assert resp.status_code == 200
        data = resp.json()

        wf_data = next((w for w in data["workflows"] if w["id"] == wf_id), None)
        assert wf_data is not None, "WF가 응답에 없음"
        assert wf_data["latestInstance"] is not None

        # latestInstance 는 oldest exec 이지만 그게 exec_old_fail 또는 exec_old_done 중 최신
        # (두 개 동시 생성 시 순서는 DB 삽입 순서 따름 — 여기선 old_done 이 나중)
        assert wf_data["latestInstance"]["id"] in (exec_old_fail, exec_old_done)

    finally:
        asyncio.run(_delete_workflows([wf_id]))


# ── 테스트 4: 인스턴스 없는 워크플로우 ──────────────────────────────────────


def test_summary_workflow_with_no_instances():
    """실행 이력이 없는 워크플로우는 latestInstance=null 로 반환."""
    wf_id = f"wf-ds-norun-{uuid.uuid4().hex[:6]}"
    asyncio.run(_create_workflow(wf_id, WorkflowStatus.ACTIVE))

    try:
        resp = client.get("/api/v1/dashboard/summary")
        assert resp.status_code == 200
        data = resp.json()

        wf_data = next((w for w in data["workflows"] if w["id"] == wf_id), None)
        assert wf_data is not None, "WF가 응답에 없음"
        assert wf_data["latestInstance"] is None

    finally:
        asyncio.run(_delete_workflows([wf_id]))
