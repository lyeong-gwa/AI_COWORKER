"""인스턴스DB 라우트 — 파일시스템 재설계 후 메타 CRUD + records 조회 검증.

검증 포인트:
1. POST /instance-dbs → 메타 등록 (schema 필드 제거됨)
2. GET 목록 + q 검색
3. GET 상세 + 404 envelope
4. PUT 수정 + 이름 중복 시 409
5. DELETE 시 폴더 통째 삭제 (records 도 함께 사라짐)
6. records 리스트: limit/offset 페이지네이션 + sourceWorkflowId/sourceExecutionId 필터
7. records 단건 GET + 404 envelope
8. 카탈로그에 instance-db-insert / instance-db-lookup 두 엔트리 노출
9. DELETE 참조 무결성 (instance-db-insert/lookup 노드, sorter rule, force=true)

Note
----
records 추가 엔드포인트는 라우트에 없으므로 store 를 직접 호출하여 GET 경로만 검증한다.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import async_session_maker
from app.models.workflow import Workflow, WorkflowNode, WorkflowStatus
from app.services.instance_db_store import get_instance_db_store


client = TestClient(app, raise_server_exceptions=False)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────


def _create_idb(name_suffix: str = "") -> dict:
    """라이프사이클용 메타 1개 등록 후 응답 dict 반환."""
    payload = {
        "name": f"테스트 InstanceDB {uuid.uuid4().hex[:6]}{name_suffix}",
        "description": "test_instance_dbs_api.py 생성",
        "tags": ["test"],
    }
    r = client.post("/api/v1/instance-dbs", json=payload)
    assert r.status_code == 201, f"메타 등록 실패: {r.text}"
    return r.json()


async def _insert_record_directly(
    instance_db_id: str,
    data: dict,
    source_workflow_id: str | None = None,
    source_execution_id: str | None = None,
    source_warehouse_id: str | None = None,
) -> str:
    """store 직접 호출로 record 1건 시드. 라우트에 records 적재 엔드포인트가 없으므로."""
    store = get_instance_db_store()
    rec = await store.insert_record(
        instance_db_id,
        data=data,
        source={
            "workflowId": source_workflow_id,
            "executionId": source_execution_id,
            "warehouseId": source_warehouse_id,
        },
    )
    return rec["id"]


# ── 테스트 ────────────────────────────────────────────────────────────────


def test_create_instance_db_lifecycle():
    """등록 → 목록 노출 → 상세 → 수정 → 삭제 라이프사이클."""
    created = _create_idb()
    idb_id = created["id"]

    assert idb_id.startswith("idb-"), f"id 접두사 idb- 기대, 실제={idb_id}"
    assert created["createdBy"] == "cli"
    assert isinstance(created["tags"], list)
    # schema 키는 사라졌어야 한다
    assert "schema" not in created

    # 목록에 노출
    r = client.get("/api/v1/instance-dbs")
    assert r.status_code == 200
    listing = r.json()
    assert any(item["id"] == idb_id for item in listing), "목록에 등록한 InstanceDB 미노출"

    # 상세 조회
    r = client.get(f"/api/v1/instance-dbs/{idb_id}")
    assert r.status_code == 200
    detail = r.json()
    assert detail["id"] == idb_id
    assert detail["name"] == created["name"]
    assert "schema" not in detail

    # 수정 (description 변경)
    r = client.put(
        f"/api/v1/instance-dbs/{idb_id}",
        json={"description": "수정됨"},
    )
    assert r.status_code == 200, f"수정 실패: {r.text}"
    assert r.json()["description"] == "수정됨"

    # 삭제
    r = client.delete(f"/api/v1/instance-dbs/{idb_id}")
    assert r.status_code == 200
    assert r.json().get("id") == idb_id

    # 삭제 후 404
    r = client.get(f"/api/v1/instance-dbs/{idb_id}")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "NOT_FOUND"
    assert err["details"].get("instanceDbId") == idb_id


def test_create_rejects_empty_name():
    """name 빈 문자열은 422 VALIDATION_ERROR."""
    r = client.post(
        "/api/v1/instance-dbs",
        json={"name": "", "tags": []},
    )
    assert r.status_code == 422, f"빈 name 거부 안됨: {r.status_code} {r.text}"


def test_create_rejects_duplicate_name():
    """동일 name 으로 두 번 등록하면 409 CONFLICT."""
    name = f"중복테스트-{uuid.uuid4().hex[:6]}"
    r1 = client.post("/api/v1/instance-dbs", json={"name": name})
    assert r1.status_code == 201
    r2 = client.post("/api/v1/instance-dbs", json={"name": name})
    assert r2.status_code == 409
    err = r2.json()["error"]
    assert err["code"] == "CONFLICT"

    # 정리
    client.delete(f"/api/v1/instance-dbs/{r1.json()['id']}")


def test_search_by_q_param():
    """q 검색이 name 부분 일치로 동작."""
    unique_marker = f"검색마커{uuid.uuid4().hex[:6]}"
    created = _create_idb(name_suffix=unique_marker)

    r = client.get(f"/api/v1/instance-dbs?q={unique_marker}")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    assert any(item["id"] == created["id"] for item in items)

    # 정리
    client.delete(f"/api/v1/instance-dbs/{created['id']}")


def test_records_list_pagination():
    """records 리스트 페이지네이션 + 메타 삭제 시 폴더 통째 삭제."""
    created = _create_idb()
    idb_id = created["id"]

    # store 직접 삽입: record 3개
    rec_ids = []
    for i in range(3):
        rec_ids.append(
            asyncio.run(
                _insert_record_directly(
                    idb_id,
                    {"boardId": 1000 + i, "title": f"제목{i}"},
                )
            )
        )

    # 전체 리스트
    r = client.get(f"/api/v1/instance-dbs/{idb_id}/records?limit=2&offset=0")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2
    for item in body["items"]:
        assert item["instanceDbId"] == idb_id
        assert "dedupKey" not in item  # 구 필드 사라짐

    # 다음 페이지
    r = client.get(f"/api/v1/instance-dbs/{idb_id}/records?limit=2&offset=2")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1

    # 단건 GET — 가장 먼저 삽입된 것 (createdAt 내림차순이라 마지막 인덱스)
    target_rec_id = rec_ids[0]
    r = client.get(f"/api/v1/instance-dbs/{idb_id}/records/{target_rec_id}")
    assert r.status_code == 200
    rec = r.json()
    assert rec["id"] == target_rec_id
    assert rec["instanceDbId"] == idb_id

    # 존재하지 않는 record id → 404 envelope
    r = client.get(f"/api/v1/instance-dbs/{idb_id}/records/rec-nonexis")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "NOT_FOUND"

    # 메타 삭제 → 폴더 통째 사라짐. 후속 records 조회 404
    r = client.delete(f"/api/v1/instance-dbs/{idb_id}")
    assert r.status_code == 200
    r = client.get(f"/api/v1/instance-dbs/{idb_id}/records")
    assert r.status_code == 404


def test_catalog_exposes_instance_db_entries():
    """카탈로그에 instance-db-insert / instance-db-lookup 두 엔트리가 정상 노출."""
    r = client.get("/api/v1/nodes/catalog")
    assert r.status_code == 200
    catalog = r.json()
    by_type = {e["defType"]: e for e in catalog}

    insert_entry = by_type.get("instance-db-insert")
    assert insert_entry is not None, "instance-db-insert 엔트리가 카탈로그에 없음"
    assert insert_entry["category"] == "action"
    insert_required_cfg = {c["name"] for c in insert_entry["config"] if c.get("required")}
    assert "instanceDbId" in insert_required_cfg, (
        "instance-db-insert.config.instanceDbId required=True 여야 함"
    )
    insert_cfg_names = {c["name"] for c in insert_entry["config"]}
    # 구 필드는 사라졌어야 한다
    assert "dedupKeyTemplate" not in insert_cfg_names
    assert "skipOnDuplicate" not in insert_cfg_names

    lookup_entry = by_type.get("instance-db-lookup")
    assert lookup_entry is not None, "instance-db-lookup 엔트리가 카탈로그에 없음"
    assert lookup_entry["category"] == "action"
    lookup_required_cfg = {c["name"] for c in lookup_entry["config"] if c.get("required")}
    assert "instanceDbId" in lookup_required_cfg
    lookup_cfg_names = {c["name"] for c in lookup_entry["config"]}
    # 구 필드는 사라졌어야 한다
    assert "mode" not in lookup_cfg_names
    assert "keyTemplate" not in lookup_cfg_names


# ── DELETE 참조 무결성 차단 ────────────────────────────────────────────────


async def _seed_workflow_with_node(
    *,
    definition_type: str,
    config: dict,
) -> tuple[str, str]:
    """워크플로우 + 단일 노드 시드. (workflow_id, node_id) 반환."""
    wf_id = f"wf-{uuid.uuid4().hex[:8]}"
    node_id = f"wn-{uuid.uuid4().hex[:8]}"
    async with async_session_maker() as db:
        wf = Workflow(
            id=wf_id,
            name=f"ref-test-{wf_id}",
            description="DELETE 참조 무결성 검증용",
            status=WorkflowStatus.DRAFT,
            trigger={"type": "manual", "config": {}},
            variables={},
            tags=[],
            created_by="test",
        )
        db.add(wf)
        wn = WorkflowNode(
            id=node_id,
            workflow_id=wf_id,
            node_id=f"front-{uuid.uuid4().hex[:6]}",
            definition_type=definition_type,
            config=config,
            name=f"node-{definition_type}",
        )
        db.add(wn)
        await db.commit()
    return wf_id, node_id


async def _cleanup_workflow(workflow_id: str) -> None:
    async with async_session_maker() as db:
        from sqlalchemy import select as sa_select

        wf_obj = (
            await db.execute(sa_select(Workflow).where(Workflow.id == workflow_id))
        ).scalar_one_or_none()
        if wf_obj is not None:
            await db.delete(wf_obj)
            await db.commit()


def test_delete_blocked_by_instance_db_insert_reference():
    """instance-db-insert 노드가 참조 중이면 DELETE 가 409 INSTANCE_DB_REFERENCED."""
    created = _create_idb()
    idb_id = created["id"]

    wf_id, _ = asyncio.run(
        _seed_workflow_with_node(
            definition_type="instance-db-insert",
            config={"instanceDbId": idb_id, "sourceMode": "auto"},
        )
    )
    try:
        r = client.delete(f"/api/v1/instance-dbs/{idb_id}")
        assert r.status_code == 409, f"참조 차단 실패: {r.status_code} {r.text}"
        err = r.json()["error"]
        assert err["code"] == "INSTANCE_DB_REFERENCED", err
        assert err["details"].get("refCount") == 1, err
        assert "force" in err["details"]
    finally:
        asyncio.run(_cleanup_workflow(wf_id))
        client.delete(f"/api/v1/instance-dbs/{idb_id}")


def test_delete_blocked_by_sorter_instance_db_rule_reference():
    """sorter rule (dataSource=instance-db) 가 참조 중이면 DELETE 가 409 차단."""
    created = _create_idb()
    idb_id = created["id"]

    wf_id, _ = asyncio.run(
        _seed_workflow_with_node(
            definition_type="sorter",
            config={
                "rules": [
                    {
                        "id": "already-answered",
                        "dataSource": "instance-db",
                        "instanceDbId": idb_id,
                        "filterTemplate": {"boardId": "{{boardId}}"},
                        "condition": "exists",
                    },
                    {
                        "id": "infra",
                        "field": "category",
                        "operator": "equals",
                        "value": "infra",
                    },
                ],
            },
        )
    )
    try:
        r = client.delete(f"/api/v1/instance-dbs/{idb_id}")
        assert r.status_code == 409, f"sorter rule 참조 차단 실패: {r.status_code} {r.text}"
        err = r.json()["error"]
        assert err["code"] == "INSTANCE_DB_REFERENCED", err
        assert err["details"].get("refCount") == 1, err
    finally:
        asyncio.run(_cleanup_workflow(wf_id))
        client.delete(f"/api/v1/instance-dbs/{idb_id}")


def test_delete_with_force_bypasses_reference_check():
    """force=true 면 참조가 있어도 폴더 삭제가 정상 진행."""
    created = _create_idb()
    idb_id = created["id"]

    wf_id, _ = asyncio.run(
        _seed_workflow_with_node(
            definition_type="instance-db-lookup",
            config={
                "instanceDbId": idb_id,
                "filterTemplate": {"boardId": "{{x}}"},
            },
        )
    )
    try:
        r = client.delete(f"/api/v1/instance-dbs/{idb_id}?force=true")
        assert r.status_code == 200, f"force 모드 실패: {r.status_code} {r.text}"
        body = r.json()
        assert body["id"] == idb_id

        r = client.get(f"/api/v1/instance-dbs/{idb_id}")
        assert r.status_code == 404
    finally:
        asyncio.run(_cleanup_workflow(wf_id))


# ── sourceWorkflowId / sourceExecutionId 필터 ─────────────────────────────


def test_filter_by_source_workflow_id():
    """sourceWorkflowId 필터: 두 워크플로우가 같은 InstanceDB 에 적재 → 한 쪽만 반환."""
    created = _create_idb()
    idb_id = created["id"]

    wf_a = f"wf-filter-a-{uuid.uuid4().hex[:6]}"
    wf_b = f"wf-filter-b-{uuid.uuid4().hex[:6]}"

    for i in range(2):
        asyncio.run(
            _insert_record_directly(
                idb_id,
                {"boardId": 100 + i, "title": f"A-{i}"},
                source_workflow_id=wf_a,
            )
        )
    asyncio.run(
        _insert_record_directly(
            idb_id,
            {"boardId": 200, "title": "B-0"},
            source_workflow_id=wf_b,
        )
    )

    r = client.get(f"/api/v1/instance-dbs/{idb_id}/records?sourceWorkflowId={wf_a}")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2, f"wf_a 필터 total 기대 2, 실제 {body['total']}"
    assert all(item["sourceWorkflowId"] == wf_a for item in body["items"])

    r = client.get(f"/api/v1/instance-dbs/{idb_id}/records?sourceWorkflowId={wf_b}")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["sourceWorkflowId"] == wf_b

    assert "total" in body and "limit" in body and "offset" in body and "items" in body

    client.delete(f"/api/v1/instance-dbs/{idb_id}")


def test_filter_by_source_execution_id():
    """sourceExecutionId 필터: 두 실행이 같은 InstanceDB 에 적재 → 한 실행만 반환."""
    created = _create_idb()
    idb_id = created["id"]

    exec_x = f"exec-x-{uuid.uuid4().hex[:6]}"
    exec_y = f"exec-y-{uuid.uuid4().hex[:6]}"

    asyncio.run(
        _insert_record_directly(
            idb_id, {"boardId": 300, "title": "X-0"}, source_execution_id=exec_x
        )
    )
    for i in range(3):
        asyncio.run(
            _insert_record_directly(
                idb_id, {"boardId": 400 + i, "title": f"Y-{i}"}, source_execution_id=exec_y
            )
        )

    r = client.get(f"/api/v1/instance-dbs/{idb_id}/records?sourceExecutionId={exec_x}")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["sourceExecutionId"] == exec_x

    r = client.get(f"/api/v1/instance-dbs/{idb_id}/records?sourceExecutionId={exec_y}")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert all(item["sourceExecutionId"] == exec_y for item in body["items"])

    client.delete(f"/api/v1/instance-dbs/{idb_id}")


def test_filter_by_both_source_workflow_and_execution_id():
    """sourceWorkflowId + sourceExecutionId 동시 지정 → AND 필터 동작."""
    created = _create_idb()
    idb_id = created["id"]

    wf_id = f"wf-and-{uuid.uuid4().hex[:6]}"
    exec_1 = f"exec-1-{uuid.uuid4().hex[:6]}"
    exec_2 = f"exec-2-{uuid.uuid4().hex[:6]}"

    asyncio.run(
        _insert_record_directly(
            idb_id, {"boardId": 500, "title": "match"},
            source_workflow_id=wf_id, source_execution_id=exec_1,
        )
    )
    asyncio.run(
        _insert_record_directly(
            idb_id, {"boardId": 501, "title": "no-match-exec"},
            source_workflow_id=wf_id, source_execution_id=exec_2,
        )
    )
    asyncio.run(
        _insert_record_directly(
            idb_id, {"boardId": 502, "title": "no-match-wf"},
            source_workflow_id="wf-other", source_execution_id=exec_1,
        )
    )

    r = client.get(
        f"/api/v1/instance-dbs/{idb_id}/records"
        f"?sourceWorkflowId={wf_id}&sourceExecutionId={exec_1}"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1, f"AND 필터 total 기대 1, 실제 {body['total']}"
    item = body["items"][0]
    assert item["sourceWorkflowId"] == wf_id
    assert item["sourceExecutionId"] == exec_1
    assert item["data"]["boardId"] == 500

    assert set(body.keys()) >= {"total", "limit", "offset", "items"}

    client.delete(f"/api/v1/instance-dbs/{idb_id}")
