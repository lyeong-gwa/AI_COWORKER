"""Self-contained workflow blueprint — Phase 6 (import) + Phase 8 (reconciliation) 테스트.

검증 범위:
- Phase 6 import:
  - 재-ID (fresh wn-/wc-, 내부 참조 일관성: connections, sorter rules)
  - import 가 ApiDefinition/AINode 레지스트리 행을 추가하지 않음 (스냅샷-only)
  - instanceDb name-match 재사용 + 미존재 시 생성(빈 store) + instanceDbId 노드/소터 재작성
  - 재료(auth/defaultParams)를 삭제해도 스냅샷-only 로 검증 통과
  - 버전 불일치 422 (BLUEPRINT_INCOMPATIBLE)
  - dryRun 은 아무것도 쓰지 않음 (워크플로우/인스턴스DB 미생성)
- Phase 8 reconciliation:
  - knowledge satisfied/partial/missing
  - materialsToFill 가 redactedFields 에서 new id 로 remap 되어 도출
  - fill-materials 가 값 set + 재동결 안 함 + materialsToFill 축소
  - knowledge-remap 가 config 재작성
- E2E 라운드트립: export → import → (재료 남아있어도) 검증 통과 & 스냅샷으로 실행 가능
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from app.main import app
from app.core.database import async_session_maker
from app.models.api_definition import ApiDefinition
from app.models.node import AINode
from app.models.workflow import (
    Workflow,
    WorkflowNode,
    WorkflowConnection,
    WorkflowStatus,
)
from app.services.instance_db_store import get_instance_db_store


client = TestClient(app, raise_server_exceptions=False)


# ── 재료 시드/삭제 헬퍼 ──────────────────────────────────────────────────────


async def _make_api_def(**overrides: Any) -> str:
    api_id = overrides.pop("id", None) or f"api-{uuid.uuid4().hex[:8]}"
    async with async_session_maker() as db:
        api_def = ApiDefinition(
            id=api_id,
            name=overrides.get("name", "테스트 API"),
            description=overrides.get("description", "import 테스트"),
            method=overrides.get("method", "GET"),
            url_template=overrides.get("url_template", "http://localhost:8001/test"),
            headers=overrides.get("headers", {"X-Trace": "1"}),
            body_template=overrides.get("body_template"),
            auth_type=overrides.get("auth_type", "bearer"),
            auth_config=overrides.get("auth_config", {"token": "secret-token"}),
            parameters=overrides.get("parameters", [{"name": "q", "in": "query"}]),
            response_schema=overrides.get("response_schema", {}),
            tags=[],
        )
        db.add(api_def)
        await db.commit()
    return api_id


async def _delete_api_def(api_id: str) -> None:
    async with async_session_maker() as db:
        await db.execute(delete(ApiDefinition).where(ApiDefinition.id == api_id))
        await db.commit()


async def _make_ai_node(**overrides: Any) -> str:
    node_id = overrides.pop("id", None) or f"ai-{uuid.uuid4().hex[:8]}"
    async with async_session_maker() as db:
        ai_node = AINode(
            id=node_id,
            name=overrides.get("name", "테스트 AI 노드"),
            description=overrides.get("description", "import 테스트"),
            system_prompt=overrides.get("system_prompt", "you are helpful"),
            user_prompt_template=overrides.get("user_prompt_template", "안녕 {{input.x}}"),
            input_schema=overrides.get("input_schema", {"type": "object", "properties": {}}),
            output_schema=overrides.get("output_schema", {"type": "object", "properties": {}}),
            output_enforcement=overrides.get("output_enforcement", {}),
            llm_config=overrides.get("llm_config", {"model": "gpt-4o-mini"}),
            tags=[],
        )
        db.add(ai_node)
        await db.commit()
    return node_id


async def _delete_ai_node(node_id: str) -> None:
    async with async_session_maker() as db:
        await db.execute(delete(AINode).where(AINode.id == node_id))
        await db.commit()


async def _make_workflow_raw(
    nodes: List[Dict[str, Any]],
    connections: Optional[List[Dict[str, Any]]] = None,
) -> str:
    wf_id = f"wf-{uuid.uuid4().hex[:8]}"
    async with async_session_maker() as db:
        wf = Workflow(
            id=wf_id,
            name="blueprint-import-test-wf",
            description="import 테스트용",
            status=WorkflowStatus.DRAFT,
            tags=["bp"],
            trigger={"type": "manual", "config": {}},
            variables={},
            created_by="cli",
        )
        db.add(wf)
        for idx, nd in enumerate(nodes):
            db.add(
                WorkflowNode(
                    id=nd.get("id") or f"wn-{uuid.uuid4().hex[:8]}",
                    workflow_id=wf_id,
                    node_id=nd["nodeId"],
                    definition_type=nd["definitionType"],
                    ai_node_id=nd.get("aiNodeId"),
                    config=nd.get("config", {}),
                    name=nd.get("name", nd["nodeId"]),
                    order_index=nd.get("orderIndex", idx),
                    config_overrides=nd.get("configOverrides", {}),
                    input_mapping=nd.get("inputMapping", {}),
                )
            )
        for c in (connections or []):
            db.add(
                WorkflowConnection(
                    id=c.get("id") or f"wc-{uuid.uuid4().hex[:8]}",
                    workflow_id=wf_id,
                    source_node_id=c["sourceNodeId"],
                    target_node_id=c["targetNodeId"],
                    source_handle=c.get("sourceHandle"),
                    target_handle=c.get("targetHandle"),
                    condition=c.get("condition"),
                )
            )
        await db.commit()
    return wf_id


async def _delete_workflow(wf_id: str) -> None:
    async with async_session_maker() as db:
        wf = await db.get(Workflow, wf_id)
        if wf:
            await db.delete(wf)
            await db.commit()


async def _load_nodes(wf_id: str) -> List[WorkflowNode]:
    async with async_session_maker() as db:
        result = await db.execute(
            select(Workflow)
            .options(selectinload(Workflow.nodes), selectinload(Workflow.connections))
            .where(Workflow.id == wf_id)
        )
        wf = result.scalar_one()
        return list(wf.nodes)


async def _node_config(wf_id: str, node_id: str) -> Dict[str, Any]:
    nodes = await _load_nodes(wf_id)
    for n in nodes:
        if n.node_id == node_id:
            return n.config or {}
    raise AssertionError(f"node {node_id} not found in {wf_id}")


async def _count_api_defs() -> int:
    async with async_session_maker() as db:
        return int((await db.execute(select(func.count(ApiDefinition.id)))).scalar() or 0)


async def _count_ai_nodes() -> int:
    async with async_session_maker() as db:
        return int((await db.execute(select(func.count(AINode.id)))).scalar() or 0)


# ── 설계도 빌더 헬퍼 ─────────────────────────────────────────────────────────


def _api_snapshot(url: str = "http://localhost:8001/imp", token_blank: bool = True) -> Dict[str, Any]:
    return {
        "method": "GET",
        "urlTemplate": url,
        "headers": {"X-Trace": "1"},
        "authType": "bearer",
        "authConfig": {"token": "" if token_blank else "live-secret"},
        "parameters": [{"name": "q", "in": "query"}],
        "responseSchema": {"fields": [{"field": "id", "type": "int"}]},
        "name": "snap api",
        "description": "snap",
        "id": "api-original-src",
    }


def _ai_snapshot() -> Dict[str, Any]:
    return {
        "systemPrompt": "you are helpful",
        "userPromptTemplate": "설계도 {{input.q}}",
        "inputSchema": {"type": "object", "properties": {}},
        "outputSchema": {"type": "object", "properties": {}},
        "outputEnforcement": {},
        "llmConfig": {"model": "gpt-4o-mini"},
        "name": "snap ai",
        "description": "snap",
        "id": "ai-original-src",
    }


def _base_blueprint(nodes: List[Dict[str, Any]], connections: List[Dict[str, Any]],
                    instance_dbs: Optional[List[Dict[str, Any]]] = None,
                    knowledge: Optional[List[Dict[str, Any]]] = None,
                    redacted: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    return {
        "blueprintVersion": "1.0",
        "kind": "workflow-blueprint",
        "exportedAt": "2026-06-05T00:00:00",
        "sourceWorkflowId": "wf-source",
        "workflow": {
            "name": "imported wf",
            "description": "from blueprint",
            "tags": ["imp"],
            "trigger": {"type": "manual", "config": {}},
            "variables": {},
            "nodes": nodes,
            "connections": connections,
        },
        "dependencies": {
            "instanceDbs": instance_dbs or [],
            "knowledge": knowledge or [],
        },
        "redactedFields": redacted or [],
    }


# ════════════════════════════════════════════════════════════════════════════
# PHASE 6 — import
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_import_reids_nodes_and_keeps_refs_consistent():
    """import 가 새 wn-/wc- id 를 부여하고 내부 참조(연결)를 일관되게 리매핑한다."""
    bp = _base_blueprint(
        nodes=[
            {
                "nodeId": "old-api",
                "definitionType": "api-start",
                "name": "API",
                "orderIndex": 0,
                "config": {
                    "apiDefinitionId": "api-original-src",
                    "apiSpecSnapshot": _api_snapshot(),
                    "snapshotSourceId": "api-original-src",
                    "defaultParams": {"owner": ""},
                },
                "configOverrides": {},
                "inputMapping": {},
            },
            {
                "nodeId": "old-out",
                "definitionType": "result",
                "name": "OUT",
                "orderIndex": 1,
                "config": {},
                "configOverrides": {},
                "inputMapping": {},
            },
        ],
        connections=[
            {"id": "oldc1", "sourceNodeId": "old-api", "targetNodeId": "old-out",
             "sourceHandle": None, "targetHandle": None, "condition": None},
        ],
    )
    r = client.post("/api/v1/blueprint/import", json={"blueprint": bp})
    assert r.status_code == 200, r.text
    body = r.json()
    wf_id = body["workflowId"]
    try:
        async with async_session_maker() as db:
            result = await db.execute(
                select(Workflow)
                .options(selectinload(Workflow.nodes), selectinload(Workflow.connections))
                .where(Workflow.id == wf_id)
            )
            wf = result.scalar_one()
            node_ids = {n.node_id for n in wf.nodes}
            # fresh ids — 옛 id 사라짐, wn- 접두사
            assert "old-api" not in node_ids
            assert "old-out" not in node_ids
            assert all(nid.startswith("wn-") for nid in node_ids)
            # 연결 일관성 — endpoint 가 새 노드 id 를 가리킴 + wc- 접두사
            for c in wf.connections:
                assert c.id.startswith("wc-")
                assert c.source_node_id in node_ids
                assert c.target_node_id in node_ids
    finally:
        await _delete_workflow(wf_id)


@pytest.mark.asyncio
async def test_import_remaps_sorter_rule_instance_db_id():
    """import 가 sorter rules[].instanceDbId 를 name-match 로 생성된 로컬 id 로 재작성한다."""
    # 빈 store 가정 — name-match 실패 → create.
    bp_idb_name = f"sorter-idb-{uuid.uuid4().hex[:6]}"
    bp = _base_blueprint(
        nodes=[
            {"nodeId": "old-start", "definitionType": "form-start", "name": "S",
             "orderIndex": 0, "config": {}, "configOverrides": {}, "inputMapping": {}},
            {
                "nodeId": "old-sorter",
                "definitionType": "sorter",
                "name": "SORT",
                "orderIndex": 1,
                "config": {
                    "rules": [
                        {
                            "id": "r1",
                            "dataSource": "instance-db",
                            "instanceDbId": "idb-source-1",
                            "filterTemplate": {"k": "{{k}}"},
                            "condition": "not_exists",
                        }
                    ]
                },
                "configOverrides": {},
                "inputMapping": {},
            },
            {"nodeId": "old-out", "definitionType": "result", "name": "OUT",
             "orderIndex": 2, "config": {}, "configOverrides": {}, "inputMapping": {}},
        ],
        connections=[
            {"id": "c1", "sourceNodeId": "old-start", "targetNodeId": "old-sorter",
             "sourceHandle": None, "targetHandle": None, "condition": None},
            {"id": "c2", "sourceNodeId": "old-sorter", "targetNodeId": "old-out",
             "sourceHandle": "rule-r1", "targetHandle": None, "condition": None},
        ],
        instance_dbs=[
            {"snapshotSourceId": "idb-source-1", "name": bp_idb_name,
             "description": "sorter idb", "tags": ["t"], "viewerHints": {}},
        ],
    )
    r = client.post("/api/v1/blueprint/import", json={"blueprint": bp})
    assert r.status_code == 200, r.text
    wf_id = r.json()["workflowId"]
    try:
        # 생성된 로컬 instanceDb id 확인
        store = get_instance_db_store()
        metas = await store.list_meta()
        created = next(m for m in metas if m["name"] == bp_idb_name)
        local_id = created["id"]
        assert local_id.startswith("idb-")
        assert local_id != "idb-source-1"

        # sorter rule 의 instanceDbId 가 로컬 id 로 재작성됨
        nodes = await _load_nodes(wf_id)
        sorter = next(n for n in nodes if n.definition_type == "sorter")
        assert sorter.config["rules"][0]["instanceDbId"] == local_id
    finally:
        await _delete_workflow(wf_id)


@pytest.mark.asyncio
async def test_import_instance_db_name_match_reuse():
    """기존에 같은 name 의 instanceDb 가 있으면 재사용하고 새로 만들지 않는다."""
    store = get_instance_db_store()
    name = f"reuse-idb-{uuid.uuid4().hex[:6]}"
    existing = await store.create_meta(name=name, description="기존", tags=[], viewer_hints={})
    existing_id = existing["id"]
    before_count = len(await store.list_meta())

    bp = _base_blueprint(
        nodes=[
            {"nodeId": "old-start", "definitionType": "form-start", "name": "S",
             "orderIndex": 0, "config": {}, "configOverrides": {}, "inputMapping": {}},
            {
                "nodeId": "old-idb",
                "definitionType": "instance-db-insert",
                "name": "IDB",
                "orderIndex": 1,
                "config": {
                    "instanceDbId": "idb-source-x",
                    "snapshotSourceId": "idb-source-x",
                    "instanceDbMeta": {"name": name, "snapshotSourceId": "idb-source-x"},
                },
                "configOverrides": {},
                "inputMapping": {},
            },
        ],
        connections=[
            {"id": "c1", "sourceNodeId": "old-start", "targetNodeId": "old-idb",
             "sourceHandle": None, "targetHandle": None, "condition": None},
        ],
        instance_dbs=[
            {"snapshotSourceId": "idb-source-x", "name": name,
             "description": "기존", "tags": [], "viewerHints": {}},
        ],
    )
    r = client.post("/api/v1/blueprint/import", json={"blueprint": bp})
    assert r.status_code == 200, r.text
    wf_id = r.json()["workflowId"]
    try:
        after_count = len(await store.list_meta())
        assert after_count == before_count  # 새로 만들지 않음 (재사용)

        cfg = await _node_config(wf_id, await _first_idb_node_id(wf_id))
        assert cfg["instanceDbId"] == existing_id
        assert cfg["instanceDbMeta"]["snapshotSourceId"] == existing_id
    finally:
        await _delete_workflow(wf_id)


async def _first_idb_node_id(wf_id: str) -> str:
    nodes = await _load_nodes(wf_id)
    return next(n.node_id for n in nodes if n.definition_type == "instance-db-insert")


@pytest.mark.asyncio
async def test_import_no_registry_writes():
    """import 는 ApiDefinition/AINode 레지스트리 행을 추가하지 않는다 (스냅샷-only)."""
    api_before = await _count_api_defs()
    ai_before = await _count_ai_nodes()

    bp = _base_blueprint(
        nodes=[
            {"nodeId": "old-api", "definitionType": "api-start", "name": "API",
             "orderIndex": 0, "config": {
                 "apiDefinitionId": "api-original-src",
                 "apiSpecSnapshot": _api_snapshot(),
                 "snapshotSourceId": "api-original-src"},
             "configOverrides": {}, "inputMapping": {}},
            {"nodeId": "old-ai", "definitionType": "ai-custom", "name": "AI",
             "orderIndex": 1, "config": {
                 "ai_node_id": "ai-original-src",
                 "aiNodeSnapshot": _ai_snapshot(),
                 "snapshotSourceId": "ai-original-src"},
             "configOverrides": {}, "inputMapping": {}},
            {"nodeId": "old-out", "definitionType": "result", "name": "OUT",
             "orderIndex": 2, "config": {}, "configOverrides": {}, "inputMapping": {}},
        ],
        connections=[
            {"id": "c1", "sourceNodeId": "old-api", "targetNodeId": "old-ai",
             "sourceHandle": None, "targetHandle": None, "condition": None},
            {"id": "c2", "sourceNodeId": "old-ai", "targetNodeId": "old-out",
             "sourceHandle": None, "targetHandle": None, "condition": None},
        ],
    )
    r = client.post("/api/v1/blueprint/import", json={"blueprint": bp})
    assert r.status_code == 200, r.text
    wf_id = r.json()["workflowId"]
    try:
        assert await _count_api_defs() == api_before  # 레지스트리 미증가
        assert await _count_ai_nodes() == ai_before
        # 스냅샷은 노드 config 에 남아 있음
        nodes = await _load_nodes(wf_id)
        api_node = next(n for n in nodes if n.definition_type == "api-start")
        assert api_node.config["apiSpecSnapshot"]["urlTemplate"]
    finally:
        await _delete_workflow(wf_id)


@pytest.mark.asyncio
async def test_import_validates_with_materials_deleted_snapshot_only():
    """재료(라이브 ApiDefinition)가 없어도 스냅샷-only 로 검증을 통과한다."""
    # 라이브 재료 없음 — 스냅샷만으로 E7 통과해야 한다.
    bp = _base_blueprint(
        nodes=[
            {"nodeId": "old-api", "definitionType": "api-start", "name": "API",
             "orderIndex": 0, "config": {
                 "apiDefinitionId": "api-nonexistent",
                 "apiSpecSnapshot": _api_snapshot(),
                 "snapshotSourceId": "api-nonexistent"},
             "configOverrides": {}, "inputMapping": {}},
            {"nodeId": "old-out", "definitionType": "result", "name": "OUT",
             "orderIndex": 1, "config": {}, "configOverrides": {}, "inputMapping": {}},
        ],
        connections=[
            {"id": "c1", "sourceNodeId": "old-api", "targetNodeId": "old-out",
             "sourceHandle": None, "targetHandle": None, "condition": None},
        ],
    )
    r = client.post("/api/v1/blueprint/import", json={"blueprint": bp})
    assert r.status_code == 200, r.text
    wf_id = r.json()["workflowId"]
    await _delete_workflow(wf_id)


@pytest.mark.asyncio
async def test_import_version_mismatch_422():
    """blueprintVersion 메이저가 1 이 아니면 422 + BLUEPRINT_INCOMPATIBLE."""
    bp = _base_blueprint(nodes=[], connections=[])
    bp["blueprintVersion"] = "2.0"
    r = client.post("/api/v1/blueprint/import", json={"blueprint": bp})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "BLUEPRINT_INCOMPATIBLE"


@pytest.mark.asyncio
async def test_import_wrong_kind_422():
    bp = _base_blueprint(nodes=[], connections=[])
    bp["kind"] = "something-else"
    r = client.post("/api/v1/blueprint/import", json={"blueprint": bp})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "BLUEPRINT_INCOMPATIBLE"


@pytest.mark.asyncio
async def test_import_accepts_json_string_blueprint():
    """blueprint 가 JSON 문자열로 붙여넣어져도 처리한다."""
    import json as _json

    bp = _base_blueprint(
        nodes=[
            {"nodeId": "old-start", "definitionType": "form-start", "name": "S",
             "orderIndex": 0, "config": {}, "configOverrides": {}, "inputMapping": {}},
            {"nodeId": "old-out", "definitionType": "result", "name": "OUT",
             "orderIndex": 1, "config": {}, "configOverrides": {}, "inputMapping": {}},
        ],
        connections=[
            {"id": "c1", "sourceNodeId": "old-start", "targetNodeId": "old-out",
             "sourceHandle": None, "targetHandle": None, "condition": None},
        ],
    )
    r = client.post("/api/v1/blueprint/import", json={"blueprint": _json.dumps(bp)})
    assert r.status_code == 200, r.text
    await _delete_workflow(r.json()["workflowId"])


@pytest.mark.asyncio
async def test_import_dry_run_writes_nothing():
    """dryRun=true 는 워크플로우/인스턴스DB 를 만들지 않고 계획만 반환한다."""
    store = get_instance_db_store()
    idb_before = len(await store.list_meta())
    async with async_session_maker() as db:
        wf_before = int((await db.execute(select(func.count(Workflow.id)))).scalar() or 0)

    name = f"dry-idb-{uuid.uuid4().hex[:6]}"
    bp = _base_blueprint(
        nodes=[
            {"nodeId": "old-start", "definitionType": "form-start", "name": "S",
             "orderIndex": 0, "config": {}, "configOverrides": {}, "inputMapping": {}},
            {"nodeId": "old-idb", "definitionType": "instance-db-insert", "name": "IDB",
             "orderIndex": 1, "config": {"instanceDbId": "idb-src",
                                         "snapshotSourceId": "idb-src",
                                         "instanceDbMeta": {"name": name}},
             "configOverrides": {}, "inputMapping": {}},
        ],
        connections=[
            {"id": "c1", "sourceNodeId": "old-start", "targetNodeId": "old-idb",
             "sourceHandle": None, "targetHandle": None, "condition": None},
        ],
        instance_dbs=[
            {"snapshotSourceId": "idb-src", "name": name, "description": "",
             "tags": [], "viewerHints": {}},
        ],
    )
    r = client.post("/api/v1/blueprint/import", json={"blueprint": bp, "dryRun": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "plan" in body
    assert "workflowId" not in body
    assert "reconciliation" in body
    # 계획에 create 액션 + localId None
    plan_idbs = body["plan"]["instanceDbs"]
    assert any(p["action"] == "create" and p["localId"] is None for p in plan_idbs)
    # nodeIdRemap 존재
    assert body["plan"]["nodeIdRemap"]

    # 아무것도 안 만들어짐
    assert len(await store.list_meta()) == idb_before
    async with async_session_maker() as db:
        wf_after = int((await db.execute(select(func.count(Workflow.id)))).scalar() or 0)
    assert wf_after == wf_before


# ════════════════════════════════════════════════════════════════════════════
# PHASE 8 — reconciliation
# ════════════════════════════════════════════════════════════════════════════


def _knowledge_node(node_id: str, categories: List[str], services: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "nodeId": node_id,
        "definitionType": "knowledge",
        "name": "KB",
        "orderIndex": 1,
        "config": {
            "categories": categories,
            "services": services or [],
            "searchField": "input.query",
            "tags": [],
            "pageTypes": [],
            "minScore": 0.0,
            "expandBacklinks": False,
        },
        "configOverrides": {},
        "inputMapping": {},
    }


@pytest.mark.asyncio
async def test_reconciliation_knowledge_satisfied_partial_missing():
    """knowledge 상태가 가용 카테고리 대조로 satisfied/partial/missing 으로 분류된다."""
    from app.api.routes.blueprint import _available_knowledge_facets

    avail_cats, _ = _available_knowledge_facets()
    assert avail_cats, "가용 지식 카테고리가 있어야 의미 있는 테스트"
    present = sorted(avail_cats)[0]
    absent = "확실히-없는-카테고리-zzz"

    bp = _base_blueprint(
        nodes=[
            {"nodeId": "old-start", "definitionType": "form-start", "name": "S",
             "orderIndex": 0, "config": {}, "configOverrides": {}, "inputMapping": {}},
            _knowledge_node("kb-sat", [present]),
            _knowledge_node("kb-part", [present, absent]),
            _knowledge_node("kb-mis", [absent]),
            {"nodeId": "old-out", "definitionType": "result", "name": "OUT",
             "orderIndex": 5, "config": {}, "configOverrides": {}, "inputMapping": {}},
        ],
        connections=[
            {"id": "c1", "sourceNodeId": "old-start", "targetNodeId": "kb-sat",
             "sourceHandle": None, "targetHandle": None, "condition": None},
            {"id": "c2", "sourceNodeId": "kb-sat", "targetNodeId": "kb-part",
             "sourceHandle": None, "targetHandle": None, "condition": None},
            {"id": "c3", "sourceNodeId": "kb-part", "targetNodeId": "kb-mis",
             "sourceHandle": None, "targetHandle": None, "condition": None},
            {"id": "c4", "sourceNodeId": "kb-mis", "targetNodeId": "old-out",
             "sourceHandle": None, "targetHandle": None, "condition": None},
        ],
    )
    r = client.post("/api/v1/blueprint/import", json={"blueprint": bp})
    assert r.status_code == 200, r.text
    wf_id = r.json()["workflowId"]
    try:
        recon = r.json()["reconciliation"]
        summ = recon["summary"]["knowledge"]
        assert summ["satisfied"] == 1
        assert summ["partial"] == 1
        assert summ["missing"] == 1
        statuses = {k["status"] for k in recon["knowledge"]}
        assert statuses == {"satisfied", "partial", "missing"}
    finally:
        await _delete_workflow(wf_id)


@pytest.mark.asyncio
async def test_reconciliation_materials_remapped_to_new_ids():
    """materialsToFill 가 redactedFields 에서 new node id 로 remap 되어 도출된다."""
    bp = _base_blueprint(
        nodes=[
            {"nodeId": "old-api", "definitionType": "api-start", "name": "API",
             "orderIndex": 0, "config": {
                 "apiDefinitionId": "api-original-src",
                 "apiSpecSnapshot": _api_snapshot(),
                 "snapshotSourceId": "api-original-src",
                 "defaultParams": {"owner": ""}},
             "configOverrides": {}, "inputMapping": {}},
            {"nodeId": "old-out", "definitionType": "result", "name": "OUT",
             "orderIndex": 1, "config": {}, "configOverrides": {}, "inputMapping": {}},
        ],
        connections=[
            {"id": "c1", "sourceNodeId": "old-api", "targetNodeId": "old-out",
             "sourceHandle": None, "targetHandle": None, "condition": None},
        ],
        redacted=[
            {"nodeRef": "old-api", "path": "apiSpecSnapshot.authConfig.token", "kind": "authSecret"},
            {"nodeRef": "old-api", "path": "defaultParams.owner", "kind": "envParam"},
            {"nodeRef": "old-api", "path": "apiSpecSnapshot.responseSchema.example", "kind": "trimmedExample"},
        ],
    )
    r = client.post("/api/v1/blueprint/import", json={"blueprint": bp})
    assert r.status_code == 200, r.text
    wf_id = r.json()["workflowId"]
    try:
        recon = r.json()["reconciliation"]
        materials = recon["materialsToFill"]
        # trimmedExample 제외 → 2건
        kinds = {m["kind"] for m in materials}
        assert kinds == {"authSecret", "envParam"}
        # nodeRef 가 새 id (wn-) 로 remap
        new_ids = {m["nodeRef"] for m in materials}
        assert all(nid.startswith("wn-") for nid in new_ids)
        assert "old-api" not in new_ids
        assert recon["summary"]["materialsToFill"] == 2
    finally:
        await _delete_workflow(wf_id)


@pytest.mark.asyncio
async def test_fill_materials_sets_value_no_resnapshot_shrinks_list():
    """fill-materials 가 값을 set + 스냅샷 재동결 안 함 + materialsToFill 축소."""
    bp = _base_blueprint(
        nodes=[
            {"nodeId": "old-api", "definitionType": "api-start", "name": "API",
             "orderIndex": 0, "config": {
                 "apiDefinitionId": "api-original-src",
                 "apiSpecSnapshot": _api_snapshot(url="http://localhost:8001/frozen"),
                 "snapshotSourceId": "api-original-src",
                 "snapshotAt": "2026-01-01T00:00:00",
                 "defaultParams": {"owner": ""}},
             "configOverrides": {}, "inputMapping": {}},
            {"nodeId": "old-out", "definitionType": "result", "name": "OUT",
             "orderIndex": 1, "config": {}, "configOverrides": {}, "inputMapping": {}},
        ],
        connections=[
            {"id": "c1", "sourceNodeId": "old-api", "targetNodeId": "old-out",
             "sourceHandle": None, "targetHandle": None, "condition": None},
        ],
        redacted=[
            {"nodeRef": "old-api", "path": "apiSpecSnapshot.authConfig.token", "kind": "authSecret"},
            {"nodeRef": "old-api", "path": "defaultParams.owner", "kind": "envParam"},
        ],
    )
    r = client.post("/api/v1/blueprint/import", json={"blueprint": bp})
    assert r.status_code == 200, r.text
    wf_id = r.json()["workflowId"]
    try:
        recon = r.json()["reconciliation"]
        api_ref = next(m["nodeRef"] for m in recon["materialsToFill"])
        before_count = recon["summary"]["materialsToFill"]
        assert before_count == 2

        # 동결 스냅샷 기준값 기억
        cfg0 = await _node_config(wf_id, api_ref)
        assert cfg0["apiSpecSnapshot"]["urlTemplate"] == "http://localhost:8001/frozen"
        snap_at0 = cfg0.get("snapshotAt")
        src0 = cfg0.get("snapshotSourceId")

        fill = client.post(
            f"/api/v1/blueprint/workflows/{wf_id}/fill-materials",
            json={"values": [
                {"nodeRef": api_ref, "path": "apiSpecSnapshot.authConfig.token", "value": "my-token"},
                {"nodeRef": api_ref, "path": "defaultParams.owner", "value": "acme"},
            ]},
        )
        assert fill.status_code == 200, fill.text
        fbody = fill.json()
        assert len(fbody["applied"]) == 2

        # 값이 채워졌고 스냅샷은 그대로 (재동결 없음)
        cfg1 = await _node_config(wf_id, api_ref)
        assert cfg1["apiSpecSnapshot"]["authConfig"]["token"] == "my-token"
        assert cfg1["defaultParams"]["owner"] == "acme"
        assert cfg1["apiSpecSnapshot"]["urlTemplate"] == "http://localhost:8001/frozen"
        assert cfg1.get("snapshotAt") == snap_at0  # 재동결 안 됨
        assert cfg1.get("snapshotSourceId") == src0

        # materialsToFill 축소 (2 → 0)
        assert fbody["reconciliation"]["summary"]["materialsToFill"] == 0
    finally:
        await _delete_workflow(wf_id)


@pytest.mark.asyncio
async def test_knowledge_remap_rewrites_config():
    """knowledge-remap 가 knowledge 노드의 category 를 from→to 로 재작성한다."""
    from app.api.routes.blueprint import _available_knowledge_facets

    avail_cats, _ = _available_knowledge_facets()
    target = sorted(avail_cats)[0]
    bad = "잘못된-카테고리-yyy"

    bp = _base_blueprint(
        nodes=[
            {"nodeId": "old-start", "definitionType": "form-start", "name": "S",
             "orderIndex": 0, "config": {}, "configOverrides": {}, "inputMapping": {}},
            _knowledge_node("kb1", [bad]),
            {"nodeId": "old-out", "definitionType": "result", "name": "OUT",
             "orderIndex": 2, "config": {}, "configOverrides": {}, "inputMapping": {}},
        ],
        connections=[
            {"id": "c1", "sourceNodeId": "old-start", "targetNodeId": "kb1",
             "sourceHandle": None, "targetHandle": None, "condition": None},
            {"id": "c2", "sourceNodeId": "kb1", "targetNodeId": "old-out",
             "sourceHandle": None, "targetHandle": None, "condition": None},
        ],
    )
    r = client.post("/api/v1/blueprint/import", json={"blueprint": bp})
    assert r.status_code == 200, r.text
    wf_id = r.json()["workflowId"]
    try:
        recon = r.json()["reconciliation"]
        kb_ref = next(k["nodeRef"] for k in recon["knowledge"])
        assert recon["summary"]["knowledge"]["missing"] == 1

        remap = client.post(
            f"/api/v1/blueprint/workflows/{wf_id}/knowledge-remap",
            json={"remaps": [{"nodeRef": kb_ref, "from": bad, "to": target}]},
        )
        assert remap.status_code == 200, remap.text
        rbody = remap.json()
        assert len(rbody["applied"]) == 1

        cfg = await _node_config(wf_id, kb_ref)
        assert target in cfg["categories"]
        assert bad not in cfg["categories"]
        # 재매핑 후 satisfied
        assert rbody["reconciliation"]["summary"]["knowledge"]["satisfied"] == 1
        assert rbody["reconciliation"]["summary"]["knowledge"]["missing"] == 0
    finally:
        await _delete_workflow(wf_id)


# ════════════════════════════════════════════════════════════════════════════
# E2E — export → import 라운드트립
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_e2e_export_then_import_roundtrip_validates():
    """export 한 워크플로우를 import 하면 검증을 통과하고 스냅샷으로 자급 실행 가능하다."""
    api_id = await _make_api_def(
        url_template="http://localhost:8001/e2e",
        auth_config={"token": "live-secret"},
    )
    ai_id = await _make_ai_node(user_prompt_template="e2e {{input.q}}")
    src_wf = await _make_workflow_raw(
        nodes=[
            {"nodeId": "n_api", "definitionType": "api-start",
             "config": {"apiDefinitionId": api_id, "defaultParams": {"owner": "acme"}}},
            {"nodeId": "n_ai", "definitionType": "ai-custom", "aiNodeId": ai_id, "config": {}},
            {"nodeId": "n_out", "definitionType": "result", "config": {}},
        ],
        connections=[
            {"sourceNodeId": "n_api", "targetNodeId": "n_ai"},
            {"sourceNodeId": "n_ai", "targetNodeId": "n_out"},
        ],
    )
    imported_wf_id = None
    try:
        # export
        ex = client.get(f"/api/v1/blueprint/workflows/{src_wf}")
        assert ex.status_code == 200, ex.text
        bp = ex.json()

        # 라이브 재료 삭제 — import 가 스냅샷-only 로 동작해야 함
        await _delete_api_def(api_id)
        await _delete_ai_node(ai_id)

        # import
        im = client.post("/api/v1/blueprint/import", json={"blueprint": bp})
        assert im.status_code == 200, im.text
        imported_wf_id = im.json()["workflowId"]

        # 검증 통과 + 스냅샷 존재 (자급 실행 가능 형태)
        nodes = await _load_nodes(imported_wf_id)
        api_node = next(n for n in nodes if n.definition_type == "api-start")
        ai_node = next(n for n in nodes if n.definition_type == "ai-custom")
        assert api_node.config["apiSpecSnapshot"]["urlTemplate"] == "http://localhost:8001/e2e"
        assert ai_node.config["aiNodeSnapshot"]["userPromptTemplate"] == "e2e {{input.q}}"

        # 구조 검증 직접 호출 — valid 여야 함 (라이브 재료 없이 스냅샷으로)
        from app.services.workflow_validator import validate_workflow_structure
        async with async_session_maker() as db:
            result = await db.execute(
                select(Workflow)
                .options(selectinload(Workflow.nodes), selectinload(Workflow.connections))
                .where(Workflow.id == imported_wf_id)
            )
            wf = result.scalar_one()
            from app.api.routes.blueprint import _nodes_with_ids, _connections_as_dicts
            v = await validate_workflow_structure(
                _nodes_with_ids(wf), _connections_as_dicts(wf), db
            )
        assert v["valid"], v["errors"]
    finally:
        if imported_wf_id:
            await _delete_workflow(imported_wf_id)
        await _delete_workflow(src_wf)
        await _delete_api_def(api_id)
        await _delete_ai_node(ai_id)
