"""워크플로우 cascade 삭제 + delete-preview 검증.

검증 포인트:
1. /workflows/{id}/delete-preview — 카운트 정확
2. DELETE /workflows/{id} — workflow + nodes + connections + executions + warehouse_entries
   가 모두 삭제됨 (쓰레기 데이터 0)
3. 미존재 워크플로우 DELETE / preview → 404
4. cascade 응답 body 의 카운트 정확
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
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


client = TestClient(app, raise_server_exceptions=False)


# ── 픽스처 시드 ────────────────────────────────────────────────────────────


async def _seed_workflow_with_data(
    *,
    instance_count: int,
    warehouse_per_instance: int,
    node_results_per_instance: int = 2,
) -> tuple[str, list[str], list[str], list[str], list[str]]:
    """워크플로우 + 노드·연결선·실행이력·창고 항목 시드.

    반환: (wf_id, node_ids, connection_ids, execution_ids, warehouse_ids)
    """
    wf_id = f"wf-cascade-{uuid.uuid4().hex[:8]}"
    node_ids = [f"wn-{uuid.uuid4().hex[:8]}" for _ in range(2)]
    conn_ids = [f"wc-{uuid.uuid4().hex[:8]}"]
    exec_ids: list[str] = []
    warehouse_ids: list[str] = []

    async with async_session_maker() as db:
        wf = Workflow(
            id=wf_id,
            name=f"cascade-test-{wf_id}",
            description="cascade 삭제 검증용",
            status=WorkflowStatus.DRAFT,
            trigger={"type": "manual", "config": {}},
            variables={},
            tags=[],
            created_by="test",
        )
        db.add(wf)

        # 노드 2개
        for i, nid in enumerate(node_ids):
            db.add(
                WorkflowNode(
                    id=nid,
                    workflow_id=wf_id,
                    node_id=f"front-{nid}",
                    definition_type="ai-custom",
                    config={},
                    name=f"node-{i}",
                )
            )

        # 연결선 1개
        db.add(
            WorkflowConnection(
                id=conn_ids[0],
                workflow_id=wf_id,
                source_node_id=node_ids[0],
                target_node_id=node_ids[1],
            )
        )

        # 실행 이력 N건
        for i in range(instance_count):
            eid = f"exec-cascade-{uuid.uuid4().hex[:8]}"
            exec_ids.append(eid)
            # node_results 안에 N 개 키
            nr = {
                f"step-{k}": {"status": "completed", "outputData": {"v": k}}
                for k in range(node_results_per_instance)
            }
            db.add(
                WorkflowExecution(
                    id=eid,
                    workflow_id=wf_id,
                    status=ExecutionStatus.COMPLETED,
                    input_data={"i": i},
                    output_data={"ok": True},
                    node_results=nr,
                )
            )
            # 창고 항목 per_instance 개
            for j in range(warehouse_per_instance):
                wid = f"wh-cascade-{uuid.uuid4().hex[:8]}"
                warehouse_ids.append(wid)
                db.add(
                    WarehouseEntry(
                        id=wid,
                        node_instance_id=node_ids[0],
                        execution_id=eid,
                        data={"i": i, "j": j},
                    )
                )

        await db.commit()

    return wf_id, node_ids, conn_ids, exec_ids, warehouse_ids


async def _count_all(wf_id: str, exec_ids: list[str]) -> dict:
    """4개 테이블에서 wf 관련 row 카운트."""
    async with async_session_maker() as db:
        nodes = int(
            (
                await db.execute(
                    select(func.count(WorkflowNode.id)).where(
                        WorkflowNode.workflow_id == wf_id
                    )
                )
            ).scalar()
            or 0
        )
        conns = int(
            (
                await db.execute(
                    select(func.count(WorkflowConnection.id)).where(
                        WorkflowConnection.workflow_id == wf_id
                    )
                )
            ).scalar()
            or 0
        )
        execs = int(
            (
                await db.execute(
                    select(func.count(WorkflowExecution.id)).where(
                        WorkflowExecution.workflow_id == wf_id
                    )
                )
            ).scalar()
            or 0
        )
        warehouse = 0
        if exec_ids:
            warehouse = int(
                (
                    await db.execute(
                        select(func.count(WarehouseEntry.id)).where(
                            WarehouseEntry.execution_id.in_(exec_ids)
                        )
                    )
                ).scalar()
                or 0
            )
        wf_exists = (
            (await db.execute(select(Workflow).where(Workflow.id == wf_id)))
            .scalar_one_or_none()
        ) is not None
        return {
            "workflow": 1 if wf_exists else 0,
            "nodes": nodes,
            "connections": conns,
            "executions": execs,
            "warehouseEntries": warehouse,
        }


# ── 테스트 ────────────────────────────────────────────────────────────────


def test_delete_preview_returns_accurate_counts():
    """/delete-preview 응답 카운트가 실제 시드 데이터와 일치."""
    wf_id, _, _, exec_ids, warehouse_ids = asyncio.run(
        _seed_workflow_with_data(
            instance_count=3,
            warehouse_per_instance=4,
            node_results_per_instance=2,
        )
    )
    try:
        r = client.get(f"/api/v1/workflows/{wf_id}/delete-preview")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["workflowId"] == wf_id
        assert body["workflowName"].startswith("cascade-test-")
        assert body["instanceCount"] == 3
        assert body["warehouseEntryCount"] == 3 * 4  # 12
        assert body["nodeResultCount"] == 3 * 2  # 6
        assert body["willCascadeDelete"] is True
    finally:
        # 정리 — 실제 DELETE 호출
        client.delete(f"/api/v1/workflows/{wf_id}")


def test_delete_workflow_cascade_zeros_all_related_rows():
    """워크플로우 DELETE 시 nodes/connections/executions/warehouse_entries 모두 0."""
    wf_id, node_ids, conn_ids, exec_ids, warehouse_ids = asyncio.run(
        _seed_workflow_with_data(
            instance_count=2,
            warehouse_per_instance=5,
            node_results_per_instance=3,
        )
    )

    # 사전 카운트 — 시드가 정확히 들어갔는지 검증
    before = asyncio.run(_count_all(wf_id, exec_ids))
    assert before == {
        "workflow": 1,
        "nodes": 2,
        "connections": 1,
        "executions": 2,
        "warehouseEntries": 10,
    }, f"시드 상태 불일치: {before}"

    # DELETE
    r = client.delete(f"/api/v1/workflows/{wf_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] is True
    assert body["workflowId"] == wf_id
    cascade = body["cascadeCounts"]
    assert cascade["instances"] == 2
    assert cascade["warehouseEntries"] == 10
    assert cascade["nodeResults"] == 6

    # 사후 카운트 — 모두 0 (쓰레기 데이터 0)
    after = asyncio.run(_count_all(wf_id, exec_ids))
    assert after == {
        "workflow": 0,
        "nodes": 0,
        "connections": 0,
        "executions": 0,
        "warehouseEntries": 0,
    }, f"잔존 데이터 발견: {after}"


def test_delete_missing_workflow_returns_404():
    """미존재 워크플로우 DELETE → 404 envelope."""
    ghost = f"wf-ghost-{uuid.uuid4().hex[:8]}"
    r = client.delete(f"/api/v1/workflows/{ghost}")
    assert r.status_code == 404, r.text
    err = r.json()["error"]
    assert err["code"] == "NOT_FOUND"
    assert err["details"]["workflowId"] == ghost


def test_delete_preview_missing_workflow_returns_404():
    """미존재 워크플로우 /delete-preview → 404 envelope."""
    ghost = f"wf-ghost-{uuid.uuid4().hex[:8]}"
    r = client.get(f"/api/v1/workflows/{ghost}/delete-preview")
    assert r.status_code == 404, r.text
    err = r.json()["error"]
    assert err["code"] == "NOT_FOUND"


def test_delete_workflow_with_no_executions_returns_zero_cascade():
    """실행이력 없는 워크플로우 DELETE → cascade 카운트 모두 0, 정상 삭제."""
    wf_id, _, _, _, _ = asyncio.run(
        _seed_workflow_with_data(
            instance_count=0,
            warehouse_per_instance=0,
            node_results_per_instance=0,
        )
    )
    r = client.delete(f"/api/v1/workflows/{wf_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cascadeCounts"]["instances"] == 0
    assert body["cascadeCounts"]["warehouseEntries"] == 0
    assert body["cascadeCounts"]["nodeResults"] == 0

    # 워크플로우 자체는 사라짐
    after = asyncio.run(_count_all(wf_id, []))
    assert after["workflow"] == 0


def test_delete_does_not_touch_other_workflows():
    """다른 워크플로우의 실행/창고는 영향받지 않음 (격리)."""
    wf_a, _, _, exec_a, _ = asyncio.run(
        _seed_workflow_with_data(
            instance_count=2, warehouse_per_instance=3
        )
    )
    wf_b, _, _, exec_b, _ = asyncio.run(
        _seed_workflow_with_data(
            instance_count=1, warehouse_per_instance=2
        )
    )
    try:
        r = client.delete(f"/api/v1/workflows/{wf_a}")
        assert r.status_code == 200, r.text

        # wf_a → 0
        after_a = asyncio.run(_count_all(wf_a, exec_a))
        assert after_a["workflow"] == 0
        assert after_a["warehouseEntries"] == 0

        # wf_b → 보존
        after_b = asyncio.run(_count_all(wf_b, exec_b))
        assert after_b["workflow"] == 1
        assert after_b["executions"] == 1
        assert after_b["warehouseEntries"] == 2
    finally:
        client.delete(f"/api/v1/workflows/{wf_b}")
