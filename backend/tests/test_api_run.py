"""Phase 2b — ``POST /api/v1/workflows/{id}/run`` 백그라운드 실행 스켈레톤 검증.

검증 포인트:
1. 존재하지 않는 workflow 에 대한 /run 호출 → 404 NOT_FOUND (envelope)
2. 활성화된 워크플로우에 /run 호출 → 202, ``{instanceId, workflowId, status:"queued", createdAt}``
3. 반환된 instanceId 로 인스턴스 상세 조회 가능
4. 인스턴스 상세는 envelope 에 ``workflowId``, ``status`` 포함
5. DRAFT 상태 워크플로우는 실행 불가 → WORKFLOW_NOT_ACTIVE 코드

Note
----
TestClient 는 내부적으로 BlockingPortal 을 사용해 sync→async 브릿지를 만든다.
따라서 테스트 자체는 **동기 함수**로 작성해야 하며, DB 선/후 정리는
``asyncio.run(...)`` 으로 수행한다. ``@pytest.mark.asyncio`` 와 TestClient 를
동시에 쓰면 nested event loop 충돌이 발생한다.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.core.database import async_session_maker
from app.models.workflow import Workflow, WorkflowStatus


# 백그라운드 태스크(workflow_engine.run) 가 노드가 없는 테스트용 WF 에서
# ValueError 를 발생시키더라도 응답 자체는 202 로 정상 반환되어야 한다.
# raise_server_exceptions=False 로 설정하면 TestClient 가 백그라운드 예외를
# 호출자에게 재전파하지 않는다. 엔진 내부는 catch 후 DB 에 FAILED 로 영속화한다.
client = TestClient(app, raise_server_exceptions=False)


# ── DB 헬퍼 ────────────────────────────────────────────────────────────────


async def _async_create_workflow(wf_id: str, status: WorkflowStatus) -> None:
    async with async_session_maker() as db:
        wf = Workflow(
            id=wf_id,
            name=f"Run 테스트 WF {wf_id}",
            description="test_api_run.py 용 자동 생성",
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
        result = await db.execute(select(Workflow).where(Workflow.id == wf_id))
        wf = result.scalar_one_or_none()
        if wf is not None:
            await db.delete(wf)
            await db.commit()


def _create_workflow(status: WorkflowStatus = WorkflowStatus.ACTIVE) -> str:
    wf_id = f"wf-test-{uuid.uuid4().hex[:6]}"
    asyncio.run(_async_create_workflow(wf_id, status))
    return wf_id


def _delete_workflow(wf_id: str) -> None:
    asyncio.run(_async_delete_workflow(wf_id))


# ── 테스트 케이스 ──────────────────────────────────────────────────────────


def test_run_missing_workflow_returns_404_envelope():
    r = client.post(
        "/api/v1/workflows/___no_such_wf___/run",
        json={"inputData": {}},
    )
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["details"].get("workflowId") == "___no_such_wf___"


def test_run_active_workflow_returns_queued_instance():
    wf_id = _create_workflow(WorkflowStatus.ACTIVE)
    try:
        r = client.post(
            f"/api/v1/workflows/{wf_id}/run",
            json={"inputData": {"foo": "bar"}},
        )
        assert r.status_code == 202, r.text
        body = r.json()
        # 설계서 섹션 5.2: 응답은 instanceId, workflowId, status, createdAt
        assert set(body.keys()) >= {"instanceId", "workflowId", "status", "createdAt"}
        assert body["workflowId"] == wf_id
        assert body["status"] == "queued"
        assert isinstance(body["instanceId"], str) and body["instanceId"].startswith(
            "exec-"
        )
        assert isinstance(body["createdAt"], str) and body["createdAt"]

        # 인스턴스 상세 조회 — camelCase + instanceId 필드
        instance_id = body["instanceId"]
        r2 = client.get(f"/api/v1/warehouse/instances/{instance_id}")
        assert r2.status_code == 200, r2.text
        detail = r2.json()
        assert detail["instanceId"] == instance_id
        assert detail["workflowId"] == wf_id
        # status 는 실행 엔진 진행에 따라 변할 수 있으므로 유효 값만 검증
        assert detail["status"] in {
            "pending",
            "running",
            "completed",
            "failed",
            "cancelled",
        }
    finally:
        _delete_workflow(wf_id)


def test_run_draft_workflow_returns_not_active_error():
    wf_id = _create_workflow(WorkflowStatus.DRAFT)
    try:
        r = client.post(
            f"/api/v1/workflows/{wf_id}/run",
            json={"inputData": {}},
        )
        assert r.status_code == 400
        body = r.json()
        assert body["error"]["code"] == "WORKFLOW_NOT_ACTIVE"
        assert body["error"]["details"].get("workflowId") == wf_id
        assert body["error"]["details"].get("status") == "draft"
    finally:
        _delete_workflow(wf_id)


def test_run_accepts_empty_input_data():
    """inputData 를 생략해도 (디폴트 {}) 정상 접수되어야 한다."""
    wf_id = _create_workflow(WorkflowStatus.ACTIVE)
    try:
        r = client.post(f"/api/v1/workflows/{wf_id}/run", json={})
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["status"] == "queued"
        assert body["instanceId"].startswith("exec-")
    finally:
        _delete_workflow(wf_id)


# ── SSE 스트림 스모크 테스트 ──────────────────────────────────────────────


async def _async_mark_instance_completed(ex_id: str) -> None:
    """DB 에 직접 완료 상태 인스턴스를 삽입 (BackgroundTask 의존하지 않음)."""
    from app.models.workflow import WorkflowExecution, ExecutionStatus
    from datetime import datetime

    async with async_session_maker() as db:
        db.add(
            WorkflowExecution(
                id=ex_id,
                workflow_id="wf-stream-test",
                status=ExecutionStatus.COMPLETED,
                input_data={},
                output_data={"ok": True},
                node_results={
                    "n1": {"status": "completed", "outputData": {"x": 1}},
                },
                completed_at=datetime.utcnow(),
            )
        )
        await db.commit()


async def _async_cleanup_instance_only(ex_id: str) -> None:
    from app.models.workflow import WorkflowExecution

    async with async_session_maker() as db:
        ex = (
            await db.execute(
                select(WorkflowExecution).where(WorkflowExecution.id == ex_id)
            )
        ).scalar_one_or_none()
        if ex is not None:
            await db.delete(ex)
            await db.commit()


def test_stream_missing_instance_returns_404_envelope():
    r = client.get("/api/v1/warehouse/instances/___no_instance_stream___/stream")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "NOT_FOUND"


def test_stream_emits_sse_events_for_completed_instance():
    ex_id = f"exec-stream-{uuid.uuid4().hex[:6]}"
    asyncio.run(_async_mark_instance_completed(ex_id))
    try:
        with client.stream(
            "GET", f"/api/v1/warehouse/instances/{ex_id}/stream"
        ) as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers.get("content-type", "")
            # 제한적으로 읽어서 execution_complete 까지 도달하는지 확인
            seen_events: list[str] = []
            for line in r.iter_lines():
                if line.startswith("event: "):
                    seen_events.append(line[len("event: "):])
                if "execution_complete" in line:
                    break
            assert "stream_open" in seen_events
            assert "execution_complete" in seen_events
    finally:
        asyncio.run(_async_cleanup_instance_only(ex_id))
