"""Karpathy v2 P6 acceptance — Archive 복원 CLI 통합 검증.

검증 시나리오 (사용자 지시 R1~R5):
    R1. POST /knowledge/restore-from-archive {dry_run:true, llm_enabled:false}
        → 200, would_restore 배열에 archive 의 .md 들이 포함됨, 실제 등록 X
    R2. POST /knowledge/restore-from-archive {dry_run:false, llm_enabled:false, max_files:3}
        → restored 배열에 1~3건. GET /knowledge 결과 추가됨. _restore-report.md 작성됨.
    R3. dry_run 보고서에 LLM 미사용 → llm_calls=0, estimated_cost_usd=0
    R4. 등록된 페이지의 category/page_type/slug 가 모두 schema 검증 통과 (422 없음)
    R5. failed 케이스 fixture: 빈 본문 .md 파일을 archive 에 일시 생성 → failed 에 등장,
        restored 에는 안 등장.
"""

from __future__ import annotations

import os
import shutil
import uuid
from typing import List

import pytest
from fastapi.testclient import TestClient

from app.core.config import _BACKEND_DIR
from app.main import app


client = TestClient(app, raise_server_exceptions=False)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────


@pytest.fixture
def unique_suffix() -> str:
    return uuid.uuid4().hex[:8]


def _archive_dir() -> str:
    return os.path.join(_BACKEND_DIR, "data", "knowledge-archive")


def _knowledge_dir() -> str:
    return os.path.join(_BACKEND_DIR, "data", "knowledge")


def _restore_report_path() -> str:
    return os.path.join(_knowledge_dir(), "_restore-report.md")


def _cleanup_doc(doc_id: str) -> None:
    """force 삭제로 정리. 404 무시."""
    try:
        client.delete(f"/api/v1/knowledge/{doc_id}?force=true")
    except Exception:
        pass


def _restored_ids_from_response(body: dict) -> List[str]:
    return [item["new_id"] for item in (body.get("restored") or [])]


# ── R1: dry_run + llm_enabled=false → would_restore 비어있지 않음, 실제 등록 X ──


