"""Phase 2b — 통일 에러 응답 포맷(envelope) 검증.

설계서 섹션 5.4 요구사항:

    {
        "error": {
            "code":    "SCREAMING_SNAKE",
            "message": "human readable",
            "details": { ... }
        }
    }

검증 대상:
1. NotFound 시 envelope 준수 + code='NOT_FOUND'
2. 요청 body 검증 실패 시 code='VALIDATION_ERROR'
3. 레거시 HTTPException 경로도 동일 envelope 로 변환되는지 확인
4. 응답 상태코드가 envelope 와 정합
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _assert_envelope(payload: dict) -> dict:
    """응답 payload 가 통일 envelope 를 따르는지 검증하고 error 블록을 반환."""
    assert isinstance(payload, dict), f"응답이 dict 가 아님: {type(payload)}"
    assert "error" in payload, f"'error' 키 누락: keys={list(payload)}"
    err = payload["error"]
    assert isinstance(err, dict), "error 값이 dict 가 아님"
    for field in ("code", "message", "details"):
        assert field in err, f"error.{field} 누락: keys={list(err)}"
    assert isinstance(err["code"], str) and err["code"], "code 가 비어있음"
    assert isinstance(err["message"], str) and err["message"], "message 가 비어있음"
    assert isinstance(err["details"], dict), "details 는 dict 여야 함"
    return err


# ── NotFoundError 경로 ─────────────────────────────────────────────────────


def test_workflow_not_found_uses_envelope():
    r = client.get("/api/v1/workflows/___no_such_wf___")
    assert r.status_code == 404
    err = _assert_envelope(r.json())
    assert err["code"] == "NOT_FOUND"
    assert err["details"].get("workflowId") == "___no_such_wf___"


def test_instance_not_found_uses_envelope():
    r = client.get("/api/v1/warehouse/instances/___no_instance___")
    assert r.status_code == 404
    err = _assert_envelope(r.json())
    assert err["code"] == "NOT_FOUND"
    assert err["details"].get("instanceId") == "___no_instance___"


def test_node_not_found_uses_envelope():
    r = client.get("/api/v1/nodes/___no_node___")
    assert r.status_code == 404
    err = _assert_envelope(r.json())
    assert err["code"] == "NOT_FOUND"
    assert err["details"].get("nodeId") == "___no_node___"


def test_api_definition_not_found_uses_envelope():
    """legacy HTTPException 경로(route 에서 raise 한 HTTPException) 도 envelope 로 변환되는지 확인."""
    r = client.get("/api/v1/api-definitions/___no_api_def___")
    assert r.status_code == 404
    err = _assert_envelope(r.json())
    assert err["code"] == "NOT_FOUND"
    assert err["details"].get("apiDefinitionId") == "___no_api_def___"


# ── ValidationError (Pydantic RequestValidationError) ─────────────────────


def test_pydantic_validation_error_uses_envelope():
    """빈 title 로 노드 생성 요청 → 422 VALIDATION_ERROR"""
    r = client.post(
        "/api/v1/nodes",
        json={
            # name 누락 → pydantic validation error
            "description": "x",
        },
    )
    assert r.status_code == 422
    err = _assert_envelope(r.json())
    assert err["code"] == "VALIDATION_ERROR"
    # pydantic errors 배열이 details 에 포함되어야 한다
    assert "errors" in err["details"]
    assert isinstance(err["details"]["errors"], list)
    assert len(err["details"]["errors"]) >= 1


# ── 경로 기반 HTTPException (FastAPI 내부) ────────────────────────────────


def test_unknown_path_returns_envelope():
    """존재하지 않는 경로 — FastAPI 내부 404 도 envelope 로 직렬화."""
    r = client.get("/api/v1/___definitely_not_a_route___")
    assert r.status_code == 404
    err = _assert_envelope(r.json())
    # FastAPI 가 raise 하는 HTTPException(status=404, detail='Not Found') 를
    # 핸들러가 code='NOT_FOUND' 로 변환한다.
    assert err["code"] == "NOT_FOUND"


# ── 메타: 모든 error code 가 SCREAMING_SNAKE 포맷 ─────────────────────────


def test_error_codes_are_screaming_snake():
    import re

    pattern = re.compile(r"^[A-Z][A-Z0-9_]*$")
    probes = [
        "/api/v1/workflows/__missing__",
        "/api/v1/warehouse/instances/__missing__",
        "/api/v1/nodes/__missing__",
        "/api/v1/api-definitions/__missing__",
    ]
    for url in probes:
        r = client.get(url)
        err = _assert_envelope(r.json())
        assert pattern.match(err["code"]), (
            f"code '{err['code']}' ({url}) 가 SCREAMING_SNAKE 패턴에 부합하지 않음"
        )
