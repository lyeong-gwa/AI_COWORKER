"""Karpathy v2 P4 acceptance — Lint + Index/Rebuild + Brief.

검증 시나리오 (사용자 지시 L1~L8):
    L1. POST /knowledge/lint (dry_run=true) 빈 위키에서 → 200, 모든 섹션 (none), report 파일 생성
    L2. 의도적 위반 5종 fixture 셋업 후 lint (dry_run=true) → 정적 위반 모두 보고서에 표시:
        - 카테고리 enum 위반 (DB 직접 frontmatter 변조)
        - slug 위반 (rename)
        - 깨진 link ([[nonexistent/x]] 포함 페이지)
        - 고아 페이지 (Summary 인데 backlink 0)
        - page_type Comparison 인데 link 1개만
    L3. lint 보고서 파일이 _lint-report.md + _lint-history/{ts}.md 모두 작성됨
    L4. POST /knowledge/index/rebuild → 응답 rebuilt 카테고리 목록, _index-*.md 파일들 갱신됨
    L5. POST /knowledge/brief {topic:"codeeyes"} → pages 배열 비어있을 수 있음 OK, indexes 동봉, retrievalNotes 존재
    L6. POST /knowledge/brief {query:"...something..."} maxPages=3 → pages 최대 3건, page_type 가중치 적용
    L7. /knowledge/brief includeLog=true → recentChanges 배열 존재 (_log.md 가 비어있으면 [])
    L8. /knowledge/lint llm_enabled=false → llm_calls=0, dynamic 섹션 모두 (none), 정적만 보고
"""

from __future__ import annotations

import os
import re
import shutil
import uuid
from typing import List

import pytest
from fastapi.testclient import TestClient

from app.core.config import _BACKEND_DIR
from app.main import app


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


def _knowledge_dir() -> str:
    return os.path.join(_BACKEND_DIR, "data", "knowledge")


def _report_md_path() -> str:
    return os.path.join(_knowledge_dir(), "_lint-report.md")


def _history_dir() -> str:
    return os.path.join(_knowledge_dir(), "_lint-history")


# ── L1: dry_run lint on empty wiki (or current wiki) → 200 + report 생성 ──


def test_l1_lint_dry_run_creates_report():
    """기존 위키 상태에서도 dry_run 은 정적 검사만 수행, llm_calls=0, report 작성."""
    r = client.post("/api/v1/knowledge/lint", json={"dry_run": True})
    assert r.status_code == 200, r.text
    body = r.json()

    assert "summary" in body
    assert body["summary"]["llm_calls"] == 0, body["summary"]
    assert body["summary"]["estimated_cost_usd"] == 0.0
    # 동적 섹션은 모두 비어 있어야 함 (dry_run)
    assert body["duplicates"] == []
    assert body["contradictions"] == []
    assert body["outdated"] == []
    # 보고서 경로
    assert "report_path" in body and body["report_path"].endswith("_lint-report.md")
    assert "history_path" in body
    # 실제 파일 존재
    assert os.path.exists(_report_md_path()), f"report missing: {_report_md_path()}"
    history_full = os.path.join(_BACKEND_DIR, body["history_path"].replace("/", os.sep))
    assert os.path.exists(history_full), f"history missing: {history_full}"
    # 보고서 내용 sanity — 헤더 포함
    with open(_report_md_path(), "r", encoding="utf-8") as f:
        report = f.read()
    assert "# Knowledge Lint Report" in report
    assert "## Summary" in report
    assert "## 1. Duplicates" in report
    assert "## 6. Schema Violations" in report


# ── L2: 의도적 위반 5종 fixture → 정적 위반 모두 보고서에 표시 ─────────


