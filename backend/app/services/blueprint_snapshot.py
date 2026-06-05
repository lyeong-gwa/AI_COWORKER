"""Self-contained workflow blueprint — material snapshot service.

워크플로우가 **저장 시점의 재료 명세를 노드 config 에 동결(freeze)**하여,
실행 시 라이브 DB 조회 없이 동결된 스펙으로 동작하게 한다 (source-PC 자급 실행).

핵심 정책 (LOCKED):
- **Freeze-once + 수동 재동기화** — 노드가 특정 재료를 처음 참조할 때 1회 캡처하고,
  이후 저장에서는 그대로 보존한다. 노드의 참조 id 가 *바뀐* 경우에만 재캡처한다.
  같은 id 의 스냅샷을 갱신(refresh)하는 것은 명시적 재동기화 액션(후속 Phase)으로만 한다.
- 디스크 스냅샷은 **전체 스펙(auth_config 시크릿 포함)** 을 담는다 — source-PC 런타임에 필요.
  (Export 시 레닥션은 후속 Phase.)
- 스냅샷 대상: API 명세(api-call, api-start), ai-api-router(선택된 apiIds 집합),
  커스텀 AI 노드(ai-custom). 인스턴스DB 는 **메타만**(import 용; 런타임은 라이브 store 사용).
  **지식(knowledge) 은 절대 스냅샷하지 않는다.**

스냅샷 config 키:
- api-call/api-start: ``apiSpecSnapshot``
- ai-api-router:       ``apiSpecSnapshots`` (배열)
- ai-custom:          ``aiNodeSnapshot``
- instance-db-*:      ``instanceDbMeta`` (메타 전용; 런타임 미사용)
- 공통:               ``snapshotAt`` (ISO 문자열), ``snapshotSourceId`` (소스 재료 id)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.routes.export_import import _ai_node_to_export, _api_def_to_export
from ..models.api_definition import ApiDefinition
from ..models.node import AINode


# ── 스냅샷 config 키 상수 ────────────────────────────────────────────────────

API_SPEC_SNAPSHOT_KEY = "apiSpecSnapshot"
API_SPEC_SNAPSHOTS_KEY = "apiSpecSnapshots"
AI_NODE_SNAPSHOT_KEY = "aiNodeSnapshot"
INSTANCE_DB_META_KEY = "instanceDbMeta"
SNAPSHOT_AT_KEY = "snapshotAt"
SNAPSHOT_SOURCE_ID_KEY = "snapshotSourceId"


# ── 필드 프로젝션 헬퍼 ───────────────────────────────────────────────────────


def _project_api_spec(api_def: ApiDefinition) -> Dict[str, Any]:
    """ApiDefinition → apiSpecSnapshot 형태로 프로젝션.

    export_import._api_def_to_export 를 재사용해 동일한 camelCase 직렬화를 보장하고,
    스냅샷 스키마에 정의된 키만 추린다(전체 스펙 — auth_config 시크릿 포함).
    """
    full = _api_def_to_export(api_def)
    return {
        "method": full.get("method"),
        "urlTemplate": full.get("urlTemplate"),
        "headers": full.get("headers"),
        "bodyTemplate": full.get("bodyTemplate"),
        "authType": full.get("authType"),
        "authConfig": full.get("authConfig"),
        "parameters": full.get("parameters"),
        "responseSchema": full.get("responseSchema"),
        "name": full.get("name"),
        "description": full.get("description"),
        # 식별용 — 재동기화/감사에 유용 (스키마 외 부가 정보)
        "id": full.get("id"),
    }


def _project_ai_node_spec(ai_node: AINode) -> Dict[str, Any]:
    """AINode → aiNodeSnapshot 형태로 프로젝션."""
    full = _ai_node_to_export(ai_node)
    return {
        "systemPrompt": full.get("systemPrompt"),
        "userPromptTemplate": full.get("userPromptTemplate"),
        "inputSchema": full.get("inputSchema"),
        "outputSchema": full.get("outputSchema"),
        "outputEnforcement": full.get("outputEnforcement"),
        "llmConfig": full.get("llmConfig"),
        "name": full.get("name"),
        "description": full.get("description"),
        "id": full.get("id"),
    }


def _project_instance_db_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
    """instance_db store meta → instanceDbMeta 형태로 프로젝션(메타 전용)."""
    return {
        "name": meta.get("name"),
        "description": meta.get("description"),
        "tags": meta.get("tags") or [],
        "viewerHints": meta.get("viewerHints") or {},
    }


# ── 단건 스냅샷 함수 ─────────────────────────────────────────────────────────


async def snapshot_api_def(db: AsyncSession, api_def_id: str) -> Optional[Dict[str, Any]]:
    """단일 API 명세를 apiSpecSnapshot dict 로 캡처. 없으면 None."""
    if not api_def_id:
        return None
    result = await db.execute(
        select(ApiDefinition).where(ApiDefinition.id == api_def_id)
    )
    api_def = result.scalar_one_or_none()
    if api_def is None:
        return None
    return _project_api_spec(api_def)


async def snapshot_ai_node(db: AsyncSession, ai_node_id: str) -> Optional[Dict[str, Any]]:
    """단일 커스텀 AI 노드를 aiNodeSnapshot dict 로 캡처. 없으면 None."""
    if not ai_node_id:
        return None
    result = await db.execute(select(AINode).where(AINode.id == ai_node_id))
    ai_node = result.scalar_one_or_none()
    if ai_node is None:
        return None
    return _project_ai_node_spec(ai_node)


async def snapshot_instance_db_meta(idb_id: str) -> Optional[Dict[str, Any]]:
    """인스턴스DB 메타(name/description/tags/viewerHints)만 캡처. 없으면 None."""
    if not idb_id:
        return None
    from .instance_db_store import get_instance_db_store

    store = get_instance_db_store()
    meta = await store.get_meta(idb_id)
    if meta is None:
        return None
    return _project_instance_db_meta(meta)


async def snapshot_ai_router_apis(
    db: AsyncSession, selected_ids: Optional[List[str]]
) -> List[Dict[str, Any]]:
    """ai-api-router 용 API 스냅샷 배열.

    selected_ids 가 주어지면 해당 id 들만(순서 보존), 없으면 현재 활성 API 전체.
    존재하지 않는 id 는 건너뛴다.
    """
    if selected_ids:
        snapshots: List[Dict[str, Any]] = []
        for aid in selected_ids:
            snap = await snapshot_api_def(db, aid)
            if snap is not None:
                snapshots.append(snap)
        return snapshots

    result = await db.execute(
        select(ApiDefinition).where(ApiDefinition.is_active == True)  # noqa: E712
    )
    return [_project_api_spec(d) for d in result.scalars().all()]


# ── 노드별 참조 id 해석 ──────────────────────────────────────────────────────


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """ORM/Pydantic/dict 혼용 안전 접근."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _get_config(node: Any) -> Dict[str, Any]:
    cfg = _attr(node, "config")
    return cfg if isinstance(cfg, dict) else {}


