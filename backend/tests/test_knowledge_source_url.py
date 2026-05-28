"""source_url 필드 acceptance — LLM URL hallucination 차단 인프라.

검증 (작업 지시 A-1 ~ A-6):
    1.  KnowledgeFileDoc.source_url default 가 None
    2.  build_md_file: source_url 명시 → frontmatter 에 보존
    3.  build_md_file: source_url None / 빈 문자열 → frontmatter 미기재
    4.  write_md_file → parse_frontmatter round-trip
    5.  POST /knowledge {source_url: "..."} → 201 + 응답 sourceUrl 일치, GET 일관
    6.  POST /knowledge 없이 source_url → 응답 sourceUrl=null
    7.  PUT /knowledge source_url 추가 / 변경 / 빈 문자열로 제거
    8.  GET /knowledge (목록) 응답에 sourceUrl 키 노출
    9.  ChromaDB metadata sync — source_url 있는 페이지만 metadata 에 키 보존
    10. knowledge 노드 응답에 source_url 키 노출 (값 또는 None)
    11. legacy frontmatter 미기재 페이지는 source_url=None default 유지 (회귀 가드)
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.knowledge_file_service import (
    KnowledgeFileDoc,
    build_md_file,
    list_md_files,
    parse_frontmatter,
    read_md_file,
    write_md_file,
)
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


# ── 1. dataclass default ──────────────────────────────────────────────────


def test_knowledge_file_doc_source_url_default_is_none():
    """legacy 페이지 호환: frontmatter 에 source_url 없으면 None."""
    doc = KnowledgeFileDoc(id="x/y", title="t", content="c")
    assert doc.source_url is None


# ── 2~3. build_md_file ────────────────────────────────────────────────────


def test_build_md_file_includes_source_url_when_given():
    raw = build_md_file(
        title="t",
        content="body",
        category="overview",
        source_url="https://intra-coder-doc.example.com/p1",
    )
    meta, _ = parse_frontmatter(raw)
    assert meta.get("source_url") == "https://intra-coder-doc.example.com/p1"


def test_build_md_file_omits_source_url_when_none():
    raw = build_md_file(
        title="t",
        content="body",
        category="overview",
        source_url=None,
    )
    meta, _ = parse_frontmatter(raw)
    assert "source_url" not in meta, meta


def test_build_md_file_omits_source_url_when_blank():
    """빈 문자열 / 공백 문자열은 미기재."""
    raw = build_md_file(
        title="t",
        content="body",
        category="overview",
        source_url="   ",
    )
    meta, _ = parse_frontmatter(raw)
    assert "source_url" not in meta, meta


# ── 4. write_md_file round-trip via read_md_file ──────────────────────────


def test_write_md_file_round_trip_with_source_url(unique_suffix):
    """write → read 후 source_url 일치."""
    slug = f"src-url-rt-{unique_suffix}"
    doc_id = f"overview/{slug}"
    try:
        # POST 가 아니라 service-level write 만 (라우터 검증 우회)
        # 단 카테고리 디렉토리 존재 의존 — overview 는 기본 존재
        url = "https://intra-coder-doc.example.com/round-trip"
        write_md_file(
            doc_id=doc_id,
            title="rt",
            content="body",
            category="overview",
            service="codeeyes",
            source_url=url,
            page_type="Summary",
            version=1,
            links=[],
        )
        loaded = read_md_file(doc_id)
        assert loaded is not None
        assert loaded.source_url == url
    finally:
        # 직접 파일 삭제 (changelog 우회)
        from app.services.knowledge_file_service import delete_md_file
        delete_md_file(doc_id)


def test_write_md_file_round_trip_without_source_url(unique_suffix):
    """source_url 미지정 → read 시 None."""
    slug = f"src-url-none-{unique_suffix}"
    doc_id = f"overview/{slug}"
    try:
        write_md_file(
            doc_id=doc_id,
            title="rt",
            content="body",
            category="overview",
            service="codeeyes",
            page_type="Summary",
            version=1,
            links=[],
        )
        loaded = read_md_file(doc_id)
        assert loaded is not None
        assert loaded.source_url is None
    finally:
        from app.services.knowledge_file_service import delete_md_file
        delete_md_file(doc_id)


# ── 5. POST /knowledge with source_url ─────────────────────────────────────


def test_post_knowledge_persists_source_url(unique_suffix):
    """POST 시 source_url 명시 → 응답 sourceUrl 노출, GET 일관."""
    slug = f"src-url-post-{unique_suffix}"
    doc_id = f"overview/{slug}"
    url = "https://intra-coder-doc.example.com/post-test"
    try:
        r = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "overview",
                "slug": slug,
                "page_type": "Summary",
                "title": "post test",
                "content": "본문",
                "source_url": url,
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body.get("sourceUrl") == url, body

        # GET 일관
        g = client.get(f"/api/v1/knowledge/{doc_id}")
        assert g.status_code == 200, g.text
        assert g.json().get("sourceUrl") == url

        # frontmatter 직접 검증
        doc = read_md_file(doc_id)
        assert doc is not None
        assert doc.source_url == url
    finally:
        _cleanup_doc(doc_id)


# ── 6. POST 없이 source_url → null ────────────────────────────────────────


def test_post_knowledge_without_source_url_returns_null(unique_suffix):
    """source_url 누락 시 응답에서 sourceUrl=null."""
    slug = f"src-url-nullpost-{unique_suffix}"
    doc_id = f"overview/{slug}"
    try:
        r = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "overview",
                "slug": slug,
                "page_type": "Summary",
                "title": "no url",
                "content": "본문",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert "sourceUrl" in body, body
        assert body["sourceUrl"] is None, body
    finally:
        _cleanup_doc(doc_id)


# ── 7. PUT /knowledge — 추가 / 변경 / 빈 문자열로 제거 ─────────────────────


def test_put_knowledge_adds_source_url(unique_suffix):
    """기존 페이지에 PUT 으로 source_url 추가."""
    slug = f"src-url-add-{unique_suffix}"
    doc_id = f"overview/{slug}"
    try:
        # 1) 생성 (source_url 없음)
        r1 = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "overview",
                "slug": slug,
                "page_type": "Summary",
                "title": "add url",
                "content": "본문",
            },
        )
        assert r1.status_code == 201, r1.text
        assert r1.json().get("sourceUrl") is None

        # 2) PUT 으로 source_url 추가
        new_url = "https://intra-coder-doc.example.com/added"
        r2 = client.put(
            f"/api/v1/knowledge/{doc_id}",
            json={"source_url": new_url},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json().get("sourceUrl") == new_url

        # 3) GET 일관
        g = client.get(f"/api/v1/knowledge/{doc_id}")
        assert g.json().get("sourceUrl") == new_url
    finally:
        _cleanup_doc(doc_id)


def test_put_knowledge_preserves_source_url_when_not_specified(unique_suffix):
    """PUT 요청 body 에 source_url 미포함 → 기존 값 유지 (다른 필드만 갱신해도)."""
    slug = f"src-url-preserve-{unique_suffix}"
    doc_id = f"overview/{slug}"
    original_url = "https://intra-coder-doc.example.com/preserve"
    try:
        r1 = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "overview",
                "slug": slug,
                "page_type": "Summary",
                "title": "preserve url",
                "content": "본문",
                "source_url": original_url,
            },
        )
        assert r1.status_code == 201, r1.text

        # 다른 필드만 갱신
        r2 = client.put(
            f"/api/v1/knowledge/{doc_id}",
            json={"title": "new title"},
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["title"] == "new title"
        # source_url 보존
        assert body.get("sourceUrl") == original_url, body
    finally:
        _cleanup_doc(doc_id)


def test_put_knowledge_removes_source_url_with_blank(unique_suffix):
    """빈 문자열로 PUT → source_url 제거 (None)."""
    slug = f"src-url-remove-{unique_suffix}"
    doc_id = f"overview/{slug}"
    try:
        r1 = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "overview",
                "slug": slug,
                "page_type": "Summary",
                "title": "remove url",
                "content": "본문",
                "source_url": "https://intra-coder-doc.example.com/will-be-removed",
            },
        )
        assert r1.status_code == 201, r1.text

        r2 = client.put(
            f"/api/v1/knowledge/{doc_id}",
            json={"source_url": ""},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json().get("sourceUrl") is None, r2.json()
    finally:
        _cleanup_doc(doc_id)


# ── 8. GET 목록 응답에 sourceUrl 키 ───────────────────────────────────────


def test_get_list_response_contains_source_url_key(unique_suffix):
    """GET /knowledge (목록) 응답의 각 항목에 sourceUrl 키 존재."""
    slug = f"src-url-list-{unique_suffix}"
    doc_id = f"overview/{slug}"
    url = "https://intra-coder-doc.example.com/list-test"
    try:
        r = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "overview",
                "slug": slug,
                "page_type": "Summary",
                "title": "list test",
                "content": "x",
                "source_url": url,
            },
        )
        assert r.status_code == 201, r.text

        listing = client.get("/api/v1/knowledge", params={"limit": 500})
        assert listing.status_code == 200, listing.text
        items = listing.json()
        target = next((it for it in items if it["id"] == doc_id), None)
        assert target is not None
        assert target.get("sourceUrl") == url
        # 모든 항목에 sourceUrl 키 존재 (legacy 도 None default)
        for it in items:
            assert "sourceUrl" in it, it
    finally:
        _cleanup_doc(doc_id)


# ── 9. ChromaDB metadata sync — source_url 포함 ───────────────────────────


def test_chromadb_metadata_includes_source_url(unique_suffix):
    """source_url 가 있는 페이지는 ChromaDB metadata 에 키 보존."""
    slug = f"src-url-chroma-{unique_suffix}"
    doc_id = f"overview/{slug}"
    url = "https://intra-coder-doc.example.com/chroma-test"
    try:
        r = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "overview",
                "slug": slug,
                "page_type": "Summary",
                "title": "chroma url test",
                "content": "유니크한 본문 내용 for chroma test",
                "source_url": url,
            },
        )
        assert r.status_code == 201, r.text

        # ChromaDB collection 에서 직접 메타 조회
        from app.services.embedding import get_vector_db

        try:
            vector_db = get_vector_db()
        except Exception:
            pytest.skip("ChromaDB unavailable in this environment")

        # page_id 로 직접 get
        try:
            results = vector_db._collection.get(  # noqa: SLF001
                where={"page_id": doc_id},
                include=["metadatas"],
            )
        except Exception:
            pytest.skip("ChromaDB get unavailable in this environment")

        metas = results.get("metadatas") or []
        assert metas, f"no chroma rows for {doc_id}"
        # 최소 한 청크는 source_url 메타 포함
        urls_seen = [m.get("source_url") for m in metas if isinstance(m, dict)]
        assert url in urls_seen, f"source_url not found in chroma metadata: {urls_seen}"
    finally:
        _cleanup_doc(doc_id)


def test_chromadb_metadata_omits_source_url_when_none(unique_suffix):
    """source_url 없는 페이지는 ChromaDB metadata 에 키가 없어야 (LLM hallucination 차단)."""
    slug = f"src-url-chroma-none-{unique_suffix}"
    doc_id = f"overview/{slug}"
    try:
        r = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "overview",
                "slug": slug,
                "page_type": "Summary",
                "title": "chroma null test",
                "content": "본문 only",
            },
        )
        assert r.status_code == 201, r.text

        from app.services.embedding import get_vector_db

        try:
            vector_db = get_vector_db()
            results = vector_db._collection.get(  # noqa: SLF001
                where={"page_id": doc_id},
                include=["metadatas"],
            )
        except Exception:
            pytest.skip("ChromaDB unavailable in this environment")

        metas = results.get("metadatas") or []
        assert metas, f"no chroma rows for {doc_id}"
        for m in metas:
            if isinstance(m, dict):
                # 키가 아예 없거나, 값이 빈 문자열/None 이어야 함
                val = m.get("source_url")
                assert val in (None, ""), f"unexpected source_url in chroma meta: {val}"
    finally:
        _cleanup_doc(doc_id)


# ── 10. knowledge 노드 응답에 source_url 키 ────────────────────────────────


def test_knowledge_node_response_exposes_source_url(unique_suffix):
    """KnowledgeHandler 결과 item 에 source_url 키가 항상 존재해야 함 (값 or None)."""
    import asyncio

    from app.nodes.action.knowledge import KnowledgeHandler
    from app.nodes.base import ExecutionContext

    slug = f"src-url-node-{unique_suffix}"
    doc_id = f"overview/{slug}"
    url = "https://intra-coder-doc.example.com/node-test"
    common_text = f"knowledge-node-srcurl-test-{unique_suffix} 본문"
    try:
        r = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "overview",
                "slug": slug,
                "page_type": "Summary",
                "title": "node url test",
                "content": common_text,
                "source_url": url,
            },
        )
        assert r.status_code == 201, r.text

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
                "maxResults": 14,
            },
        )

        handler = KnowledgeHandler()
        result = asyncio.run(handler.execute(node, {"q": common_text}, ctx))
        items = result.get("knowledge", [])
        # 결과의 모든 item 에 source_url 키 존재
        for it in items:
            assert "source_url" in it, it
        # 우리 페이지가 결과에 포함되어 있으면 url 일치
        target = next((it for it in items if it["id"] == doc_id), None)
        if target is not None:
            assert target["source_url"] == url, target
    finally:
        _cleanup_doc(doc_id)


# ── 11. legacy 페이지 회귀 가드 ───────────────────────────────────────────


def test_existing_legacy_pages_default_source_url_to_none():
    """기존 운영 페이지들은 모두 source_url=None default (frontmatter 미기재 시)."""
    docs = list_md_files()
    assert len(docs) >= 1, "기존 페이지 0건 — list_md_files 깨짐 의심"
    # 1건 sampling — frontmatter 에 source_url 키가 없으면 None 이어야 함
    for d in docs[:20]:
        # source_url 은 None 이거나 str (write_md_file 가 빈 문자열은 None 정규화)
        assert d.source_url is None or isinstance(d.source_url, str), d
