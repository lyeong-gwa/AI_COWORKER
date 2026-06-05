"""Self-contained workflow blueprint — 스냅샷 인프라 테스트 (Phase 1-3).

검증 범위:
- Phase 1: 생성 시 스냅샷 임베딩, freeze-once(보존/재캡처), 누락 재료 무예외,
           인스턴스DB 메타 전용(레코드 없음).
- Phase 2: 각 핸들러가 라이브 재료 삭제 후에도 스냅샷으로 실행, ai-custom 우선순위.
- Phase 3: E7 — apiSpecSnapshot 있으면 라이브 def 없어도 통과, instanceDbId 는 여전히 엄격.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from app.core.database import async_session_maker
from app.models.api_definition import ApiDefinition
from app.models.node import AINode
from app.nodes.base import ExecutionContext
from app.services.blueprint_snapshot import (
    embed_snapshots_into_nodes,
    snapshot_api_def,
    snapshot_ai_node,
    snapshot_ai_router_apis,
    snapshot_instance_db_meta,
)
from app.services.instance_db_store import get_instance_db_store


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────


def _node(
    def_type: str,
    config: Optional[Dict[str, Any]] = None,
    ai_node_id: Optional[str] = None,
) -> SimpleNamespace:
    """embed_snapshots_into_nodes 가 보는 노드의 최소 attribute."""
    return SimpleNamespace(
        id=f"n-{uuid.uuid4().hex[:6]}",
        definitionType=def_type,
        definition_type=def_type,
        aiNodeId=ai_node_id,
        ai_node_id=ai_node_id,
        config=config or {},
    )


async def _make_api_def(**overrides: Any) -> str:
    api_id = overrides.pop("id", None) or f"api-{uuid.uuid4().hex[:8]}"
    async with async_session_maker() as db:
        api_def = ApiDefinition(
            id=api_id,
            name=overrides.get("name", "테스트 API"),
            description=overrides.get("description", "snapshot 테스트"),
            method=overrides.get("method", "GET"),
            url_template=overrides.get("url_template", "http://localhost:8001/test"),
            headers=overrides.get("headers", {"X-Trace": "1"}),
            body_template=overrides.get("body_template"),
            auth_type=overrides.get("auth_type", "bearer"),
            auth_config=overrides.get("auth_config", {"token": "secret-token"}),
            parameters=overrides.get("parameters", []),
            response_schema=overrides.get("response_schema", {}),
            tags=[],
        )
        db.add(api_def)
        await db.commit()
    return api_id


async def _delete_api_def(api_id: str) -> None:
    from sqlalchemy import delete

    async with async_session_maker() as db:
        await db.execute(delete(ApiDefinition).where(ApiDefinition.id == api_id))
        await db.commit()


async def _make_ai_node(**overrides: Any) -> str:
    node_id = overrides.pop("id", None) or f"ai-{uuid.uuid4().hex[:8]}"
    async with async_session_maker() as db:
        ai_node = AINode(
            id=node_id,
            name=overrides.get("name", "테스트 AI 노드"),
            description=overrides.get("description", "snapshot 테스트"),
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
    from sqlalchemy import delete

    async with async_session_maker() as db:
        await db.execute(delete(AINode).where(AINode.id == node_id))
        await db.commit()


async def _embed(nodes: List[Any]) -> List[Any]:
    async with async_session_maker() as db:
        return await embed_snapshots_into_nodes(db, nodes)


# ── 더미 httpx 클라이언트 (실제 네트워크 호출 방지) ───────────────────────────


class _DummyResponse:
    def __init__(self, payload: Any, status: int = 200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def json(self) -> Any:
        return self._payload


class _DummyClient:
    """httpx.AsyncClient 대체 — 요청 인자를 캡처하고 더미 응답 반환."""

    captured: Dict[str, Any] = {}

    def __init__(self, *args: Any, **kwargs: Any):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args: Any):
        return False

    async def request(self, **kwargs: Any) -> _DummyResponse:
        type(self).captured = dict(kwargs)
        return _DummyResponse({"ok": True})


# ════════════════════════════════════════════════════════════════════════════
# Phase 1 — 스냅샷 임베딩 + freeze-once
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_snapshot_embedded_on_create():
    """api-call 노드 생성 시 apiSpecSnapshot 이 config 에 임베딩된다(시크릿 포함)."""
    api_id = await _make_api_def()
    try:
        node = _node("api-call", {"apiDefinitionId": api_id})
        await _embed([node])

        snap = node.config.get("apiSpecSnapshot")
        assert snap is not None
        assert snap["urlTemplate"] == "http://localhost:8001/test"
        assert snap["method"] == "GET"
        # 전체 스펙(시크릿 포함)
        assert snap["authType"] == "bearer"
        assert snap["authConfig"]["token"] == "secret-token"
        assert node.config["snapshotSourceId"] == api_id
        assert node.config.get("snapshotAt")
    finally:
        await _delete_api_def(api_id)


@pytest.mark.asyncio
async def test_freeze_once_preserved_on_second_save_same_ref():
    """같은 참조 id 로 두 번째 저장 시 스냅샷이 보존된다(라이브 변경 무시)."""
    api_id = await _make_api_def(url_template="http://localhost:8001/v1")
    try:
        node = _node("api-call", {"apiDefinitionId": api_id})
        await _embed([node])
        first_snap = dict(node.config["apiSpecSnapshot"])
        first_at = node.config["snapshotAt"]

        # 라이브 재료를 바꿔도 (id 동일) 보존되어야 함
        await _delete_api_def(api_id)
        await _make_api_def(id=api_id, url_template="http://localhost:8001/v2-CHANGED")

        await _embed([node])
        assert node.config["apiSpecSnapshot"] == first_snap
        assert node.config["apiSpecSnapshot"]["urlTemplate"] == "http://localhost:8001/v1"
        assert node.config["snapshotAt"] == first_at  # 갱신 안 됨
    finally:
        await _delete_api_def(api_id)


@pytest.mark.asyncio
async def test_freeze_once_resnapshot_on_ref_change():
    """참조 id 가 바뀌면 새 재료로 재캡처된다."""
    api_a = await _make_api_def(url_template="http://localhost:8001/A")
    api_b = await _make_api_def(url_template="http://localhost:8001/B")
    try:
        node = _node("api-call", {"apiDefinitionId": api_a})
        await _embed([node])
        assert node.config["apiSpecSnapshot"]["urlTemplate"] == "http://localhost:8001/A"
        assert node.config["snapshotSourceId"] == api_a

        # 노드가 다른 재료를 가리키도록 변경
        node.config["apiDefinitionId"] = api_b
        await _embed([node])
        assert node.config["apiSpecSnapshot"]["urlTemplate"] == "http://localhost:8001/B"
        assert node.config["snapshotSourceId"] == api_b
    finally:
        await _delete_api_def(api_a)
        await _delete_api_def(api_b)


@pytest.mark.asyncio
async def test_missing_material_does_not_raise():
    """참조 재료가 존재하지 않아도 예외 없이 건너뛴다(스냅샷 키 미생성)."""
    node = _node("api-call", {"apiDefinitionId": "api-nonexistent"})
    await _embed([node])  # 예외 없어야 함
    assert "apiSpecSnapshot" not in node.config


@pytest.mark.asyncio
async def test_embed_idempotent_only_touches_snapshot_keys():
    """멱등 + 스냅샷 키 외 다른 config 키는 건드리지 않는다."""
    api_id = await _make_api_def()
    try:
        node = _node(
            "api-call",
            {"apiDefinitionId": api_id, "defaultParams": {"q": "keep-me"}, "customKey": 42},
        )
        await _embed([node])
        await _embed([node])  # 두 번째 호출 — 멱등
        assert node.config["defaultParams"] == {"q": "keep-me"}
        assert node.config["customKey"] == 42
        assert node.config.get("apiSpecSnapshot") is not None
    finally:
        await _delete_api_def(api_id)


@pytest.mark.asyncio
async def test_instance_db_meta_only_no_records():
    """instance-db 노드는 메타만 임베딩(레코드 없음)하고, 런타임 키는 instanceDbId 유지."""
    store = get_instance_db_store()
    meta = await store.create_meta(
        name=f"idb-{uuid.uuid4().hex[:6]}",
        description="메타 전용",
        tags=["t1"],
        viewer_hints={"body": "markdown"},
    )
    idb_id = meta["id"]

    node = _node("instance-db-insert", {"instanceDbId": idb_id})
    await _embed([node])

    embedded = node.config.get("instanceDbMeta")
    assert embedded is not None
    assert embedded["name"] == meta["name"]
    assert embedded["description"] == "메타 전용"
    assert embedded["tags"] == ["t1"]
    assert embedded["viewerHints"] == {"body": "markdown"}
    # 메타만 — 레코드 데이터 키가 섞이지 않아야 함
    assert "records" not in embedded
    # 런타임 참조는 여전히 instanceDbId
    assert node.config["instanceDbId"] == idb_id


@pytest.mark.asyncio
async def test_router_snapshot_selected_ids():
    """ai-api-router 는 선택된 apiIds 만 스냅샷한다."""
    api_a = await _make_api_def(url_template="http://localhost:8001/RA")
    api_b = await _make_api_def(url_template="http://localhost:8001/RB")
    api_c = await _make_api_def(url_template="http://localhost:8001/RC")
    try:
        node = _node("ai-api-router", {"apiIds": [api_a, api_c]})
        await _embed([node])
        snaps = node.config.get("apiSpecSnapshots")
        assert snaps is not None
        urls = {s["urlTemplate"] for s in snaps}
        assert urls == {"http://localhost:8001/RA", "http://localhost:8001/RC"}
        assert node.config["snapshotSourceId"] == ",".join(sorted([api_a, api_c]))
    finally:
        await _delete_api_def(api_a)
        await _delete_api_def(api_b)
        await _delete_api_def(api_c)


@pytest.mark.asyncio
async def test_router_snapshot_all_active_when_no_ids():
    """apiIds 없으면 현재 활성 API 전체를 스냅샷한다."""
    api_id = await _make_api_def(url_template="http://localhost:8001/ALL")
    try:
        node = _node("ai-api-router", {})
        snaps = await snapshot_ai_router_apis_via_embed(node)
        assert any(s["urlTemplate"] == "http://localhost:8001/ALL" for s in snaps)
        assert node.config["snapshotSourceId"] == "*active"
    finally:
        await _delete_api_def(api_id)


async def snapshot_ai_router_apis_via_embed(node: Any) -> List[Dict[str, Any]]:
    await _embed([node])
    return node.config.get("apiSpecSnapshots") or []


@pytest.mark.asyncio
async def test_knowledge_never_snapshotted():
    """knowledge 노드는 스냅샷 대상이 아니다(어떤 스냅샷 키도 안 붙음)."""
    node = _node("knowledge", {"knowledgeDocIds": ["doc-1"]})
    await _embed([node])
    assert "apiSpecSnapshot" not in node.config
    assert "apiSpecSnapshots" not in node.config
    assert "aiNodeSnapshot" not in node.config
    assert "instanceDbMeta" not in node.config


# ── 단건 스냅샷 함수 직접 검증 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_snapshot_functions_missing_return_none():
    async with async_session_maker() as db:
        assert await snapshot_api_def(db, "api-nope") is None
        assert await snapshot_ai_node(db, "ai-nope") is None
    assert await snapshot_instance_db_meta("idb-nope") is None


# ════════════════════════════════════════════════════════════════════════════
# Phase 2 — 핸들러 snapshot-first (라이브 재료 삭제 후에도 실행)
# ════════════════════════════════════════════════════════════════════════════


def _ctx() -> ExecutionContext:
    from app.services.tool_executor import render_template

    return ExecutionContext(
        db=None,
        execution_id="exec-test",
        node_id="n-test",
        render_template=render_template,
    )


@pytest.mark.asyncio
async def test_api_call_handler_uses_snapshot_when_live_deleted(monkeypatch):
    """api-call: 라이브 def 삭제 후에도 스냅샷으로 호출한다."""
    import app.nodes.action.api_call as mod

    api_id = await _make_api_def(url_template="http://localhost:8001/snap-call")
    node = _node("api-call", {"apiDefinitionId": api_id})
    await _embed([node])
    await _delete_api_def(api_id)  # 라이브 삭제

    monkeypatch.setattr(mod.httpx, "AsyncClient", _DummyClient)
    handler = mod.ApiCallHandler()
    result = await handler.execute(node, {}, _ctx())
    assert result["status"] == 200
    assert _DummyClient.captured["url"].startswith("http://localhost:8001/snap-call")
    # 시크릿(bearer) 도 스냅샷에서 복원되어 헤더로 적용됨
    assert _DummyClient.captured["headers"].get("Authorization") == "Bearer secret-token"


@pytest.mark.asyncio
async def test_api_start_handler_uses_snapshot_when_live_deleted(monkeypatch):
    """api-start: 라이브 def 삭제 후에도 스냅샷으로 호출한다."""
    import app.nodes.triggers.api_start as mod

    api_id = await _make_api_def(url_template="http://localhost:8001/snap-start")
    node = _node("api-start", {"apiDefinitionId": api_id})
    await _embed([node])
    await _delete_api_def(api_id)

    monkeypatch.setattr(mod.httpx, "AsyncClient", _DummyClient)
    handler = mod.ApiStartHandler()
    result = await handler.execute(node, {}, _ctx())
    assert result["status"] == 200
    assert _DummyClient.captured["url"].startswith("http://localhost:8001/snap-start")


@pytest.mark.asyncio
async def test_api_call_handler_malformed_snapshot_raises(monkeypatch):
    """불완전한 스냅샷(필수 urlTemplate 누락)은 ValueError — 조용한 fallback 금지."""
    import app.nodes.action.api_call as mod

    node = _node("api-call", {"apiSpecSnapshot": {"method": "GET"}})  # urlTemplate 없음
    monkeypatch.setattr(mod.httpx, "AsyncClient", _DummyClient)
    handler = mod.ApiCallHandler()
    with pytest.raises(ValueError):
        await handler.execute(node, {}, _ctx())


@pytest.mark.asyncio
async def test_ai_api_router_handler_uses_snapshot_when_live_deleted(monkeypatch):
    """ai-api-router: 라이브 def 삭제 후에도 apiSpecSnapshots 로 카탈로그 구성·호출."""
    import app.nodes.ai.ai_api_router as mod

    api_id = await _make_api_def(
        name="라우터API",
        url_template="http://localhost:8001/router/{{q}}",
        method="GET",
    )
    node = _node("ai-api-router", {"apiIds": [api_id], "prompt": "분석"})
    await _embed([node])
    await _delete_api_def(api_id)  # 라이브 삭제

    # LLM 이 해당 API 호출을 결정하도록 모킹
    async def _fake_chat(**kwargs: Any):
        return SimpleNamespace(
            content=(
                '{"shouldCall": true, "reason": "ok", '
                f'"apiId": "{api_id}", "parameters": {{"q": "hi"}}}}'
            )
        )

    monkeypatch.setattr(mod, "chat", _fake_chat)
    monkeypatch.setattr(mod.httpx, "AsyncClient", _DummyClient)

    handler = mod.AiApiRouterHandler()
    result = await handler.execute(node, {"q": "hi"}, _ctx())
    route = result["api_route"]
    assert route["called"] is True
    assert route["apiId"] == api_id
    assert route["apiName"] == "라우터API"
    assert _DummyClient.captured["url"].startswith("http://localhost:8001/router/")


@pytest.mark.asyncio
async def test_ai_custom_snapshot_priority(monkeypatch):
    """ai-custom 우선순위: aiNodeSnapshot > 라이브 AINode > config.prompt.

    스냅샷이 있으면 라이브 노드가 삭제되어도 스냅샷의 transient AINode 로 실행한다.
    """
    import app.nodes.ai.ai_custom as mod

    ai_id = await _make_ai_node(user_prompt_template="SNAP: {{input.x}}")
    node = SimpleNamespace(
        id="n-aic",
        definitionType="ai-custom",
        definition_type="ai-custom",
        aiNodeId=ai_id,
        ai_node_id=ai_id,
        config={},
    )
    await _embed([node])
    await _delete_ai_node(ai_id)  # 라이브 삭제

    captured: Dict[str, Any] = {}

    async def _fake_execute_node(node, input_data, db):  # noqa: A002
        captured["node"] = node
        captured["input"] = input_data
        return SimpleNamespace(success=True, output={"response": "from-snapshot"}, error=None)

    # execute_node 는 ai_custom 내부에서 지연 임포트되므로 원본 모듈을 패치
    import app.services.node_executor as ne_mod

    monkeypatch.setattr(ne_mod, "execute_node", _fake_execute_node)

    handler = mod.AiCustomHandler()
    ctx = ExecutionContext(db=None, execution_id="e", node_id="n", render_template=lambda t, d: t)
    # 큐 우회: _execute_ai_node 직접 호출
    out = await handler._execute_ai_node(node, node.config, {"x": "v"}, ctx)
    assert out == {"response": "from-snapshot"}
    # 전달된 노드는 스냅샷에서 만든 transient AINode (라이브 아님)
    assert captured["node"].user_prompt_template == "SNAP: {{input.x}}"


@pytest.mark.asyncio
async def test_ai_custom_malformed_snapshot_raises():
    """ai-custom: 불완전한 aiNodeSnapshot(userPromptTemplate 누락)은 ValueError."""
    import app.nodes.ai.ai_custom as mod

    node = SimpleNamespace(
        id="n-aic2",
        definitionType="ai-custom",
        definition_type="ai-custom",
        aiNodeId=None,
        ai_node_id=None,
        config={"aiNodeSnapshot": {"name": "x"}},  # userPromptTemplate 없음
    )
    handler = mod.AiCustomHandler()
    ctx = ExecutionContext(db=None, execution_id="e", node_id="n", render_template=lambda t, d: t)
    with pytest.raises(ValueError):
        await handler._execute_ai_node(node, node.config, {}, ctx)


# ════════════════════════════════════════════════════════════════════════════
# Phase 3 — E7 완화 (apiSpecSnapshot/aiNodeSnapshot) + instanceDbId 엄격 유지
# ════════════════════════════════════════════════════════════════════════════


def _vnode(
    nid: str,
    def_type: str,
    config: Optional[Dict[str, Any]] = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=nid,
        definitionType=def_type,
        definition_type=def_type,
        name=nid,
        config=config or {},
        config_overrides={},
        configOverrides={},
        input_mapping={},
        inputMapping={},
    )


def _vconn(src: str, tgt: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"c-{uuid.uuid4().hex[:6]}",
        source_node_id=src,
        sourceNodeId=src,
        target_node_id=tgt,
        targetNodeId=tgt,
        source_handle=None,
        sourceHandle=None,
        target_handle=None,
        targetHandle=None,
    )


def _codes(issues: List[Dict[str, Any]]) -> List[str]:
    return [i["code"] for i in issues]


@pytest.mark.asyncio
async def test_e7_passes_with_api_snapshot_and_missing_live_def():
    """apiSpecSnapshot 이 있으면 라이브 def 가 없어도 E7(broken-ref) 미보고."""
    from app.services.workflow_validator import validate_workflow_structure

    n1 = _vnode(
        "n1",
        "api-start",
        config={
            "apiDefinitionId": "api-gone",  # 라이브에 없음
            "apiSpecSnapshot": {
                "urlTemplate": "http://localhost:8001/x",
                "method": "GET",
            },
        },
    )
    n2 = _vnode("n2", "result")
    c = _vconn("n1", "n2")
    async with async_session_maker() as db:
        result = await validate_workflow_structure([n1, n2], [c], db)
    assert "broken-ref" not in _codes(result["errors"])


@pytest.mark.asyncio
async def test_e7_passes_with_ai_node_snapshot_and_missing_live_node():
    """aiNodeSnapshot 이 있으면 라이브 AINode 가 없어도 E7 미보고."""
    from app.services.workflow_validator import validate_workflow_structure

    n1 = _vnode("n1", "form-start")
    n2 = _vnode(
        "n2",
        "ai-custom",
        config={
            "ai_node_id": "ai-gone",
            "aiNodeSnapshot": {"userPromptTemplate": "hi"},
        },
    )
    n3 = _vnode("n3", "result")
    async with async_session_maker() as db:
        result = await validate_workflow_structure(
            [n1, n2, n3], [_vconn("n1", "n2"), _vconn("n2", "n3")], db
        )
    assert "broken-ref" not in _codes(result["errors"])


@pytest.mark.asyncio
async def test_e7_still_reports_api_without_snapshot():
    """스냅샷 없는 깨진 apiDefinitionId 는 여전히 E7 보고(회귀 가드)."""
    from app.services.workflow_validator import validate_workflow_structure

    n1 = _vnode("n1", "api-start", config={"apiDefinitionId": "api-gone"})
    n2 = _vnode("n2", "result")
    async with async_session_maker() as db:
        result = await validate_workflow_structure([n1, n2], [_vconn("n1", "n2")], db)
    assert "broken-ref" in _codes(result["errors"])


@pytest.mark.asyncio
async def test_e7_strict_for_instance_db_id_even_with_meta():
    """instanceDbId 는 instanceDbMeta 가 있어도 엄격 유지(완화하지 않음)."""
    from app.services.workflow_validator import validate_workflow_structure

    n1 = _vnode("n1", "form-start")
    n2 = _vnode(
        "n2",
        "instance-db-insert",
        config={
            "instanceDbId": "idb-gone",
            "instanceDbMeta": {"name": "x", "description": "", "tags": [], "viewerHints": {}},
        },
    )
    n3 = _vnode("n3", "result")
    async with async_session_maker() as db:
        result = await validate_workflow_structure(
            [n1, n2, n3], [_vconn("n1", "n2"), _vconn("n2", "n3")], db
        )
    assert "broken-ref" in _codes(result["errors"])
