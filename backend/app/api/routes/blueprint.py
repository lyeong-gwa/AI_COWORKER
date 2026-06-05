"""Workflow Blueprint (설계도) Export Routes — Phase 5.

설계도(blueprint)는 워크플로우의 **설계 정보(규격·체계·노드정보)만** 담는다.
환경 의존 **재료 값**(auth 시크릿, 구체적 ``defaultParams`` 값, 식별 코드, 초기 입력값)은
**제외(redact)** 한다. 수신 측이 나중에 자기 환경 값으로 채운다(보정 단계 — 별도 Phase).

핵심:
- 디스크 스냅샷은 전체 값(소스 런타임용)을 유지한다. **EXPORT 결과만** 환경 값을 비운다.
- self-heal: export 시 누락 스냅샷을 임베딩하되 **저장된 워크플로우는 건드리지 않는다**(read-only).
- ``redactedFields`` 매니페스트로 무엇이 비워졌는지 알려, import 의 보정 단계가 질문할 수 있게 한다.

blueprint JSON shape::

    { "blueprintVersion":"1.0", "kind":"workflow-blueprint", "exportedAt":"...",
      "sourceWorkflowId":"wf-...",
      "workflow": { name, description, tags, trigger, variables,
                    nodes:[ {nodeId, definitionType, name, orderIndex,
                             config, configOverrides, inputMapping} ],
                    connections:[ {id, sourceNodeId, targetNodeId,
                                   sourceHandle, targetHandle, condition} ] },
      "dependencies": { instanceDbs:[ {snapshotSourceId, name, description, tags, viewerHints} ],
                        knowledge:[ {nodeRef, categories, tags, pageTypes, services,
                                     searchField, minScore, expandBacklinks} ] },
      "redactedFields": [ {nodeRef, path, kind} ] }
"""

from __future__ import annotations

import copy
import json
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...core.database import get_db
from ...core.exceptions import NotFoundError, ValidationError
from ...models.workflow import (
    Workflow,
    WorkflowConnection,
    WorkflowNode,
    WorkflowStatus,
)
from ...services.blueprint_snapshot import (
    AI_NODE_SNAPSHOT_KEY,
    API_SPEC_SNAPSHOT_KEY,
    API_SPEC_SNAPSHOTS_KEY,
    INSTANCE_DB_META_KEY,
    SNAPSHOT_AT_KEY,
    SNAPSHOT_SOURCE_ID_KEY,
    embed_snapshots_into_nodes,
)

router = APIRouter()

BLUEPRINT_VERSION = "1.0"
BLUEPRINT_KIND = "workflow-blueprint"

# responseSchema.example 가 이보다 크면(JSON 직렬화 길이) 트리밍한다.
_EXAMPLE_TRIM_THRESHOLD = 2000


# ── 환경 값 레닥션 (순수 헬퍼) ───────────────────────────────────────────────

# 민감 헤더 키 판별 — 정확 일치(소문자) 또는 부분문자열 포함.
_SENSITIVE_HEADER_EXACT: frozenset = frozenset(
    {"authorization", "proxy-authorization", "cookie", "set-cookie"}
)
_SENSITIVE_HEADER_SUBSTR: tuple = (
    "api-key", "apikey", "x-api-key", "token", "secret",
    "password", "access-key", "private-key",
)

# 순수 플레이스홀더 패턴 — 값 전체가 {{...}} 또는 {단일키} 으로만 구성된 경우.
_PLACEHOLDER_ONLY_RE = re.compile(
    r"^\s*(\{\{[^}]+\}\}|\{[^}]+\})\s*$"
)

# 하드코딩된 시크릿 휴리스틱 패턴들.
_SECRET_HEURISTICS: tuple = (
    # Bearer <token> — 리터럴 토큰 (플레이스홀더 아님)
    re.compile(r"Bearer\s+(?!\{\{)(?!\{)[A-Za-z0-9+/._\-]{8,}", re.IGNORECASE),
    # key=value 또는 key:"value" 형태의 시크릿 파라미터
    re.compile(
        r"(?:token|secret|password|api[_-]?key|access[_-]?key)"
        r"\s*[=:]\s*[\"']?(?!\{\{)(?!\{)([A-Za-z0-9+/._\-]{8,})",
        re.IGNORECASE,
    ),
    # 잘 알려진 토큰 접두사 (sk-, ghp_, xoxb-, xoxe-, xoxp-, xoxa-, xoxo-)
    re.compile(r"\b(sk-[A-Za-z0-9]{16,}|gh[pors]_[A-Za-z0-9]{16,}|xox[bepao]-[A-Za-z0-9\-]{8,})\b"),
    # 20자 이상 연속 base64/hex 덩어리 (공백·구분자 없음) — 쿼리스트링 값 등
    re.compile(r"(?<![A-Za-z0-9])([A-Za-z0-9+/]{20,}={0,2})(?![A-Za-z0-9+/=])"),
)


def _is_placeholder_only(value: str) -> bool:
    """값이 순수 플레이스홀더(``{{var}}`` / ``{var}``)로만 구성되면 True.

    이 경우 런타임 파라미터/환경변수 참조이므로 레닥션 대상이 아니다.
    """
    if not isinstance(value, str):
        return False
    return bool(_PLACEHOLDER_ONLY_RE.match(value))


def _is_sensitive_header_key(key: str) -> bool:
    """헤더 키가 민감 시크릿 패턴에 해당하는지 판별 (대소문자 무관)."""
    lower = key.lower()
    if lower in _SENSITIVE_HEADER_EXACT:
        return True
    return any(sub in lower for sub in _SENSITIVE_HEADER_SUBSTR)


def _scan_for_literal_secrets(text: str) -> bool:
    """문자열에 하드코딩 시크릿으로 의심되는 리터럴이 포함되는지 검사.

    ``{{...}}`` / ``{...}`` 플레이스홀더만으로 구성된 매치는 무시한다.
    """
    if not isinstance(text, str):
        return False
    for pattern in _SECRET_HEURISTICS:
        for m in pattern.finditer(text):
            matched = m.group(0)
            # 매치가 플레이스홀더뿐이면 무시
            if _is_placeholder_only(matched):
                continue
            # 내부에 플레이스홀더가 포함된 경우에도, 리터럴 문자가 함께 있으면 경고
            return True
    return False


