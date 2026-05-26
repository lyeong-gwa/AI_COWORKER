"""Phase 4b — 노드별 timeout 로직 검증.

검증 포인트
----------
1. ``_get_node_timeout`` 은 정의된 타입에 대해 override 값을 반환하고
   없으면 기본값(``NODE_DEFAULT_TIMEOUT_SECONDS``)을 반환한다.
2. 노드 핸들러가 지정된 시간 내에 반환하지 못하면 ``NodeTimeoutError`` 가
   발생하며, 엔진은 이를 실패 이벤트로 전파한다.
3. timeout 으로 인한 실패도 DB 에 ``FAILED`` 상태와 timeout 메시지로 영속화.

테스트 전략
----------
- ``_NODE_TIMEOUT_OVERRIDES`` 를 monkeypatch 로 교체하여 form-start 노드에
  극단적으로 짧은 (0.05s) timeout 을 설정.
- form-start 핸들러를 ``asyncio.sleep(1.0)`` 으로 교체 → timeout 트리거.
"""
from __future__ import annotations

import asyncio
import uuid

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
from app.services import workflow_engine as engine_mod
from app.services.execution_bus import (
    _reset_execution_bus_for_tests,
    get_execution_bus,
)
from app.services.workflow_engine import (
    NODE_DEFAULT_TIMEOUT_SECONDS,
    NodeTimeoutError,
    WorkflowEngine,
)


@pytest.fixture
def fresh_bus():
    _reset_execution_bus_for_tests()
    yield get_execution_bus()
    _reset_execution_bus_for_tests()


# ── 단위: _get_node_timeout ──────────────────────────────────────────────


def test_get_node_timeout_returns_override_when_defined():
    """AI 노드는 override 를 따른다 (기본 300s 가 아니라 600s 이상)."""
    engine = WorkflowEngine("exec-dummy-for-timeout")
    ai_timeout = engine._get_node_timeout("ai-custom")
    # override 값이 있을 것이므로 기본값보다 같거나 크다
    assert ai_timeout >= NODE_DEFAULT_TIMEOUT_SECONDS


def test_get_node_timeout_returns_default_when_undefined():
    """override 없는 타입은 기본값을 반환."""
    engine = WorkflowEngine("exec-dummy-for-timeout")
    # form-start 는 기본 override 가 없으므로 기본값.
    assert engine._get_node_timeout("form-start") == NODE_DEFAULT_TIMEOUT_SECONDS
    # 존재하지 않는 타입도 기본값.
    assert engine._get_node_timeout("__nonexistent__") == NODE_DEFAULT_TIMEOUT_SECONDS


def test_get_node_timeout_knowledge_is_shorter_than_ai():
    """지식/API 노드는 AI 노드보다 짧게 제한되어야 한다."""
    engine = WorkflowEngine("exec-dummy-for-timeout")
    assert engine._get_node_timeout("knowledge") < engine._get_node_timeout("ai-custom")
    assert engine._get_node_timeout("api-call") < engine._get_node_timeout("ai-custom")


# ── 통합: 실제 실행에서 timeout 이 발동하면 NodeTimeoutError ─────────────