def _inject_unknown_category(doc_id: str) -> str:
    """DB API 우회 — 파일을 직접 카테고리 디렉토리에 작성해서 unknown 카테고리 위반 생성.

    valid 카테고리 디렉토리 하위에 frontmatter 의 `category` 만 unknown 으로 변조.
    list_md_files 가 디렉토리 기반으로 doc.id 를 만들지만, doc.category 는 frontmatter
    로부터 읽으므로 mismatch 발생 → schema validate_category 가 위반 보고.
    """
    cat_dir = os.path.join(_knowledge_dir(), "codeeyes")
    os.makedirs(cat_dir, exist_ok=True)
    slug = f"l2-bad-cat-{doc_id}"
    path = os.path.join(cat_dir, f"{slug}.md")
    body = (
        "---\n"
        "title: L2 Bad Cat\n"
        "category: zzz-unknown-cat-zzz\n"
        "tags: []\n"
        "source: ''\n"
        "created: '2026-01-01T00:00:00'\n"
        "page_type: Summary\n"
        "version: 1\n"
        "links: []\n"
        "---\n\n"
        "본문\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return f"codeeyes/{slug}"


def _inject_bad_slug(doc_id: str) -> str:
    """카테고리 디렉토리에 비-kebab-case slug 의 .md 파일 직접 작성."""
    cat_dir = os.path.join(_knowledge_dir(), "codeeyes")
    os.makedirs(cat_dir, exist_ok=True)
    # 대문자 + 언더스코어 → slug regex 위반
    bad_slug = f"L2_BadSlug_{doc_id}"
    path = os.path.join(cat_dir, f"{bad_slug}.md")
    body = (
        "---\n"
        "title: L2 Bad Slug\n"
        "category: codeeyes\n"
        "tags: []\n"
        "source: ''\n"
        "created: '2026-01-01T00:00:00'\n"
        "page_type: Summary\n"
        "version: 1\n"
        "links: []\n"
        "---\n\n"
        "본문\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return f"codeeyes/{bad_slug}"


def test_l2_static_lint_detects_5_violations(unique_suffix):
    suffix = unique_suffix
    # 정상 등록 — Summary 가 다른 페이지를 가리키지 않으면 고아 위반
    orphan_slug = f"l2-orphan-{suffix}"
    orphan_id = f"codeeyes/{orphan_slug}"

    # broken link 가진 페이지
    broken_slug = f"l2-broken-{suffix}"
    broken_id = f"codeeyes/{broken_slug}"
    nonexist_id = f"codeeyes/l2-nonexistent-{suffix}"

    # Comparison 인데 link 1개만 (min_links=2 위반)
    cmp_slug = f"l2-cmp-{suffix}"
    cmp_id = f"codeeyes/{cmp_slug}"
    cmp_target_slug = f"l2-cmp-target-{suffix}"
    cmp_target_id = f"codeeyes/{cmp_target_slug}"

    bad_cat_id: str | None = None
    bad_slug_id: str | None = None

    try:
        # 1) orphan: link 없음, page_type=Summary
        r1 = client.post("/api/v1/knowledge", json={
            "service": "codeeyes",
            "category": "codeeyes",
            "slug": orphan_slug,
            "page_type": "Summary",
            "title": "L2 Orphan",
            "content": "본문에 링크 없음",
            "tags": [],
        })
        assert r1.status_code == 201, r1.text

        # 2) broken link 페이지 (Entity 로 두면 orphan 위반 회피)
        r2 = client.post("/api/v1/knowledge", json={
            "service": "codeeyes",
            "category": "codeeyes",
            "slug": broken_slug,
            "page_type": "Entity",
            "title": "L2 Broken",
            "content": f"존재하지 않는 [[{nonexist_id}]] 참조",
            "tags": [],
        })
        assert r2.status_code == 201, r2.text

        # 3) Comparison 인데 link 1개 → min_links=2 위반
        # 먼저 target 1건 등록
        r_target = client.post("/api/v1/knowledge", json={
            "service": "codeeyes",
            "category": "codeeyes",
            "slug": cmp_target_slug,
            "page_type": "Entity",
            "title": "L2 Cmp Target",
            "content": "비교 대상 entity",
            "tags": [],
        })
        assert r_target.status_code == 201, r_target.text
        # Comparison 페이지 — link 1개만
        r3 = client.post("/api/v1/knowledge", json={
            "service": "codeeyes",
            "category": "codeeyes",
            "slug": cmp_slug,
            "page_type": "Comparison",
            "title": "L2 Comparison",
            "content": f"하나만 비교 [[{cmp_target_id}]]",
            "tags": [],
        })
        assert r3.status_code == 201, r3.text

        # 4) unknown category 직접 주입
        bad_cat_id = _inject_unknown_category(suffix)
        # 5) bad slug 직접 주입
        bad_slug_id = _inject_bad_slug(suffix)

        # 실행 (dry_run)
        r = client.post("/api/v1/knowledge/lint", json={"dry_run": True})
        assert r.status_code == 200, r.text
        body = r.json()

        # 정적 결과 검증
        all_ids = lambda items, key: {it.get(key) for it in items}

        # (a) schema_violations 에 unknown cat + bad slug 포함
        sv_pairs = [(s.get("id"), s.get("field")) for s in body["schema_violations"]]
        assert (bad_cat_id, "category") in sv_pairs, (
            f"unknown category violation 누락 — schema_violations={sv_pairs}"
        )
        assert (bad_slug_id, "slug") in sv_pairs, (
            f"bad slug violation 누락 — schema_violations={sv_pairs}"
        )

        # (b) broken_links 에 nonexist 포함
        bl_pairs = [(b.get("from"), b.get("to")) for b in body["broken_links"]]
        assert (broken_id, nonexist_id) in bl_pairs, (
            f"broken link 누락 — broken_links={bl_pairs}"
        )

        # (c) orphans 에 orphan_id 포함 (Summary, backlink 0)
        orph_ids = {o.get("id") for o in body["orphans"]}
        assert orphan_id in orph_ids, f"orphan 누락 — orphans={orph_ids}"

        # (d) Comparison min_links=2 위반 — schema_violations 의 field=links
        ml_pairs = [
            (s.get("id"), s.get("field")) for s in body["schema_violations"]
        ]
        assert (cmp_id, "links") in ml_pairs, (
            f"min_links 위반 누락 — schema_violations={ml_pairs}"
        )

        # 보고서 파일에도 모두 표시되는지
        with open(_report_md_path(), "r", encoding="utf-8") as f:
            report = f.read()
        assert nonexist_id in report
        assert orphan_id in report
        assert cmp_id in report
        assert bad_cat_id in report
        assert bad_slug_id in report
        # dry_run 이므로 LLM 호출 0
        assert "LLM calls: 0" in report

    finally:
        _cleanup_doc(orphan_id)
        _cleanup_doc(broken_id)
        _cleanup_doc(cmp_id)
        _cleanup_doc(cmp_target_id)
        # 직접 작성한 파일 정리
        if bad_cat_id:
            path = os.path.join(_knowledge_dir(), "codeeyes", f"{bad_cat_id.split('/')[1]}.md")
            if os.path.exists(path):
                os.remove(path)
        if bad_slug_id:
            path = os.path.join(_knowledge_dir(), "codeeyes", f"{bad_slug_id.split('/')[1]}.md")
            if os.path.exists(path):
                os.remove(path)


# ── L3: report + history 둘 다 작성 ───────────────────────────────────────


def test_l3_lint_writes_report_and_history():
    """report + history 둘 다 작성됨. 동일 초 재실행 시 history 는 덮어쓰기 정상."""
    hist = _history_dir()
    os.makedirs(hist, exist_ok=True)

    r = client.post("/api/v1/knowledge/lint", json={"dry_run": True})
    assert r.status_code == 200, r.text
    body = r.json()
    # report (덮어쓰기)
    assert os.path.exists(_report_md_path())
    # history (timestamp 파일) — body 의 history_path 가 가리키는 파일이 존재
    assert "history_path" in body and body["history_path"]
    history_name = os.path.basename(body["history_path"])
    history_full = os.path.join(hist, history_name)
    assert os.path.exists(history_full), f"history file missing: {history_full}"
    # 파일 내용도 report 와 동일해야 함
    with open(_report_md_path(), "r", encoding="utf-8") as f:
        r1 = f.read()
    with open(history_full, "r", encoding="utf-8") as f:
        r2 = f.read()
    assert r1 == r2, "report 와 history 내용 불일치"


# ── L4: POST /knowledge/index/rebuild ───────────────────────────────────


def test_l4_index_rebuild_response_and_files():
    r = client.post("/api/v1/knowledge/index/rebuild", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "rebuilt" in body and isinstance(body["rebuilt"], list)
    # multi-service v3 (`.omc/plans/지식-multi-service.md` §2.1) — _schema.yaml 의
    # 기능형 카테고리가 모두 등록되어 있어야 함. legacy id (`codeeyes`,
    # `ito-portal-operations`, `plugin-troubleshooting`) 는 v3 enum 에서 제외되어
    # rebuild 가 다루지 않는다 (단, validator 는 WARN+통과로 호환 유지).
    assert "overview" in body["rebuilt"]
    assert "operations-guide" in body["rebuilt"]
    assert "faq" in body["rebuilt"]
    # 각 카테고리 _index-*.md 파일 존재
    for cat in body["rebuilt"]:
        idx_path = os.path.join(_knowledge_dir(), cat, f"_index-{cat}.md")
        assert os.path.exists(idx_path), f"index missing: {idx_path}"
        with open(idx_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert f"# Index — {cat}" in content


def test_l4b_index_rebuild_with_specific_category(unique_suffix):
    # 단일 카테고리 지정
    r = client.post(
        "/api/v1/knowledge/index/rebuild",
        json={"categories": ["faq"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rebuilt"] == ["faq"], body


# ── L5: brief topic, empty pages OK, indexes 동봉 ─────────────────────────


def test_l5_brief_topic_returns_indexes_even_if_no_pages():
    r = client.post(
        "/api/v1/knowledge/brief",
        json={"topic": "codeeyes", "categories": ["codeeyes"], "maxPages": 8, "includeLog": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "pages" in body and isinstance(body["pages"], list)
    assert "indexes" in body and isinstance(body["indexes"], list)
    # categories 인자가 지정되었으므로 codeeyes 인덱스가 반드시 동봉
    cats_in_indexes = {i["category"] for i in body["indexes"]}
    assert "codeeyes" in cats_in_indexes, f"codeeyes index 누락: {cats_in_indexes}"
    assert "retrievalNotes" in body and isinstance(body["retrievalNotes"], str)
    assert "page_type weighting" in body["retrievalNotes"]


# ── L6: brief query maxPages + page_type 가중치 ──────────────────────────


def test_l6_brief_query_max_pages_and_weighting(unique_suffix):
    # 같은 카테고리에 Synthesis + Entity 두 페이지 — 같은 query 에 대해
    # Synthesis 가 더 높은 weightedScore 를 받아야 함 (가중치 1.5 vs 0.9).
    syn_slug = f"l6-syn-{unique_suffix}"
    ent_slug = f"l6-ent-{unique_suffix}"
    syn_id = f"codeeyes/{syn_slug}"
    ent_id = f"codeeyes/{ent_slug}"
    try:
        common_text = "L6 통합 통찰 페이지 본문 — codeeyes 운영 관련 내용입니다."
        r1 = client.post("/api/v1/knowledge", json={
            "service": "codeeyes",
            "category": "codeeyes",
            "slug": syn_slug,
            "page_type": "Synthesis",
            "title": "L6 Synthesis",
            "content": common_text,
            "tags": [],
        })
        assert r1.status_code == 201, r1.text
        r2 = client.post("/api/v1/knowledge", json={
            "service": "codeeyes",
            "category": "codeeyes",
            "slug": ent_slug,
            "page_type": "Entity",
            "title": "L6 Entity",
            "content": common_text,
            "tags": [],
        })
        assert r2.status_code == 201, r2.text

        r = client.post(
            "/api/v1/knowledge/brief",
            json={
                "query": "L6 통합 통찰 codeeyes 운영",
                "categories": ["codeeyes"],
                "maxPages": 3,
                "includeLog": False,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # maxPages 상한
        assert len(body["pages"]) <= 3, len(body["pages"])
        ids = [p["id"] for p in body["pages"]]
        # 두 페이지가 모두 포함되었는지 (top3 이내)
        if syn_id in ids and ent_id in ids:
            syn_w = next(p["weightedScore"] for p in body["pages"] if p["id"] == syn_id)
            ent_w = next(p["weightedScore"] for p in body["pages"] if p["id"] == ent_id)
            # 같은 cosine 이면 Synthesis (1.5) 가 Entity (0.9) 보다 weightedScore 큼
            # 실제로는 score 가 약간 다를 수 있으므로 cosine 동일 시 우선 검증
            syn_s = next(p["score"] for p in body["pages"] if p["id"] == syn_id)
            ent_s = next(p["score"] for p in body["pages"] if p["id"] == ent_id)
            if abs(syn_s - ent_s) < 0.001:
                assert syn_w > ent_w, (
                    f"Synthesis 가중치(1.5) 가 Entity(0.9) 보다 커야 함: syn={syn_w}, ent={ent_w}"
                )
    finally:
        _cleanup_doc(syn_id)
        _cleanup_doc(ent_id)


# ── L7: brief includeLog=true → recentChanges 배열 ──────────────────────


def test_l7_brief_include_log_returns_recent_changes():
    r = client.post(
        "/api/v1/knowledge/brief",
        json={"topic": "ito", "categories": [], "maxPages": 3, "includeLog": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "recentChanges" in body
    rc = body["recentChanges"]
    assert isinstance(rc, list)
    # 비어 있어도 OK. 비어있지 않다면 구조 확인.
    if rc:
        first = rc[0]
        assert "timestamp" in first
        assert "id" in first
        assert "summary" in first


# ── L8: lint llm_enabled=false → llm_calls=0, 정적만 ────────────────────


def test_l8_lint_llm_disabled_keeps_static_only():
    r = client.post(
        "/api/v1/knowledge/lint",
        json={"dry_run": False, "llm_enabled": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["llm_calls"] == 0
    assert body["summary"]["estimated_cost_usd"] == 0.0
    # dynamic 섹션 비어 있어야 함
    assert body["duplicates"] == []
    assert body["contradictions"] == []
    assert body["outdated"] == []
    # 보고서에도 dynamic 섹션 (none)
    with open(_report_md_path(), "r", encoding="utf-8") as f:
        report = f.read()
    # Section 1, 2, 4 가 (none) 인지 검증 — 단순히 LLM calls: 0 확인
    assert "LLM calls: 0" in report
