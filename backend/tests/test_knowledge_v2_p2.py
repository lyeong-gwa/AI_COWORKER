"""Karpathy v2 P2 acceptance — POST/PUT/DELETE/raw/backlinks 통합 검증.

검증 시나리오 (plan §13 P2 + 사용자 지시 11종):
    1.  POST codeeyes/codeeyes-overview Summary, links 자동 채움, _log/_index 갱신
    2.  POST page_type 누락 → 422
    3.  POST category enum 위반 → 422
    4.  POST 한글 slug → 422
    5.  POST 중복 id → 409
    6.  POST codeeyes/codeeyes-system Entity — overview → system 링크 확립
    7.  GET /knowledge/codeeyes/codeeyes-system/backlinks → ["codeeyes/codeeyes-overview"]
    8.  DELETE codeeyes/codeeyes-system (backlink 보유) → 409 with backlinks
    9.  DELETE ?force=true → 200, overview 본문이 [[deleted:...]] 로 치환됨 + version=2
    10. POST /knowledge/raw small text → RawSource 반환, 파일 존재
    11. PUT codeeyes/codeeyes-overview {content:"updated body"} → version=3, changelog 1행 추가
"""

from __future__ import annotations

import asyncio
import io
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from app.main import app
from app.core.database import async_session_maker
from app.models.knowledge_changelog import KnowledgeChangelogEntry


client = TestClient(app, raise_server_exceptions=False)


# ── 테스트 격리: 고유 prefix 부여 + 각 테스트 후 정리 ─────────────────────


@pytest.fixture
def unique_suffix() -> str:
    return uuid.uuid4().hex[:8]


def _cleanup_doc(doc_id: str) -> None:
    """force 삭제로 정리. 404 무시."""
    try:
        client.delete(f"/api/v1/knowledge/{doc_id}?force=true")
    except Exception:
        pass


def _count_changelog_for(knowledge_id: str) -> int:
    async def _q():
        async with async_session_maker() as db:
            r = await db.execute(
                select(func.count(KnowledgeChangelogEntry.id)).where(
                    KnowledgeChangelogEntry.knowledge_id == knowledge_id
                )
            )
            return int(r.scalar() or 0)

    return asyncio.run(_q())


# ── 시나리오 1: POST 정상 생성 + links 자동 + log/index 갱신 ──────────────


def test_s1_post_creates_doc_with_link_parsing_and_index(unique_suffix):
    slug = f"s1-overview-{unique_suffix}"
    doc_id = f"codeeyes/{slug}"
    target_slug = f"s1-system-{unique_suffix}"
    target_id = f"codeeyes/{target_slug}"
    try:
        r = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "codeeyes",
                "slug": slug,
                "page_type": "Summary",
                "title": "Overview S1",
                "content": f"본문 with [[{target_id}]]",
                "tags": [],
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["id"] == doc_id
        assert body["pageType"] == "Summary"
        assert body["version"] == 1
        assert body["links"] == [target_id]

        # _log.md 에 create 한 줄 append 되었는지
        from app.core.config import _BACKEND_DIR
        log_path = os.path.join(_BACKEND_DIR, "data", "knowledge", "_log.md")
        with open(log_path, "r", encoding="utf-8") as f:
            log_content = f.read()
        assert f"create | {doc_id} | v1" in log_content

        # _index-codeeyes.md 에 행 추가됨
        idx_path = os.path.join(
            _BACKEND_DIR, "data", "knowledge", "codeeyes", "_index-codeeyes.md"
        )
        with open(idx_path, "r", encoding="utf-8") as f:
            idx_content = f.read()
        assert doc_id in idx_content
        assert "Overview S1" in idx_content
        assert "Summary" in idx_content
    finally:
        _cleanup_doc(doc_id)


# ── 시나리오 2: page_type 누락 → 422 ──────────────────────────────────────


