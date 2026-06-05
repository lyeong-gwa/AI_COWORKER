"""워크플로우 생성 추적 로그(generation trace) 단위·통합 테스트.

LLM 을 실제 호출하지 않는다 — monkeypatch 로 가짜 handler 를 주입한다.

케이스:
  1. generate_workflow 1회 실행 → JSONL 1줄 기록,
     get_trace(traceId) 로 읽으면 description·llmCalls·validationHistory·finalDraft 포함.
  2. read_traces 요약 필드 검증.
  3. 임시 로그 경로 격리 (set_log_file_path / reset_log_file_path).
  4. 예외 발생 시에도 trace 가 기록되고 result='error'.
  5. append_trace 예외 삼킴 (로깅 실패가 생성 실패로 이어지지 않음).
  6. get_trace 없으면 None 반환.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.database import async_session_maker
from app.services.workflow_generator import generate_workflow, MAX_REPAIR
from app.services import generation_trace as gt_module
from app.services.generation_trace import (
    append_trace,
    read_traces,
    get_trace,
    get_traces_by_ids,
    trace_to_conversation_item,
    set_log_file_path,
    reset_log_file_path,
    make_tracing_proxy,
)


# ── 공통 픽스처: 임시 로그 경로 격리 ─────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate_log_path(tmp_path):
    """각 테스트마다 임시 JSONL 파일 경로로 격리한다."""
    log_file = tmp_path / "test_generation.jsonl"
    set_log_file_path(log_file)
    yield log_file
    reset_log_file_path()


# ── 공통 draft 조각 ───────────────────────────────────────────────────────────

_GOOD_DRAFT = {
    "name": "추적 테스트 워크플로우",
    "description": "추적 테스트용",
    "tags": [],
    "nodes": [
        {
            "id": "wn-trace001",
            "nodeId": "wn-trace001",
            "definitionType": "form-start",
            "name": "시작",
            "config": {},
            "inputMapping": {},
        },
        {
            "id": "wn-trace002",
            "nodeId": "wn-trace002",
            "definitionType": "result",
            "name": "결과",
            "config": {},
            "inputMapping": {},
        },
    ],
    "connections": [
        {
            "id": "wc-trace001",
            "sourceNodeId": "wn-trace001",
            "targetNodeId": "wn-trace002",
            "sourceHandle": None,
        }
    ],
}

_SKELETON_RESP = json.dumps([
    {"defType": "form-start", "name": "시작", "purpose": "트리거"},
    {"defType": "result", "name": "결과", "purpose": "저장"},
])


def _fake_resp(content: str) -> Any:
    return SimpleNamespace(content=content, token_usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30})


# ── 케이스 1: generate_workflow → JSONL 1줄 기록, get_trace 로 읽기 ───────────

@pytest.mark.asyncio
async def test_generate_workflow_records_trace(monkeypatch, _isolate_log_path):
    """generate_workflow 1회 실행 후 JSONL 에 1줄이 기록되어야 하며,
    get_trace 로 읽으면 핵심 필드가 모두 존재해야 한다.
    """
    resps = [
        _fake_resp(_SKELETON_RESP),
        _fake_resp(json.dumps(_GOOD_DRAFT)),
    ]
    call_idx = [0]

    async def fake_chat(req):
        idx = call_idx[0]
        call_idx[0] += 1
        return resps[idx] if idx < len(resps) else _fake_resp(json.dumps(_GOOD_DRAFT))

    fake_handler = SimpleNamespace(chat=fake_chat)
    monkeypatch.setattr("app.services.workflow_generator.get_llm_handler", lambda: fake_handler)
    monkeypatch.setattr(
        "app.services.workflow_generator._collect_materials",
        __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(
            return_value={"apiDefinitions": [], "instanceDbs": [], "aiNodes": [], "knowledgeCategories": []}
        ),
    )
    monkeypatch.setattr(
        "app.services.workflow_generator.validate_workflow_structure",
        __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(
            return_value={"valid": True, "errorCount": 0, "warningCount": 0, "errors": [], "warnings": []}
        ),
    )

    description = "테스트용 업무 설명입니다"
    async with async_session_maker() as db:
        result = await generate_workflow(description, db)

    trace_id = result.get("traceId")
    assert trace_id is not None, "result 에 traceId 가 없음"
    assert trace_id.startswith("gen-"), f"traceId 형식 오류: {trace_id}"

    # JSONL 파일에 1줄이 기록되었는지 확인
    log_file: Path = _isolate_log_path
    assert log_file.exists(), "JSONL 로그 파일이 생성되지 않음"
    lines = [l for l in log_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1, f"JSONL 줄 수 기대=1, 실제={len(lines)}"

    # get_trace 로 전체 읽기
    trace = get_trace(trace_id)
    assert trace is not None, f"get_trace({trace_id!r}) 가 None 반환"

    # description 포함 확인
    assert trace.get("description") == description, \
        f"description 불일치: {trace.get('description')!r}"

    # llmCalls: IN(시스템·유저 프롬프트) + OUT(응답) 포함
    llm_calls = trace.get("llmCalls")
    assert llm_calls is not None and len(llm_calls) >= 1, \
        f"llmCalls 가 없거나 비어있음: {llm_calls}"
    for call in llm_calls:
        assert "callType" in call, "llmCalls 항목에 callType 없음"
        assert "prompt" in call, "llmCalls 항목에 prompt 없음"
        assert "response" in call, "llmCalls 항목에 response 없음"
        assert "ok" in call, "llmCalls 항목에 ok 없음"
        assert "durationMs" in call, "llmCalls 항목에 durationMs 없음"

    # validationHistory: 최소 1 항목(초기 검증)
    val_history = trace.get("validationHistory")
    assert val_history is not None and len(val_history) >= 1, \
        f"validationHistory 가 없거나 비어있음: {val_history}"
    first_val = val_history[0]
    assert "valid" in first_val, "validationHistory[0] 에 valid 없음"
    assert "errorCount" in first_val, "validationHistory[0] 에 errorCount 없음"
    assert "warningCount" in first_val, "validationHistory[0] 에 warningCount 없음"

    # finalDraft 포함
    final_draft = trace.get("finalDraft")
    assert final_draft is not None and isinstance(final_draft, dict), \
        "finalDraft 가 없거나 dict 가 아님"
    assert "nodes" in final_draft, "finalDraft 에 nodes 없음"

    # result 필드
    assert trace.get("result") in ("valid", "invalid", "error"), \
        f"result 필드 값 이상: {trace.get('result')}"


# ── 케이스 2: read_traces 요약 필드 검증 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_read_traces_summary_fields(monkeypatch, _isolate_log_path):
    """2건을 기록한 후 read_traces 가 최신순 요약을 반환하는지 검증한다."""
    resps = [
        _fake_resp(_SKELETON_RESP),
        _fake_resp(json.dumps(_GOOD_DRAFT)),
    ]
    call_idx = [0]

    async def fake_chat(req):
        idx = call_idx[0] % len(resps)
        call_idx[0] += 1
        return resps[idx]

    fake_handler = SimpleNamespace(chat=fake_chat)
    monkeypatch.setattr("app.services.workflow_generator.get_llm_handler", lambda: fake_handler)
    from unittest.mock import AsyncMock
    monkeypatch.setattr(
        "app.services.workflow_generator._collect_materials",
        AsyncMock(return_value={"apiDefinitions": [], "instanceDbs": [], "aiNodes": [], "knowledgeCategories": []}),
    )
    monkeypatch.setattr(
        "app.services.workflow_generator.validate_workflow_structure",
        AsyncMock(return_value={"valid": True, "errorCount": 0, "warningCount": 0, "errors": [], "warnings": []}),
    )

    async with async_session_maker() as db:
        r1 = await generate_workflow("첫번째 업무", db)
        # 두번째 호출을 위해 fake_chat 인덱스 리셋
        call_idx[0] = 0
        r2 = await generate_workflow("두번째 업무", db)

    summaries = read_traces(limit=10)
    assert len(summaries) >= 2, f"read_traces 반환 건수 기대 ≥2, 실제={len(summaries)}"

    # 최신순이므로 첫 번째 항목이 두번째 호출 결과여야 함
    first = summaries[0]
    required_fields = ["traceId", "createdAt", "mode", "description", "attempts", "result", "errorCount", "warningCount", "nodeCount"]
    for field in required_fields:
        assert field in first, f"read_traces 요약에 '{field}' 필드 없음"

    # description 은 120자 이내
    assert len(first.get("description", "")) <= 120, "description 120자 초과"


# ── 케이스 3: 예외 발생 시에도 trace 기록 (result='error') ───────────────────

@pytest.mark.asyncio
async def test_trace_recorded_on_exception(monkeypatch, _isolate_log_path):
    """LLM handler.chat 이 예외를 던져도 trace 가 JSONL 에 기록되어야 하며
    result='error' 여야 한다.
    """
    async def exploding_chat(req):
        raise RuntimeError("LLM 서버 연결 실패")

    fake_handler = SimpleNamespace(chat=exploding_chat)
    monkeypatch.setattr("app.services.workflow_generator.get_llm_handler", lambda: fake_handler)
    from unittest.mock import AsyncMock
    monkeypatch.setattr(
        "app.services.workflow_generator._collect_materials",
        AsyncMock(return_value={"apiDefinitions": [], "instanceDbs": [], "aiNodes": [], "knowledgeCategories": []}),
    )

    async with async_session_maker() as db:
        with pytest.raises(Exception):
            await generate_workflow("예외 발생 테스트", db)

    log_file: Path = _isolate_log_path
    assert log_file.exists(), "예외 발생 시에도 JSONL 파일이 생성되어야 함"
    lines = [l for l in log_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1, f"예외 발생 시 JSONL 줄 수 기대=1, 실제={len(lines)}"

    trace = json.loads(lines[0])
    assert trace.get("result") == "error", f"result='error' 기대, 실제={trace.get('result')}"
    assert trace.get("error") is not None, "error 필드가 None"


# ── 케이스 4: append_trace 예외 삼킴 ─────────────────────────────────────────

def test_append_trace_swallows_exceptions(tmp_path):
    """읽기전용 경로 등으로 append_trace 가 실패해도 예외가 밖으로 나오지 않아야 한다."""
    # 읽기전용 디렉토리 시뮬레이션: 존재하지 않는 경로 위에 파일 경로 지정
    bad_path = tmp_path / "nonexistent_dir" / "subdir" / "trace.jsonl"
    set_log_file_path(bad_path)
    try:
        # 디렉토리 생성을 막기 위해 부모를 파일로 만든다
        (tmp_path / "nonexistent_dir").write_text("I am a file, not a dir")
        # append_trace 는 예외를 삼켜야 한다
        append_trace({"traceId": "test", "description": "예외 삼킴 테스트"})
        # 여기까지 왔으면 예외가 삼켜진 것
    finally:
        reset_log_file_path()


# ── 케이스 5: get_trace 없으면 None ──────────────────────────────────────────

def test_get_trace_returns_none_for_missing(tmp_path):
    """존재하지 않는 traceId 조회 시 None 을 반환해야 한다."""
    log_file = tmp_path / "empty.jsonl"
    set_log_file_path(log_file)
    try:
        result = get_trace("gen-nonexistent")
        assert result is None, f"없는 traceId 에 대해 None 기대, 실제={result}"
    finally:
        reset_log_file_path()


# ── 케이스 6: make_tracing_proxy 단위 테스트 ─────────────────────────────────

@pytest.mark.asyncio
async def test_tracing_proxy_records_call():
    """make_tracing_proxy 가 LLM 호출을 llm_calls 에 기록하는지 검증한다."""
    from app.services.llm.base import LLMRequest

    call_result = SimpleNamespace(
        content="응답 텍스트",
        token_usage={"prompt_tokens": 5, "completion_tokens": 15, "total_tokens": 20},
    )

    async def fake_chat(req):
        return call_result

    fake_handler = SimpleNamespace(chat=fake_chat)
    proxy = make_tracing_proxy(fake_handler)

    req = LLMRequest.simple(
        prompt="테스트 프롬프트",
        system_prompt="테스트 시스템",
        call_type="test_call",
    )
    resp = await proxy.chat(req)

    assert resp.content == "응답 텍스트"
    assert len(proxy.llm_calls) == 1
    call = proxy.llm_calls[0]
    assert call["callType"] == "test_call"
    assert "테스트 시스템" in call["systemPrompt"]
    assert "테스트 프롬프트" in call["prompt"]
    assert call["response"] == "응답 텍스트"
    assert call["ok"] is True
    assert call["durationMs"] >= 0


@pytest.mark.asyncio
async def test_tracing_proxy_records_failed_call():
    """make_tracing_proxy 가 실패한 LLM 호출도 ok=False 로 기록하는지 검증한다."""
    from app.services.llm.base import LLMRequest

    async def failing_chat(req):
        raise ConnectionError("연결 실패")

    fake_handler = SimpleNamespace(chat=failing_chat)
    proxy = make_tracing_proxy(fake_handler)

    req = LLMRequest.simple(prompt="실패 테스트", call_type="fail_test")

    with pytest.raises(ConnectionError):
        await proxy.chat(req)

    assert len(proxy.llm_calls) == 1
    call = proxy.llm_calls[0]
    assert call["ok"] is False
    assert call["callType"] == "fail_test"


# ── 케이스 7: read_traces 파일 없으면 빈 리스트 ──────────────────────────────

def test_read_traces_empty_when_no_file(tmp_path):
    """로그 파일이 없으면 read_traces 가 빈 리스트를 반환해야 한다."""
    set_log_file_path(tmp_path / "nonexistent.jsonl")
    try:
        result = read_traces(limit=10)
        assert result == [], f"파일 없을 때 빈 리스트 기대, 실제={result}"
    finally:
        reset_log_file_path()


# ── 케이스 8: traceId 가 반환 dict 에 포함 ───────────────────────────────────

@pytest.mark.asyncio
async def test_generate_workflow_returns_trace_id(monkeypatch, _isolate_log_path):
    """generate_workflow 반환 dict 에 traceId 가 포함되어야 한다."""
    resps = [
        _fake_resp(_SKELETON_RESP),
        _fake_resp(json.dumps(_GOOD_DRAFT)),
    ]
    call_idx = [0]

    async def fake_chat(req):
        idx = call_idx[0]
        call_idx[0] += 1
        return resps[idx] if idx < len(resps) else _fake_resp(json.dumps(_GOOD_DRAFT))

    fake_handler = SimpleNamespace(chat=fake_chat)
    monkeypatch.setattr("app.services.workflow_generator.get_llm_handler", lambda: fake_handler)
    from unittest.mock import AsyncMock
    monkeypatch.setattr(
        "app.services.workflow_generator._collect_materials",
        AsyncMock(return_value={"apiDefinitions": [], "instanceDbs": [], "aiNodes": [], "knowledgeCategories": []}),
    )
    monkeypatch.setattr(
        "app.services.workflow_generator.validate_workflow_structure",
        AsyncMock(return_value={"valid": True, "errorCount": 0, "warningCount": 0, "errors": [], "warnings": []}),
    )

    async with async_session_maker() as db:
        result = await generate_workflow("traceId 포함 테스트", db)

    assert "traceId" in result, "generate_workflow 반환값에 traceId 없음"
    assert isinstance(result["traceId"], str), "traceId 가 str 이 아님"
    assert result["traceId"].startswith("gen-"), f"traceId 형식 오류: {result['traceId']}"


# ── 케이스 9: trace 가 userMessage + assistantMessage 를 저장 ────────────────

@pytest.mark.asyncio
async def test_generate_workflow_records_user_and_assistant_message(monkeypatch, _isolate_log_path):
    """generate_workflow 가 trace 에 userMessage(=입력) 와 assistantMessage(=AI 회신)
    를 모두 저장해야 한다."""
    resps = [
        _fake_resp(_SKELETON_RESP),
        _fake_resp(json.dumps(_GOOD_DRAFT)),
    ]
    call_idx = [0]

    async def fake_chat(req):
        idx = call_idx[0]
        call_idx[0] += 1
        return resps[idx] if idx < len(resps) else _fake_resp(json.dumps(_GOOD_DRAFT))

    fake_handler = SimpleNamespace(chat=fake_chat)
    monkeypatch.setattr("app.services.workflow_generator.get_llm_handler", lambda: fake_handler)
    from unittest.mock import AsyncMock
    monkeypatch.setattr(
        "app.services.workflow_generator._collect_materials",
        AsyncMock(return_value={"apiDefinitions": [], "instanceDbs": [], "aiNodes": [], "knowledgeCategories": []}),
    )
    monkeypatch.setattr(
        "app.services.workflow_generator.validate_workflow_structure",
        AsyncMock(return_value={"valid": True, "errorCount": 0, "warningCount": 0, "errors": [], "warnings": []}),
    )

    description = "사용자 메시지 보존 검증"
    async with async_session_maker() as db:
        result = await generate_workflow(description, db)

    trace = get_trace(result["traceId"])
    assert trace is not None
    # userMessage == 입력 설명
    assert trace.get("userMessage") == description, \
        f"userMessage 불일치: {trace.get('userMessage')!r}"
    # assistantMessage == 반환된 assistantMessage 와 동일
    assert trace.get("assistantMessage") is not None, "assistantMessage 가 None"
    assert trace.get("assistantMessage") == result.get("assistantMessage"), \
        "trace.assistantMessage 가 반환 assistantMessage 와 다름"
    # description back-compat 유지
    assert trace.get("description") == description


# ── 케이스 10: get_traces_by_ids 순서 보존 + 누락 skip ───────────────────────

def test_get_traces_by_ids_preserves_order_and_skips_missing(tmp_path):
    """get_traces_by_ids 는 입력 id 순서대로 반환하고, 없는 id 는 건너뛴다."""
    log_file = tmp_path / "ordering.jsonl"
    set_log_file_path(log_file)
    try:
        # 파일에는 c, a, b 순으로 기록되어 있어도
        append_trace({"traceId": "gen-c", "userMessage": "C", "assistantMessage": "rc"})
        append_trace({"traceId": "gen-a", "userMessage": "A", "assistantMessage": "ra"})
        append_trace({"traceId": "gen-b", "userMessage": "B", "assistantMessage": "rb"})

        # 입력 순서 a, b, c (+ 없는 id) 로 요청하면 그 순서대로 반환
        out = get_traces_by_ids(["gen-a", "gen-b", "gen-c", "gen-missing"])
        assert [t["traceId"] for t in out] == ["gen-a", "gen-b", "gen-c"], \
            f"순서/누락 처리 오류: {[t.get('traceId') for t in out]}"

        # 빈 입력 → 빈 리스트
        assert get_traces_by_ids([]) == []
        # 전부 없는 id → 빈 리스트
        assert get_traces_by_ids(["gen-x", "gen-y"]) == []
    finally:
        reset_log_file_path()


def test_trace_to_conversation_item_shape(tmp_path):
    """trace_to_conversation_item 이 약속된 필드 집합을 반환하고
    errorCount/warningCount 를 finalValidation 에서 파생한다."""
    trace = {
        "traceId": "gen-z",
        "createdAt": "2026-06-04T00:00:00",
        "mode": "create",
        "userMessage": "유저 메시지",
        "assistantMessage": "AI 회신",
        "attempts": 2,
        "result": "valid",
        "finalValidation": {"errorCount": 1, "warningCount": 3},
    }
    item = trace_to_conversation_item(trace)
    assert item == {
        "traceId": "gen-z",
        "createdAt": "2026-06-04T00:00:00",
        "mode": "create",
        "userMessage": "유저 메시지",
        "assistantMessage": "AI 회신",
        "attempts": 2,
        "result": "valid",
        "errorCount": 1,
        "warningCount": 3,
    }
    # userMessage 부재 시 description 폴백
    legacy = {"traceId": "gen-old", "description": "구버전 설명"}
    item2 = trace_to_conversation_item(legacy)
    assert item2["userMessage"] == "구버전 설명"
    assert item2["assistantMessage"] == ""
    assert item2["errorCount"] == 0 and item2["warningCount"] == 0