def redact_blueprint_env_values(
    node_config: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """노드 config 에서 환경 의존 **값**을 비우고(구조 유지), 비운 항목 매니페스트를 반환.

    저장 데이터를 절대 변형하지 않도록 **deep-copy 한 사본**에 작업한다.

    레닥션 정책 (구조는 유지, 값만 ""):
    - ``apiSpecSnapshot.authConfig`` 의 시크릿 값 → "" (키 + authType 은 유지). kind=authSecret
    - ``apiSpecSnapshot.headers`` 의 민감 키 값 → "" (키 유지, 순수 플레이스홀더 제외). kind=headerSecret
    - 노드 ``defaultParams`` 의 각 VALUE → "" (키는 placeholder 로 유지). kind=envParam
    - ``apiSpecSnapshots[].authConfig`` / ``apiSpecSnapshots[].headers`` (router) 동일 처리.
    - ``apiSpecSnapshot.responseSchema.example`` 이 매우 크면 제거(fields 는 유지). kind=trimmedExample
    - ``apiSpecSnapshot.bodyTemplate`` / ``apiSpecSnapshot.urlTemplate`` 에 리터럴 시크릿 의심
      패턴이 있으면 경고(값 유지, 구조 손상 없음). kind=possibleSecretLiteral
    - 레닥션 안 함: prompts, schemas, 파라미터 정의, 비민감 헤더 키, 와이어링,
      knowledge 요구 구조, 순수 플레이스홀더 헤더 값.

    Returns
    -------
    ``(redacted_config, redactions)`` — ``redactions`` 는 ``{path, kind}`` dict 목록
    (nodeRef 는 호출자가 노드 단위로 채운다).
    ``headerSecret`` 항목은 수신측이 재입력해야 하는 재료로 취급된다(materialsToFill 포함).
    ``possibleSecretLiteral`` 항목은 정보성 경고이며 재입력 대상이 아니다(materialsToFill 제외).
    """
    cfg = copy.deepcopy(node_config or {})
    redactions: List[Dict[str, str]] = []

    def _blank_auth_config(auth_config: Any, base_path: str) -> None:
        """authConfig dict 의 모든 값을 빈 문자열로 (키/authType 유지)."""
        if not isinstance(auth_config, dict):
            return
        for k in list(auth_config.keys()):
            if auth_config[k] not in (None, ""):
                auth_config[k] = ""
                redactions.append(
                    {"path": f"{base_path}.{k}", "kind": "authSecret"}
                )
            else:
                # 이미 빈 값이라도 키 존재는 보존 (placeholder).
                auth_config[k] = ""

    def _blank_sensitive_headers(headers: Any, base_path: str) -> None:
        """민감 헤더 키의 값을 빈 문자열로 (키 유지).

        순수 플레이스홀더(``{{var}}`` / ``{var}``) 값은 건드리지 않는다 — 런타임
        파라미터 참조이므로 시크릿이 아니다.
        """
        if not isinstance(headers, dict):
            return
        for key in list(headers.keys()):
            if not _is_sensitive_header_key(key):
                continue
            val = headers[key]
            if not isinstance(val, str):
                continue
            if _is_placeholder_only(val):
                # 순수 플레이스홀더 — 구조 참조, 레닥션 불필요.
                continue
            if val == "":
                # 이미 비어있음 — 기록만.
                continue
            headers[key] = ""
            redactions.append(
                {"path": f"{base_path}.{key}", "kind": "headerSecret"}
            )

    def _warn_template_secrets(api_spec: Any, base_path: str) -> None:
        """bodyTemplate / urlTemplate 에 하드코딩 시크릿 의심 패턴이 있으면 경고 기록.

        값 자체는 변경하지 않는다(구조·설계 정보이므로 유지).
        """
        if not isinstance(api_spec, dict):
            return
        for field in ("bodyTemplate", "urlTemplate"):
            val = api_spec.get(field)
            if not isinstance(val, str) or not val:
                continue
            if _scan_for_literal_secrets(val):
                redactions.append(
                    {
                        "path": f"{base_path}.{field}",
                        "kind": "possibleSecretLiteral",
                        "warning": (
                            "이 노드의 body/url에 비밀값이 하드코딩된 것 같습니다 "
                            "— API 명세를 authConfig 사용으로 고치세요."
                        ),
                    }
                )

    def _trim_example(api_spec: Any, base_path: str) -> None:
        if not isinstance(api_spec, dict):
            return
        resp = api_spec.get("responseSchema")
        if not isinstance(resp, dict):
            return
        example = resp.get("example")
        if example is None:
            return
        try:
            import json as _json

            size = len(_json.dumps(example, ensure_ascii=False))
        except (TypeError, ValueError):
            size = _EXAMPLE_TRIM_THRESHOLD + 1  # 직렬화 불가 → 트리밍 대상
        if size > _EXAMPLE_TRIM_THRESHOLD:
            resp.pop("example", None)
            redactions.append(
                {"path": f"{base_path}.responseSchema.example", "kind": "trimmedExample"}
            )

    def _process_api_spec(api_spec: Any, base_path: str) -> None:
        """단일 apiSpec 처리 — authConfig 레닥션 + 민감 헤더 레닥션 + 시크릿 경고 + 예시 트리밍."""
        if not isinstance(api_spec, dict):
            return
        _blank_auth_config(api_spec.get("authConfig"), f"{base_path}.authConfig")
        _blank_sensitive_headers(api_spec.get("headers"), f"{base_path}.headers")
        _warn_template_secrets(api_spec, base_path)
        _trim_example(api_spec, base_path)

    # 1) apiSpecSnapshot (api-call / api-start)
    api_spec = cfg.get(API_SPEC_SNAPSHOT_KEY)
    if isinstance(api_spec, dict):
        _process_api_spec(api_spec, API_SPEC_SNAPSHOT_KEY)

    # 2) apiSpecSnapshots[] (ai-api-router)
    api_specs = cfg.get(API_SPEC_SNAPSHOTS_KEY)
    if isinstance(api_specs, list):
        for idx, spec in enumerate(api_specs):
            if isinstance(spec, dict):
                _process_api_spec(spec, f"{API_SPEC_SNAPSHOTS_KEY}[{idx}]")

    # 3) defaultParams — 각 값 blank (키는 placeholder 로 유지)
    default_params = cfg.get("defaultParams")
    if isinstance(default_params, dict):
        for k in list(default_params.keys()):
            default_params[k] = ""
            redactions.append({"path": f"defaultParams.{k}", "kind": "envParam"})

    return cfg, redactions


# ── 의존성 추출 헬퍼 ─────────────────────────────────────────────────────────


def _instance_db_dependency(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """instance-db 노드 config → instanceDbs 의존성 항목(메타 전용). 없으면 None."""
    meta = config.get(INSTANCE_DB_META_KEY)
    if not isinstance(meta, dict):
        return None
    return {
        "snapshotSourceId": config.get(SNAPSHOT_SOURCE_ID_KEY)
        or config.get("instanceDbId"),
        "name": meta.get("name"),
        "description": meta.get("description"),
        "tags": meta.get("tags") or [],
        "viewerHints": meta.get("viewerHints") or {},
    }


def _knowledge_dependency(node_ref: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """knowledge 노드 config → 선언적 지식 요구 구조 (임베딩 아님).

    실제 키 이름은 ``app/nodes/action/knowledge.py`` 의 핸들러 기준:
    ``categories`` / ``tags`` / ``pageTypes`` / ``services`` / ``searchField`` /
    ``minScore`` / ``expandBacklinks``.
    """
    # categories — multi-category 우선, 단일 category 하위호환 흡수
    categories = config.get("categories") or []
    if not categories:
        old_cat = config.get("category")
        if old_cat:
            categories = [old_cat]

    return {
        "nodeRef": node_ref,
        "categories": categories,
        "tags": config.get("tags") or [],
        "pageTypes": config.get("pageTypes") or [],
        "services": config.get("services") or [],
        "searchField": config.get("searchField", ""),
        "minScore": config.get("minScore", 0.0),
        "expandBacklinks": bool(config.get("expandBacklinks", False)),
    }


# ── 노드 detached 사본 (self-heal 시 저장 데이터 비변형) ──────────────────────


class _DetachedNode:
    """``embed_snapshots_into_nodes`` 가 보는 최소 노드 인터페이스.

    저장된 ORM 노드를 더럽히지 않기 위해 config 를 deep-copy 한 사본을 들고 있는다.
    embed 함수는 ``definitionType``/``definition_type``, ``aiNodeId``/``ai_node_id``,
    ``config`` 속성과 ``_set_config`` (setattr) 를 사용한다.
    """

    def __init__(self, orm_node: Any) -> None:
        self.node_id = orm_node.node_id
        self.id = orm_node.id
        self.definitionType = orm_node.definition_type
        self.definition_type = orm_node.definition_type
        self.aiNodeId = orm_node.ai_node_id
        self.ai_node_id = orm_node.ai_node_id
        self.name = orm_node.name
        self.order_index = orm_node.order_index
        self.config_overrides = copy.deepcopy(orm_node.config_overrides or {})
        self.input_mapping = copy.deepcopy(orm_node.input_mapping or {})
        self.config = copy.deepcopy(orm_node.config or {})


# ── Export 엔드포인트 ────────────────────────────────────────────────────────


@router.get("/workflows/{workflow_id}")
async def export_blueprint(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
):
    """단일 워크플로우를 설계도(blueprint) JSON 으로 내보낸다 (환경 값 레닥션 포함)."""
    result = await db.execute(
        select(Workflow)
        .where(Workflow.id == workflow_id)
        .options(
            selectinload(Workflow.nodes),
            selectinload(Workflow.connections),
        )
    )
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다")

    # 1) self-heal — detached 사본에 누락 스냅샷 임베딩 (저장 데이터 비변형, persist 안 함)
    detached = [_DetachedNode(n) for n in wf.nodes]
    await embed_snapshots_into_nodes(db, detached)

    # 2) 노드 목록 + 레닥션
    blueprint_nodes: List[Dict[str, Any]] = []
    redacted_fields: List[Dict[str, str]] = []
    instance_dbs: List[Dict[str, Any]] = []
    knowledge_deps: List[Dict[str, Any]] = []
    seen_idb_keys: set = set()

    # 안정 정렬 — orderIndex 우선
    for dn in sorted(detached, key=lambda n: (n.order_index, n.node_id)):
        redacted_cfg, redactions = redact_blueprint_env_values(dn.config)
        for r in redactions:
            redacted_fields.append(
                {"nodeRef": dn.node_id, "path": r["path"], "kind": r["kind"]}
            )

        blueprint_nodes.append(
            {
                "nodeId": dn.node_id,
                "definitionType": dn.definition_type,
                "name": dn.name,
                "orderIndex": dn.order_index,
                "config": redacted_cfg,
                "configOverrides": dn.config_overrides,
                "inputMapping": dn.input_mapping,
            }
        )

        # instanceDbs 의존성 (distinct by snapshotSourceId)
        if dn.definition_type in ("instance-db-insert", "instance-db-lookup"):
            dep = _instance_db_dependency(dn.config)
            if dep is not None:
                key = dep.get("snapshotSourceId") or dep.get("name")
                if key not in seen_idb_keys:
                    seen_idb_keys.add(key)
                    instance_dbs.append(dep)

        # knowledge 의존성 (선언적; 임베딩 아님)
        if dn.definition_type == "knowledge":
            knowledge_deps.append(_knowledge_dependency(dn.node_id, dn.config))

    # 3) connections
    connections: List[Dict[str, Any]] = []
    for c in wf.connections:
        connections.append(
            {
                "id": c.id,
                "sourceNodeId": c.source_node_id,
                "targetNodeId": c.target_node_id,
                "sourceHandle": c.source_handle,
                "targetHandle": c.target_handle,
                "condition": c.condition,
            }
        )

    # 4) blueprint 조립 (generationTraceIds 는 OMIT)
    return {
        "blueprintVersion": BLUEPRINT_VERSION,
        "kind": BLUEPRINT_KIND,
        "exportedAt": datetime.utcnow().isoformat(),
        "sourceWorkflowId": wf.id,
        "workflow": {
            "name": wf.name,
            "description": wf.description,
            "tags": wf.tags or [],
            "trigger": wf.trigger or {},
            "variables": wf.variables or {},
            "nodes": blueprint_nodes,
            "connections": connections,
        },
        "dependencies": {
            "instanceDbs": instance_dbs,
            "knowledge": knowledge_deps,
        },
        "redactedFields": redacted_fields,
    }


# ════════════════════════════════════════════════════════════════════════════
# PHASE 6 — 결정론적 import (LLM 미사용, 레지스트리 쓰기 없음)
# ════════════════════════════════════════════════════════════════════════════

# 스냅샷 키 모음 — 보정(fill)/리맵 시 재동결 방지 가드용.
_SNAPSHOT_KEYS = (
    API_SPEC_SNAPSHOT_KEY,
    API_SPEC_SNAPSHOTS_KEY,
    AI_NODE_SNAPSHOT_KEY,
    INSTANCE_DB_META_KEY,
)


# ── 호환성 헬퍼 ───────────────────────────────────────────────────────────────


def _check_blueprint_compatible(blueprint: Dict[str, Any]) -> None:
    """``kind`` / ``blueprintVersion`` 메이저 버전 호환성 검증. 실패 시 422.

    에러 포맷: ``{error:{code:"BLUEPRINT_INCOMPATIBLE", message, details}}``.
    """
    kind = blueprint.get("kind")
    version = str(blueprint.get("blueprintVersion") or "")
    major = version.split(".")[0] if version else ""

    if kind != BLUEPRINT_KIND or major != "1":
        raise ValidationError(
            (
                "호환되지 않는 설계도입니다. "
                f"kind='{BLUEPRINT_KIND}', blueprintVersion 메이저 '1' 이어야 합니다."
            ),
            code="BLUEPRINT_INCOMPATIBLE",
            status_code=422,
            details={
                "kind": kind,
                "blueprintVersion": blueprint.get("blueprintVersion"),
                "expectedKind": BLUEPRINT_KIND,
                "expectedMajorVersion": "1",
            },
        )


# ── 재-ID (chat 생성 의미 재사용: nodeId → id 어댑터) ─────────────────────────


def _reid_blueprint(
    bp_nodes: List[Dict[str, Any]],
    bp_connections: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, str]]:
    """설계도 노드/연결을 새 ``wn-``/``wc-`` id 로 재부여한다.

    설계도 노드는 ``nodeId`` 키를 쓴다. chat 생성 경로의 ``_ensure_ids`` 는
    ``id`` 키를 기준으로 동작하므로, 어댑터로 ``id`` 를 채워 넣은 뒤 호출하고
    결과를 다시 설계도 형태로 정규화한다.

    반환: ``(reided_nodes, reided_connections, old_to_new_map)``.
    - reided_nodes: 설계도 노드 형태(``nodeId`` 유지, 새 id) deep-copy 사본.
    - old_to_new_map: 옛 nodeId → 새 nodeId.
    """
    from ...services.workflow_generator import _ensure_ids

    # deep-copy 사본에 작업 (입력 blueprint 비변형).
    nodes = copy.deepcopy(bp_nodes or [])
    connections = copy.deepcopy(bp_connections or [])

    # 어댑터: 설계도 nodeId → _ensure_ids 가 보는 id 키.
    for n in nodes:
        n["id"] = n.get("nodeId") or n.get("id")

    # _ensure_ids 가:
    #  - 각 노드에 새 wn- id 부여 + id_map 구성
    #  - connections 의 source/target 리매핑 + 새 wc- id
    #  - config 내부 노드-id 문자열 참조 재귀 치환 (sorter rules, mapper.warehouseNodeId 등)
    _ensure_ids(nodes, connections)

    # old→new 맵 재구성: _ensure_ids 가 n["id"]=n["nodeId"]=새 id 로 맞춰 두므로
    # 원본 blueprint 의 nodeId 와 짝지어 맵을 만든다.
    old_to_new: Dict[str, str] = {}
    for orig, new_n in zip(bp_nodes or [], nodes):
        old_ref = orig.get("nodeId") or orig.get("id")
        new_ref = new_n.get("nodeId") or new_n.get("id")
        if old_ref and new_ref:
            old_to_new[old_ref] = new_ref

    return nodes, connections, old_to_new


# ── instanceDb name-match-or-create (LOCKED 정책) ─────────────────────────────


async def _resolve_instance_dbs(
    instance_db_deps: List[Dict[str, Any]],
    *,
    create: bool,
) -> Tuple[Dict[str, str], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """설계도 instanceDb 의존성을 로컬 store 와 name-match-or-create 한다.

    LOCKED 정책:
      - 같은 ``name`` 의 기존 메타가 있으면 그 id 재사용.
      - 없으면 (``create=True`` 일 때만) 설계도 메타로 새로 생성.
      - 매칭된 기존 DB 의 viewerHints/tags 가 설계도와 다르면 reconciliation 경고
        (kind="instanceDbMetaMismatch") 를 추가하되 기존 DB 를 덮어쓰지 않는다.

    Parameters
    ----------
    create:
        True 면 실제 생성, False 면 dryRun 계획만 수립(생성 안 함).

    Returns
    -------
    ``(source_to_local, warnings, plan)``
    - source_to_local: snapshotSourceId → 로컬 instanceDbId 맵.
    - warnings: reconciliation 경고 목록.
    - plan: dryRun 계획 항목 목록 ``[{snapshotSourceId, name, action, localId?}]``.
    """
    from ...services.instance_db_store import get_instance_db_store

    store = get_instance_db_store()
    existing = await store.list_meta()
    by_name: Dict[str, Dict[str, Any]] = {m.get("name"): m for m in existing}

    source_to_local: Dict[str, str] = {}
    warnings: List[Dict[str, Any]] = []
    plan: List[Dict[str, Any]] = []

    # 같은 설계도 내 동일 name 을 중복 생성하지 않도록 세션 캐시.
    created_this_run: Dict[str, str] = {}

    for dep in instance_db_deps or []:
        src_id = dep.get("snapshotSourceId")
        name = dep.get("name")
        if not name:
            continue

        matched = by_name.get(name)
        if matched is not None:
            local_id = matched.get("id")
            if src_id:
                source_to_local[src_id] = local_id
            # 메타 불일치 경고 (덮어쓰지 않음).
            bp_hints = dep.get("viewerHints") or {}
            bp_tags = sorted(dep.get("tags") or [])
            ex_hints = matched.get("viewerHints") or {}
            ex_tags = sorted(matched.get("tags") or [])
            if bp_hints != ex_hints or bp_tags != ex_tags:
                warnings.append(
                    {
                        "kind": "instanceDbMetaMismatch",
                        "message": (
                            f"기존 인스턴스DB '{name}' 의 viewerHints/tags 가 "
                            f"설계도와 다릅니다. 기존 DB 를 보존하고 덮어쓰지 않습니다."
                        ),
                        "instanceDbId": local_id,
                        "blueprint": {"viewerHints": bp_hints, "tags": dep.get("tags") or []},
                        "existing": {"viewerHints": ex_hints, "tags": matched.get("tags") or []},
                    }
                )
            plan.append(
                {
                    "snapshotSourceId": src_id,
                    "name": name,
                    "action": "reuse",
                    "localId": local_id,
                }
            )
            continue

        # 미존재 → 생성(또는 dryRun 계획).
        if name in created_this_run:
            if src_id:
                source_to_local[src_id] = created_this_run[name]
            plan.append(
                {
                    "snapshotSourceId": src_id,
                    "name": name,
                    "action": "reuse-created",
                    "localId": created_this_run[name],
                }
            )
            continue

        if create:
            meta = await store.create_meta(
                name=name,
                description=dep.get("description"),
                tags=dep.get("tags") or [],
                viewer_hints=dep.get("viewerHints") or {},
            )
            local_id = meta["id"]
            created_this_run[name] = local_id
            if src_id:
                source_to_local[src_id] = local_id
            plan.append(
                {
                    "snapshotSourceId": src_id,
                    "name": name,
                    "action": "create",
                    "localId": local_id,
                }
            )
        else:
            plan.append(
                {
                    "snapshotSourceId": src_id,
                    "name": name,
                    "action": "create",
                    "localId": None,
                }
            )

    return source_to_local, warnings, plan


def _rewrite_instance_db_ids(
    nodes: List[Dict[str, Any]],
    source_to_local: Dict[str, str],
) -> None:
    """노드 config 의 instanceDbId(노드/소터 rule) 와 instanceDbMeta.snapshotSourceId 를
    source→local 맵으로 in-place 재작성한다.

    dryRun 에서 local 이 아직 없는 경우(맵에 없음)는 건드리지 않는다.
    """
    if not source_to_local:
        return

    for n in nodes:
        cfg = n.get("config")
        if not isinstance(cfg, dict):
            continue

        # 1) 노드 최상위 instanceDbId
        idb = cfg.get("instanceDbId")
        if idb in source_to_local:
            cfg["instanceDbId"] = source_to_local[idb]

        # 2) sorter rules[].instanceDbId
        rules = cfg.get("rules")
        if isinstance(rules, list):
            for rule in rules:
                if isinstance(rule, dict):
                    rid = rule.get("instanceDbId")
                    if rid in source_to_local:
                        rule["instanceDbId"] = source_to_local[rid]

        # 3) instanceDbMeta.snapshotSourceId + 공통 snapshotSourceId
        meta = cfg.get(INSTANCE_DB_META_KEY)
        if isinstance(meta, dict):
            src = meta.get(SNAPSHOT_SOURCE_ID_KEY)
            if src in source_to_local:
                meta[SNAPSHOT_SOURCE_ID_KEY] = source_to_local[src]
        # instance-db 노드의 공통 snapshotSourceId 도 동기화 (= 옛 instanceDbId).
        common_src = cfg.get(SNAPSHOT_SOURCE_ID_KEY)
        if (
            n.get("definitionType") in ("instance-db-insert", "instance-db-lookup")
            and common_src in source_to_local
        ):
            cfg[SNAPSHOT_SOURCE_ID_KEY] = source_to_local[common_src]


# ── reconciliation (보정) 리포트 빌더 — Phase 8 공용 ─────────────────────────


def _available_knowledge_facets() -> Tuple[set, set]:
    """현재 가용한 지식 카테고리/서비스 집합. (list_md_files 기반)"""
    cats: set = set()
    svcs: set = set()
    try:
        from ...services.knowledge_file_service import list_md_files

        for d in list_md_files():
            if getattr(d, "category", None):
                cats.add(d.category)
            if getattr(d, "service", None) and d.service != "unknown":
                svcs.add(d.service)
    except Exception:  # pragma: no cover - 가용성 보조
        pass
    return cats, svcs


def _knowledge_status_for(
    requirement: Dict[str, Any],
    available_cats: set,
    available_svcs: set,
) -> Dict[str, Any]:
    """단일 knowledge 요구사항을 가용 카테고리/서비스와 대조해 상태 산출."""
    req_cats = [c for c in (requirement.get("categories") or []) if c]
    req_svcs = [s for s in (requirement.get("services") or []) if s]

    needed = list(req_cats) + [f"service:{s}" for s in req_svcs]
    missing_cats = [c for c in req_cats if c not in available_cats]
    missing_svcs = [s for s in req_svcs if s not in available_svcs]
    missing = list(missing_cats) + [f"service:{s}" for s in missing_svcs]

    if not needed:
        status = "satisfied"
    elif not missing:
        status = "satisfied"
    elif len(missing) == len(needed):
        status = "missing"
    else:
        status = "partial"

    suggested: List[Dict[str, Any]] = []
    for c in missing_cats:
        suggested.append({"type": "create_category", "category": c})
        suggested.append(
            {"type": "remap", "from": c, "candidates": sorted(available_cats)}
        )
    for s in missing_svcs:
        suggested.append({"type": "create_category", "service": s})
    if status == "satisfied":
        suggested.append({"type": "link_existing"})
    if missing:
        suggested.append({"type": "warn", "missing": missing})

    return {
        "status": status,
        "missingCategories": missing_cats,
        "missingServices": missing_svcs,
        "availableCategories": sorted(available_cats),
        "availableServices": sorted(available_svcs),
        "suggestedActions": suggested,
    }


def _knowledge_requirement_from_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """knowledge 노드 config → 요구 구조 (export 의 _knowledge_dependency 와 동형)."""
    categories = cfg.get("categories") or []
    if not categories and cfg.get("category"):
        categories = [cfg.get("category")]
    return {
        "categories": categories,
        "tags": cfg.get("tags") or [],
        "pageTypes": cfg.get("pageTypes") or [],
        "services": cfg.get("services") or [],
        "searchField": cfg.get("searchField", ""),
        "minScore": cfg.get("minScore", 0.0),
        "expandBacklinks": bool(cfg.get("expandBacklinks", False)),
    }


def _build_reconciliation(
    nodes: List[Dict[str, Any]],
    redacted_fields: List[Dict[str, Any]],
    old_to_new: Dict[str, str],
    extra_warnings: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """보정(reconciliation) 리포트 빌드 — knowledge + 재료(env 값) 모두 커버.

    Parameters
    ----------
    nodes:
        새 id 가 부여된(또는 저장된) 노드 목록. 각 노드는 ``nodeId`` + ``config`` 보유.
    redacted_fields:
        설계도의 redactedFields (옛 nodeRef 기준). new id 로 remap 한다.
    old_to_new:
        옛 nodeRef → 새 nodeRef. 빈 맵이면 항등(이미 새 id).
    extra_warnings:
        instanceDb 등 사전 단계에서 모은 경고.
    """
    available_cats, available_svcs = _available_knowledge_facets()

    knowledge_report: List[Dict[str, Any]] = []
    sat = par = mis = 0
    for n in nodes:
        if n.get("definitionType") != "knowledge":
            continue
        cfg = n.get("config") or {}
        requirement = _knowledge_requirement_from_config(cfg)
        status_info = _knowledge_status_for(requirement, available_cats, available_svcs)
        status = status_info["status"]
        if status == "satisfied":
            sat += 1
        elif status == "partial":
            par += 1
        else:
            mis += 1
        knowledge_report.append(
            {
                "nodeRef": n.get("nodeId"),
                "requirement": requirement,
                "status": status,
                "missingCategories": status_info["missingCategories"],
                "missingServices": status_info["missingServices"],
                "availableCategories": status_info["availableCategories"],
                "availableServices": status_info["availableServices"],
                "suggestedActions": status_info["suggestedActions"],
            }
        )

    # materialsToFill — redactedFields 에서 정보성 항목(trimmedExample, possibleSecretLiteral)
    # 제외, nodeRef remap.
    # - trimmedExample: 정보성, 입력 불필요.
    # - possibleSecretLiteral: 경고성, 값을 통째로 대체하지 않음(구조 보존) — 입력 불필요.
    # - headerSecret: 수신측이 민감 헤더 값을 재입력해야 하므로 포함.
    _FILL_EXCLUDED_KINDS = frozenset({"trimmedExample", "possibleSecretLiteral"})
    materials: List[Dict[str, Any]] = []
    for rf in redacted_fields or []:
        kind = rf.get("kind")
        if kind in _FILL_EXCLUDED_KINDS:
            continue
        old_ref = rf.get("nodeRef")
        new_ref = old_to_new.get(old_ref, old_ref)
        materials.append(
            {
                "nodeRef": new_ref,
                "path": rf.get("path"),
                "kind": kind,
            }
        )

    warnings: List[Dict[str, Any]] = list(extra_warnings or [])

    return {
        "summary": {
            "knowledge": {"satisfied": sat, "partial": par, "missing": mis},
            "materialsToFill": len(materials),
            "warnings": len(warnings),
        },
        "knowledge": knowledge_report,
        "materialsToFill": materials,
        "warnings": warnings,
    }


# ── import 요청 바디 ──────────────────────────────────────────────────────────


class BlueprintImportRequest(BaseModel):
    """설계도 import 요청.

    ``blueprint`` 는 dict 또는 JSON 문자열 모두 허용한다(붙여넣기 호환).
    """

    blueprint: Union[Dict[str, Any], str]
    dryRun: bool = False


def _coerce_blueprint(raw: Union[Dict[str, Any], str]) -> Dict[str, Any]:
    """blueprint 가 문자열이면 json.loads, dict 면 그대로."""
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError) as e:
            raise ValidationError(
                f"설계도 JSON 파싱 실패: {e}",
                code="BLUEPRINT_INCOMPATIBLE",
                status_code=422,
            )
        if not isinstance(parsed, dict):
            raise ValidationError(
                "설계도는 JSON 객체여야 합니다.",
                code="BLUEPRINT_INCOMPATIBLE",
                status_code=422,
            )
        return parsed
    return raw


# ── import 엔드포인트 ────────────────────────────────────────────────────────


@router.post(
    "/import",
    summary="설계도(blueprint)를 새 워크플로우로 import (결정론적)",
    description=(
        "설계도 JSON 을 받아 노드/연결을 새 id 로 재부여하고, 인스턴스DB 를 "
        "name-match-or-create 로 해소한 뒤 새 워크플로우를 생성한다. "
        "LLM 미사용·레지스트리(ApiDefinition/AINode) 쓰기 없음 — 스냅샷은 노드 config 에 "
        "동결된 상태로만 유지된다. ``dryRun=true`` 면 저장하지 않고 계획+보정 리포트만 반환. "
        "보정(reconciliation) 리포트로 채워야 할 재료/지식 상태를 함께 반환한다."
    ),
)
async def import_blueprint(
    data: BlueprintImportRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """설계도 → 새 워크플로우 결정론적 import."""
    blueprint = _coerce_blueprint(data.blueprint)

    # 1) 호환성 검증
    _check_blueprint_compatible(blueprint)

    wf_meta = blueprint.get("workflow") or {}
    bp_nodes = wf_meta.get("nodes") or []
    bp_connections = wf_meta.get("connections") or []
    redacted_fields = blueprint.get("redactedFields") or []
    deps = blueprint.get("dependencies") or {}
    idb_deps = deps.get("instanceDbs") or []

    # 2) 재-ID (nodeId 어댑터 경유)
    nodes, connections, old_to_new = _reid_blueprint(bp_nodes, bp_connections)

    # 3) instanceDb name-match-or-create (dryRun 이면 생성 안 함)
    source_to_local, idb_warnings, idb_plan = await _resolve_instance_dbs(
        idb_deps, create=not data.dryRun
    )
    _rewrite_instance_db_ids(nodes, source_to_local)

    # 보정 리포트 (공용)
    reconciliation = _build_reconciliation(
        nodes, redacted_fields, old_to_new, extra_warnings=idb_warnings
    )

    # 7) dryRun — 저장/생성하지 않고 계획 + 보정만 반환
    if data.dryRun:
        return {
            "plan": {
                "nodeIdRemap": old_to_new,
                "instanceDbs": idb_plan,
                "nodeCount": len(nodes),
                "connectionCount": len(connections),
            },
            "reconciliation": reconciliation,
        }

    # 5) 워크플로우 생성 — create_workflow 형태와 동일하게 ORM 빌드
    workflow_id = f"wf-{uuid.uuid4().hex[:8]}"
    workflow = Workflow(
        id=workflow_id,
        name=wf_meta.get("name") or "imported-workflow",
        description=wf_meta.get("description"),
        tags=wf_meta.get("tags") or [],
        trigger=wf_meta.get("trigger") or {"type": "manual", "config": {}},
        variables=wf_meta.get("variables") or {},
        created_by="cli",
        generation_trace_ids=[],
    )
    db.add(workflow)

    for idx, nd in enumerate(nodes):
        node = WorkflowNode(
            id=nd.get("id") or nd.get("nodeId"),
            workflow_id=workflow_id,
            node_id=nd.get("nodeId") or nd.get("id"),
            definition_type=nd.get("definitionType"),
            ai_node_id=nd.get("aiNodeId"),
            config=nd.get("config") or {},
            name=nd.get("name") or nd.get("nodeId"),
            order_index=nd.get("orderIndex") if nd.get("orderIndex") is not None else idx,
            config_overrides=nd.get("configOverrides") or {},
            input_mapping=nd.get("inputMapping") or {},
        )
        db.add(node)

    for c in connections:
        conn = WorkflowConnection(
            id=c.get("id") or f"wc-{uuid.uuid4().hex[:8]}",
            workflow_id=workflow_id,
            source_node_id=c.get("sourceNodeId"),
            target_node_id=c.get("targetNodeId"),
            source_handle=c.get("sourceHandle"),
            target_handle=c.get("targetHandle"),
            condition=c.get("condition"),
        )
        db.add(conn)

    # 검증 게이트 — 스냅샷이 E7 을 만족, instanceDbId 는 로컬/유효
    from ...services.workflow_validator import validate_workflow_structure

    # 검증은 새 노드/연결 dict 기준 (camelCase 허용).
    validation = await validate_workflow_structure(nodes, connections, db)
    if not validation["valid"]:
        await db.rollback()
        raise ValidationError(
            "import 된 워크플로우 구조 검증에 실패했습니다",
            code="WORKFLOW_INVALID",
            status_code=422,
            details={
                "errors": validation["errors"],
                "warnings": validation["warnings"],
            },
        )

    await db.commit()

    return {"workflowId": workflow_id, "reconciliation": reconciliation}


# ════════════════════════════════════════════════════════════════════════════
# PHASE 8 — reconciliation(보정) 적용 엔드포인트 (결정론적, LLM 미사용)
# ════════════════════════════════════════════════════════════════════════════


async def _load_workflow_with_graph(db: AsyncSession, workflow_id: str) -> Workflow:
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.nodes), selectinload(Workflow.connections))
        .where(Workflow.id == workflow_id)
    )
    wf = result.scalar_one_or_none()
    if not wf:
        raise NotFoundError(
            "워크플로우를 찾을 수 없습니다",
            details={"workflowId": workflow_id},
        )
    return wf


def _nodes_as_dicts(wf: Workflow) -> List[Dict[str, Any]]:
    """ORM 노드 → reconciliation 빌더가 보는 dict 형태."""
    out: List[Dict[str, Any]] = []
    for n in wf.nodes:
        out.append(
            {
                "nodeId": n.node_id,
                "definitionType": n.definition_type,
                "config": n.config or {},
            }
        )
    return out


def _materials_from_current_config(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """저장된 노드 config 에서 아직 비어 있는(채워야 할) 재료 항목을 재계산한다.

    - apiSpecSnapshot.authConfig.* 값이 "" 이면 authSecret 으로 보고.
    - apiSpecSnapshots[i].authConfig.* 값이 "" 이면 authSecret.
    - defaultParams.* 값이 "" 이면 envParam.
    채워진(비어있지 않은) 항목은 목록에서 빠져 materialsToFill 가 줄어든다.
    """
    materials: List[Dict[str, Any]] = []

    def _scan_auth(auth: Any, base_path: str, node_ref: str) -> None:
        if not isinstance(auth, dict):
            return
        for k, v in auth.items():
            if v == "" or v is None:
                materials.append(
                    {"nodeRef": node_ref, "path": f"{base_path}.{k}", "kind": "authSecret"}
                )

    for n in nodes:
        node_ref = n.get("nodeId")
        cfg = n.get("config") or {}

        api_spec = cfg.get(API_SPEC_SNAPSHOT_KEY)
        if isinstance(api_spec, dict):
            _scan_auth(
                api_spec.get("authConfig"),
                f"{API_SPEC_SNAPSHOT_KEY}.authConfig",
                node_ref,
            )

        api_specs = cfg.get(API_SPEC_SNAPSHOTS_KEY)
        if isinstance(api_specs, list):
            for i, spec in enumerate(api_specs):
                if isinstance(spec, dict):
                    _scan_auth(
                        spec.get("authConfig"),
                        f"{API_SPEC_SNAPSHOTS_KEY}[{i}].authConfig",
                        node_ref,
                    )

        default_params = cfg.get("defaultParams")
        if isinstance(default_params, dict):
            for k, v in default_params.items():
                if v == "" or v is None:
                    materials.append(
                        {"nodeRef": node_ref, "path": f"defaultParams.{k}", "kind": "envParam"}
                    )

    return materials


def _build_reconciliation_from_workflow(
    wf: Workflow,
    extra_warnings: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """저장된 워크플로우 기준 보정 리포트 재계산 (fill/remap 후 응답용).

    materialsToFill 는 현재 config 에서 비어 있는 값만 재산출하므로,
    값을 채우면 자연히 줄어든다.
    """
    nodes = _nodes_as_dicts(wf)
    available_cats, available_svcs = _available_knowledge_facets()

    knowledge_report: List[Dict[str, Any]] = []
    sat = par = mis = 0
    for n in nodes:
        if n.get("definitionType") != "knowledge":
            continue
        requirement = _knowledge_requirement_from_config(n.get("config") or {})
        status_info = _knowledge_status_for(requirement, available_cats, available_svcs)
        status = status_info["status"]
        if status == "satisfied":
            sat += 1
        elif status == "partial":
            par += 1
        else:
            mis += 1
        knowledge_report.append(
            {
                "nodeRef": n.get("nodeId"),
                "requirement": requirement,
                "status": status,
                "missingCategories": status_info["missingCategories"],
                "missingServices": status_info["missingServices"],
                "availableCategories": status_info["availableCategories"],
                "availableServices": status_info["availableServices"],
                "suggestedActions": status_info["suggestedActions"],
            }
        )

    materials = _materials_from_current_config(nodes)
    warnings = list(extra_warnings or [])

    return {
        "summary": {
            "knowledge": {"satisfied": sat, "partial": par, "missing": mis},
            "materialsToFill": len(materials),
            "warnings": len(warnings),
        },
        "knowledge": knowledge_report,
        "materialsToFill": materials,
        "warnings": warnings,
    }


# ── config path 세터 (점/대괄호 경로 지원) ────────────────────────────────────

import re as _re  # noqa: E402

_PATH_TOKEN_RE = _re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def _parse_path(path: str) -> List[Union[str, int]]:
    """``a.b[0].c`` → ``['a','b',0,'c']`` 토큰 목록."""
    tokens: List[Union[str, int]] = []
    for m in _PATH_TOKEN_RE.finditer(path or ""):
        key, idx = m.group(1), m.group(2)
        if key is not None:
            tokens.append(key)
        elif idx is not None:
            tokens.append(int(idx))
    return tokens


def _set_at_path(container: Dict[str, Any], path: str, value: Any) -> bool:
    """config 의 점/대괄호 경로 위치에 value 를 설정. 성공 True.

    중간 경로가 없으면(스냅샷 키가 없는 등) 새로 만들지 않고 False (보수적).
    단, 마지막 키는 기존 dict 안에 없어도 설정한다(envParam 등 placeholder 보존 가정).
    """
    tokens = _parse_path(path)
    if not tokens:
        return False
    cur: Any = container
    for tok in tokens[:-1]:
        if isinstance(tok, int):
            if not isinstance(cur, list) or tok >= len(cur):
                return False
            cur = cur[tok]
        else:
            if not isinstance(cur, dict) or tok not in cur:
                return False
            cur = cur[tok]
    last = tokens[-1]
    if isinstance(last, int):
        if not isinstance(cur, list) or last >= len(cur):
            return False
        cur[last] = value
        return True
    if not isinstance(cur, dict):
        return False
    cur[last] = value
    return True


class FillMaterialItem(BaseModel):
    nodeRef: str
    path: str
    value: Any


class FillMaterialsRequest(BaseModel):
    values: List[FillMaterialItem] = Field(default_factory=list)


@router.post(
    "/workflows/{workflow_id}/fill-materials",
    summary="보정: 비워진 재료 값(auth/defaultParams) 채우기 (결정론적)",
    description=(
        "import 직후 비워진(redacted) 재료 값을 수신 환경 값으로 채운다. "
        "config 경로(예: ``apiSpecSnapshot.authConfig.token``, ``defaultParams.owner``)에 "
        "값을 set 한다. 기존 config 에 in-place 기록하므로 스냅샷 재동결을 트리거하지 않으며 "
        "snapshotSourceId 는 그대로 유지된다. generationTraceIds 도 보존된다. "
        "갱신된 보정 리포트(materialsToFill 축소)를 반환한다."
    ),
)
async def fill_materials(
    workflow_id: str,
    data: FillMaterialsRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """비워진 재료 값을 노드 config 경로에 채운다 (재동결 없음)."""
    from sqlalchemy.orm.attributes import flag_modified

    wf = await _load_workflow_with_graph(db, workflow_id)
    nodes_by_ref: Dict[str, WorkflowNode] = {n.node_id: n for n in wf.nodes}

    applied: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for item in data.values:
        node = nodes_by_ref.get(item.nodeRef)
        if node is None:
            skipped.append({"nodeRef": item.nodeRef, "path": item.path, "reason": "node not found"})
            continue
        cfg = dict(node.config or {})
        # 스냅샷 키는 절대 통째로 교체하지 않는다 — 경로 내부 값만 set.
        ok = _set_at_path(cfg, item.path, item.value)
        if not ok:
            skipped.append({"nodeRef": item.nodeRef, "path": item.path, "reason": "path not found"})
            continue
        node.config = cfg
        flag_modified(node, "config")
        applied.append({"nodeRef": item.nodeRef, "path": item.path})

    # generationTraceIds 및 스냅샷은 손대지 않음 — config 값만 갱신, 재동결 없음.
    await db.commit()

    # 갱신된 보정 리포트 재계산
    wf = await _load_workflow_with_graph(db, workflow_id)
    reconciliation = _build_reconciliation_from_workflow(wf)

    return {
        "workflowId": workflow_id,
        "applied": applied,
        "skipped": skipped,
        "reconciliation": reconciliation,
    }


class KnowledgeRemapItem(BaseModel):
    nodeRef: str
    from_: str = Field(..., alias="from")
    to: str

    model_config = {"populate_by_name": True}


class KnowledgeRemapRequest(BaseModel):
    remaps: List[KnowledgeRemapItem] = Field(default_factory=list)


@router.post(
    "/workflows/{workflow_id}/knowledge-remap",
    summary="보정: knowledge 노드 카테고리/서비스 from→to 재매핑 (결정론적)",
    description=(
        "knowledge 노드의 categories(및 services)를 from→to 로 결정론적으로 재작성한다. "
        "재검증 후 갱신된 보정 리포트를 반환한다. LLM 미사용."
    ),
)
async def knowledge_remap(
    workflow_id: str,
    data: KnowledgeRemapRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """knowledge 노드 category/service 를 from→to 로 재매핑."""
    from sqlalchemy.orm.attributes import flag_modified
    from ...services.workflow_validator import validate_workflow_structure

    wf = await _load_workflow_with_graph(db, workflow_id)
    nodes_by_ref: Dict[str, WorkflowNode] = {n.node_id: n for n in wf.nodes}

    applied: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for rm in data.remaps:
        node = nodes_by_ref.get(rm.nodeRef)
        if node is None or node.definition_type != "knowledge":
            skipped.append({"nodeRef": rm.nodeRef, "reason": "knowledge node not found"})
            continue
        cfg = dict(node.config or {})
        changed = False

        # categories (multi) — 단일 category 하위호환 흡수
        cats = list(cfg.get("categories") or [])
        if not cats and cfg.get("category"):
            cats = [cfg.get("category")]
        if rm.from_ in cats:
            cats = [rm.to if c == rm.from_ else c for c in cats]
            cfg["categories"] = cats
            cfg.pop("category", None)  # 단일 키 정리
            changed = True

        # services
        svcs = list(cfg.get("services") or [])
        if rm.from_ in svcs:
            svcs = [rm.to if s == rm.from_ else s for s in svcs]
            cfg["services"] = svcs
            changed = True

        if changed:
            node.config = cfg
            flag_modified(node, "config")
            applied.append({"nodeRef": rm.nodeRef, "from": rm.from_, "to": rm.to})
        else:
            skipped.append({"nodeRef": rm.nodeRef, "reason": "from value not present"})

    # 재검증 (구조 — 스냅샷이 E7 만족)
    nodes_for_validate = _nodes_with_ids(wf)
    connections_for_validate = _connections_as_dicts(wf)
    validation = await validate_workflow_structure(
        nodes_for_validate, connections_for_validate, db
    )
    if not validation["valid"]:
        await db.rollback()
        raise ValidationError(
            "knowledge 재매핑 후 구조 검증에 실패했습니다",
            code="WORKFLOW_INVALID",
            status_code=422,
            details={
                "errors": validation["errors"],
                "warnings": validation["warnings"],
            },
        )

    await db.commit()

    wf = await _load_workflow_with_graph(db, workflow_id)
    reconciliation = _build_reconciliation_from_workflow(wf)

    return {
        "workflowId": workflow_id,
        "applied": applied,
        "skipped": skipped,
        "reconciliation": reconciliation,
    }


def _nodes_with_ids(wf: Workflow) -> List[Dict[str, Any]]:
    """검증기용 노드 dict — id/nodeId/definitionType/config 포함."""
    out: List[Dict[str, Any]] = []
    for n in wf.nodes:
        out.append(
            {
                "id": n.node_id,
                "nodeId": n.node_id,
                "definitionType": n.definition_type,
                "aiNodeId": n.ai_node_id,
                "name": n.name,
                "config": n.config or {},
                "configOverrides": n.config_overrides or {},
                "inputMapping": n.input_mapping or {},
            }
        )
    return out


def _connections_as_dicts(wf: Workflow) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for c in wf.connections:
        out.append(
            {
                "id": c.id,
                "sourceNodeId": c.source_node_id,
                "targetNodeId": c.target_node_id,
                "sourceHandle": c.source_handle,
                "targetHandle": c.target_handle,
                "condition": c.condition,
            }
        )
    return out
