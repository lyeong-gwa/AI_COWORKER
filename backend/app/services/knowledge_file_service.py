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
    """파일 기반 지식 문서"""
    id: str
    title: str
    content: str
    category: str = ""
    tags: List[str] = field(default_factory=list)
    source: str = ""
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
) -> str:
    """YAML frontmatter + 마크다운 본문 생성"""
    import yaml

    now = datetime.utcnow().isoformat()

    metadata = {
        "title": title,
        "category": category or "",
        "tags": tags or [],
        "source": source or "",
        "created": created or now,
    }

    # 비표준 메타데이터 병합 (api 등)
    if extra_metadata:
        metadata.update(extra_metadata)

    yaml_str = yaml.dump(metadata, allow_unicode=True, default_flow_style=False, sort_keys=False).strip()

    return f"---\n{yaml_str}\n---\n\n{content}"


def list_md_files(chroma_hashes: Optional[Dict[str, str]] = None) -> List[KnowledgeFileDoc]:
    """MD 파일 목록 조회 + 동기화 상태 판별"""
    knowledge_dir = _knowledge_dir()
    docs = []

    if chroma_hashes is None:
        chroma_hashes = {}

    for filename in sorted(os.listdir(knowledge_dir)):
        if not filename.endswith('.md'):
            continue

        doc_id = filename[:-3]  # .md 제거
        filepath = os.path.join(knowledge_dir, filename)

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

        # 비표준 키 추출 (standard keys 제외)
        _STANDARD_KEYS = {"title", "category", "tags", "source", "created"}
        extra_meta = {k: v for k, v in metadata.items() if k not in _STANDARD_KEYS}

        docs.append(KnowledgeFileDoc(
            id=doc_id,
            title=metadata.get("title", doc_id),
            content=body,
            category=metadata.get("category", ""),
            tags=tags_raw,
            source=metadata.get("source", ""),
            created=str(file_created),
            updated=str(file_updated),
            content_hash=content_hash,
            sync_status=sync_status,
            extra_metadata=extra_meta,
        ))

    return docs


def read_md_file(doc_id: str, chroma_hashes: Optional[Dict[str, str]] = None) -> Optional[KnowledgeFileDoc]:
    """단일 MD 파일 읽기"""
    knowledge_dir = _knowledge_dir()
    filepath = os.path.join(knowledge_dir, f"{doc_id}.md")

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

    # 비표준 키 추출 (standard keys 제외)
    _STANDARD_KEYS = {"title", "category", "tags", "source", "created"}
    extra_meta = {k: v for k, v in metadata.items() if k not in _STANDARD_KEYS}

    return KnowledgeFileDoc(
        id=doc_id,
        title=metadata.get("title", doc_id),
        content=body,
        category=metadata.get("category", ""),
        tags=tags_raw,
        source=metadata.get("source", ""),
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
) -> KnowledgeFileDoc:
    """MD 파일 작성 (생성 또는 덮어쓰기)"""
    knowledge_dir = _knowledge_dir()
    safe_id = _sanitize_filename(doc_id)
    filepath = os.path.join(knowledge_dir, f"{safe_id}.md")

    raw = build_md_file(title, content, category, tags, source, created, extra_metadata)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(raw)

    content_hash = compute_hash(content)
    now = datetime.utcnow().isoformat()

    return KnowledgeFileDoc(
        id=safe_id,
        title=title,
        content=content,
        category=category,
        tags=tags or [],
        source=source,
        created=created or now,
        updated=now,
        content_hash=content_hash,
        sync_status="not_synced",
        extra_metadata=extra_metadata or {},
    )


def delete_md_file(doc_id: str) -> bool:
    """MD 파일 삭제"""
    knowledge_dir = _knowledge_dir()
    filepath = os.path.join(knowledge_dir, f"{doc_id}.md")

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
