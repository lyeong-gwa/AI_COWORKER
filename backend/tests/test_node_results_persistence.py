"""Phase 4a — WorkflowExecution.node_results JSON 영속화 검증.

설계서 섹션 8.3 는 노드별 실행 상태의 DB 영속화를 요구한다.
Phase 4a 의 결정: 별도 ``node_execution_results`` 테이블을 신설하지 않고
기존 ``WorkflowExecution.node_results`` JSON 컬럼에 누적한다.

**근거**:
- 기존 엔진(`workflow_engine.py`)은 이미 노드 실행 후 ``self.node_results``
  dict 를 ``self.execution.node_results`` 로 복사 후 commit 하는 루프를 갖는다.
- 토이 단계에서 추가 테이블은 join 비용과 마이그레이션 부담만 가중.
- 행 수 폭증 문제는 워크플로우당 노드 수가 <= WORKFLOW_MAX_NODES (100) 로
  상한이 있으므로 JSON 컬럼 크기도 실질적으로 bounded.

검증 포인트
----------
1. 실행 완료 후 ``execution.node_results`` 에 각 노드별 엔트리가 존재.
2. 각 엔트리는 최소 ``{status, startTime, endTime, outputData}`` 필드 포함.
3. 노드 ID 가 키로 사용되며, 모든 실행 노드가 누락 없이 기록됨.
4. status 값이 "completed" (성공) 또는 "failed" (실패) 중 하나.
"""

from __future__ import annotations

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
from app.services.workflow_engine import WorkflowEngine


async def _setup_wf_with_two_nodes() -> tuple[str, str, tuple[str, str]]:
    wf_id = f"wf-np-{uuid.uuid4().hex[:6]}"
    ex_id = f"exec-np-{uuid.uuid4().hex[:6]}"
    n_start = f"n-start-{uuid.uuid4().hex[:4]}"
    n_result = f"n-result-{uuid.uuid4().hex[:4]}"

    async with async_session_maker() as db:
        db.add(
            Workflow(
                id=wf_id,
                name=f"node-persist-wf {wf_id}",
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
                input_data={"msg": "persist me"},
            )
        )
        await db.commit()

    return wf_id, ex_id, (n_start, n_result)


async def _cleanup(wf_id: str, ex_id: str) -> None:
    async with async_session_maker() as db:
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


# ── 테스트 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_node_results_persisted_after_successful_run():
    """정상 실행 후 DB 에서 execution.node_results 를 재조회하면 노드별 상태 존재."""
    wf_id, ex_id, (n_start, n_result) = await _setup_wf_with_two_nodes()
    try:
        engine = WorkflowEngine(ex_id)
        await engine.run()

        # 별도 세션에서 재조회 (실제로 DB 에 영속화되었는지 확인)
        async with async_session_maker() as db:
            row = (
                await db.execute(
                    select(WorkflowExecution).where(WorkflowExecution.id == ex_id)
                )
            ).scalar_one()
            assert row.status == ExecutionStatus.COMPLETED

            node_results = row.node_results or {}
            assert isinstance(node_results, dict), (
                f"node_results 가 dict 가 아님: {type(node_results)}"
            )

            # 두 노드 모두 기록되어야 한다
            assert n_start in node_results, (
                f"시작 노드 {n_start} 가 node_results 에 없음: keys={list(node_results)}"
            )
            assert n_result in node_results, (
                f"결과 노드 {n_result} 가 node_results 에 없음: keys={list(node_results)}"
            )

            # 각 엔트리의 필수 필드 검증
            for nid, block in node_results.items():
                assert isinstance(block, dict), f"{nid} 결과가 dict 아님"
                assert block.get("status") == "completed", (
                    f"{nid} status 가 completed 가 아님: {block.get('status')}"
                )
                assert "startTime" in block, f"{nid} startTime 누락"
                assert "endTime" in block, f"{nid} endTime 누락"
                assert "outputData" in block, f"{nid} outputData 누락"
                assert block.get("definitionType") in ("form-start", "result"), (
                    f"{nid} definitionType 누락/오류: {block.get('definitionType')}"
                )
    finally:
        await _cleanup(wf_id, ex_id)


@pytest.mark.asyncio
async def test_node_results_captures_failure_state():
    """실패 실행도 node_results 에 반영되어야 한다. 여기선 실행 자체가 노드 진입 전
    fail 하는 케이스를 사용하므로 node_results 는 비어있을 수 있지만, DB 상태는
    FAILED 이고 error_message 가 기록된다."""
    wf_id = f"wf-npfail-{uuid.uuid4().hex[:6]}"
    ex_id = f"exec-npfail-{uuid.uuid4().hex[:6]}"

    async with async_session_maker() as db:
        db.add(
            Workflow(
                id=wf_id,
                name="fail-persist-wf",
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
        engine = WorkflowEngine(ex_id)
        with pytest.raises(ValueError):
            await engine.run()

        async with async_session_maker() as db:
            row = (
                await db.execute(
                    select(WorkflowExecution).where(WorkflowExecution.id == ex_id)
                )
            ).scalar_one()
            assert row.status == ExecutionStatus.FAILED
            assert row.error_message and "시작 노드" in row.error_message
            # node_results 는 dict 이고 (빈 dict 여도 OK) 타입 계약이 지켜져야 함
            assert isinstance(row.node_results, dict)
    finally:
        async with async_session_maker() as db:
            ex = (
                await db.execute(
                    select(WorkflowExecution).where(WorkflowExecution.id == ex_id)
                )
            ).scalar_one_or_none()
            if ex is not None:
                await db.delete(ex)
            wf = (
                await db.execute(select(Workflow).where(Workflow.id == wf_id))
            ).scalar_one_or_none()
            if wf is not None:
                await db.delete(wf)
            await db.commit()


@pytest.mark.asyncio
async def test_node_results_structure_matches_sse_polling_contract():
    """warehouse.py SSE polling 엔드포인트가 의존하는 필드들이 node_results 에 실제 존재.

    SSE polling 은 각 ``node_results[node_id]["status"]`` 의 변화를 diff 로 감지하고
    ``outputData`` / ``error`` 를 이벤트 payload 로 꺼낸다. 이 계약이 깨지면
    Phase 4b 에서 SSE 를 push 기반으로 교체할 때 frontend 호환성이 문제가 된다.
    """
    wf_id, ex_id, (n_start, n_result) = await _setup_wf_with_two_nodes()
    try:
        engine = WorkflowEngine(ex_id)
        await engine.run()

        async with async_session_maker() as db:
            row = (
                await db.execute(
                    select(WorkflowExecution).where(WorkflowExecution.id == ex_id)
                )
            ).scalar_one()

        node_results = row.node_results or {}
        # SSE polling 이 의존하는 필드
        for nid, block in node_results.items():
            assert "status" in block, (
                f"SSE polling 은 status 를 기대하지만 {nid} 에 없음"
            )
            # 완료 상태라면 outputData 기대
            if block["status"] == "completed":
                assert "outputData" in block, (
                    f"completed 상태인데 outputData 없음: {nid}"
                )
    finally:
        await _cleanup(wf_id, ex_id)
