"""결정론적 워크플로우 수정-제안(advisor).

완성된 워크플로우의 config 품질 문제를 결정론적 규칙으로 점검하여
"이렇게 고치라"는 구체적 제안을 반환한다. LLM 호출 없음.

반환 형식:
    {
        "suggestions": [
            {code, severity, nodeId, nodeName, message, suggestion}, ...
        ],
        "count": N
    }

규칙 목록:
    R1: instance-db-insert 노드가 dedup 키만 저장 (warning)
    R2: api-call POST 노드의 body_template 변수 누락 (warning)
    R3: ai-custom inline prompt가 미존재 필드 참조 (info)
    R4: knowledge searchField 비표준 (info)
    R5: validate_workflow_structure 경고 흡수 → 한국어 수정 지시문으로 변환
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.ext.asyncio import AsyncSession

from ..nodes.catalog import get_entry
from ..services.flow_validator import _attr, _NODE_OUTPUT_HINTS
from ..core.constants import TRIGGER_TYPE_VALUES


# ── 식별자성 키 패턴 (dedup 전용으로 간주되는 키들) ─────────────────────────
_DEDUP_KEY_PATTERNS = re.compile(
    r"^(board_id|id|key|pk|uuid|ticket_id|issue_id|item_id|record_id|dedup_key|"
    r"unique_key|external_id|ref_id|rid|seq|no)$",
    re.IGNORECASE,
)

# 템플릿 변수 추출 정규식
_TEMPLATE_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def _node_id(node: Any) -> Optional[str]:
    return _attr(node, "id")


def _node_name(node: Any) -> Optional[str]:
    return _attr(node, "name")


def _def_type(node: Any) -> str:
    return _attr(node, "definition_type") or _attr(node, "definitionType") or ""


def _node_config(node: Any) -> Dict[str, Any]:
    cfg = _attr(node, "config")
    return cfg if isinstance(cfg, dict) else {}


def _node_config_overrides(node: Any) -> Dict[str, Any]:
    ovr = _attr(node, "config_overrides") or _attr(node, "configOverrides")
    return ovr if isinstance(ovr, dict) else {}


def _conn_src(conn: Any) -> Optional[str]:
    return _attr(conn, "source_node_id") or _attr(conn, "sourceNodeId")


def _conn_tgt(conn: Any) -> Optional[str]:
    return _attr(conn, "target_node_id") or _attr(conn, "targetNodeId")


def _make_suggestion(
    code: str,
    severity: str,
    message: str,
    suggestion: str,
    node_id: Optional[str] = None,
    node_name: Optional[str] = None,
) -> Dict[str, Any]:
    """제안 dict 생성 헬퍼."""
    return {
        "code": code,
        "severity": severity,
        "nodeId": node_id,
        "nodeName": node_name,
        "message": message,
        "suggestion": suggestion,
    }


# ── 업스트림 키 추정 헬퍼 ────────────────────────────────────────────────────

def _estimate_upstream_keys(
    nodes: List[Any],
    connections: List[Any],
) -> Set[str]:
    """워크플로우 전체의 잠재적 상위 키 집합을 추정한다.

    트리거 form-start의 config.fields 이름 + 카탈로그 output hints +
    'response'(ai-custom 출력) + 일반 통과 필드를 수집한다.
    보수적으로 넓게 수집하여 info 오탐을 최소화한다.
    """
    keys: Set[str] = set()

    # 카탈로그 힌트 전부
    for hint_keys in _NODE_OUTPUT_HINTS.values():
        keys.update(hint_keys)

    # 주요 공통 필드 추가
    keys.update({
        "response", "data", "status", "results", "query", "knowledge",
        "records", "count", "total", "record", "found", "recordId",
        "instanceDbId", "items", "_item_index", "_item_total",
        "matchedItems", "matchedCount", "api_route",
    })

    # form-start config.fields 이름 수집
    for node in nodes:
        if _def_type(node) in TRIGGER_TYPE_VALUES:
            cfg = _node_config(node)
            fields = cfg.get("fields") or []
            if isinstance(fields, list):
                for f in fields:
                    if isinstance(f, dict) and f.get("name"):
                        keys.add(f["name"])

    return keys


# ── 규칙 1: instance-db-insert dedup 키만 저장 ────────────────────────────────

def _check_r1_instance_db_dedup_only(
    nodes: List[Any],
    suggestions: List[Dict[str, Any]],
) -> None:
    """R1: instance-db-insert 노드가 식별자 키만 저장하는 경우 경고."""
    for node in nodes:
        if _def_type(node) != "instance-db-insert":
            continue
        try:
            nid = _node_id(node)
            name = _node_name(node)
            cfg = {**_node_config(node), **_node_config_overrides(node)}

            data_template = cfg.get("dataTemplate")
            if not isinstance(data_template, dict):
                # dataTemplate 이 없거나 dict 가 아니면 규칙 미적용
                continue

            keys_in_template = set(data_template.keys())

            # 키가 0~1개이거나, 있는 키가 모두 식별자 패턴이면 경고
            if len(keys_in_template) == 0:
                meaningful = False
            else:
                meaningful_keys = {
                    k for k in keys_in_template
                    if not _DEDUP_KEY_PATTERNS.match(k)
                }
                meaningful = bool(meaningful_keys)

            if not meaningful:
                suggestions.append(_make_suggestion(
                    code="r1-dedup-only",
                    severity="warning",
                    message=(
                        f"'{name or nid}' 노드의 처리 이력(dataTemplate)에 "
                        f"식별자 키({', '.join(sorted(keys_in_template)) or '없음'})만 저장되어 "
                        f"답변 본문이나 원문 정보가 누락됩니다."
                    ),
                    suggestion=(
                        f"'{name or nid}' 노드의 dataTemplate에 "
                        f"답변 본문(response)과 원문 핵심 필드도 함께 저장해줘."
                    ),
                    node_id=nid,
                    node_name=name,
                ))
        except Exception:
            # 실패해도 다른 규칙은 계속
            pass


# ── 규칙 2: api-call POST body_template 변수 누락 ─────────────────────────────

async def _check_r2_api_call_body_vars(
    nodes: List[Any],
    db: AsyncSession,
    suggestions: List[Dict[str, Any]],
) -> None:
    """R2: api-call POST 노드에서 body_template 변수가 defaultParams에 없으면 경고."""
    from sqlalchemy import select as sa_select
    from ..models.api_definition import ApiDefinition

    for node in nodes:
        if _def_type(node) != "api-call":
            continue
        try:
            nid = _node_id(node)
            name = _node_name(node)
            cfg = {**_node_config(node), **_node_config_overrides(node)}

            api_def_id = cfg.get("apiDefinitionId")
            if not api_def_id:
                continue

            # ApiDefinition 조회
            result = await db.execute(
                sa_select(ApiDefinition).where(ApiDefinition.id == api_def_id)
            )
            api_def = result.scalar_one_or_none()
            if api_def is None:
                continue

            # POST 메서드이고 body_template 이 있는 경우만 검사
            if (api_def.method or "GET").upper() != "POST":
                continue
            if not api_def.body_template:
                continue

            # body_template 에서 {{var}} 변수 추출
            template_vars = set(_TEMPLATE_VAR_RE.findall(api_def.body_template))
            if not template_vars:
                continue

            # 노드 defaultParams 의 키 집합
            default_params = cfg.get("defaultParams")
            if isinstance(default_params, dict):
                param_keys = set(default_params.keys())
            else:
                param_keys = set()

            # defaultParams 에 없는 변수 = 누락 후보
            missing_vars = template_vars - param_keys
            for var in sorted(missing_vars):
                suggestions.append(_make_suggestion(
                    code="r2-body-var-missing",
                    severity="warning",
                    message=(
                        f"'{name or nid}' 노드가 참조하는 API의 요청 본문 "
                        f"변수 '{var}'가 defaultParams에 없어 채워지지 않을 수 있습니다."
                    ),
                    suggestion=(
                        f"'{name or nid}' 노드의 defaultParams에 "
                        f"'{var}' 값을 추가하거나 input_mapping으로 연결해줘."
                    ),
                    node_id=nid,
                    node_name=name,
                ))
        except Exception:
            pass


# ── 규칙 3: ai-custom inline prompt 미존재 필드 참조 ─────────────────────────

def _check_r3_inline_prompt_vars(
    nodes: List[Any],
    connections: List[Any],
    suggestions: List[Dict[str, Any]],
) -> None:
    """R3: ai-custom inline prompt가 업스트림 제공 불가 필드를 참조하면 info."""
    upstream_keys = _estimate_upstream_keys(nodes, connections)

    for node in nodes:
        if _def_type(node) != "ai-custom":
            continue
        try:
            nid = _node_id(node)
            name = _node_name(node)
            cfg = {**_node_config(node), **_node_config_overrides(node)}

            # ai_node_id 가 있으면 inline prompt 아님 → 규칙 미적용
            ai_node_id = cfg.get("ai_node_id") or cfg.get("aiNodeId")
            if ai_node_id:
                continue

            prompt = cfg.get("prompt") or ""
            system_prompt = cfg.get("systemPrompt") or ""
            combined_prompt = f"{prompt} {system_prompt}"

            # {{변수}} 추출
            template_vars = set(_TEMPLATE_VAR_RE.findall(combined_prompt))
            if not template_vars:
                continue

            # 업스트림 키에 없는 변수만 신고 (너무 공격적이지 않게 info 수준)
            unknown_vars = template_vars - upstream_keys
            for var in sorted(unknown_vars):
                suggestions.append(_make_suggestion(
                    code="r3-prompt-unknown-var",
                    severity="info",
                    message=(
                        f"'{name or nid}' 노드의 프롬프트가 "
                        f"업스트림에서 제공되지 않을 수 있는 필드 "
                        f"'{{{{{{var}}}}}}'를 참조합니다."
                    ),
                    suggestion=(
                        f"'{name or nid}' 노드의 프롬프트에서 "
                        f"'{var}' 필드가 업스트림에서 올바르게 전달되는지 "
                        f"확인하거나, input_mapping으로 명시적으로 연결해줘."
                    ),
                    node_id=nid,
                    node_name=name,
                ))
        except Exception:
            pass


# ── 규칙 4: knowledge searchField 비표준 ──────────────────────────────────────

def _check_r4_knowledge_search_field(
    nodes: List[Any],
    connections: List[Any],
    suggestions: List[Dict[str, Any]],
) -> None:
    """R4: knowledge 노드의 searchField 값이 업스트림 추정 키에 없으면 info."""
    upstream_keys = _estimate_upstream_keys(nodes, connections)

    for node in nodes:
        if _def_type(node) != "knowledge":
            continue
        try:
            nid = _node_id(node)
            name = _node_name(node)
            cfg = {**_node_config(node), **_node_config_overrides(node)}

            search_field = cfg.get("searchField") or ""
            if not search_field:
                continue  # searchField 미지정은 자동 쿼리 구성이므로 정상

            if search_field not in upstream_keys:
                suggestions.append(_make_suggestion(
                    code="r4-search-field-unknown",
                    severity="info",
                    message=(
                        f"'{name or nid}' 노드의 searchField='{search_field}'가 "
                        f"업스트림 출력 키 목록에서 확인되지 않습니다."
                    ),
                    suggestion=(
                        f"'{name or nid}' 노드의 searchField를 업스트림에서 "
                        f"실제로 제공되는 필드명으로 수정하거나, "
                        f"input_mapping으로 해당 값을 연결해줘."
                    ),
                    node_id=nid,
                    node_name=name,
                ))
        except Exception:
            pass


# ── 규칙 5: validate_workflow_structure 경고 흡수 ────────────────────────────

_VALIDATOR_CODE_TO_SUGGESTION: Dict[str, str] = {
    "dead-end": "연결이 끊긴 리프 노드에 다음 단계 노드를 연결하거나, 출력(result/markdown-viewer) 노드로 마무리해줘.",
    "type-mismatch": "unpacker 노드 앞에 배열을 출력하는 노드(api-call/knowledge 등)를 연결해줘.",
    "mapping-null": "input_mapping 경로를 업스트림 출력 키에 맞게 수정해줘.",
    "subgraph": "분리된 서브그래프를 메인 흐름에 연결하거나 불필요하면 삭제해줘.",
    "dangling-edge": "존재하지 않는 노드를 참조하는 연결선을 삭제하거나 올바른 노드 ID로 수정해줘.",
    "disconnected-node": "고립된 노드를 워크플로우 흐름에 연결하거나 삭제해줘.",
    "no-trigger": "워크플로우에 form-start 또는 api-start 트리거 노드를 추가해줘.",
    "unreachable": "트리거에서 도달할 수 없는 노드를 연결선으로 메인 흐름에 이어줘.",
    "unknown-deftype": "지원하지 않는 노드 타입을 카탈로그에서 지원하는 타입으로 교체해줘.",
    "missing-config": "필수 설정(required=true)이 누락된 노드의 config를 채워줘.",
    "broken-ref": "노드 config에서 참조하는 ID(apiDefinitionId/instanceDbId/ai_node_id)를 실제 등록된 값으로 수정해줘.",
    "sorter-handle": "sorter 노드의 분기 엣지(sourceHandle)를 rule-<id> 또는 default로 올바르게 연결해줘.",
    "cycle": "워크플로우 연결 그래프의 순환을 제거해줘 (단방향 DAG로 수정해줘).",
}


async def _check_r5_absorb_validator(
    nodes: List[Any],
    connections: List[Any],
    db: AsyncSession,
    suggestions: List[Dict[str, Any]],
) -> None:
    """R5: workflow_validator 의 warnings/errors 를 제안으로 흡수."""
    from .workflow_validator import validate_workflow_structure

    try:
        v_result = await validate_workflow_structure(nodes, connections, db)
    except Exception:
        return

    # warnings 처리
    for issue in v_result.get("warnings", []):
        try:
            code = issue.get("code", "unknown")
            base_suggestion = _VALIDATOR_CODE_TO_SUGGESTION.get(
                code,
                "워크플로우 구조 경고를 확인하고 수정해줘.",
            )
            node_name = issue.get("nodeName")
            suggestion_text = (
                f"'{node_name}' 노드: {base_suggestion}"
                if node_name
                else base_suggestion
            )
            suggestions.append(_make_suggestion(
                code=f"r5-{code}",
                severity="warning",
                message=issue.get("message", "구조 경고"),
                suggestion=suggestion_text,
                node_id=issue.get("nodeId"),
                node_name=node_name,
            ))
        except Exception:
            pass

    # errors 처리 (severity=warning 으로 포함, "구조 오류" 표기)
    for issue in v_result.get("errors", []):
        try:
            code = issue.get("code", "unknown")
            base_suggestion = _VALIDATOR_CODE_TO_SUGGESTION.get(
                code,
                "워크플로우 구조 오류를 수정해줘.",
            )
            node_name = issue.get("nodeName")
            suggestion_text = (
                f"'{node_name}' 노드: {base_suggestion}"
                if node_name
                else base_suggestion
            )
            suggestions.append(_make_suggestion(
                code=f"r5-{code}",
                severity="warning",
                message=f"[구조 오류] {issue.get('message', '구조 오류')}",
                suggestion=suggestion_text,
                node_id=issue.get("nodeId"),
                node_name=node_name,
            ))
        except Exception:
            pass


# ── 메인 진입점 ───────────────────────────────────────────────────────────────

async def advise_workflow(
    nodes: List[Any],
    connections: List[Any],
    db: AsyncSession,
) -> Dict[str, Any]:
    """워크플로우 config 품질을 결정론적 규칙으로 점검하여 수정 제안 목록을 반환한다.

    Parameters
    ----------
    nodes:
        WorkflowNodeCreate / WorkflowNode ORM / camelCase dict 혼용 허용.
    connections:
        WorkflowConnectionCreate / WorkflowConnection ORM / camelCase dict 혼용 허용.
    db:
        AsyncSession — ApiDefinition 등 DB 조회용.

    Returns
    -------
    dict:
        {
            "suggestions": [{code, severity, nodeId, nodeName, message, suggestion}, ...],
            "count": int,
        }
    """
    suggestions: List[Dict[str, Any]] = []

    # R1: instance-db-insert dedup 키만 저장
    try:
        _check_r1_instance_db_dedup_only(nodes, suggestions)
    except Exception:
        pass

    # R2: api-call POST body_template 변수 누락
    try:
        await _check_r2_api_call_body_vars(nodes, db, suggestions)
    except Exception:
        pass

    # R3: ai-custom inline prompt 미존재 필드 참조
    try:
        _check_r3_inline_prompt_vars(nodes, connections, suggestions)
    except Exception:
        pass

    # R4: knowledge searchField 비표준
    try:
        _check_r4_knowledge_search_field(nodes, connections, suggestions)
    except Exception:
        pass

    # R5: workflow_validator 경고 흡수
    try:
        await _check_r5_absorb_validator(nodes, connections, db, suggestions)
    except Exception:
        pass

    return {"suggestions": suggestions, "count": len(suggestions)}


__all__ = ["advise_workflow"]
