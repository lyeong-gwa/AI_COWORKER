"""단계적 워크플로우 생성 서비스.

사용자가 자연어로 업무를 설명하면, LLM 게이트웨이를 단계적으로 호출하여
워크플로우 draft를 생성하고, Phase 1 검증기(workflow_validator)로 게이트한 뒤
결과를 반환한다. 저장은 하지 않는다.

파이프라인 단계:
  Stage A · Plan   — 골격(defType + name + purpose 배열) 생성
  Stage B · Assemble — 완전한 draft JSON 생성
  Stage C · Validate — 구조 검증
  Stage D · Repair   — 검증 실패 시 최대 MAX_REPAIR 회 수정 반복
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..nodes.catalog import get_catalog, get_entry
from ..services.llm import get_llm_handler, LLMRequest
from ..services.workflow_validator import validate_workflow_structure
from ..services.generation_trace import append_trace, make_tracing_proxy

logger = logging.getLogger(__name__)

# 최대 repair 시도 횟수
MAX_REPAIR = 3


# ── 내부 유틸 ────────────────────────────────────────────────────────────────


def _uuid8() -> str:
    """8자리 랜덤 hex ID 생성."""
    return uuid.uuid4().hex[:8]


def _clean_json(text: str) -> str:
    """LLM 응답에서 마크다운 코드펜스(```json ... ```)를 제거하고 순수 JSON 문자열 반환."""
    # ```json ... ``` 또는 ``` ... ``` 패턴 제거
    text = text.strip()
    pattern = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)
    m = pattern.match(text)
    if m:
        return m.group(1).strip()
    # 앞/뒤 펜스만 있는 경우도 처리
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _remap_config_ids(config: Any, id_map: Dict[str, str]) -> Any:
    """config 내부를 재귀 순회하며 old_id → new_id 치환.

    문자열 값이 id_map의 키와 정확히 일치하면 new_id로 교체한다.
    inputMapping 값($.key 형식)은 노드 id가 아니므로 이 함수가 처리해도 무해하지만,
    실제 노드 id가 포함될 일이 없어 사실상 무변환으로 통과한다.
    """
    if isinstance(config, dict):
        return {k: _remap_config_ids(v, id_map) for k, v in config.items()}
    if isinstance(config, list):
        return [_remap_config_ids(item, id_map) for item in config]
    if isinstance(config, str) and config in id_map:
        return id_map[config]
    return config


def _normalize_sorter_wiring(draft: Dict) -> Dict:
    """sorter 노드의 배선을 결정론적으로 정규화한다.

    LLM이 sorter 핸들/연결을 기계적으로 틀리는 패턴을 후처리로 교정:
    1. 자기순환 제거: sourceNodeId == targetNodeId인 연결 삭제.
    2. 중복 연결 제거: (source, target, sourceHandle) 동일한 연결 1개만 유지.
    3. sorter config 정리: definitionType=="sorter" 노드의 config에서
       sourceHandle 같은 연결 전용 키 제거 (config.rules만 유지).
    4. sorter 출력 핸들 정규화:
       - 유효 핸들 집합 = { "rule-<r['id']>" for r in rules } ∪ {"default"}
       - sourceHandle이 유효 집합에 없으면 rules 수에 따라 교정/재배정.
       - 각 rule에 대응 연결이 없으면 핸들 불명 연결 재배정 또는 새 연결 생성.
       - 동일 rule 핸들 중복 연결은 1개만 유지.
    """
    import copy

    draft = copy.deepcopy(draft)
    nodes: List[Dict] = draft.get("nodes", [])
    connections: List[Dict] = draft.get("connections", [])

    # ── 1. 자기순환 제거 ────────────────────────────────────────────────────
    connections = [
        c for c in connections
        if c.get("sourceNodeId") != c.get("targetNodeId")
    ]

    # ── 2. 중복 연결 제거 (source, target, sourceHandle) ────────────────────
    seen_conn_keys: set = set()
    unique_connections: List[Dict] = []
    for c in connections:
        key = (c.get("sourceNodeId"), c.get("targetNodeId"), c.get("sourceHandle"))
        if key not in seen_conn_keys:
            seen_conn_keys.add(key)
            unique_connections.append(c)
    connections = unique_connections

    # ── 3. sorter config 정리 + ── 4. 핸들 정규화 ───────────────────────────
    # sorter 노드 인덱스 구성
    sorter_nodes = [
        n for n in nodes
        if n.get("definitionType") == "sorter"
    ]

    for sorter in sorter_nodes:
        sorter_id = sorter.get("id") or sorter.get("nodeId")
        config = sorter.get("config") or {}

        # 3. config에서 연결 전용 키 제거 (sourceHandle 등)
        CONN_ONLY_KEYS = {"sourceHandle", "targetHandle", "handle"}
        for k in list(config.keys()):
            if k in CONN_ONLY_KEYS:
                logger.debug(
                    "sorter config 정리: 노드 %s의 config에서 연결 전용 키 '%s' 제거",
                    sorter_id, k
                )
                del config[k]
        sorter["config"] = config

        rules: List[Dict] = config.get("rules") or []
        if not rules:
            # rules가 없으면 핸들 정규화 불필요
            continue

        # 유효 핸들 집합
        valid_handles: set = {f"rule-{r['id']}" for r in rules if r.get("id")}
        valid_handles.add("default")

        # 이 sorter에서 나가는 연결 목록 (인덱스 포함)
        out_conns = [
            (i, c) for i, c in enumerate(connections)
            if c.get("sourceNodeId") == sorter_id
        ]

        # 각 rule의 유효 핸들
        rule_handles = [f"rule-{r['id']}" for r in rules if r.get("id")]

        # 이미 올바르게 매핑된 rule 핸들 집합 추적
        assigned_rule_handles: set = set()
        # 핸들이 유효하지 않은 연결 (교정 필요)
        bad_out_idxs: List[int] = []

        for global_idx, c in out_conns:
            sh = c.get("sourceHandle")
            if sh in valid_handles:
                if sh != "default":
                    assigned_rule_handles.add(sh)
            else:
                # 유효하지 않은 핸들 → 교정 대상
                bad_out_idxs.append(global_idx)

        # 핸들 교정: rules==1이면 첫 rule 핸들로, 여러 개면 아직 미할당 rule 순서대로 배정
        unassigned_rule_handles = [h for h in rule_handles if h not in assigned_rule_handles]

        for global_idx in bad_out_idxs:
            c = connections[global_idx]
            sh = c.get("sourceHandle") or ""
            # "rule-"로 시작하지만 잘못된 경우: rule id가 접두사 없이 그대로 들어온 경우 교정
            # 예: rule id="rule-1" → LLM이 sourceHandle="rule-1"로 씀 → 실제 핸들은 "rule-rule-1"
            corrected = False
            if sh and not sh.startswith("rule-"):
                # 접두사 없이 id가 직접 들어온 경우: "rule-" + sh로 시도
                candidate = f"rule-{sh}"
                if candidate in valid_handles:
                    logger.debug(
                        "sorter 핸들 교정: 노드 %s 연결의 sourceHandle '%s' → '%s'",
                        sorter_id, sh, candidate
                    )
                    connections[global_idx]["sourceHandle"] = candidate
                    if candidate in unassigned_rule_handles:
                        unassigned_rule_handles.remove(candidate)
                        assigned_rule_handles.add(candidate)
                    corrected = True

            if not corrected:
                if len(rules) == 1:
                    # rule이 1개면 그 rule 핸들로 강제 배정
                    target_handle = rule_handles[0]
                    logger.debug(
                        "sorter 핸들 교정(단일 rule): 노드 %s 연결의 sourceHandle '%s' → '%s'",
                        sorter_id, sh, target_handle
                    )
                    connections[global_idx]["sourceHandle"] = target_handle
                    assigned_rule_handles.add(target_handle)
                    if target_handle in unassigned_rule_handles:
                        unassigned_rule_handles.remove(target_handle)
                elif unassigned_rule_handles:
                    # 미할당 rule 중 첫 번째에 배정
                    target_handle = unassigned_rule_handles.pop(0)
                    logger.debug(
                        "sorter 핸들 교정(미할당 배정): 노드 %s 연결의 sourceHandle '%s' → '%s'",
                        sorter_id, sh, target_handle
                    )
                    connections[global_idx]["sourceHandle"] = target_handle
                    assigned_rule_handles.add(target_handle)
                # 배정할 미할당 rule이 없으면 그대로 둠 (검증기가 잡게 둠)

        # 교정 후 다시 assigned 재계산
        assigned_rule_handles_after: set = set()
        out_conns_after = [(i, c) for i, c in enumerate(connections) if c.get("sourceNodeId") == sorter_id]
        for _, c in out_conns_after:
            sh = c.get("sourceHandle")
            if sh and sh in valid_handles and sh != "default":
                assigned_rule_handles_after.add(sh)

        # rule 핸들별 중복 연결 제거
        rule_handle_seen: set = set()
        to_remove_idxs: set = set()
        for i, c in enumerate(connections):
            if c.get("sourceNodeId") != sorter_id:
                continue
            sh = c.get("sourceHandle")
            if sh and sh in valid_handles and sh != "default":
                if sh in rule_handle_seen:
                    to_remove_idxs.add(i)
                else:
                    rule_handle_seen.add(sh)
        if to_remove_idxs:
            connections = [c for i, c in enumerate(connections) if i not in to_remove_idxs]

        # rule에 대응 연결이 없는 경우: 타겟을 찾아 연결 생성
        assigned_final: set = set()
        out_conns_final = [(i, c) for i, c in enumerate(connections) if c.get("sourceNodeId") == sorter_id]
        for _, c in out_conns_final:
            sh = c.get("sourceHandle")
            if sh and sh in valid_handles and sh != "default":
                assigned_final.add(sh)

        still_unassigned = [h for h in rule_handles if h not in assigned_final]
        if still_unassigned:
            # 노드 정의타입 맵
            node_def_map = {
                (n.get("id") or n.get("nodeId")): n.get("definitionType", "")
                for n in nodes
            }
            # 1순위: 이미 나가는 연결의 타겟 중 비-sorter 노드
            downstream_targets = [
                c.get("targetNodeId") for _, c in out_conns_final
                if c.get("targetNodeId")
            ]
            non_sorter_targets = [
                t for t in downstream_targets
                if node_def_map.get(t, "") != "sorter"
            ]
            target_for_new = non_sorter_targets[0] if non_sorter_targets else (
                downstream_targets[0] if downstream_targets else None
            )
            # 2순위: 연결이 전혀 없는 경우, 전체 노드에서 sorter/트리거가 아닌 첫 번째 노드를 fallback으로 사용
            if target_for_new is None:
                TRIGGER_TYPES = {"form-start", "api-start"}
                fallback_nodes = [
                    n for n in nodes
                    if (n.get("id") or n.get("nodeId")) != sorter_id
                    and n.get("definitionType") not in TRIGGER_TYPES
                    and n.get("definitionType") != "sorter"
                ]
                if fallback_nodes:
                    target_for_new = fallback_nodes[0].get("id") or fallback_nodes[0].get("nodeId")

            for missing_handle in still_unassigned:
                if target_for_new:
                    new_conn: Dict = {
                        "id": f"wc-{_uuid8()}",
                        "sourceNodeId": sorter_id,
                        "targetNodeId": target_for_new,
                        "sourceHandle": missing_handle,
                    }
                    logger.debug(
                        "sorter 연결 생성: 노드 %s rule 핸들 '%s' → 타겟 %s",
                        sorter_id, missing_handle, target_for_new
                    )
                    connections.append(new_conn)
                else:
                    logger.debug(
                        "sorter 연결 생성 스킵: 노드 %s rule 핸들 '%s' — 타겟 없음",
                        sorter_id, missing_handle
                    )

    draft["connections"] = connections
    return draft


def _ensure_ids(nodes: List[Dict], connections: List[Dict]) -> tuple[List[Dict], List[Dict]]:
    """LLM이 준 노드·연결 id를 신뢰하지 않고 항상 새로운 전역 고유 id를 부여한다.

    처리 순서:
    1. 각 노드에 wn-<uuid8> 새 id를 부여하고 old→new 리매핑 맵을 구성한다.
    2. connections의 sourceNodeId/targetNodeId를 리매핑 맵으로 치환한다.
       connection 자체 id도 wc-<uuid8>으로 새로 부여한다.
    3. 노드 config 내부를 재귀 순회하며 old_id 집합에 속하는 문자열을 new_id로 치환한다.
       (mapper.warehouseNodeId, sorter.dedup.warehouseNodeId 등 커버)
    """
    # ── 1. 노드 id 리매핑 ──────────────────────────────────────────────────────
    id_map: Dict[str, str] = {}
    for n in nodes:
        old_id = n.get("id") or ""
        new_id = f"wn-{_uuid8()}"
        if old_id:
            id_map[old_id] = new_id
        n["id"] = new_id
        n["nodeId"] = new_id  # nodeId == id 관례 유지

    # ── 2. connections 치환 ────────────────────────────────────────────────────
    for c in connections:
        c["id"] = f"wc-{_uuid8()}"
        src = c.get("sourceNodeId")
        if src and src in id_map:
            c["sourceNodeId"] = id_map[src]
        tgt = c.get("targetNodeId")
        if tgt and tgt in id_map:
            c["targetNodeId"] = id_map[tgt]

    # ── 3. config 내부 노드 id 참조 치환 ──────────────────────────────────────
    if id_map:
        for n in nodes:
            if "config" in n and isinstance(n["config"], (dict, list)):
                n["config"] = _remap_config_ids(n["config"], id_map)

    return nodes, connections


def _build_catalog_summary() -> str:
    """Stage A 용: defType·purpose·connectsWellWith 한 줄 요약 목록."""
    lines = []
    for entry in get_catalog():
        lines.append(
            f"- {entry.defType}: {entry.purpose[:80]}  "
            f"(connectsWellWith: {', '.join(entry.connectsWellWith)})"
        )
    return "\n".join(lines)


def _build_catalog_detail(def_types: List[str]) -> str:
    """Stage B 용: 선택된 defType들의 전체 카탈로그 스키마 상세."""
    sections = []
    for dt in def_types:
        entry = get_entry(dt)
        if entry is None:
            continue
        # 필수 config 필드만 추출
        required_configs = [
            f"  - {f.name} (required={f.required}): {f.description}"
            for f in entry.config
        ]
        inputs_desc = [
            f"  - {f.name} ({f.type}): {f.description}"
            for f in entry.inputs
        ]
        outputs_desc = [
            f"  - {f.name} ({f.type}): {f.description}"
            for f in entry.outputs
        ]
        sections.append(
            f"### {entry.defType} ({entry.label})\n"
            f"purpose: {entry.purpose}\n"
            f"requiresUpstream: {entry.requiresUpstream}\n"
            f"producesArray: {entry.producesArray}\n"
            f"connectsWellWith: {entry.connectsWellWith}\n"
            f"inputs:\n" + ("\n".join(inputs_desc) or "  (없음)") + "\n"
            f"outputs:\n" + ("\n".join(outputs_desc) or "  (없음)") + "\n"
            f"config 필드:\n" + ("\n".join(required_configs) or "  (없음)")
        )
    return "\n\n".join(sections)


async def _collect_materials(db: AsyncSession) -> Dict[str, Any]:
    """DB에서 가용 재료(api-definitions, instance-dbs, ai-nodes, knowledge) 목록 수집.

    각 목록은 LLM에 전달할 요약 형태로 반환한다.
    """
    materials: Dict[str, Any] = {
        "apiDefinitions": [],
        "instanceDbs": [],
        "aiNodes": [],
        "knowledgeCategories": [],
    }

    try:
        from sqlalchemy import select as sa_select
        from ..models.api_definition import ApiDefinition
        result = await db.execute(
            sa_select(
                ApiDefinition.id,
                ApiDefinition.name,
                ApiDefinition.method,
                ApiDefinition.url_template,
                ApiDefinition.parameters,
                ApiDefinition.body_template,
            )
            .where(ApiDefinition.is_active == True)  # noqa: E712
        )
        for row in result.all():
            # bodyTemplate에서 {{변수명}} 패턴 추출 (LLM이 body 변수명을 알도록)
            body_vars: list[str] = []
            if row.body_template:
                body_vars = re.findall(r"\{\{(\w+)\}\}", row.body_template)

            # query/path 파라미터 목록 (name, in, required)
            params_summary: list[dict] = []
            for p in (row.parameters or []):
                if isinstance(p, dict):
                    params_summary.append({
                        "name": p.get("name", ""),
                        "in": p.get("in", ""),
                        "required": p.get("required", False),
                    })

            materials["apiDefinitions"].append({
                "id": row.id,
                "name": row.name,
                "method": row.method,
                "url": row.url_template,
                "params": params_summary,       # query/path 파라미터 상세
                "bodyVars": body_vars,          # bodyTemplate 필요 변수명 목록
            })
    except Exception as e:
        logger.debug("api-definitions 조회 실패(무시): %s", e)

    try:
        from ..services.instance_db_store import get_instance_db_store
        store = get_instance_db_store()
        # list_dbs() 는 존재하지 않음 — 올바른 비동기 메서드 list_meta() 사용
        dbs = await store.list_meta()
        for item in dbs:
            materials["instanceDbs"].append({
                "id": item.get("id"),
                "name": item.get("name"),
                # LLM이 용도를 파악할 수 있도록 description도 포함 (없으면 None)
                "description": item.get("description"),
            })
    except Exception as e:
        logger.debug("instance-dbs 조회 실패(무시): %s", e)

    try:
        from sqlalchemy import select as sa_select
        from ..models.node import AINode
        result = await db.execute(
            sa_select(AINode.id, AINode.name, AINode.description, AINode.system_prompt)
            .where(AINode.is_active == True)  # noqa: E712
        )
        for row in result.all():
            # 용도 텍스트: description 우선, 없으면 system_prompt 앞 50자 요약
            usage = (row.description or "").strip()
            if not usage and row.system_prompt:
                usage = row.system_prompt.strip()[:50]
            materials["aiNodes"].append({"id": row.id, "name": row.name, "usage": usage})
    except Exception as e:
        logger.debug("ai-nodes 조회 실패(무시): %s", e)

    try:
        from ..services.knowledge_file_service import list_md_files
        docs = list_md_files()
        cats = set()
        for d in docs:
            cat = d.get("category") or d.get("metadata", {}).get("category")
            if cat:
                cats.add(cat)
        materials["knowledgeCategories"] = sorted(cats)
    except Exception as e:
        logger.debug("knowledge 조회 실패(무시): %s", e)

    return materials


def _materials_summary(materials: Dict[str, Any]) -> str:
    """재료 목록을 LLM에 전달할 텍스트로 직렬화.

    ⚠️ 중요: config의 apiDefinitionId / instanceDbId / aiNodeId 는
    반드시 아래 목록의 실제 ID 중에서만 선택하라. 임의의 ID를 지어내지 말라.
    """
    lines = [
        "## 가용 재료",
        "⚠️ 경고: config 필드(apiDefinitionId, instanceDbId, aiNodeId 등)에는",
        "반드시 아래 목록의 실제 ID 값만 사용하라. 목록에 없는 임의의 ID를 지어내는 것은 절대 금지.",
        "",
    ]

    api_defs = materials.get("apiDefinitions", [])
    if api_defs:
        lines.append("### API 명세 (api-definitions) — apiDefinitionId 에 아래 id 중 하나만 사용")
        for a in api_defs:
            lines.append(f"  - id={a['id']!r}, name={a['name']!r}, {a['method']} {a['url']}")
            # query/path 파라미터 상세: LLM이 defaultParams에 실제 값을 채울 수 있도록
            params = a.get("params") or []
            if params:
                req_params = [p for p in params if p.get("required")]
                opt_params = [p for p in params if not p.get("required")]
                if req_params:
                    req_desc = ", ".join(
                        f"{p['name']}({p['in']})" for p in req_params
                    )
                    lines.append(f"    [필수 파라미터] {req_desc}")
                if opt_params:
                    opt_desc = ", ".join(
                        f"{p['name']}({p['in']})" for p in opt_params
                    )
                    lines.append(f"    [선택 파라미터] {opt_desc}")
            else:
                lines.append("    [파라미터 없음]")
            # bodyTemplate 변수명: LLM이 POST body 변수를 정확히 맞출 수 있도록
            body_vars = a.get("bodyVars") or []
            if body_vars:
                lines.append(f"    [body 필요 변수] {', '.join(body_vars)}")
    else:
        lines.append("### API 명세: (등록된 항목 없음 — api-call/api-start 노드 사용 불가)")

    idbs = materials.get("instanceDbs", [])
    if idbs:
        lines.append("### 인스턴스DB (instance-dbs) — instanceDbId 에 아래 id 중 하나만 사용")
        for d in idbs:
            lines.append(f"  - id={d['id']!r}, name={d['name']!r}")
    else:
        lines.append(
            "### 인스턴스DB: (등록된 항목 없음 — instance-db-insert/instance-db-lookup 노드 사용 불가,"
            " 해당 노드를 골격에 포함하지 말 것)"
        )

    ai_nodes = materials.get("aiNodes", [])
    if ai_nodes:
        lines.append("### 커스텀 AI 노드 (ai-nodes) — ai_node_id 에 아래 id 중 하나만 사용")
        lines.append("  ⚠️ ai_node_id는 커스텀 노드의 용도가 현재 작업과 명백히 일치할 때만 사용할 것.")
        lines.append("  분류(classify)/추출(extract)/라우팅 전용 노드를 '답변 작성/요약/생성' 작업에 사용하는 것은 금지.")
        lines.append("  의미가 정확히 맞는 커스텀 노드가 없으면 반드시 inline config.prompt(+model)를 사용할 것.")
        for n in ai_nodes:
            usage_text = n.get("usage", "")
            usage_part = f", 용도='{usage_text}'" if usage_text else ""
            lines.append(f"  - id={n['id']!r}, name={n['name']!r}{usage_part}")
    else:
        lines.append("### 커스텀 AI 노드: (등록된 항목 없음 — ai-custom 노드는 inline config.prompt(+model)를 사용할 것)")

    knowledge_cats = materials.get("knowledgeCategories", [])
    if knowledge_cats:
        lines.append("### 지식 카테고리 (knowledge) — knowledge 노드의 category 파라미터로 사용 가능")
        lines.append("  " + ", ".join(knowledge_cats))
    else:
        lines.append("### 지식 카테고리: (등록된 항목 없음)")

    return "\n".join(lines)


def _build_broken_ref_hint(errors: List[Dict], materials: Dict[str, Any]) -> str:
    """broken-ref 오류가 있을 때 유효 ID 목록을 안내하는 힌트 문자열을 생성한다."""
    broken = [e for e in errors if e.get("code") == "broken-ref"]
    if not broken:
        return ""

    lines = ["\n## ❌ 참조 오류(broken-ref) 수정 안내"]
    lines.append("다음 config 필드에 존재하지 않는 ID가 사용되었습니다. 반드시 아래 유효 ID로 교체하세요:\n")

    for e in broken:
        lines.append(f"  - {e.get('message', '')}")

    lines.append("\n유효한 ID 목록:")

    api_defs = materials.get("apiDefinitions", [])
    if api_defs:
        lines.append("  [apiDefinitionId 후보]")
        for a in api_defs:
            lines.append(f"    - {a['id']!r}  ({a['name']})")
    else:
        lines.append("  [apiDefinitionId] 등록된 항목 없음 — 해당 노드를 제거하세요")

    idbs = materials.get("instanceDbs", [])
    if idbs:
        lines.append("  [instanceDbId 후보]")
        for d in idbs:
            lines.append(f"    - {d['id']!r}  ({d['name']})")
    else:
        lines.append("  [instanceDbId] 등록된 항목 없음 — 해당 노드를 제거하세요")

    ai_nodes = materials.get("aiNodes", [])
    if ai_nodes:
        lines.append("  [aiNodeId / ai_node_id 후보]")
        for n in ai_nodes:
            usage_text = n.get("usage", "")
            usage_part = f", 용도='{usage_text}'" if usage_text else ""
            lines.append(f"    - {n['id']!r}  ({n['name']}{usage_part})")
    else:
        lines.append("  [aiNodeId] 등록된 항목 없음")

    lines.append("\n임의의 ID(예: 'idb-1a2b3c4d', 'api-abc123')를 지어내는 것은 절대 금지.")
    return "\n".join(lines)


# ── Stage A: Plan ─────────────────────────────────────────────────────────────

_STAGE_A_SYSTEM = """당신은 워크플로우 설계 전문가입니다.
반드시 JSON 배열만 출력하세요. 마크다운 코드펜스(```)는 절대 사용하지 마세요.
설명 문장, 인사말 등 JSON 이외의 텍스트를 포함하지 마세요.

출력 형식(JSON 배열):
[
  {"defType": "<defType>", "name": "<노드이름>", "purpose": "<이 노드가 여기서 하는 역할>"},
  ...
]

제약:
- 반드시 트리거 노드(form-start 또는 api-start) 1개로 시작하세요.
- 범용 13종 defType(form-start, api-start, ai-custom, ai-api-router, sorter, unpacker,
  mapper, api-call, knowledge, instance-db-insert, instance-db-lookup, result, markdown-viewer)
  만 사용하세요. 도메인 특화 노드는 절대 만들지 마세요.
- 최소 2개, 최대 8개 노드로 구성하세요.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【노드 선택 패턴 매핑 규칙 (골격 분해 기준)】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. **데이터 출처 판단 — form-start vs api-start**
   - 워크플로우가 처리할 데이터를 "사용자가 직접 입력"하면 → `form-start`
   - "외부 시스템/등록된 API에서 조회·수집·가져온다"면 → `api-start` (가용 재료의 적절한 api-definition 사용)
   - 신호 표현: "목록을 조회/가져와서 ~한다", "~에서 데이터를 받아", "~API를 호출해" → `api-start` 신호
   - **[강화] 처리 대상이 외부 시스템의 레코드·목록(문의글·티켓·이슈·게시글·주문 등)이고,
     가용 재료의 api-definition 중 그 데이터를 조회(GET)하는 것이 있으면,
     사용자 설명에 "조회/가져온다" 같은 명시 동사가 없더라도 반드시 `api-start`로 그 API를 트리거에 사용한다.**
   - "~문의글에 대해", "~티켓을 처리", "~목록을 ~한다" 처럼 **이미 어딘가에 존재하는 데이터 집합**을 대상으로 하는 표현이 있으면
     조회용 `api-start`가 기본이다. 사용자가 매 실행마다 값을 직접 타이핑하는 것이 명백한 경우에만 `form-start`를 선택한다.

2. **배열/목록 건별 처리 — unpacker**
   - 조회 결과가 여러 건(목록/배열)이고 각 건을 개별로 처리해야 한다면 → `unpacker` 필수
   - 신호 표현: "목록", "여러 건", "각 건마다", "건별로" → `unpacker` 신호

3. **중복·이미 처리한 것 제외(스킵 필터) — sorter (instance-db-lookup 아님)**
   - "이미 처리/답변한 것 제외", "과거에 ~하지 않은 것만", "중복 없이", "한 번만 처리" 같은 요구
     → 반드시 `sorter` 로 구현한다 (인스턴스DB 이력과 대조하여 신규만 통과, 기존은 스킵)
   - ⚠️ `instance-db-lookup`은 사용하지 말 것 — lookup은 '다른 데이터를 가져와 현재 입력에 병합'할 때만
   - 구분 요약: 스킵 필터 = sorter / 데이터 병합 = instance-db-lookup

4. **처리 이력 저장 — instance-db-insert**
   - "이력을 남긴다", "다음 실행 때 중복 방지", "처리한 것을 기록한다" 요구
     → 워크플로우 끝에 `instance-db-insert` 를 추가해 처리 키를 저장한다

5. **지식 기반 생성 — knowledge + ai-custom**
   - "지식/문서를 근거로", "지식베이스 참고", "KB 검색 후" 등이면
     → `ai-custom` 앞에 `knowledge` 노드를 둔다

6. **복합 신호가 결합될 때 — 전체 골격 포함 필수**
   - 외부 목록 조회 + 과거 처리분 제외 + 건별 작업 + 이력 저장이 모두 있으면
     아래 골격을 **빠짐없이** 포함한다:

     api-start → unpacker → sorter(이력대조 스킵) → [knowledge →] ai-custom → [api-call →] instance-db-insert

   - 각 신호에 해당하는 노드를 누락하지 말 것. 신호가 없는 노드만 생략 가능.
"""


async def _stage_a_plan(
    description: str,
    catalog_summary: str,
    materials_text: str,
    handler: Any,
) -> tuple[List[Dict], str]:
    """Stage A: 워크플로우 골격 배열 생성."""
    prompt = f"""사용자 업무 설명:
{description}

## 범용 노드 카탈로그 (defType: purpose)
{catalog_summary}

{materials_text}

위 업무를 자동화하는 워크플로우의 노드 골격을 JSON 배열로 출력하세요.
각 항목: {{"defType": "...", "name": "...", "purpose": "..."}}
"""
    req = LLMRequest.simple(
        prompt=prompt,
        system_prompt=_STAGE_A_SYSTEM,
        temperature=0.3,
        max_tokens=1000,
        call_type="workflow_generator_stage_a",
    )
    resp = await handler.chat(req)
    raw = _clean_json(resp.content)

    try:
        skeleton = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Stage A JSON 파싱 실패: %s", raw[:200])
        skeleton = []

    # 카탈로그에 없는 defType 제거
    valid_defs = {e.defType for e in get_catalog()}
    filtered = [item for item in skeleton if isinstance(item, dict) and item.get("defType") in valid_defs]
    removed = [item for item in skeleton if isinstance(item, dict) and item.get("defType") not in valid_defs]

    stage_note = f"Stage A 완료: {len(filtered)}개 노드 골격"
    if removed:
        stage_note += f" (카탈로그 외 {len(removed)}개 제거: {[r.get('defType') for r in removed]})"

    return filtered, stage_note


# ── Stage B: Assemble ─────────────────────────────────────────────────────────

_STAGE_B_SYSTEM = """당신은 워크플로우 JSON 생성 전문가입니다.
반드시 JSON 객체만 출력하세요. 마크다운 코드펜스(```)는 절대 사용하지 마세요.
설명 문장, 인사말 등 JSON 이외의 텍스트를 포함하지 마세요.

