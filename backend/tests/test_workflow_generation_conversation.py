"""워크플로우 ↔ 생성 추적(대화) 연결 통합 테스트.

검증 포인트:
1. POST /workflows 가 generationTraceIds 를 그대로 저장한다 (순서 보존 + 중복 제거).
2. PATCH /workflows/{id} 가 새 generationTraceIds 를 기존 목록에 append + dedup 한다
   (요청 omit 시 기존 목록 보존).
3. GET /workflows/{id}/generation-traces 가 연결된 대화를 저장 순서(오래된→최신)대로 반환.
4. 연결된 trace 가 없으면 빈 배열.
5. 미존재 워크플로우 → 404.

생성 추적은 JSONL 파일에 저장되므로, 테스트는 set_log_file_path 로 임시 파일에
trace 를 직접 append 하여 격리한다 (LLM 미호출).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.generation_trace import (
    append_trace,
    set_log_file_path,
    reset_log_file_path,
)


client = TestClient(app, raise_server_exceptions=False)


# ── 임시 trace 로그 격리 ──────────────────────────────────────────────────────

@pytest.fixture()
def _isolate_trace_log(tmp_path):
    log_file = tmp_path / "conv_traces.jsonl"
    set_log_file_path(log_file)
    yield log_file
    reset_log_file_path()


# ── 유효한 최소 워크플로우 페이로드 (form-start → result) ────────────────────

def _valid_payload(name: str, trace_ids: list[str] | None = None) -> dict:
    start_id = f"wn-{uuid.uuid4().hex[:8]}"
    result_id = f"wn-{uuid.uuid4().hex[:8]}"
    conn_id = f"wc-{uuid.uuid4().hex[:8]}"
    payload = {
        "name": name,
        "description": "대화 연결 검증용",
        "tags": [],
        "nodes": [
            {
                "id": start_id,
                "nodeId": start_id,
                "definitionType": "form-start",
                "name": "시작",
                "config": {},
                "inputMapping": {},
            },
            {
                "id": result_id,
                "nodeId": result_id,
                "definitionType": "result",
                "name": "결과",
                "config": {},
                "inputMapping": {},
            },
        ],
        "connections": [
            {
                "id": conn_id,
                "sourceNodeId": start_id,
                "targetNodeId": result_id,
            }
        ],
    }
    if trace_ids is not None:
        payload["generationTraceIds"] = trace_ids
    return payload


def _create(payload: dict) -> dict:
    r = client.post("/api/v1/workflows", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# ── 케이스 1: create 가 generationTraceIds 저장 ──────────────────────────────

def test_create_persists_generation_trace_ids():
    body = _create(_valid_payload("conv-create", trace_ids=["gen-aaa", "gen-bbb", "gen-aaa"]))
    wf_id = body["id"]
    try:
        # 중복 제거 + 순서 보존
        assert body["generationTraceIds"] == ["gen-aaa", "gen-bbb"], body["generationTraceIds"]

        # 재조회해도 동일
        g = client.get(f"/api/v1/workflows/{wf_id}")
        assert g.status_code == 200, g.text
        assert g.json()["generationTraceIds"] == ["gen-aaa", "gen-bbb"]
    finally:
        client.delete(f"/api/v1/workflows/{wf_id}")


def test_create_defaults_empty_trace_ids():
    body = _create(_valid_payload("conv-create-empty"))  # generationTraceIds 생략
    wf_id = body["id"]
    try:
        assert body["generationTraceIds"] == []
    finally:
        client.delete(f"/api/v1/workflows/{wf_id}")


# ── 케이스 2: update 가 append + dedup, omit 시 보존 ─────────────────────────

def test_update_appends_and_dedups_trace_ids():
    body = _create(_valid_payload("conv-update", trace_ids=["gen-1", "gen-2"]))
    wf_id = body["id"]
    try:
        # gen-2(중복) + gen-3(신규) 를 append → [gen-1, gen-2, gen-3]
        r = client.patch(
            f"/api/v1/workflows/{wf_id}",
            json={"generationTraceIds": ["gen-2", "gen-3"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["generationTraceIds"] == ["gen-1", "gen-2", "gen-3"]

        # generationTraceIds 를 omit 한 수정 → 기존 목록 보존
        r2 = client.patch(f"/api/v1/workflows/{wf_id}", json={"description": "설명만 변경"})
        assert r2.status_code == 200, r2.text
        assert r2.json()["generationTraceIds"] == ["gen-1", "gen-2", "gen-3"]
        assert r2.json()["description"] == "설명만 변경"
    finally:
        client.delete(f"/api/v1/workflows/{wf_id}")


# ── 케이스 3+4: GET /generation-traces 순서/빈배열 ───────────────────────────

def test_get_generation_traces_returns_ordered_conversation(_isolate_trace_log):
    # 임시 로그에 trace 3건을 임의 순서로 기록
    append_trace({
        "traceId": "gen-t2", "createdAt": "2026-06-04T00:02:00", "mode": "edit",
        "userMessage": "두번째 요청", "assistantMessage": "두번째 응답",
        "attempts": 1, "result": "valid",
        "finalValidation": {"errorCount": 0, "warningCount": 2},
    })
    append_trace({
        "traceId": "gen-t1", "createdAt": "2026-06-04T00:01:00", "mode": "create",
        "userMessage": "첫번째 요청", "assistantMessage": "첫번째 응답",
        "attempts": 0, "result": "valid",
        "finalValidation": {"errorCount": 0, "warningCount": 0},
    })
    append_trace({
        "traceId": "gen-t3", "createdAt": "2026-06-04T00:03:00", "mode": "edit",
        "userMessage": "세번째 요청", "assistantMessage": "세번째 응답",
        "attempts": 2, "result": "invalid",
        "finalValidation": {"errorCount": 1, "warningCount": 0},
    })

    # 저장 순서(대화 순서) t1 → t2 → t3 로 워크플로우 생성
    body = _create(_valid_payload("conv-get", trace_ids=["gen-t1", "gen-t2", "gen-t3"]))
    wf_id = body["id"]
    try:
        r = client.get(f"/api/v1/workflows/{wf_id}/generation-traces")
        assert r.status_code == 200, r.text
        conv = r.json()
        assert [c["traceId"] for c in conv] == ["gen-t1", "gen-t2", "gen-t3"]

        # 항목 형태 검증
        first = conv[0]
        assert first["userMessage"] == "첫번째 요청"
        assert first["assistantMessage"] == "첫번째 응답"
        assert first["mode"] == "create"
        assert first["errorCount"] == 0 and first["warningCount"] == 0
        # 마지막 항목 invalid + errorCount 파생
        assert conv[2]["result"] == "invalid"
        assert conv[2]["errorCount"] == 1
    finally:
        client.delete(f"/api/v1/workflows/{wf_id}")


def test_get_generation_traces_empty_when_no_links(_isolate_trace_log):
    body = _create(_valid_payload("conv-empty"))  # trace 없음
    wf_id = body["id"]
    try:
        r = client.get(f"/api/v1/workflows/{wf_id}/generation-traces")
        assert r.status_code == 200, r.text
        assert r.json() == []
    finally:
        client.delete(f"/api/v1/workflows/{wf_id}")


# ── 케이스 5: 미존재 워크플로우 → 404 ────────────────────────────────────────

def test_get_generation_traces_missing_workflow_404():
    ghost = f"wf-ghost-{uuid.uuid4().hex[:8]}"
    r = client.get(f"/api/v1/workflows/{ghost}/generation-traces")
    assert r.status_code == 404, r.text
    err = r.json()["error"]
    assert err["code"] == "NOT_FOUND"
    assert err["details"]["workflowId"] == ghost


# ── 케이스 6: /generation-traces (id 없음) 와 라우트 충돌 없음 ────────────────

def test_generation_traces_list_route_not_shadowed(_isolate_trace_log):
    """literal /generation-traces 가 /{workflow_id}/generation-traces 와 충돌하지 않음."""
    r = client.get("/api/v1/workflows/generation-traces?limit=5")
    # 200 이며 list 반환 (workflow 404 가 아님)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)