def test_s2_post_missing_page_type_returns_422(unique_suffix):
    r = client.post(
        "/api/v1/knowledge",
        json={
            "service": "codeeyes",
            "category": "codeeyes",
            "slug": f"s2-{unique_suffix}",
            "title": "no page type",
            "content": "x",
        },
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


# ── 시나리오 3: 알 수 없는 카테고리 → 422 ───────────────────────────────


def test_s3_post_unknown_category_returns_422(unique_suffix):
    r = client.post(
        "/api/v1/knowledge",
        json={
            "service": "codeeyes",
            "category": "unknown-cat",
            "slug": f"s3-{unique_suffix}",
            "page_type": "Summary",
            "title": "unknown cat",
            "content": "x",
        },
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    details = body["error"].get("details", {})
    # validate_category 가 enum 목록을 details 로 전달
    assert details.get("field") == "category" or "unknown-cat" in str(details)


# ── 시나리오 4: 한글 slug → 422 ────────────────────────────────────────────


def test_s4_post_korean_slug_returns_422(unique_suffix):
    r = client.post(
        "/api/v1/knowledge",
        json={
            "service": "codeeyes",
            "category": "codeeyes",
            "slug": "한글slug",
            "page_type": "Summary",
            "title": "korean slug",
            "content": "x",
        },
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    # validate_slug 가 422 로 통과시키거나 (서버측 validator) — 우리는 details.field=slug 보장
    details = body["error"].get("details", {})
    if details.get("field"):
        assert details["field"] == "slug"


# ── 시나리오 5: 중복 id → 409 ─────────────────────────────────────────────


def test_s5_post_duplicate_id_returns_409(unique_suffix):
    slug = f"s5-overview-{unique_suffix}"
    doc_id = f"codeeyes/{slug}"
    try:
        # 첫 등록
        r1 = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "codeeyes",
                "slug": slug,
                "page_type": "Summary",
                "title": "First",
                "content": "first body",
            },
        )
        assert r1.status_code == 201, r1.text
        # 중복 등록
        r2 = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "codeeyes",
                "slug": slug,
                "page_type": "Summary",
                "title": "Duplicate",
                "content": "dup body",
            },
        )
        assert r2.status_code == 409, r2.text
        body = r2.json()
        assert body["error"]["code"] == "CONFLICT"
        assert body["error"]["details"]["id"] == doc_id
    finally:
        _cleanup_doc(doc_id)


# ── 시나리오 6: 두 페이지 — overview → system 링크 확립 ──────────────────


def test_s6_overview_links_to_system(unique_suffix):
    over_slug = f"s6-overview-{unique_suffix}"
    sys_slug = f"s6-system-{unique_suffix}"
    over_id = f"codeeyes/{over_slug}"
    sys_id = f"codeeyes/{sys_slug}"
    try:
        # overview 가 system 을 참조
        r1 = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "codeeyes",
                "slug": over_slug,
                "page_type": "Summary",
                "title": "S6 Overview",
                "content": f"see [[{sys_id}]] for detail",
            },
        )
        assert r1.status_code == 201, r1.text
        assert r1.json()["links"] == [sys_id]

        # system 등록 (Entity)
        r2 = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "codeeyes",
                "slug": sys_slug,
                "page_type": "Entity",
                "title": "S6 System",
                "content": "X",
            },
        )
        assert r2.status_code == 201, r2.text
        assert r2.json()["links"] == []
    finally:
        _cleanup_doc(over_id)
        _cleanup_doc(sys_id)


# ── 시나리오 7: GET backlinks ─────────────────────────────────────────────


def test_s7_backlinks_returns_owners(unique_suffix):
    over_slug = f"s7-overview-{unique_suffix}"
    sys_slug = f"s7-system-{unique_suffix}"
    over_id = f"codeeyes/{over_slug}"
    sys_id = f"codeeyes/{sys_slug}"
    try:
        client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "codeeyes",
                "slug": over_slug,
                "page_type": "Summary",
                "title": "S7 Overview",
                "content": f"see [[{sys_id}]]",
            },
        )
        client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "codeeyes",
                "slug": sys_slug,
                "page_type": "Entity",
                "title": "S7 System",
                "content": "X",
            },
        )
        r = client.get(f"/api/v1/knowledge/{sys_id}/backlinks")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == sys_id
        assert over_id in body["backlinks"]
    finally:
        _cleanup_doc(over_id)
        _cleanup_doc(sys_id)


# ── 시나리오 8: DELETE with backlinks → 409 ───────────────────────────────


