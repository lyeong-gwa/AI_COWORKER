"""Karpathy v2 P3 acceptance — 청킹·검색 노드·그래프 통합 검증.

검증 시나리오 (사용자 지시 G1~G9):
    G1. POST 짧은 문서(<1024 토큰) → ChromaDB 에 단일 row (chunk_total=1)
    G2. POST 긴 문서(>2000 토큰) → ChromaDB 에 N>1 row, chunk_total 일치
    G3. /knowledge/search 가 청크 hit 을 page 단위로 dedup 하여 반환
    G4. knowledge 노드 핸들러: pageTypes=["Summary"] 필터 정상
    G5. knowledge 노드 minScore=0.9 → 낮은 score 결과 배제
    G6. knowledge 노드 expandBacklinks=true → hit 의 backlink 가 결과에 추가
    G7. GET /knowledge/graph 응답 nodes/edges 유효
    G8. /knowledge/graph?category=codeeyes → codeeyes 페이지/엣지만 반환
    G9. broken link 케이스: 존재하지 않는 페이지를 가리키는 [[link]] → graph 에서 is_broken=true
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import async_session_maker
from app.nodes.base import ExecutionContext
from app.nodes.registry import NodeHandlerRegistry
from app.services.embedding import get_vector_db
from app.services.knowledge_chunker import count_tokens, chunk_document


client = TestClient(app, raise_server_exceptions=False)


# ── 헬퍼 ─────────────────────────────────────────────────────────────────


@pytest.fixture
def unique_suffix() -> str:
    return uuid.uuid4().hex[:8]


def _cleanup_doc(doc_id: str) -> None:
    try:
        client.delete(f"/api/v1/knowledge/{doc_id}?force=true")
    except Exception:
        pass


def _make_long_content(min_tokens: int = 2500) -> str:
    """`min_tokens` 이상의 한국어 본문 생성. 토큰 카운터로 보장."""
    base = "이것은 한국어로 작성된 매우 긴 지식 문서의 한 줄입니다. " \
           "여러 문장이 반복되어 청킹 임계값(1024 토큰)을 충분히 초과하도록 설계되었습니다. "
    out = base
    while count_tokens(out) < min_tokens:
        out = out + base
    return out


def _get_chroma_rows(page_id: str) -> List[Dict[str, Any]]:
    """주어진 page_id 의 모든 청크 row 메타를 반환."""
    vd = get_vector_db()
    # 둘 다 시도 — 청크 메타가 있는 경우 (page_id) + legacy (id 그대로)
    try:
        rows = vd._collection.get(where={"page_id": page_id}, include=["metadatas", "documents"])
    except Exception:
        rows = {"ids": [], "metadatas": [], "documents": []}

    ids = list(rows.get("ids") or [])
    metas = list(rows.get("metadatas") or [])
    docs = list(rows.get("documents") or [])

    if not ids:
        try:
            rows2 = vd._collection.get(ids=[page_id], include=["metadatas", "documents"])
            ids = list(rows2.get("ids") or [])
            metas = list(rows2.get("metadatas") or [])
            docs = list(rows2.get("documents") or [])
        except Exception:
            pass

    out: List[Dict[str, Any]] = []
    for i, rid in enumerate(ids):
        out.append({
            "id": rid,
            "metadata": metas[i] if i < len(metas) else {},
            "document": docs[i] if i < len(docs) else "",
        })
    return out


def _run_knowledge_node(config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
    """knowledge 노드 핸들러를 직접 호출 (워크플로우 실행 없이)."""
    handler = NodeHandlerRegistry.get("knowledge")

    def get_nested(data: Dict, path: str) -> Any:
        if not path:
            return None
        cur: Any = data
        for k in path.split("."):
            if isinstance(cur, dict):
                cur = cur.get(k)
            else:
                return None
        return cur

    node = SimpleNamespace(
        id=f"n-{uuid.uuid4().hex[:6]}",
        workflow_id="wf-test-p3",
        config=config,
        definition_type="knowledge",
    )

    async def _run():
        async with async_session_maker() as db:
            ctx = ExecutionContext(
                db=db,
                execution_id="ex-test",
                node_id=node.id,
                get_nested_value=get_nested,
                render_template=lambda t, d: t,
            )
            return await handler.execute(node=node, input_data=input_data, ctx=ctx)

    return asyncio.run(_run())


# ── G1: 짧은 문서 → 단일 row ─────────────────────────────────────────────


def test_g1_short_doc_creates_single_chunk_row(unique_suffix):
    slug = f"g1-short-{unique_suffix}"
    doc_id = f"codeeyes/{slug}"
    try:
        r = client.post(
            "/api/v1/knowledge",
            json={
            "service": "codeeyes",
            "category": "codeeyes",
                "slug": slug,
                "page_type": "Summary",
                "title": "G1 Short",
                "content": "짧은 본문입니다. 한 청크면 충분합니다.",
                "tags": [],
            },
        )
        assert r.status_code == 201, r.text

        rows = _get_chroma_rows(doc_id)
        assert len(rows) == 1, f"단일 row 기대, got {len(rows)}: {[r['id'] for r in rows]}"
        meta = rows[0]["metadata"]
        # 단일 청크: chunk_total=1, chunk_index=0, page_id 일치
        assert int(meta.get("chunk_total", 0)) == 1, meta
        assert int(meta.get("chunk_index", -1)) == 0, meta
        assert meta.get("page_id") == doc_id, meta
        # row id == page_id 그대로 (단일 청크 호환)
        assert rows[0]["id"] == doc_id
    finally:
        _cleanup_doc(doc_id)


# ── G2: 긴 문서 → 다중 row ───────────────────────────────────────────────


def test_g2_long_doc_creates_multiple_chunk_rows(unique_suffix):
    slug = f"g2-long-{unique_suffix}"
    doc_id = f"codeeyes/{slug}"
    long_content = _make_long_content(min_tokens=2500)
    token_count = count_tokens(long_content)
    assert token_count >= 1024, f"fixture 토큰 수 {token_count} 가 임계 미달"

    expected_chunks = chunk_document(long_content)
    expected_total = len(expected_chunks)
    assert expected_total > 1, f"fixture 가 다중 청크여야 함 (got total={expected_total})"

    try:
        r = client.post(
            "/api/v1/knowledge",
            json={
            "service": "codeeyes",
            "category": "codeeyes",
                "slug": slug,
                "page_type": "Synthesis",
                "title": "G2 Long",
                "content": long_content,
                "tags": [],
            },
        )
        assert r.status_code == 201, r.text

        rows = _get_chroma_rows(doc_id)
        assert len(rows) == expected_total, (
            f"청크 수 불일치: expected {expected_total}, got {len(rows)}"
        )
        # 모든 청크의 chunk_total 이 동일해야 함
        totals = {int(r["metadata"].get("chunk_total", 0)) for r in rows}
        assert totals == {expected_total}, totals
        # id 패턴 — {page_id}#chunk-{N}
        for r in rows:
            assert r["id"].startswith(f"{doc_id}#chunk-"), r["id"]
            assert r["metadata"].get("page_id") == doc_id
    finally:
        _cleanup_doc(doc_id)


# ── G3: search dedup ─────────────────────────────────────────────────────


def test_g3_search_dedups_to_page_level(unique_suffix):
    slug = f"g3-{unique_suffix}"
    doc_id = f"codeeyes/{slug}"
    long_content = _make_long_content(min_tokens=2500)
    try:
        r = client.post(
            "/api/v1/knowledge",
            json={
            "service": "codeeyes",
            "category": "codeeyes",
                "slug": slug,
                "page_type": "Synthesis",
                "title": "G3 Search Dedup",
                "content": long_content,
                "tags": [],
            },
        )
        assert r.status_code == 201, r.text

        # 모든 청크가 매칭될 만한 쿼리
        r2 = client.post(
            "/api/v1/knowledge/search",
            json={"query": "한국어 지식 문서 청킹", "topK": 5},
        )
        assert r2.status_code == 200, r2.text
        results = r2.json()
        # page_id 중복 없음
        ids = [it["document"]["id"] for it in results]
        assert len(ids) == len(set(ids)), f"dedup 위반: {ids}"
    finally:
        _cleanup_doc(doc_id)


# ── G4: pageTypes 필터 ───────────────────────────────────────────────────


def test_g4_node_handler_filters_by_page_types(unique_suffix):
    sum_slug = f"g4-sum-{unique_suffix}"
    ent_slug = f"g4-ent-{unique_suffix}"
    sum_id = f"codeeyes/{sum_slug}"
    ent_id = f"codeeyes/{ent_slug}"
    try:
        # Summary 1개
        r1 = client.post("/api/v1/knowledge", json={
            "service": "codeeyes",
            "category": "codeeyes",
            "slug": sum_slug,
            "page_type": "Summary",
            "title": "G4 Summary doc",
            "content": "이 문서는 G4 페이지타입 필터 시나리오의 Summary 페이지입니다.",
        })
        assert r1.status_code == 201, r1.text
        # Entity 1개
        r2 = client.post("/api/v1/knowledge", json={
            "service": "codeeyes",
            "category": "codeeyes",
            "slug": ent_slug,
            "page_type": "Entity",
            "title": "G4 Entity doc",
            "content": "이 문서는 G4 페이지타입 필터 시나리오의 Entity 페이지입니다.",
        })
        assert r2.status_code == 201, r2.text

        # pageTypes=["Summary"] 만 검색
        out = _run_knowledge_node(
            config={
                "searchField": "q",
                "categories": ["codeeyes"],
                "pageTypes": ["Summary"],
                "maxResults": 14,
            },
            input_data={"q": "G4 페이지타입 필터"},
        )
        items = out.get("knowledge", [])
        # search_page_types 동봉 검증
        assert out.get("search_page_types") == ["Summary"], out.get("search_page_types")
        # 결과의 모든 page_type 이 Summary
        assert items, "결과가 비어 있음 — 카테고리 필터·검색 모두 동작해야 함"
        for it in items:
            assert it.get("page_type") == "Summary", it
        # Entity 페이지가 결과에 없음
        ids = [it["id"] for it in items]
        assert ent_id not in ids, f"Entity 페이지가 잘못 포함됨: {ids}"
        # Summary 페이지가 포함됨
        assert sum_id in ids, f"Summary 페이지가 누락됨: {ids}"
    finally:
        _cleanup_doc(sum_id)
        _cleanup_doc(ent_id)


# ── G5: minScore 필터 ───────────────────────────────────────────────────


def test_g5_node_handler_min_score_excludes_low(unique_suffix):
    slug = f"g5-{unique_suffix}"
    doc_id = f"codeeyes/{slug}"
    try:
        client.post("/api/v1/knowledge", json={
            "service": "codeeyes",
            "category": "codeeyes",
            "slug": slug,
            "page_type": "Summary",
            "title": "G5 doc",
            "content": "이 문서는 G5 시나리오 전용입니다.",
        })

        # minScore=0.99 — 거의 모든 결과 배제 (완전 일치 query 가 아니라면)
        out = _run_knowledge_node(
            config={
                "searchField": "q",
                "categories": ["codeeyes"],
                "maxResults": 14,
                "minScore": 0.99,
            },
            input_data={"q": "전혀 다른 토픽 무관 검색어 xyz123"},
        )
        items = out.get("knowledge", [])
        # 모든 결과 score >= 0.99
        for it in items:
            assert it["score"] >= 0.99, f"minScore 위반: {it}"
        # 보통 0건이지만 0건도 정상 (filter 동작 자체가 검증 대상)
    finally:
        _cleanup_doc(doc_id)


# ── G6: expandBacklinks ──────────────────────────────────────────────────


def test_g6_node_handler_expand_backlinks(unique_suffix):
    # minScore 로 overview 를 1차 hit 에서 배제 → expandBacklinks 가 다시 추가하는지 검증.
    # overview 본문은 sys 와 의미적으로 거리가 멀고, [[sys_id]] 링크만 보유.
    over_slug = f"g6-over-{unique_suffix}"
    sys_slug = f"g6-sys-{unique_suffix}"
    over_id = f"codeeyes/{over_slug}"
    sys_id = f"codeeyes/{sys_slug}"
    try:
        # overview: sys 와 무관한 본문 + sys 링크
        r1 = client.post("/api/v1/knowledge", json={
            "service": "codeeyes",
            "category": "codeeyes",
            "slug": over_slug,
            "page_type": "Summary",
            "title": "G6 Overview",
            "content": f"오늘 날씨는 매우 맑고 햇살이 좋아 산책하기 좋은 날입니다. [[{sys_id}]]",
        })
        assert r1.status_code == 201, r1.text
        # sys: 검색 쿼리와 거의 일치하는 본문
        sys_text = "xenobyte 분산 시스템 핵심 엔진 아키텍처 컴포넌트 모듈 구성"
        r2 = client.post("/api/v1/knowledge", json={
            "service": "codeeyes",
            "category": "codeeyes",
            "slug": sys_slug,
            "page_type": "Entity",
            "title": "G6 System",
            "content": sys_text,
        })
        assert r2.status_code == 201, r2.text

        # 1) 먼저 minScore 0 으로 두 페이지 score 차이 확인 (디버그용)
        out_no_filter = _run_knowledge_node(
            config={
                "searchField": "q",
                "categories": ["codeeyes"],
                "maxResults": 4,
                "expandBacklinks": False,
            },
            input_data={"q": sys_text},
        )
        items_nf = out_no_filter.get("knowledge", [])
        scores_by_id = {it["id"]: it["score"] for it in items_nf}
        sys_score = scores_by_id.get(sys_id, 0.0)
        over_score = scores_by_id.get(over_id, -1.0)
        # 동적으로 두 score 사이값을 minScore 로 사용 → overview 만 배제
        # over_score 가 sys_score 보다 작아야 의미 있음
        if over_score >= sys_score or sys_score <= 0:
            pytest.skip(
                f"임베딩이 sys/overview score 분리 실패 (sys={sys_score}, over={over_score})"
            )
        min_score = (sys_score + over_score) / 2.0

        # 2) minScore 적용 + expandBacklinks=True
        out = _run_knowledge_node(
            config={
                "searchField": "q",
                "categories": ["codeeyes"],
                "maxResults": 4,
                "minScore": min_score,
                "expandBacklinks": True,
            },
            input_data={"q": sys_text},
        )
        items = out.get("knowledge", [])
        ids = [it["id"] for it in items]
        assert sys_id in ids, f"sys 페이지 hit 누락: {ids}"
        # overview 는 1차 hit 에서 배제됐어야 하므로 expansion 으로 추가됨
        over_item = next((it for it in items if it["id"] == over_id), None)
        assert over_item is not None, (
            f"overview backlink 가 expand 되지 않음 — 결과 ids: {ids}, items: {items}"
        )
        assert over_item.get("isBacklinkExpansion") is True, (
            f"expand 된 항목인데 마킹 누락: {over_item}"
        )
    finally:
        _cleanup_doc(over_id)
        _cleanup_doc(sys_id)


# ── G7: GET /knowledge/graph ─────────────────────────────────────────────


def test_g7_graph_endpoint_returns_valid_nodes_edges(unique_suffix):
    over_slug = f"g7-over-{unique_suffix}"
    sys_slug = f"g7-sys-{unique_suffix}"
    over_id = f"codeeyes/{over_slug}"
    sys_id = f"codeeyes/{sys_slug}"
    try:
        client.post("/api/v1/knowledge", json={
            "service": "codeeyes",
            "category": "codeeyes",
            "slug": over_slug,
            "page_type": "Summary",
            "title": "G7 Overview",
            "content": f"See [[{sys_id}]]",
        })
        client.post("/api/v1/knowledge", json={
            "service": "codeeyes",
            "category": "codeeyes",
            "slug": sys_slug,
            "page_type": "Entity",
            "title": "G7 System",
            "content": "system body",
        })

        r = client.get("/api/v1/knowledge/graph")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "nodes" in body and "edges" in body
        node_ids = {n["id"] for n in body["nodes"]}
        assert over_id in node_ids
        assert sys_id in node_ids
        edge_pairs = {(e["from"], e["to"]) for e in body["edges"]}
        assert (over_id, sys_id) in edge_pairs
        # over -> sys 엣지의 isBroken=false
        over_to_sys = next(e for e in body["edges"] if e["from"] == over_id and e["to"] == sys_id)
        assert over_to_sys["isBroken"] is False
        # nodes 정렬 — id ASC
        ids_sorted = [n["id"] for n in body["nodes"]]
        assert ids_sorted == sorted(ids_sorted)
        # edges 정렬 — from ASC, to ASC
        edge_tuples = [(e["from"], e["to"]) for e in body["edges"]]
        assert edge_tuples == sorted(edge_tuples)
        # backlinksCount 확인 — sys 가 1
        sys_node = next(n for n in body["nodes"] if n["id"] == sys_id)
        assert sys_node["backlinksCount"] >= 1
    finally:
        _cleanup_doc(over_id)
        _cleanup_doc(sys_id)


# ── G8: graph category 필터 ─────────────────────────────────────────────


def test_g8_graph_filter_by_category(unique_suffix):
    code_slug = f"g8-codeeyes-{unique_suffix}"
    faq_slug = f"g8-faq-{unique_suffix}"
    code_id = f"codeeyes/{code_slug}"
    faq_id = f"faq/{faq_slug}"
    try:
        client.post("/api/v1/knowledge", json={
            "service": "codeeyes",
            "category": "codeeyes",
            "slug": code_slug,
            "page_type": "Summary",
            "title": "G8 CodeEyes",
            "content": "codeeyes side",
        })
        client.post("/api/v1/knowledge", json={
            "category": "faq",
            "slug": faq_slug,
            "page_type": "Summary",
            "title": "G8 FAQ",
            "content": "faq side",
        })

        r = client.get("/api/v1/knowledge/graph", params={"category": "codeeyes"})
        assert r.status_code == 200, r.text
        body = r.json()
        node_ids = {n["id"] for n in body["nodes"]}
        # codeeyes 만 — faq 미포함
        assert code_id in node_ids
        assert faq_id not in node_ids
        # 모든 node 의 category 가 codeeyes
        for n in body["nodes"]:
            assert n["category"] == "codeeyes", n
    finally:
        _cleanup_doc(code_id)
        _cleanup_doc(faq_id)


# ── G9: broken link ─────────────────────────────────────────────────────


def test_g9_graph_broken_link_marked(unique_suffix):
    slug = f"g9-{unique_suffix}"
    doc_id = f"codeeyes/{slug}"
    missing_id = f"codeeyes/g9-missing-{unique_suffix}"
    try:
        client.post("/api/v1/knowledge", json={
            "service": "codeeyes",
            "category": "codeeyes",
            "slug": slug,
            "page_type": "Summary",
            "title": "G9",
            "content": f"이 문서는 존재하지 않는 [[{missing_id}]] 를 참조합니다.",
        })

        r = client.get("/api/v1/knowledge/graph")
        assert r.status_code == 200, r.text
        body = r.json()
        # missing 페이지는 nodes 에 없음
        node_ids = {n["id"] for n in body["nodes"]}
        assert missing_id not in node_ids
        # broken edge 존재 확인
        broken = [
            e for e in body["edges"]
            if e["from"] == doc_id and e["to"] == missing_id
        ]
        assert broken, f"broken edge 누락. edges with from={doc_id}: " \
                       f"{[e for e in body['edges'] if e['from'] == doc_id]}"
        assert broken[0]["isBroken"] is True
    finally:
        _cleanup_doc(doc_id)
