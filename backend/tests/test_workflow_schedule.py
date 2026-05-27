"""워크플로우 스케줄러 UI Phase A 검증.

검증 포인트:
- T1: 신규 워크플로우 default schedule_config 부여
- T2: PATCH /schedule {enabled:true, cronExpr} → DB 갱신
- T3: PATCH 후 ops/scheduler/jobs 에 wf:{id} 등록 확인
- T4: PATCH {enabled:false} → ops/scheduler/jobs 에서 제거
- T5: 잘못된 cron 표현식 → 422 (VALIDATION_ERROR/INVALID_CRON_EXPR)
- T6: GET /workflows/{id} 응답에 scheduleConfig 포함
- T7: next-run API 응답 형식

TestClient 는 컨텍스트 매니저로 사용하여 lifespan(=scheduler 기동) 을 발동시킨다.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.core.database import async_session_maker
from app.models.workflow import Workflow, WorkflowStatus


# ── 헬퍼 ───────────────────────────────────────────────────────────────────


async def _async_create_workflow(wf_id: str, status: WorkflowStatus) -> None:
    async with async_session_maker() as db:
        wf = Workflow(
            id=wf_id,
            name=f"Schedule 테스트 WF {wf_id}",
            description="test_workflow_schedule.py 용 자동 생성",
            status=status,
            tags=[],
            trigger={"type": "manual", "config": {}},
            variables={},
            created_by="test",
        )
        db.add(wf)
        await db.commit()


async def _async_delete_workflow(wf_id: str) -> None:
    async with async_session_maker() as db:
        wf = (
            await db.execute(select(Workflow).where(Workflow.id == wf_id))
        ).scalar_one_or_none()
        if wf is not None:
            await db.delete(wf)
            await db.commit()


async def _async_get_schedule_config(wf_id: str) -> dict | None:
    async with async_session_maker() as db:
        wf = (
            await db.execute(select(Workflow).where(Workflow.id == wf_id))
        ).scalar_one_or_none()
        return wf.schedule_config if wf else None


def _make_wf(status: WorkflowStatus = WorkflowStatus.ACTIVE) -> str:
    wf_id = f"wf-sched-{uuid.uuid4().hex[:6]}"
    asyncio.run(_async_create_workflow(wf_id, status))
    return wf_id


def _drop_wf(wf_id: str) -> None:
    asyncio.run(_async_delete_workflow(wf_id))


# ── T1 ────────────────────────────────────────────────────────────────────


def test_new_workflow_has_default_schedule_config():
    """신규 워크플로우는 default schedule_config 를 가져야 한다."""
    wf_id = _make_wf(WorkflowStatus.DRAFT)
    try:
        cfg = asyncio.run(_async_get_schedule_config(wf_id))
        assert cfg is not None
        assert cfg.get("enabled") is False
        assert cfg.get("cronExpr") == "0 * * * *"
        assert cfg.get("timezone") == "Asia/Seoul"
    finally:
        _drop_wf(wf_id)


# ── T2 + T3 + T4 (scheduler lifecycle 필요 → with TestClient(app)) ────────


def test_patch_schedule_updates_db_and_registers_job():
    """PATCH /schedule {enabled:true} → DB 갱신 + ops/scheduler/jobs 에 등록.

    이어서 enabled=false 로 PATCH → 등록 해제 확인.
    """
    wf_id = _make_wf(WorkflowStatus.ACTIVE)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            # T2: PATCH enabled=true
            r = client.patch(
                f"/api/v1/workflows/{wf_id}/schedule",
                json={"enabled": True, "cronExpr": "*/10 * * * *"},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["workflowId"] == wf_id
            assert body["scheduleConfig"]["enabled"] is True
            assert body["scheduleConfig"]["cronExpr"] == "*/10 * * * *"
            assert body["scheduleConfig"]["timezone"] == "Asia/Seoul"
            # ACTIVE + enabled → 등록되었으므로 nextRunTime 이 있어야 함
            assert body["nextRunTime"] is not None and isinstance(body["nextRunTime"], str)

            # DB 검증
            cfg = asyncio.run(_async_get_schedule_config(wf_id))
            assert cfg["enabled"] is True
            assert cfg["cronExpr"] == "*/10 * * * *"

            # T3: ops/scheduler/jobs 에 wf:{id} 등록 확인
            r2 = client.get("/api/v1/ops/scheduler/jobs")
            assert r2.status_code == 200
            jobs_body = r2.json()
            assert jobs_body["running"] is True
            job_ids = [j["id"] for j in jobs_body["jobs"]]
            assert f"wf:{wf_id}" in job_ids, f"job not registered, got={job_ids}"

            # T4: PATCH enabled=false → 등록 해제
            r3 = client.patch(
                f"/api/v1/workflows/{wf_id}/schedule",
                json={"enabled": False, "cronExpr": "*/10 * * * *"},
            )
            assert r3.status_code == 200, r3.text
            assert r3.json()["scheduleConfig"]["enabled"] is False
            # 비활성이면 next-run 없어야 함
            assert r3.json()["nextRunTime"] is None

            r4 = client.get("/api/v1/ops/scheduler/jobs")
            assert r4.status_code == 200
            jobs_body2 = r4.json()
            job_ids2 = [j["id"] for j in jobs_body2["jobs"]]
            assert f"wf:{wf_id}" not in job_ids2, f"job not removed, got={job_ids2}"
    finally:
        _drop_wf(wf_id)


# ── T5: invalid cron ──────────────────────────────────────────────────────


def test_patch_schedule_rejects_invalid_cron_expression():
    """잘못된 cron 표현식은 422 반환."""
    wf_id = _make_wf(WorkflowStatus.DRAFT)
    try:
        client = TestClient(app, raise_server_exceptions=False)
        r = client.patch(
            f"/api/v1/workflows/{wf_id}/schedule",
            json={"enabled": True, "cronExpr": "이상한값 not-a-cron"},
        )
        assert r.status_code == 422, r.text
        err = r.json()["error"]
        assert err["code"] in {"INVALID_CRON_EXPR", "VALIDATION_ERROR"}
    finally:
        _drop_wf(wf_id)


def test_patch_schedule_404_for_missing_workflow():
    """미존재 워크플로우 PATCH → 404."""
    client = TestClient(app, raise_server_exceptions=False)
    ghost = f"wf-ghost-{uuid.uuid4().hex[:6]}"
    r = client.patch(
        f"/api/v1/workflows/{ghost}/schedule",
        json={"enabled": True, "cronExpr": "*/10 * * * *"},
    )
    assert r.status_code == 404, r.text
    err = r.json()["error"]
    assert err["code"] == "NOT_FOUND"
    assert err["details"]["workflowId"] == ghost


# ── T6: GET /workflows/{id} 응답에 scheduleConfig 포함 ────────────────────


def test_workflow_detail_includes_schedule_config():
    """GET /workflows/{id} 와 GET /workflows 응답에 scheduleConfig 포함."""
    wf_id = _make_wf(WorkflowStatus.DRAFT)
    try:
        client = TestClient(app, raise_server_exceptions=False)

        # 상세
        r = client.get(f"/api/v1/workflows/{wf_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "scheduleConfig" in body
        assert body["scheduleConfig"]["enabled"] is False
        assert body["scheduleConfig"]["cronExpr"] == "0 * * * *"
        assert body["scheduleConfig"]["timezone"] == "Asia/Seoul"

        # 목록
        r2 = client.get("/api/v1/workflows")
        assert r2.status_code == 200, r2.text
        items = r2.json()
        # 우리가 만든 wf 가 들어있어야 함
        targets = [w for w in items if w["id"] == wf_id]
        assert len(targets) == 1
        assert "scheduleConfig" in targets[0]
        assert targets[0]["scheduleConfig"]["enabled"] is False
    finally:
        _drop_wf(wf_id)


# ── T7: next-run API 응답 형식 ─────────────────────────────────────────────


def test_next_run_api_response_shape():
    """GET /schedule/next-run 응답 형식 검증."""
    wf_id = _make_wf(WorkflowStatus.ACTIVE)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            # 등록 전 — registered=False, nextRunTime=None
            r = client.get(f"/api/v1/workflows/{wf_id}/schedule/next-run")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["workflowId"] == wf_id
            assert body["registered"] is False
            assert body["nextRunTime"] is None

            # enable 후
            r2 = client.patch(
                f"/api/v1/workflows/{wf_id}/schedule",
                json={"enabled": True, "cronExpr": "0 9 * * 1"},
            )
            assert r2.status_code == 200, r2.text

            r3 = client.get(f"/api/v1/workflows/{wf_id}/schedule/next-run")
            assert r3.status_code == 200, r3.text
            body3 = r3.json()
            assert body3["workflowId"] == wf_id
            assert body3["registered"] is True
            assert isinstance(body3["nextRunTime"], str) and body3["nextRunTime"]
    finally:
        _drop_wf(wf_id)


def test_next_run_404_for_missing_workflow():
    client = TestClient(app, raise_server_exceptions=False)
    ghost = f"wf-ghost-{uuid.uuid4().hex[:6]}"
    r = client.get(f"/api/v1/workflows/{ghost}/schedule/next-run")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
