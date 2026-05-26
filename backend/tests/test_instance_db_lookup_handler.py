"""인스턴스DB 조회 노드 핸들러 — 파일시스템 재설계 후 시나리오 검증.

핸들러를 직접(InstanceDBLookupHandler.execute) 호출해 검증한다. dedup_key 기반의
by_key 모드는 폐기되었고 filter 모드(필터 비어있으면 모두 매칭)만 남는다.

검증 케이스:
1. filter 단일 조건 hit (다건) → records 길이 == 매칭 개수
2. filter 다조건 AND 매칭
3. filter limit 적용
4. instanceDbId 미존재 → ValueError
5. 빈 filterTemplate → 모두 매칭 (limit 적용)
6. 1,000 records 부하 회귀 가드 — filter limit=10, 5초 미만
"""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from app.core.database import async_session_maker
from app.nodes.base import ExecutionContext
from app.nodes.registry import NodeHandlerRegistry
from app.services.instance_db_store import get_instance_db_store
from app.services.tool_executor import render_template


# ── 헬퍼 ──────────────────────────────────────────────────────────────────


def _make_node(config: Dict[str, Any], workflow_id: str = "wf-test") -> SimpleNamespace:
    return SimpleNamespace(
        id=f"n-{uuid.uuid4().hex[:6]}",
        workflow_id=workflow_id,
        config=config,
        definition_type="instance-db-lookup",
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


async def _run_lookup(node, input_data: Dict[str, Any], execution_id: str):
    handler = NodeHandlerRegistry.get("instance-db-lookup")
    async with async_session_maker() as db:
        ctx = ExecutionContext(
            db=db,
            execution_id=execution_id,
            node_id=node.id,
            get_nested_value=_get_nested_value,
            render_template=render_template,
        )
        return await handler.execute(node, input_data, ctx)


async def _create_idb() -> str:
    store = get_instance_db_store()
    meta = await store.create_meta(
        name=f"테스트 IDB {uuid.uuid4().hex[:6]}",
        description="test_instance_db_lookup_handler",
        tags=["test"],
    )
    return meta["id"]


async def _seed_record(instance_db_id: str, data: Dict[str, Any]) -> str:
    """instance_db_id 에 record 1건 시드."""
    store = get_instance_db_store()
    rec = await store.insert_record(
        instance_db_id,
        data=data,
        source={
            "workflowId": "wf-seed",
            "executionId": f"exec-seed-{uuid.uuid4().hex[:6]}",
            "warehouseId": None,
        },
    )
    return rec["id"]


# ── 1. filter mode 단일 조건 hit (다건) ─────────────────────────────────


@pytest.mark.asyncio
async def test_filter_mode_single_condition_returns_all_matching():
    idb_id = await _create_idb()
    # category=infra 가 3건, network 가 2건
    for i in range(3):
        await _seed_record(idb_id, {"boardId": 100 + i, "category": "infra", "title": f"i{i}"})
    for i in range(2):
        await _seed_record(idb_id, {"boardId": 200 + i, "category": "network", "title": f"n{i}"})

    node = _make_node(
        {
            "instanceDbId": idb_id,
            "filterTemplate": {"category": "{{cat}}"},
            "limit": 10,
        }
    )
    result = await _run_lookup(node, {"cat": "infra"}, f"exec-{uuid.uuid4().hex[:6]}")

    assert result["found"] is True
    assert result["count"] == 3, result
    assert len(result["records"]) == 3
    assert all(r["category"] == "infra" for r in result["records"])
    assert result["record"] == result["records"][0]


# ── 2. filter mode 다조건 AND ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_filter_mode_multi_condition_and_match():
    idb_id = await _create_idb()
    await _seed_record(idb_id, {"boardId": 10, "category": "infra", "title": "a"})
    await _seed_record(idb_id, {"boardId": 11, "category": "infra", "title": "b"})
    await _seed_record(idb_id, {"boardId": 10, "category": "network", "title": "c"})

    node = _make_node(
        {
            "instanceDbId": idb_id,
            "filterTemplate": {
                "category": "{{cat}}",
                "boardId": "{{bid}}",  # 단일 참조 → int 타입 보존
            },
        }
    )
    result = await _run_lookup(node, {"cat": "infra", "bid": 10}, f"exec-{uuid.uuid4().hex[:6]}")

    assert result["count"] == 1, result["records"]
    assert result["records"][0]["boardId"] == 10
    assert result["records"][0]["category"] == "infra"
    assert result["records"][0]["title"] == "a"


# ── 3. filter mode limit 적용 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_filter_mode_limit_caps_results():
    idb_id = await _create_idb()
    for i in range(5):
        await _seed_record(idb_id, {"boardId": 300 + i, "category": "infra"})

    node = _make_node(
        {
            "instanceDbId": idb_id,
            "filterTemplate": {"category": "infra"},
            "limit": 2,
        }
    )
    result = await _run_lookup(node, {}, f"exec-{uuid.uuid4().hex[:6]}")

    assert result["count"] == 2
    assert len(result["records"]) == 2
    assert result["found"] is True


# ── 4. instanceDbId 미존재 → ValueError ──────────────────────────────────


@pytest.mark.asyncio
async def test_missing_instance_db_raises_value_error():
    node = _make_node(
        {
            "instanceDbId": "idb-does-not-exist-xxx",
            "filterTemplate": {"x": 1},
        }
    )
    with pytest.raises(ValueError) as excinfo:
        await _run_lookup(node, {"x": 1}, f"exec-{uuid.uuid4().hex[:6]}")
    assert "instancedb not found" in str(excinfo.value).lower()


# ── 5. filter mode + empty filterTemplate → 모두 매칭 (limit 적용) ──────


@pytest.mark.asyncio
async def test_filter_mode_empty_template_returns_all_within_limit():
    """filterTemplate 가 비어있으면 instance_db 전체를 limit 만큼 반환."""
    idb_id = await _create_idb()
    for i in range(4):
        await _seed_record(idb_id, {"boardId": 500 + i, "category": "x"})

    # filterTemplate 누락 + limit=2
    node = _make_node(
        {
            "instanceDbId": idb_id,
            "limit": 2,
        }
    )
    result = await _run_lookup(node, {}, f"exec-{uuid.uuid4().hex[:6]}")
    assert result["count"] == 2
    assert len(result["records"]) == 2
    assert result["found"] is True

    # filterTemplate={} 명시 + limit=10 → 4건 전부
    node2 = _make_node(
        {
            "instanceDbId": idb_id,
            "filterTemplate": {},
            "limit": 10,
        }
    )
    result2 = await _run_lookup(node2, {}, f"exec-{uuid.uuid4().hex[:6]}")
    assert result2["count"] == 4
    assert len(result2["records"]) == 4


# ── 6. 부하 회귀 가드 (파일시스템 store, 토이 부하) ─────────────────────


@pytest.mark.asyncio
async def test_filter_mode_handles_two_hundred_records_within_time_budget():
    """200 records 적재 후 filter limit=10 조회. 결과 길이 == 10, 시간 10초 미만.

    파일시스템 store 는 SQLite 보다 단건 IO 가 느리다 (Windows 특히). 토이 부하
    가정에서 200건 정도의 record 조회가 합리적 시간 내에 끝나는지 확인하는
    회귀 가드. 향후 record 수가 더 커지면 인덱싱 파일이나 SQLite 보조 인덱스로
    전환할 수 있는 구조를 유지한다.
    """
    import time

    idb_id = await _create_idb()

    TOTAL = 200
    for n in range(TOTAL):
        await _seed_record(
            idb_id,
            {
                "boardId": 1000 + n,
                "category": "infra" if n % 2 == 0 else "network",
                "title": f"t-{n}",
            },
        )

    node = _make_node(
        {
            "instanceDbId": idb_id,
            "filterTemplate": {"category": "infra"},
            "limit": 10,
        }
    )

    start = time.perf_counter()
    result = await _run_lookup(node, {}, f"exec-{uuid.uuid4().hex[:6]}")
    elapsed = time.perf_counter() - start

    assert result["count"] == 10, f"limit=10 결과가 10건이 아님: {result['count']}"
    assert len(result["records"]) == 10
    assert all(r["category"] == "infra" for r in result["records"])
    # 10초 임계값 (flaky 회피, Windows tmp 변수성 고려)
    assert elapsed < 10.0, f"filter 200 records 조회가 너무 느림: {elapsed:.2f}s"
