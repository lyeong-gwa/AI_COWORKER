"""실행 이벤트 버스 (in-memory pub/sub) — Phase 4a 신설.

엔진이 노드 실행 상태를 push 하고, SSE 엔드포인트(또는 기타 구독자)가 subscribe 하는
단순한 비동기 pub/sub 매커니즘. 프로세스 내부에서만 동작하며, 멀티 프로세스
확장이 필요해지면 Redis pub/sub 또는 NATS 로 투명하게 교체 가능하도록 설계.

핵심 설계 원칙
----------------
1. **Replay 없음** — subscribe 시점 이후 이벤트만 전달. 과거 상태는 DB 의
   ``WorkflowExecution.node_results`` 에서 스냅샷으로 조회.
2. **Drop-oldest 버퍼링** — 구독자 큐가 가득 차면 가장 오래된 이벤트부터 drop.
   실행 로직이 SSE 지연 때문에 블록되지 않도록 보장.
3. **Publish 실패 격리** — publish 는 ``asyncio.Queue.put_nowait`` 만 호출하므로
   구독자가 없거나 큐 예외가 발생해도 엔진 흐름에 영향이 없다. 엔진은
   ``asyncio.create_task(bus.publish(...))`` 로 fire-and-forget 호출할 수도 있고,
   ``await bus.publish(...)`` 로 직접 호출해도 된다 (publish 자체는 non-blocking).
4. **멀티 구독자** — 하나의 execution_id 에 대해 여러 SSE 클라이언트가 동시에
   구독할 수 있다 (현재 UX 는 1대1이지만, 탭 복제 등을 고려).

주의
----
이 버스는 **in-memory 싱글톤**이다. FastAPI 워커가 여러 프로세스로 분리되면
(예: gunicorn with multiple workers) 이벤트가 크로스하지 않는다. 토이 단계에서
uvicorn 싱글 워커 기준 설계. 프로덕션 분산 환경은 별도 작업으로 전환.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import AsyncIterator, Dict, Set

from ..schemas.workflow import ExecutionLogEvent


# 단일 구독자 큐의 최대 버퍼 크기. 256 개 이상 밀리면 drop-oldest 로 뒤처진
# 이벤트부터 버린다. 워크플로우 하나의 노드 수가 100을 초과하기 어려우므로
# 256은 충분히 여유있는 값.
_QUEUE_MAXSIZE = 256


class ExecutionEventBus:
    """노드 실행 이벤트용 비동기 pub/sub 버스."""

    def __init__(self) -> None:
        # execution_id → 구독자 큐 세트. 구독자가 여러 명일 수 있으므로 set.
        self._subscribers: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def publish(self, execution_id: str, event: ExecutionLogEvent) -> None:
        """엔진이 호출. 모든 구독자에게 이벤트 전달 (non-blocking).

        구독자가 없으면 조용히 drop. 큐가 가득 차면 오래된 이벤트를 버리고
        새 이벤트를 put. 이 메서드는 절대 예외를 전파하지 않는다 (엔진 흐름
        보호 목적).
        """
        async with self._lock:
            queues = list(self._subscribers.get(execution_id, ()))

        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # drop-oldest: 가장 오래된 항목 제거 후 재시도
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    # 정상 상황에서는 도달하지 않음. 방어적 로깅.
                    import logging
                    logging.getLogger(__name__).warning(
                        "execution_bus: publish drop 실패 execution_id=%s event=%s",
                        execution_id, event.eventType,
                    )
            except Exception:
                # 어떤 경우에도 publish 는 엔진을 멈추면 안 된다.
                import logging
                logging.getLogger(__name__).warning(
                    "execution_bus: publish 예외 무시 execution_id=%s", execution_id,
                    exc_info=True,
                )

    async def subscribe(
        self, execution_id: str
    ) -> AsyncIterator[ExecutionLogEvent]:
        """SSE 엔드포인트가 호출. 이벤트를 async generator 로 수신.

        종료 조건은 호출자가 판단 (예: ``execution_complete`` 수신 시 break).
        호출자가 ``anext`` 를 더 이상 호출하지 않으면 finalizer 가
        구독 해제를 수행한다 (async generator 의 ``.aclose()``).
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        async with self._lock:
            self._subscribers[execution_id].add(q)
        try:
            while True:
                event = await q.get()
                yield event
        finally:
            async with self._lock:
                subs = self._subscribers.get(execution_id)
                if subs is not None:
                    subs.discard(q)
                    if not subs:
                        self._subscribers.pop(execution_id, None)

    async def subscriber_count(self, execution_id: str) -> int:
        """테스트/디버그용: 특정 execution_id 에 대한 현재 구독자 수."""
        async with self._lock:
            return len(self._subscribers.get(execution_id, ()))

    async def reset(self) -> None:
        """테스트 전용: 전 구독자 제거. 프로덕션 코드에서 호출하지 말 것."""
        async with self._lock:
            self._subscribers.clear()


# ── 싱글톤 ─────────────────────────────────────────────────────────────────

_bus_instance: ExecutionEventBus | None = None


def get_execution_bus() -> ExecutionEventBus:
    """프로세스 전역 이벤트 버스 싱글톤을 반환."""
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = ExecutionEventBus()
    return _bus_instance


def _reset_execution_bus_for_tests() -> None:
    """테스트 격리용: 싱글톤 인스턴스를 완전히 재생성.

    ``pytest`` fixture 에서 호출하여 테스트 간 구독자/상태 누수를 방지.
    """
    global _bus_instance
    _bus_instance = None
