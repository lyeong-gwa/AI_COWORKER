"""결정론적 워크플로우 구조 검증기.

생성·수정 시점에 워크플로우의 구조적 무결성을 검사하여
문제 있는 워크플로우가 저장되는 것을 방지한다.

반환 형식:
    {
        "valid": bool,
        "errorCount": int,
        "warningCount": int,
        "errors": [ {code, severity, nodeId, nodeName, message}, ... ],
        "warnings": [ {code, severity, nodeId, nodeName, message}, ... ],
    }
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.constants import TRIGGER_TYPE_VALUES
from ..nodes.catalog import get_entry
from ..services.flow_validator import validate_workflow_data_flow, _attr


# ── 내부 유틸 ───────────────────────────────────────────────────────────────


def _node_id(node: Any) -> Optional[str]:
    return _attr(node, "id")


def _node_name(node: Any) -> Optional[str]:
    return _attr(node, "name")


def _def_type(node: Any) -> str:
    return _attr(node, "definition_type") or _attr(node, "definitionType") or ""


def _node_config(node: Any) -> Dict[str, Any]:
    return _attr(node, "config") or {}


def _node_config_overrides(node: Any) -> Dict[str, Any]:
    return _attr(node, "config_overrides") or _attr(node, "configOverrides") or {}


def _conn_src(conn: Any) -> Optional[str]:
    return _attr(conn, "source_node_id") or _attr(conn, "sourceNodeId")


def _conn_tgt(conn: Any) -> Optional[str]:
    return _attr(conn, "target_node_id") or _attr(conn, "targetNodeId")


def _conn_src_handle(conn: Any) -> Optional[str]:
    return _attr(conn, "source_handle") or _attr(conn, "sourceHandle")


def _make_issue(
    code: str,
    severity: str,
    message: str,
    node_id: Optional[str] = None,
    node_name: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "nodeId": node_id,
        "nodeName": node_name,
        "message": message,
    }


# 출력 노드 타입 — dead-end (W3) 판별 시 리프여도 경고하지 않는 타입
_OUTPUT_DEF_TYPES = {"result", "markdown-viewer", "instance-db-insert"}


async def validate_workflow_structure(
    nodes: List[Any],
    connections: List[Any],
    db: AsyncSession,
) -> Dict[str, Any]:
    """워크플로우 구조를 검사하고 오류/경고 목록을 반환한다.

    Parameters
    ----------
    nodes:
        WorkflowNodeCreate / WorkflowNode ORM / camelCase dict 혼용 허용.
    connections:
        WorkflowConnectionCreate / WorkflowConnection ORM / camelCase dict 혼용 허용.
    db:
        AsyncSession — 외부 참조(ApiDefinition, AINode 등) 조회용.

    Returns
    -------
    dict:
        valid, errorCount, warningCount, errors, warnings
    """
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    # ── 노드·연결 인덱스 구축 ────────────────────────────────────────────────

    nodes_by_id: Dict[str, Any] = {}
    for n in nodes:
        nid = _node_id(n)
        if nid:
            nodes_by_id[nid] = n

    node_ids: Set[str] = set(nodes_by_id.keys())

    # 방향 그래프: outgoing[src] = [tgt, ...], incoming[tgt] = [src, ...]
    outgoing: Dict[str, List[str]] = defaultdict(list)
    incoming: Dict[str, List[str]] = defaultdict(list)
    # sourceHandle 목록: outgoing_handles[src] = [(tgt, handle), ...]
    outgoing_handles: Dict[str, List[tuple]] = defaultdict(list)

    for conn in connections:
        src = _conn_src(conn)
        tgt = _conn_tgt(conn)
        handle = _conn_src_handle(conn)

        # E1: dangling-edge — 엣지의 노드가 없음
        dangling = False
        if src and src not in node_ids:
            errors.append(_make_issue(
                "dangling-edge",
                "error",
                f"연결선의 sourceNodeId '{src}'가 노드 목록에 없습니다.",
            ))
            dangling = True
        if tgt and tgt not in node_ids:
            errors.append(_make_issue(
                "dangling-edge",
                "error",
                f"연결선의 targetNodeId '{tgt}'가 노드 목록에 없습니다.",
            ))
            dangling = True

        if not dangling and src and tgt:
            outgoing[src].append(tgt)
            incoming[tgt].append(src)
            outgoing_handles[src].append((tgt, handle))

    # ── 트리거 노드 식별 ─────────────────────────────────────────────────────

    trigger_ids: List[str] = []
    for nid, node in nodes_by_id.items():
        if _def_type(node) in TRIGGER_TYPE_VALUES:
            trigger_ids.append(nid)

    # ── 개별 규칙 검사 ───────────────────────────────────────────────────────

    # E2: disconnected-node — 노드 2개 이상인데 연결선이 전혀 없는 노드
    if len(nodes_by_id) >= 2:
        for nid, node in nodes_by_id.items():
            if len(outgoing[nid]) == 0 and len(incoming[nid]) == 0:
                errors.append(_make_issue(
                    "disconnected-node",
                    "error",
                    f"노드 '{_node_name(node) or nid}'은 다른 노드와 연결되지 않은 고립 노드입니다.",
                    node_id=nid,
                    node_name=_node_name(node),
                ))

    # E3: no-trigger — 트리거 노드 없음
    if not trigger_ids:
        errors.append(_make_issue(
            "no-trigger",
            "error",
            "워크플로우에 트리거 노드(form-start, api-start 등)가 없습니다.",
        ))

    # BFS: 트리거에서 도달 가능한 노드 집합 계산
    reachable: Set[str] = set()
    if trigger_ids:
        queue: deque = deque(trigger_ids)
        reachable.update(trigger_ids)
        while queue:
            cur = queue.popleft()
            for nxt in outgoing[cur]:
                if nxt not in reachable:
                    reachable.add(nxt)
                    queue.append(nxt)

    # E4: unreachable — 트리거에서 도달 못 한 비트리거 노드
    e4_nodes: Set[str] = set()
    for nid, node in nodes_by_id.items():
        if nid not in trigger_ids and nid not in reachable:
            e4_nodes.add(nid)
            errors.append(_make_issue(
                "unreachable",
                "error",
                f"노드 '{_node_name(node) or nid}'은 트리거에서 도달할 수 없습니다.",
                node_id=nid,
                node_name=_node_name(node),
            ))

    # E5/E6/E7/E8: 노드별 상세 검사
    # DB 참조 조회에 필요한 import는 함수 내부에서 lazy하게 수행
    from sqlalchemy import select as sa_select
    from ..models.api_definition import ApiDefinition
    from ..models.node import AINode

    # 워크플로우 내 노드 id 집합 (E7 mapper/sorter 참조용)
    workflow_node_ids = node_ids

    for nid, node in nodes_by_id.items():
        def_type = _def_type(node)
        node_name = _node_name(node)
        cfg = _node_config(node)
        cfg_overrides = _node_config_overrides(node)

        # config 병합: config_overrides가 config를 덮어씀
        merged_cfg = {**cfg, **cfg_overrides}

        # E5: unknown-deftype
        entry = get_entry(def_type)
        if entry is None:
            errors.append(_make_issue(
                "unknown-deftype",
                "error",
                f"노드 '{node_name or nid}'의 definitionType '{def_type}'이 카탈로그에 없습니다.",
                node_id=nid,
                node_name=node_name,
            ))
            # 카탈로그가 없으면 이후 config 검사 불가
            continue

        # E6: missing-config — required=True 필드가 비어 있음
        for field in entry.config:
            if not field.required:
                continue
            val = merged_cfg.get(field.name)
            is_empty = val is None or val == "" or val == [] or val == {}
            if is_empty:
                errors.append(_make_issue(
                    "missing-config",
                    "error",
                    (
                        f"노드 '{node_name or nid}'의 필수 설정 '{field.name}'이 "
                        f"누락되거나 비어 있습니다."
                    ),
                    node_id=nid,
                    node_name=node_name,
                ))

        # E7: broken-ref — 설정 내 참조 ID가 실제로 없음
        await _check_broken_refs(
            nid, node_name, def_type, merged_cfg, workflow_node_ids,
            db, errors,
        )

        # E8: sorter-handle 검사
        if def_type == "sorter":
            _check_sorter_handles(
                nid, node_name, merged_cfg, outgoing_handles[nid], errors
            )

        # W3: dead-end — 출력 계열이 아닌데 outgoing이 없는 리프
        if def_type not in _OUTPUT_DEF_TYPES and len(outgoing[nid]) == 0:
            # 트리거 단독(1개)이고 트리거 자체가 리프인 경우는 허용
            if not (nid in trigger_ids and len(nodes_by_id) == 1):
                warnings.append(_make_issue(
                    "dead-end",
                    "warning",
                    (
                        f"노드 '{node_name or nid}'은 출력 노드가 아닌데 "
                        f"연결된 다음 노드가 없습니다."
                    ),
                    node_id=nid,
                    node_name=node_name,
                ))

    # E9: cycle — DFS/위상정렬로 순환 감지
    cycle_node = _detect_cycle(nodes_by_id, outgoing)
    if cycle_node:
        nid = cycle_node
        errors.append(_make_issue(
            "cycle",
            "error",
            f"워크플로우 연결 그래프에 순환이 존재합니다 (노드 '{_node_name(nodes_by_id.get(nid)) or nid}' 포함).",
            node_id=nid,
            node_name=_node_name(nodes_by_id.get(nid)),
        ))

    # W1: mapping-null — flow_validator 재사용
    try:
        flow_result = validate_workflow_data_flow(nodes, connections, sample_input=None)
        for issue in flow_result.get("issues", []):
            warnings.append(_make_issue(
                "mapping-null",
                "warning",
                issue.get("message", "input_mapping 경로 null 리스크"),
                node_id=issue.get("nodeId"),
                node_name=issue.get("nodeName"),
            ))
    except Exception:
        pass  # 분석 실패 시 경고 생략

    # W2: type-mismatch — 카탈로그 producesArray 기반 힌트
    for nid, node in nodes_by_id.items():
        def_type = _def_type(node)
        node_name = _node_name(node)
        entry = get_entry(def_type)
        if entry is None:
            continue
        cfg = _node_config(node)
        cfg_overrides = _node_config_overrides(node)
        merged_cfg = {**cfg, **cfg_overrides}

        # unpacker: arrayField가 가리키는 업스트림 출력이 array 계열인지 확인
        if def_type == "unpacker":
            array_field = merged_cfg.get("arrayField", "")
            # 업스트림 노드 중 producesArray=False인 노드만 있으면 경고
            upstream_ids = incoming.get(nid, [])
            if upstream_ids and array_field:
                all_non_array = all(
                    not _upstream_produces_array(nodes_by_id.get(uid))
                    for uid in upstream_ids
                    if nodes_by_id.get(uid)
                )
                if all_non_array:
                    warnings.append(_make_issue(
                        "type-mismatch",
                        "warning",
                        (
                            f"unpacker 노드 '{node_name or nid}'의 arrayField='{array_field}'가 "
                            f"가리키는 업스트림 노드가 배열을 출력하지 않을 수 있습니다."
                        ),
                        node_id=nid,
                        node_name=node_name,
                    ))

    # W4: subgraph — 트리거에서 도달 가능한 집합 외에 추가 분리 컴포넌트
    # E4가 이미 잡은 노드는 W4에서 제외
    non_reachable = node_ids - reachable - e4_nodes
    if non_reachable and reachable:
        # 분리된 컴포넌트 탐색 (E4에서 이미 보고한 노드 제외 후)
        # 실제로 non_reachable 중 연결된 그룹이 따로 있으면 W4
        subgraph_groups = _find_components(non_reachable, outgoing, incoming)
        for group in subgraph_groups:
            sample_nid = next(iter(group))
            sample_name = _node_name(nodes_by_id.get(sample_nid))
            warnings.append(_make_issue(
                "subgraph",
                "warning",
                (
                    f"트리거에서 도달할 수 없는 분리된 서브그래프가 있습니다 "
                    f"(노드 {len(group)}개, 예: '{sample_name or sample_nid}')."
                ),
                node_id=sample_nid,
                node_name=sample_name,
            ))

    return {
        "valid": len(errors) == 0,
        "errorCount": len(errors),
        "warningCount": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }


# ── 보조 함수들 ─────────────────────────────────────────────────────────────


def _upstream_produces_array(node: Any) -> bool:
    """업스트림 노드가 배열을 출력하는지 카탈로그 힌트로 판단."""
    if node is None:
        return False
    def_type = _def_type(node)
    entry = get_entry(def_type)
    if entry is None:
        return False
    return entry.producesArray


async def _check_broken_refs(
    nid: str,
    node_name: Optional[str],
    def_type: str,
    merged_cfg: Dict[str, Any],
    workflow_node_ids: Set[str],
    db: AsyncSession,
    errors: List[Dict[str, Any]],
) -> None:
    """E7: config 내 참조 ID가 실제로 존재하는지 확인."""
    from sqlalchemy import select as sa_select
    from ..models.api_definition import ApiDefinition
    from ..models.node import AINode

    # apiDefinitionId 참조 (api-start, api-call 노드)
    # 동결 스냅샷(apiSpecSnapshot)이 있으면 라이브 재료가 없어도 자급 실행 가능하므로 broken-ref 보고 생략.
    if def_type in ("api-start", "api-call") and not merged_cfg.get("apiSpecSnapshot"):
        api_def_id = merged_cfg.get("apiDefinitionId")
        if api_def_id:
            result = await db.execute(
                sa_select(ApiDefinition.id).where(ApiDefinition.id == api_def_id)
            )
            if result.scalar_one_or_none() is None:
                errors.append(_make_issue(
                    "broken-ref",
                    "error",
                    (
                        f"노드 '{node_name or nid}'의 apiDefinitionId '{api_def_id}'가 "
                        f"등록된 API 명세에 없습니다."
                    ),
                    node_id=nid,
                    node_name=node_name,
                ))

    # ai_node_id 참조 (ai-custom 노드)
    # 동결 스냅샷(aiNodeSnapshot)이 있으면 라이브 재료가 없어도 자급 실행 가능하므로 broken-ref 보고 생략.
    if def_type == "ai-custom" and not merged_cfg.get("aiNodeSnapshot"):
        ai_node_id = merged_cfg.get("ai_node_id") or merged_cfg.get("aiNodeId")
        if ai_node_id:
            result = await db.execute(
                sa_select(AINode.id).where(AINode.id == ai_node_id)
            )
            if result.scalar_one_or_none() is None:
                errors.append(_make_issue(
                    "broken-ref",
                    "error",
                    (
                        f"노드 '{node_name or nid}'의 ai_node_id '{ai_node_id}'가 "
                        f"등록된 AI 노드에 없습니다."
                    ),
                    node_id=nid,
                    node_name=node_name,
                ))

    # instanceDbId 참조 (instance-db-insert, instance-db-lookup)
    if def_type in ("instance-db-insert", "instance-db-lookup"):
        idb_id = merged_cfg.get("instanceDbId")
        if idb_id:
            from ..services.instance_db_store import get_instance_db_store
            store = get_instance_db_store()
            meta = store._read_json(store._meta_path(idb_id))
            if meta is None:
                errors.append(_make_issue(
                    "broken-ref",
                    "error",
                    (
                        f"노드 '{node_name or nid}'의 instanceDbId '{idb_id}'가 "
                        f"존재하지 않는 인스턴스DB입니다."
                    ),
                    node_id=nid,
                    node_name=node_name,
                ))

    # sorter 노드: dedup.warehouseNodeId가 같은 워크플로우 내 노드 id인지 확인
    if def_type == "sorter":
        dedup = merged_cfg.get("dedup") or {}
        if isinstance(dedup, dict) and dedup.get("enabled"):
            wh_node_id = dedup.get("warehouseNodeId")
            if wh_node_id and wh_node_id not in workflow_node_ids:
                errors.append(_make_issue(
                    "broken-ref",
                    "error",
                    (
                        f"sorter 노드 '{node_name or nid}'의 dedup.warehouseNodeId "
                        f"'{wh_node_id}'가 같은 워크플로우의 노드 id에 없습니다."
                    ),
                    node_id=nid,
                    node_name=node_name,
                ))
        # rules 내 instance-db dataSource의 instanceDbId 확인
        for rule in merged_cfg.get("rules", []):
            if (rule.get("dataSource") or "input").lower() == "instance-db":
                rule_idb_id = rule.get("instanceDbId")
                if rule_idb_id:
                    from ..services.instance_db_store import get_instance_db_store
                    store = get_instance_db_store()
                    meta = store._read_json(store._meta_path(rule_idb_id))
                    if meta is None:
                        errors.append(_make_issue(
                            "broken-ref",
                            "error",
                            (
                                f"sorter 노드 '{node_name or nid}'의 rule instanceDbId "
                                f"'{rule_idb_id}'가 존재하지 않는 인스턴스DB입니다."
                            ),
                            node_id=nid,
                            node_name=node_name,
                        ))

    # mapper 노드: warehouseNodeId가 같은 워크플로우 내 노드 id인지 확인
    if def_type == "mapper":
        wh_node_id = merged_cfg.get("warehouseNodeId")
        if wh_node_id and wh_node_id not in workflow_node_ids:
            errors.append(_make_issue(
                "broken-ref",
                "error",
                (
                    f"mapper 노드 '{node_name or nid}'의 warehouseNodeId "
                    f"'{wh_node_id}'가 같은 워크플로우의 노드 id에 없습니다."
                ),
                node_id=nid,
                node_name=node_name,
            ))


def _check_sorter_handles(
    nid: str,
    node_name: Optional[str],
    merged_cfg: Dict[str, Any],
    out_handles: List[tuple],  # [(tgt_id, handle_str), ...]
    errors: List[Dict[str, Any]],
) -> None:
    """E8: sorter 노드의 출력 엣지 sourceHandle 유효성 검사."""
    rules = merged_cfg.get("rules", [])
    rule_ids = [r.get("id") for r in rules if r.get("id")]
    valid_handles: Set[str] = {f"rule-{rid}" for rid in rule_ids}
    valid_handles.add("default")
    valid_handles.add("__skip__")  # BeltKey.SORTER_HANDLE skip 값

    for tgt_id, handle in out_handles:
        if handle is not None and handle not in valid_handles:
            errors.append(_make_issue(
                "sorter-handle",
                "error",
                (
                    f"sorter 노드 '{node_name or nid}'의 출력 엣지 sourceHandle "
                    f"'{handle}'이 유효하지 않습니다. "
                    f"허용: {sorted(valid_handles)}"
                ),
                node_id=nid,
                node_name=node_name,
            ))

    # 각 rule id에 대응하는 출력 엣지가 없으면 error (분기 누락)
    used_handles = {h for _, h in out_handles if h}
    for rid in rule_ids:
        expected_handle = f"rule-{rid}"
        if expected_handle not in used_handles:
            errors.append(_make_issue(
                "sorter-handle",
                "error",
                (
                    f"sorter 노드 '{node_name or nid}'의 rule id '{rid}'에 대한 "
                    f"출력 엣지(sourceHandle='rule-{rid}')가 없습니다 (분기 누락)."
                ),
                node_id=nid,
                node_name=node_name,
            ))


def _detect_cycle(
    nodes_by_id: Dict[str, Any],
    outgoing: Dict[str, List[str]],
) -> Optional[str]:
    """DFS 기반 순환 감지. 순환에 속한 노드 id 하나를 반환, 없으면 None."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in nodes_by_id}

    cycle_found: List[Optional[str]] = [None]

    def dfs(v: str) -> None:
        if cycle_found[0]:
            return
        color[v] = GRAY
        for w in outgoing.get(v, []):
            if w not in color:
                continue
            if color[w] == GRAY:
                cycle_found[0] = w
                return
            if color[w] == WHITE:
                dfs(w)
                if cycle_found[0]:
                    return
        color[v] = BLACK

    for nid in list(nodes_by_id.keys()):
        if color.get(nid, WHITE) == WHITE:
            dfs(nid)
            if cycle_found[0]:
                break

    return cycle_found[0]


def _find_components(
    node_subset: Set[str],
    outgoing: Dict[str, List[str]],
    incoming: Dict[str, List[str]],
) -> List[Set[str]]:
    """주어진 노드 집합 내에서 연결된 컴포넌트들을 반환 (방향 무관)."""
    visited: Set[str] = set()
    components: List[Set[str]] = []

    for start in node_subset:
        if start in visited:
            continue
        # BFS (무방향)
        component: Set[str] = set()
        queue: deque = deque([start])
        while queue:
            cur = queue.popleft()
            if cur in visited or cur not in node_subset:
                continue
            visited.add(cur)
            component.add(cur)
            for nxt in outgoing.get(cur, []):
                if nxt in node_subset and nxt not in visited:
                    queue.append(nxt)
            for prv in incoming.get(cur, []):
                if prv in node_subset and prv not in visited:
                    queue.append(prv)
        if component:
            components.append(component)

    return components


__all__ = ["validate_workflow_structure"]