def _set_config(node: Any, cfg: Dict[str, Any]) -> None:
    if isinstance(node, dict):
        node["config"] = cfg
    else:
        setattr(node, "config", cfg)


def _node_def_type(node: Any) -> str:
    return _attr(node, "definitionType") or _attr(node, "definition_type") or ""


def _resolve_api_ref(node: Any, cfg: Dict[str, Any]) -> Optional[str]:
    return cfg.get("apiDefinitionId")


def _resolve_ai_node_ref(node: Any, cfg: Dict[str, Any]) -> Optional[str]:
    # 노드 최상위 aiNodeId(=ai_node_id) 또는 config 내 키 모두 허용
    return (
        _attr(node, "aiNodeId")
        or _attr(node, "ai_node_id")
        or cfg.get("aiNodeId")
        or cfg.get("ai_node_id")
    )


def _resolve_instance_db_ref(node: Any, cfg: Dict[str, Any]) -> Optional[str]:
    return cfg.get("instanceDbId")


def _resolve_router_ids(node: Any, cfg: Dict[str, Any]) -> Optional[List[str]]:
    ids = cfg.get("apiIds")
    if isinstance(ids, list) and ids:
        return [str(x) for x in ids if x]
    return None


def _router_source_signature(selected_ids: Optional[List[str]]) -> str:
    """router 스냅샷의 snapshotSourceId — 선택 id 집합을 결정론적 문자열로.

    apiIds 가 없으면(=활성 전체 사용) ``"*active"`` 표식을 쓴다.
    """
    if not selected_ids:
        return "*active"
    return ",".join(sorted(str(x) for x in selected_ids))


# ── 핵심: freeze-once 임베딩 ─────────────────────────────────────────────────


def _node_identity(node: Any) -> Optional[str]:
    """노드 고유 식별자 — ``force_node_ids`` 매칭용.

    저장된 WorkflowNode 는 ``node_id``(=프론트 nodeId) 와 PK ``id`` 둘 다 가진다.
    재동기화 대상 지정 시 둘 중 하나로 매칭되면 강제 대상으로 본다.
    """
    return _attr(node, "node_id") or _attr(node, "nodeId") or _attr(node, "id")