def test_s8_delete_with_backlinks_returns_409(unique_suffix):
    over_slug = f"s8-overview-{unique_suffix}"
    sys_slug = f"s8-system-{unique_suffix}"
    over_id = f"codeeyes/{over_slug}"
    sys_id = f"codeeyes/{sys_slug}"
    try:
        client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "codeeyes",
                "slug": over_slug,
                "page_type": "Summary",
                "title": "S8 Overview",
                "content": f"see [[{sys_id}]]",
            },
        )
        client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "codeeyes",
                "slug": sys_slug,
                "page_type": "Entity",
                "title": "S8 System",
                "content": "X",
            },
        )
        r = client.delete(f"/api/v1/knowledge/{sys_id}")
        assert r.status_code == 409, r.text
        body = r.json()
        assert body["error"]["code"] == "CONFLICT"
        assert over_id in body["error"]["details"]["backlinks"]
    finally:
        _cleanup_doc(over_id)
        _cleanup_doc(sys_id)


# ── 시나리오 9: DELETE force=true → 200 + cascade 치환 ───────────────────


def test_s9_delete_force_cascades_deleted_marker(unique_suffix):
    over_slug = f"s9-overview-{unique_suffix}"
    sys_slug = f"s9-system-{unique_suffix}"
    over_id = f"codeeyes/{over_slug}"
    sys_id = f"codeeyes/{sys_slug}"
    try:
        # overview 가 system 참조
        client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "codeeyes",
                "slug": over_slug,
                "page_type": "Summary",
                "title": "S9 Overview",
                "content": f"see [[{sys_id}]]",
            },
        )
        client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "codeeyes",
                "slug": sys_slug,
                "page_type": "Entity",
                "title": "S9 System",
                "content": "X",
            },
        )
        # force 삭제
        r = client.delete(f"/api/v1/knowledge/{sys_id}?force=true")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["deleted"] is True
        assert over_id in body["cascadedBacklinks"]

        # overview 본문에 [[deleted:...]] 마커, version=2
        r2 = client.get(f"/api/v1/knowledge/{over_id}")
        assert r2.status_code == 200, r2.text
        owner = r2.json()
        assert f"[[deleted:{sys_id}]]" in owner["content"]
        assert owner["version"] == 2
    finally:
        _cleanup_doc(over_id)
        _cleanup_doc(sys_id)


# ── 시나리오 10: POST /raw small text file ───────────────────────────────


def test_s10_raw_upload_returns_rawsource_and_persists_blob():
    small = b"hello raw"
    r = client.post(
        "/api/v1/knowledge/raw",
        files={"file": ("hello.txt", io.BytesIO(small), "text/plain")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["filename"] == "hello.txt"
    assert body["mime"] == "text/plain"
    assert body["size"] == len(small)
    assert body["contentHash"]
    blob_path = body["originalBlobPath"]
    # backend/ 기준 상대경로
    from app.core.config import _BACKEND_DIR
    abs_path = os.path.join(_BACKEND_DIR, blob_path)
    assert os.path.exists(abs_path), f"blob not found at {abs_path}"
    with open(abs_path, "rb") as f:
        assert f.read() == small


# ── 시나리오 11: PUT version 자동 증가 + changelog ───────────────────────


def test_s11_put_increments_version_and_adds_changelog(unique_suffix):
    over_slug = f"s11-overview-{unique_suffix}"
    sys_slug = f"s11-system-{unique_suffix}"
    over_id = f"codeeyes/{over_slug}"
    sys_id = f"codeeyes/{sys_slug}"
    try:
        # 사전: overview → system 링크 → force 삭제로 cascade → overview v=2
        client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "codeeyes",
                "slug": over_slug,
                "page_type": "Summary",
                "title": "S11 Overview",
                "content": f"see [[{sys_id}]]",
            },
        )
        client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "codeeyes",
                "slug": sys_slug,
                "page_type": "Entity",
                "title": "S11 System",
                "content": "X",
            },
        )
        # force delete sys → cascade overview v=2
        r_del = client.delete(f"/api/v1/knowledge/{sys_id}?force=true")
        assert r_del.status_code == 200, r_del.text

        # changelog 사전 카운트 (create + lint-fix cascade = 2)
        before = _count_changelog_for(over_id)
        assert before >= 2

        # PUT 업데이트
        r = client.put(
            f"/api/v1/knowledge/{over_id}",
            json={"content": "updated body"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["version"] == 3, f"expected v3, got v{body['version']}"
        assert body.get("changelogId")

        after = _count_changelog_for(over_id)
        assert after == before + 1, (
            f"expected +1 changelog, got before={before} after={after}"
        )
    finally:
        _cleanup_doc(over_id)
        _cleanup_doc(sys_id)