출력 형식(JSON 객체):
{
  "name": "<워크플로우 이름>",
  "description": "<설명>",
  "tags": ["<태그>"],
  "nodes": [
    {
      "id": "wn-<8hex>",
      "nodeId": "wn-<8hex>",
      "definitionType": "<defType>",
      "name": "<노드이름>",
      "config": { <카탈로그의 required 설정 필드를 모두 채움> },
      "inputMapping": {}
    }
  ],
  "connections": [
    {
      "id": "wc-<8hex>",
      "sourceNodeId": "<노드id>",
      "targetNodeId": "<노드id>",
      "sourceHandle": null
    }
  ]
}

필수 규칙:
1. 모든 노드를 연결하세요 (고립 노드 금지).
2. 트리거 노드(form-start 또는 api-start)가 정확히 1개 있어야 합니다.
   **[강화] Stage A 골격에 api-start가 포함되어 있으면 반드시 api-start를 트리거로 사용하고, 적절한 apiDefinitionId를 config에 지정한다.
   처리 대상이 외부 시스템의 레코드·목록(문의글·티켓·이슈·게시글·주문 등)인 경우 api-start + 조회 API가 기본이다.**
3. 카탈로그의 required=True config 필드를 모두 채우세요.
4. sorter 노드가 있으면 각 rule에 대응하는 "rule-<id>" sourceHandle 연결을 반드시 추가하세요.
5. api-start/api-call 노드의 config.apiDefinitionId에는 반드시 아래 '가용 재료' 목록의 실제 id만 사용하세요. 임의의 ID를 지어내지 마세요.
6. ai-custom 노드의 config.ai_node_id에는 반드시 아래 '가용 재료' 목록의 실제 id만 사용하세요. 임의의 ID를 지어내지 마세요.
7. instance-db-insert/instance-db-lookup 노드의 config.instanceDbId에는 반드시 아래 '가용 재료' 목록의 실제 id만 사용하세요. 임의의 ID를 지어내지 마세요.
8. '가용 재료' 목록에 해당 재료가 없으면(예: 인스턴스DB 0개), 그 노드를 생성하지 마세요.
9. id 형식: 노드 wn-<8hex>, 연결 wc-<8hex>.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【form-start의 config.fields 작성 규칙】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