async def embed_snapshots_into_nodes(
    db: AsyncSession,
    nodes: List[Any],
    force_node_ids: Optional[set] = None,
) -> List[Any]:
    """노드 목록에 freeze-once 스냅샷을 임베딩한다.

    Freeze-once 규칙:
      - 노드에 스냅샷 키가 이미 있고 그 ``snapshotSourceId`` 가 현재 참조 id 와 같으면
        → **변경하지 않고 그대로 둔다**(보존).
      - 그렇지 않으면(키 없음 OR 참조 id 변경됨) → **새로 캡처**하고
        ``snapshotAt``/``snapshotSourceId`` 를 갱신한다.

    멱등(idempotent): 같은 입력으로 두 번 호출해도 결과 동일.
    스냅샷 관련 키 외 다른 config 키는 절대 건드리지 않는다.
    TOLERANT: 참조 재료가 없으면 임베딩을 건너뛴다(예외 없음).

    재동기화(force) — ``force_node_ids`` 에 포함된 노드는 ``snapshotSourceId`` 가
    같더라도 freeze-once 를 우회하고 라이브 재료에서 **강제 재캡처**한다.
    ``force_node_ids`` 가 ``None`` 이면 모든 노드가 정상 freeze-once 경로를 탄다.
    강제 대상 매칭은 ``node_id`` / ``nodeId`` / PK ``id`` 중 하나로 한다.
    """
    captured_at = datetime.utcnow().isoformat()
    force_ids = set(force_node_ids) if force_node_ids else None

    for node in nodes:
        def_type = _node_def_type(node)
        cfg = _get_config(node)
        # 원본 보존을 위해 복사본에 작업 후 재할당 (Pydantic/dict 모두 안전)
        new_cfg = dict(cfg)
        changed = False

        # 강제 재동기화 대상 여부 — 매칭되면 freeze-once 보존 분기를 우회한다.
        forced = force_ids is not None and _node_identity(node) in force_ids

        if def_type in ("api-call", "api-start"):
            ref_id = _resolve_api_ref(node, new_cfg)
            if ref_id:
                if (
                    not forced
                    and API_SPEC_SNAPSHOT_KEY in new_cfg
                    and new_cfg.get(SNAPSHOT_SOURCE_ID_KEY) == ref_id
                ):
                    pass  # freeze-once: 보존
                else:
                    snap = await snapshot_api_def(db, ref_id)
                    if snap is not None:
                        new_cfg[API_SPEC_SNAPSHOT_KEY] = snap
                        new_cfg[SNAPSHOT_AT_KEY] = captured_at
                        new_cfg[SNAPSHOT_SOURCE_ID_KEY] = ref_id
                        changed = True
                    # 재료 없음 → 건너뜀(검증이 별도 처리)

        elif def_type == "ai-api-router":
            selected_ids = _resolve_router_ids(node, new_cfg)
            signature = _router_source_signature(selected_ids)
            if (
                not forced
                and API_SPEC_SNAPSHOTS_KEY in new_cfg
                and new_cfg.get(SNAPSHOT_SOURCE_ID_KEY) == signature
            ):
                pass  # freeze-once: 보존
            else:
                snaps = await snapshot_ai_router_apis(db, selected_ids)
                if snaps:
                    new_cfg[API_SPEC_SNAPSHOTS_KEY] = snaps
                    new_cfg[SNAPSHOT_AT_KEY] = captured_at
                    new_cfg[SNAPSHOT_SOURCE_ID_KEY] = signature
                    changed = True
                # 재료 없음 → 건너뜀

        elif def_type == "ai-custom":
            ref_id = _resolve_ai_node_ref(node, new_cfg)
            if ref_id:
                if (
                    not forced
                    and AI_NODE_SNAPSHOT_KEY in new_cfg
                    and new_cfg.get(SNAPSHOT_SOURCE_ID_KEY) == ref_id
                ):
                    pass  # freeze-once: 보존
                else:
                    snap = await snapshot_ai_node(db, ref_id)
                    if snap is not None:
                        new_cfg[AI_NODE_SNAPSHOT_KEY] = snap
                        new_cfg[SNAPSHOT_AT_KEY] = captured_at
                        new_cfg[SNAPSHOT_SOURCE_ID_KEY] = ref_id
                        changed = True
                    # 재료 없음 → 건너뜀

        elif def_type in ("instance-db-insert", "instance-db-lookup"):
            ref_id = _resolve_instance_db_ref(node, new_cfg)
            if ref_id:
                if (
                    not forced
                    and INSTANCE_DB_META_KEY in new_cfg
                    and new_cfg.get(SNAPSHOT_SOURCE_ID_KEY) == ref_id
                ):
                    pass  # freeze-once: 보존
                else:
                    meta = await snapshot_instance_db_meta(ref_id)
                    if meta is not None:
                        new_cfg[INSTANCE_DB_META_KEY] = meta
                        new_cfg[SNAPSHOT_AT_KEY] = captured_at
                        new_cfg[SNAPSHOT_SOURCE_ID_KEY] = ref_id
                        changed = True
                    # 재료 없음 → 건너뜀

        if changed:
            _set_config(node, new_cfg)

    return nodes
