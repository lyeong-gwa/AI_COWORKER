"""
Knowledge Schema Loader & Validator (Layer 3 — Karpathy v2).

`data/knowledge/_schema.yaml` 의 정책을 로드/캐시하고 검증 함수를 제공한다.
P1 에서는 단위 동작만 보장하며, API 진입점에 wiring (422 강제) 은 P2 의 몫.

설계 근거: `.omc/plans/지식-karpathy-v2.md` §8.2, D9.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
import logging

from ..core.config import settings, _BACKEND_DIR

logger = logging.getLogger(__name__)

# 5종 page_type — `_schema.yaml` 의 키와 정확히 일치해야 한다.
ALLOWED_PAGE_TYPES: Set[str] = {
    "Summary",
    "Entity",
    "Concept",
    "Comparison",
    "Synthesis",
}

# 기본 slug regex (schema 미존재 시 fallback). schema 가 우선.
_DEFAULT_SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
_DEFAULT_MAX_SLUG_LEN = 64

# 다중 서비스 P1 — legacy 카테고리: 신 enum 에는 없지만, 기존 66 페이지/테스트가
# 자유롭게 GET/POST 할 수 있도록 WARN+pass 시킨다. P4 마이그레이션에서 모두
# 신 카테고리로 재태깅되면 이 집합은 비울 수 있다.
LEGACY_CATEGORY_IDS: Set[str] = {
    "codeeyes",
    "ito-portal-operations",
    "plugin-troubleshooting",
}

# 항상 허용되는 service id — 마이그레이션 호환용 sentinel.
SERVICE_UNKNOWN: str = "unknown"


@dataclass
class KnowledgeSchema:
    """`_schema.yaml` 의 메모리 표현."""

    version: int = 3
    schema_owner: str = "human"
    last_curated: str = ""
    services: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    categories: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    page_types: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    link_policy: Dict[str, Any] = field(default_factory=dict)
    filename_policy: Dict[str, Any] = field(default_factory=dict)

    @property
    def category_ids(self) -> Set[str]:
        return set(self.categories.keys())

    @property
    def service_ids(self) -> Set[str]:
        return set(self.services.keys())

    @property
    def slug_pattern(self) -> str:
        return self.filename_policy.get("slug_pattern", _DEFAULT_SLUG_PATTERN)

    @property
    def max_slug_length(self) -> int:
        try:
            return int(self.filename_policy.get("max_slug_length", _DEFAULT_MAX_SLUG_LEN))
        except (TypeError, ValueError):
            return _DEFAULT_MAX_SLUG_LEN


def _schema_path() -> str:
    """`_schema.yaml` 절대경로 — backend/data/knowledge/_schema.yaml."""
    knowledge_dir = settings.KNOWLEDGE_DIR
    if not os.path.isabs(knowledge_dir):
        knowledge_dir = os.path.join(_BACKEND_DIR, knowledge_dir)
    return os.path.join(knowledge_dir, "_schema.yaml")


# ── 캐시 (프로세스당 1회 로드, mtime 기반 무효화) ──────────────────────────
_cache_lock = threading.Lock()
_cached_schema: Optional[KnowledgeSchema] = None
_cached_mtime: float = 0.0


def _parse_schema_dict(raw: Dict[str, Any]) -> KnowledgeSchema:
    """`_schema.yaml` dict → `KnowledgeSchema`."""
    categories_list = raw.get("categories", []) or []
    if not isinstance(categories_list, list):
        categories_list = []
    categories: Dict[str, Dict[str, Any]] = {}
    for cat in categories_list:
        if not isinstance(cat, dict):
            continue
        cid = cat.get("id")
        if not cid:
            continue
        categories[str(cid)] = cat

    services_list = raw.get("services", []) or []
    if not isinstance(services_list, list):
        services_list = []
    services: Dict[str, Dict[str, Any]] = {}
    for svc in services_list:
        if not isinstance(svc, dict):
            continue
        sid = svc.get("id")
        if not sid:
            continue
        services[str(sid)] = svc

    page_types_raw = raw.get("page_types", {}) or {}
    if not isinstance(page_types_raw, dict):
        page_types_raw = {}

    return KnowledgeSchema(
        version=int(raw.get("version", 3) or 3),
        schema_owner=str(raw.get("schema_owner", "human") or "human"),
        last_curated=str(raw.get("last_curated", "") or ""),
        services=services,
        categories=categories,
        page_types={str(k): (v if isinstance(v, dict) else {}) for k, v in page_types_raw.items()},
        link_policy=raw.get("link_policy", {}) or {},
        filename_policy=raw.get("filename_policy", {}) or {},
    )


def load_schema(force: bool = False) -> KnowledgeSchema:
    """`_schema.yaml` 로드. mtime 기반 캐시 무효화.

    파일이 없으면 빈 schema (categories 0) 를 반환한다 — 호출자가 미설정 상태를
    `category_ids` 비어 있음으로 감지하면 된다.
    """
    global _cached_schema, _cached_mtime

    path = _schema_path()
    if not os.path.exists(path):
        with _cache_lock:
            _cached_schema = KnowledgeSchema()
            _cached_mtime = 0.0
        return _cached_schema

    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0.0

    with _cache_lock:
        if not force and _cached_schema is not None and mtime == _cached_mtime:
            return _cached_schema

        try:
            import yaml
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            if not isinstance(raw, dict):
                raw = {}
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"_schema.yaml 로드 실패: {exc}")
            raw = {}

        _cached_schema = _parse_schema_dict(raw)
        _cached_mtime = mtime
        return _cached_schema


def reset_schema_cache() -> None:
    """테스트/운영자 명시 reload 용 (e.g. POST /knowledge/schema/reload — P6)."""
    global _cached_schema, _cached_mtime
    with _cache_lock:
        _cached_schema = None
        _cached_mtime = 0.0


# ── 검증 함수 ──────────────────────────────────────────────────────────────

class SchemaValidationError(ValueError):
    """schema 위반. API 진입점에서 422 로 변환."""

    def __init__(self, field: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.field = field
        self.details = details or {}


def validate_category(category: str, schema: Optional[KnowledgeSchema] = None) -> None:
    """카테고리 id 가 `_schema.yaml` enum 에 존재하는지 검증.

    schema 가 비어 있으면 (file missing) 모든 값 허용 — 부트스트랩 단계 호환.

    **다중 서비스 P1 호환 (WARN 모드):** legacy 카테고리(`codeeyes`,
    `ito-portal-operations`, `plugin-troubleshooting`) 는 신 enum 에 없더라도
    WARN 로그만 남기고 통과한다. P4 마이그레이션 완료 후에는 LEGACY_CATEGORY_IDS
    를 비우면 자동으로 strict 모드로 돌아온다. `faq` 는 신·구 동명이라 일반 enum
    경로로 통과한다.
    """
    s = schema or load_schema()
    if not s.category_ids:
        return  # schema 부재 — soft pass
    if category in s.category_ids:
        return
    if category in LEGACY_CATEGORY_IDS:
        logger.warning(
            "[KNOWLEDGE_SCHEMA] legacy 카테고리 '%s' 사용 — P4 마이그레이션 전까지 호환 통과",
            category,
        )
        return
    raise SchemaValidationError(
        field="category",
        message=f"카테고리 '{category}' 는 _schema.yaml 에 정의되지 않았습니다.",
        details={"allowed": sorted(s.category_ids), "got": category},
    )


def validate_service(service: str, schema: Optional[KnowledgeSchema] = None) -> str:
    """service id 가 `_schema.yaml` services enum 에 존재하는지 검증.

    - `unknown` 은 마이그레이션 sentinel 로 schema 정의 여부와 관계없이 항상 허용.
    - schema 의 `services` 섹션이 비어 있으면 (구 v2 yaml 등) silent pass — 부트스트랩 호환.
    - 그 외 미정의 id 는 `SchemaValidationError` (422 변환은 호출자 책임).

    Returns:
        정규화된 service id (현재는 입력 그대로 반환). 향후 alias 처리 여지.
    """
    s = schema or load_schema()
    sid = (service or "").strip()
    if not sid:
        raise SchemaValidationError(
            field="service",
            message="service 는 비어 있을 수 없습니다.",
            details={"got": service},
        )
    if sid == SERVICE_UNKNOWN:
        return sid
    if not s.service_ids:
        return sid  # schema 에 services 섹션 부재 — soft pass
    if sid not in s.service_ids:
        raise SchemaValidationError(
            field="service",
            message=f"service '{sid}' 는 _schema.yaml services enum 에 정의되지 않았습니다.",
            details={"allowed": sorted(s.service_ids), "got": sid},
        )
    return sid


def list_services(schema: Optional[KnowledgeSchema] = None) -> List[Dict[str, Any]]:
    """`{id, title, description}` 리스트 — UI 사이드바/CLI 보조용."""
    s = schema or load_schema()
    return [
        {
            "id": sid,
            "title": svc.get("title", sid),
            "description": svc.get("description", ""),
        }
        for sid, svc in sorted(s.services.items())
    ]


def validate_page_type(page_type: str, schema: Optional[KnowledgeSchema] = None) -> None:
    """page_type 이 5종 enum 중 하나인지 검증.

    `_schema.yaml` 의 `page_types` 키가 우선이며, 비어 있으면 하드코딩된
    `ALLOWED_PAGE_TYPES` 로 fallback.
    """
    s = schema or load_schema()
    allowed = set(s.page_types.keys()) if s.page_types else ALLOWED_PAGE_TYPES
    if page_type not in allowed:
        raise SchemaValidationError(
            field="page_type",
            message=f"page_type '{page_type}' 가 허용 enum 에 없습니다.",
            details={"allowed": sorted(allowed), "got": page_type},
        )


def validate_slug(slug: str, schema: Optional[KnowledgeSchema] = None) -> None:
    """slug 가 영문 kebab-case 규칙(`^[a-z0-9]+(-[a-z0-9]+)*$`) + 길이 제한을 만족하는지."""
    s = schema or load_schema()
    pattern = s.slug_pattern or _DEFAULT_SLUG_PATTERN
    max_len = s.max_slug_length

    if not slug:
        raise SchemaValidationError(
            field="slug",
            message="slug 는 비어 있을 수 없습니다.",
            details={"got": slug},
        )
    if len(slug) > max_len:
        raise SchemaValidationError(
            field="slug",
            message=f"slug 길이가 {max_len} 자를 초과합니다.",
            details={"got_length": len(slug), "max": max_len},
        )
    if not re.match(pattern, slug):
        raise SchemaValidationError(
            field="slug",
            message=f"slug '{slug}' 가 패턴 {pattern!r} 을 위반합니다 (영문 kebab-case 강제).",
            details={"pattern": pattern, "got": slug},
        )


def list_categories(schema: Optional[KnowledgeSchema] = None) -> List[Dict[str, Any]]:
    """`{id, title, description}` 리스트 — UI/CLI 보조용."""
    s = schema or load_schema()
    return [
        {
            "id": cid,
            "title": cat.get("title", cid),
            "description": cat.get("description", ""),
        }
        for cid, cat in sorted(s.categories.items())
    ]
