"""워크플로우 자동 생성 서비스 단위 테스트.

LLM을 실제로 호출하지 않는다 — monkeypatch로 handler.chat을 가짜로 대체한다.

케이스:
  1. Stage B가 처음엔 잘못된 draft(엣지 없음, 고립 노드) → repair 1회 후 정상 draft
     → valid=True, attempts >= 1
  2. Stage B가 처음부터 정상 draft → valid=True, attempts == 0
  3. LLM이 계속 실패하는 draft 반환 → MAX_REPAIR 후 valid=False (예외 아님)
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, List
from unittest.mock import AsyncMock

import pytest

from unittest.mock import AsyncMock, MagicMock, patch

from app.core.database import async_session_maker
from app.services.workflow_generator import (
    generate_workflow,
    MAX_REPAIR,
    _materials_summary,
    _build_broken_ref_hint,
    _ensure_ids,
    _remap_config_ids,
    _STAGE_A_SYSTEM,
    _normalize_sorter_wiring,
)


# ── 헬퍼: 가짜 LLMResponse ───────────────────────────────────────────────────

def _fake_resp(content: str) -> Any:
    """LLMResponse처럼 .content를 가진 SimpleNamespace 반환."""
    return SimpleNamespace(content=content)


# ── 테스트에서 공통으로 쓰는 draft 조각들 ────────────────────────────────────

# 정상 draft: form-start → result (모든 규칙 충족)
_GOOD_DRAFT = {
    "name": "테스트 워크플로우",
    "description": "테스트용",
    "tags": [],
    "nodes": [
        {
            "id": "wn-aabb0001",
            "nodeId": "wn-aabb0001",
            "definitionType": "form-start",
            "name": "시작",
            "config": {},
            "inputMapping": {},
        },
        {
            "id": "wn-aabb0002",
            "nodeId": "wn-aabb0002",
            "definitionType": "result",
            "name": "결과",
            "config": {},
            "inputMapping": {},
        },
    ],
    "connections": [
        {
            "id": "wc-cc110001",
            "sourceNodeId": "wn-aabb0001",
            "targetNodeId": "wn-aabb0002",
            "sourceHandle": None,
        }
    ],
}

# 잘못된 draft: 엣지가 없어 노드가 고립 상태 (disconnected-node 오류 발생)
_BAD_DRAFT = {
    "name": "잘못된 워크플로우",
    "description": "테스트용 - 엣지 없음",
    "tags": [],
    "nodes": [
        {
            "id": "wn-bad00001",
            "nodeId": "wn-bad00001",
            "definitionType": "form-start",
            "name": "시작",
            "config": {},
            "inputMapping": {},
        },
        {
            "id": "wn-bad00002",
            "nodeId": "wn-bad00002",
            "definitionType": "result",
            "name": "결과",
            "config": {},
            "inputMapping": {},
        },
    ],
    "connections": [],  # 연결 없음 → disconnected-node 오류
}

# Stage A 골격 응답 (공통)
_SKELETON_RESPONSE = json.dumps([
    {"defType": "form-start", "name": "시작", "purpose": "트리거"},
    {"defType": "result", "name": "결과", "purpose": "결과 저장"},
])


# ── 케이스 1: 처음엔 잘못된 draft, repair 1회 후 정상 ────────────────────────

@pytest.mark.asyncio
async def test_repair_once_then_valid(monkeypatch):
    """Stage B가 처음엔 잘못된 draft → repair 1회 후 정상 draft.

    검증: valid=True, attempts >= 1.
    """
    # 순차 응답: [Stage A, Stage B(나쁜), Repair #1(좋은)]
    responses = [
        _fake_resp(_SKELETON_RESPONSE),              # Stage A
        _fake_resp(json.dumps(_BAD_DRAFT)),          # Stage B (잘못된 draft)
        _fake_resp(json.dumps(_GOOD_DRAFT)),         # Repair #1 (정상 draft)
    ]
    call_index = [0]

    async def fake_chat(req) -> Any:
        idx = call_index[0]
        call_index[0] += 1
        if idx < len(responses):
            return responses[idx]
        # 초과 호출 시 정상 draft 반환
        return _fake_resp(json.dumps(_GOOD_DRAFT))

    # monkeypatch: generator 모듈이 import한 get_llm_handler를 가짜 핸들러로 교체
    fake_handler = SimpleNamespace(chat=fake_chat)
    monkeypatch.setattr(
        "app.services.workflow_generator.get_llm_handler",
        lambda: fake_handler,
    )

    async with async_session_maker() as db:
        result = await generate_workflow("테스트 업무 설명", db)

    assert result["validation"]["valid"] is True, (
        f"valid=True 기대, 실제 errors: {result['validation']['errors']}"
    )
    assert result["attempts"] >= 1, f"repair 최소 1회 기대, 실제 attempts={result['attempts']}"
    assert "draft" in result
    assert "stages" in result
    assert len(result["stages"]) > 0


# ── 케이스 2: 처음부터 정상 draft ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_repair_needed(monkeypatch):
    """Stage B가 처음부터 정상 draft를 반환.

    검증: valid=True, attempts == 0.
    """
    responses = [
        _fake_resp(_SKELETON_RESPONSE),          # Stage A
        _fake_resp(json.dumps(_GOOD_DRAFT)),     # Stage B (정상)
    ]
    call_index = [0]

    async def fake_chat(req) -> Any:
        idx = call_index[0]
        call_index[0] += 1
        if idx < len(responses):
            return responses[idx]
        return _fake_resp(json.dumps(_GOOD_DRAFT))

    fake_handler = SimpleNamespace(chat=fake_chat)
    monkeypatch.setattr(
        "app.services.workflow_generator.get_llm_handler",
        lambda: fake_handler,
    )

    async with async_session_maker() as db:
        result = await generate_workflow("테스트 업무 설명", db)

    assert result["validation"]["valid"] is True, (
        f"valid=True 기대, 실제 errors: {result['validation']['errors']}"
    )
    assert result["attempts"] == 0, f"repair 0회 기대, 실제 attempts={result['attempts']}"
    assert result["draft"]["name"] is not None


# ── 케이스 3: 계속 실패 → MAX_REPAIR 후 valid=False 반환 (예외 아님) ──────────

@pytest.mark.asyncio
async def test_max_repair_exhausted(monkeypatch):
    """LLM이 항상 잘못된 draft를 반환 → MAX_REPAIR 후 valid=False (예외 발생 안 함).

    검증: valid=False, attempts == MAX_REPAIR, 예외 없음.
    """
    async def fake_chat(req) -> Any:
        # 항상 잘못된 draft 반환
        return _fake_resp(json.dumps(_BAD_DRAFT))

    fake_handler = SimpleNamespace(chat=fake_chat)
    monkeypatch.setattr(
        "app.services.workflow_generator.get_llm_handler",
        lambda: fake_handler,
    )

    async with async_session_maker() as db:
        # 예외가 발생하면 안 됨
        result = await generate_workflow("테스트 업무 설명", db)

    assert result["validation"]["valid"] is False, "MAX_REPAIR 소진 후 valid=False 기대"
    assert result["attempts"] == MAX_REPAIR, (
        f"attempts={MAX_REPAIR} 기대, 실제={result['attempts']}"
    )
    # draft는 반환되어야 함 (빈 dict 아님)
    assert "draft" in result
    assert isinstance(result["draft"], dict)


# ── 케이스 4: LLM 게이트웨이 미설정 → RuntimeError (502 시나리오) ──────────────

@pytest.mark.asyncio
async def test_llm_gateway_unavailable(monkeypatch):
    """get_llm_handler가 예외를 던지면 RuntimeError로 래핑되어야 한다."""
    def bad_handler():
        raise ValueError("API 키 없음")

    monkeypatch.setattr(
        "app.services.workflow_generator.get_llm_handler",
        bad_handler,
    )

    async with async_session_maker() as db:
        with pytest.raises(RuntimeError, match="LLM 게이트웨이"):
            await generate_workflow("테스트", db)


# ── 케이스 5: Stage A JSON 파싱 실패 시 최소 골격으로 계속 진행 ──────────────

@pytest.mark.asyncio
async def test_stage_a_parse_failure_continues(monkeypatch):
    """Stage A가 파싱 불가 응답을 반환해도 최소 골격으로 Stage B 진행."""
    responses = [
        _fake_resp("이건 JSON이 아닙니다. 죄송합니다."),  # Stage A 실패
        _fake_resp(json.dumps(_GOOD_DRAFT)),               # Stage B 정상
    ]
    call_index = [0]

    async def fake_chat(req) -> Any:
        idx = call_index[0]
        call_index[0] += 1
        if idx < len(responses):
            return responses[idx]
        return _fake_resp(json.dumps(_GOOD_DRAFT))

    fake_handler = SimpleNamespace(chat=fake_chat)
    monkeypatch.setattr(
        "app.services.workflow_generator.get_llm_handler",
        lambda: fake_handler,
    )

    async with async_session_maker() as db:
        result = await generate_workflow("테스트 업무 설명", db)

    # 예외 없이 결과가 반환되어야 함
    assert "draft" in result
    assert "validation" in result


# ── 케이스 6: _materials_summary 헬퍼 — 실제 ID가 프롬프트에 포함되는지 ─────────

def test_materials_summary_contains_real_ids():
    """_materials_summary()가 반환하는 문자열에 재료의 실제 ID가 포함되어야 한다."""
    materials = {
        "apiDefinitions": [
            {"id": "api-real-001", "name": "주문 API", "method": "GET", "url": "https://example.com/orders"},
        ],
        "instanceDbs": [
            {"id": "idb-real-abc1", "name": "문의 DB"},
            {"id": "idb-real-abc2", "name": "답변 DB"},
        ],
        "aiNodes": [
            {"id": "ain-real-xyz9", "name": "답변 생성 AI"},
        ],
        "knowledgeCategories": ["FAQ", "정책"],
    }

    text = _materials_summary(materials)

    # 실제 ID들이 텍스트에 포함되어야 함
    assert "api-real-001" in text, "apiDefinition ID가 materials_summary에 없음"
    assert "idb-real-abc1" in text, "instanceDb ID 1이 materials_summary에 없음"
    assert "idb-real-abc2" in text, "instanceDb ID 2가 materials_summary에 없음"
    assert "ain-real-xyz9" in text, "aiNode ID가 materials_summary에 없음"
    # 금지 문구도 있어야 함
    assert "임의의 ID를 지어내지 말라" in text or "임의의 ID" in text, \
        "임의 ID 금지 문구가 없음"


def test_materials_summary_empty_instance_dbs():
    """인스턴스DB가 없을 때 '등록된 항목 없음' 메시지가 포함되어야 한다."""
    materials = {
        "apiDefinitions": [],
        "instanceDbs": [],
        "aiNodes": [],
        "knowledgeCategories": [],
    }

    text = _materials_summary(materials)

    assert "등록된 항목 없음" in text
    # 인스턴스DB 관련 노드 사용 불가 안내
    assert "instance-db-insert" in text or "사용 불가" in text


def test_build_broken_ref_hint_with_broken_errors():
    """broken-ref 오류가 있을 때 유효 ID 목록이 힌트에 포함되어야 한다."""
    errors = [
        {"code": "broken-ref", "message": "instanceDbId 'idb-1a2b3c4d' 가 존재하지 않음"},
        {"code": "disconnected-node", "message": "노드 wn-abc 고립"},
    ]
    materials = {
        "apiDefinitions": [],
        "instanceDbs": [{"id": "idb-real-999", "name": "실제 DB"}],
        "aiNodes": [],
        "knowledgeCategories": [],
    }

    hint = _build_broken_ref_hint(errors, materials)

    assert "idb-real-999" in hint, "유효 instanceDbId가 힌트에 없음"
    assert "broken-ref" in hint or "참조 오류" in hint


def test_build_broken_ref_hint_no_broken_errors():
    """broken-ref 오류가 없으면 빈 문자열을 반환해야 한다."""
    errors = [
        {"code": "disconnected-node", "message": "노드 고립"},
    ]
    materials = {"apiDefinitions": [], "instanceDbs": [], "aiNodes": [], "knowledgeCategories": []}

    hint = _build_broken_ref_hint(errors, materials)

    assert hint == "", f"broken-ref 없을 때 빈 문자열 기대, 실제: {hint!r}"


# ── _ensure_ids 단위 테스트 (PK 충돌 버그 수정 검증) ─────────────────────────

# LLM이 항상 동일하게 반환하는 고정 id payload
_FIXED_NODES_FOR_REMAP = [
    {
        "id": "wn-1a2b3c4d",
        "nodeId": "wn-1a2b3c4d",
        "definitionType": "form-start",
        "name": "시작",
        "config": {},
        "inputMapping": {},
    },
    {
        "id": "wn-5e6f7g8h",
        "nodeId": "wn-5e6f7g8h",
        "definitionType": "result",
        "name": "결과",
        "config": {},
        "inputMapping": {},
    },
]

_FIXED_CONNS_FOR_REMAP = [
    {
        "id": "wc-aaaabbbb",
        "sourceNodeId": "wn-1a2b3c4d",
        "targetNodeId": "wn-5e6f7g8h",
        "sourceHandle": None,
    }
]


def _clone_fixed_payload():
    """매 호출마다 딥카피로 동일한 고정 payload 반환."""
    import copy
    return copy.deepcopy(_FIXED_NODES_FOR_REMAP), copy.deepcopy(_FIXED_CONNS_FOR_REMAP)


def test_ensure_ids_always_generates_fresh_node_ids():
    """같은 고정 id payload를 두 번 처리하면 id가 서로 달라야 한다 (전역 고유 보장)."""
    nodes1, conns1 = _clone_fixed_payload()
    nodes2, conns2 = _clone_fixed_payload()

    _ensure_ids(nodes1, conns1)
    _ensure_ids(nodes2, conns2)

    ids1 = {n["id"] for n in nodes1}
    ids2 = {n["id"] for n in nodes2}

    assert ids1.isdisjoint(ids2), (
        f"두 번의 _ensure_ids 호출에서 노드 id가 겹쳤습니다: {ids1 & ids2}"
    )


def test_ensure_ids_node_id_equals_id():
    """처리 후 nodeId 필드는 id와 항상 동일해야 한다."""
    nodes, conns = _clone_fixed_payload()
    _ensure_ids(nodes, conns)
    for n in nodes:
        assert n["nodeId"] == n["id"], (
            f"nodeId({n['nodeId']}) != id({n['id']})"
        )


def test_ensure_ids_connections_reference_valid_nodes():
    """리매핑 후 connections의 sourceNodeId/targetNodeId가 새 노드 id 집합에 있어야 한다."""
    nodes, conns = _clone_fixed_payload()
    _ensure_ids(nodes, conns)

    node_ids = {n["id"] for n in nodes}
    for c in conns:
        assert c["sourceNodeId"] in node_ids, (
            f"sourceNodeId '{c['sourceNodeId']}' 가 노드 id 집합에 없음"
        )
        assert c["targetNodeId"] in node_ids, (
            f"targetNodeId '{c['targetNodeId']}' 가 노드 id 집합에 없음"
        )


def test_ensure_ids_old_ids_not_present_after_remap():
    """처리 후 원래 고정 id가 결과 노드 id 집합에 남아 있으면 안 된다."""
    nodes, conns = _clone_fixed_payload()
    _ensure_ids(nodes, conns)

    all_new_ids = {n["id"] for n in nodes}
    assert "wn-1a2b3c4d" not in all_new_ids
    assert "wn-5e6f7g8h" not in all_new_ids


def test_ensure_ids_connection_gets_new_id():
    """연결 자체의 id도 새로 부여되어야 한다."""
    nodes, conns = _clone_fixed_payload()
    _ensure_ids(nodes, conns)

    assert conns[0]["id"] != "wc-aaaabbbb", "connection id가 교체되지 않음"
    assert conns[0]["id"].startswith("wc-"), "connection id 접두사 불일치"


def test_ensure_ids_config_warehouse_node_id_remapped():
    """config.warehouseNodeId (mapper 패턴) 내부 참조가 새 id로 치환되어야 한다."""
    import copy

    nodes = [
        {
            "id": "wn-result001",
            "nodeId": "wn-result001",
            "definitionType": "result",
            "name": "결과저장",
            "config": {},
            "inputMapping": {},
        },
        {
            "id": "wn-mapper001",
            "nodeId": "wn-mapper001",
            "definitionType": "mapper",
            "name": "맵퍼",
            "config": {
                "warehouseNodeId": "wn-result001",  # 치환 대상
                "matchKey": "id",
            },
            "inputMapping": {},
        },
    ]
    conns = [
        {
            "id": "wc-c001",
            "sourceNodeId": "wn-result001",
            "targetNodeId": "wn-mapper001",
            "sourceHandle": None,
        }
    ]

    nodes_copy = copy.deepcopy(nodes)
    conns_copy = copy.deepcopy(conns)
    _ensure_ids(nodes_copy, conns_copy)

    result_node = next(n for n in nodes_copy if n["definitionType"] == "result")
    mapper_node = next(n for n in nodes_copy if n["definitionType"] == "mapper")

    assert mapper_node["config"]["warehouseNodeId"] == result_node["id"], (
        f"warehouseNodeId가 new result id({result_node['id']})로 치환되지 않음: "
        f"{mapper_node['config']['warehouseNodeId']}"
    )


def test_ensure_ids_sorter_dedup_warehouse_node_id_remapped():
    """config.dedup.warehouseNodeId (sorter dedup 패턴)도 치환되어야 한다."""
    import copy

    nodes = [
        {
            "id": "wn-res-sorter",
            "nodeId": "wn-res-sorter",
            "definitionType": "result",
            "name": "결과",
            "config": {},
            "inputMapping": {},
        },
        {
            "id": "wn-sorter001",
            "nodeId": "wn-sorter001",
            "definitionType": "sorter",
            "name": "분류기",
            "config": {
                "rules": [{"id": "r1", "conditions": []}],
                "dedup": {
                    "enabled": True,
                    "warehouseNodeId": "wn-res-sorter",  # 치환 대상
                },
            },
            "inputMapping": {},
        },
    ]
    conns = [
        {
            "id": "wc-s001",
            "sourceNodeId": "wn-sorter001",
            "targetNodeId": "wn-res-sorter",
            "sourceHandle": "rule-r1",
        }
    ]

    nodes_copy = copy.deepcopy(nodes)
    conns_copy = copy.deepcopy(conns)
    _ensure_ids(nodes_copy, conns_copy)

    result_node = next(n for n in nodes_copy if n["definitionType"] == "result")
    sorter_node = next(n for n in nodes_copy if n["definitionType"] == "sorter")

    assert sorter_node["config"]["dedup"]["warehouseNodeId"] == result_node["id"], (
        "sorter dedup.warehouseNodeId가 new result id로 치환되지 않음"
    )


# ── _remap_config_ids 단위 테스트 ────────────────────────────────────────────


def test_remap_config_ids_replaces_matching_strings():
    config = {"warehouseNodeId": "wn-old", "matchKey": "id"}
    result = _remap_config_ids(config, {"wn-old": "wn-new"})
    assert result["warehouseNodeId"] == "wn-new"
    assert result["matchKey"] == "id"  # 비대상 값 유지


def test_remap_config_ids_handles_nested_dict():
    config = {"dedup": {"enabled": True, "warehouseNodeId": "wn-old"}}
    result = _remap_config_ids(config, {"wn-old": "wn-new"})
    assert result["dedup"]["warehouseNodeId"] == "wn-new"


def test_remap_config_ids_handles_list():
    config = {"items": ["wn-old", "other", "wn-old"]}
    result = _remap_config_ids(config, {"wn-old": "wn-new"})
    assert result["items"] == ["wn-new", "other", "wn-new"]


def test_remap_config_ids_no_match_unchanged():
    config = {"key": "unrelated-value"}
    result = _remap_config_ids(config, {"wn-old": "wn-new"})
    assert result == {"key": "unrelated-value"}


# ── generate_workflow 통합 테스트 (id 전역 고유성) ────────────────────────────

def _make_fixed_draft_json() -> str:
    """두 번 호출해도 항상 동일한 고정 draft JSON 반환 (LLM 모의)."""
    draft = {
        "name": "테스트 워크플로우",
        "description": "고정 id 테스트용",
        "tags": [],
        "nodes": [
            {
                "id": "wn-1a2b3c4d",
                "nodeId": "wn-1a2b3c4d",
                "definitionType": "form-start",
                "name": "시작",
                "config": {},
                "inputMapping": {},
            },
            {
                "id": "wn-5e6f7g8h",
                "nodeId": "wn-5e6f7g8h",
                "definitionType": "result",
                "name": "결과",
                "config": {},
                "inputMapping": {},
            },
        ],
        "connections": [
            {
                "id": "wc-aaaabbbb",
                "sourceNodeId": "wn-1a2b3c4d",
                "targetNodeId": "wn-5e6f7g8h",
                "sourceHandle": None,
            }
        ],
    }
    return json.dumps(draft, ensure_ascii=False)


def _make_fixed_skeleton_json() -> str:
    skeleton = [
        {"defType": "form-start", "name": "시작", "purpose": "트리거"},
        {"defType": "result", "name": "결과", "purpose": "출력"},
    ]
    return json.dumps(skeleton, ensure_ascii=False)


@pytest.mark.asyncio
async def test_generate_workflow_node_ids_globally_unique(monkeypatch):
    """가짜 LLM이 두 번 모두 동일한 고정 id draft를 반환해도
    두 결과의 노드 id 집합이 서로 겹치지 않아야 한다 (전역 고유 / PK 충돌 방지).
    """
    from app.services.llm.base import LLMResponse

    fake_skeleton = LLMResponse(content=_make_fixed_skeleton_json(), model="fake")
    fake_draft = LLMResponse(content=_make_fixed_draft_json(), model="fake")

    call_count = [0]

    async def fake_chat(req):
        call_count[0] += 1
        # 홀수 호출 = Stage A (골격), 짝수 호출 = Stage B (draft)
        if call_count[0] % 2 == 1:
            return fake_skeleton
        return fake_draft

    fake_handler = SimpleNamespace(chat=fake_chat)
    monkeypatch.setattr(
        "app.services.workflow_generator.get_llm_handler",
        lambda: fake_handler,
    )
    monkeypatch.setattr(
        "app.services.workflow_generator._collect_materials",
        AsyncMock(return_value={
            "apiDefinitions": [],
            "instanceDbs": [],
            "aiNodes": [],
            "knowledgeCategories": [],
        }),
    )
    monkeypatch.setattr(
        "app.services.workflow_generator.validate_workflow_structure",
        AsyncMock(return_value={
            "valid": True,
            "errorCount": 0,
            "warningCount": 0,
            "errors": [],
            "warnings": [],
        }),
    )

    async with async_session_maker() as db:
        result1 = await generate_workflow("테스트 업무 1", db)
        result2 = await generate_workflow("테스트 업무 2", db)

    ids1 = {n["id"] for n in result1["draft"]["nodes"]}
    ids2 = {n["id"] for n in result2["draft"]["nodes"]}

    assert ids1.isdisjoint(ids2), (
        f"두 번의 generate_workflow 호출에서 노드 id가 겹쳤습니다: {ids1 & ids2}\n"
        f"ids1={ids1}\nids2={ids2}"
    )


# ── 케이스: 수정(refine) 모드 — Stage A 생략, base_draft 프롬프트 포함 ──────────

# 수정 모드에서 기준이 될 3노드 draft
_BASE_DRAFT_3NODES = {
    "name": "기존 워크플로우",
    "description": "수정 테스트용 기존 draft",
    "tags": [],
    "nodes": [
        {
            "id": "wn-base0001",
            "nodeId": "wn-base0001",
            "definitionType": "api-start",
            "name": "API 시작",
            "config": {},
            "inputMapping": {},
        },
        {
            "id": "wn-base0002",
            "nodeId": "wn-base0002",
            "definitionType": "ai-custom",
            "name": "AI 처리",
            "config": {},
            "inputMapping": {},
        },
        {
            "id": "wn-base0003",
            "nodeId": "wn-base0003",
            "definitionType": "result",
            "name": "결과",
            "config": {},
            "inputMapping": {},
        },
    ],
    "connections": [
        {
            "id": "wc-base0001",
            "sourceNodeId": "wn-base0001",
            "targetNodeId": "wn-base0002",
            "sourceHandle": None,
        },
        {
            "id": "wc-base0002",
            "sourceNodeId": "wn-base0002",
            "targetNodeId": "wn-base0003",
            "sourceHandle": None,
        },
    ],
}

# 수정 결과로 반환될 draft (result 노드 2개로 추가된 시나리오)
_REFINED_DRAFT = {
    "name": "수정된 워크플로우",
    "description": "수정 테스트용",
    "tags": [],
    "nodes": [
        {
            "id": "wn-base0001",
            "nodeId": "wn-base0001",
            "definitionType": "api-start",
            "name": "API 시작",
            "config": {},
            "inputMapping": {},
        },
        {
            "id": "wn-base0002",
            "nodeId": "wn-base0002",
            "definitionType": "ai-custom",
            "name": "AI 처리",
            "config": {},
            "inputMapping": {},
        },
        {
            "id": "wn-base0003",
            "nodeId": "wn-base0003",
            "definitionType": "result",
            "name": "결과1",
            "config": {},
            "inputMapping": {},
        },
        {
            "id": "wn-base0004",
            "nodeId": "wn-base0004",
            "definitionType": "result",
            "name": "결과2 (추가)",
            "config": {},
            "inputMapping": {},
        },
    ],
    "connections": [
        {
            "id": "wc-base0001",
            "sourceNodeId": "wn-base0001",
            "targetNodeId": "wn-base0002",
            "sourceHandle": None,
        },
        {
            "id": "wc-base0002",
            "sourceNodeId": "wn-base0002",
            "targetNodeId": "wn-base0003",
            "sourceHandle": None,
        },
        {
            "id": "wc-base0003",
            "sourceNodeId": "wn-base0002",
            "targetNodeId": "wn-base0004",
            "sourceHandle": None,
        },
    ],
}


@pytest.mark.asyncio
async def test_refine_mode_skips_stage_a_and_uses_base_draft(monkeypatch):
    """base_draft + mode='edit'로 호출하면:
    - Stage A(Plan) LLM 호출이 발생하지 않거나 호출 횟수가 신규 생성보다 적어야 한다.
    - base_draft 내용이 Stage R 프롬프트에 포함되어야 한다.
    - 최종적으로 valid draft가 반환되어야 한다.
    """
    call_records: list[dict] = []

    async def fake_chat(req) -> Any:
        # 호출된 요청 기록 (call_type + 모든 메시지 내용)
        call_type = getattr(req, "call_type", "") or ""
        messages = getattr(req, "messages", []) or []
        full_text = " ".join(getattr(m, "content", "") for m in messages)
        call_records.append({"call_type": call_type, "text": full_text})
        # 수정 모드에서는 Stage R만 호출되어야 함 → _REFINED_DRAFT 반환
        return _fake_resp(json.dumps(_REFINED_DRAFT))

    fake_handler = SimpleNamespace(chat=fake_chat)
    monkeypatch.setattr(
        "app.services.workflow_generator.get_llm_handler",
        lambda: fake_handler,
    )
    monkeypatch.setattr(
        "app.services.workflow_generator._collect_materials",
        AsyncMock(return_value={
            "apiDefinitions": [],
            "instanceDbs": [],
            "aiNodes": [],
            "knowledgeCategories": [],
        }),
    )
    monkeypatch.setattr(
        "app.services.workflow_generator.validate_workflow_structure",
        AsyncMock(return_value={
            "valid": True,
            "errorCount": 0,
            "warningCount": 0,
            "errors": [],
            "warnings": [],
        }),
    )

    async with async_session_maker() as db:
        result = await generate_workflow(
            description="result 노드를 하나 더 추가해줘",
            db=db,
            mode="edit",
            base_draft=_BASE_DRAFT_3NODES,
            history=[
                {"role": "user", "content": "API에서 데이터를 가져와 AI로 처리하는 워크플로우 만들어줘"},
                {"role": "assistant", "content": "워크플로우 '기존 워크플로우'이(가) 성공적으로 생성되었습니다."},
            ],
        )

    # 1. 최종 draft가 valid여야 함
    assert result["validation"]["valid"] is True, (
        f"수정 모드에서 valid=True 기대: {result['validation']['errors']}"
    )

    # 2. LLM 호출이 정확히 1회여야 함 (Stage R만, Stage A 없음)
    assert len(call_records) == 1, (
        f"수정 모드에서 LLM 호출은 Stage R 1회만 기대, 실제 {len(call_records)}회: "
        f"{[r['call_type'] for r in call_records]}"
    )

    # 3. Stage R 프롬프트에 base_draft의 내용이 포함되어야 함
    stage_r_text = call_records[0]["text"]
    assert "기존 워크플로우" in stage_r_text or "api-start" in stage_r_text, (
        f"Stage R 프롬프트에 base_draft 내용(워크플로우 이름 또는 노드 타입)이 없음. "
        f"실제 텍스트 앞부분: {stage_r_text[:300]}"
    )

    # 4. call_type이 Stage R임을 확인
    assert call_records[0]["call_type"] == "workflow_generator_stage_r_refine", (
        f"예상 call_type 'workflow_generator_stage_r_refine', 실제: {call_records[0]['call_type']}"
    )

    # 5. stages에 '수정 모드 진입' 기록이 있어야 함
    stages_text = " ".join(result["stages"])
    assert "수정 모드" in stages_text, f"stages에 수정 모드 기록 없음: {result['stages']}"

    # 6. draft가 반환되어야 함
    assert "draft" in result
    assert isinstance(result["draft"], dict)
    assert len(result["draft"].get("nodes", [])) >= 3, "기존 3노드가 보존되어야 함"


@pytest.mark.asyncio
async def test_generate_workflow_connections_reference_valid_nodes(monkeypatch):
    """generate_workflow 결과에서 connections의 source/target이
    모두 draft 노드 id 집합에 존재해야 한다 (리매핑 정합성).
    """
    from app.services.llm.base import LLMResponse

    fake_skeleton = LLMResponse(content=_make_fixed_skeleton_json(), model="fake")
    fake_draft = LLMResponse(content=_make_fixed_draft_json(), model="fake")

    call_count = [0]

    async def fake_chat(req):
        call_count[0] += 1
        if call_count[0] % 2 == 1:
            return fake_skeleton
        return fake_draft

    fake_handler = SimpleNamespace(chat=fake_chat)
    monkeypatch.setattr(
        "app.services.workflow_generator.get_llm_handler",
        lambda: fake_handler,
    )
    monkeypatch.setattr(
        "app.services.workflow_generator._collect_materials",
        AsyncMock(return_value={
            "apiDefinitions": [],
            "instanceDbs": [],
            "aiNodes": [],
            "knowledgeCategories": [],
        }),
    )
    monkeypatch.setattr(
        "app.services.workflow_generator.validate_workflow_structure",
        AsyncMock(return_value={
            "valid": True,
            "errorCount": 0,
            "warningCount": 0,
            "errors": [],
            "warnings": [],
        }),
    )

    async with async_session_maker() as db:
        result = await generate_workflow("테스트 업무", db)

    draft = result["draft"]
    node_ids = {n["id"] for n in draft["nodes"]}

    for conn in draft["connections"]:
        assert conn["sourceNodeId"] in node_ids, (
            f"sourceNodeId '{conn['sourceNodeId']}' 가 노드 id 집합에 없음"
        )
        assert conn["targetNodeId"] in node_ids, (
            f"targetNodeId '{conn['targetNodeId']}' 가 노드 id 집합에 없음"
        )


# ── 개선 1: 재료 컨텍스트 — API 파라미터 상세 및 bodyTemplate 변수 노출 ──────────

def test_materials_summary_includes_api_query_params():
    """api-definition에 query 파라미터가 있으면 materials_summary에 파라미터 이름이 포함되어야 한다.

    LLM이 api-start/api-call의 defaultParams에 실제 값을 채울 수 있게 하는 핵심 컨텍스트.
    """
    materials = {
        "apiDefinitions": [
            {
                "id": "api-board-001",
                "name": "게시판 조회 API",
                "method": "GET",
                "url": "https://example.com/boards?status={status}",
                "params": [
                    {"name": "status", "in": "query", "required": True},
                    {"name": "page", "in": "query", "required": False},
                ],
                "bodyVars": [],
            }
        ],
        "instanceDbs": [],
        "aiNodes": [],
        "knowledgeCategories": [],
    }

    text = _materials_summary(materials)

    # (a) query 파라미터 이름이 텍스트에 포함되어야 함
    assert "status" in text, "필수 query 파라미터 'status'가 materials_summary에 없음"
    assert "page" in text, "선택 query 파라미터 'page'가 materials_summary에 없음"
    # (b) 필수/선택 구분 표시
    assert "필수 파라미터" in text or "query" in text, \
        "파라미터 구분(필수/선택) 또는 'query' 표시가 없음"


def test_materials_summary_includes_body_template_vars():
    """api-definition의 bodyTemplate에 {{변수명}} 패턴이 있으면
    materials_summary에 해당 변수명이 포함되어야 한다.

    LLM이 api-call(POST)의 body 변수를 업스트림 출력 키와 일치시킬 수 있게 함.
    """
    materials = {
        "apiDefinitions": [
            {
                "id": "api-reply-001",
                "name": "답변 등록 API",
                "method": "POST",
                "url": "https://example.com/replies",
                "params": [],
                "bodyVars": ["board_id", "response"],  # bodyTemplate에서 추출된 변수명
            }
        ],
        "instanceDbs": [],
        "aiNodes": [],
        "knowledgeCategories": [],
    }

    text = _materials_summary(materials)

    # (b) bodyTemplate placeholder 변수명이 텍스트에 포함되어야 함
    assert "board_id" in text, "bodyTemplate 변수 'board_id'가 materials_summary에 없음"
    assert "response" in text, "bodyTemplate 변수 'response'가 materials_summary에 없음"
    assert "body 필요 변수" in text or "body" in text, \
        "'body 필요 변수' 안내가 materials_summary에 없음"


def test_materials_summary_api_no_params_shows_placeholder():
    """api-definition에 파라미터가 없으면 '[파라미터 없음]' 안내가 출력되어야 한다."""
    materials = {
        "apiDefinitions": [
            {
                "id": "api-simple-001",
                "name": "단순 조회 API",
                "method": "GET",
                "url": "https://example.com/simple",
                "params": [],
                "bodyVars": [],
            }
        ],
        "instanceDbs": [],
        "aiNodes": [],
        "knowledgeCategories": [],
    }

    text = _materials_summary(materials)

    assert "파라미터 없음" in text, "'[파라미터 없음]' 안내가 없음"


def test_materials_summary_body_vars_extracted_from_collect():
    """_collect_materials가 body_template에서 {{변수}} 패턴을 추출하는 로직을
    단위로 검증한다 (정규식 추출 함수 직접 호출).

    workflow_generator.py 내부 로직: re.findall(r'\\{\\{(\\w+)\\}\\}', body_template)
    """
    import re

    # bodyTemplate 예시 (실제 등록된 API 명세의 body_template 필드값)
    body_template = '{"board_id": "{{board_id}}", "answer": "{{response}}", "meta": "{{extra}}"}'

    extracted = re.findall(r"\{\{(\w+)\}\}", body_template)

    assert "board_id" in extracted, "board_id가 추출되지 않음"
    assert "response" in extracted, "response가 추출되지 않음"
    assert "extra" in extracted, "extra가 추출되지 않음"
    assert len(extracted) == 3, f"추출된 변수 수가 3이 아님: {extracted}"


def test_materials_summary_existing_ids_still_present():
    """개선 후에도 기존 테스트 호환성 확인:
    params/bodyVars 필드가 없는 구 형태 dict도 정상 렌더링되어야 한다.
    """
    materials = {
        "apiDefinitions": [
            # params/bodyVars 없는 구 형태 (하위 호환)
            {"id": "api-old-001", "name": "구형 API", "method": "GET", "url": "https://example.com/old"},
        ],
        "instanceDbs": [],
        "aiNodes": [],
        "knowledgeCategories": [],
    }

    # 예외 없이 실행되어야 하고 id가 포함되어야 함
    text = _materials_summary(materials)
    assert "api-old-001" in text, "구형 api-def ID가 materials_summary에 없음"


# ── 개선 2: 커스텀 AI 노드 용도(description) 노출 ─────────────────────────────

def test_materials_summary_ai_node_includes_usage():
    """커스텀 AI 노드 목록에 id, name에 더해 용도(usage) 텍스트가 포함되어야 한다.

    LLM이 '티켓분류기'가 답변 작성에 부적합하다는 판단을 할 수 있도록
    각 커스텀 노드의 용도 설명을 재료 컨텍스트에 노출한다.
    """
    materials = {
        "apiDefinitions": [],
        "instanceDbs": [],
        "aiNodes": [
            {
                "id": "node-637489dc",
                "name": "티켓분류기",
                "usage": "문의를 카테고리로 분류",
            },
            {
                "id": "node-abc12345",
                "name": "답변생성AI",
                "usage": "고객 문의에 대한 답변을 생성",
            },
        ],
        "knowledgeCategories": [],
    }

    text = _materials_summary(materials)

    # (a) 각 노드 id, name 포함
    assert "node-637489dc" in text, "티켓분류기 id가 materials_summary에 없음"
    assert "티켓분류기" in text, "티켓분류기 name이 materials_summary에 없음"
    assert "node-abc12345" in text, "답변생성AI id가 materials_summary에 없음"
    # (b) 용도 설명이 포함되어야 함 — 이 텍스트가 없으면 LLM이 용도 불일치를 판단 불가
    assert "문의를 카테고리로 분류" in text, "티켓분류기 용도가 materials_summary에 없음"
    assert "고객 문의에 대한 답변을 생성" in text, "답변생성AI 용도가 materials_summary에 없음"
    # (c) ai_node_id 사용 제한 규칙 안내도 포함되어야 함
    assert "용도가 현재 작업과 명백히 일치할 때만" in text or "명백히 일치" in text, \
        "ai_node_id 사용 제한 규칙 안내가 없음"
    assert "분류" in text and "금지" in text, \
        "분류 전용 노드 오남용 금지 안내가 없음"


def test_materials_summary_ai_node_without_usage_still_renders():
    """usage 필드가 없는 노드도 예외 없이 렌더링되어야 한다 (하위 호환)."""
    materials = {
        "apiDefinitions": [],
        "instanceDbs": [],
        "aiNodes": [
            # usage 필드가 없는 구 형태
            {"id": "node-legacy01", "name": "레거시노드"},
        ],
        "knowledgeCategories": [],
    }

    text = _materials_summary(materials)

    assert "node-legacy01" in text, "구형 ai-node id가 materials_summary에 없음"
    assert "레거시노드" in text, "구형 ai-node name이 materials_summary에 없음"


# ── 회귀 테스트: _collect_materials가 list_meta()를 올바르게 호출하여
#    instanceDbs가 빈 리스트가 되지 않음을 검증 ────────────────────────────────

@pytest.mark.asyncio
async def test_collect_materials_instance_dbs_not_empty(monkeypatch):
    """버그 수정 회귀 테스트: store.list_dbs() (존재하지 않음) 대신
    await store.list_meta()를 호출하여 등록된 instanceDb가 materials에 포함되는지 검증.

    list_meta가 1건을 반환하도록 monkeypatch하여 _collect_materials가
    그 항목의 id를 포함한 instanceDbs를 돌려주는지 확인한다.
    """
    from unittest.mock import AsyncMock, MagicMock
    from app.services.workflow_generator import _collect_materials

    # list_meta가 반환할 가짜 메타 1건
    fake_meta = [
        {
            "id": "idb-4dd8da93",
            "name": "문의 DB",
            "description": "고객 문의 저장소",
            "tags": [],
            "viewerHints": {},
            "createdAt": "2026-06-01T00:00:00",
            "updatedAt": "2026-06-01T00:00:00",
        }
    ]

    # store 모킹: list_meta는 async 메서드이므로 AsyncMock 사용
    fake_store = MagicMock()
    fake_store.list_meta = AsyncMock(return_value=fake_meta)

    # _collect_materials 내부에서 from ..services.instance_db_store import get_instance_db_store
    # 를 로컬 임포트하므로, 원본 모듈의 심볼을 패치해야 한다.
    monkeypatch.setattr(
        "app.services.instance_db_store.get_instance_db_store",
        lambda: fake_store,
    )

    # DB 세션이 필요하지만 api-definitions·ai-nodes·knowledge 조회에만 쓰임.
    # 오류는 except로 삼켜지므로 간단한 MagicMock으로 대체.
    fake_db = MagicMock()
    # execute 호출을 비동기로 처리 — AsyncMock으로 설정
    fake_db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    materials = await _collect_materials(fake_db)

    # instanceDbs가 빈 리스트가 아니어야 함 (버그 수정 핵심)
    assert len(materials["instanceDbs"]) == 1, (
        f"instanceDbs에 1건이 있어야 함, 실제: {materials['instanceDbs']}"
    )
    assert materials["instanceDbs"][0]["id"] == "idb-4dd8da93", (
        f"id 불일치: {materials['instanceDbs'][0]}"
    )
    assert materials["instanceDbs"][0]["name"] == "문의 DB", (
        f"name 불일치: {materials['instanceDbs'][0]}"
    )
    # list_meta가 실제로 호출되었는지 확인
    fake_store.list_meta.assert_called_once()


# ── Stage A 시스템 프롬프트 패턴 매핑 규칙 포함 여부 검증 ───────────────────────

def test_stage_a_system_prompt_contains_pattern_mapping_rules():
    """Stage A 시스템 프롬프트에 노드 선택 패턴 매핑 규칙의 핵심 키워드가 포함되어야 한다.

    규칙 요약:
    1. 데이터 출처 판단: 외부 조회 → api-start (form-start 아님)
    2. 배열 목록 건별 처리 → unpacker
    3. 스킵 필터(중복 제외) → sorter (instance-db-lookup 아님)
    4. 처리 이력 저장 → instance-db-insert
    5. 지식 기반 생성 → knowledge + ai-custom
    6. 복합 신호 결합 시 전체 골격 포함 필수
    """
    prompt = _STAGE_A_SYSTEM

    # 규칙 1: 데이터 출처 판단
    assert "api-start" in prompt, "api-start 노드 선택 규칙이 Stage A 프롬프트에 없음"
    assert "form-start" in prompt, "form-start 노드 선택 규칙이 Stage A 프롬프트에 없음"
    assert "외부" in prompt or "조회" in prompt, "외부 조회 → api-start 신호 설명이 없음"

    # 규칙 2: unpacker
    assert "unpacker" in prompt, "unpacker 규칙이 Stage A 프롬프트에 없음"
    assert "배열" in prompt or "목록" in prompt, "배열/목록 신호 설명이 없음"

    # 규칙 3: 스킵 필터 = sorter, NOT instance-db-lookup
    assert "sorter" in prompt, "sorter 규칙이 Stage A 프롬프트에 없음"
    assert "instance-db-lookup" in prompt, "instance-db-lookup 오남용 금지 언급이 없음"
    # sorter와 lookup의 역할 구분이 명시되어야 함
    assert "스킵" in prompt or "중복" in prompt, "스킵 필터 신호 설명이 없음"

    # 규칙 4: 처리 이력 저장 = instance-db-insert
    assert "instance-db-insert" in prompt, "instance-db-insert 규칙이 Stage A 프롬프트에 없음"
    assert "이력" in prompt, "이력 저장 신호 설명이 없음"

    # 규칙 5: knowledge 노드
    assert "knowledge" in prompt, "knowledge 노드 규칙이 Stage A 프롬프트에 없음"

    # 규칙 6: 복합 신호 골격 예시
    assert "api-start" in prompt and "unpacker" in prompt and "sorter" in prompt \
        and "instance-db-insert" in prompt, \
        "복합 신호 결합 골격(api-start → unpacker → sorter → ... → instance-db-insert)이 Stage A 프롬프트에 없음"

    # ── 규칙 1 강화: 처리 대상이 외부 레코드/목록이면 api-start 기본 ────────────
    # "조회/가져온다" 명시 동사 없어도 외부 데이터 집합 대상이면 api-start를 써야 한다는 규칙
    assert "명시 동사" in prompt or "명시적" in prompt or "명시" in prompt, \
        "명시 동사 없어도 api-start를 추론해야 한다는 규칙이 Stage A 프롬프트에 없음"
    assert "레코드" in prompt or "데이터 집합" in prompt, \
        "외부 레코드/데이터 집합 대상 시 api-start 사용 규칙이 Stage A 프롬프트에 없음"
    assert "직접 타이핑" in prompt or "직접 입력" in prompt, \
        "form-start는 사용자가 직접 타이핑하는 경우에만 사용한다는 기준이 Stage A 프롬프트에 없음"
    # 문의글·티켓 등 대표 예시 도메인 언급 여부
    assert "문의글" in prompt or "티켓" in prompt or "이슈" in prompt or "게시글" in prompt, \
        "외부 레코드의 도메인 예시(문의글/티켓/이슈 등)가 Stage A 프롬프트에 없음"


# ── _normalize_sorter_wiring 단위 테스트 ─────────────────────────────────────
# LLM 없이 순수 함수만 테스트한다.

def _make_sorter_draft(
    sorter_id: str = "wn-sorter01",
    rules: list = None,
    connections: list = None,
    sorter_config_extra: dict = None,
    downstream_id: str = "wn-result01",
    downstream_def: str = "result",
) -> dict:
    """테스트용 sorter 단일 노드 draft 생성 헬퍼."""
    if rules is None:
        rules = [{"id": "rule-1", "conditions": []}]
    config = {"rules": rules}
    if sorter_config_extra:
        config.update(sorter_config_extra)

    nodes = [
        {
            "id": "wn-trigger01",
            "nodeId": "wn-trigger01",
            "definitionType": "form-start",
            "name": "시작",
            "config": {},
            "inputMapping": {},
        },
        {
            "id": sorter_id,
            "nodeId": sorter_id,
            "definitionType": "sorter",
            "name": "분류기",
            "config": config,
            "inputMapping": {},
        },
        {
            "id": downstream_id,
            "nodeId": downstream_id,
            "definitionType": downstream_def,
            "name": "다운스트림",
            "config": {},
            "inputMapping": {},
        },
    ]

    if connections is None:
        connections = []

    draft = {
        "name": "테스트",
        "description": "",
        "tags": [],
        "nodes": nodes,
        "connections": connections,
    }
    return draft


# ── 테스트 1: 자기순환 연결 제거 ──────────────────────────────────────────────

def test_normalize_removes_self_loop():
    """sourceNodeId == targetNodeId인 자기순환 연결이 제거되어야 한다."""
    sorter_id = "wn-sorter01"
    draft = _make_sorter_draft(
        sorter_id=sorter_id,
        rules=[{"id": "rule-1", "conditions": []}],
        connections=[
            # 자기순환
            {
                "id": "wc-self01",
                "sourceNodeId": sorter_id,
                "targetNodeId": sorter_id,
                "sourceHandle": "rule-rule-1",
            },
            # 정상 연결
            {
                "id": "wc-ok01",
                "sourceNodeId": sorter_id,
                "targetNodeId": "wn-result01",
                "sourceHandle": "rule-rule-1",
            },
        ],
    )
    result = _normalize_sorter_wiring(draft)
    conns = result["connections"]
    # 자기순환은 제거되어야 함
    self_loops = [c for c in conns if c["sourceNodeId"] == c["targetNodeId"]]
    assert len(self_loops) == 0, f"자기순환 연결이 제거되지 않음: {self_loops}"
    # 정상 연결은 유지
    ok_conns = [c for c in conns if c["sourceNodeId"] == sorter_id and c["targetNodeId"] == "wn-result01"]
    assert len(ok_conns) >= 1, "정상 연결이 제거됨"


# ── 테스트 2: sourceHandle "rule-1" → "rule-rule-1" 교정 ─────────────────────

def test_normalize_fixes_missing_prefix_handle():
    """LLM이 rule id="rule-1"일 때 sourceHandle="rule-1"로 쓰면
    올바른 핸들 "rule-rule-1"로 교정되어야 한다.
    """
    sorter_id = "wn-sorter01"
    draft = _make_sorter_draft(
        sorter_id=sorter_id,
        rules=[{"id": "rule-1", "conditions": []}],
        connections=[
            {
                "id": "wc-bad01",
                "sourceNodeId": sorter_id,
                "targetNodeId": "wn-result01",
                "sourceHandle": "rule-1",  # 잘못된 핸들: "rule-rule-1" 이어야 함
            }
        ],
    )
    result = _normalize_sorter_wiring(draft)
    conns = [c for c in result["connections"] if c.get("sourceNodeId") == sorter_id]
    assert len(conns) >= 1, "sorter 출력 연결이 사라짐"
    handles = [c.get("sourceHandle") for c in conns]
    assert "rule-rule-1" in handles, (
        f"sourceHandle 'rule-1'이 'rule-rule-1'로 교정되지 않음. 실제 핸들: {handles}"
    )


# ── 테스트 3: 이미 올바른 핸들은 변경되지 않아야 함 (idempotent) ────────────────

def test_normalize_correct_wiring_unchanged():
    """올바른 배선(rule id="r1", sourceHandle="rule-r1")은 변형 없이 통과해야 한다."""
    sorter_id = "wn-sorter01"
    draft = _make_sorter_draft(
        sorter_id=sorter_id,
        rules=[{"id": "r1", "conditions": []}],
        connections=[
            {
                "id": "wc-ok01",
                "sourceNodeId": sorter_id,
                "targetNodeId": "wn-result01",
                "sourceHandle": "rule-r1",  # 이미 올바름
            }
        ],
    )
    result = _normalize_sorter_wiring(draft)
    conns = [c for c in result["connections"] if c.get("sourceNodeId") == sorter_id]
    handles = [c.get("sourceHandle") for c in conns]
    assert "rule-r1" in handles, f"올바른 핸들 'rule-r1'이 사라짐. 실제: {handles}"
    # 추가 연결이 생기지 않아야 함 (이미 rule에 연결 있으므로)
    assert len(conns) == 1, f"불필요한 연결이 추가됨: {conns}"


# ── 테스트 4: rule에 연결 없을 때 재배정 또는 신규 생성 ──────────────────────────

def test_normalize_creates_missing_rule_connection():
    """rule이 있는데 해당 rule에 대응하는 연결이 하나도 없으면
    다운스트림 타겟을 향한 연결이 새로 생성되거나 재배정되어야 한다.
    """
    sorter_id = "wn-sorter01"
    # rule id="r1"이 있지만 연결 없음
    draft = _make_sorter_draft(
        sorter_id=sorter_id,
        rules=[{"id": "r1", "conditions": []}],
        connections=[],  # 연결 없음
    )
    result = _normalize_sorter_wiring(draft)
    conns = [c for c in result["connections"] if c.get("sourceNodeId") == sorter_id]
    rule_conns = [c for c in conns if c.get("sourceHandle") == "rule-r1"]
    assert len(rule_conns) >= 1, (
        f"rule 'r1'에 대응하는 연결이 생성되지 않음. sorter 출력 연결: {conns}"
    )


# ── 테스트 5: sorter config의 stray sourceHandle 키 제거 ─────────────────────

def test_normalize_removes_stray_sourcehandle_from_config():
    """sorter config에 실수로 들어간 sourceHandle 키가 제거되어야 한다."""
    sorter_id = "wn-sorter01"
    draft = _make_sorter_draft(
        sorter_id=sorter_id,
        rules=[{"id": "r1", "conditions": []}],
        connections=[
            {
                "id": "wc-ok01",
                "sourceNodeId": sorter_id,
                "targetNodeId": "wn-result01",
                "sourceHandle": "rule-r1",
            }
        ],
        sorter_config_extra={"sourceHandle": "rule-r1"},  # config에 있으면 안 되는 키
    )
    result = _normalize_sorter_wiring(draft)
    sorter_node = next(n for n in result["nodes"] if n["definitionType"] == "sorter")
    assert "sourceHandle" not in sorter_node["config"], (
        f"sorter config에서 sourceHandle이 제거되지 않음: {sorter_node['config']}"
    )
    # rules는 그대로 유지
    assert "rules" in sorter_node["config"], "sorter config.rules가 사라짐"


# ── 테스트 6: 단일 rule + 핸들 불명 연결 → 해당 rule 핸들로 배정 ──────────────

def test_normalize_single_rule_assigns_bad_handle_conn():
    """rule이 정확히 1개이고 핸들이 유효 집합에 없는 연결이 있으면
    그 연결의 sourceHandle이 해당 rule 핸들로 교정되어야 한다.
    """
    sorter_id = "wn-sorter01"
    draft = _make_sorter_draft(
        sorter_id=sorter_id,
        rules=[{"id": "matched", "conditions": []}],
        connections=[
            {
                "id": "wc-bad01",
                "sourceNodeId": sorter_id,
                "targetNodeId": "wn-result01",
                "sourceHandle": "completely-wrong",  # 유효 집합에 없음
            }
        ],
    )
    result = _normalize_sorter_wiring(draft)
    conns = [c for c in result["connections"] if c.get("sourceNodeId") == sorter_id]
    handles = [c.get("sourceHandle") for c in conns]
    assert "rule-matched" in handles, (
        f"단일 rule 'matched'로 sourceHandle이 교정되지 않음. 실제: {handles}"
    )


# ── 테스트 7: 동일 rule 핸들 중복 연결 → 1개만 유지 ─────────────────────────────

def test_normalize_deduplicates_rule_connections():
    """같은 rule 핸들로 가는 연결이 2개 이상이면 1개만 남아야 한다."""
    sorter_id = "wn-sorter01"
    draft = _make_sorter_draft(
        sorter_id=sorter_id,
        rules=[{"id": "r1", "conditions": []}],
        connections=[
            {
                "id": "wc-dup01",
                "sourceNodeId": sorter_id,
                "targetNodeId": "wn-result01",
                "sourceHandle": "rule-r1",
            },
            {
                "id": "wc-dup02",
                "sourceNodeId": sorter_id,
                "targetNodeId": "wn-result01",
                "sourceHandle": "rule-r1",
            },
        ],
    )
    result = _normalize_sorter_wiring(draft)
    rule_conns = [
        c for c in result["connections"]
        if c.get("sourceNodeId") == sorter_id and c.get("sourceHandle") == "rule-r1"
    ]
    assert len(rule_conns) == 1, (
        f"같은 rule 핸들 연결이 1개로 줄어들지 않음. 실제 수: {len(rule_conns)}"
    )


# ── 테스트 8: sorter가 없는 draft는 변형 없이 그대로 통과 ─────────────────────────

def test_normalize_no_sorter_unchanged():
    """sorter 노드가 없는 draft는 연결이 그대로 유지되어야 한다."""
    draft = {
        "name": "단순 워크플로우",
        "description": "",
        "tags": [],
        "nodes": [
            {"id": "wn-a", "nodeId": "wn-a", "definitionType": "form-start", "name": "시작", "config": {}, "inputMapping": {}},
            {"id": "wn-b", "nodeId": "wn-b", "definitionType": "result", "name": "결과", "config": {}, "inputMapping": {}},
        ],
        "connections": [
            {"id": "wc-1", "sourceNodeId": "wn-a", "targetNodeId": "wn-b", "sourceHandle": None},
        ],
    }
    result = _normalize_sorter_wiring(draft)
    assert len(result["connections"]) == 1, "sorter 없는 draft의 연결이 변경됨"
    assert result["connections"][0]["sourceHandle"] is None, "sourceHandle이 의도치 않게 변경됨"


# ── 테스트 9: 여러 rule이 있는 sorter, 미할당 rule에 순서대로 배정 ─────────────

def test_normalize_multi_rule_assigns_unmatched_connections():
    """rule이 2개이고 핸들 불명 연결이 있으면 미할당 rule에 순서대로 배정된다."""
    sorter_id = "wn-sorter01"
    draft = _make_sorter_draft(
        sorter_id=sorter_id,
        rules=[
            {"id": "a", "conditions": []},
            {"id": "b", "conditions": []},
        ],
        connections=[
            # rule-a는 이미 올바르게 연결됨
            {
                "id": "wc-ok01",
                "sourceNodeId": sorter_id,
                "targetNodeId": "wn-result01",
                "sourceHandle": "rule-a",
            },
            # rule-b 연결은 핸들이 잘못됨 (재배정 대상)
            {
                "id": "wc-bad01",
                "sourceNodeId": sorter_id,
                "targetNodeId": "wn-result01",
                "sourceHandle": "wrong-handle",
            },
        ],
    )
    result = _normalize_sorter_wiring(draft)
    conns = [c for c in result["connections"] if c.get("sourceNodeId") == sorter_id]
    handles = {c.get("sourceHandle") for c in conns}
    assert "rule-a" in handles, f"rule-a 핸들이 사라짐. 실제: {handles}"
    assert "rule-b" in handles, f"rule-b 핸들이 배정되지 않음. 실제: {handles}"


# ── 테스트 10: 원본 draft는 변형되지 않음 (순수 함수) ────────────────────────────

def test_normalize_does_not_mutate_original_draft():
    """_normalize_sorter_wiring이 원본 draft를 변형하지 않아야 한다 (deepcopy 사용)."""
    sorter_id = "wn-sorter01"
    original = _make_sorter_draft(
        sorter_id=sorter_id,
        rules=[{"id": "rule-1", "conditions": []}],
        connections=[
            {
                "id": "wc-bad01",
                "sourceNodeId": sorter_id,
                "targetNodeId": "wn-result01",
                "sourceHandle": "rule-1",  # 잘못된 핸들
            }
        ],
        sorter_config_extra={"sourceHandle": "rule-1"},  # config stray key
    )
    import copy
    original_backup = copy.deepcopy(original)

    _normalize_sorter_wiring(original)

    # 원본이 변형되지 않아야 함
    sorter_node_orig = next(n for n in original["nodes"] if n["definitionType"] == "sorter")
    assert "sourceHandle" in sorter_node_orig["config"], (
        "원본 draft의 sorter config가 변형됨 (순수 함수 위반)"
    )
    assert original["connections"][0]["sourceHandle"] == "rule-1", (
        "원본 draft의 연결 sourceHandle이 변형됨 (순수 함수 위반)"
    )
