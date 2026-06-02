"""워크플로우 데이터 흐름 정적 분석.

실행 없이 input_mapping 경로의 null 리스크를 사전 식별한다.
업스트림 노드의 예상 출력 키와 다음 노드의 input_mapping을 비교해
매핑이 존재하지 않는 키를 참조하는 경우를 경고한다.
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional

from ..core.constants import FIELD_MAPPING_PREFIX, TRIGGER_TYPE_VALUES


# 노드 타입별 출력 키 힌트 (정적 분석용 휴리스틱)
# 실제 실행 결과가 아니므로 100% 정확하지는 않지만, 명백한 매핑 오류를 잡는다.
_NODE_OUTPUT_HINTS: Dict[str, set] = {
    "api-start":          {"status", "data"},
    "api-call":           {"status", "data"},
    "form-start":         set(),          # 폼 필드가 동적
    "manual":             set(),
    "knowledge":          {"results", "query", "topK"},
    "sorter":             {"__sorterHandle"},
    "instance-db-lookup": {"records", "count", "total"},
    "instance-db-insert": {"recordId", "deduped"},
    "mapper":             set(),          # 입력+매핑 결과 동적
    "result":             {"entryId", "data"},
    "markdown-viewer":    {"entryId", "markdown"},
    # AI 노드는 출력이 완전히 동적이므로 힌트 없음
    "ai-custom":          set(),
    "ai-api-router":      set(),
}


def validate_workflow_data_flow(
    workflow_nodes: List[Any],
    workflow_connections: List[Any],
    sample_input: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """워크플로우의 데이터 흐름을 정적으로 분석하여 잠재적 null 리스크를 반환한다.

    Parameters
    ----------
    workflow_nodes:
        WorkflowNode ORM 객체 또는 camelCase dict 목록.
    workflow_connections:
        WorkflowConnection ORM 객체 또는 camelCase dict 목록.
    sample_input:
        워크플로우 트리거 시 전달될 예상 입력 dict. None이면 빈 입력으로 가정.

    Returns
    -------
    {
        "workflowNodeCount": int,
        "issueCount": int,
        "issues": [...],       # 경고 목록
        "hasIssues": bool,
        "recommendation": str,
    }
    """
    # ── 노드·연결 정규화 ─────────────────────────────────────────────────────

    nodes_by_id: Dict[str, Any] = {}
    for n in workflow_nodes:
        nid = _attr(n, "id")
        if nid:
            nodes_by_id[nid] = n

    incoming: Dict[str, List[str]] = defaultdict(list)
    outgoing: Dict[str, List[str]] = defaultdict(list)
    for conn in workflow_connections:
        src = _attr(conn, "source_node_id") or _attr(conn, "sourceNodeId")
        tgt = _attr(conn, "target_node_id") or _attr(conn, "targetNodeId")
        if src and tgt:
            incoming[tgt].append(src)
            outgoing[src].append(tgt)

    # ── 트리거 노드에서 BFS ───────────────────────────────────────────────────

    # 각 노드에 도달 가능한 최상위 키 집합 (passthrough 포함 누적)
    reachable_keys: Dict[str, set] = {}

    trigger_ids = []
    for nid, node in nodes_by_id.items():
        if _attr(node, "definition_type") in TRIGGER_TYPE_VALUES:
            trigger_ids.append(nid)
            init_keys = set(sample_input.keys() if sample_input else [])
            def_type = _attr(node, "definition_type") or ""
            init_keys.update(_NODE_OUTPUT_HINTS.get(def_type, {"status", "data"}))
            reachable_keys[nid] = init_keys

    issues: List[Dict[str, Any]] = []
    visited: set = set()
    queue = list(trigger_ids)

    while queue:
        nid = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)

        node = nodes_by_id.get(nid)
        if not node:
            continue

        # 업스트림 키 병합
        merged: set = set()
        for src_id in incoming.get(nid, []):
            merged.update(reachable_keys.get(src_id, set()))

        # 시작 노드는 이미 initial_keys 설정됨
        if nid not in reachable_keys:
            reachable_keys[nid] = merged

        # input_mapping 분석
        mapping = _attr(node, "input_mapping") or _attr(node, "inputMapping") or {}
        if mapping and merged:
            node_name = _attr(node, "name") or nid
            def_type = _attr(node, "definition_type") or ""
            upstream_names = [
                _attr(nodes_by_id.get(sid), "name") or sid
                for sid in incoming.get(nid, [])
            ]
            for target_key, source_expr in mapping.items():
                if not (isinstance(source_expr, str) and source_expr.startswith(FIELD_MAPPING_PREFIX)):
                    continue
                path = source_expr[len(FIELD_MAPPING_PREFIX):]
                top_key = path.split(".")[0]
                if top_key not in merged:
                    issues.append({
                        "nodeId": nid,
                        "nodeName": node_name,
                        "definitionType": def_type,
                        "targetField": target_key,
                        "sourceExpr": source_expr,
                        "missingKey": top_key,
                        "availableKeys": sorted(merged),
                        "upstreamNodes": upstream_names,
                        "severity": "warning",
                        "message": (
                            f"노드 '{node_name}': '{target_key}' 매핑('{source_expr}')의 "
                            f"최상위 키 '{top_key}'가 업스트림 출력에서 확인되지 않습니다. "
                            f"가용 키: [{', '.join(sorted(merged))}]"
                        ),
                    })

        # 현재 노드 출력 키를 reachable_keys에 추가
        def_type = _attr(node, "definition_type") or ""
        own_keys = _NODE_OUTPUT_HINTS.get(def_type, set())
        reachable_keys[nid] = merged | own_keys

        for next_id in outgoing.get(nid, []):
            if next_id not in visited:
                queue.append(next_id)

    # ── 결과 반환 ─────────────────────────────────────────────────────────────

    recommendation = "데이터 흐름 검증 통과: 잠재적 null 리스크가 감지되지 않았습니다."
    if issues:
        parts = []
        for issue in issues[:3]:
            parts.append(
                f"'{issue['nodeName']}' → '{issue['targetField']}'({issue['sourceExpr']}): "
                f"키 '{issue['missingKey']}' 확인 필요"
            )
        if len(issues) > 3:
            parts.append(f"... 외 {len(issues) - 3}개 더")
        recommendation = " / ".join(parts)

    return {
        "workflowNodeCount": len(nodes_by_id),
        "issueCount": len(issues),
        "issues": issues,
        "hasIssues": bool(issues),
        "recommendation": recommendation,
    }


# ── 내부 유틸 ───────────────────────────────────────────────────────────────

def _attr(obj: Any, name: str) -> Any:
    """ORM 객체 또는 dict 에서 snake_case·camelCase 속성을 안전하게 읽는다."""
    if obj is None:
        return None
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict):
        # camelCase 변환 시도
        camel = _to_camel(name)
        return obj.get(name) or obj.get(camel)
    return None


def _to_camel(snake: str) -> str:
    parts = snake.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])