10. form-start의 config.fields는 **오직 사용자가 워크플로우를 시작할 때 직접 입력하는 값**만 정의한다.
    - 올바른 예: 문의 내용, 티켓 번호, 조회 키워드, 날짜, 고객명 등 사람이 입력창에 직접 타이핑하는 항목.

11. 다운스트림 노드(knowledge, ai-custom, api-call, result 등)가 실행 중에 생성하는 출력 키는
    절대로 form-start 필드로 만들지 말 것.
    - 금지 예시: knowledge 노드의 출력 키 "knowledge", ai-custom 노드의 출력 키 "response",
      api-call 결과 "data", "results", "answer", "summary" 등.
    - 이들은 노드가 내부적으로 생성하는 값이며 사용자 입력이 아니다.

12. 필드 이름(name)은 의미 있는 실제 영문 snake_case 키를 사용한다.
    - 금지 예: `<사용자_정의_필드>`, `<field_name>`, `field1` 같은 플레이스홀더 텍스트.
    - 올바른 예: `inquiry`, `ticket_id`, `search_keyword`, `customer_name`.

13. 각 field는 반드시 다음 형식을 따를 것:
    {"name": "<영문_snake_case>", "label": "<한국어 표시명>", "type": "string", "required": true}

14. 대부분의 워크플로우에서 form-start는 1~2개의 핵심 입력 필드면 충분하다.
    불필요하게 많은 필드를 만들지 말 것.

