"""Phase 4b — SSE 엔드포인트가 ExecutionEventBus 기반 push 로 동작하는지 검증.

검증 포인트
----------
1. 이미 종료된 인스턴스에 연결하면 ``stream_open`` 스냅샷 + ``execution_complete``
   을 즉시 보내고 스트림 종료.
2. ``stream_open`` 이벤트에 현재 ``nodeResults`` 스냅샷이 포함됨.
3. 실행 중인 인스턴스에 이벤트가 publish 되면 SSE 로 릴레이.
4. heartbeat 타입 이벤트도 정상적으로 전달.

실행 중 테스트 전략
------------------
TestClient 내부 portal 은 request 중에만 활성화되므로, 테스트 스레드에서
bus.publish 를 하려면 별도의 ``anyio.blocking_portal`` 을 열고 그 portal 을
TestClient 에 주입해야 한다. 그래야 SSE 제너레이터와 publisher 가 같은
event loop 를 공유한다.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from datetime import datetime

import anyio.from_thread
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import async_session_maker
from app.main import app
from app.models.workflow import (
    ExecutionStatus,
    WorkflowExecution,
)
from app.schemas.workflow import ExecutionLogEvent
from app.services.execution_bus import (
    _reset_execution_bus_for_tests,
    get_execution_bus,
)


# 간단한 테스트(404, 스냅샷)는 기본 client 로 충분
client = TestClient(app, raise_server_exceptions=False)


# ── DB helper ─────────────────────────────────────────────────────────────


async def _mark_completed(ex_id: str, node_results: dict) -> None:
    async with async_session_maker() as db:
        db.add(
            WorkflowExecution(
                id=ex_id,
                workflow_id=f"wf-sse-bus-{uuid.uuid4().hex[:4]}",
                status=ExecutionStatus.COMPLETED,
                input_data={},
                output_data={"finished": True},
                node_results=node_results,
                completed_at=datetime.utcnow(),
            )
        )
        await db.commit()


async def _mark_running(ex_id: str) -> None:
    async with async_session_maker() as db:
        db.add(
            WorkflowExecution(
                id=ex_id,
                workflow_id=f"wf-sse-bus-{uuid.uuid4().hex[:4]}",
                status=ExecutionStatus.RUNNING,
                input_data={},
                node_results={},
                started_at=datetime.utcnow(),
            )
        )
        await db.commit()


async def _delete_execution(ex_id: str) -> None:
    async with async_session_maker() as db:
        ex = (
            await db.execute(
                select(WorkflowExecution).where(WorkflowExecution.id == ex_id)
            )
        ).scalar_one_or_none()
        if ex is not None:
            await db.delete(ex)
            await db.commit()


# ── 테스트 ────────────────────────────────────────────────────────────────


def test_stream_open_includes_snapshot_for_completed_instance():
    """이미 종료된 실행에 연결하면 stream_open 에 스냅샷이 실리고 execution_complete 로 즉시 종료."""
    _reset_execution_bus_for_tests()
    ex_id = f"exec-sse-snap-{uuid.uuid4().hex[:6]}"
    node_results = {
        "node-1": {
            "status": "completed",
            "outputData": {"x": 1},
            "definitionType": "form-start",
        },
        "node-2": {
            "status": "completed",
            "outputData": {"y": 2},
            "definitionType": "result",
        },
    }
    asyncio.run(_mark_completed(ex_id, node_results))

    try:
        seen: list[tuple[str, dict]] = []
        with client.stream("GET", f"/api/v1/warehouse/instances/{ex_id}/stream") as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers.get("content-type", "")

            current_event: str | None = None
            for line in r.iter_lines():
                if not line:
                    current_event = None
                    continue
                if line.startswith("event: "):
                    current_event = line[len("event: ") :]
                elif line.startswith("data: ") and current_event:
                    try:
                        payload = json.loads(line[len("data: ") :])
                    except json.JSONDecodeError:
                        continue
                    seen.append((current_event, payload))
                    current_event = None

                if seen and seen[-1][0] == "execution_complete":
                    break

        event_types = [ev for ev, _ in seen]
        assert "stream_open" in event_types
        assert "execution_complete" in event_types

        # stream_open 스냅샷 검증
        open_payload = next(data for ev, data in seen if ev == "stream_open")
        assert open_payload["instanceId"] == ex_id
        assert open_payload["status"] == "completed"
        assert "nodeResults" in open_payload
        assert set(open_payload["nodeResults"].keys()) == {"node-1", "node-2"}
        assert (
            open_payload["nodeResults"]["node-1"]["outputData"] == {"x": 1}
        )

        # execution_complete 페이로드
        complete_payload = next(
            data for ev, data in seen if ev == "execution_complete"
        )
        assert complete_payload["status"] == "completed"
    finally:
        asyncio.run(_delete_execution(ex_id))
        _reset_execution_bus_for_tests()


def _stream_and_publish(
    ex_id: str,
    publish_events: list[ExecutionLogEvent],
    delay_before_first: float = 0.3,
    delay_between: float = 0.05,
    overall_timeout: float = 10.0,
) -> list[tuple[str, dict]]:
    """TestClient 의 portal 을 공유하는 방식으로 SSE 를 읽으며 bus.publish 수행.

    Returns
    -------
    list[(event_type, payload)]
    """
    with anyio.from_thread.start_blocking_portal() as portal:
        # portal 을 주입한 TestClient 생성 → request 내부 이벤트 루프 공유
        client_with_portal = TestClient(app, raise_server_exceptions=False)
        client_with_portal.portal = portal

        bus = get_execution_bus()

        def publisher():
            time.sleep(delay_before_first)
            for event in publish_events:
                try:
                    portal.call(bus.publish, ex_id, event)
                except Exception as exc:
                    print(f"[publisher] publish 실패: {exc}")
                    return
                time.sleep(delay_between)

        pub_t = threading.Thread(target=publisher, daemon=True)
        pub_t.start()

        seen: list[tuple[str, dict]] = []
        with client_with_portal.stream(
            "GET", f"/api/v1/warehouse/instances/{ex_id}/stream"
        ) as r:
            assert r.status_code == 200
            current_event: str | None = None
            started = time.time()
            for line in r.iter_lines():
                if time.time() - started > overall_timeout:
                    break
                if not line:
                    current_event = None
                    continue
                if line.startswith("event: "):
                    current_event = line[len("event: ") :]
                elif line.startswith("data: ") and current_event:
                    try:
                        payload = json.loads(line[len("data: ") :])
                    except json.JSONDecodeError:
                        continue
                    seen.append((current_event, payload))
                    current_event = None
                    if seen[-1][0] == "execution_complete":
                        break

        pub_t.join(timeout=2.0)
    return seen


def test_stream_relays_events_from_execution_bus():
    """실행 중 인스턴스에 bus.publish 로 이벤트를 넣으면 SSE 로 릴레이."""
    _reset_execution_bus_for_tests()
    ex_id = f"exec-sse-relay-{uuid.uuid4().hex[:6]}"
    asyncio.run(_mark_running(ex_id))

    try:
        seen = _stream_and_publish(
            ex_id,
            publish_events=[
                ExecutionLogEvent(
                    eventType="node_start",
                    timestamp=datetime.utcnow(),
                    nodeId="n-relay-1",
                    data={
                        "definitionType": "form-start",
                        "startTime": datetime.utcnow().isoformat(),
                    },
                ),
                ExecutionLogEvent(
                    eventType="node_complete",
                    timestamp=datetime.utcnow(),
                    nodeId="n-relay-1",
                    data={
                        "definitionType": "form-start",
                        "output": {"relayed": True},
                        "endTime": datetime.utcnow().isoformat(),
                    },
                ),
                ExecutionLogEvent(
                    eventType="execution_complete",
                    timestamp=datetime.utcnow(),
                    nodeId=None,
                    data={
                        "status": ExecutionStatus.COMPLETED.value,
                        "outputData": {"done": True},
                    },
                ),
            ],
        )

        event_types = [ev for ev, _ in seen]
        assert event_types, "수신된 이벤트가 없음"
        assert event_types[0] == "stream_open"
        assert "node_start" in event_types, f"node_start 릴레이 안 됨: {event_types}"
        assert "node_complete" in event_types, (
            f"node_complete 릴레이 안 됨: {event_types}"
        )
        assert event_types[-1] == "execution_complete"

        # 각 이벤트 payload 확인
        ns = next(data for ev, data in seen if ev == "node_start")
        assert ns["nodeId"] == "n-relay-1"
        assert ns["status"] == "running"

        nc = next(data for ev, data in seen if ev == "node_complete")
        assert nc["nodeId"] == "n-relay-1"
        assert nc["output"] == {"relayed": True}
        assert nc["status"] == "completed"
    finally:
        asyncio.run(_delete_execution(ex_id))
        _reset_execution_bus_for_tests()


def test_stream_returns_404_for_missing_instance():
    """존재하지 않는 인스턴스는 즉시 404 envelope."""
    r = client.get("/api/v1/warehouse/instances/___no_sse_target___/stream")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "NOT_FOUND"


def test_stream_relays_heartbeat_event():
    """엔진이 보내는 heartbeat 이벤트가 SSE 에 릴레이된다."""
    _reset_execution_bus_for_tests()
    ex_id = f"exec-sse-hb-{uuid.uuid4().hex[:6]}"
    asyncio.run(_mark_running(ex_id))

    try:
        seen = _stream_and_publish(
            ex_id,
            publish_events=[
                ExecutionLogEvent(
                    eventType="heartbeat",
                    timestamp=datetime.utcnow(),
                    nodeId=None,
                    data={"timestamp": datetime.utcnow().isoformat()},
                ),
                ExecutionLogEvent(
                    eventType="execution_complete",
                    timestamp=datetime.utcnow(),
                    nodeId=None,
                    data={"status": ExecutionStatus.COMPLETED.value},
                ),
            ],
        )

        event_types = [ev for ev, _ in seen]
        assert "heartbeat" in event_types, f"heartbeat 릴레이 안됨: {event_types}"

        hb = next(data for ev, data in seen if ev == "heartbeat")
        assert "timestamp" in hb
    finally:
        asyncio.run(_delete_execution(ex_id))
        _reset_execution_bus_for_tests()
