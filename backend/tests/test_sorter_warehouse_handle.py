"""sorter 노드 — warehouse 적재 시 분기 메타 포함 검증.

T1: rule 매칭 → warehouse data 에 __sorterHandle == matched handle, __matchedRuleId == rule id
T2: rule 미매칭(default) → __sorterHandle == "default", __matchedRuleId == None
T3: 기존 outputData 형식 변경 없음 회귀 (BeltKey.SORTER_HANDLE 값 정상)
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, Dict

import pytest
from sqlalchemy import select as sa_select

from app.core.constants import BeltKey
from app.core.database import async_session_maker
from app.models.workflow import WarehouseEntry
from app.nodes.base import ExecutionContext
from app.nodes.registry import NodeHandlerRegistry
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


async def _run_sorter_and_get_entry(
    node: SimpleNamespace,
    input_data: Dict[str, Any],
    execution_id: str,
):
    """sorter 실행 후 (output_result, warehouse_entry_data) 반환."""
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

        # 방금 생성된 warehouse entry 조회
        stmt = sa_select(WarehouseEntry).where(
            WarehouseEntry.node_instance_id == node.id,
            WarehouseEntry.execution_id == execution_id,
        )
        rows = (await db.execute(stmt)).scalars().all()

    return result, rows


# ── T1: rule 매칭 → warehouse data 에 __sorterHandle 및 __matchedRuleId ──


@pytest.mark.asyncio
async def test_warehouse_entry_contains_sorter_handle_when_rule_matched():
    """T1: rule 1개 매칭 → warehouse data 에 __sorterHandle == 해당 handle,
    __matchedRuleId == rule.id"""
    node = _make_node(
        {
            "rules": [
                {
                    "id": "newonly",
                    "field": "status",
                    "operator": "equals",
                    "value": "신규",
                },
            ],
        }
    )
    execution_id = f"exec-{uuid.uuid4().hex[:8]}"
    input_data = {"status": "신규", "title": "테스트 항목"}

    output, entries = await _run_sorter_and_get_entry(node, input_data, execution_id)

    # outputData 형식 확인
    assert output[BeltKey.SORTER_HANDLE] == "rule-newonly"

    # warehouse entry 존재 및 메타 확인
    assert len(entries) == 1, f"warehouse entry 수: {len(entries)}"
    data = entries[0].data
    assert data["__sorterHandle"] == "rule-newonly", data
    assert data["__matchedRuleId"] == "newonly", data

    # 원본 필드도 보존되어 있어야 함
    assert data.get("status") == "신규", data


# ── T2: rule 미매칭(default) → __sorterHandle == "default", __matchedRuleId == None ──


@pytest.mark.asyncio
async def test_warehouse_entry_has_default_handle_when_no_rule_matched():
    """T2: 어떤 rule 도 매칭되지 않으면 __sorterHandle == 'default',
    __matchedRuleId == None"""
    node = _make_node(
        {
            "rules": [
                {
                    "id": "onlynew",
                    "field": "status",
                    "operator": "equals",
                    "value": "신규",
                },
            ],
        }
    )
    execution_id = f"exec-{uuid.uuid4().hex[:8]}"
    input_data = {"status": "완료"}  # 매칭 안됨

    output, entries = await _run_sorter_and_get_entry(node, input_data, execution_id)

    assert output[BeltKey.SORTER_HANDLE] == "default"

    assert len(entries) == 1, f"warehouse entry 수: {len(entries)}"
    data = entries[0].data
    assert data["__sorterHandle"] == "default", data
    assert data["__matchedRuleId"] is None, data


# ── T3: 기존 outputData 형식 변경 없음 회귀 ──────────────────────────────


@pytest.mark.asyncio
async def test_output_data_format_unchanged():
    """T3: 다음 노드에 전달되는 outputData 형식({__sorterHandle: ...}) 변경 없음."""
    node = _make_node(
        {
            "rules": [
                {
                    "id": "matched",
                    "field": "flag",
                    "operator": "equals",
                    "value": "yes",
                },
            ],
        }
    )
    execution_id = f"exec-{uuid.uuid4().hex[:8]}"

    # 매칭 케이스
    output_matched, _ = await _run_sorter_and_get_entry(
        node, {"flag": "yes"}, execution_id
    )
    assert set(output_matched.keys()) == {BeltKey.SORTER_HANDLE}, (
        f"outputData 에 예상치 못한 키 포함: {output_matched.keys()}"
    )
    assert output_matched[BeltKey.SORTER_HANDLE] == "rule-matched"

    # 미매칭 케이스
    execution_id2 = f"exec-{uuid.uuid4().hex[:8]}"
    output_default, _ = await _run_sorter_and_get_entry(
        node, {"flag": "no"}, execution_id2
    )
    assert set(output_default.keys()) == {BeltKey.SORTER_HANDLE}, (
        f"outputData 에 예상치 못한 키 포함: {output_default.keys()}"
    )
    assert output_default[BeltKey.SORTER_HANDLE] == "default"
