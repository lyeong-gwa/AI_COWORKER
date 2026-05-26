"""노드 카탈로그 정합성 테스트 (Phase 2a + 인스턴스DB Phase A 확장).

검증 포인트:
1. CATALOG에 정확히 13개 항목 (11종 범용 + 인스턴스DB 노드 2종)
2. 각 defType이 NodeDefType enum의 value와 정합
3. connectsWellWith에 나열된 defType이 모두 카탈로그에 존재 (dangling reference 0)
4. get_entry(존재) 성공, get_entry(없음) None
5. 카테고리 분포가 설계서(섹션 4) + 인스턴스DB 확장 분포와 일치
"""

from app.core.constants import NodeDefType, CATALOG_NODE_TYPE_VALUES
from app.nodes.catalog import CATALOG, NodeCatalogEntry, get_catalog, get_entry


# 설계서 섹션 4의 11종 + 인스턴스DB Phase A 추가 2종
EXPECTED_DEF_TYPES = {
    "form-start",
    "api-start",
    "ai-custom",
    "ai-api-router",
    "sorter",
    "unpacker",
    "mapper",
    "api-call",
    "knowledge",
    "result",
    "markdown-viewer",
    "instance-db-insert",
    "instance-db-lookup",
}


def test_catalog_has_exactly_thirteen_entries():
    assert len(CATALOG) == 13, f"카탈로그 항목 수는 13이어야 함 (실제 {len(CATALOG)})"


def test_catalog_def_types_match_spec():
    actual = {e.defType for e in CATALOG}
    assert actual == EXPECTED_DEF_TYPES, (
        f"카탈로그 defType 집합이 설계서 11종과 불일치.\n"
        f"누락: {EXPECTED_DEF_TYPES - actual}\n"
        f"초과: {actual - EXPECTED_DEF_TYPES}"
    )


def test_all_def_types_are_in_node_def_type_enum():
    """각 entry의 defType이 NodeDefType enum value에 존재해야 한다."""
    enum_values = {m.value for m in NodeDefType}
    for entry in CATALOG:
        assert entry.defType in enum_values, (
            f"카탈로그 defType '{entry.defType}'이 NodeDefType enum에 없음"
        )


def test_catalog_matches_constants_catalog_set():
    """constants.py의 CATALOG_NODE_TYPE_VALUES 집합과 정합."""
    actual = {e.defType for e in CATALOG}
    assert actual == CATALOG_NODE_TYPE_VALUES, (
        "CATALOG과 constants.CATALOG_NODE_TYPE_VALUES가 서로 다르다."
    )


def test_no_dangling_connects_well_with_references():
    """connectsWellWith의 모든 항목이 카탈로그에 정의된 defType이어야 한다."""
    all_types = {e.defType for e in CATALOG}
    for entry in CATALOG:
        for ref in entry.connectsWellWith:
            assert ref in all_types, (
                f"노드 '{entry.defType}'의 connectsWellWith='{ref}'가 카탈로그에 없음"
            )


def test_each_entry_has_required_metadata():
    """label, purpose, category 는 반드시 비어있지 않아야 한다."""
    for entry in CATALOG:
        assert entry.label, f"{entry.defType}: label 비어있음"
        assert entry.purpose, f"{entry.defType}: purpose 비어있음"
        assert entry.category, f"{entry.defType}: category 비어있음"


def test_starters_have_requires_upstream_false():
    starters = [e for e in CATALOG if e.category == "starter"]
    assert len(starters) == 2, "starter는 form-start, api-start 2개여야 한다"
    for e in starters:
        assert e.requiresUpstream is False, (
            f"starter {e.defType}는 requiresUpstream=False여야 한다"
        )


def test_non_starters_have_requires_upstream_true():
    for e in CATALOG:
        if e.category != "starter":
            assert e.requiresUpstream is True, (
                f"{e.defType}({e.category})는 requiresUpstream=True여야 한다"
            )


def test_category_distribution_matches_spec():
    """카테고리 분포: starter 2, ai 2, logic 3, action 4 (api-call/knowledge/instance-db-insert/instance-db-lookup), output 2."""
    from collections import Counter
    counts = Counter(e.category for e in CATALOG)
    assert counts == {
        "starter": 2,
        "ai": 2,
        "logic": 3,
        "action": 4,
        "output": 2,
    }, f"카테고리 분포 불일치: {dict(counts)}"


def test_each_entry_has_at_least_one_use_case():
    for entry in CATALOG:
        assert len(entry.useCases) >= 1, (
            f"{entry.defType}: useCases가 비어있음 (CLI few-shot 힌트 필요)"
        )


def test_get_catalog_returns_all_entries():
    assert get_catalog() is CATALOG or get_catalog() == CATALOG


def test_get_entry_existing():
    entry = get_entry("form-start")
    assert entry is not None
    assert entry.defType == "form-start"
    assert isinstance(entry, NodeCatalogEntry)


def test_get_entry_missing_returns_none():
    assert get_entry("nonexistent-node") is None
    assert get_entry("") is None


def test_unpacker_is_marked_as_produces_array():
    """unpacker는 반복 실행을 위해 producesArray=True여야 한다 (CLI가 unpacker 후 연결 판단)."""
    entry = get_entry("unpacker")
    assert entry is not None
    assert entry.producesArray is True


def test_api_start_has_required_api_definition_id():
    entry = get_entry("api-start")
    assert entry is not None
    required_fields = {c.name for c in entry.config if c.required}
    assert "apiDefinitionId" in required_fields


def test_api_call_has_required_api_definition_id():
    entry = get_entry("api-call")
    assert entry is not None
    required_fields = {c.name for c in entry.config if c.required}
    assert "apiDefinitionId" in required_fields


def test_sorter_rules_required():
    entry = get_entry("sorter")
    assert entry is not None
    required_fields = {c.name for c in entry.config if c.required}
    assert "rules" in required_fields


def test_unpacker_array_field_required():
    entry = get_entry("unpacker")
    assert entry is not None
    required_fields = {c.name for c in entry.config if c.required}
    assert "arrayField" in required_fields


def test_mapper_required_fields():
    entry = get_entry("mapper")
    assert entry is not None
    required_fields = {c.name for c in entry.config if c.required}
    assert "warehouseNodeId" in required_fields
    assert "matchKey" in required_fields


def test_instance_db_entries_marked_as_infra_purpose():
    """LOW-1: instance-db-insert / instance-db-lookup 의 purpose 가 '인프라' 표현을 포함해야 한다.

    LLM CLI 가 향후 비슷한 인프라 노드를 무분별 신설 요청하지 않도록 경계 문구가 필요.
    """
    insert_entry = get_entry("instance-db-insert")
    assert insert_entry is not None
    assert "인프라" in insert_entry.purpose, (
        f"instance-db-insert.purpose 에 '인프라' 표현이 없음: {insert_entry.purpose}"
    )

    lookup_entry = get_entry("instance-db-lookup")
    assert lookup_entry is not None
    assert "인프라" in lookup_entry.purpose, (
        f"instance-db-lookup.purpose 에 '인프라' 표현이 없음: {lookup_entry.purpose}"
    )