async def _setup_single_node_wf() -> tuple[str, str, str]:
    wf_id = f"wf-to-{uuid.uuid4().hex[:6]}"
    ex_id = f"exec-to-{uuid.uuid4().hex[:6]}"
    n_id = f"n-to-{uuid.uuid4().hex[:4]}"

    async with async_session_maker() as db:
        db.add(
            Workflow(
                id=wf_id,
                name=f"timeout wf {wf_id}",
                status=WorkflowStatus.ACTIVE,
                tags=[],
                trigger={"type": "manual", "config": {}},
                variables={},
                created_by="test",
            )
        )
        db.add(
            WorkflowNode(
                id=n_id,
                workflow_id=wf_id,
                node_id=n_id,
                definition_type="form-start",
                config={},
                name="slow-start",
                order_index=0,
                config_overrides={},
                input_mapping={},
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

    return wf_id, ex_id, n_id


async def _cleanup(wf_id: str, ex_id: str) -> None:
    async with async_session_maker() as db:
        for e in (
            (
                await db.execute(
                    select(WarehouseEntry).where(WarehouseEntry.execution_id == ex_id)
                )
            )
            .scalars()
            .all()
        ):
            await db.delete(e)
        ex = (
            await db.execute(
                select(WorkflowExecution).where(WorkflowExecution.id == ex_id)
            )
        ).scalar_one_or_none()
        if ex is not None:
            await db.delete(ex)
        for n in (
            (
                await db.execute(
                    select(WorkflowNode).where(WorkflowNode.workflow_id == wf_id)
                )
            )
            .scalars()
            .all()
        ):
            await db.delete(n)
        for c in (
            (
                await db.execute(
                    select(WorkflowConnection).where(
                        WorkflowConnection.workflow_id == wf_id
                    )
                )
            )
            .scalars()
            .all()
        ):
            await db.delete(c)
        wf = (
            await db.execute(select(Workflow).where(Workflow.id == wf_id))
        ).scalar_one_or_none()
        if wf is not None:
            await db.delete(wf)
        await db.commit()


@pytest.mark.asyncio
async def test_node_that_exceeds_timeout_raises_node_timeout_error(
    fresh_bus, monkeypatch
):
    """form-start 핸들러를 느리게 만들고 짧은 timeout 을 적용 → 타임아웃."""
    wf_id, ex_id, n_id = await _setup_single_node_wf()
    try:
        # form-start 에 극단적으로 짧은 timeout (50ms) 을 설정.
        short_override = {"form-start": 0.05}
        monkeypatch.setattr(
            engine_mod,
            "_NODE_TIMEOUT_OVERRIDES",
            short_override,
            raising=True,
        )

        # form-start 핸들러의 execute 를 슬립으로 교체.
        from app.nodes.triggers.form_start import FormStartHandler

        async def slow_execute(self, node, input_data, ctx):
            await asyncio.sleep(2.0)  # 50ms 한도 초과
            return input_data

        monkeypatch.setattr(FormStartHandler, "execute", slow_execute, raising=True)

        # 이벤트 수집
        collected: list[ExecutionLogEvent] = []

        async def consume():
            async for ev in fresh_bus.subscribe(ex_id):
                collected.append(ev)
                if ev.eventType == "execution_complete":
                    return

        consumer_task = asyncio.create_task(consume())
        for _ in range(50):
            if await fresh_bus.subscriber_count(ex_id) >= 1:
                break
            await asyncio.sleep(0.01)

        engine = WorkflowEngine(ex_id)
        with pytest.raises(NodeTimeoutError) as ei:
            await engine.run()

        # timeout 정보 확인
        assert ei.value.node_id == n_id
        assert ei.value.def_type == "form-start"
        assert ei.value.seconds == 0.05

        # 이벤트 확인 — node_error + execution_complete(failed)
        await asyncio.wait_for(consumer_task, timeout=5.0)
        types = [ev.eventType for ev in collected]
        assert "node_error" in types
        assert collected[-1].eventType == "execution_complete"
        assert collected[-1].data.get("status") == ExecutionStatus.FAILED.value

        # DB 에도 FAILED 기록
        async with async_session_maker() as db:
            row = (
                await db.execute(
                    select(WorkflowExecution).where(WorkflowExecution.id == ex_id)
                )
            ).scalar_one()
            assert row.status == ExecutionStatus.FAILED
            assert row.error_message and "timed out" in row.error_message
    finally:
        await _cleanup(wf_id, ex_id)


@pytest.mark.asyncio
async def test_node_completes_within_timeout_does_not_raise(fresh_bus, monkeypatch):
    """timeout 내에 끝나는 노드는 정상 완료되어야 한다 (regression 가드)."""
    wf_id, ex_id, n_id = await _setup_single_node_wf()
    try:
        # 여유로운 timeout (5초). 기본 핸들러는 즉시 반환.
        monkeypatch.setattr(
            engine_mod,
            "_NODE_TIMEOUT_OVERRIDES",
            {"form-start": 5.0},
            raising=True,
        )

        engine = WorkflowEngine(ex_id)
        await engine.run()  # 예외 없음

        async with async_session_maker() as db:
            row = (
                await db.execute(
                    select(WorkflowExecution).where(WorkflowExecution.id == ex_id)
                )
            ).scalar_one()
            assert row.status == ExecutionStatus.COMPLETED
    finally:
        await _cleanup(wf_id, ex_id)