【좋은 예시 — 문의 답변 워크플로우】
  form-start config.fields:
    [{"name": "inquiry", "label": "문의 내용", "type": "string", "required": true}]
  (knowledge 노드가 검색 결과를 "knowledge" 키로 출력하고,
   ai-custom 노드가 답변을 "response" 키로 출력하지만,
   이 키들은 form-start 필드가 아니라 각 노드의 outputData 항목이다.)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【config 세부값 품질 규칙 (실측 오류 방지)】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

15. **API 파라미터 채우기**: api-start/api-call 노드는 사용해야 할 API 명세의
    query/path 파라미터를 `config.defaultParams`에 실제 값으로 채운다.
    사용자 설명에 값이 명시된 경우(예: "status가 신규인") 그 값을 넣는다.
    URL 템플릿 변수({status} 등)를 빈 채로 두지 말 것.
    아래 '가용 재료'에 각 API의 [필수 파라미터] / [선택 파라미터] 목록이 있으니 반드시 참고하라.

16. **API 바디 변수 일치**: api-call(POST) 노드의 경우, 대상 API 명세의 bodyTemplate이
    요구하는 변수명과 정확히 동일한 키가 업스트림 belt에 존재해야 한다.
    아래 '가용 재료'에 각 API의 [body 필요 변수] 목록이 있다.
    예: API가 board_id, response 를 요구하면 업스트림(ai-custom 등)이 같은 이름으로
    출력해야 한다. ai-custom의 inline 출력 키는 `response`임을 기억할 것.

