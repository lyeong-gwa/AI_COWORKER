"""지식 그래프 재구성 Phase 1 — backend acceptance.

`.omc/plans/지식-그래프-재구성.md` Phase 1 §3.5.

검증 시나리오:
    T1.  빈 호출 (필터로 0 페이지) → nodes/edges/communities 모두 빈 배열.
    T2.  3 페이지 fixture + 명시 [[link]] 2개 → explicit 엣지만 검출 (kind=explicit, weight=1.0).
    T3.  implicit_threshold 를 매우 낮게 (-1.0) → explicit 외 implicit 엣지가 추가됨.
    T4.  implicit_max_per_page=1 + threshold=-1.0 → 페이지당 implicit 엣지 ≤ 1.
    T5.  Louvain community 분할 — community id 는 [0..N-1], 각 페이지는 정확히 1개 community.
    T6.  godScore 모든 노드에서 0.0 ≤ score ≤ 1.0.
    T7.  GET /knowledge/edge?from=X&to=Y — 응답 형식 + edge.kind.
    T8.  POST /knowledge/edge/promote — A 본문에 [[B]] 추가, version+1, linkAdded=True.
    T9.  이미 explicit 한 페어 promote → 409.
    T10. service/category 필터 — 필터링 정상 동작.

기존 230 회귀 0 유지가 목표.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.knowledge_graph_builder import build_graph


client = TestClient(app, raise_server_exceptions=False)


# ── 헬퍼 ─────────────────────────────────────────────────────────────────


@pytest.fixture
def unique_suffix() -> str:
    return uuid.uuid4().hex[:8]


def _cleanup(doc_ids: List[str]) -> None:
    for did in doc_ids:
        try:
            client.delete(f"/api/v1/knowledge/{did}?force=true")
        except Exception:
            pass


def _post_page(
    *,
    slug: str,
    title: str,
    content: str,
    category: str = "codeeyes",
    service: str = "codeeyes",
    page_type: str = "Summary",
) -> str:
    r = client.post(
        "/api/v1/knowledge",
        json={
            "service": service,
            "category": category,
            "slug": slug,
            "page_type": page_type,
            "title": title,
            "content": content,
            "tags": [],
        },
    )
    assert r.status_code == 201, r.text
    return f"{category}/{slug}"


def _ids_of(items: List[Dict[str, Any]], key: str = "id") -> List[str]:
    return [it[key] for it in items]


# ── T1: 빈 호출 ──────────────────────────────────────────────────────────


def test_t1_empty_call_returns_empty_graph(unique_suffix):
    # 존재하지 않는 카테고리로 필터 → kept_docs 0
    result = build_graph(category=f"__nope__{unique_suffix}__")
    assert result["nodes"] == []
    assert result["edges"] == []
    assert result["communities"] == []
    meta = result["meta"]
    assert meta["explicitEdgeCount"] == 0
    assert meta["implicitEdgeCount"] == 0
    assert meta["communityCount"] == 0
    assert "implicitThreshold" in meta
    assert "implicitMaxPerPage" in meta


# ── T2: explicit only ────────────────────────────────────────────────────


def test_t2_explicit_edges_only(unique_suffix):
    a = f"t2-a-{unique_suffix}"
    b = f"t2-b-{unique_suffix}"
    c = f"t2-c-{unique_suffix}"
    a_id = f"codeeyes/{a}"
    b_id = f"codeeyes/{b}"
    c_id = f"codeeyes/{c}"

    created: List[str] = []
    try:
        # B 먼저 (A 가 B 를 참조)
        created.append(_post_page(
            slug=b,
            title="T2 B 시스템 구성",
            content="B 페이지는 codeeyes 시스템 구성 정보를 담는다.",
        ))
        created.append(_post_page(
            slug=c,
            title="T2 C 운영 가이드",
            content="C 페이지는 codeeyes 운영 가이드를 정리한다.",
        ))
        # A 가 B 와 C 둘 다 명시 참조
        created.append(_post_page(
            slug=a,
            title="T2 A 개요",
            content=(
                "A 페이지는 codeeyes 개요다.\n\n"
                f"참고: [[{b_id}]] 와 [[{c_id}]] 를 살펴라."
            ),
        ))

        # implicit_threshold 매우 높게 → implicit 0
        # (그러나 codeeyes 전체에 다른 페이지가 섞이므로 노드만 우리 fixture 로 좁힌다.
        #  여기서는 category=codeeyes 필터에 기존 페이지가 잡힐 수 있으므로
        #  검증은 "우리 3 페이지 사이의 explicit 만" 으로 한정한다.)
        result = build_graph(implicit_threshold=2.0, implicit_max_per_page=5)

        # explicit edge: A→B, A→C 가 포함되어야 함
        our_edges = [
            e for e in result["edges"]
            if e["from"] in {a_id, b_id, c_id} and e["to"] in {a_id, b_id, c_id}
        ]
        explicit_pairs = {(e["from"], e["to"]) for e in our_edges if e["kind"] == "explicit"}
        assert (a_id, b_id) in explicit_pairs
        assert (a_id, c_id) in explicit_pairs

        for e in our_edges:
            if e["kind"] == "explicit":
                assert e["weight"] == 1.0
                assert e["similarity"] is None
                assert e["isBroken"] is False

        # implicit 은 우리 페이지 사이에 0 (threshold=2.0 으로 차단)
        our_implicit = [
            e for e in our_edges if e["kind"] == "implicit"
        ]
        assert len(our_implicit) == 0
    finally:
        _cleanup(created)


# ── T3: implicit 엣지 추가 ───────────────────────────────────────────────


def test_t3_low_threshold_adds_implicit_edges(unique_suffix):
    a = f"t3-a-{unique_suffix}"
    b = f"t3-b-{unique_suffix}"
    c = f"t3-c-{unique_suffix}"
    a_id = f"codeeyes/{a}"
    b_id = f"codeeyes/{b}"
    c_id = f"codeeyes/{c}"

    created: List[str] = []
    try:
        # 의미가 비슷한 본문 — cosine 이 충분히 0 보다 크게 나오도록.
        created.append(_post_page(
            slug=a,
            title="T3 A 점검",
            content="A 페이지는 점검 절차와 운영 가이드를 담는다.",
        ))
        created.append(_post_page(
            slug=b,
            title="T3 B 점검",
            content="B 페이지는 점검 절차의 상세 단계와 운영 절차를 담는다.",
        ))
        created.append(_post_page(
            slug=c,
            title="T3 C 점검",
            content="C 페이지는 점검 절차 운영 매뉴얼이다.",
        ))

        # threshold 음수 → 모든 cosine 통과 (자기자신 제외)
        result = build_graph(implicit_threshold=-1.0, implicit_max_per_page=10)

        # 우리 페이지 사이 implicit 엣지가 1개 이상 존재
        our_implicit = [
            e for e in result["edges"]
            if e["kind"] == "implicit"
            and e["from"] in {a_id, b_id, c_id}
            and e["to"] in {a_id, b_id, c_id}
        ]
        assert len(our_implicit) >= 1, "낮은 threshold 에서 implicit 0건은 비정상"

        for e in our_implicit:
            assert e["kind"] == "implicit"
            assert e["similarity"] is not None
            assert 0.0 <= float(e["weight"]) <= 1.0
            # similarity == weight
            assert float(e["weight"]) == pytest.approx(float(e["similarity"]))
    finally:
        _cleanup(created)


# ── T4: max_per_page 제한 ────────────────────────────────────────────────


def test_t4_max_per_page_caps_implicit(unique_suffix):
    a = f"t4-a-{unique_suffix}"
    b = f"t4-b-{unique_suffix}"
    c = f"t4-c-{unique_suffix}"
    d = f"t4-d-{unique_suffix}"
    a_id = f"codeeyes/{a}"
    ids = [f"codeeyes/{s}" for s in (a, b, c, d)]

    created: List[str] = []
    try:
        for s, title in zip([a, b, c, d], ["A", "B", "C", "D"]):
            created.append(_post_page(
                slug=s,
                title=f"T4 {title} 점검",
                content=f"{title} 페이지는 점검 절차 운영 가이드 매뉴얼이다.",
            ))

        # threshold 음수 + max_per_page=1 → 페이지당 implicit ≤ 1
        result = build_graph(implicit_threshold=-1.0, implicit_max_per_page=1)

        # 페이지 A 가 from 또는 to 로 등장하는 implicit edge 카운트
        our_implicit = [
            e for e in result["edges"]
            if e["kind"] == "implicit"
            and e["from"] in set(ids) and e["to"] in set(ids)
        ]
        # max_per_page 는 from 기준이지만 implicit 는 한 쪽 페이지에서만 추가되므로
        # 각 from 별 카운트가 ≤ 1.
        from_counts: Dict[str, int] = {}
        for e in our_implicit:
            from_counts[e["from"]] = from_counts.get(e["from"], 0) + 1
        for f_id, cnt in from_counts.items():
            assert cnt <= 1, f"{f_id} 의 implicit 엣지 수 {cnt} > 1"
    finally:
        _cleanup(created)


# ── T5: Louvain community 정합 ───────────────────────────────────────────


def test_t5_louvain_communities_partition_all_nodes(unique_suffix):
    a = f"t5-a-{unique_suffix}"
    b = f"t5-b-{unique_suffix}"
    c = f"t5-c-{unique_suffix}"
    a_id = f"codeeyes/{a}"
    b_id = f"codeeyes/{b}"
    c_id = f"codeeyes/{c}"

    created: List[str] = []
    try:
        created.append(_post_page(slug=a, title="T5 A 페이지", content="A 본문 점검."))
        created.append(_post_page(slug=b, title="T5 B 페이지", content="B 본문 운영."))
        created.append(_post_page(slug=c, title="T5 C 페이지", content="C 본문 가이드."))

        result = build_graph()

        # 우리 3 페이지의 community id 가 모두 정수여야 한다
        our_nodes = [
            n for n in result["nodes"]
            if n["id"] in {a_id, b_id, c_id}
        ]
        assert len(our_nodes) == 3
        for n in our_nodes:
            assert isinstance(n.get("community"), int)
            assert n["community"] >= 0

        # communities 응답 필드 검증
        comms = result["communities"]
        assert len(comms) >= 1
        for c in comms:
            assert isinstance(c["id"], int)
            assert isinstance(c["label"], str)
            assert isinstance(c["size"], int)
            assert c["size"] >= 1
            assert c["color"].startswith("#")
    finally:
        _cleanup(created)


# ── T6: godScore 정규화 [0,1] ────────────────────────────────────────────


def test_t6_godscore_normalized_in_unit_range(unique_suffix):
    a = f"t6-a-{unique_suffix}"
    b = f"t6-b-{unique_suffix}"
    c = f"t6-c-{unique_suffix}"
    a_id = f"codeeyes/{a}"
    b_id = f"codeeyes/{b}"
    c_id = f"codeeyes/{c}"

    created: List[str] = []
    try:
        created.append(_post_page(slug=b, title="T6 B", content="B 본문."))
        created.append(_post_page(slug=c, title="T6 C", content="C 본문."))
        created.append(_post_page(
            slug=a,
            title="T6 A 허브",
            content=f"A 는 [[{b_id}]] 와 [[{c_id}]] 를 참조한다.",
        ))

        result = build_graph(implicit_threshold=2.0)  # explicit 만

        for n in result["nodes"]:
            score = float(n["godScore"])
            assert 0.0 <= score <= 1.0, f"{n['id']} godScore={score} 범위 위반"
    finally:
        _cleanup(created)


# ── T7: /knowledge/edge 엔드포인트 ──────────────────────────────────────


def test_t7_edge_endpoint_returns_full_docs_and_edge(unique_suffix):
    a = f"t7-a-{unique_suffix}"
    b = f"t7-b-{unique_suffix}"
    a_id = f"codeeyes/{a}"
    b_id = f"codeeyes/{b}"

    created: List[str] = []
    try:
        created.append(_post_page(slug=b, title="T7 B 페이지", content="B 의 본문 내용."))
        created.append(_post_page(
            slug=a,
            title="T7 A 페이지",
            content=f"A 는 다음을 참조한다: [[{b_id}]]",
        ))

        r = client.get(f"/api/v1/knowledge/edge?from={a_id}&to={b_id}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["from"]["id"] == a_id
        assert data["to"]["id"] == b_id
        # 양쪽 본문 포함
        assert "content" in data["from"]
        assert "content" in data["to"]
        edge = data["edge"]
        assert edge is not None
        assert edge["kind"] == "explicit"
        assert edge["weight"] == 1.0
        assert edge["similarity"] is None
        assert edge["isBroken"] is False
        assert edge["crossService"] is False
    finally:
        _cleanup(created)


def test_t7b_edge_404_when_page_missing(unique_suffix):
    r = client.get(
        f"/api/v1/knowledge/edge?from=codeeyes/__nope_{unique_suffix}_a__"
        f"&to=codeeyes/__nope_{unique_suffix}_b__"
    )
    assert r.status_code == 404, r.text


def test_t7c_edge_validation_when_from_equals_to(unique_suffix):
    # 동일 id 는 422 (자기루프 거부)
    r = client.get(
        f"/api/v1/knowledge/edge?from=codeeyes/same_{unique_suffix}"
        f"&to=codeeyes/same_{unique_suffix}"
    )
    assert r.status_code == 422, r.text


# ── T8: /knowledge/edge/promote 정상 ────────────────────────────────────


def test_t8_promote_adds_link_and_bumps_version(unique_suffix):
    a = f"t8-a-{unique_suffix}"
    b = f"t8-b-{unique_suffix}"
    a_id = f"codeeyes/{a}"
    b_id = f"codeeyes/{b}"

    created: List[str] = []
    try:
        created.append(_post_page(slug=b, title="T8 B", content="B 본문."))
        created.append(_post_page(
            slug=a,
            title="T8 A",
            content="A 본문. 아직 B 를 명시 참조하지 않는다.",
        ))

        # 등록 직후 version 확인 = 1
        r0 = client.get(f"/api/v1/knowledge/{a_id}")
        assert r0.status_code == 200
        assert r0.json()["version"] == 1

        r = client.post(
            "/api/v1/knowledge/edge/promote",
            json={"from": a_id, "to": b_id, "anchorText": "관련"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["from"] == a_id
        assert data["to"] == b_id
        assert data["linkAdded"] is True
        assert data["newVersion"] == 2

        # A 본문에 [[B]] 가 실제로 추가됨
        r2 = client.get(f"/api/v1/knowledge/{a_id}")
        assert r2.status_code == 200
        a_doc = r2.json()
        assert f"[[{b_id}]]" in a_doc["content"]
        assert a_doc["version"] == 2
        assert b_id in a_doc["links"]
        # anchor text 포함
        assert "관련" in a_doc["content"]
    finally:
        _cleanup(created)


# ── T9: 이미 explicit → 409 ──────────────────────────────────────────────


def test_t9_promote_already_explicit_returns_409(unique_suffix):
    a = f"t9-a-{unique_suffix}"
    b = f"t9-b-{unique_suffix}"
    a_id = f"codeeyes/{a}"
    b_id = f"codeeyes/{b}"

    created: List[str] = []
    try:
        created.append(_post_page(slug=b, title="T9 B", content="B 본문."))
        created.append(_post_page(
            slug=a,
            title="T9 A",
            content=f"A 본문이며 이미 [[{b_id}]] 를 명시 참조한다.",
        ))

        r = client.post(
            "/api/v1/knowledge/edge/promote",
            json={"from": a_id, "to": b_id},
        )
        assert r.status_code == 409, r.text
    finally:
        _cleanup(created)


# ── T10: service/category 필터 ───────────────────────────────────────────


def test_t10_filters_apply_correctly(unique_suffix):
    a = f"t10-a-{unique_suffix}"
    b = f"t10-b-{unique_suffix}"
    a_id = f"codeeyes/{a}"
    b_id = f"faq/{b}"

    created: List[str] = []
    try:
        created.append(_post_page(
            slug=a,
            title="T10 A codeeyes",
            content="A 본문 codeeyes 카테고리.",
            category="codeeyes",
        ))
        created.append(_post_page(
            slug=b,
            title="T10 B faq",
            content="B 본문 faq 카테고리.",
            category="faq",
        ))

        # category=codeeyes 필터 → b_id 제외, a_id 포함
        r_cat = build_graph(category="codeeyes")
        ids_cat = {n["id"] for n in r_cat["nodes"]}
        assert a_id in ids_cat
        assert b_id not in ids_cat

        # category=faq 필터 → b_id 포함, a_id 제외
        r_faq = build_graph(category="faq")
        ids_faq = {n["id"] for n in r_faq["nodes"]}
        assert b_id in ids_faq
        assert a_id not in ids_faq

        # service=codeeyes 는 두 페이지 모두 codeeyes 서비스 → 둘 다 포함
        r_svc = build_graph(service="codeeyes")
        ids_svc = {n["id"] for n in r_svc["nodes"]}
        assert a_id in ids_svc
        assert b_id in ids_svc
    finally:
        _cleanup(created)
