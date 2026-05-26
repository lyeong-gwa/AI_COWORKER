"""Phase 4a — ExecutionEventBus (in-memory pub/sub) 단위 테스트.

검증 포인트
----------
1. subscribe 후 publish 한 이벤트를 수신.
2. publish 전에 subscribe 하지 않으면 해당 이벤트는 drop (replay 없음).
3. unsubscribe(생성기 close) 후엔 구독자 수 감소 + 이후 publish 영향 없음.
4. 여러 구독자가 동시에 같은 execution_id 를 수신.
5. 구독자 큐가 가득 차면 drop-oldest 로 처리, 엔진은 블록되지 않음.
6. 존재하지 않는 execution_id 에 publish 하면 silent no-op.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from app.schemas.workflow import ExecutionLogEvent
from app.services.execution_bus import (
    ExecutionEventBus,
    _reset_execution_bus_for_tests,
    get_execution_bus,
)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────

def _make_event(event_type: str, node_id: str | None = None) -> ExecutionLogEvent:
    return ExecutionLogEvent(
        eventType=event_type,
        timestamp=datetime.utcnow(),
        nodeId=node_id,
        data={},
    )


@pytest.fixture
def fresh_bus():
    """각 테스트마다 싱글톤을 리셋하여 상태 누수 방지."""
    _reset_execution_bus_for_tests()
    bus = get_execution_bus()
    yield bus
    _reset_execution_bus_for_tests()


# ── 테스트 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_subscriber_receives_event_after_subscription(fresh_bus: ExecutionEventBus):
    """subscribe 후 publish 한 이벤트는 반드시 수신된다."""
    execution_id = "exec-bus-1"
    received: list[ExecutionLogEvent] = []

    async def consume():
        async for event in fresh_bus.subscribe(execution_id):
            received.append(event)
            if event.eventType == "execution_complete":
                break

    consumer_task = asyncio.create_task(consume())
    # 구독 등록이 완료될 때까지 살짝 대기
    for _ in range(20):
        if await fresh_bus.subscriber_count(execution_id) >= 1:
            break
        await asyncio.sleep(0.01)

    await fresh_bus.publish(execution_id, _make_event("node_start", "n1"))
    await fresh_bus.publish(execution_id, _make_event("node_complete", "n1"))
    await fresh_bus.publish(execution_id, _make_event("execution_complete"))

    await asyncio.wait_for(consumer_task, timeout=2.0)

    types = [ev.eventType for ev in received]
    assert types == ["node_start", "node_complete", "execution_complete"]


@pytest.mark.asyncio
async def test_publish_before_subscribe_is_not_replayed(fresh_bus: ExecutionEventBus):
    """publish → subscribe 순서일 때 과거 이벤트는 전달되지 않는다 (설계 의도)."""
    execution_id = "exec-bus-2"

    # 먼저 publish — 구독자 없음 → drop
    await fresh_bus.publish(execution_id, _make_event("node_start", "n1"))

    received: list[ExecutionLogEvent] = []

    async def consume():
        async for event in fresh_bus.subscribe(execution_id):
            received.append(event)
            if event.eventType == "execution_complete":
                break

    consumer_task = asyncio.create_task(consume())
    for _ in range(20):
        if await fresh_bus.subscriber_count(execution_id) >= 1:
            break
        await asyncio.sleep(0.01)

    await fresh_bus.publish(execution_id, _make_event("execution_complete"))
    await asyncio.wait_for(consumer_task, timeout=2.0)

    types = [ev.eventType for ev in received]
    # 이전에 publish 된 node_start 는 나타나지 않아야 한다
    assert "node_start" not in types
    assert types == ["execution_complete"]


@pytest.mark.asyncio
async def test_unsubscribe_after_generator_close(fresh_bus: ExecutionEventBus):
    """generator 를 종료하면 구독이 해제되고 subscriber_count 가 0 으로."""
    execution_id = "exec-bus-3"

    async def consume():
        async for event in fresh_bus.subscribe(execution_id):
            # 첫 이벤트만 소비하고 break → finally 블록에서 unsubscribe
            break

    consumer_task = asyncio.create_task(consume())
    for _ in range(20):
        if await fresh_bus.subscriber_count(execution_id) >= 1:
            break
        await asyncio.sleep(0.01)

    await fresh_bus.publish(execution_id, _make_event("node_start"))
    await asyncio.wait_for(consumer_task, timeout=2.0)

    # 구독자가 모두 해제되어 count 0
    assert await fresh_bus.subscriber_count(execution_id) == 0

    # 이후 publish 는 no-op (예외 없이 조용히 drop)
    await fresh_bus.publish(execution_id, _make_event("node_complete"))


@pytest.mark.asyncio
async def test_multiple_subscribers_receive_same_event(fresh_bus: ExecutionEventBus):
    """동일 execution_id 에 복수 구독자가 붙어 있으면 모두 이벤트를 수신."""
    execution_id = "exec-bus-4"
    received_a: list[ExecutionLogEvent] = []
    received_b: list[ExecutionLogEvent] = []

    async def consume(sink: list):
        async for event in fresh_bus.subscribe(execution_id):
            sink.append(event)
            if event.eventType == "execution_complete":
                break

    task_a = asyncio.create_task(consume(received_a))
    task_b = asyncio.create_task(consume(received_b))
    for _ in range(20):
        if await fresh_bus.subscriber_count(execution_id) >= 2:
            break
        await asyncio.sleep(0.01)

    await fresh_bus.publish(execution_id, _make_event("node_start", "n1"))
    await fresh_bus.publish(execution_id, _make_event("execution_complete"))

    await asyncio.wait_for(task_a, timeout=2.0)
    await asyncio.wait_for(task_b, timeout=2.0)

    assert [e.eventType for e in received_a] == ["node_start", "execution_complete"]
    assert [e.eventType for e in received_b] == ["node_start", "execution_complete"]


@pytest.mark.asyncio
async def test_publish_never_raises_even_without_subscribers(fresh_bus: ExecutionEventBus):
    """구독자가 없는 execution_id 에 대한 publish 는 조용히 성공해야 한다."""
    # 예외가 발생하지 않아야 성공
    await fresh_bus.publish("exec-nobody", _make_event("node_start", "n1"))
    await fresh_bus.publish("exec-nobody", _make_event("execution_complete"))
    # count 도 0 유지
    assert await fresh_bus.subscriber_count("exec-nobody") == 0


@pytest.mark.asyncio
async def test_drop_oldest_when_queue_full(monkeypatch):
    """큐가 가득 찼을 때 drop-oldest 로 처리되어 publish 는 블록되지 않는다."""
    # 작은 max 사이즈의 버스를 만들기 위해 내부 상수를 우회.
    # 설계상 직접 수정 API 는 없으므로 private 경로로 한정된 테스트.
    _reset_execution_bus_for_tests()

    from app.services import execution_bus as bus_mod
    monkeypatch.setattr(bus_mod, "_QUEUE_MAXSIZE", 2, raising=True)

    bus = bus_mod.ExecutionEventBus()
    execution_id = "exec-bus-full"

    # 구독자를 수동으로 붙이되, 큐에서 꺼내지 않도록 의도적으로 방치.
    # subscribe() 의 async generator 의 내부 큐가 maxsize=2 로 생성된다.
    gen = bus.subscribe(execution_id)
    # async generator 초기화 (anext 1회 태스크)
    first_task = asyncio.create_task(gen.__anext__())
    for _ in range(20):
        if await bus.subscriber_count(execution_id) >= 1:
            break
        await asyncio.sleep(0.01)

    # 3개 연속 publish — 2개 초과분은 drop-oldest.
    # 첫 put 은 first_task 가 즉시 소비하므로 큐는 비어짐.
    await bus.publish(execution_id, _make_event("node_start", "n1"))
    # first_task 수신
    first = await asyncio.wait_for(first_task, timeout=1.0)
    assert first.nodeId == "n1"

    # 이후는 큐에 쌓임 (소비자 없음)
    await bus.publish(execution_id, _make_event("node_start", "n2"))
    await bus.publish(execution_id, _make_event("node_start", "n3"))
    # 여기서 publish 는 큐가 가득 차서 drop-oldest → n2 제거, n4 삽입
    await bus.publish(execution_id, _make_event("node_start", "n4"))

    # 구독자 큐의 다음 2개를 꺼내 확인 — 최신 2개만 남아있어야 함
    next_task_1 = asyncio.create_task(gen.__anext__())
    got1 = await asyncio.wait_for(next_task_1, timeout=1.0)

    next_task_2 = asyncio.create_task(gen.__anext__())
    got2 = await asyncio.wait_for(next_task_2, timeout=1.0)

    # drop-oldest 정책: n2 가 버려지고 n3, n4 가 남음
    assert got1.nodeId == "n3"
    assert got2.nodeId == "n4"

    # 정리: generator close
    await gen.aclose()
