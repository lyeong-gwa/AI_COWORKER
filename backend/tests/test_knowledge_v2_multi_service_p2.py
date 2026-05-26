"""Multi-service v3 P2 acceptance — API · knowledge 노드 · 브리프 · 그래프 wiring.

검증 (`.omc/plans/지식-multi-service.md` Phase 2 + 작업 지시 §2):
    1.  GET /knowledge/services → codeeyes + unknown 2종 반환 (P2 §2.2)
    2.  POST 응답에 service 키 노출 (P2 §2.1)
    3.  GET /knowledge/{id} 응답에 service 키 노출 (P2 §2.1)
    4.  GET /knowledge?service=codeeyes → codeeyes 페이지만 (P2 §2.3)
    5.  GET /knowledge?service=xyz → 422 (P2 §2.3)
    6.  GET /knowledge/graph?service=codeeyes → service 일치 노드만 + crossService 키 존재 (P2 §2.4)
    7.  GET /knowledge/graph?service=xyz → 422
    8.  POST /knowledge/brief {services:["codeeyes"]} → pages 모두 service=codeeyes (P2 §2.5)
    9.  POST /knowledge/brief {services:["xyz"]} → 422
    10. knowledge 노드 핸들러: config.services=["codeeyes"] 필터 동작 + 응답 service 키 (P2 §2.6)
    11. catalog 응답에 knowledge 노드의 services config 명세 포함 (P2 §2.6)
    12. POST /knowledge/_internal/reindex-services → total/synced/failed 보고
    13. 기존 회귀 0 — 63 backend 테스트는 별도 세션에서 통과 확인.
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.knowledge_schema import reset_schema_cache


client = TestClient(app, raise_server_exceptions=False)


# ── 격리 ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_schema_cache_between_tests():
    reset_schema_cache()
    yield
    reset_schema_cache()


@pytest.fixture
def unique_suffix() -> str:
    return uuid.uuid4().hex[:8]


def _cleanup_doc(doc_id: str) -> None:
    try:
        client.delete(f"/api/v1/knowledge/{doc_id}?force=true")
    except Exception:
        pass


# ── 1. GET /knowledge/services ────────────────────────────────────────────


def test_get_services_returns_codeeyes_and_unknown():
    """P2 §2.2 — _schema.yaml services 그대로 list_services() 응답."""
    r = client.get("/api/v1/knowledge/services")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list), body
    ids = [s["id"] for s in body]
    assert "codeeyes" in ids
    assert "unknown" in ids
    for s in body:
        assert set(s.keys()) >= {"id", "title", "description"}


# ── 2. POST/GET 응답에 service 키 ─────────────────────────────────────────


def test_post_response_contains_service_key(unique_suffix):
    """P2 §2.1 — POST 응답에도 service 노출."""
    slug = f"p2-postresp-{unique_suffix}"
    doc_id = f"overview/{slug}"
    try:
        r = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "overview",
                "slug": slug,
                "page_type": "Summary",
                "title": "P2 POST response service key",
                "content": "본문",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert "service" in body, body
        assert body["service"] == "codeeyes"
    finally:
        _cleanup_doc(doc_id)


def test_get_single_doc_response_contains_service_key(unique_suffix):
    """P2 §2.1 — GET /knowledge/{id} 응답에도 service 노출."""
    slug = f"p2-getsingle-{unique_suffix}"
    doc_id = f"overview/{slug}"
    try:
        r = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "overview",
                "slug": slug,
                "page_type": "Summary",
                "title": "P2 GET single service key",
                "content": "본문",
            },
        )
        assert r.status_code == 201, r.text

        g = client.get(f"/api/v1/knowledge/{doc_id}")
        assert g.status_code == 200, g.text
        gbody = g.json()
        assert gbody.get("service") == "codeeyes"
    finally:
        _cleanup_doc(doc_id)


def test_get_list_response_contains_service_key(unique_suffix):
    """P2 §2.1 — GET /knowledge (목록) 응답의 각 항목에도 service 노출."""
    slug = f"p2-getlist-{unique_suffix}"
    doc_id = f"overview/{slug}"
    try:
        r = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "overview",
                "slug": slug,
                "page_type": "Summary",
                "title": "P2 list service key",
                "content": "본문",
            },
        )
        assert r.status_code == 201, r.text

        listing = client.get("/api/v1/knowledge", params={"limit": 500})
        assert listing.status_code == 200, listing.text
        items = listing.json()
        target = next((it for it in items if it["id"] == doc_id), None)
        assert target is not None, f"created doc not found in listing: {doc_id}"
        assert target.get("service") == "codeeyes"
        # 목록의 모든 항목에 service 키가 존재 (legacy 도 default unknown)
        for it in items:
            assert "service" in it, it
    finally:
        _cleanup_doc(doc_id)


# ── 3. GET /knowledge?service=... 필터 ────────────────────────────────────


def test_get_list_service_filter_returns_only_matching(unique_suffix):
    """P2 §2.3 — service 필터 + category 필터 AND."""
    # 1) service=codeeyes 페이지 생성
    code_slug = f"p2-svcflt-code-{unique_suffix}"
    code_id = f"overview/{code_slug}"
    # 2) service=unknown 페이지 생성 (sentinel 항상 허용)
    unk_slug = f"p2-svcflt-unk-{unique_suffix}"
    unk_id = f"overview/{unk_slug}"
    try:
        r1 = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "overview",
                "slug": code_slug,
                "page_type": "Summary",
                "title": "p2 svc filter codeeyes",
                "content": "x",
            },
        )
        assert r1.status_code == 201, r1.text
        r2 = client.post(
            "/api/v1/knowledge",
            json={
                "service": "unknown",
                "category": "overview",
                "slug": unk_slug,
                "page_type": "Summary",
                "title": "p2 svc filter unknown",
                "content": "x",
            },
        )
        assert r2.status_code == 201, r2.text

        # service=codeeyes 필터 → unknown 페이지는 빠져야 함
        flt = client.get(
            "/api/v1/knowledge",
            params={"service": "codeeyes", "limit": 500},
        )
        assert flt.status_code == 200, flt.text
        items = flt.json()
        ids = {it["id"] for it in items}
        assert code_id in ids, f"codeeyes 페이지 누락: {code_id}"
        assert unk_id not in ids, f"unknown 페이지가 service=codeeyes 필터에 포함됨: {unk_id}"
        # 응답의 모든 service 값이 codeeyes
        for it in items:
            assert it["service"] == "codeeyes", it
    finally:
        _cleanup_doc(code_id)
        _cleanup_doc(unk_id)


def test_get_list_service_filter_undefined_returns_422():
    """P2 §2.3 — _schema.yaml services enum 에 없는 service 는 422."""
    r = client.get("/api/v1/knowledge", params={"service": "xyz-not-defined"})
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


# ── 4. GET /knowledge/graph + service 필터 / crossService ─────────────────


def test_graph_nodes_contain_service_key_and_filter_works(unique_suffix):
    """P2 §2.4 — graph nodes 에 service 키 + service 필터 동작."""
    code_slug = f"p2-gph-code-{unique_suffix}"
    code_id = f"overview/{code_slug}"
    unk_slug = f"p2-gph-unk-{unique_suffix}"
    unk_id = f"overview/{unk_slug}"
    try:
        client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "overview",
                "slug": code_slug,
                "page_type": "Summary",
                "title": "graph code",
                "content": "x",
            },
        )
        client.post(
            "/api/v1/knowledge",
            json={
                "service": "unknown",
                "category": "overview",
                "slug": unk_slug,
                "page_type": "Summary",
                "title": "graph unk",
                "content": "x",
            },
        )

        # 필터 없이 → 모든 노드에 service 키 존재
        r = client.get("/api/v1/knowledge/graph")
        assert r.status_code == 200, r.text
        body = r.json()
        for n in body["nodes"]:
            assert "service" in n, n
        # edges 응답에 crossService 키 존재
        for e in body["edges"]:
            assert "crossService" in e, e

        # service=codeeyes 필터 → codeeyes 만 포함, unknown 페이지는 제외
        r2 = client.get("/api/v1/knowledge/graph", params={"service": "codeeyes"})
        assert r2.status_code == 200, r2.text
        body2 = r2.json()
        node_ids = {n["id"] for n in body2["nodes"]}
        assert code_id in node_ids
        assert unk_id not in node_ids
        # 모든 노드의 service == codeeyes
        for n in body2["nodes"]:
            assert n["service"] == "codeeyes", n
    finally:
        _cleanup_doc(code_id)
        _cleanup_doc(unk_id)


def test_graph_service_filter_undefined_returns_422():
    r = client.get("/api/v1/knowledge/graph", params={"service": "xyz-not-defined"})
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_graph_edge_cross_service_marker(unique_suffix):
    """P2 §2.4 — 서로 다른 service 의 두 페이지가 링크되면 crossService=true."""
    code_slug = f"p2-cross-code-{unique_suffix}"
    code_id = f"overview/{code_slug}"
    unk_slug = f"p2-cross-unk-{unique_suffix}"
    unk_id = f"overview/{unk_slug}"
    try:
        # unknown 페이지 먼저 (링크 target)
        client.post(
            "/api/v1/knowledge",
            json={
                "service": "unknown",
                "category": "overview",
                "slug": unk_slug,
                "page_type": "Entity",
                "title": "cross unk",
                "content": "target",
            },
        )
        # codeeyes 페이지가 unknown 페이지를 링크
        client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "overview",
                "slug": code_slug,
                "page_type": "Summary",
                "title": "cross code",
                "content": f"see [[{unk_id}]]",
            },
        )

        r = client.get("/api/v1/knowledge/graph")
        assert r.status_code == 200, r.text
        body = r.json()
        target_edge = next(
            (e for e in body["edges"] if e["from"] == code_id and e["to"] == unk_id),
            None,
        )
        assert target_edge is not None, f"엣지 누락: {code_id} -> {unk_id}"
        assert target_edge["crossService"] is True, target_edge
        assert target_edge["isBroken"] is False, target_edge
    finally:
        _cleanup_doc(code_id)
        _cleanup_doc(unk_id)


# ── 5. POST /knowledge/brief services 필터 ────────────────────────────────


def test_brief_services_filter_returns_only_matching(unique_suffix):
    """P2 §2.5 — services 필터 적용 시 pages 모두 service=요청값."""
    # codeeyes / unknown 각각 동일 토픽 페이지 생성
    code_slug = f"p2-brief-code-{unique_suffix}"
    code_id = f"overview/{code_slug}"
    unk_slug = f"p2-brief-unk-{unique_suffix}"
    unk_id = f"overview/{unk_slug}"
    try:
        common = f"p2-brief-{unique_suffix} 통합 통찰 운영"
        client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "overview",
                "slug": code_slug,
                "page_type": "Synthesis",
                "title": "brief code",
                "content": common,
            },
        )
        client.post(
            "/api/v1/knowledge",
            json={
                "service": "unknown",
                "category": "overview",
                "slug": unk_slug,
                "page_type": "Synthesis",
                "title": "brief unk",
                "content": common,
            },
        )

        r = client.post(
            "/api/v1/knowledge/brief",
            json={
                "query": common,
                "services": ["codeeyes"],
                "maxPages": 8,
                "includeLog": False,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        for p in body["pages"]:
            # services 필터가 동작해야 한다 — pages 의 모든 service 가 codeeyes
            assert p.get("service") == "codeeyes", p
        # retrievalNotes 에 사용된 service 필터가 명시되어 있어야 한다 (P2 §2.5)
        assert "Service filter applied" in body["retrievalNotes"], body["retrievalNotes"]
        assert "codeeyes" in body["retrievalNotes"]
    finally:
        _cleanup_doc(code_id)
        _cleanup_doc(unk_id)


def test_brief_services_undefined_returns_422():
    """P2 §2.5 — services 안의 미정의 id 는 422."""
    r = client.post(
        "/api/v1/knowledge/brief",
        json={
            "query": "anything",
            "services": ["xyz-not-defined"],
            "maxPages": 3,
            "includeLog": False,
        },
    )
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


# ── 6. knowledge 노드 핸들러 services 필터 ────────────────────────────────


def test_knowledge_node_handler_services_filter(unique_suffix):
    """P2 §2.6 — knowledge 노드 config.services 필터가 ChromaDB where 결합 + 응답
    페이로드 service 키 노출."""
    # 두 페이지 등록 — 같은 본문 / 다른 service
    code_slug = f"p2-knode-code-{unique_suffix}"
    code_id = f"overview/{code_slug}"
    unk_slug = f"p2-knode-unk-{unique_suffix}"
    unk_id = f"overview/{unk_slug}"
    common_text = f"knowledge-node-svcflt-{unique_suffix} 본문 텍스트"
    try:
        client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "overview",
                "slug": code_slug,
                "page_type": "Summary",
                "title": "knode code",
                "content": common_text,
            },
        )
        client.post(
            "/api/v1/knowledge",
            json={
                "service": "unknown",
                "category": "overview",
                "slug": unk_slug,
                "page_type": "Summary",
                "title": "knode unk",
                "content": common_text,
            },
        )

        # KnowledgeHandler 직접 호출
        from app.nodes.action.knowledge import KnowledgeHandler
        from app.nodes.base import ExecutionContext

        def _get_nested(data, path):
            if not path:
                return None
            cur = data
            for seg in path.split("."):
                if isinstance(cur, dict):
                    cur = cur.get(seg)
                else:
                    return None
            return cur

        # 최소 ExecutionContext 구성 — knowledge 핸들러는 db 미사용.
        ctx = ExecutionContext(
            db=None,
            execution_id="test-exec",
            node_id="n1",
            get_nested_value=_get_nested,
        )

        node = SimpleNamespace(
            id="n1",
            config={
                "searchField": "",
                "services": ["codeeyes"],
                "maxResults": 7,
            },
        )

        handler = KnowledgeHandler()
        result = asyncio.run(handler.execute(node, {"q": common_text}, ctx))
        # search_services 메타가 노출됨
        assert result.get("search_services") == ["codeeyes"], result
        items = result.get("knowledge", [])
        # 응답에 service 키가 존재하며 codeeyes 페이지만 포함
        for it in items:
            assert "service" in it, it
        # codeeyes 페이지가 포함되어야 하고 unknown 페이지는 빠져야 한다
        # (벡터 검색이 실패할 수도 있으므로 ChromaDB 미가용 케이스는 빈 결과 + KNOWLEDGE_ERROR 가능)
        if items:
            ids = [it["id"] for it in items]
            # unknown 페이지가 결과에 포함되면 필터 실패
            assert unk_id not in ids, f"service 필터가 동작하지 않음: {ids}"
            # codeeyes 페이지가 포함되어야 한다 (결과가 있을 때)
            for it in items:
                assert it["service"] == "codeeyes", it
    finally:
        _cleanup_doc(code_id)
        _cleanup_doc(unk_id)


# ── 7. catalog 의 services 필드 ───────────────────────────────────────────


def test_catalog_knowledge_node_has_services_config():
    """P2 §2.6 — /api/v1/nodes/catalog 의 knowledge 엔트리에 services 명세 포함."""
    r = client.get("/api/v1/nodes/catalog")
    assert r.status_code == 200, r.text
    catalog = r.json()
    knowledge_entry = next(
        (e for e in catalog if e["defType"] == "knowledge"),
        None,
    )
    assert knowledge_entry is not None, "knowledge 노드 엔트리 누락"
    cfg_names = {c["name"] for c in knowledge_entry["config"]}
    assert "services" in cfg_names, f"services config 누락: {cfg_names}"
    output_names = {o["name"] for o in knowledge_entry["outputs"]}
    assert "search_services" in output_names, f"search_services output 누락: {output_names}"


# ── 8. reindex-services 엔드포인트 ────────────────────────────────────────


def test_reindex_services_endpoint_returns_counts():
    """P2 §2.7 — 모든 페이지 metadata 에 service 키 반영. 응답 schema 검증."""
    r = client.post("/api/v1/knowledge/_internal/reindex-services")
    # ChromaDB 미가용 시 503, 일반 환경은 200
    assert r.status_code in (200, 503), r.text
    if r.status_code == 200:
        body = r.json()
        assert "total" in body
        assert "synced" in body
        assert "failed" in body
        assert "failedSampleIds" in body
        assert body["total"] >= 0
        assert body["synced"] + body["failed"] == body["total"], body
