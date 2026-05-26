"""
Knowledge File Service

MD 파일 기반 지식 문서 관리 서비스
- YAML frontmatter + 마크다운 본문
- 파일명(확장자 제외) = 문서 ID
- data/knowledge/ 디렉토리에 저장
"""

import os
import re
import hashlib
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from ..core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeFileDoc:
    """파일 기반 지식 문서.

    Karpathy v2 확장 (`.omc/plans/지식-karpathy-v2.md` §5.1):
      - `page_type` : Summary | Entity | Concept | Comparison | Synthesis
      - `version`   : PUT 마다 +1
      - `links`     : `[[...]]` 파싱 결과 id 정규화 목록
      - `raw_source_id` : RawSource FK (없으면 None)

    다중 서비스 v3 확장 (`.omc/plans/지식-multi-service.md` §5.2):
      - `service` : `_schema.yaml` services enum id. legacy 페이지는 default `"unknown"`.

    하위호환: 기존 archive 파일은 frontmatter 에 위 필드가 없으므로 default 가 사용된다.
    P2 에서 API 진입점에서 enum 강제 검증을 wiring 한다.
    """
    id: str
    title: str
    content: str
    category: str = ""
    service: str = "unknown"  # NEW (multi-service v3)
    page_type: str = "Summary"  # NEW (v2)
    tags: List[str] = field(default_factory=list)
    source: str = ""
    raw_source_id: Optional[str] = None  # NEW (v2)
    version: int = 1  # NEW (v2)
    links: List[str] = field(default_factory=list)  # NEW (v2)
    created: str = ""
    updated: str = ""
    content_hash: str = ""
    sync_status: str = "not_synced"  # synced | modified | not_synced
    extra_metadata: Dict[str, Any] = field(default_factory=dict)


def _knowledge_dir() -> str:
    """지식 문서 디렉토리 경로 (backend/ 기준 해석)"""
    from ..core.config import _BACKEND_DIR
    d = settings.KNOWLEDGE_DIR
    if not os.path.isabs(d):
        d = os.path.join(_BACKEND_DIR, d)
    os.makedirs(d, exist_ok=True)
    return d


def _sanitize_filename(name: str) -> str:
    """파일명에 사용할 수 없는 문자 제거"""
    # 공백을 하이픈으로 변환, 특수문자 제거
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.strip()
    return name


def compute_hash(content: str) -> str:
    """MD5 해시 계산"""
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def parse_frontmatter(raw: str) -> tuple[Dict[str, Any], str]:
    """YAML frontmatter 파싱

    Returns:
        (metadata_dict, body_text)
    """
    import yaml

    raw = raw.strip()
    if not raw.startswith('---'):
        return {}, raw

    # Find closing ---
    end_idx = raw.find('---', 3)
    if end_idx == -1:
        return {}, raw

    yaml_str = raw[3:end_idx].strip()
    body = raw[end_idx + 3:].strip()

    try:
        metadata = yaml.safe_load(yaml_str) or {}
    except Exception:
        metadata = {}

    return metadata, body


def build_md_file(
    title: str,
    content: str,
    category: str = "",
    tags: Optional[List[str]] = None,
    source: str = "",
    created: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
    *,
    page_type: Optional[str] = None,
    version: Optional[int] = None,
    links: Optional[List[str]] = None,
    raw_source_id: Optional[str] = None,
    service: Optional[str] = None,
) -> str:
    """YAML frontmatter + 마크다운 본문 생성.

    Karpathy v2 신규 필드는 명시 지정 시 frontmatter 에 추가된다.
    `extra_metadata` 안에 동일 키가 있어도 명시 인자가 우선한다.

    다중 서비스 v3: `service` 가 None 이 아니면 frontmatter 에 보존. extra_metadata
    안의 동일 키는 명시 인자에 의해 덮어쓰여진다.
    """
    import yaml

    now = datetime.utcnow().isoformat()

    metadata: Dict[str, Any] = {
        "title": title,
        "category": category or "",
        "tags": tags or [],
        "source": source or "",
        "created": created or now,
    }

    # v2 신규 필드 — None 이 아니면 항상 frontmatter 에 보존.
    if page_type is not None:
        metadata["page_type"] = page_type
    if version is not None:
        metadata["version"] = int(version)
    if links is not None:
        metadata["links"] = list(links)
    if raw_source_id is not None:
        metadata["raw_source_id"] = raw_source_id
    # 다중 서비스 v3 — service 가 명시되면 frontmatter 에 보존.
    if service is not None:
        metadata["service"] = str(service)

    # 비표준 메타데이터 병합 (api 등) — 단 표준 키는 위에서 이미 결정됨.
    if extra_metadata:
        for k, v in extra_metadata.items():
            if k in {"page_type", "version", "links", "raw_source_id", "service"}:
                # 명시 인자가 우선이므로 extra 의 동일 키는 무시
                continue
            metadata[k] = v

    yaml_str = yaml.dump(metadata, allow_unicode=True, default_flow_style=False, sort_keys=False).strip()

    return f"---\n{yaml_str}\n---\n\n{content}"


