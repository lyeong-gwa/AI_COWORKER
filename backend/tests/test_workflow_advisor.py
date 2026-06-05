"""워크플로우 advisor 단위 테스트.

규칙별 유발 케이스 + 깨끗한 케이스(suggestions 0).

규칙 목록:
    R1: instance-db-insert dedup 키만 저장 (warning)
    R2: api-call POST body_template 변수 누락 (warning)
    R3: ai-custom inline prompt 미존재 필드 참조 (info)
    R4: knowledge searchField 비표준 (info)
    R5: validate_workflow_structure 경고 흡수
    CLEAN: 깨끗한 워크플로우 → suggestions 0
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from app.core.database import async_session_maker
from app.services.workflow_advisor import advise_workflow


# ── 노드/연결 빌더 (test_workflow_validator.py 패턴 재사용) ──────────────────


def _node(
    nid: str,
    def_type: str,
    name: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
    input_mapping: Optional[Dict[str, Any]] = None,
) -> SimpleNamespace:
    """테스트용 노드 SimpleNamespace."""
    return SimpleNamespace(
        id=nid,
        definitionType=def_type,
        definition_type=def_type,
        name=name or nid,
        config=config or {},
        config_overrides=config_overrides or {},
        configOverrides=config_overrides or {},
        input_mapping=input_mapping or {},
        inputMapping=input_mapping or {},
    )


def _conn(
    src: str,
    tgt: str,
    handle: Optional[str] = None,
) -> SimpleNamespace:
    """테스트용 연결 SimpleNamespace."""
    return SimpleNamespace(
        id=f"conn-{uuid.uuid4().hex[:6]}",
        source_node_id=src,
        sourceNodeId=src,
        target_node_id=tgt,
        targetNodeId=tgt,
        source_handle=handle,
        sourceHandle=handle,
        target_handle=None,
        targetHandle=None,
    )


async def _advise(nodes, conns):
    """공통 advise 호출 헬퍼."""
    async with async_session_maker() as db:
        return await advise_workflow(nodes, conns, db)


def _codes(suggestions: List[Dict]) -> List[str]:
    return [s["code"] for s in suggestions]


def _severities(suggestions: List[Dict]) -> List[str]:
    return [s["severity"] for s in suggestions]


# ── CLEAN: 깨끗한 워크플로우 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clean_workflow_no_suggestions():
    """깨끗한 form-start → result 워크플로우 → suggestions 빈 배열."""
    n1 = _node("n1", "form-start", "폼 시작")
    n2 = _node("n2", "result", "결과")
    c1 = _conn("n1", "n2")

    result = await _advise([n1, n2], [c1])

    assert result["count"] == 0
    assert result["suggestions"] == []


# ── R1: instance-db-insert dedup 키만 저장 ───────────────────────────────────


@pytest.mark.asyncio
async def test_r1_dedup_only_empty_data_template():
    """R1: dataTemplate 키가 0개인 경우 경고 발생."""
    n1 = _node("n1", "form-start", "시작")
    n2 = _node(
        "n2", "instance-db-insert", "이력 저장",
        config={
            "instanceDbId": "idb-test",
            "sourceMode": "input",
            "dataTemplate": {},  # 키 0개
        },
    )
    n3 = _node("n3", "result", "결과")
    c1 = _conn("n1", "n2")
    c2 = _conn("n2", "n3")

    result = await _advise([n1, n2, n3], [c1, c2])

    codes = _codes(result["suggestions"])
    assert "r1-dedup-only" in codes


@pytest.mark.asyncio
async def test_r1_dedup_only_identifier_keys():
    """R1: dataTemplate에 식별자 키(board_id, id)만 있는 경우 경고."""
    n1 = _node("n1", "form-start", "시작")
    n2 = _node(
        "n2", "instance-db-insert", "이력 저장",
        config={
            "instanceDbId": "idb-test",
            "sourceMode": "input",
            "dataTemplate": {"board_id": "{{board_id}}", "id": "{{id}}"},
        },
    )
    n3 = _node("n3", "result", "결과")

    result = await _advise([n1, n2, n3], [_conn("n1", "n2"), _conn("n2", "n3")])

    codes = _codes(result["suggestions"])
    assert "r1-dedup-only" in codes
    # suggestion 문구에 '답변 본문' 언급 확인
    r1_sug = next(s for s in result["suggestions"] if s["code"] == "r1-dedup-only")
    assert "response" in r1_sug["suggestion"] or "dataTemplate" in r1_sug["suggestion"]


@pytest.mark.asyncio
async def test_r1_no_warning_when_meaningful_keys():
    """R1: dataTemplate에 의미 있는 키(response, title 등)가 있으면 경고 없음."""
    n1 = _node("n1", "form-start", "시작")
    n2 = _node(
        "n2", "instance-db-insert", "이력 저장",
        config={
            "instanceDbId": "idb-test",
            "sourceMode": "input",
            "dataTemplate": {
                "board_id": "{{board_id}}",
                "response": "{{response}}",  # 의미 있는 키
                "title": "{{title}}",
            },
        },
    )
    n3 = _node("n3", "result", "결과")

    result = await _advise([n1, n2, n3], [_conn("n1", "n2"), _conn("n2", "n3")])

    codes = _codes(result["suggestions"])
    assert "r1-dedup-only" not in codes


@pytest.mark.asyncio
async def test_r1_no_warning_without_data_template():
    """R1: dataTemplate이 없으면(sourceMode=auto) 규칙 미적용."""
    n1 = _node("n1", "form-start", "시작")
    n2 = _node(
        "n2", "instance-db-insert", "이력 저장",
        config={"instanceDbId": "idb-test", "sourceMode": "auto"},
    )
    n3 = _node("n3", "result", "결과")

    result = await _advise([n1, n2, n3], [_conn("n1", "n2"), _conn("n2", "n3")])

    codes = _codes(result["suggestions"])
    assert "r1-dedup-only" not in codes


# ── R2: api-call POST body_template 변수 누락 ────────────────────────────────


@pytest.mark.asyncio
async def test_r2_post_body_var_missing():
    """R2: api-call POST 노드의 body_template 변수가 defaultParams에 없으면 경고."""
    from app.models.api_definition import ApiDefinition

    api_id = f"api-{uuid.uuid4().hex[:8]}"
    async with async_session_maker() as db:
        api_def = ApiDefinition(
            id=api_id,
            name="테스트 POST API",
            description="R2 테스트",
            url_template="http://localhost/post",
            method="POST",
            headers={},
            tags=[],
            parameters=[],
            auth_type="none",
            auth_config={},
            body_template='{"message": "{{message}}", "boardId": "{{board_id}}"}',
        )
        db.add(api_def)
        await db.commit()

    n1 = _node("n1", "form-start", "시작")
    n2 = _node(
        "n2", "api-call", "POST 호출",
        config={
            "apiDefinitionId": api_id,
            "defaultParams": {},  # message, board_id 모두 없음
        },
    )
    n3 = _node("n3", "result", "결과")

    result = await _advise([n1, n2, n3], [_conn("n1", "n2"), _conn("n2", "n3")])

    codes = _codes(result["suggestions"])
    assert "r2-body-var-missing" in codes

    # 정리
    async with async_session_maker() as db:
        from sqlalchemy import delete
        await db.execute(delete(ApiDefinition).where(ApiDefinition.id == api_id))
        await db.commit()


@pytest.mark.asyncio
async def test_r2_no_warning_when_params_provided():
    """R2: body_template 변수가 defaultParams에 모두 있으면 경고 없음."""
    from app.models.api_definition import ApiDefinition

    api_id = f"api-{uuid.uuid4().hex[:8]}"
    async with async_session_maker() as db:
        api_def = ApiDefinition(
            id=api_id,
            name="충족된 POST API",
            description="R2 정상 테스트",
            url_template="http://localhost/post2",
            method="POST",
            headers={},
            tags=[],
            parameters=[],
            auth_type="none",
            auth_config={},
            body_template='{"message": "{{message}}"}',
        )
        db.add(api_def)
        await db.commit()

    n1 = _node("n1", "form-start", "시작")
    n2 = _node(
        "n2", "api-call", "POST 호출",
        config={
            "apiDefinitionId": api_id,
            "defaultParams": {"message": "안녕하세요"},  # 변수 충족
        },
    )
    n3 = _node("n3", "result", "결과")

    result = await _advise([n1, n2, n3], [_conn("n1", "n2"), _conn("n2", "n3")])

    codes = _codes(result["suggestions"])
    assert "r2-body-var-missing" not in codes

    # 정리
    async with async_session_maker() as db:
        from sqlalchemy import delete
        await db.execute(delete(ApiDefinition).where(ApiDefinition.id == api_id))
        await db.commit()


@pytest.mark.asyncio
async def test_r2_no_warning_for_get_api():
    """R2: GET 메서드 API는 body_template 없으므로 경고 없음."""
    from app.models.api_definition import ApiDefinition

    api_id = f"api-{uuid.uuid4().hex[:8]}"
    async with async_session_maker() as db:
        api_def = ApiDefinition(
            id=api_id,
            name="GET API",
            description="R2 GET 테스트",
            url_template="http://localhost/get",
            method="GET",
            headers={},
            tags=[],
            parameters=[],
            auth_type="none",
            auth_config={},
            body_template=None,
        )
        db.add(api_def)
        await db.commit()

    n1 = _node("n1", "form-start", "시작")
    n2 = _node(
        "n2", "api-call", "GET 호출",
        config={"apiDefinitionId": api_id, "defaultParams": {}},
    )
    n3 = _node("n3", "result", "결과")

    result = await _advise([n1, n2, n3], [_conn("n1", "n2"), _conn("n2", "n3")])

    codes = _codes(result["suggestions"])
    assert "r2-body-var-missing" not in codes

    # 정리
    async with async_session_maker() as db:
        from sqlalchemy import delete
        await db.execute(delete(ApiDefinition).where(ApiDefinition.id == api_id))
        await db.commit()


# ── R3: ai-custom inline prompt 미존재 필드 참조 ─────────────────────────────


@pytest.mark.asyncio
async def test_r3_prompt_unknown_var():
    """R3: inline prompt에서 업스트림 키에 없는 변수 참조 → info."""
    n1 = _node("n1", "form-start", "시작", config={"fields": [{"name": "query"}]})
    n2 = _node(
        "n2", "ai-custom", "AI 응답",
        config={
            # ai_node_id 없음 (inline)
            "prompt": "{{query}}를 분석하고 {{totally_unknown_field_xyz}}도 참조해줘.",
        },
    )
    n3 = _node("n3", "result", "결과")

    result = await _advise([n1, n2, n3], [_conn("n1", "n2"), _conn("n2", "n3")])

    codes = _codes(result["suggestions"])
    assert "r3-prompt-unknown-var" in codes
    # severity 는 info
    r3_sug = [s for s in result["suggestions"] if s["code"] == "r3-prompt-unknown-var"]
    assert all(s["severity"] == "info" for s in r3_sug)


@pytest.mark.asyncio
async def test_r3_no_info_when_ai_node_id_set():
    """R3: ai_node_id 가 있으면 inline prompt 규칙 미적용."""
    n1 = _node("n1", "form-start", "시작")
    n2 = _node(
        "n2", "ai-custom", "AI 응답",
        config={
            "ai_node_id": "some-ai-node",
            "prompt": "{{totally_unknown_field}}",  # 있더라도 적용 X
        },
    )
    n3 = _node("n3", "result", "결과")

    result = await _advise([n1, n2, n3], [_conn("n1", "n2"), _conn("n2", "n3")])

    codes = _codes(result["suggestions"])
    assert "r3-prompt-unknown-var" not in codes


@pytest.mark.asyncio
async def test_r3_no_info_for_known_vars():
    """R3: prompt 변수가 업스트림 키로 인식되면 info 없음."""
    n1 = _node("n1", "form-start", "시작", config={"fields": [{"name": "question"}]})
    n2 = _node(
        "n2", "ai-custom", "AI 응답",
        config={"prompt": "{{question}}에 답변해줘. {{response}}도 참고해."},
    )
    n3 = _node("n3", "result", "결과")

    result = await _advise([n1, n2, n3], [_conn("n1", "n2"), _conn("n2", "n3")])

    codes = _codes(result["suggestions"])
    assert "r3-prompt-unknown-var" not in codes


# ── R4: knowledge searchField 비표준 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_r4_unknown_search_field():
    """R4: knowledge searchField 가 업스트림에 없는 키이면 info."""
    n1 = _node("n1", "form-start", "시작")
    n2 = _node(
        "n2", "knowledge", "지식 검색",
        config={"searchField": "totally_nonexistent_field_abc"},
    )
    n3 = _node("n3", "result", "결과")

    result = await _advise([n1, n2, n3], [_conn("n1", "n2"), _conn("n2", "n3")])

    codes = _codes(result["suggestions"])
    assert "r4-search-field-unknown" in codes
    r4_sug = [s for s in result["suggestions"] if s["code"] == "r4-search-field-unknown"]
    assert all(s["severity"] == "info" for s in r4_sug)


@pytest.mark.asyncio
async def test_r4_no_info_for_empty_search_field():
    """R4: searchField 미지정은 자동 쿼리 구성 → info 없음."""
    n1 = _node("n1", "form-start", "시작")
    n2 = _node("n2", "knowledge", "지식 검색", config={"searchField": ""})
    n3 = _node("n3", "result", "결과")

    result = await _advise([n1, n2, n3], [_conn("n1", "n2"), _conn("n2", "n3")])

    codes = _codes(result["suggestions"])
    assert "r4-search-field-unknown" not in codes


@pytest.mark.asyncio
async def test_r4_no_info_for_known_search_field():
    """R4: searchField 가 form-start field 이름이면 info 없음."""
    n1 = _node(
        "n1", "form-start", "시작",
        config={"fields": [{"name": "user_query", "label": "질문", "type": "string"}]},
    )
    n2 = _node(
        "n2", "knowledge", "지식 검색",
        config={"searchField": "user_query"},  # form-start 에서 정의한 필드
    )
    n3 = _node("n3", "result", "결과")

    result = await _advise([n1, n2, n3], [_conn("n1", "n2"), _conn("n2", "n3")])

    codes = _codes(result["suggestions"])
    assert "r4-search-field-unknown" not in codes


# ── R5: validate_workflow_structure 경고 흡수 ────────────────────────────────


@pytest.mark.asyncio
async def test_r5_absorbs_dead_end_warning():
    """R5: dead-end(W3) 경고 흡수 → r5-dead-end 제안 생성."""
    n1 = _node("n1", "form-start", "시작")
    n2 = _node("n2", "ai-custom", "AI")  # 출력 없는 리프 → W3
    c1 = _conn("n1", "n2")

    result = await _advise([n1, n2], [c1])

    codes = _codes(result["suggestions"])
    assert "r5-dead-end" in codes


@pytest.mark.asyncio
async def test_r5_absorbs_type_mismatch_warning():
    """R5: type-mismatch(W2) 경고 흡수 → r5-type-mismatch 제안 생성."""
    n1 = _node("n1", "form-start", "시작")
    n2 = _node("n2", "unpacker", "언패커", config={"arrayField": "data"})
    n3 = _node("n3", "result", "결과")
    c1 = _conn("n1", "n2")
    c2 = _conn("n2", "n3")

    result = await _advise([n1, n2, n3], [c1, c2])

    codes = _codes(result["suggestions"])
    assert "r5-type-mismatch" in codes


@pytest.mark.asyncio
async def test_r5_absorbs_structural_errors():
    """R5: no-trigger 구조 오류 → r5-no-trigger 제안 포함 (severity=warning, [구조 오류] prefix)."""
    # 트리거 없음 → E3 발생
    n1 = _node("n1", "ai-custom", "AI1")
    n2 = _node("n2", "result", "결과")
    c1 = _conn("n1", "n2")

    result = await _advise([n1, n2], [c1])

    codes = _codes(result["suggestions"])
    assert "r5-no-trigger" in codes
    r5 = [s for s in result["suggestions"] if s["code"] == "r5-no-trigger"]
    assert any("[구조 오류]" in s["message"] for s in r5)


# ── 복합 시나리오 ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_multiple_rules_fire_independently():
    """여러 규칙이 동시에 발화되어도 각각 독립적으로 수집된다."""
    # R1 + R3 동시 발화 시나리오
    n1 = _node("n1", "form-start", "시작")
    # R3: inline prompt 에 알 수 없는 변수
    n2 = _node(
        "n2", "ai-custom", "AI",
        config={"prompt": "{{totally_unknown_abc}} 처리해줘."},
    )
    # R1: dedup 키만 저장
    n3 = _node(
        "n3", "instance-db-insert", "이력 저장",
        config={
            "instanceDbId": "idb-test",
            "sourceMode": "input",
            "dataTemplate": {"board_id": "{{board_id}}"},
        },
    )
    n4 = _node("n4", "result", "결과")

    result = await _advise(
        [n1, n2, n3, n4],
        [_conn("n1", "n2"), _conn("n2", "n3"), _conn("n3", "n4")],
    )

    codes = _codes(result["suggestions"])
    assert "r3-prompt-unknown-var" in codes
    assert "r1-dedup-only" in codes
    assert result["count"] >= 2


@pytest.mark.asyncio
async def test_result_structure():
    """반환 구조가 {suggestions: [...], count: N} 형태인지 확인."""
    n1 = _node("n1", "form-start", "시작")
    n2 = _node("n2", "result", "결과")

    result = await _advise([n1, n2], [_conn("n1", "n2")])

    assert "suggestions" in result
    assert "count" in result
    assert isinstance(result["suggestions"], list)
    assert isinstance(result["count"], int)
    assert result["count"] == len(result["suggestions"])
    # 각 제안은 필수 키를 모두 가져야 함
    for sug in result["suggestions"]:
        assert "code" in sug
        assert "severity" in sug
        assert "message" in sug
        assert "suggestion" in sug
        assert sug["severity"] in ("warning", "info")
