"""인스턴스DB 적재 노드 핸들러 — 파일시스템 재설계 후 시나리오 검증.

핸들러를 직접(InstanceDBInsertHandler.execute) 호출해 검증한다. workflow_engine
의존성을 우회하여 핸들러 단위 동작을 격리 테스트한다.

검증 케이스:
1. input 모드 + 정상 데이터 → record 1건 적재
2. warehouse 모드 + 유효한 warehouseEntryId → record 1건 + _source.warehouseId 채워짐
3. auto 모드 + 입력에 warehouseEntryId 있음 → warehouse 모드 동작
4. auto 모드 + warehouseEntryId 없음 → input 모드 동작
5. instanceDbId 누락 → ValueError
6. 존재하지 않는 instanceDbId → ValueError
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from app.core.database import async_session_maker
from app.models.workflow import WarehouseEntry
from app.nodes.base import ExecutionContext
from app.nodes.registry import NodeHandlerRegistry
from app.services.instance_db_store import get_instance_db_store
from app.services.tool_executor import render_template


# ── 헬퍼 ──────────────────────────────────────────────────────────────────


def _make_node(
    config: Dict[str, Any],
    workflow_id: str = "wf-test",
) -> SimpleNamespace:
    """핸들러가 보는 WorkflowNode 의 최소 attribute(SimpleNamespace) 생성."""
    return SimpleNamespace(
        id=f"n-{uuid.uuid4().hex[:6]}",
        workflow_id=workflow_id,
        config=config,
        definition_type="instance-db-insert",
    )


def _get_nested_value(data: Dict, path: str) -> Any:
    keys = path.split(".")
    value: Any = data
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            return None
    return value


async def _run_handler(node, input_data: Dict[str, Any], execution_id: str):
    """동일 세션에서 핸들러를 실행하고 ctx.db 를 commit 한 후 결과 반환."""
    handler = NodeHandlerRegistry.get("instance-db-insert")
    async with async_session_maker() as db:
        ctx = ExecutionContext(
            db=db,
            execution_id=execution_id,
            node_id=node.id,
            get_nested_value=_get_nested_value,
            render_template=render_template,
        )
        result = await handler.execute(node, input_data, ctx)
        await db.commit()
        return result


async def _create_idb() -> str:
    """테스트용 InstanceDB 폴더 1건 생성 후 id 반환."""
    store = get_instance_db_store()
    meta = await store.create_meta(
        name=f"테스트 IDB {uuid.uuid4().hex[:6]}",
        description="test_instance_db_insert_handler",
        tags=["test"],
    )
    return meta["id"]


async def _create_warehouse_entry(data: Dict[str, Any]) -> str:
    """테스트용 WarehouseEntry 1건 생성."""
    we_id = f"wh-{uuid.uuid4().hex[:8]}"
    async with async_session_maker() as db:
        we = WarehouseEntry(
            id=we_id,
            node_instance_id=f"n-up-{uuid.uuid4().hex[:4]}",
            execution_id=f"exec-test-{uuid.uuid4().hex[:6]}",
            data=data,
            dedup_key=None,
        )
        db.add(we)
        await db.commit()
    return we_id


async def _count_records(idb_id: str) -> int:
    store = get_instance_db_store()
    _items, total = await store.list_records(idb_id, limit=10**9, offset=0)
    return total


async def _fetch_record(idb_id: str, record_id: str) -> Dict[str, Any]:
    store = get_instance_db_store()
    rec = await store.get_record(idb_id, record_id)
    assert rec is not None, f"record not found: {record_id}"
    return rec


# ── 1. input 모드 + 정상 데이터 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_input_mode_inserts_record():
    idb_id = await _create_idb()
    node = _make_node(
        {
            "instanceDbId": idb_id,
            "sourceMode": "input",
            "dataTemplate": {
                "boardId": "{{boardId}}",
                "title": "{{title}}",
            },
        }
    )
    input_data = {"boardId": 42, "title": "테스트 제목"}

    ex_id = f"exec-it1-{uuid.uuid4().hex[:6]}"
    result = await _run_handler(node, input_data, ex_id)

    assert result["instanceDbId"] == idb_id
    assert isinstance(result["recordId"], str) and result["recordId"].startswith("rec-")

    assert await _count_records(idb_id) == 1
    rec = await _fetch_record(idb_id, result["recordId"])
    assert rec["data"].get("boardId") == 42
    assert isinstance(rec["data"].get("boardId"), int)
    assert rec["data"].get("title") == "테스트 제목"
    assert rec["_source"]["workflowId"] == "wf-test"
    assert rec["_source"]["executionId"] == ex_id
    assert rec["_source"]["warehouseId"] is None


# ── 2. warehouse 모드 + 유효한 warehouseEntryId ────────────────────────────


@pytest.mark.asyncio
async def test_warehouse_mode_uses_warehouse_entry_data():
    idb_id = await _create_idb()
    we_id = await _create_warehouse_entry({"boardId": 100, "title": "from-wh"})

    node = _make_node(
        {
            "instanceDbId": idb_id,
            "sourceMode": "warehouse",
        }
    )
    ex_id = f"exec-it2-{uuid.uuid4().hex[:6]}"
    result = await _run_handler(node, {"warehouseEntryId": we_id}, ex_id)

    rec = await _fetch_record(idb_id, result["recordId"])
    assert rec["data"].get("boardId") == 100
    assert rec["data"].get("title") == "from-wh"
    assert rec["_source"]["warehouseId"] == we_id
    assert rec["_source"]["workflowId"] == "wf-test"
    assert rec["_source"]["executionId"] == ex_id


# ── 3. auto 모드 + warehouseEntryId 있음 → warehouse 모드 ──────────────────


@pytest.mark.asyncio
async def test_auto_mode_with_warehouse_entry_id_uses_warehouse_mode():
    idb_id = await _create_idb()
    we_id = await _create_warehouse_entry({"boardId": 200, "title": "auto-wh"})

    node = _make_node(
        {
            "instanceDbId": idb_id,
            "sourceMode": "auto",
        }
    )
    ex_id = f"exec-it3-{uuid.uuid4().hex[:6]}"
    result = await _run_handler(
        node,
        {"warehouseEntryId": we_id, "boardId": 999, "title": "ignored"},
        ex_id,
    )
    rec = await _fetch_record(idb_id, result["recordId"])
    # warehouse 데이터(200) 가 사용되어야 함 (입력 boardId=999 가 아님)
    assert rec["data"].get("boardId") == 200
    assert rec["_source"]["warehouseId"] == we_id


# ── 4. auto 모드 + warehouseEntryId 없음 → input 모드 ──────────────────────


@pytest.mark.asyncio
async def test_auto_mode_without_warehouse_entry_id_falls_back_to_input():
    idb_id = await _create_idb()
    node = _make_node(
        {
            "instanceDbId": idb_id,
            "sourceMode": "auto",
            # dataTemplate 없음 → 입력 dict 자체가 record
        }
    )
    ex_id = f"exec-it4-{uuid.uuid4().hex[:6]}"
    result = await _run_handler(node, {"boardId": 7, "title": "auto-input"}, ex_id)

    rec = await _fetch_record(idb_id, result["recordId"])
    assert rec["data"].get("boardId") == 7
    assert rec["data"].get("title") == "auto-input"
    assert rec["_source"]["warehouseId"] is None


# ── 5. instanceDbId 누락 → ValueError ─────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_instance_db_id_raises():
    node = _make_node({"sourceMode": "auto"})
    with pytest.raises(ValueError) as excinfo:
        await _run_handler(node, {"a": 1}, f"exec-{uuid.uuid4().hex[:6]}")
    assert "instancedbid" in str(excinfo.value).lower()


# ── 6. 존재하지 않는 instanceDbId → ValueError ────────────────────────────


@pytest.mark.asyncio
async def test_unknown_instance_db_id_raises():
    node = _make_node(
        {
            "instanceDbId": f"idb-nonexist-{uuid.uuid4().hex[:6]}",
            "sourceMode": "input",
        }
    )
    with pytest.raises(ValueError) as excinfo:
        await _run_handler(
            node, {"boardId": 1, "title": "x"}, f"exec-{uuid.uuid4().hex[:6]}"
        )
    assert "instancedb not found" in str(excinfo.value).lower()