def list_md_files(chroma_hashes: Optional[Dict[str, str]] = None) -> List[KnowledgeFileDoc]:
    """MD 파일 목록 조회 + 동기화 상태 판별.

    Karpathy v2 디렉토리 구조 호환:
      - `_` 로 시작하는 파일/디렉토리는 메타(`_schema.yaml`, `_log.md`, `_index-*.md`,
        `_lint-report.md`, `_lint-history/`) 이므로 제외.
      - 카테고리 서브디렉토리(`{category}/{slug}.md`) 재귀 스캔. 페이지 id 는
        `{category}/{slug}` 가 된다. flat 파일(legacy 호환) 도 동작.
    """
    knowledge_dir = _knowledge_dir()
    docs = []

    if chroma_hashes is None:
        chroma_hashes = {}

    # (relative_id, absolute_filepath) 페어를 수집해서 일괄 처리
    candidates: List[tuple[str, str]] = []
    for entry in sorted(os.listdir(knowledge_dir)):
        if entry.startswith('_') or entry.startswith('.'):
            # 메타 파일/디렉토리 (_schema.yaml, _log.md, _index-*.md, _lint-history/) 제외
            continue
        full = os.path.join(knowledge_dir, entry)
        if os.path.isdir(full):
            # 카테고리 서브디렉토리 — `{category}/{slug}` id 형식으로 수집
            category = entry
            for sub in sorted(os.listdir(full)):
                if sub.startswith('_') or sub.startswith('.'):
                    continue
                if not sub.endswith('.md'):
                    continue
                slug = sub[:-3]
                candidates.append((f"{category}/{slug}", os.path.join(full, sub)))
        elif entry.endswith('.md'):
            doc_id_legacy = entry[:-3]
            candidates.append((doc_id_legacy, full))

    for doc_id, filepath in candidates:

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw = f.read()
        except Exception as e:
            logger.warning(f"파일 읽기 실패: {filepath} - {e}")
            continue

        metadata, body = parse_frontmatter(raw)
        content_hash = compute_hash(body)

        # 동기화 상태 판별
        if doc_id in chroma_hashes:
            if chroma_hashes[doc_id] == content_hash:
                sync_status = "synced"
            else:
                sync_status = "modified"
        else:
            sync_status = "not_synced"

        # 파일 시스템에서 시간 정보 가져오기
        stat = os.stat(filepath)
        file_created = metadata.get("created", datetime.fromtimestamp(stat.st_ctime).isoformat())
        file_updated = datetime.fromtimestamp(stat.st_mtime).isoformat()

        tags_raw = metadata.get("tags", [])
        if isinstance(tags_raw, str):
            tags_raw = [t.strip() for t in tags_raw.split(",") if t.strip()]

        # 비표준 키 추출 (standard keys 제외 — v2 + multi-service v3 신규 필드 포함)
        _STANDARD_KEYS = {
            "title", "category", "tags", "source", "created",
            "page_type", "version", "links", "raw_source_id",
            "service",
        }
        extra_meta = {k: v for k, v in metadata.items() if k not in _STANDARD_KEYS}

        # v2 신규 필드 (legacy 파일에는 없으므로 default 사용)
        page_type = metadata.get("page_type", "Summary") or "Summary"
        version_raw = metadata.get("version", 1)
        try:
            version = int(version_raw)
        except (TypeError, ValueError):
            version = 1
        links_raw = metadata.get("links", [])
        if isinstance(links_raw, str):
            links_raw = [s.strip() for s in links_raw.split(",") if s.strip()]
        elif not isinstance(links_raw, list):
            links_raw = []
        raw_source_id = metadata.get("raw_source_id") or None

        # multi-service v3 — legacy 파일에 service 필드가 없으면 "unknown" default.
        service_raw = metadata.get("service")
        service_val = str(service_raw).strip() if service_raw else "unknown"
        if not service_val:
            service_val = "unknown"

        docs.append(KnowledgeFileDoc(
            id=doc_id,
            title=metadata.get("title", doc_id),
            content=body,
            category=metadata.get("category", ""),
            service=service_val,
            page_type=page_type,
            tags=tags_raw,
            source=metadata.get("source", ""),
            raw_source_id=raw_source_id,
            version=version,
            links=links_raw,
            created=str(file_created),
            updated=str(file_updated),
            content_hash=content_hash,
            sync_status=sync_status,
            extra_metadata=extra_meta,
        ))

    return docs