17. **sorter 인스턴스DB 중복차단**: "이미 처리/답변한 것을 건너뛴다"는 요구이면
    sorter rule을 반드시 다음 형태로 만든다:
    {
      "id": "<rule-id>",
      "dataSource": "instance-db",
      "instanceDbId": "<실제 idb-id>",
      "filterTemplate": {"<키>": "{{<키>}}"},
      "condition": "not_exists"
    }
    절대 dataSource:"api" 를 사용하지 말 것. 그리고 not_exists 매칭 항목(신규)이
    `rule-<id>` 핸들로 다음 노드에 연결되어야 하고, 이미 처리된 항목은
    `default` 핸들(미연결=스킵)로 흐른다.
    ⚠️ 스킵 필터(중복 건너뛰기)에는 반드시 `sorter`를 사용한다. `instance-db-lookup`은
    '다른 데이터를 가져와 현재 입력에 병합'할 때만 사용하며, 스킵 필터 목적으로 쓰지 말 것.

17a. **처리 이력 저장 — instance-db-insert**: "처리한 것을 이력으로 남긴다",
    "다음 실행 때 중복 방지" 요구가 있으면 워크플로우 끝(출력 노드 직전 또는 직후)에
    `instance-db-insert` 를 추가하여 처리 키를 저장한다. Stage A 골격에 sorter가 있으면
    이 노드도 함께 포함되어야 한다.

18. **sorter handle 필수 연결**: 모든 sorter rule은 `sourceHandle="rule-<그 rule의 id>"`인
    출력 연결을 반드시 하나 가져야 한다. rule만 만들고 연결을 빠뜨리면 검증기 E8으로 차단됨.

19. **knowledge searchField**: knowledge 노드의 searchField는 반드시 업스트림 데이터에
    실제 존재하는 필드명을 사용한다(예: 문의글이면 title 또는 description).
    임의로 만든 필드명(예: issue_content) 사용 금지.

20. **ai-custom 텍스트 생성 (엄격)**: `ai_node_id`는 커스텀 노드의 **용도(purpose)가 현재 작업과 명백히 일치할 때만** 사용한다.
    - **금지**: 분류(classify)·추출(extract)·라우팅 전용 커스텀 노드를 '답변 작성/요약/생성' 같은 텍스트 생성 작업에 사용하는 것은 절대 금지.
    - **의무**: 의미가 정확히 맞는 커스텀 노드가 없으면 반드시 **inline `config.prompt`(+model, 출력은 `{{response}}`)** 를 사용한다.
    - **금지**: 단지 사용 가능한 커스텀 노드가 존재한다는 이유만으로 가져다 쓰지 말 것.
    - 각 커스텀 노드의 용도는 '가용 재료' 섹션에 명시되어 있다. 반드시 확인하라.
    - inline ai-custom의 출력은 `{response: ...}` 이므로 다운스트림은 `{{response}}`로 참조.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【config 품질 종합 예시 — 문의 자동답변】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  api-start  → config.defaultParams: {status: "신규"}   ← URL ?status={status} 채움
  unpacker   → 배열 항목 개별 처리
  sorter     → rule: {dataSource:"instance-db", instanceDbId:"<실제-id>",
                      filterTemplate:{board_id:"{{board_id}}"}, condition:"not_exists"}
               + connections: [{sourceHandle:"rule-<id>", target: 다음노드}]  ← handle 연결 필수
  knowledge  → searchField: "title"   ← 실제 존재하는 필드명
  ai-custom  → config.prompt: "..."   ← 맞는 커스텀 노드 없으면 inline
               출력: {response: "..."}
  api-call   → POST, body 변수 board_id·response 일치  ← [body 필요 변수] 참고
  instance-db-insert → dataTemplate: {board_id: "{{board_id}}"}  ← 처리이력 저장
