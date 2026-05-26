"""Knowledge v2 schema layer 단위 테스트 (P1 acceptance §13).

검증:
1. `_schema.yaml` 로드 성공 — 4 카테고리, 5 page_type
2. `validate_category` enum pass / fail
3. `validate_page_type` enum pass / fail
4. `validate_slug` 영문 kebab-case 강제 — 한글 거부, 길이 초과 거부
5. `list_categories` 정렬·매핑
6. 캐시: 동일 mtime 두 번째 호출이 같은 인스턴스 반환

설계 근거: `.omc/plans/지식-karpathy-v2.md` §8.2.
"""

from __future__ import annotations

import pytest

from app.services.knowledge_schema import (
    ALLOWED_PAGE_TYPES,
    KnowledgeSchema,
    SchemaValidationError,
    list_categories,
    load_schema,
    reset_schema_cache,
    validate_category,
    validate_page_type,
    validate_slug,
)


@pytest.fixture(autouse=True)
def _reset_schema_cache_between_tests():
    """매 테스트마다 캐시 무효화하여 fixtures 가 상호 영향 없게."""
    reset_schema_cache()
    yield
    reset_schema_cache()


def test_load_schema_returns_functional_categories():
    """`_schema.yaml` v3 의 기능형 카테고리가 모두 로드된다.

    multi-service v3 (`.omc/plans/지식-multi-service.md` §2.1) 에서 카테고리는
    서비스명 기반에서 기능형으로 재정의되었다. 신 6+종 enum 중 핵심 셋이 들어
    있는지 검증한다. legacy id (`codeeyes` 등) 는 enum 에서 빠지지만 validator 가
    WARN+통과로 호환 유지한다 (별도 테스트 참조).
    """
    schema = load_schema()
    expected = {"overview", "operations-guide", "troubleshooting", "faq", "integration", "policy"}
    assert expected.issubset(schema.category_ids), (
        f"category_ids missing — got {schema.category_ids}, expected superset of {expected}"
    )


def test_load_schema_has_five_page_types():
    """`_schema.yaml` 의 5 page_type 가 모두 로드된다."""
    schema = load_schema()
    assert set(schema.page_types.keys()) == ALLOWED_PAGE_TYPES


def test_load_schema_is_cached_by_mtime():
    """첫 호출과 두 번째 호출이 같은 인스턴스 — mtime 동일."""
    a = load_schema()
    b = load_schema()
    assert a is b, "캐시 미스 — load_schema 가 매번 새 인스턴스 반환"


def test_validate_category_passes_for_known_id():
    validate_category("codeeyes")  # raise X


def test_validate_category_raises_for_unknown_id():
    with pytest.raises(SchemaValidationError) as exc:
        validate_category("nonexistent-category")
    assert exc.value.field == "category"
    assert "nonexistent-category" in str(exc.value)


def test_validate_category_soft_passes_when_schema_missing(tmp_path, monkeypatch):
    """`_schema.yaml` 부재 — 부트스트랩 단계 호환 (silent pass)."""
    empty = KnowledgeSchema()  # categories = {}
    assert empty.category_ids == set()
    # 빈 schema 직접 주입 → soft pass
    validate_category("anything", schema=empty)


@pytest.mark.parametrize("pt", sorted(ALLOWED_PAGE_TYPES))
def test_validate_page_type_passes_for_all_enum_values(pt):
    validate_page_type(pt)


def test_validate_page_type_raises_for_unknown():
    with pytest.raises(SchemaValidationError) as exc:
        validate_page_type("Tutorial")
    assert exc.value.field == "page_type"


@pytest.mark.parametrize("good_slug", [
    "codeeyes-overview",
    "abc",
    "a1-b2-c3",
    "x",
    "a-b-c-d-e",
])
def test_validate_slug_accepts_kebab_case(good_slug):
    validate_slug(good_slug)


@pytest.mark.parametrize("bad_slug", [
    "",                       # empty
    "한글슬러그",                # 한글 금지
    "Upper-Case",             # 대문자 금지
    "trailing-",              # trailing hyphen
    "-leading",               # leading hyphen
    "double--hyphen",         # double hyphen
    "with space",             # 공백 금지
    "with_underscore",        # underscore 금지
])
def test_validate_slug_rejects_invalid_inputs(bad_slug):
    with pytest.raises(SchemaValidationError) as exc:
        validate_slug(bad_slug)
    assert exc.value.field == "slug"


def test_validate_slug_rejects_too_long():
    schema = load_schema()
    max_len = schema.max_slug_length
    too_long = ("a" + "-a" * max_len)[: max_len + 5]  # >= max_len + something
    # 보장: 길이 초과
    assert len(too_long) > max_len
    with pytest.raises(SchemaValidationError) as exc:
        validate_slug(too_long)
    assert exc.value.field == "slug"


def test_list_categories_returns_sorted_id_title_description():
    cats = list_categories()
    ids = [c["id"] for c in cats]
    assert ids == sorted(ids), "list_categories 가 id 순 정렬을 반환하지 않음"
    for c in cats:
        assert set(c.keys()) >= {"id", "title", "description"}
