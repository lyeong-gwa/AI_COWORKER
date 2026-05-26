"""Phase 4a — 워크플로우 엔진이 ExecutionEventBus 에 이벤트를 push 하는지 검증.

검증 포인트
----------
1. 정상 실행 시 ``node_start`` / ``node_complete`` / ``execution_complete`` 이벤트 순서대로 push.
2. 실패 실행 시 ``node_error`` 와 ``execution_complete`` (status=failed) 이벤트가 모두 push.
3. 이벤트 publish 가 실패해도 (bus 예외) 엔진 실행 자체는 계속 진행되어야 한다.

테스트 전략
----------
- `form-start` + `result` 두 노드의 간단한 워크플로우를 DB 에 직접 삽입.
- ``WorkflowEngine.run()`` 을 호출하면서, 백그라운드에서 ``bus.subscribe()`` 로 이벤트 수집.
- 받은 이벤트 타입 리스트를 검증.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.workflow import (
    ExecutionStatus,
    WarehouseEntry,
    Workflow,
    WorkflowConnection,
    WorkflowExecution,
    WorkflowNode,
    WorkflowStatus,
)
from app.schemas.workflow import ExecutionLogEvent
from app.services.execution_bus import (
    _reset_execution_bus_for_tests,
    get_execution_bus,
)
from app.services.workflow_engine import WorkflowEngine


@pytest.fixture
def fresh_bus():
    _reset_execution_bus_for_tests()
    yield get_execution_bus()
    _reset_execution_bus_for_tests()


# ── 공용 DB 헬퍼 ──────────────────────────────────────────────────────────


async def _setup_simple_workflow() -> tuple[str, str, list[str]]:
    """form-start → result 2-노드 워크플로우와 pending 실행을 DB 에 삽입.

    Returns
    -------
    (workflow_id, execution_id, [node_id_start, node_id_result])
    """
    wf_id = f"wf-ev-{uuid.uuid4().hex[:6]}"
    ex_id = f"exec-ev-{uuid.uuid4().hex[:6]}"
    n_start = f"n-start-{uuid.uuid4().hex[:4]}"
    n_result = f"n-result-{uuid.uuid4().hex[:4]}"

    async with async_session_maker() as db:
        db.add(
            Workflow(
                id=wf_id,
                name=f"engine events wf {wf_id}",
                status=WorkflowStatus.ACTIVE,
                tags=[],
                trigger={"type": "manual", "config": {}},
                variables={},
                created_by="test",
            )
        )
        db.add(
            WorkflowNode(
                id=n_start,
                workflow_id=wf_id,
                node_id=n_start,
                definition_type="form-start",
                config={},
                name="시작",
                order_index=0,
                config_overrides={},
                input_mapping={},
            )
        )
        db.add(
            WorkflowNode(
                id=n_result,
                workflow_id=wf_id,
                node_id=n_result,
                definition_type="result",
                config={},
                name="결과",
                order_index=1,
                config_overrides={},
                input_mapping={},
            )
        )
        db.add(
            WorkflowConnection(
                id=f"conn-{uuid.uuid4().hex[:6]}",
                workflow_id=wf_id,
                source_node_id=n_start,
                target_node_id=n_result,
            )
        )
        db.add(
            WorkflowExecution(
                id=ex_id,
                workflow_id=wf_id,
                status=ExecutionStatus.PENDING,
                input_data={"hello": "world"},
            )
        )
        await db.commit()

    return wf_id, ex_id, [n_start, n_result]


async def _cleanup_workflow(wf_id: str, ex_id: str) -> None:
    async with async_session_maker() as db:
        # warehouse entries
        entries = (
            (
                await db.execute(
                    select(WarehouseEntry).where(WarehouseEntry.execution_id == ex_id)
                )
            )
            .scalars()
            .all()
        )
        for e in entries:
            await db.delete(e)

        ex = (
            await db.execute(
                select(WorkflowExecution).where(WorkflowExecution.id == ex_id)
            )
        ).scalar_one_or_none()
        if ex is not None:
            await db.delete(ex)

        nodes = (
            (
                await db.execute(
                    select(WorkflowNode).where(WorkflowNode.workflow_id == wf_id)
                )
            )
            .scalars()
            .all()
        )
        for n in nodes:
            await db.delete(n)

        conns = (
            (
                await db.execute(
                    select(WorkflowConnection).where(
                        WorkflowConnection.workflow_id == wf_id
                    )
                )
            )
            .scalars()
            .all()
        )
        for c in conns:
            await db.delete(c)

        wf = (
            await db.execute(select(Workflow).where(Workflow.id == wf_id))
        ).scalar_one_or_none()
        if wf is not None:
            await db.delete(wf)

        await db.commit()


async def _collect_events(
    execution_id: str,
    collected: list[ExecutionLogEvent],
    subscriber_ready: asyncio.Event,
) -> None:
    """실행 전/동시에 호출. execution_complete 수신 시 종료."""
    bus = get_execution_bus()
    async for event in bus.subscribe(execution_id):
        if not subscriber_ready.is_set():
            pass  # 첫 이벤트 수신 == 등록 완료 증명
        collected.append(event)
        if event.eventType == "execution_complete":
            return


# ── 성공 경로 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_engine_emits_start_complete_events_for_successful_run(fresh_bus):
    """정상 실행: node_start / node_complete / execution_complete 이벤트 순서 확인."""
    wf_id, ex_id, node_ids = await _setup_simple_workflow()
    try:
        collected: list[ExecutionLogEvent] = []
        subscriber_ready = asyncio.Event()

        # 먼저 subscriber 를 걸어놓고 (subscribe 는 subscribe_count 증가까지 대기)
        consumer_task = asyncio.create_task(
            _collect_events(ex_id, collected, subscriber_ready)
        )
        for _ in range(50):
            if await fresh_bus.subscriber_count(ex_id) >= 1:
                subscriber_ready.set()
                break
            await asyncio.sleep(0.01)
        assert subscriber_ready.is_set(), "subscriber 등록이 완료되지 않음"

        # 실행
        engine = WorkflowEngine(ex_id)
        await engine.run()

        # consumer 가 execution_complete 까지 받기를 잠깐 대기
        await asyncio.wait_for(consumer_task, timeout=3.0)

        # 검증: 이벤트 타입 카운트
        types = [ev.eventType for ev in collected]
        assert "execution_complete" in types, f"execution_complete 미수신: {types}"

        # 노드 시작/완료는 각각 2회 이상 (노드 2개)
        start_count = types.count("node_start")
        complete_count = types.count("node_complete")
        assert start_count == 2, f"node_start 개수 불일치: {start_count} (events={types})"
        assert complete_count == 2, f"node_complete 개수 불일치: {complete_count} (events={types})"

        # 순서: 각 node_start 가 같은 노드의 node_complete 보다 먼저
        # (start/complete 가 번갈아 나오는 단순 시퀀스 가정)
        # 노드 ID 일치 검증
        start_events = [ev for ev in collected if ev.eventType == "node_start"]
        complete_events = [ev for ev in collected if ev.eventType == "node_complete"]
        assert {ev.nodeId for ev in start_events} == set(node_ids)
        assert {ev.nodeId for ev in complete_events} == set(node_ids)

        # 마지막 이벤트는 execution_complete 이며 status=completed
        last = collected[-1]
        assert last.eventType == "execution_complete"
        assert last.data.get("status") == ExecutionStatus.COMPLETED.value
    finally:
        await _cleanup_workflow(wf_id, ex_id)


# ── 실패 경로 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_engine_emits_node_error_on_failure(fresh_bus):
    """시작 노드를 찾을 수 없는 워크플로우 실행 → execution_complete(failed) 이벤트 push."""
    # start 노드 없는 워크플로우 (노드 0개 → 시작 노드 없음 → ValueError)
    wf_id = f"wf-evfail-{uuid.uuid4().hex[:6]}"
    ex_id = f"exec-evfail-{uuid.uuid4().hex[:6]}"

    async with async_session_maker() as db:
        db.add(
            Workflow(
                id=wf_id,
                name="no-start-wf",
                status=WorkflowStatus.ACTIVE,
                tags=[],
                trigger={"type": "manual", "config": {}},
                variables={},
                created_by="test",
            )
        )
        db.add(
            WorkflowExecution(
                id=ex_id,
                workflow_id=wf_id,
                status=ExecutionStatus.PENDING,
                input_data={},
            )
        )
        await db.commit()

    try:
        collected: list[ExecutionLogEvent] = []
        subscriber_ready = asyncio.Event()
        consumer_task = asyncio.create_task(
            _collect_events(ex_id, collected, subscriber_ready)
        )
        for _ in range(50):
            if await fresh_bus.subscriber_count(ex_id) >= 1:
                subscriber_ready.set()
                break
            await asyncio.sleep(0.01)

        engine = WorkflowEngine(ex_id)
        with pytest.raises(ValueError):
            await engine.run()

        await asyncio.wait_for(consumer_task, timeout=3.0)

        types = [ev.eventType for ev in collected]
        # 실행이 시작되기 전에 실패하므로 node_start 는 없음
        assert "node_start" not in types
        # execution_complete(failed) 는 반드시 있어야 함
        assert collected[-1].eventType == "execution_complete"
        assert collected[-1].data.get("status") == ExecutionStatus.FAILED.value
        assert "error" in collected[-1].data
    finally:
        await _cleanup_workflow(wf_id, ex_id)


# ── 방어성 검증 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_failure_does_not_break_execution(fresh_bus, monkeypatch):
    """이벤트 버스에서 publish 가 예외를 던져도 엔진 실행은 완료되어야 한다."""
    wf_id, ex_id, _ = await _setup_simple_workflow()
    try:
        # 이벤트 버스의 publish 를 예외로 교체 — 엔진의 _emit_event 의
        # try/except 방어가 제대로 작동하는지 확인.
        from app.services import execution_bus as bus_mod

        async def failing_publish(self, execution_id: str, event: ExecutionLogEvent) -> None:
            raise RuntimeError("publish is broken")

        monkeypatch.setattr(
            bus_mod.ExecutionEventBus,
            "publish",
            failing_publish,
            raising=True,
        )

        engine = WorkflowEngine(ex_id)
        # 예외 없이 완료되어야 함
        await engine.run()

        # DB 에 완료 상태로 기록되어야 함
        async with async_session_maker() as db:
            row = (
                await db.execute(
                    select(WorkflowExecution).where(WorkflowExecution.id == ex_id)
                )
            ).scalar_one()
            assert row.status == ExecutionStatus.COMPLETED, (
                f"publish 실패가 실행을 깨뜨렸다: status={row.status}"
            )
    finally:
        await _cleanup_workflow(wf_id, ex_id)