"""


async def _stage_b_assemble(
    skeleton: List[Dict],
    catalog_detail: str,
    materials_text: str,
    description: str,
    handler: Any,
) -> tuple[Dict, str]:
    """Stage B: 완전한 워크플로우 draft JSON 생성."""
    skeleton_json = json.dumps(skeleton, ensure_ascii=False, indent=2)
    prompt = f"""사용자 업무 설명:
{description}

## Stage A 골격 (defType + name + purpose)
{skeleton_json}

## 선택된 노드들의 카탈로그 상세 스키마
{catalog_detail}

{materials_text}

위 정보를 바탕으로 완전한 워크플로우 JSON을 출력하세요.
모든 노드를 연결하고, required config를 채우고, 트리거 1개를 포함하세요.

⚠️ 최종 확인: config의 apiDefinitionId, instanceDbId, aiNodeId 값은
반드시 위 '가용 재료' 목록에 명시된 실제 ID만 사용하라.
목록에 없는 임의의 ID(예: 'idb-1a2b3c4d', 'api-xyz')를 지어내는 것은 절대 금지.
해당 재료가 없으면 그 노드 자체를 포함하지 말라.
"""
    req = LLMRequest.simple(
        prompt=prompt,
        system_prompt=_STAGE_B_SYSTEM,
        temperature=0.2,
        max_tokens=3000,
        call_type="workflow_generator_stage_b",
    )
    resp = await handler.chat(req)
    raw = _clean_json(resp.content)

    try:
        draft = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Stage B JSON 파싱 실패: %s | 원문: %s", e, raw[:300])
        # 빈 draft 반환 — Repair 루프에서 잡힘
        draft = {
            "name": "생성 실패 워크플로우",
            "description": "",
            "tags": [],
            "nodes": [],
            "connections": [],
        }

    stage_note = "Stage B 완료: draft 조립"
    return draft, stage_note


# ── Stage R: Refine (수정 모드 전용) ──────────────────────────────────────────

# history에서 최근 N개 메시지만 포함 (토큰 절약)
_MAX_HISTORY_MESSAGES = 6

_STAGE_R_SYSTEM = """당신은 기존 워크플로우를 증분 편집하는 전문가입니다.
반드시 JSON 객체만 출력하세요. 마크다운 코드펜스(```)는 절대 사용하지 마세요.
설명 문장, 인사말 등 JSON 이외의 텍스트를 포함하지 마세요.

출력 형식은 기존 워크플로우와 동일한 JSON 객체입니다:
{
  "name": "<워크플로우 이름>",
  "description": "<설명>",
  "tags": ["<태그>"],
  "nodes": [...],
  "connections": [...]
}

필수 수정 규칙:
1. 기존 노드와 연결을 최대한 보존하라. 사용자가 명시적으로 제거하라고 하지 않은 노드를 임의로 삭제하지 말라.
2. 사용자가 요청한 변경 사항만 적용하라 (노드 추가/제거/수정, 연결 변경 등).
3. 모든 노드는 연결되어야 한다 (고립 노드 금지).
4. 트리거 노드(form-start 또는 api-start)가 정확히 1개 있어야 한다.
5. 카탈로그의 required=True config 필드를 모두 채우세요.
6. config 필드(apiDefinitionId, instanceDbId, aiNodeId)에는 반드시 '가용 재료' 목록의 실제 ID만 사용하라. 임의의 ID를 지어내지 말라.
7. 가용 재료 목록에 없는 재료가 필요한 노드는 생성하지 말라.
8. id 형식: 노드 wn-<8hex>, 연결 wc-<8hex>.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【config 세부값 품질 규칙 (실측 오류 방지)】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

9. **API 파라미터 채우기**: api-start/api-call 노드는 사용해야 할 API 명세의
   query/path 파라미터를 `config.defaultParams`에 실제 값으로 채운다.
   아래 '가용 재료'의 [필수 파라미터] / [선택 파라미터] 목록을 반드시 참고하라.
   URL 템플릿 변수를 빈 채로 두지 말 것.

10. **API 바디 변수 일치**: api-call(POST)의 bodyTemplate 요구 변수명과
    업스트림 출력 키를 정확히 일치시킨다. '가용 재료'의 [body 필요 변수] 참고.
    ai-custom inline 출력 키는 `response`임을 기억할 것.

11. **sorter 인스턴스DB 중복차단**: 중복 건너뛰기 요구이면
    `{dataSource:"instance-db", instanceDbId:"<실제-id>", filterTemplate:{...}, condition:"not_exists"}`
    형태로 만들고 `rule-<id>` 핸들 연결을 반드시 추가한다. dataSource:"api" 금지.

12. **sorter handle 필수 연결**: 모든 sorter rule은 `sourceHandle="rule-<rule의 id>"`인
    출력 연결을 반드시 하나 가져야 한다.

13. **knowledge searchField**: 업스트림에 실제 존재하는 필드명만 사용한다.
    임의 필드명 금지.

14. **ai-custom 텍스트 생성 (엄격)**: `ai_node_id`는 커스텀 노드의 **용도가 현재 작업과 명백히 일치할 때만** 사용한다.
    - **금지**: 분류(classify)·추출(extract)·라우팅 전용 커스텀 노드를 '답변 작성/요약/생성' 텍스트 생성 작업에 사용하는 것은 절대 금지.
    - **의무**: 의미가 정확히 맞는 커스텀 노드가 없으면 반드시 **inline `config.prompt`(+model)** 를 사용한다.
    - **금지**: 단지 사용 가능한 커스텀 노드가 존재한다는 이유만으로 가져다 쓰지 말 것.
    - 각 커스텀 노드의 용도는 '가용 재료' 섹션에 명시되어 있다. 반드시 확인하라.
    - inline 출력은 `{response: ...}`이므로 다운스트림은 `{{response}}`로 참조.
"""


async def _stage_r_refine(
    base_draft: Dict,
    description: str,
    catalog_detail: str,
    materials_text: str,
    handler: Any,
    history: Optional[List] = None,
) -> tuple[Dict, str]:
    """Stage R: 기존 draft를 사용자 요청에 따라 증분 편집."""
    base_draft_json = json.dumps(base_draft, ensure_ascii=False, indent=2)

    # 관련 defType 카탈로그 상세 (기존 노드 타입 + 전체 카탈로그 요약)
    catalog_summary = _build_catalog_summary()

    # history 컨텍스트 구성 (최근 N개만)
    history_text = ""
    if history:
        recent = history[-_MAX_HISTORY_MESSAGES:] if len(history) > _MAX_HISTORY_MESSAGES else history
        history_lines = []
        for msg in recent:
            role = msg.get("role", "user") if isinstance(msg, dict) else getattr(msg, "role", "user")
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            history_lines.append(f"[{role}]: {content}")
        if history_lines:
            history_text = "## 이전 대화 이력\n" + "\n".join(history_lines) + "\n\n"

    prompt = f"""{history_text}## 현재 워크플로우 draft (수정 기준)
{base_draft_json}

## 사용자 수정 요청
{description}

## 범용 노드 카탈로그 (defType: purpose)
{catalog_summary}

## 선택 노드 카탈로그 상세 스키마
{catalog_detail}

{materials_text}

위 수정 요청을 기존 워크플로우에 반영하여 완전한 새 워크플로우 JSON을 출력하세요.
기존에 있던 노드들(특히 트리거 노드, 처리 노드 등)을 보존하면서 요청된 변경만 적용하세요.
명시적으로 제거하라고 하지 않은 노드를 임의로 삭제하지 마세요.

⚠️ 최종 확인: config의 apiDefinitionId, instanceDbId, aiNodeId 값은
반드시 위 '가용 재료' 목록에 명시된 실제 ID만 사용하라.
목록에 없는 임의의 ID를 지어내는 것은 절대 금지.
"""
    req = LLMRequest.simple(
        prompt=prompt,
        system_prompt=_STAGE_R_SYSTEM,
        temperature=0.2,
        max_tokens=3000,
        call_type="workflow_generator_stage_r_refine",
    )
    resp = await handler.chat(req)
    raw = _clean_json(resp.content)

    try:
        draft = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Stage R JSON 파싱 실패: %s | 원문: %s", e, raw[:300])
        # 파싱 실패 시 기존 draft 유지
        draft = base_draft

    stage_note = "Stage R 완료: 기존 draft 증분 편집"
    return draft, stage_note


# ── Stage D: Repair ───────────────────────────────────────────────────────────

_REPAIR_SYSTEM = """당신은 워크플로우 오류 수정 전문가입니다.
반드시 JSON 객체만 출력하세요. 마크다운 코드펜스(```)는 절대 사용하지 마세요.
설명 문장은 절대 포함하지 마세요. 수정된 전체 워크플로우 JSON을 그대로 출력하세요.
config 필드(apiDefinitionId, instanceDbId, aiNodeId)에는 반드시 제공된 유효 ID만 사용하라. 임의의 ID를 지어내지 말라.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【config 세부값 품질 규칙 (실측 오류 방지) — repair에도 동일 적용】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- API 파라미터 채우기: api-start/api-call의 `config.defaultParams`에 query/path 파라미터
  실제 값을 채운다. '가용 재료'의 [필수 파라미터] 참고. URL 변수를 빈 채로 두지 말 것.