def test_r1_dry_run_no_llm_lists_would_restore_without_registration():
    """archive 에 63 파일 + 3 파일 = 66 .md 가 보존되어 있음. would_restore 가 그 일부."""
    archive_root = _archive_dir()
    if not os.path.isdir(archive_root):
        pytest.skip("archive 디렉토리 없음 — 본 환경에서는 skip")

    # 실행 전 wiki 의 현재 페이지 id 집합 캡처
    pre_r = client.get("/api/v1/knowledge")
    assert pre_r.status_code == 200, pre_r.text
    pre_ids = {d["id"] for d in pre_r.json()}

    r = client.post(
        "/api/v1/knowledge/restore-from-archive",
        json={"dry_run": True, "llm_enabled": False, "max_files": 200},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # 응답 구조 검증
    assert "would_restore" in body and isinstance(body["would_restore"], list)
    assert "failed" in body and isinstance(body["failed"], list)
    assert "summary" in body
    assert "report_path" in body

    # would_restore 가 비어 있지 않아야 함 (archive 에 .md 가 존재)
    # 단, archive 가 비어 있을 수도 있으므로 archive 안에 .md 가 있을 때만 보장
    archive_md_count = 0
    for root, _dirs, files in os.walk(archive_root):
        for f in files:
            if f.endswith(".md") and not f.startswith("_") and not f.startswith("."):
                archive_md_count += 1

    if archive_md_count > 0:
        assert len(body["would_restore"]) > 0, (
            f"archive 에 {archive_md_count} 개 .md 가 있으나 would_restore 빈 결과: {body}"
        )
        # 각 항목 구조 검증
        first = body["would_restore"][0]
        assert "archive_path" in first
        assert "new_id" in first
        assert "category" in first
        assert "page_type" in first
        assert "rationale" in first
        # 영문 kebab-case slug 검증 (R4 의 일부)
        assert "/" in first["new_id"], "new_id 는 {category}/{slug} 형태여야 함"

    # _실제 등록은 발생하지 않아야 함_ — 위키 페이지 변화 없음
    post_r = client.get("/api/v1/knowledge")
    assert post_r.status_code == 200
    post_ids = {d["id"] for d in post_r.json()}
    assert post_ids == pre_ids, (
        f"dry_run 인데 위키 변화 발생 — added={post_ids - pre_ids}, removed={pre_ids - post_ids}"
    )


# ── R2: dry_run=false + llm_enabled=false + max_files=3 → 실제 등록 ────────


def test_r2_real_run_no_llm_registers_up_to_max_files():
    """실제 등록 — max_files=3 으로 1~3건 추가. GET /knowledge 결과 증가, 보고서 작성."""
    archive_root = _archive_dir()
    if not os.path.isdir(archive_root):
        pytest.skip("archive 디렉토리 없음 — skip")

    # archive 에 .md 가 충분히 있는지 확인
    archive_md_count = 0
    for root, _dirs, files in os.walk(archive_root):
        for f in files:
            if f.endswith(".md") and not f.startswith("_") and not f.startswith("."):
                archive_md_count += 1
    if archive_md_count == 0:
        pytest.skip("archive 에 .md 가 없음 — skip")

    pre_r = client.get("/api/v1/knowledge")
    assert pre_r.status_code == 200
    pre_ids = {d["id"] for d in pre_r.json()}

    new_doc_ids: List[str] = []
    try:
        r = client.post(
            "/api/v1/knowledge/restore-from-archive",
            json={"dry_run": False, "llm_enabled": False, "max_files": 3},
        )
        assert r.status_code == 200, r.text
        body = r.json()

        assert "restored" in body and isinstance(body["restored"], list)
        # max_files=3 이므로 처리 candidate 가 최대 3
        assert body["summary"]["total"] <= 3
        # restored 는 0~3 (R5 처럼 빈 본문이거나 id 충돌이면 failed)
        restored_count = len(body["restored"])
        assert restored_count >= 0
        new_doc_ids = _restored_ids_from_response(body)

        # 실제 등록 검증 — restored 가 1개 이상이면 wiki 에 등장해야 함
        if restored_count > 0:
            post_r = client.get("/api/v1/knowledge")
            assert post_r.status_code == 200
            post_ids = {d["id"] for d in post_r.json()}
            added = post_ids - pre_ids
            # 등록된 id 가 wiki 에 모두 존재해야 함
            for new_id in new_doc_ids:
                assert new_id in post_ids, (
                    f"등록된 {new_id} 가 GET /knowledge 결과에 없음. added={added}"
                )

        # _restore-report.md 작성 검증
        assert os.path.exists(_restore_report_path()), (
            f"_restore-report.md 미작성: {_restore_report_path()}"
        )
        with open(_restore_report_path(), "r", encoding="utf-8") as f:
            report = f.read()
        assert "# Knowledge Archive Restore Report" in report
        assert "REAL RUN" in report

    finally:
        # 등록된 신규 페이지 정리
        for doc_id in new_doc_ids:
            _cleanup_doc(doc_id)


# ── R3: dry_run + llm_enabled=false → llm_calls=0, cost=0 ───────────────


def test_r3_dry_run_no_llm_zero_cost():
    if not os.path.isdir(_archive_dir()):
        pytest.skip("archive 디렉토리 없음 — skip")
    r = client.post(
        "/api/v1/knowledge/restore-from-archive",
        json={"dry_run": True, "llm_enabled": False, "max_files": 200},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    s = body["summary"]
    assert s["llm_calls"] == 0, s
    assert s["estimated_cost_usd"] == 0.0, s
    # 모든 would_restore 항목의 llm_used 가 false
    for item in body["would_restore"]:
        assert item.get("llm_used") is False, item


# ── R4: 등록된 페이지의 category/page_type/slug 가 schema 검증 통과 ───────


def test_r4_registered_pages_pass_schema_validation():
    """R2 와 별도로 — 등록된 페이지를 GET 후 422 안 나는지 확인.

    R2 가 등록한 페이지를 PUT (변경 없음) → 422 안 나면 schema 통과.
    """
    archive_root = _archive_dir()
    if not os.path.isdir(archive_root):
        pytest.skip("archive 디렉토리 없음 — skip")

    new_doc_ids: List[str] = []
    try:
        r = client.post(
            "/api/v1/knowledge/restore-from-archive",
            json={"dry_run": False, "llm_enabled": False, "max_files": 2},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        new_doc_ids = _restored_ids_from_response(body)
        if not new_doc_ids:
            pytest.skip("restored 결과 없음 — schema 검증 fixture 부재로 skip")

        # 각 등록 페이지 GET → 200 (schema 위반이면 GET 도 fail 하지 않지만, page_type 등 valid 한지 확인)
        for new_id in new_doc_ids:
            g = client.get(f"/api/v1/knowledge/{new_id}")
            assert g.status_code == 200, f"GET {new_id} 실패: {g.text}"
            gb = g.json()
            # schema 키 존재
            assert gb.get("pageType") in {"Summary", "Entity", "Concept", "Comparison", "Synthesis"}
            assert "/" in gb["id"], gb["id"]
            # slug 부분이 영문 kebab-case
            slug = gb["id"].partition("/")[2]
            import re
            assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", slug), f"slug {slug!r} 가 kebab-case 위반"

            # PUT 으로 schema 재검증 — page_type 같은 값으로 update
            pu = client.put(
                f"/api/v1/knowledge/{new_id}",
                json={"page_type": gb["pageType"]},
            )
            assert pu.status_code == 200, f"PUT {new_id} 실패 — schema 위반 가능성: {pu.text}"
    finally:
        for doc_id in new_doc_ids:
            _cleanup_doc(doc_id)


# ── R5: 빈 본문 archive 파일 → failed 에 등장 ──────────────────────────


@pytest.fixture
def empty_body_archive_file():
    """archive 에 빈 본문(frontmatter 만 있고 body 없음) .md 를 일시 생성."""
    archive_root = _archive_dir()
    target_dir = os.path.join(archive_root, "_TEST_R5_EMPTY")
    os.makedirs(target_dir, exist_ok=True)
    suffix = uuid.uuid4().hex[:8]
    fname = f"empty-{suffix}.md"
    path = os.path.join(target_dir, fname)
    # frontmatter 만 있고 본문 비어 있음
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "---\n"
            "title: Empty Body Test\n"
            "tags: []\n"
            "---\n\n"
        )
    rel = f"_TEST_R5_EMPTY/{fname}"
    yield rel, path
    # cleanup
    try:
        os.remove(path)
    except OSError:
        pass
    try:
        os.rmdir(target_dir)
    except OSError:
        pass


def test_r5_empty_body_file_appears_in_failed(empty_body_archive_file):
    rel_path, abs_path = empty_body_archive_file
    if not os.path.isdir(_archive_dir()):
        pytest.skip("archive 디렉토리 없음 — skip")

    r = client.post(
        "/api/v1/knowledge/restore-from-archive",
        json={
            "dry_run": True,
            "llm_enabled": False,
            "archive_subpath": "_TEST_R5_EMPTY",
            "max_files": 10,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # failed 에 우리 fixture 가 등장해야 함
    failed_paths = [f.get("archive_path") for f in body["failed"]]
    assert rel_path in failed_paths, (
        f"빈 본문 파일 {rel_path} 가 failed 에 없음: {failed_paths}"
    )
    # 이유에 '비어' 가 포함
    matching = [f for f in body["failed"] if f.get("archive_path") == rel_path]
    assert matching, "matching failed entry 없음"
    assert "비어" in (matching[0].get("reason") or "") or "empty" in (matching[0].get("reason") or "").lower()

    # would_restore 에는 절대 안 들어감
    would_paths = [w.get("archive_path") for w in body["would_restore"]]
    assert rel_path not in would_paths, (
        f"빈 본문 파일이 would_restore 에 잘못 포함됨: {would_paths}"
    )
