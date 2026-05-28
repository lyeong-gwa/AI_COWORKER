"""워크플로우 스케줄러 UI Phase A 검증.

검증 포인트:
- T1: 신규 워크플로우 default schedule_config 부여
- T2: PATCH /schedule {enabled:true, cronExpr} → DB 갱신
- T3: PATCH 후 ops/scheduler/jobs 에 wf:{id} 등록 확인
- T4: PATCH {enabled:false} → ops/scheduler/jobs 에서 제거
- T5: 잘못된 cron 표현식 → 422 (VALIDATION_ERROR/INVALID_CRON_EXPR)
- T6: GET /workflows/{id} 응답에 scheduleConfig 포함
- T7: next-run API 응답 형식
- T8: PATCH 에 payload 포함 → DB 의 schedule_config.payload 갱신
- T9: payload 없이 PATCH → 기존 payload 보존, 신규 워크플로우는 {} 유지
- T10: scheduler.trigger_now → 인스턴스의 input_data 에 payload 병합

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
        # 트리거 입력값(payload) default 는 빈 dict
        assert cfg.get("payload") == {}
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


# ── T8 / T9: payload PATCH 동작 ─────────────────────────────────────────────


def test_patch_schedule_persists_payload():
    """T8: PATCH 에 payload 포함 → DB 의 schedule_config.payload 에 저장된다."""
    wf_id = _make_wf(WorkflowStatus.DRAFT)
    try:
        client = TestClient(app, raise_server_exceptions=False)
        r = client.patch(
            f"/api/v1/workflows/{wf_id}/schedule",
            json={
                "enabled": False,
                "cronExpr": "*/10 * * * *",
                "payload": {"status": "신규", "limit": 50, "active": True},
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["scheduleConfig"]["payload"] == {
            "status": "신규",
            "limit": 50,
            "active": True,
        }

        # DB 직접 검증
        cfg = asyncio.run(_async_get_schedule_config(wf_id))
        assert cfg is not None
        assert cfg.get("payload") == {
            "status": "신규",
            "limit": 50,
            "active": True,
        }
    finally:
        _drop_wf(wf_id)


def test_patch_schedule_without_payload_preserves_existing():
    """T9: payload 키 없이 PATCH → 기존 payload 보존. 신규 wf 의 default 는 {}."""
    wf_id = _make_wf(WorkflowStatus.DRAFT)
    try:
        client = TestClient(app, raise_server_exceptions=False)

        # 1) 처음 PATCH — payload 없음 → 기존 default({})가 보존되어야 함
        r1 = client.patch(
            f"/api/v1/workflows/{wf_id}/schedule",
            json={"enabled": False, "cronExpr": "*/10 * * * *"},
        )
        assert r1.status_code == 200, r1.text
        assert r1.json()["scheduleConfig"]["payload"] == {}

        # DB 검증 — 빈 dict 유지
        cfg1 = asyncio.run(_async_get_schedule_config(wf_id))
        assert cfg1.get("payload") == {}

        # 2) payload 설정
        r2 = client.patch(
            f"/api/v1/workflows/{wf_id}/schedule",
            json={
                "enabled": False,
                "cronExpr": "*/10 * * * *",
                "payload": {"status": "신규"},
            },
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["scheduleConfig"]["payload"] == {"status": "신규"}

        # 3) payload 없이 다른 필드만 PATCH → 기존 payload 보존
        r3 = client.patch(
            f"/api/v1/workflows/{wf_id}/schedule",
            json={"enabled": False, "cronExpr": "0 * * * *"},
        )
        assert r3.status_code == 200, r3.text
        assert r3.json()["scheduleConfig"]["payload"] == {"status": "신규"}

        cfg3 = asyncio.run(_async_get_schedule_config(wf_id))
        assert cfg3.get("payload") == {"status": "신규"}
        assert cfg3.get("cronExpr") == "0 * * * *"

        # 4) 명시적으로 빈 dict → 비움
        r4 = client.patch(
            f"/api/v1/workflows/{wf_id}/schedule",
            json={"enabled": False, "cronExpr": "0 * * * *", "payload": {}},
        )
        assert r4.status_code == 200, r4.text
        assert r4.json()["scheduleConfig"]["payload"] == {}
    finally:
        _drop_wf(wf_id)


# ── T10: scheduler 즉시 실행이 payload 를 input_data 에 병합 ────────────────


def test_scheduler_run_includes_payload_in_input_data():
    """T10: schedule_config.payload 가 trigger_now 실행 시 input_data 에 병합된다.

    workflow_engine 의 노드 실행을 우회하기 위해 execute_workflow 를 모킹.
    스케줄러는 WorkflowExecution 만 생성·커밋한 뒤 execute_workflow 를 호출하므로
    DB 의 input_data 를 직접 조회해 검증.
    """
    from app.models.workflow import WorkflowExecution
    from app.core import scheduler as scheduler_mod

    wf_id = _make_wf(WorkflowStatus.ACTIVE)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            # payload 저장
            r = client.patch(
                f"/api/v1/workflows/{wf_id}/schedule",
                json={
                    "enabled": False,  # cron job 자체 등록은 불필요
                    "cronExpr": "*/10 * * * *",
                    "payload": {"status": "신규", "_scheduled": "overwritten"},
                },
            )
            assert r.status_code == 200, r.text

            # execute_workflow 모킹 (호출만 패스)
            calls: list[str] = []

            async def _noop_execute(exec_id: str) -> None:
                calls.append(exec_id)

            # scheduler 모듈 안에서 from ..services.workflow_engine import execute_workflow
            # 형태로 함수 내부 lazy import → 패치는 services.workflow_engine.execute_workflow 자체로.
            import app.services.workflow_engine as engine_mod
            original = engine_mod.execute_workflow
            engine_mod.execute_workflow = _noop_execute  # type: ignore[assignment]
            try:
                # 즉시 실행 시뮬레이션
                asyncio.run(scheduler_mod._run_workflow_job(wf_id))
            finally:
                engine_mod.execute_workflow = original  # type: ignore[assignment]

            assert len(calls) == 1, f"execute_workflow 호출 1회 기대, got={calls}"
            exec_id = calls[0]

            # DB 의 WorkflowExecution.input_data 직접 조회
            async def _fetch_input_data(eid: str) -> dict | None:
                async with async_session_maker() as db:
                    row = (
                        await db.execute(
                            select(WorkflowExecution).where(WorkflowExecution.id == eid)
                        )
                    ).scalar_one_or_none()
                    return row.input_data if row else None

            input_data = asyncio.run(_fetch_input_data(exec_id))
            assert input_data is not None
            # _scheduled 메타 키는 payload 의 동일 키에 의해 덮어써진다 (payload 우선)
            assert input_data.get("status") == "신규"
            assert input_data.get("_scheduled") == "overwritten"

            # 정리 — 생성된 인스턴스 제거
            async def _cleanup(eid: str) -> None:
                async with async_session_maker() as db:
                    row = (
                        await db.execute(
                            select(WorkflowExecution).where(WorkflowExecution.id == eid)
                        )
                    ).scalar_one_or_none()
                    if row:
                        await db.delete(row)
                        await db.commit()
            asyncio.run(_cleanup(exec_id))
    finally:
        _drop_wf(wf_id)


def test_scheduler_run_without_payload_keeps_scheduled_marker():
    """payload 가 비어 있으면 input_data 는 {'_scheduled': True} 만 가진다."""
    from app.models.workflow import WorkflowExecution
    from app.core import scheduler as scheduler_mod

    wf_id = _make_wf(WorkflowStatus.ACTIVE)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.patch(
                f"/api/v1/workflows/{wf_id}/schedule",
                json={"enabled": False, "cronExpr": "*/10 * * * *"},
            )
            assert r.status_code == 200, r.text

            calls: list[str] = []

            async def _noop_execute(exec_id: str) -> None:
                calls.append(exec_id)

            import app.services.workflow_engine as engine_mod
            original = engine_mod.execute_workflow
            engine_mod.execute_workflow = _noop_execute  # type: ignore[assignment]
            try:
                asyncio.run(scheduler_mod._run_workflow_job(wf_id))
            finally:
                engine_mod.execute_workflow = original  # type: ignore[assignment]

            assert len(calls) == 1
            exec_id = calls[0]

            async def _fetch_input_data(eid: str) -> dict | None:
                async with async_session_maker() as db:
                    row = (
                        await db.execute(
                            select(WorkflowExecution).where(WorkflowExecution.id == eid)
                        )
                    ).scalar_one_or_none()
                    return row.input_data if row else None

            input_data = asyncio.run(_fetch_input_data(exec_id))
            assert input_data == {"_scheduled": True}

            async def _cleanup(eid: str) -> None:
                async with async_session_maker() as db:
                    row = (
                        await db.execute(
                            select(WorkflowExecution).where(WorkflowExecution.id == eid)
                        )
                    ).scalar_one_or_none()
                    if row:
                        await db.delete(row)
                        await db.commit()
            asyncio.run(_cleanup(exec_id))
    finally:
        _drop_wf(wf_id)