def _resolve_doc_path(doc_id: str) -> str:
    """`doc_id` → 절대 파일경로.

    - `category/slug` (v2 권장) → `{knowledge_dir}/{category}/{slug}.md`
    - legacy flat (`some-doc-id`) → `{knowledge_dir}/{some-doc-id}.md`

    URL 인코딩된 `%2F` 는 라우터 정규화 단계에서 이미 `/` 로 디코드된다고 가정.
    """
    knowledge_dir = _knowledge_dir()
    if "/" in doc_id:
        category, _, slug = doc_id.partition("/")
        return os.path.join(knowledge_dir, category, f"{slug}.md")
    return os.path.join(knowledge_dir, f"{doc_id}.md")


def read_md_file(doc_id: str, chroma_hashes: Optional[Dict[str, str]] = None) -> Optional[KnowledgeFileDoc]:
    """단일 MD 파일 읽기 (v2: `{category}/{slug}` 형태의 id 도 지원)."""
    filepath = _resolve_doc_path(doc_id)

    if not os.path.exists(filepath):
        return None

    if chroma_hashes is None:
        chroma_hashes = {}

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            raw = f.read()
    except Exception as e:
        logger.error(f"파일 읽기 실패: {filepath} - {e}")
        return None

    metadata, body = parse_frontmatter(raw)
    content_hash = compute_hash(body)

    # 동기화 상태 판별
    if doc_id in chroma_hashes:
        if chroma_hashes[doc_id] == content_hash:
            sync_status = "synced"
        else:
            sync_status = "modified"
    else:
        sync_status = "not_synced"

    stat = os.stat(filepath)
    file_created = metadata.get("created", datetime.fromtimestamp(stat.st_ctime).isoformat())
    file_updated = datetime.fromtimestamp(stat.st_mtime).isoformat()

    tags_raw = metadata.get("tags", [])
    if isinstance(tags_raw, str):
        tags_raw = [t.strip() for t in tags_raw.split(",") if t.strip()]

    # 비표준 키 추출 (v2 + multi-service v3 신규 필드 standard 화)
    _STANDARD_KEYS = {
        "title", "category", "tags", "source", "created",
        "page_type", "version", "links", "raw_source_id",
        "service",
    }
    extra_meta = {k: v for k, v in metadata.items() if k not in _STANDARD_KEYS}

    page_type = metadata.get("page_type", "Summary") or "Summary"
    version_raw = metadata.get("version", 1)
    try:
        version = int(version_raw)
    except (TypeError, ValueError):
        version = 1
    links_raw = metadata.get("links", [])
    if isinstance(links_raw, str):
        links_raw = [s.strip() for s in links_raw.split(",") if s.strip()]
    elif not isinstance(links_raw, list):
        links_raw = []
    raw_source_id = metadata.get("raw_source_id") or None

    # multi-service v3 — legacy 파일에 service 필드가 없으면 "unknown" default.
    service_raw = metadata.get("service")
    service_val = str(service_raw).strip() if service_raw else "unknown"
    if not service_val:
        service_val = "unknown"

    return KnowledgeFileDoc(
        id=doc_id,
        title=metadata.get("title", doc_id),
        content=body,
        category=metadata.get("category", ""),
        service=service_val,
        page_type=page_type,
        tags=tags_raw,
        source=metadata.get("source", ""),
        raw_source_id=raw_source_id,
        version=version,
        links=links_raw,
        created=str(file_created),
        updated=str(file_updated),
        content_hash=content_hash,
        sync_status=sync_status,
        extra_metadata=extra_meta,
    )


