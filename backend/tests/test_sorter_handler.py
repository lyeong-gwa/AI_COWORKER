"""분류기 노드 핸들러 — 파일시스템 재설계 후 instance-db rule 검증.

instance-db rule 의 lookupKeyTemplate(dedup_key 기반) 은 폐기되었고
filterTemplate(record.data 동등 비교) 로 대체되었다. 본 테스트는
- 기존 input rule 의 회귀 방지
- 새 filterTemplate 기반 분기
- 혼합 rules 정의 순서
- instanceDbId 자체가 없는 경우의 not_exists 매칭
을 검증한다.

검증 케이스:
1. dataSource='instance-db' + condition='exists' + record 있음 → 해당 handle 분기
2. dataSource='instance-db' + condition='not_exists' + record 없음 → 해당 handle 분기
3. 혼합 rules (input rule + instance-db rule) — 정의 순서대로 평가됨
4. instanceDbId 자체가 존재하지 않는 ID + condition='not_exists' → 매칭
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from app.core.constants import BeltKey
from app.core.database import async_session_maker
from app.nodes.base import ExecutionContext
from app.nodes.registry import NodeHandlerRegistry
from app.services.instance_db_store import get_instance_db_store
from app.services.tool_executor import render_template


# ── 헬퍼 ──────────────────────────────────────────────────────────────────


def _make_node(config: Dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"n-{uuid.uuid4().hex[:6]}",
        workflow_id="wf-test",
        config=config,
        definition_type="sorter",
    )


def _get_nested_value(data: Dict, path: str) -> Any:
    if not path:
        return None
    keys = path.split(".")
    value: Any = data
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            return None
    return value


async def _run_sorter(node, input_data: Dict[str, Any], execution_id: str):
    handler = NodeHandlerRegistry.get("sorter")
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
    store = get_instance_db_store()
    meta = await store.create_meta(
        name=f"sorter-test-idb {uuid.uuid4().hex[:6]}",
        description="test_sorter_handler",
        tags=["sorter-test"],
    )
    return meta["id"]


async def _seed_record(idb_id: str, data: Dict[str, Any]) -> None:
    store = get_instance_db_store()
    await store.insert_record(
        idb_id,
        data=data,
        source={
            "workflowId": "wf-seed",
            "executionId": f"exec-seed-{uuid.uuid4().hex[:6]}",
            "warehouseId": None,
        },
    )


# ── 1. instance-db rule + exists 매칭 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_instance_db_rule_exists_matches_when_record_present():
    idb_id = await _create_idb()
    await _seed_record(idb_id, {"boardId": 42, "title": "이미 답변"})

    node = _make_node(
        {
            "rules": [
                {
                    "id": "already-answered",
                    "dataSource": "instance-db",
                    "instanceDbId": idb_id,
                    "filterTemplate": {"boardId": "{{boardId}}"},
                    "condition": "exists",
                },
            ],
        }
    )
    result = await _run_sorter(node, {"boardId": 42}, f"exec-{uuid.uuid4().hex[:6]}")
    assert result[BeltKey.SORTER_HANDLE] == "rule-already-answered", result


# ── 2. instance-db rule + not_exists + 빈 idb ─────────────────────────────


@pytest.mark.asyncio
async def test_instance_db_rule_not_exists_matches_when_record_absent():
    idb_id = await _create_idb()
    # 시드하지 않음 — record 없음

    node = _make_node(
        {
            "rules": [
                {
                    "id": "fresh",
                    "dataSource": "instance-db",
                    "instanceDbId": idb_id,
                    "filterTemplate": {"boardId": "{{boardId}}"},
                    "condition": "not_exists",
                },
            ],
        }
    )
    result = await _run_sorter(node, {"boardId": 999}, f"exec-{uuid.uuid4().hex[:6]}")
    assert result[BeltKey.SORTER_HANDLE] == "rule-fresh", result


# ── 3. 혼합 rules (input + instance-db) — 정의 순서대로 평가 ────────────


@pytest.mark.asyncio
async def test_mixed_rules_evaluated_in_declaration_order():
    """input rule 과 instance-db rule 이 섞여 있을 때 rules 정의 순서가 우선.

    sorter 의 기존 규약: 매칭된 첫 rule 의 handle 로 분기. dataSource 종류와 무관.
    """
    idb_id = await _create_idb()
    await _seed_record(idb_id, {"boardId": 7})

    # 케이스 A: input rule 이 먼저 → input rule 이 이김
    node_a = _make_node(
        {
            "rules": [
                {
                    "id": "input-first",
                    "field": "category",
                    "operator": "equals",
                    "value": "infra",
                },
                {
                    "id": "idb-second",
                    "dataSource": "instance-db",
                    "instanceDbId": idb_id,
                    "filterTemplate": {"boardId": "{{boardId}}"},
                    "condition": "exists",
                },
            ],
        }
    )
    result_a = await _run_sorter(
        node_a,
        {"boardId": 7, "category": "infra"},
        f"exec-{uuid.uuid4().hex[:6]}",
    )
    assert result_a[BeltKey.SORTER_HANDLE] == "rule-input-first", result_a

    # 케이스 B: input 매칭 안되면 instance-db rule 로 fall-through
    result_b = await _run_sorter(
        node_a,
        {"boardId": 7, "category": "other"},
        f"exec-{uuid.uuid4().hex[:6]}",
    )
    assert result_b[BeltKey.SORTER_HANDLE] == "rule-idb-second", result_b

    # 케이스 C: 순서 뒤집기 — instance-db 먼저 → instance-db 가 이김
    node_c = _make_node(
        {
            "rules": [
                {
                    "id": "idb-first",
                    "dataSource": "instance-db",
                    "instanceDbId": idb_id,
                    "filterTemplate": {"boardId": "{{boardId}}"},
                    "condition": "exists",
                },
                {
                    "id": "input-second",
                    "field": "category",
                    "operator": "equals",
                    "value": "infra",
                },
            ],
        }
    )
    result_c = await _run_sorter(
        node_c,
        {"boardId": 7, "category": "infra"},
        f"exec-{uuid.uuid4().hex[:6]}",
    )
    assert result_c[BeltKey.SORTER_HANDLE] == "rule-idb-first", result_c


# ── 4. instanceDbId 가 존재하지 않는 ID + condition='not_exists' ─────────


@pytest.mark.asyncio
async def test_instance_db_rule_missing_idb_matches_not_exists():
    """instanceDbId 자체가 존재하지 않으면 record 도 없으므로 not_exists 가 매칭."""
    node = _make_node(
        {
            "rules": [
                {
                    "id": "fresh-when-missing",
                    "dataSource": "instance-db",
                    "instanceDbId": f"idb-does-not-exist-{uuid.uuid4().hex[:6]}",
                    "filterTemplate": {"boardId": "{{boardId}}"},
                    "condition": "not_exists",
                },
            ],
        }
    )
    result = await _run_sorter(node, {"boardId": 1234}, f"exec-{uuid.uuid4().hex[:6]}")
    assert result[BeltKey.SORTER_HANDLE] == "rule-fresh-when-missing", result
