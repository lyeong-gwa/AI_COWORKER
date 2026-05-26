"""
factory warehouse execution_id 필터 테스트.

검증 포인트:
1. execution_id 없이 조회 → 노드의 모든 항목 반환 (누적)
2. execution_id 로 조회 → 해당 실행분만 반환
3. 존재하지 않는 execution_id 로 조회 → entries=[], total=0
4. DELETE /warehouse/{node_id}?execution_id=... → 해당 실행분만 삭제, 다른 실행분 잔존
5. DELETE /warehouse/{node_id} (execution_id 없음) → 전체 삭제
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import async_session_maker
from app.models.workflow import WarehouseEntry

client = TestClient(app, raise_server_exceptions=False)


# ── DB 헬퍼 ────────────────────────────────────────────────────────────────


async def _insert_entry(node_id: str, execution_id: str, data: dict) -> str:
    """WarehouseEntry 직접 삽입 → 생성된 entry id 반환"""
    entry_id = f"wh-{uuid.uuid4().hex[:8]}"
    async with async_session_maker() as db:
        entry = WarehouseEntry(
            id=entry_id,
            node_instance_id=node_id,
            execution_id=execution_id,
            data=data,
        )
        db.add(entry)
        await db.commit()
    return entry_id


async def _delete_entries_by_node(node_id: str) -> None:
    """테스트 정리: 노드 전체 항목 삭제"""
    async with async_session_maker() as db:
        from sqlalchemy import select, delete
        await db.execute(
            delete(WarehouseEntry).where(WarehouseEntry.node_instance_id == node_id)
        )
        await db.commit()


def _node_id() -> str:
    return f"wh-node-{uuid.uuid4().hex[:8]}"


def _exec_id() -> str:
    return f"exec-{uuid.uuid4().hex[:8]}"


# ── 테스트 케이스 ──────────────────────────────────────────────────────────


def test_get_warehouse_no_filter_returns_all():
    """execution_id 필터 없이 조회 시 모든 항목 반환 (기존 누적 동작 유지)."""
    node_id = _node_id()
    exec_a = _exec_id()
    exec_b = _exec_id()
    try:
        asyncio.run(_insert_entry(node_id, exec_a, {"v": 1}))
        asyncio.run(_insert_entry(node_id, exec_a, {"v": 2}))
        asyncio.run(_insert_entry(node_id, exec_b, {"v": 3}))

        r = client.get(f"/api/v1/factory/warehouse/{node_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3
    finally:
        asyncio.run(_delete_entries_by_node(node_id))


def test_get_warehouse_with_execution_id_returns_filtered():
    """execution_id 필터 적용 시 해당 실행분만 반환."""
    node_id = _node_id()
    exec_a = _exec_id()
    exec_b = _exec_id()
    try:
        asyncio.run(_insert_entry(node_id, exec_a, {"v": 1}))
        asyncio.run(_insert_entry(node_id, exec_a, {"v": 2}))
        asyncio.run(_insert_entry(node_id, exec_b, {"v": 3}))

        r = client.get(f"/api/v1/factory/warehouse/{node_id}?execution_id={exec_a}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2
        for item in body["items"]:
            assert item["executionId"] == exec_a
    finally:
        asyncio.run(_delete_entries_by_node(node_id))


def test_get_warehouse_nonexistent_execution_id_returns_empty():
    """존재하지 않는 execution_id 로 조회 시 빈 결과 반환."""
    node_id = _node_id()
    exec_a = _exec_id()
    try:
        asyncio.run(_insert_entry(node_id, exec_a, {"v": 1}))

        r = client.get(f"/api/v1/factory/warehouse/{node_id}?execution_id=nonexistent-exec-id")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 0
        assert body["items"] == []
    finally:
        asyncio.run(_delete_entries_by_node(node_id))


def test_delete_warehouse_with_execution_id_removes_only_that_execution():
    """execution_id 지정 DELETE → 해당 실행분만 삭제, 나머지 잔존."""
    node_id = _node_id()
    exec_a = _exec_id()
    exec_b = _exec_id()
    try:
        asyncio.run(_insert_entry(node_id, exec_a, {"v": 1}))
        asyncio.run(_insert_entry(node_id, exec_a, {"v": 2}))
        asyncio.run(_insert_entry(node_id, exec_b, {"v": 3}))

        r = client.delete(f"/api/v1/factory/warehouse/{node_id}?execution_id={exec_a}")
        assert r.status_code == 204, r.text

        # exec_a 항목은 사라졌어야 함
        r2 = client.get(f"/api/v1/factory/warehouse/{node_id}?execution_id={exec_a}")
        assert r2.json()["total"] == 0

        # exec_b 항목은 남아있어야 함
        r3 = client.get(f"/api/v1/factory/warehouse/{node_id}?execution_id={exec_b}")
        assert r3.json()["total"] == 1
    finally:
        asyncio.run(_delete_entries_by_node(node_id))


def test_delete_warehouse_without_execution_id_removes_all():
    """execution_id 없이 DELETE → 노드 전체 항목 삭제."""
    node_id = _node_id()
    exec_a = _exec_id()
    exec_b = _exec_id()
    try:
        asyncio.run(_insert_entry(node_id, exec_a, {"v": 1}))
        asyncio.run(_insert_entry(node_id, exec_b, {"v": 2}))

        r = client.delete(f"/api/v1/factory/warehouse/{node_id}")
        assert r.status_code == 204, r.text

        r2 = client.get(f"/api/v1/factory/warehouse/{node_id}")
        assert r2.json()["total"] == 0
    finally:
        asyncio.run(_delete_entries_by_node(node_id))
