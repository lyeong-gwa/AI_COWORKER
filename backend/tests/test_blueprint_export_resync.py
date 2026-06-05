"""Self-contained workflow blueprint — Phase 4/5/7 테스트.

검증 범위:
- Phase 4 (backfill): 레거시 워크플로우에 스냅샷 백필 + 멱등 + 재료 누락 스킵.
- Phase 5 (export): 설계도 자급성(api/ai 노드가 스냅샷 보유) + knowledge 선언만(임베딩 X)
  + instanceDb 메타 전용 + auth 시크릿 레닥션 + defaultParams 값 비움 + 버전 스탬프
  + redactedFields 매니페스트 정확성.
- Phase 7 (resync): 변경된 spec 재캡처 + diff 리포트 + 재료 사라짐/no-op + 부분집합 nodeIds
  + dryRun 미저장.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
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
            description=overrides.get("description", "blueprint 테스트"),
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
            description=overrides.get("description", "blueprint 테스트"),
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
    """검증 게이트/스냅샷 임베딩을 우회하고 ORM 으로 직접 워크플로우를 만든다.

    레거시(스냅샷 없는) 상태를 재현하기 위함. config 는 주어진 그대로 저장된다.
    """
    wf_id = f"wf-{uuid.uuid4().hex[:8]}"
    async with async_session_maker() as db:
        wf = Workflow(
            id=wf_id,
            name="blueprint-test-wf",
            description="설계도 테스트용",
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
            .options(selectinload(Workflow.nodes))
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


# ════════════════════════════════════════════════════════════════════════════
# Phase 4 — backfill 스크립트
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_backfill_populates_legacy_workflow():
    """스냅샷 없는 레거시 워크플로우에 backfill 이 스냅샷을 채운다."""
    from scripts.backfill_snapshots import backfill

    api_id = await _make_api_def(url_template="http://localhost:8001/backfill")
    wf_id = await _make_workflow_raw(
        nodes=[
            {"nodeId": "n1", "definitionType": "api-start", "config": {"apiDefinitionId": api_id}},
            {"nodeId": "n2", "definitionType": "result", "config": {}},
        ],
        connections=[{"sourceNodeId": "n1", "targetNodeId": "n2"}],
    )
    try:
        # 사전: 스냅샷 없음
        cfg_before = await _node_config(wf_id, "n1")
        assert "apiSpecSnapshot" not in cfg_before

        totals = await backfill(dry_run=False)
        assert totals["nodes_snapshotted"] >= 1

        cfg_after = await _node_config(wf_id, "n1")
        snap = cfg_after.get("apiSpecSnapshot")
        assert snap is not None
        assert snap["urlTemplate"] == "http://localhost:8001/backfill"
        assert cfg_after["snapshotSourceId"] == api_id
    finally:
        await _delete_workflow(wf_id)
        await _delete_api_def(api_id)


@pytest.mark.asyncio
async def test_backfill_idempotent():
    """backfill 을 두 번 실행해도 두 번째는 변경(persist)이 0 이다 (멱등)."""
    from scripts.backfill_snapshots import backfill

    api_id = await _make_api_def(url_template="http://localhost:8001/idem")
    wf_id = await _make_workflow_raw(
        nodes=[
            {"nodeId": "n1", "definitionType": "api-call", "config": {"apiDefinitionId": api_id}},
            {"nodeId": "n2", "definitionType": "result", "config": {}},
        ],
        connections=[{"sourceNodeId": "n1", "targetNodeId": "n2"}],
    )
    try:
        await backfill(dry_run=False)
        first = await _node_config(wf_id, "n1")

        totals2 = await backfill(dry_run=False)
        # 이 워크플로우의 노드는 이미 동결됨 → 두 번째에서 추가 스냅샷 0
        second = await _node_config(wf_id, "n1")
        assert second == first
        # 멱등 가드: 이미 처리된 노드는 다시 변경되지 않음
        assert second["snapshotAt"] == first["snapshotAt"]
        _ = totals2  # 다른 워크플로우 영향은 무관
    finally:
        await _delete_workflow(wf_id)
        await _delete_api_def(api_id)


@pytest.mark.asyncio
async def test_backfill_skips_missing_material():
    """참조 재료가 없는 노드는 스냅샷 없이 건너뛰고(warn) 예외 없이 진행한다."""
    from scripts.backfill_snapshots import backfill

    wf_id = await _make_workflow_raw(
        nodes=[
            {
                "nodeId": "n1",
                "definitionType": "api-start",
                "config": {"apiDefinitionId": "api-does-not-exist"},
            },
            {"nodeId": "n2", "definitionType": "result", "config": {}},
        ],
        connections=[{"sourceNodeId": "n1", "targetNodeId": "n2"}],
    )
    try:
        totals = await backfill(dry_run=False)
        assert totals["nodes_missing_material"] >= 1
        cfg = await _node_config(wf_id, "n1")
        assert "apiSpecSnapshot" not in cfg  # 스냅샷 미생성
    finally:
        await _delete_workflow(wf_id)


@pytest.mark.asyncio
async def test_backfill_dry_run_persists_nothing():
    """--dry-run 은 변경을 저장하지 않는다."""
    from scripts.backfill_snapshots import backfill

    api_id = await _make_api_def(url_template="http://localhost:8001/dry")
    wf_id = await _make_workflow_raw(
        nodes=[
            {"nodeId": "n1", "definitionType": "api-call", "config": {"apiDefinitionId": api_id}},
            {"nodeId": "n2", "definitionType": "result", "config": {}},
        ],
        connections=[{"sourceNodeId": "n1", "targetNodeId": "n2"}],
    )
    try:
        await backfill(dry_run=True)
        cfg = await _node_config(wf_id, "n1")
        assert "apiSpecSnapshot" not in cfg  # 저장 안 됨
    finally:
        await _delete_workflow(wf_id)
        await _delete_api_def(api_id)


# ════════════════════════════════════════════════════════════════════════════
# Phase 5 — blueprint export
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_export_self_contained_and_redacted():
    """export: api/ai 노드 스냅샷 자급 + auth 레닥션 + defaultParams 비움 + 버전 스탬프."""
    api_id = await _make_api_def(
        url_template="http://localhost:8001/export",
        auth_type="bearer",
        auth_config={"token": "super-secret-xyz"},
        response_schema={
            "fields": [{"field": "id", "type": "int"}],
            "example": {"id": 1, "name": "ok"},
        },
    )
    ai_id = await _make_ai_node(user_prompt_template="설계도 {{input.q}}")
    wf_id = await _make_workflow_raw(
        nodes=[
            {
                "nodeId": "n_api",
                "definitionType": "api-call",
                "config": {
                    "apiDefinitionId": api_id,
                    "defaultParams": {"owner": "acme", "repo": "widget", "token": "ghp_xxx"},
                },
            },
            {
                "nodeId": "n_ai",
                "definitionType": "ai-custom",
                "aiNodeId": ai_id,
                "config": {},
            },
            {"nodeId": "n_out", "definitionType": "result", "config": {}},
        ],
        connections=[
            {"sourceNodeId": "n_api", "targetNodeId": "n_ai"},
            {"sourceNodeId": "n_ai", "targetNodeId": "n_out"},
        ],
    )
    try:
        r = client.get(f"/api/v1/blueprint/workflows/{wf_id}")
        assert r.status_code == 200, r.text
        bp = r.json()

        # 버전 스탬프 + 메타
        assert bp["blueprintVersion"] == "1.0"
        assert bp["kind"] == "workflow-blueprint"
        assert bp["sourceWorkflowId"] == wf_id
        assert bp["exportedAt"]
        # generationTraceIds 는 OMIT
        assert "generationTraceIds" not in bp
        assert "generationTraceIds" not in bp["workflow"]

        nodes_by_ref = {n["nodeId"]: n for n in bp["workflow"]["nodes"]}

        # self-contained: api 노드가 스냅샷을 들고 있다 (export 시 self-heal)
        api_node = nodes_by_ref["n_api"]
        snap = api_node["config"]["apiSpecSnapshot"]
        assert snap["urlTemplate"] == "http://localhost:8001/export"
        # auth 시크릿은 레닥션 (키/authType 유지, 값 비움)
        assert snap["authType"] == "bearer"
        assert snap["authConfig"]["token"] == ""
        # defaultParams 값은 비워지고 키는 placeholder 로 유지
        dp = api_node["config"]["defaultParams"]
        assert set(dp.keys()) == {"owner", "repo", "token"}
        assert all(v == "" for v in dp.values())

        # ai 노드 스냅샷 자급
        ai_node = nodes_by_ref["n_ai"]
        ai_snap = ai_node["config"]["aiNodeSnapshot"]
        assert ai_snap["userPromptTemplate"] == "설계도 {{input.q}}"

        # redactedFields 매니페스트 정확성
        rf = bp["redactedFields"]
        kinds = {(f["nodeRef"], f["path"], f["kind"]) for f in rf}
        assert ("n_api", "apiSpecSnapshot.authConfig.token", "authSecret") in kinds
        assert ("n_api", "defaultParams.owner", "envParam") in kinds
        assert ("n_api", "defaultParams.repo", "envParam") in kinds
        assert ("n_api", "defaultParams.token", "envParam") in kinds

        # 연결(와이어링) 보존
        conns = bp["workflow"]["connections"]
        pairs = {(c["sourceNodeId"], c["targetNodeId"]) for c in conns}
        assert ("n_api", "n_ai") in pairs
        assert ("n_ai", "n_out") in pairs

        return bp  # 보고용
    finally:
        await _delete_workflow(wf_id)
        await _delete_api_def(api_id)
        await _delete_ai_node(ai_id)


@pytest.mark.asyncio
async def test_export_knowledge_declared_not_embedded():
    """knowledge 노드는 의존성으로 '선언'만 되고 본문이 임베딩되지 않는다."""
    wf_id = await _make_workflow_raw(
        nodes=[
            {"nodeId": "n_start", "definitionType": "form-start", "config": {}},
            {
                "nodeId": "n_know",
                "definitionType": "knowledge",
                "config": {
                    "categories": ["운영가이드"],
                    "tags": ["vpn"],
                    "pageTypes": ["Summary"],
                    "services": ["infra"],
                    "searchField": "input.query",
                    "minScore": 0.3,
                    "expandBacklinks": True,
                },
            },
            {"nodeId": "n_out", "definitionType": "result", "config": {}},
        ],
        connections=[
            {"sourceNodeId": "n_start", "targetNodeId": "n_know"},
            {"sourceNodeId": "n_know", "targetNodeId": "n_out"},
        ],
    )
    try:
        r = client.get(f"/api/v1/blueprint/workflows/{wf_id}")
        assert r.status_code == 200, r.text
        bp = r.json()

        deps = bp["dependencies"]["knowledge"]
        assert len(deps) == 1
        kd = deps[0]
        assert kd["nodeRef"] == "n_know"
        assert kd["categories"] == ["운영가이드"]
        assert kd["tags"] == ["vpn"]
        assert kd["pageTypes"] == ["Summary"]
        assert kd["services"] == ["infra"]
        assert kd["searchField"] == "input.query"
        assert kd["minScore"] == 0.3
        assert kd["expandBacklinks"] is True

        # knowledge 노드 config 에 스냅샷 키가 절대 없어야 함 (임베딩 X)
        node = next(n for n in bp["workflow"]["nodes"] if n["nodeId"] == "n_know")
        for k in ("apiSpecSnapshot", "apiSpecSnapshots", "aiNodeSnapshot", "instanceDbMeta"):
            assert k not in node["config"]
    finally:
        await _delete_workflow(wf_id)


@pytest.mark.asyncio
async def test_export_instance_db_meta_only():
    """instanceDb 의존성은 메타(name/description/tags/viewerHints)만 노출."""
    store = get_instance_db_store()
    meta = await store.create_meta(
        name=f"idb-export-{uuid.uuid4().hex[:6]}",
        description="export 메타",
        tags=["t1"],
        viewer_hints={"body": "markdown"},
    )
    idb_id = meta["id"]
    wf_id = await _make_workflow_raw(
        nodes=[
            {"nodeId": "n_start", "definitionType": "form-start", "config": {}},
            {
                "nodeId": "n_idb",
                "definitionType": "instance-db-insert",
                "config": {"instanceDbId": idb_id},
            },
            {"nodeId": "n_out", "definitionType": "result", "config": {}},
        ],
        connections=[
            {"sourceNodeId": "n_start", "targetNodeId": "n_idb"},
            {"sourceNodeId": "n_idb", "targetNodeId": "n_out"},
        ],
    )
    try:
        r = client.get(f"/api/v1/blueprint/workflows/{wf_id}")
        assert r.status_code == 200, r.text
        bp = r.json()

        idbs = bp["dependencies"]["instanceDbs"]
        assert len(idbs) == 1
        dep = idbs[0]
        assert dep["snapshotSourceId"] == idb_id
        assert dep["name"] == meta["name"]
        assert dep["description"] == "export 메타"
        assert dep["tags"] == ["t1"]
        assert dep["viewerHints"] == {"body": "markdown"}
        # 메타만 — records 키 없음
        assert "records" not in dep
    finally:
        await _delete_workflow(wf_id)


@pytest.mark.asyncio
async def test_export_does_not_mutate_stored_workflow():
    """export 의 self-heal 은 저장된 워크플로우를 변경하지 않는다 (read-only)."""
    api_id = await _make_api_def(url_template="http://localhost:8001/ro")
    wf_id = await _make_workflow_raw(
        nodes=[
            {"nodeId": "n1", "definitionType": "api-call", "config": {"apiDefinitionId": api_id}},
            {"nodeId": "n2", "definitionType": "result", "config": {}},
        ],
        connections=[{"sourceNodeId": "n1", "targetNodeId": "n2"}],
    )
    try:
        # export 호출 (self-heal 로 스냅샷 임베딩되지만 persist 안 함)
        r = client.get(f"/api/v1/blueprint/workflows/{wf_id}")
        assert r.status_code == 200
        # 저장된 워크플로우는 여전히 스냅샷 없음 (read-only 보장)
        cfg = await _node_config(wf_id, "n1")
        assert "apiSpecSnapshot" not in cfg
    finally:
        await _delete_workflow(wf_id)
        await _delete_api_def(api_id)


@pytest.mark.asyncio
async def test_export_404_unknown_workflow():
    r = client.get("/api/v1/blueprint/workflows/wf-nope")
    assert r.status_code == 404


def test_redact_trims_large_example_keeps_fields():
    """순수 헬퍼: 큰 responseSchema.example 은 제거(fields 유지)하고 trimmedExample 기록."""
    from app.api.routes.blueprint import redact_blueprint_env_values

    cfg = {
        "apiSpecSnapshot": {
            "urlTemplate": "http://x",
            "authConfig": {"token": "secret"},
            "responseSchema": {
                "fields": [{"field": "a", "type": "str"}],
                "example": {"blob": "z" * 5000},
            },
        }
    }
    out, redactions = redact_blueprint_env_values(cfg)
    resp = out["apiSpecSnapshot"]["responseSchema"]
    assert "example" not in resp
    assert "fields" in resp  # 구조(fields)는 유지
    kinds = {(r["path"], r["kind"]) for r in redactions}
    assert ("apiSpecSnapshot.responseSchema.example", "trimmedExample") in kinds
    # 원본 비변형
    assert cfg["apiSpecSnapshot"]["responseSchema"]["example"] == {"blob": "z" * 5000}
    assert cfg["apiSpecSnapshot"]["authConfig"]["token"] == "secret"


def test_redact_router_apispec_snapshots_auth():
    """순수 헬퍼: apiSpecSnapshots[] (router) 의 authConfig 도 레닥션."""
    from app.api.routes.blueprint import redact_blueprint_env_values

    cfg = {
        "apiSpecSnapshots": [
            {"urlTemplate": "http://a", "authConfig": {"token": "s1"}},
            {"urlTemplate": "http://b", "authConfig": {"token": "s2"}},
        ]
    }
    out, redactions = redact_blueprint_env_values(cfg)
    assert out["apiSpecSnapshots"][0]["authConfig"]["token"] == ""
    assert out["apiSpecSnapshots"][1]["authConfig"]["token"] == ""
    paths = {r["path"] for r in redactions if r["kind"] == "authSecret"}
    assert "apiSpecSnapshots[0].authConfig.token" in paths
    assert "apiSpecSnapshots[1].authConfig.token" in paths


# ════════════════════════════════════════════════════════════════════════════
# 헤더 시크릿 레닥션 (headerSecret) 테스트
# ════════════════════════════════════════════════════════════════════════════


def test_redact_sensitive_header_values_blanked_and_recorded():
    """Authorization / X-Api-Key 등 민감 헤더 값은 빈 문자열로 + headerSecret 기록."""
    from app.api.routes.blueprint import redact_blueprint_env_values

    cfg = {
        "apiSpecSnapshot": {
            "urlTemplate": "http://x",
            "authConfig": {},
            "headers": {
                "Authorization": "Bearer TOK123",
                "X-Api-Key": "LEAKED_KEY",
                "Content-Type": "application/json",  # 비민감 — 보존해야 함
            },
        }
    }
    out, redactions = redact_blueprint_env_values(cfg)

    snap_headers = out["apiSpecSnapshot"]["headers"]
    # 민감 헤더 값 → 빈 문자열 (키는 유지)
    assert snap_headers["Authorization"] == ""
    assert snap_headers["X-Api-Key"] == ""
    # 비민감 헤더는 그대로
    assert snap_headers["Content-Type"] == "application/json"

    kinds = {(r["path"], r["kind"]) for r in redactions}
    assert ("apiSpecSnapshot.headers.Authorization", "headerSecret") in kinds
    assert ("apiSpecSnapshot.headers.X-Api-Key", "headerSecret") in kinds
    # Content-Type 은 기록 안 됨
    assert ("apiSpecSnapshot.headers.Content-Type", "headerSecret") not in kinds

    # 원본 비변형
    assert cfg["apiSpecSnapshot"]["headers"]["Authorization"] == "Bearer TOK123"
    assert cfg["apiSpecSnapshot"]["headers"]["X-Api-Key"] == "LEAKED_KEY"


def test_redact_placeholder_only_header_preserved():
    """순수 플레이스홀더({{var}}) 헤더 값은 레닥션하지 않는다 (런타임 파라미터 참조)."""
    from app.api.routes.blueprint import redact_blueprint_env_values

    cfg = {
        "apiSpecSnapshot": {
            "urlTemplate": "http://x",
            "authConfig": {},
            "headers": {
                "Authorization": "{{input.token}}",   # 순수 플레이스홀더 → 보존
                "X-Api-Key": "{apiKey}",               # 중괄호 단일 형태 → 보존
                "X-Secret-Token": "literal-secret-abc123",  # 리터럴 → 레닥션
            },
        }
    }
    out, redactions = redact_blueprint_env_values(cfg)

    snap_headers = out["apiSpecSnapshot"]["headers"]
    # 플레이스홀더는 그대로
    assert snap_headers["Authorization"] == "{{input.token}}"
    assert snap_headers["X-Api-Key"] == "{apiKey}"
    # 리터럴은 빈 문자열
    assert snap_headers["X-Secret-Token"] == ""

    paths_with_kind = {(r["path"], r["kind"]) for r in redactions}
    assert ("apiSpecSnapshot.headers.Authorization", "headerSecret") not in paths_with_kind
    assert ("apiSpecSnapshot.headers.X-Api-Key", "headerSecret") not in paths_with_kind
    assert ("apiSpecSnapshot.headers.X-Secret-Token", "headerSecret") in paths_with_kind


def test_redact_router_snapshots_sensitive_headers():
    """apiSpecSnapshots[] 배열의 민감 헤더도 레닥션된다."""
    from app.api.routes.blueprint import redact_blueprint_env_values

    cfg = {
        "apiSpecSnapshots": [
            {
                "urlTemplate": "http://a",
                "authConfig": {},
                "headers": {"Authorization": "Bearer SECR", "Accept": "application/json"},
            },
        ]
    }
    out, redactions = redact_blueprint_env_values(cfg)

    assert out["apiSpecSnapshots"][0]["headers"]["Authorization"] == ""
    assert out["apiSpecSnapshots"][0]["headers"]["Accept"] == "application/json"

    paths = {r["path"] for r in redactions if r["kind"] == "headerSecret"}
    assert "apiSpecSnapshots[0].headers.Authorization" in paths


# ════════════════════════════════════════════════════════════════════════════
# bodyTemplate / urlTemplate 시크릿 경고 (possibleSecretLiteral) 테스트
# ════════════════════════════════════════════════════════════════════════════


def test_redact_body_template_literal_token_warns_not_blanked():
    """bodyTemplate 에 Bearer 리터럴 토큰이 있으면 possibleSecretLiteral 경고 — 값은 유지."""
    from app.api.routes.blueprint import redact_blueprint_env_values

    body_with_secret = '{"Authorization": "Bearer ghp_realtoken1234567890"}'
    cfg = {
        "apiSpecSnapshot": {
            "urlTemplate": "http://x",
            "authConfig": {},
            "bodyTemplate": body_with_secret,
        }
    }
    out, redactions = redact_blueprint_env_values(cfg)

    # 값은 절대 변경하지 않음 (구조 보존)
    assert out["apiSpecSnapshot"]["bodyTemplate"] == body_with_secret

    kinds = {(r["path"], r["kind"]) for r in redactions}
    assert ("apiSpecSnapshot.bodyTemplate", "possibleSecretLiteral") in kinds

    # 경고 메시지도 포함되어야 함
    warn_entries = [r for r in redactions if r.get("kind") == "possibleSecretLiteral"]
    assert warn_entries
    assert "authConfig" in warn_entries[0].get("warning", "")


def test_redact_url_template_api_key_querystring_warns():
    """urlTemplate 쿼리스트링에 api_key=SECRET 형태가 있으면 possibleSecretLiteral 경고."""
    from app.api.routes.blueprint import redact_blueprint_env_values

    url_with_secret = "http://api.example.com/data?api_key=supersecret12345678"
    cfg = {
        "apiSpecSnapshot": {
            "urlTemplate": url_with_secret,
            "authConfig": {},
        }
    }
    out, redactions = redact_blueprint_env_values(cfg)

    # 값 변경 없음
    assert out["apiSpecSnapshot"]["urlTemplate"] == url_with_secret

    kinds = {(r["path"], r["kind"]) for r in redactions}
    assert ("apiSpecSnapshot.urlTemplate", "possibleSecretLiteral") in kinds


def test_redact_normal_placeholder_url_not_warned():
    """{{var}} 플레이스홀더만 있는 urlTemplate / bodyTemplate 은 경고 없음."""
    from app.api.routes.blueprint import redact_blueprint_env_values

    cfg = {
        "apiSpecSnapshot": {
            "urlTemplate": "http://api.example.com/repos/{{owner}}/{{repo}}/issues",
            "authConfig": {},
            "bodyTemplate": '{"query": "{{input.q}}", "limit": {{input.limit}}}',
        }
    }
    out, redactions = redact_blueprint_env_values(cfg)

    kinds = [r["kind"] for r in redactions]
    assert "possibleSecretLiteral" not in kinds

    # 값 그대로
    assert "{{owner}}" in out["apiSpecSnapshot"]["urlTemplate"]
    assert "{{input.q}}" in out["apiSpecSnapshot"]["bodyTemplate"]


# ════════════════════════════════════════════════════════════════════════════
# materialsToFill 포함/제외 — reconciliation 매핑 검증
# ════════════════════════════════════════════════════════════════════════════


def test_build_reconciliation_header_secret_in_materials_to_fill():
    """headerSecret 는 materialsToFill 에 포함, possibleSecretLiteral 는 제외."""
    from app.api.routes.blueprint import _build_reconciliation

    redacted_fields = [
        {"nodeRef": "n1", "path": "apiSpecSnapshot.authConfig.token", "kind": "authSecret"},
        {"nodeRef": "n1", "path": "apiSpecSnapshot.headers.Authorization", "kind": "headerSecret"},
        {"nodeRef": "n1", "path": "apiSpecSnapshot.bodyTemplate", "kind": "possibleSecretLiteral",
         "warning": "경고"},
        {"nodeRef": "n1", "path": "apiSpecSnapshot.urlTemplate", "kind": "possibleSecretLiteral",
         "warning": "경고"},
        {"nodeRef": "n1", "path": "apiSpecSnapshot.responseSchema.example", "kind": "trimmedExample"},
        {"nodeRef": "n1", "path": "defaultParams.owner", "kind": "envParam"},
    ]

    recon = _build_reconciliation(
        nodes=[],  # knowledge 없음
        redacted_fields=redacted_fields,
        old_to_new={},  # 항등 — nodeRef 변경 없음
    )

    materials = recon["materialsToFill"]
    fill_kinds = {m["kind"] for m in materials}

    # 포함 대상
    assert "authSecret" in fill_kinds
    assert "headerSecret" in fill_kinds
    assert "envParam" in fill_kinds

    # 제외 대상
    assert "trimmedExample" not in fill_kinds
    assert "possibleSecretLiteral" not in fill_kinds

    # 개수 확인: authSecret(1) + headerSecret(1) + envParam(1) = 3
    assert len(materials) == 3


# ════════════════════════════════════════════════════════════════════════════
# Phase 7 — resync 엔드포인트
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_resync_refreshes_changed_spec():
    """라이브 spec 이 바뀌면 resync 가 강제로 재캡처하고 diff 를 보고한다."""
    from scripts.backfill_snapshots import backfill

    api_id = await _make_api_def(url_template="http://localhost:8001/v1")
    wf_id = await _make_workflow_raw(
        nodes=[
            {"nodeId": "n1", "definitionType": "api-call", "config": {"apiDefinitionId": api_id}},
            {"nodeId": "n2", "definitionType": "result", "config": {}},
        ],
        connections=[{"sourceNodeId": "n1", "targetNodeId": "n2"}],
    )
    try:
        # 최초 동결
        await backfill(dry_run=False)
        cfg0 = await _node_config(wf_id, "n1")
        assert cfg0["apiSpecSnapshot"]["urlTemplate"] == "http://localhost:8001/v1"

        # 라이브 spec 변경 (같은 id)
        await _delete_api_def(api_id)
        await _make_api_def(id=api_id, url_template="http://localhost:8001/v2-NEW")

        r = client.post(f"/api/v1/workflows/{wf_id}/resync-snapshots", json={})
        assert r.status_code == 200, r.text
        report = r.json()
        assert report["changedCount"] == 1
        n1_report = next(n for n in report["nodes"] if n["nodeId"] == "n1")
        assert n1_report["changed"] is True
        assert "apiSpecSnapshot" in n1_report["changedFields"]

        # 저장 확인 — 스냅샷이 v2 로 갱신됨
        cfg1 = await _node_config(wf_id, "n1")
        assert cfg1["apiSpecSnapshot"]["urlTemplate"] == "http://localhost:8001/v2-NEW"
    finally:
        await _delete_workflow(wf_id)
        await _delete_api_def(api_id)


@pytest.mark.asyncio
async def test_resync_noop_when_spec_unchanged():
    """spec 이 동일하면 resync 는 변경 없음(no-op)으로 보고하고 unsyncable 아님."""
    from scripts.backfill_snapshots import backfill

    api_id = await _make_api_def(url_template="http://localhost:8001/same")
    wf_id = await _make_workflow_raw(
        nodes=[
            {"nodeId": "n1", "definitionType": "api-call", "config": {"apiDefinitionId": api_id}},
            {"nodeId": "n2", "definitionType": "result", "config": {}},
        ],
        connections=[{"sourceNodeId": "n1", "targetNodeId": "n2"}],
    )
    try:
        await backfill(dry_run=False)
        r = client.post(f"/api/v1/workflows/{wf_id}/resync-snapshots", json={})
        assert r.status_code == 200, r.text
        report = r.json()
        n1 = next(n for n in report["nodes"] if n["nodeId"] == "n1")
        assert n1["changed"] is False
        assert n1["changedFields"] == []
        assert "unsyncable" not in n1
    finally:
        await _delete_workflow(wf_id)
        await _delete_api_def(api_id)


@pytest.mark.asyncio
async def test_resync_unsyncable_when_material_gone():
    """라이브 재료가 사라지면 unsyncable 로 보고하고 기존 스냅샷은 보존."""
    from scripts.backfill_snapshots import backfill

    api_id = await _make_api_def(url_template="http://localhost:8001/gone")
    wf_id = await _make_workflow_raw(
        nodes=[
            {"nodeId": "n1", "definitionType": "api-call", "config": {"apiDefinitionId": api_id}},
            {"nodeId": "n2", "definitionType": "result", "config": {}},
        ],
        connections=[{"sourceNodeId": "n1", "targetNodeId": "n2"}],
    )
    try:
        await backfill(dry_run=False)
        # 라이브 재료 삭제
        await _delete_api_def(api_id)

        r = client.post(f"/api/v1/workflows/{wf_id}/resync-snapshots", json={})
        assert r.status_code == 200, r.text
        report = r.json()
        n1 = next(n for n in report["nodes"] if n["nodeId"] == "n1")
        assert n1["changed"] is False
        assert n1.get("unsyncable") is True
        assert n1["reason"] == "no live material"

        # 기존 스냅샷 보존
        cfg = await _node_config(wf_id, "n1")
        assert cfg["apiSpecSnapshot"]["urlTemplate"] == "http://localhost:8001/gone"
    finally:
        await _delete_workflow(wf_id)


@pytest.mark.asyncio
async def test_resync_subset_node_ids():
    """nodeIds 부분집합 지정 시 해당 노드만 재동기화 대상."""
    from scripts.backfill_snapshots import backfill

    api_a = await _make_api_def(url_template="http://localhost:8001/A1")
    api_b = await _make_api_def(url_template="http://localhost:8001/B1")
    wf_id = await _make_workflow_raw(
        nodes=[
            {"nodeId": "nA", "definitionType": "api-start", "config": {"apiDefinitionId": api_a}},
            {"nodeId": "nB", "definitionType": "api-call", "config": {"apiDefinitionId": api_b}},
            {"nodeId": "nOut", "definitionType": "result", "config": {}},
        ],
        connections=[
            {"sourceNodeId": "nA", "targetNodeId": "nB"},
            {"sourceNodeId": "nB", "targetNodeId": "nOut"},
        ],
    )
    try:
        await backfill(dry_run=False)
        # 두 API 모두 변경
        await _delete_api_def(api_a)
        await _make_api_def(id=api_a, url_template="http://localhost:8001/A2")
        await _delete_api_def(api_b)
        await _make_api_def(id=api_b, url_template="http://localhost:8001/B2")

        # nA 만 대상
        r = client.post(
            f"/api/v1/workflows/{wf_id}/resync-snapshots", json={"nodeIds": ["nA"]}
        )
        assert r.status_code == 200, r.text
        report = r.json()
        assert report["targetCount"] == 1
        refs = {n["nodeId"] for n in report["nodes"]}
        assert refs == {"nA"}

        # nA 는 갱신, nB 는 freeze-once 보존
        cfg_a = await _node_config(wf_id, "nA")
        cfg_b = await _node_config(wf_id, "nB")
        assert cfg_a["apiSpecSnapshot"]["urlTemplate"] == "http://localhost:8001/A2"
        assert cfg_b["apiSpecSnapshot"]["urlTemplate"] == "http://localhost:8001/B1"  # 그대로
    finally:
        await _delete_workflow(wf_id)
        await _delete_api_def(api_a)
        await _delete_api_def(api_b)


@pytest.mark.asyncio
async def test_resync_dry_run_writes_nothing():
    """dryRun=true 는 diff 를 보고하지만 저장하지 않는다."""
    from scripts.backfill_snapshots import backfill

    api_id = await _make_api_def(url_template="http://localhost:8001/dryv1")
    wf_id = await _make_workflow_raw(
        nodes=[
            {"nodeId": "n1", "definitionType": "api-call", "config": {"apiDefinitionId": api_id}},
            {"nodeId": "n2", "definitionType": "result", "config": {}},
        ],
        connections=[{"sourceNodeId": "n1", "targetNodeId": "n2"}],
    )
    try:
        await backfill(dry_run=False)
        await _delete_api_def(api_id)
        await _make_api_def(id=api_id, url_template="http://localhost:8001/dryv2")

        r = client.post(
            f"/api/v1/workflows/{wf_id}/resync-snapshots", json={"dryRun": True}
        )
        assert r.status_code == 200, r.text
        report = r.json()
        assert report["dryRun"] is True
        n1 = next(n for n in report["nodes"] if n["nodeId"] == "n1")
        assert n1["changed"] is True  # diff 는 보고됨

        # 저장은 안 됨 — 여전히 v1
        cfg = await _node_config(wf_id, "n1")
        assert cfg["apiSpecSnapshot"]["urlTemplate"] == "http://localhost:8001/dryv1"
    finally:
        await _delete_workflow(wf_id)
        await _delete_api_def(api_id)