- API 바디 변수 일치: api-call(POST) bodyTemplate 요구 변수명과 업스트림 출력 키를
  정확히 일치시킨다. '가용 재료'의 [body 필요 변수] 참고.
  ai-custom inline 출력 키는 `response`임에 주의.
- sorter 인스턴스DB 중복차단: 중복 건너뛰기는
  `{dataSource:"instance-db", instanceDbId:"<실제-id>", filterTemplate:{...}, condition:"not_exists"}`
  + `rule-<id>` 핸들 연결 필수. dataSource:"api" 금지.
- sorter handle 필수 연결: 모든 sorter rule은 `sourceHandle="rule-<rule의 id>"` 연결 필수.
- knowledge searchField: 업스트림 실제 존재 필드명만 사용. 임의 필드명 금지.
- ai-custom 텍스트 생성 (엄격): ai_node_id는 커스텀 노드의 용도가 현재 작업과 명백히 일치할 때만 사용.
  분류(classify)/추출(extract)/라우팅 전용 노드를 답변 작성/요약/생성에 사용하는 것은 절대 금지.
  의미가 정확히 맞는 커스텀 노드가 없으면 반드시 inline config.prompt(+model)를 사용할 것.
  단지 사용 가능한 커스텀 노드가 존재한다는 이유만으로 가져다 쓰지 말 것.
  inline 출력은 `{response: ...}` → 다운스트림은 `{{response}}`로 참조.
"""


async def _stage_d_repair(
    draft: Dict,
    errors: List[Dict],
    handler: Any,
    attempt: int,
    materials: Optional[Dict[str, Any]] = None,
) -> Dict:
    """Stage D: 검증 실패 draft를 LLM에 피드백하여 수정."""
    error_text = "\n".join(
        f"  - [{e.get('code')}] {e.get('message')}" for e in errors
    )
    draft_json = json.dumps(draft, ensure_ascii=False, indent=2)

    # broken-ref 오류가 있으면 유효 ID 목록을 별도 안내
    broken_ref_hint = ""
    if materials is not None:
        broken_ref_hint = _build_broken_ref_hint(errors, materials)

    # 재료 컨텍스트 (repair에도 포함)
    materials_section = ""
    if materials is not None:
        materials_section = "\n" + _materials_summary(materials)

    prompt = f"""아래 워크플로우 JSON에 오류가 있습니다.
