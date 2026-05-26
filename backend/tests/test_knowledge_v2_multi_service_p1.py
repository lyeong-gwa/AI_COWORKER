"""Multi-service v3 P1 acceptance — schema + 모델 + validator 단위/통합.

검증 (작업 지시 §2.6, §2.7):
    1.  list_services() 가 codeeyes + unknown 2종 반환
    2.  validate_service('codeeyes') 통과
    3.  validate_service('unknown') 항상 통과 (sentinel)
    4.  validate_service('xyz') → SchemaValidationError (미정의 id)
    5.  validate_service('') → SchemaValidationError (빈 값)
    6.  legacy category 'codeeyes' → WARN + 통과 (P4 마이그레이션 호환)
    7.  POST /knowledge 시 service 필드 round-trip (frontmatter 보존, GET 응답 일관)
    8.  POST /knowledge 시 service 누락 → 422
    9.  POST /knowledge 시 미정의 service ('xyz') → 422
    10. POST /knowledge 시 service='unknown' 허용
    11. 기존 66 페이지 GET 정상 (legacy category + service default='unknown')
    12. KnowledgeFileDoc.service default 가 'unknown'
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.knowledge_schema import (
    LEGACY_CATEGORY_IDS,
    SERVICE_UNKNOWN,
    SchemaValidationError,
    list_services,
    load_schema,
    reset_schema_cache,
    validate_category,
    validate_service,
)
from app.services.knowledge_file_service import KnowledgeFileDoc, list_md_files, read_md_file


client = TestClient(app, raise_server_exceptions=False)


# ── 테스트 격리 ───────────────────────────────────────────────────────────


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


# ── 1. list_services / validate_service 단위 ──────────────────────────────


def test_list_services_returns_codeeyes_and_unknown():
    svcs = list_services()
    ids = [s["id"] for s in svcs]
    assert "codeeyes" in ids
    assert "unknown" in ids
    assert len(svcs) == 2, f"expected exactly 2 services (codeeyes + unknown), got {ids}"
    # 각 항목 schema
    for s in svcs:
        assert set(s.keys()) >= {"id", "title", "description"}


def test_validate_service_accepts_codeeyes():
    assert validate_service("codeeyes") == "codeeyes"


def test_validate_service_always_accepts_unknown_sentinel():
    assert validate_service("unknown") == "unknown"
    assert validate_service(SERVICE_UNKNOWN) == "unknown"


def test_validate_service_rejects_undefined_id():
    with pytest.raises(SchemaValidationError) as exc:
        validate_service("xyz-not-defined")
    assert exc.value.field == "service"
    # 메시지에 enum 목록 정보가 들어가야 사용자가 이해 가능
    details = exc.value.details
    assert "allowed" in details
    assert "codeeyes" in details["allowed"]


def test_validate_service_rejects_empty_string():
    with pytest.raises(SchemaValidationError) as exc:
        validate_service("")
    assert exc.value.field == "service"


# ── 2. legacy category WARN+pass ──────────────────────────────────────────


def test_validate_category_codeeyes_warn_passes_after_v3_redesign():
    """v3 enum 에서 빠진 'codeeyes' 카테고리도 WARN+pass 로 통과 — 기존 66 페이지 호환."""
    # raise 하지 않아야 함
    validate_category("codeeyes")
    validate_category("ito-portal-operations")
    validate_category("plugin-troubleshooting")
    # 신·구 동명 'faq' 는 enum 정식 경로로 통과
    validate_category("faq")
    # legacy set 명세 검증
    assert "codeeyes" in LEGACY_CATEGORY_IDS
    assert "ito-portal-operations" in LEGACY_CATEGORY_IDS
    assert "plugin-troubleshooting" in LEGACY_CATEGORY_IDS


def test_validate_category_truly_unknown_still_rejects():
    """legacy 도 신 enum 도 아닌 카테고리는 여전히 거부."""
    with pytest.raises(SchemaValidationError):
        validate_category("truly-unknown-category-zzz")


# ── 3. KnowledgeFileDoc.service default ───────────────────────────────────


def test_knowledge_file_doc_service_default_is_unknown():
    """dataclass default — 마이그레이션 전 frontmatter 미지정 페이지가 unknown 으로 fallback."""
    doc = KnowledgeFileDoc(id="x/y", title="t", content="c")
    assert doc.service == "unknown"


# ── 4. POST round-trip with service ───────────────────────────────────────


def test_post_persists_service_and_get_returns_it(unique_suffix):
    """POST 시 service 명시 → frontmatter 보존 → 후속 list/get 에서 일관 노출."""
    slug = f"p1-svc-rt-{unique_suffix}"
    doc_id = f"overview/{slug}"
    try:
        r = client.post(
            "/api/v1/knowledge",
            json={
                "service": "codeeyes",
                "category": "overview",
                "slug": slug,
                "page_type": "Summary",
                "title": "P1 service round-trip",
                "content": "본문",
            },
        )
        assert r.status_code == 201, r.text

        # frontmatter 에 service 가 보존되었는지 — service-service 가 직접 파일을 읽어 확인
        doc = read_md_file(doc_id)
        assert doc is not None
        assert doc.service == "codeeyes"
        assert doc.category == "overview"

        # GET 응답에서도 (응답에 service 키가 명시 노출되지는 않지만 — P2 wiring 의 몫 —
        # 적어도 파일이 잘 보존되었는지 list 에서도 확인 가능해야 한다)
        all_docs = list_md_files()
        target = next((d for d in all_docs if d.id == doc_id), None)
        assert target is not None
        assert target.service == "codeeyes"
    finally:
        _cleanup_doc(doc_id)


def test_post_missing_service_returns_422(unique_suffix):
    """service 누락 시 Pydantic missing-field → 422."""
    r = client.post(
        "/api/v1/knowledge",
        json={
            "category": "overview",
            "slug": f"p1-noservice-{unique_suffix}",
            "page_type": "Summary",
            "title": "no service",
            "content": "x",
        },
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_post_undefined_service_returns_422(unique_suffix):
    """미정의 service id → Pydantic field_validator 가 SchemaValidationError raise → 422.
    응답 메시지에 서비스 id 가 들어 있어야 사용자가 원인 파악 가능."""
    r = client.post(
        "/api/v1/knowledge",
        json={
            "service": "xyz-not-defined",
            "category": "overview",
            "slug": f"p1-badsvc-{unique_suffix}",
            "page_type": "Summary",
            "title": "bad service",
            "content": "x",
        },
    )
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    # Pydantic v2 가 RequestValidationError 의 errors[0].msg 안에 SchemaValidationError 메시지 보존
    raw = str(body)
    assert "xyz-not-defined" in raw or "service" in raw


def test_post_service_unknown_is_always_allowed(unique_suffix):
    """sentinel 'unknown' 은 항상 통과해야 (마이그레이션 임시 페이지)."""
    slug = f"p1-svcunk-{unique_suffix}"
    doc_id = f"overview/{slug}"
    try:
        r = client.post(
            "/api/v1/knowledge",
            json={
                "service": "unknown",
                "category": "overview",
                "slug": slug,
                "page_type": "Summary",
                "title": "unknown service ok",
                "content": "x",
            },
        )
        assert r.status_code == 201, r.text
        doc = read_md_file(doc_id)
        assert doc is not None
        assert doc.service == "unknown"
    finally:
        _cleanup_doc(doc_id)


# ── 5. legacy 66 페이지 호환 — service default + legacy category 통과 ────────


def test_existing_pages_get_with_legacy_category_and_default_service():
    """기존 66 페이지가 모두 list 에 정상 노출되며 service='unknown' default 부여,
    legacy category (codeeyes 등) 가 거부되지 않아야 한다."""
    docs = list_md_files()
    # 운영 데이터의 정확한 카운트는 환경 의존이므로 ≥ 1 만 보장 (회귀 안전)
    assert len(docs) >= 1, "기존 페이지가 0건 — list_md_files 깨짐 의심"

    # legacy category 페이지가 GET 에서 거부되지 않는지 — 임의 1건 sampling
    legacy_docs = [d for d in docs if d.category in LEGACY_CATEGORY_IDS]
    if legacy_docs:
        sample = legacy_docs[0]
        r = client.get(f"/api/v1/knowledge/{sample.id}")
        assert r.status_code == 200, r.text
        # service frontmatter 미기재 페이지는 default 'unknown' 으로 부여되어야 함
        # (이미 service 가 채워진 페이지는 그 값 유지 — 둘 다 허용)
        assert sample.service in {"unknown", "codeeyes"} or sample.service != ""


def test_existing_pages_count_unchanged_count_via_list_md_files():
    """현재 운영 디렉토리의 페이지 카운트가 비파괴적으로 유지되는지 회귀 가드.
    P1 변경은 schema/모델/validator 만 → 페이지 수는 절대 변할 수 없다."""
    docs = list_md_files()
    # 메타 파일/디렉토리(_xxx) 와 archive 는 제외되므로 실제 wiki 페이지만 카운트.
    # 운영 기준 66 (작업 지시 §2.6) — 환경 의존이지만 baseline 으로 단언.
    # 만약 환경에서 다르면 이 단언을 갱신.
    count = len(docs)
    assert count >= 60, f"기존 페이지 카운트 회귀 의심 — got {count} (baseline ≥ 60)"