def write_md_file(
    doc_id: str,
    title: str,
    content: str,
    category: str = "",
    tags: Optional[List[str]] = None,
    source: str = "",
    created: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
    *,
    page_type: Optional[str] = None,
    version: Optional[int] = None,
    links: Optional[List[str]] = None,
    raw_source_id: Optional[str] = None,
    service: Optional[str] = None,
) -> KnowledgeFileDoc:
    """MD 파일 작성 (생성 또는 덮어쓰기).

    v2 doc_id 가 `category/slug` 형태이면 카테고리 서브디렉토리에 저장한다.
    legacy flat id 는 sanitize 후 knowledge_dir 루트에 저장 (하위호환).

    v2 신규 키워드 인자: ``page_type``, ``version``, ``links``, ``raw_source_id``
    multi-service v3 키워드 인자: ``service`` (None 이면 frontmatter 에 미기재 →
    재로드 시 default ``"unknown"``).
    """
    knowledge_dir = _knowledge_dir()
    if "/" in doc_id:
        # v2: {category}/{slug}
        cat, _, slug = doc_id.partition("/")
        # sanitize 는 slug 부분에만 적용 (`/` 보존)
        safe_slug = _sanitize_filename(slug)
        safe_id = f"{cat}/{safe_slug}"
        cat_dir = os.path.join(knowledge_dir, cat)
        os.makedirs(cat_dir, exist_ok=True)
        filepath = os.path.join(cat_dir, f"{safe_slug}.md")
    else:
        safe_id = _sanitize_filename(doc_id)
        filepath = os.path.join(knowledge_dir, f"{safe_id}.md")

    raw = build_md_file(
        title, content, category, tags, source, created, extra_metadata,
        page_type=page_type,
        version=version,
        links=links,
        raw_source_id=raw_source_id,
        service=service,
    )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(raw)

    content_hash = compute_hash(content)
    now = datetime.utcnow().isoformat()

    return KnowledgeFileDoc(
        id=safe_id,
        title=title,
        content=content,
        category=category,
        service=service or "unknown",
        page_type=page_type or "Summary",
        tags=tags or [],
        source=source,
        raw_source_id=raw_source_id,
        version=version if version is not None else 1,
        links=list(links) if links else [],
        created=created or now,
        updated=now,
        content_hash=content_hash,
        sync_status="not_synced",
        extra_metadata=extra_metadata or {},
    )


def delete_md_file(doc_id: str) -> bool:
    """MD 파일 삭제 (v2: `category/slug` 지원)."""
    filepath = _resolve_doc_path(doc_id)

    if not os.path.exists(filepath):
        return False

    try:
        os.remove(filepath)
        logger.info(f"파일 삭제: {filepath}")
        return True
    except Exception as e:
        logger.error(f"파일 삭제 실패: {filepath} - {e}")
        return False


def generate_doc_id(title: str) -> str:
    """제목에서 문서 ID 생성"""
    # 한글/영문/숫자/하이픈만 유지
    doc_id = re.sub(r'[^가-힣a-zA-Z0-9\s-]', '', title)
    doc_id = re.sub(r'\s+', '-', doc_id.strip())
    doc_id = doc_id.lower() if doc_id.isascii() else doc_id

    if not doc_id:
        doc_id = f"doc-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    # 중복 체크
    knowledge_dir = _knowledge_dir()
    base_id = doc_id
    counter = 1
    while os.path.exists(os.path.join(knowledge_dir, f"{doc_id}.md")):
        doc_id = f"{base_id}-{counter}"
        counter += 1

    return doc_id