오류 목록(시도 #{attempt}):
{error_text}
{broken_ref_hint}
{materials_section}

현재 draft:
{draft_json}

위 오류를 모두 수정한 완전한 워크플로우 JSON을 출력하세요.
- 고립 노드가 있으면 연결을 추가하세요.
- 트리거가 없으면 form-start를 추가하세요.
- 누락된 required config를 채우세요.
- sorter의 handle 분기 누락이 있으면 연결을 추가하세요.
- broken-ref 오류가 있으면 위 유효 ID 목록에서만 ID를 선택하세요. 임의의 ID를 지어내지 마세요.
- 해당 재료(인스턴스DB 등)가 목록에 없으면 그 노드를 제거하세요.
"""
    req = LLMRequest.simple(
        prompt=prompt,
        system_prompt=_REPAIR_SYSTEM,
        temperature=0.1,
        max_tokens=3000,
        call_type="workflow_generator_repair",
    )
    resp = await handler.chat(req)
    raw = _clean_json(resp.content)

    try:
        repaired = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Repair JSON 파싱 실패 (attempt %d): %s", attempt, e)
        repaired = draft  # 파싱 실패 시 원본 유지
    return repaired


# ── 메인 함수 ─────────────────────────────────────────────────────────────────


async def generate_workflow(
    description: str,
    db: AsyncSession,
    mode: str = "create",
    base_workflow_id: Optional[str] = None,
    history: Optional[List] = None,
    base_draft: Optional[Dict] = None,
) -> Dict[str, Any]:
    """자연어 업무 설명으로부터 워크플로우 draft를 단계적으로 생성한다.

    Parameters
    ----------
    description:
        사용자 자연어 업무 설명.
    db:
        AsyncSession — 재료 조회·검증용.
    mode:
        "create" (신규) | "edit"/"refine" (기존 수정).
    base_workflow_id:
        mode="edit"일 때 기준 워크플로우 ID (참고용).
    history:
        대화 이력. 수정 모드에서 프롬프트 컨텍스트에 포함.
    base_draft:
        수정 모드에서 기준이 되는 현재 워크플로우 draft.
        base_draft가 있거나 mode in ("edit","refine")이면 수정 모드로 동작.

    Returns
    -------
    dict:
        {
            "draft": {...},           # 생성된 워크플로우 형태 (name/description/tags/nodes/connections)
            "validation": {...},     # validate_workflow_structure 결과
            "assistantMessage": str, # 사용자에게 전달할 요약 메시지
            "attempts": int,         # repair 루프 시도 횟수
            "stages": [...]          # 각 단계 기록
            "traceId": str,          # 생성 추적 ID
        }

    Raises
    ------
    RuntimeError:
        LLM 핸들러를 가져오지 못한 경우 (게이트웨이 미설정 등).
    """
    stages: List[str] = []
    attempts = 0

    # ── 수정 모드 판정 ──────────────────────────────────────────────────────
    is_refine_mode = bool(base_draft) or mode in ("edit", "refine")

    # ── 생성 추적 trace 초기화 ────────────────────────────────────────────
    trace_id = f"gen-{uuid.uuid4().hex[:8]}"
    trace: Dict[str, Any] = {
        "traceId": trace_id,
        "createdAt": datetime.utcnow().isoformat(),
        "mode": mode,
        # description: 기존 필드 유지(back-compat).
        "description": description,
        # userMessage: 이 turn 에서 사용자가 입력한 메시지(= description 과 동일).
        # 대화 보존용 신규 필드. description 과 의미는 같지만 명시적으로 둔다.
        "userMessage": description,
        # assistantMessage: 사용자에게 회신한 AI 메시지. 최종화 직전에 채운다.
        "assistantMessage": None,
        "baseDraftProvided": base_draft is not None,
        "llmCalls": [],
        "validationHistory": [],
        "finalDraft": None,
        "finalValidation": None,
        "attempts": 0,
        "result": "error",
        "error": None,
    }

    # ── LLM 핸들러 준비 ────────────────────────────────────────────────────
    try:
        _raw_handler = get_llm_handler()
    except Exception as e:
        trace["error"] = str(e)
        append_trace(trace)
        raise RuntimeError(
            f"LLM 게이트웨이를 초기화할 수 없습니다. 환경변수(DEFAULT_LLM_PROVIDER 등)를 확인하세요. 원인: {e}"
        ) from e

    # LLM 호출 추적 프록시로 핸들러를 감싼다
    handler = make_tracing_proxy(_raw_handler)
    # trace["llmCalls"]를 프록시의 llm_calls 리스트와 연결 (같은 객체 참조)
    trace["llmCalls"] = handler.llm_calls

    try:
        # ── 컨텍스트 수집(결정론적) ────────────────────────────────────────
        catalog_summary = _build_catalog_summary()
        materials = await _collect_materials(db)
        materials_text = _materials_summary(materials)
        # 재료 요약 문자 수 기록 (진단용)
        trace["materialsSummaryChars"] = len(materials_text)
        stages.append("컨텍스트 수집 완료")

        if is_refine_mode and base_draft is not None:
            # ── 수정 모드: Stage A(Plan) 생략, Stage R(Refine) 직행 ─────────
            stages.append("수정 모드 진입: Stage A(Plan) 생략")

            # 기존 draft의 defType들 + 전체 카탈로그로 상세 스키마 구성
            existing_def_types = list({
                n.get("definitionType", n.get("defType", ""))
                for n in base_draft.get("nodes", [])
            })
            all_def_types = [e.defType for e in get_catalog()]
            catalog_detail = _build_catalog_detail(list(set(existing_def_types + all_def_types)))

            draft, stage_r_note = await _stage_r_refine(
                base_draft=base_draft,
                description=description,
                catalog_detail=catalog_detail,
                materials_text=materials_text,
                handler=handler,
                history=history,
            )
            stages.append(stage_r_note)
        else:
            # ── 신규 생성 모드: Stage A → Stage B ────────────────────────────
            skeleton, stage_a_note = await _stage_a_plan(
                description=description,
                catalog_summary=catalog_summary,
                materials_text=materials_text,
                handler=handler,
            )
            stages.append(stage_a_note)

            if not skeleton:
                # 골격이 없으면 최소 트리거라도 넣어서 진행
                skeleton = [{"defType": "form-start", "name": "시작", "purpose": "워크플로우 시작"}]
                stages.append("Stage A 결과가 비어 골격을 최소화 (form-start)")

            def_types = [item.get("defType", "") for item in skeleton]
            catalog_detail = _build_catalog_detail(def_types)

            draft, stage_b_note = await _stage_b_assemble(
                skeleton=skeleton,
                catalog_detail=catalog_detail,
                materials_text=materials_text,
                description=description,
                handler=handler,
            )
            stages.append(stage_b_note)

        # draft 기본 구조 보장
        if not isinstance(draft, dict):
            draft = {"name": "생성 실패", "description": "", "tags": [], "nodes": [], "connections": []}

        draft.setdefault("name", "AI 생성 워크플로우")
        draft.setdefault("description", description[:200])
        draft.setdefault("tags", [])
        draft.setdefault("nodes", [])
        draft.setdefault("connections", [])

        # 서버에서 id 보장
        draft["nodes"], draft["connections"] = _ensure_ids(draft["nodes"], draft["connections"])

        # ── sorter 배선 결정론적 정규화 (검증 직전 최종 교정) ─────────────
        draft = _normalize_sorter_wiring(draft)

        # ── Stage C+D: Validate & Repair 루프 ─────────────────────────────
        validation = await validate_workflow_structure(draft["nodes"], draft["connections"], db)
        stages.append(f"Stage C 검증: valid={validation['valid']}, errors={validation['errorCount']}")

        # 검증 이력 기록
        trace["validationHistory"].append({
            "attempt": 0,
            "valid": validation["valid"],
            "errorCount": validation.get("errorCount", 0),
            "warningCount": validation.get("warningCount", 0),
            "errors": validation.get("errors", []),
            "warnings": validation.get("warnings", []),
        })

        while not validation["valid"] and attempts < MAX_REPAIR:
            attempts += 1
            draft = await _stage_d_repair(
                draft=draft,
                errors=validation["errors"],
                handler=handler,
                attempt=attempts,
                materials=materials,
            )
            # id 재보장 (repair 후 누락 방지)
            draft.setdefault("nodes", [])
            draft.setdefault("connections", [])
            draft["nodes"], draft["connections"] = _ensure_ids(draft["nodes"], draft["connections"])

            # sorter 배선 결정론적 정규화 (repair가 다시 망가뜨려도 잡힘)
            draft = _normalize_sorter_wiring(draft)

            validation = await validate_workflow_structure(draft["nodes"], draft["connections"], db)
            stages.append(
                f"Stage D Repair #{attempts}: valid={validation['valid']}, errors={validation['errorCount']}"
            )

            # 각 repair attempt의 검증 결과 기록
            trace["validationHistory"].append({
                "attempt": attempts,
                "valid": validation["valid"],
                "errorCount": validation.get("errorCount", 0),
                "warningCount": validation.get("warningCount", 0),
                "errors": validation.get("errors", []),
                "warnings": validation.get("warnings", []),
            })

        # ── 최종 응답 구성 ──────────────────────────────────────────────────
        # 재료 부재 안내 메시지 구성
        missing_material_notes: List[str] = []
        if not materials.get("instanceDbs"):
            missing_material_notes.append(
                "인스턴스DB가 없어 저장 단계(instance-db-insert/instance-db-lookup)를 생략했습니다. "
                "먼저 인스턴스DB를 등록하세요(POST /api/v1/instance-dbs)."
            )
        if not materials.get("apiDefinitions"):
            # api-call/api-start 노드가 실제로 draft에 있을 때만 경고
            draft_def_types = {n.get("definitionType") for n in draft.get("nodes", [])}
            if draft_def_types & {"api-call", "api-start"}:
                missing_material_notes.append(
                    "API 명세가 없어 api-call/api-start 노드를 사용할 수 없습니다. "
                    "먼저 API 명세를 등록하세요(POST /api/v1/api-definitions)."
                )

        action_word = "수정" if is_refine_mode else "생성"
        save_button_label = "'변경 저장'" if is_refine_mode else "'저장'"
        if validation["valid"]:
            assistant_message = (
                f"워크플로우 '{draft.get('name', '이름 없음')}'이(가) {action_word}되었습니다. "
                f"노드 {len(draft.get('nodes', []))}개, 연결 {len(draft.get('connections', []))}개. "
                f"검토 후 {save_button_label} 버튼을 눌러 저장하세요."
            )
            if missing_material_notes:
                assistant_message += " 참고: " + " / ".join(missing_material_notes)
        else:
            assistant_message = (
                f"워크플로우 초안을 {action_word}했지만 {MAX_REPAIR}회 수정 후에도 "
                f"{validation['errorCount']}개 오류가 남아 있습니다. "
                f"draft를 참고하여 수동으로 수정하거나 설명을 더 구체적으로 바꿔 재시도하세요."
            )
            if missing_material_notes:
                assistant_message += " 참고: " + " / ".join(missing_material_notes)

        # ── trace 최종화 ───────────────────────────────────────────────────
        trace["finalDraft"] = draft
        trace["finalValidation"] = validation
        trace["attempts"] = attempts
        trace["result"] = "valid" if validation["valid"] else "invalid"
        # 사용자에게 회신한 AI 메시지를 trace 에 보존 (대화 복원용).
        trace["assistantMessage"] = assistant_message

        return {
            "draft": draft,
            "validation": validation,
            "assistantMessage": assistant_message,
            "attempts": attempts,
            "stages": stages,
            "traceId": trace_id,
        }

    except Exception as exc:
        # 예외 발생 시에도 trace를 기록
        trace["error"] = str(exc)
        trace["attempts"] = attempts
        trace["result"] = "error"
        raise
    finally:
        # 정상/예외 무관하게 항상 trace를 파일에 기록
        append_trace(trace)


__all__ = ["generate_workflow", "_normalize_sorter_wiring"]
