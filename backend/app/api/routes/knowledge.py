"""
Knowledge Base API Routes

MD 파일 기반 지식 문서 관리 + ChromaDB 유사도 검색.

Karpathy v2 (`.omc/plans/지식-karpathy-v2.md` P2):
  - POST/PUT/DELETE 가 schema 검증 (page_type/category/slug enum) 강제
  - `[[link]]` 자동 파싱 → `links` 필드 채움
  - `_log.md` / `_index-{category}.md` 자동 갱신
  - PUT 시 `version` 자동 증가 + KnowledgeChangelogEntry 적재
  - DELETE 시 backlink 보호 (409), `?force=true` 시 backlink 페이지 자동 치환
  - 신규: POST /raw, GET /{id}/backlinks
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import json
import logging
import time
import threading
import os

from ...core.database import get_db
from ...core.exceptions import (
    AppException,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from ...models.workflow import WarehouseEntry, WorkflowExecution
from ...schemas.knowledge import (
    KnowledgeCreate, KnowledgeUpdate,
    KnowledgeSearchRequest,
)
from ...services.knowledge_file_service import (
    list_md_files, read_md_file, write_md_file, delete_md_file,
    generate_doc_id, compute_hash, KnowledgeFileDoc,
)
from ...services.knowledge_schema import (
    SchemaValidationError,
    list_services,
    load_schema,
    validate_category,
    validate_page_type,
    validate_service,
    validate_slug,
)
from ...services.knowledge_link_parser import (
    parse_links,
    has_link_to,
    replace_link_with_deleted,
)
from ...services.knowledge_writer import (
    append_log_entry,
    rebuild_index,
)
from ...services.knowledge_changelog_service import add_changelog
from ...services.raw_source_service import (
    save_raw_source,
    raw_source_to_dict,
    MAX_RAW_FILE_BYTES,
)
from ...services.knowledge_lint import run_lint
from ...services.knowledge_brief import build_brief
from ...services.knowledge_restore import restore_from_archive

logger = logging.getLogger(__name__)
router = APIRouter()

# ── 일괄 동기화 상태 (in-memory, 단일 프로세스 기준) ────────────────────────
_bulk_sync_state: dict = {
    "status": "idle",     # idle | running | completed | failed
    "total": 0,
    "synced": 0,
    "failed": 0,
    "started_at": None,
}
_bulk_sync_lock = threading.Lock()


def _doc_to_response(doc: KnowledgeFileDoc, *, warnings: Optional[List[str]] = None) -> dict:
    """KnowledgeFileDoc -> camelCase dict 응답.

    Karpathy v2: page_type/version/links/rawSourceId 노출. ``warnings`` 가 주어지면
    동봉 (POST/PUT 응답에서 15.4 권고 메시지 전달용).

    Multi-service v3 P2 (`.omc/plans/지식-multi-service.md` §2.1): ``service`` 키를
    모든 응답(단건 GET / 목록 GET / POST / PUT) 에 노출. 미정의 페이지는 ``"unknown"``.
    """
    resp = {
        "id": doc.id,
        "title": doc.title,
        "content": doc.content,
        "category": doc.category,
        "service": doc.service or "unknown",
        "tags": doc.tags,
        "source": doc.source,
        "sourceUrl": doc.source_url,
        "pageType": doc.page_type,
        "version": doc.version,
        "links": list(doc.links),
        "rawSourceId": doc.raw_source_id,
        "contentHash": doc.content_hash,
        "syncStatus": doc.sync_status,
        "createdAt": doc.created,
        "updatedAt": doc.updated,
    }
    # 도구-API 문서의 경우 api 메타데이터 포함
    if hasattr(doc, 'extra_metadata') and doc.extra_metadata.get('api'):
        resp["api"] = doc.extra_metadata["api"]
    if warnings:
        resp["warnings"] = list(warnings)
    return resp


def _get_chroma_hashes() -> dict:
    """ChromaDB에서 해시 조회 (실패 시 빈 dict)"""
    try:
        from ...services.embedding import get_vector_db
        vector_db = get_vector_db()
        return vector_db.get_all_document_hashes()
    except Exception as e:
        logger.warning(f"ChromaDB 해시 조회 실패: {e}")
        return {}


def _sync_doc_to_chroma(doc: KnowledgeFileDoc) -> None:
    """단일 문서를 chunk-aware ChromaDB 에 sync (best-effort).

    Karpathy v2 P3 §3.1 — POST/PUT 시 자동 호출. 실패해도 파일은 보존되며 경고만.

    Multi-service v3 P2 (`.omc/plans/지식-multi-service.md` §2.7): 청크 metadata 에
    ``service`` 를 포함하여 knowledge 노드 / brief 의 service 필터가 ChromaDB
    where_filter 로 일관 동작하게 한다. 기존 페이지는 P2 reindex 엔드포인트로
    1회 갱신된다.
    """
    try:
        from ...services.embedding import get_vector_db
        vector_db = get_vector_db()
        content_hash = compute_hash(doc.content)
        meta: Dict[str, Any] = {
            "title": doc.title,
            "category": doc.category or "",
            "service": doc.service or "unknown",
            "source": doc.source or "",
            "content_hash": content_hash,
            "page_type": doc.page_type or "Summary",
            "version": doc.version or 1,
            "links": list(doc.links or []),
        }
        # source_url 은 None 이면 metadata 에 _기록하지 않는다_ (LLM URL hallucination 차단).
        # ChromaDB 가 None 을 거부하므로 빈 키 자체를 생략한다.
        if doc.source_url:
            meta["source_url"] = doc.source_url
        vector_db.add_document(
            doc_id=doc.id,
            content=doc.content,
            metadata=meta,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[KNOWLEDGE_SYNC] ChromaDB sync 실패 — 파일은 보존됨: %s", e)


def _raise_schema_violation(exc: SchemaValidationError) -> None:
    """SchemaValidationError → 422 envelope. P2 진입점 일괄 처리용."""
    details = dict(exc.details or {})
    details["field"] = exc.field
    raise ValidationError(str(exc), details=details)


def _build_warnings(doc: KnowledgeFileDoc, all_docs: List[KnowledgeFileDoc]) -> List[str]:
    """Plan §15.4 비차단 권고 메시지.

    - outgoing link 0 + page_type != Entity → 고아 가능성 권고
    - 동일 카테고리 내 동일 title 페이지 (정확 일치) → 의미적 중복 가능성 권고
      (P2 에서는 cosine 계산 없이 title 일치만 가벼운 휴리스틱으로 사용.
       LLM 기반 의미 중복 점검은 P4 lint 의 몫.)
    """
    warns: List[str] = []
    if not doc.links and doc.page_type != "Entity":
        warns.append(
            f"outgoing link 0건 + page_type={doc.page_type} — 고아 페이지 가능성"
        )
    same_title = [
        d for d in all_docs
        if d.id != doc.id and d.category == doc.category and d.title == doc.title
    ]
    if same_title:
        warns.append(
            "동일 카테고리·동일 제목 페이지 존재 — 의미적 중복 가능성: "
            + ", ".join(d.id for d in same_title[:3])
        )
    return warns


# ── 목록/조회 (기존) ───────────────────────────────────────────────────────


@router.get(
    "",
    summary="지식문서 목록 조회",
    description=(
        "YAML frontmatter + 마크다운으로 저장된 지식문서 목록을 반환한다. "
        "ChromaDB 인덱스와의 동기화 상태(``syncStatus``)도 함께 제공."
    ),
)
async def list_documents(
    category: Optional[str] = Query(None, description="카테고리 필터"),
    service: Optional[str] = Query(
        None,
        description=(
            "service 필터 (multi-service v3 P2). _schema.yaml services enum 에 "
            "존재해야 하며, 미정의 service id 면 422. 'unknown' sentinel 도 허용."
        ),
    ),
    sync_status: Optional[str] = Query(None, description="동기화 상태 필터"),
    q: Optional[str] = Query(None, description="검색어 (제목, 내용)"),
    skip: int = Query(0, ge=0, description="건너뛸 항목 수"),
    limit: int = Query(100, ge=1, le=500, description="최대 항목 수"),
):
    """문서 목록 조회 (폴더 스캔 + ChromaDB 해시 비교).

    Multi-service v3 P2 (`.omc/plans/지식-multi-service.md` §2.3):
        ``service`` 필터를 ``category`` 와 AND 결합으로 지원. 미정의 service 는 422.
    """
    chroma_hashes = _get_chroma_hashes()
    docs = list_md_files(chroma_hashes)

    # service 필터 (enum 강제) — P2 §2.3
    if service:
        try:
            validate_service(service)
        except SchemaValidationError as exc:
            _raise_schema_violation(exc)
        docs = [d for d in docs if (d.service or "unknown") == service]

    # 카테고리 필터
    if category:
        docs = [d for d in docs if d.category == category]

    # 동기화 상태 필터
    if sync_status:
        docs = [d for d in docs if d.sync_status == sync_status]

    # 텍스트 검색
    if q:
        q_lower = q.lower()
        docs = [
            d for d in docs
            if q_lower in d.title.lower()
            or q_lower in d.content.lower()
            or any(q_lower in tag.lower() for tag in d.tags)
        ]

    # 정렬: 최신 순
    docs.sort(key=lambda d: d.updated or d.created, reverse=True)

    # 페이지네이션
    docs = docs[skip:skip + limit]

    return [_doc_to_response(d) for d in docs]


@router.get("/meta")
async def get_metadata():
    """지식 문서의 고유 카테고리/태그 목록 + 카테고리별 태그 매핑 반환"""
    docs = list_md_files()
    categories = sorted({d.category for d in docs if d.category})
    tags = sorted({t for d in docs for t in d.tags if t})

    # 카테고리별 태그 빈도 집계
    from collections import Counter
    cat_tag_counters: dict[str, Counter] = {}
    for d in docs:
        if not d.category:
            continue
        if d.category not in cat_tag_counters:
            cat_tag_counters[d.category] = Counter()
        for t in d.tags:
            if t:
                cat_tag_counters[d.category][t] += 1

    # 빈도순 정렬
    category_tags: dict[str, list[str]] = {
        cat: [tag for tag, _ in counter.most_common()]
        for cat, counter in sorted(cat_tag_counters.items())
    }

    return {"categories": categories, "tags": tags, "categoryTags": category_tags}


# ── /raw (Karpathy v2 신규) ────────────────────────────────────────────────


@router.post(
    "/raw",
    status_code=201,
    summary="원본 파일(raw blob) 업로드",
    description=(
        "Karpathy v2 Layer 1 — `data/knowledge-raw/{yyyy}/{mm}/{uuid}.{ext}` 에 "
        "blob 저장 후 ``RawSource`` 1 행을 DB 에 적재. "
        "이후 운영자가 raw → wiki 페이지 큐레이션 (P6)."
    ),
)
async def create_raw_source(
    file: UploadFile = File(..., description="원본 파일 (binary)"),
    filename: Optional[str] = Form(default=None, description="저장될 filename override"),
    derived_knowledge_ids: Optional[str] = Form(
        default=None,
        description="comma-separated 파생 wiki id (예: 'codeeyes/overview,faq/q1')",
    ),
    db: AsyncSession = Depends(get_db),
):
    blob = await file.read()
    size = len(blob)
    if size == 0:
        raise ValidationError("업로드된 파일이 비어 있습니다", details={"size": 0})
    if size > MAX_RAW_FILE_BYTES:
        raise ValidationError(
            f"파일 크기 {size} 바이트가 한계 {MAX_RAW_FILE_BYTES} 바이트를 초과합니다",
            details={"size": size, "max": MAX_RAW_FILE_BYTES},
        )

    derived = []
    if derived_knowledge_ids:
        derived = [s.strip() for s in derived_knowledge_ids.split(",") if s.strip()]

    final_filename = filename or file.filename or "upload"
    mime = file.content_type or "application/octet-stream"

    try:
        row = await save_raw_source(
            db,
            filename=final_filename,
            mime=mime,
            blob=blob,
            derived_knowledge_ids=derived,
        )
    except ValueError as exc:
        raise ValidationError(str(exc))

    return raw_source_to_dict(row)


# ── /{doc_id}/backlinks (Karpathy v2 신규) ────────────────────────────────


@router.get(
    "/{doc_id:path}/backlinks",
    summary="이 페이지를 가리키는 모든 페이지 id 목록",
    description=(
        "Karpathy v2 — 다른 페이지 본문에서 ``[[{doc_id}]]`` 패턴 보유 페이지의 id "
        "(category/slug) 목록을 ASC 정렬로 반환."
    ),
)
async def get_backlinks(doc_id: str):
    # 자기 자신 제외
    all_docs = list_md_files()
    incoming = [
        d.id for d in all_docs
        if d.id != doc_id and has_link_to(d.content, doc_id)
    ]
    incoming.sort()
    return {"id": doc_id, "backlinks": incoming}


# 주의: GET /sync/status, POST /search, POST /from-instance 등 구체 path 들은
# 아래 ``GET /{doc_id:path}`` 가 가로채지 않도록 _그 위에_ 정의되어 있어야 한다.
# FastAPI 는 라우트 등록 순서대로 매칭하기 때문이다.


@router.get(
    "/services",
    summary="등록된 서비스 enum 목록 (multi-service v3 P2)",
    description=(
        "`_schema.yaml` 의 ``services:`` 섹션을 ``[{id, title, description}]`` "
        "형태로 반환. UI 사이드바 1단(서비스) 렌더 + CLI 보조용. "
        "주의: 본 라우트는 catch-all ``GET /{doc_id:path}`` 가로채기 방지를 위해 "
        "그 _위에_ 등록되어 있다."
    ),
)
async def get_services():
    """multi-service v3 P2 §2.2 — 서비스 enum 노출."""
    return list_services()


@router.get("/sync/status")
async def get_sync_status():
    """일괄 동기화 진행 상태 조회 (GET catch-all 보다 _먼저_ 등록되어야 한다)"""
    with _bulk_sync_lock:
        return dict(_bulk_sync_state)


@router.post(
    "/_internal/reindex-services",
    summary="모든 페이지 ChromaDB metadata 에 service 키 반영 (multi-service v3 P2 §2.7)",
    description=(
        "기존 v2 컬렉션의 페이지 metadata 에 service 키가 없으면 knowledge 노드/brief "
        "의 service 필터가 동작하지 않는다. 본 엔드포인트는 모든 .md 페이지를 다시 "
        "``vector_db.add_document`` 로 upsert 하여 service 키를 1회 갱신한다. "
        "best-effort — 실패 페이지는 카운트만 누적. P2 배포 직후 1회 실행 후에는 "
        "POST/PUT 의 ``_sync_doc_to_chroma`` 가 자동 갱신을 이어간다."
    ),
)
async def reindex_services():
    from ...services.embedding import get_vector_db

    try:
        vector_db = get_vector_db()
    except Exception as exc:  # noqa: BLE001
        raise AppException(
            f"벡터 DB 초기화 실패: {exc}",
            code="VECTOR_DB_UNAVAILABLE",
            status_code=503,
        )

    docs = list_md_files()
    total = len(docs)
    synced = 0
    failed = 0
    failed_ids: List[str] = []
    for doc in docs:
        try:
            content_hash = compute_hash(doc.content)
            meta: Dict[str, Any] = {
                "title": doc.title,
                "category": doc.category or "",
                "service": doc.service or "unknown",
                "source": doc.source or "",
                "content_hash": content_hash,
                "page_type": doc.page_type or "Summary",
                "version": doc.version or 1,
                "links": list(doc.links or []),
            }
            if doc.source_url:
                meta["source_url"] = doc.source_url
            vector_db.add_document(
                doc_id=doc.id,
                content=doc.content,
                metadata=meta,
            )
            synced += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("[REINDEX_SERVICES] %s 실패: %s", doc.id, exc)
            failed += 1
            if len(failed_ids) < 20:
                failed_ids.append(doc.id)

    return {
        "total": total,
        "synced": synced,
        "failed": failed,
        "failedSampleIds": failed_ids,
    }


# ── /knowledge/lint, /knowledge/index/rebuild, /knowledge/brief ───────────
# Karpathy v2 P4 §6.1 — 모두 `GET /{doc_id:path}` 가로채기 방지를 위해
# 구체 path 가 먼저 등록되어야 한다.


class LintRequest(BaseModel):
    """POST /knowledge/lint 요청 body. plan §6.1, §9 D3 (on-demand only)."""

    categories: Optional[List[str]] = Field(default=None, description="검사 대상 카테고리 필터. None/빈 리스트 = 전체.")
    dry_run: bool = Field(default=False, description="True 면 정적 검사만, LLM 호출 0. 보고서/history 는 작성.")
    llm_enabled: bool = Field(default=True, description="False 면 LLM 호출 0 (dynamic 섹션 모두 (none)).")


@router.post(
    "/lint",
    summary="on-demand 위키 점검 — 정적+동적 lint",
    description=(
        "**Karpathy v2 P4** — 카테고리·page_type·slug enum 위반, 깨진 링크, 고아 페이지, "
        "page_type min_links 위반을 정적으로 검사하고, 의미적 중복·모순·구식 의심을 "
        "임베딩+LLM(temperature=0.1, batch 5) 으로 동적 검사한다. "
        "`_lint-report.md` 를 덮어쓰고 `_lint-history/{ts}.md` 에 백업한다. "
        "D3 정책: on-demand only — 자동 스케줄러 절대 미도입."
    ),
)
async def lint_knowledge(request: LintRequest):
    try:
        result = await run_lint(
            categories=request.categories or None,
            dry_run=bool(request.dry_run),
            llm_enabled=bool(request.llm_enabled),
        )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("[KNOWLEDGE_LINT] 실패")
        raise AppException(
            f"lint 실행 실패: {exc}",
            code="LINT_ERROR",
            status_code=500,
        )


class IndexRebuildRequest(BaseModel):
    """POST /knowledge/index/rebuild 요청. 카테고리 미지정 시 전체."""

    categories: Optional[List[str]] = Field(default=None, description="재생성할 카테고리. None/빈 = 전체 카테고리.")


@router.post(
    "/index/rebuild",
    summary="`_index-{category}.md` 전체 재생성",
    description=(
        "Karpathy v2 P4 §6.1 — 지정한 카테고리(또는 전체) 의 인덱스 파일을 "
        "디렉토리 스캔으로부터 재생성한다. POST/PUT/DELETE 가 정상 동작하면 "
        "각 카테고리 인덱스는 자동 갱신되지만, 운영자가 외부 편집 후 강제 "
        "재정렬이 필요한 경우 본 엔드포인트를 호출한다."
    ),
)
async def index_rebuild(request: IndexRebuildRequest):
    try:
        from ...services.knowledge_schema import load_schema

        target_cats: List[str] = []
        if request.categories:
            target_cats = [c for c in request.categories if c]
        else:
            schema = load_schema()
            target_cats = sorted(schema.category_ids)

        rebuilt: List[str] = []
        for cat in target_cats:
            try:
                rebuild_index(cat)
                rebuilt.append(cat)
            except Exception as e:  # noqa: BLE001
                logger.warning("[INDEX_REBUILD] %s 실패: %s", cat, e)
        return {"rebuilt": rebuilt}
    except Exception as exc:  # noqa: BLE001
        logger.exception("[KNOWLEDGE_INDEX_REBUILD] 실패")
        raise AppException(
            f"index/rebuild 실패: {exc}",
            code="INDEX_REBUILD_ERROR",
            status_code=500,
        )


class BriefRequest(BaseModel):
    """POST /knowledge/brief 요청. Consumer B (CLI 어시스턴트 작업이해)."""

    topic: Optional[str] = Field(default=None, description="자유 주제. query 와 둘 중 하나 필수.")
    query: Optional[str] = Field(default=None, description="검색 쿼리. 지정 시 topic 보다 우선.")
    categories: Optional[List[str]] = Field(default=None, description="카테고리 필터 (다중 OR).")
    services: Optional[List[str]] = Field(
        default=None,
        description=(
            "multi-service v3 P2 §2.5 — service 필터 (다중 OR). "
            "None/빈 리스트 = 전체. 각 service id 는 _schema.yaml services enum 에 "
            "존재해야 하며, 미정의 id 가 1개라도 포함되면 422."
        ),
    )
    maxPages: int = Field(default=8, ge=1, le=50, description="응답 페이지 최대 개수.")
    includeLog: bool = Field(default=True, description="`_log.md` 최근 변경이력 포함 여부.")


@router.post(
    "/brief",
    summary="Consumer B — CLI 어시스턴트용 briefing 패키지",
    description=(
        "**Karpathy v2 P4 — Consumer B 핵심.** "
        "사용자가 CLI 로 AI 와 작업할 때 그 AI 가 사용자의 작업 의도를 broadly 이해할 수 있도록 "
        "(1) page_type 가중치 적용된 페이지 전체, (2) 해당 카테고리 인덱스, "
        "(3) 최근 변경이력 을 한 패키지로 반환한다. "
        "page_type 가중치: Synthesis x1.5, Summary x1.3, Comparison x1.1, Concept x1.0, Entity x0.9."
    ),
)
async def brief_knowledge(request: BriefRequest):
    if not (request.topic or request.query):
        raise ValidationError(
            "topic 또는 query 중 하나는 필수입니다",
            details={"field": "topic|query"},
        )

    # multi-service v3 P2 §2.5 — services enum 강제 (미정의 1개라도 → 422)
    services_arg: Optional[List[str]] = None
    if request.services:
        try:
            for sid in request.services:
                validate_service(sid)
        except SchemaValidationError as exc:
            _raise_schema_violation(exc)
        services_arg = list(request.services)

    try:
        result = await build_brief(
            topic=request.topic,
            query=request.query,
            categories=request.categories or None,
            services=services_arg,
            max_pages=int(request.maxPages),
            include_log=bool(request.includeLog),
        )
        return result
    except ValueError as exc:
        raise ValidationError(str(exc), details={"field": "topic|query"})
    except Exception as exc:  # noqa: BLE001
        logger.exception("[KNOWLEDGE_BRIEF] 실패")
        raise AppException(
            f"brief 실행 실패: {exc}",
            code="BRIEF_ERROR",
            status_code=500,
        )


# ── /knowledge/restore-from-archive (Karpathy v2 P6 §6.1, §10.1 step 7) ──


class RestoreFromArchiveRequest(BaseModel):
    """POST /knowledge/restore-from-archive 요청.

    Karpathy v2 P6 §6.1, §10.1 step 7 — archive .md 를 신정책 형식으로 재등록.
    default ``dry_run=True`` (안전). 운영자가 보고서 검토 후 ``dry_run=False`` 로 실제 실행.
    """

    category_hint: Optional[str] = Field(
        default=None,
        description=(
            "우선 카테고리 ('codeeyes'|'ito-portal-operations'|'plugin-troubleshooting'|'faq'). "
            "schema enum 미일치 시 LLM/휴리스틱 판단으로 fallback."
        ),
    )
    archive_subpath: Optional[str] = Field(
        default=None,
        description=(
            "archive 의 서브폴더 ('소스코드검증-운영가이드'|'_DUPLICATE_REVIEW'). "
            "None 이면 archive 전체 재귀 스캔."
        ),
    )
    dry_run: bool = Field(
        default=True,
        description="True (default) 면 결과만 보고. False 면 실제 등록.",
    )
    max_files: int = Field(
        default=200,
        ge=1,
        le=2000,
        description="비용 가드 — 한 번에 처리할 archive 파일 최대 수.",
    )
    llm_enabled: bool = Field(
        default=True,
        description=(
            "False 면 LLM 호출 0 (휴리스틱만). "
            "page_type=Summary 기본, slug=파일명 ascii-fold, category=hint or 휴리스틱."
        ),
    )


@router.post(
    "/restore-from-archive",
    summary="archive 의 .md 들을 신정책 형식으로 재등록 (default dry_run)",
    description=(
        "**Karpathy v2 P6** — `data/knowledge-archive/` 의 .md 파일들을 "
        "_보존_ 한 채로, 신정책 (page_type 5종 enum + 카테고리 schema enum + "
        "영문 kebab-case slug) 형식으로 wiki 에 _신규 등록_ 한다. "
        "default ``dry_run=True`` (안전). 실제 실행은 `dry_run=False` 로 명시. "
        "LLM 으로 카테고리/page_type/slug 자동 판단, 실패/비활성 시 휴리스틱 fallback. "
        "보고서는 `data/knowledge/_restore-report.md` 에 덮어쓰기."
    ),
)
async def restore_from_archive_endpoint(
    request: RestoreFromArchiveRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await restore_from_archive(
            category_hint=request.category_hint or None,
            archive_subpath=request.archive_subpath or None,
            dry_run=bool(request.dry_run),
            max_files=int(request.max_files),
            llm_enabled=bool(request.llm_enabled),
            db=db,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("[KNOWLEDGE_RESTORE] 실패")
        raise AppException(
            f"restore-from-archive 실행 실패: {exc}",
            code="RESTORE_ERROR",
            status_code=500,
        )


# ── /knowledge/graph (재구성 Phase 1 — 임베딩 기반 의미 엣지 + community) ──


@router.get(
    "/graph",
    summary="지식 페이지 그래프 (explicit + implicit + community)",
    description=(
        "**그래프 재구성 Phase 1** (`.omc/plans/지식-그래프-재구성.md`) — "
        "explicit `[[link]]` 엣지 위에 ChromaDB ``knowledge_v2`` 임베딩 기반 "
        "implicit cosine 엣지를 추가하고, Louvain community + degree-centrality "
        "godScore 를 계산하여 반환한다. LLM 호출 0 (폐쇄환경 호환). "
        "선택 필터: ``category`` (단일), ``page_type`` (단일), ``service`` (단일). "
        "튜닝 env: ``KNOWLEDGE_IMPLICIT_THRESHOLD`` (default 0.75), "
        "``KNOWLEDGE_IMPLICIT_MAX_PER_PAGE`` (default 5)."
    ),
)
async def get_knowledge_graph(
    category: Optional[str] = Query(default=None, description="단일 카테고리 필터"),
    page_type: Optional[str] = Query(default=None, description="단일 page_type 필터"),
    service: Optional[str] = Query(
        default=None,
        description=(
            "단일 service 필터 (multi-service v3 P2). _schema.yaml services enum "
            "에 존재해야 하며, 미정의 service id 면 422. 'unknown' 도 허용."
        ),
    ),
):
    # service 필터는 enum 강제 (P2 §2.4)
    if service:
        try:
            validate_service(service)
        except SchemaValidationError as exc:
            _raise_schema_violation(exc)

    # builder 위임 — 모든 그래프 로직은 knowledge_graph_builder 가 단일 진실원.
    from ...services.knowledge_graph_builder import build_graph as _build

    return _build(
        service=service,
        page_type=page_type,
        category=category,
    )


# ── /knowledge/edge (EdgeInspector 데이터 페어 — Phase 1 §3.3) ────────────


@router.get(
    "/edge",
    summary="두 페이지 사이 엣지 + 양쪽 페이지 전체 본문 (EdgeInspector 용)",
    description=(
        "**그래프 재구성 Phase 1 §3.3** — `from`, `to` 페이지의 KnowledgeDoc 전체와 "
        "두 페이지를 잇는 엣지 메타 (kind/weight/similarity/isBroken/crossService) "
        "를 한 응답에 묶어 반환. 엣지가 없으면 ``edge=null`` + 200. 한 쪽이라도 "
        "페이지가 없으면 404."
    ),
)
async def get_knowledge_edge(
    from_: str = Query(..., alias="from", description="시작 페이지 id"),
    to: str = Query(..., description="대상 페이지 id"),
):
    from_id = from_
    if not from_id or not to:
        raise ValidationError(
            "'from' 과 'to' 모두 필수입니다",
            details={"from": from_id, "to": to},
        )
    if from_id == to:
        raise ValidationError(
            "'from' 과 'to' 가 동일합니다 — 자기루프는 엣지가 아닙니다",
            details={"from": from_id, "to": to},
        )

    chroma_hashes = _get_chroma_hashes()
    from_doc = read_md_file(from_id, chroma_hashes)
    to_doc = read_md_file(to, chroma_hashes)
    if from_doc is None or to_doc is None:
        missing = [pid for pid, d in [(from_id, from_doc), (to, to_doc)] if d is None]
        raise NotFoundError(
            "페이지를 찾을 수 없습니다",
            details={"missing": missing},
        )

    # 1) explicit 검사 — from 본문에 [[to]] 가 있으면 explicit 엣지.
    is_explicit_from_to = has_link_to(from_doc.content, to)
    is_explicit_to_from = has_link_to(to_doc.content, from_id)

    edge_obj: Optional[Dict[str, Any]] = None
    from_service = from_doc.service or "unknown"
    to_service = to_doc.service or "unknown"
    cross_service = from_service != to_service

    if is_explicit_from_to or is_explicit_to_from:
        edge_obj = {
            "kind": "explicit",
            "weight": 1.0,
            "similarity": None,
            "isBroken": False,
            "crossService": bool(cross_service),
            # 추가 정보 — 어느 방향이 explicit 인지
            "fromToExplicit": bool(is_explicit_from_to),
            "toFromExplicit": bool(is_explicit_to_from),
        }
    else:
        # 2) implicit 후보 — ChromaDB 임베딩으로 cosine 계산.
        try:
            from ...services.knowledge_graph_builder import _load_page_embeddings
            import numpy as _np

            embs = _load_page_embeddings([from_id, to])
            v1 = embs.get(from_id)
            v2 = embs.get(to)
            if v1 is not None and v2 is not None:
                sim = float(_np.dot(v1, v2))  # 둘 다 L2 normalize 됨
                threshold = float(
                    os.getenv("KNOWLEDGE_IMPLICIT_THRESHOLD", "0.75") or 0.75
                )
                if sim >= threshold:
                    edge_obj = {
                        "kind": "implicit",
                        "weight": float(sim),
                        "similarity": float(sim),
                        "isBroken": False,
                        "crossService": bool(cross_service),
                    }
                else:
                    # threshold 미달 — 엣지는 없지만 similarity 는 알려준다 (디버깅 용).
                    edge_obj = None
            else:
                edge_obj = None
        except Exception as e:  # noqa: BLE001
            logger.warning("[KNOWLEDGE_EDGE] cosine 계산 실패: %s", e)
            edge_obj = None

    return {
        "from": _doc_to_response(from_doc),
        "to": _doc_to_response(to_doc),
        "edge": edge_obj,
    }


# ── /knowledge/edge/promote (implicit → explicit 승격 — Phase 1 §3.4) ──


class EdgePromoteRequest(BaseModel):
    """POST /knowledge/edge/promote 요청 body."""

    model_config = {"populate_by_name": True}

    from_: str = Field(..., alias="from", description="시작 페이지 id (수정 대상)")
    to: str = Field(..., description="대상 페이지 id (링크 대상)")
    anchorText: Optional[str] = Field(
        default=None,
        description="링크 prefix 텍스트 (예: '참고'). 비우면 '참고' 사용.",
    )


@router.post(
    "/edge/promote",
    summary="implicit 엣지 → explicit 링크 승격 (페이지 본문 자동 편집)",
    description=(
        "**그래프 재구성 Phase 1 §3.4** — `from` 페이지 본문 끝에 `[[to]]` 를 "
        "포함한 새 문단을 추가하고 (anchorText prefix 적용), 내부 PUT 흐름과 "
        "동일하게 version+1, changelog, _log/_index 갱신, ChromaDB sync 를 수행한다. "
        "이미 `[[to]]` 가 포함되어 있으면 409."
    ),
)
async def promote_edge_to_explicit(
    request: EdgePromoteRequest,
    db: AsyncSession = Depends(get_db),
):
    from_id = request.from_
    to_id = request.to
    if not from_id or not to_id:
        raise ValidationError(
            "'from' 과 'to' 모두 필수입니다",
            details={"from": from_id, "to": to_id},
        )
    if from_id == to_id:
        raise ValidationError(
            "'from' 과 'to' 가 동일합니다",
            details={"from": from_id, "to": to_id},
        )

    from_doc = read_md_file(from_id)
    to_doc = read_md_file(to_id)
    if from_doc is None or to_doc is None:
        missing = [pid for pid, d in [(from_id, from_doc), (to_id, to_doc)] if d is None]
        raise NotFoundError(
            "페이지를 찾을 수 없습니다",
            details={"missing": missing},
        )

    # 이미 explicit 이면 409
    if has_link_to(from_doc.content, to_id):
        raise ConflictError(
            "이미 explicit 링크가 존재합니다 (이 페이지는 이미 [[to]] 를 가리킵니다)",
            details={"from": from_id, "to": to_id},
        )

    anchor = (request.anchorText or "참고").strip() or "참고"

    # 본문 끝에 새 문단 추가 — 마지막 줄 공백 정규화.
    base = from_doc.content.rstrip()
    new_paragraph = f"\n\n{anchor}: [[{to_id}]]\n"
    new_content = base + new_paragraph

    # links 재파싱, version+1
    new_links = parse_links(new_content)
    new_version = (from_doc.version or 1) + 1

    # 파일 저장 (rename 없음, 동일 id 유지)
    updated_doc = write_md_file(
        doc_id=from_id,
        title=from_doc.title,
        content=new_content,
        category=from_doc.category or "",
        tags=from_doc.tags,
        source=from_doc.source or "",
        created=from_doc.created,
        extra_metadata=from_doc.extra_metadata if from_doc.extra_metadata else None,
        page_type=from_doc.page_type,
        version=new_version,
        links=new_links,
        raw_source_id=from_doc.raw_source_id,
        service=from_doc.service or "unknown",
        source_url=from_doc.source_url,
    )

    operator = "edge-promote"

    # changelog
    try:
        await add_changelog(
            db,
            knowledge_id=from_id,
            version=new_version,
            change_type="update",
            operator=operator,
            diff_summary=f"edge promote: implicit→explicit [[{to_id}]] (v{from_doc.version}→v{new_version})",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[KNOWLEDGE_EDGE_PROMOTE] changelog 적재 실패: %s", e)

    # _log + _index
    try:
        append_log_entry(
            operator=operator,
            change_type="update",
            doc_id=from_id,
            version=new_version,
        )
        if from_doc.category:
            rebuild_index(from_doc.category)
    except Exception as e:  # noqa: BLE001
        logger.warning("[KNOWLEDGE_EDGE_PROMOTE] log/index 갱신 실패: %s", e)

    # ChromaDB sync — 본문이 바뀌었으므로 재임베딩.
    _sync_doc_to_chroma(updated_doc)

    return {
        "from": from_id,
        "to": to_id,
        "newVersion": int(new_version),
        "linkAdded": True,
        "anchorText": anchor,
    }


# ── 상세 조회 ─────────────────────────────────────────────────────────────


@router.get("/{doc_id:path}")
async def get_document(doc_id: str):
    """문서 상세 조회"""
    chroma_hashes = _get_chroma_hashes()
    doc = read_md_file(doc_id, chroma_hashes)

    if not doc:
        raise NotFoundError(
            "문서를 찾을 수 없습니다",
            details={"docId": doc_id},
        )

    return _doc_to_response(doc)


# ── POST /knowledge (Karpathy v2 — schema 강제, link 파싱, log/index 자동 갱신) ──


@router.post(
    "",
    status_code=201,
    summary="지식문서 등록 (Karpathy v2)",
    description=(
        "**Karpathy v2 정책 (P2)** — `page_type` (5종 enum), `category` (schema enum), "
        "`slug` (영문 kebab-case) 모두 필수. id = `{category}/{slug}` 가 자동 생성된다. "
        "본문의 `[[...]]` 가 자동 파싱되어 `links` 필드를 채우고, `_log.md` 와 "
        "`_index-{category}.md` 가 자동 갱신된다."
    ),
)
async def create_document(data: KnowledgeCreate, db: AsyncSession = Depends(get_db)):
    schema = load_schema()

    # 1) schema 검증 (multi-service v3 P1: service 도 라우터에서 재검증 — Pydantic
    #    field_validator 가 이미 한 번 호출하지만, schema 부재/캐시 일관성 안전망)
    try:
        validate_service(data.service, schema=schema)
        validate_page_type(data.page_type, schema=schema)
        validate_category(data.category, schema=schema)
        validate_slug(data.slug, schema=schema)
    except SchemaValidationError as exc:
        _raise_schema_violation(exc)

    # 2) id 생성 + 충돌 검사
    doc_id = f"{data.category}/{data.slug}"
    existing = read_md_file(doc_id)
    if existing is not None:
        raise ConflictError(
            "동일 id 의 지식문서가 이미 존재합니다",
            details={"id": doc_id, "category": data.category, "slug": data.slug},
        )

    # 3) link 파싱
    links = parse_links(data.content)

    # 4) extra metadata
    extra_metadata = {}
    if data.api:
        extra_metadata["api"] = data.api

    # 5) 파일 저장 (multi-service v3 P1: frontmatter 에 service 보존)
    doc = write_md_file(
        doc_id=doc_id,
        title=data.title,
        content=data.content,
        category=data.category,
        tags=data.tags,
        source=data.source or "",
        extra_metadata=extra_metadata if extra_metadata else None,
        page_type=data.page_type,
        version=1,
        links=links,
        raw_source_id=data.raw_source_id,
        service=data.service,
        source_url=data.source_url,
    )

    # 6) changelog (create)
    operator = data.operator or "cli"
    try:
        await add_changelog(
            db,
            knowledge_id=doc_id,
            version=1,
            change_type="create",
            operator=operator,
            diff_summary=f"create {doc_id} v1 by {operator}",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[KNOWLEDGE_CREATE] changelog 적재 실패 — 파일은 보존됨: %s", e)

    # 7) _log.md + _index 갱신
    try:
        append_log_entry(operator=operator, change_type="create", doc_id=doc_id, version=1)
        rebuild_index(data.category)
    except Exception as e:  # noqa: BLE001
        logger.warning("[KNOWLEDGE_CREATE] log/index 갱신 실패: %s", e)

    # 7b) ChromaDB chunk-aware sync (P3 §3.1)
    _sync_doc_to_chroma(doc)

    # 8) warnings (15.4)
    all_docs = list_md_files()
    warns = _build_warnings(doc, all_docs)

    return _doc_to_response(doc, warnings=warns)


# ── PUT /knowledge/{id} (Karpathy v2 — 부분 업데이트 + version++ + changelog) ──


@router.put("/{doc_id:path}")
async def update_document(
    doc_id: str,
    data: KnowledgeUpdate,
    db: AsyncSession = Depends(get_db),
):
    schema = load_schema()
    existing = read_md_file(doc_id)
    if not existing:
        raise NotFoundError(
            "문서를 찾을 수 없습니다",
            details={"docId": doc_id},
        )

    # 변경 가능 필드 결정 (부분 업데이트)
    new_title = data.title if data.title is not None else existing.title
    new_content = data.content if data.content is not None else existing.content
    new_category = data.category if data.category is not None else existing.category
    new_page_type = data.page_type if data.page_type is not None else existing.page_type
    new_tags = data.tags if data.tags is not None else list(existing.tags)
    new_source = data.source if data.source is not None else existing.source
    new_raw_source_id = (
        data.raw_source_id if data.raw_source_id is not None else existing.raw_source_id
    )
    # multi-service v3 P1: PUT 으로 service 변경 가능. 미지정 시 기존 값 유지.
    new_service = data.service if data.service is not None else (existing.service or "unknown")
    # source_url: 미지정(None) 이면 기존 유지. 빈 문자열 명시 시 제거 (write_md_file 가
    # 빈 문자열 → None 으로 정규화하여 frontmatter 에서 빠짐).
    if data.source_url is not None:
        new_source_url: Optional[str] = data.source_url
    else:
        new_source_url = existing.source_url

    # schema 검증 (변경된 enum 필드)
    try:
        if data.page_type is not None:
            validate_page_type(new_page_type, schema=schema)
        if data.category is not None:
            validate_category(new_category, schema=schema)
        if data.service is not None:
            validate_service(new_service, schema=schema)
    except SchemaValidationError as exc:
        _raise_schema_violation(exc)

    # extra_metadata merge
    extra_metadata = dict(existing.extra_metadata) if existing.extra_metadata else {}
    if data.api is not None:
        if data.api:
            extra_metadata["api"] = data.api
        else:
            extra_metadata.pop("api", None)

    # link 재파싱 (content 갱신과 무관하게 항상 재계산 — 안전)
    new_links = parse_links(new_content)
    new_version = (existing.version or 1) + 1

    # 카테고리 변경 시: 기존 파일을 삭제하고 새 경로에 작성 (rename)
    target_id = doc_id
    rebuild_target_categories: List[str] = []
    if data.category is not None and new_category and new_category != existing.category:
        # legacy flat id 도 가능하므로 안전하게 slug 추출
        if "/" in doc_id:
            _, _, slug = doc_id.partition("/")
        else:
            slug = doc_id
        new_id = f"{new_category}/{slug}"
        # 새 위치에 이미 존재 시 409
        if read_md_file(new_id) is not None:
            raise ConflictError(
                "이동 대상 id 가 이미 존재합니다",
                details={"id": new_id},
            )
        # old 삭제
        delete_md_file(doc_id)
        target_id = new_id
        rebuild_target_categories.append(existing.category or "")

    # 파일 쓰기 (multi-service v3 P1: service 보존)
    doc = write_md_file(
        doc_id=target_id,
        title=new_title,
        content=new_content,
        category=new_category or "",
        tags=new_tags,
        source=new_source or "",
        created=existing.created,
        extra_metadata=extra_metadata if extra_metadata else None,
        page_type=new_page_type,
        version=new_version,
        links=new_links,
        raw_source_id=new_raw_source_id,
        service=new_service,
        source_url=new_source_url,
    )

    # changelog (update)
    operator = data.operator or "cli"
    changelog_id: Optional[str] = None
    try:
        row = await add_changelog(
            db,
            knowledge_id=target_id,
            version=new_version,
            change_type="update",
            operator=operator,
            diff_summary=f"v{existing.version}→v{new_version} by {operator}",
        )
        changelog_id = row.id
    except Exception as e:  # noqa: BLE001
        logger.warning("[KNOWLEDGE_UPDATE] changelog 적재 실패: %s", e)

    # _log + index
    try:
        append_log_entry(
            operator=operator,
            change_type="update",
            doc_id=target_id,
            version=new_version,
        )
        # 새 카테고리 + (rename 이면 옛 카테고리도) 재빌드
        if new_category:
            rebuild_target_categories.append(new_category)
        for cat in {c for c in rebuild_target_categories if c}:
            rebuild_index(cat)
    except Exception as e:  # noqa: BLE001
        logger.warning("[KNOWLEDGE_UPDATE] log/index 갱신 실패: %s", e)

    # ChromaDB chunk-aware sync (P3) — rename 시 옛 doc_id row 삭제 후 새 id 적재
    if target_id != doc_id:
        try:
            from ...services.embedding import get_vector_db
            get_vector_db().delete_document(doc_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("[KNOWLEDGE_UPDATE] chroma 옛 id 삭제 실패: %s", e)
    _sync_doc_to_chroma(doc)

    resp = _doc_to_response(doc)
    if changelog_id:
        resp["changelogId"] = changelog_id
    return resp


# ── DELETE /knowledge/{id} (Karpathy v2 — backlink 보호 + force 마커 치환) ──


@router.delete("/{doc_id:path}")
async def delete_document(
    doc_id: str,
    force: bool = Query(default=False, description="true 면 backlink 보유 페이지도 자동 치환 후 강제 삭제"),
    operator: str = Query(default="cli", description="changelog operator"),
    db: AsyncSession = Depends(get_db),
):
    existing = read_md_file(doc_id)
    if not existing:
        raise NotFoundError(
            "문서를 찾을 수 없습니다",
            details={"docId": doc_id},
        )

    # backlink 계산
    all_docs = list_md_files()
    backlink_owners = [
        d for d in all_docs
        if d.id != doc_id and has_link_to(d.content, doc_id)
    ]
    backlink_ids = sorted(d.id for d in backlink_owners)

    if backlink_owners and not force:
        # 409 + 응답 body 에 backlinks 포함 (envelope details 로 운반)
        raise ConflictError(
            "이 문서를 가리키는 backlink 가 존재합니다. force=true 로 강제 삭제하세요.",
            details={"docId": doc_id, "backlinks": backlink_ids},
        )

    affected_categories: set[str] = set()
    if existing.category:
        affected_categories.add(existing.category)

    # 강제 삭제 시 backlink 보유 페이지를 [[deleted:{id}]] 로 자동 치환
    if force and backlink_owners:
        sys_operator = "system:delete-force"
        for owner in backlink_owners:
            new_content = replace_link_with_deleted(owner.content, doc_id)
            if new_content == owner.content:
                continue  # 변화 없음 (이미 deleted 마커)
            owner_new_links = parse_links(new_content)
            owner_new_version = (owner.version or 1) + 1
            # owner 파일 다시 쓰기 (multi-service v3 P1: service 보존)
            write_md_file(
                doc_id=owner.id,
                title=owner.title,
                content=new_content,
                category=owner.category,
                tags=owner.tags,
                source=owner.source,
                created=owner.created,
                extra_metadata=owner.extra_metadata if owner.extra_metadata else None,
                page_type=owner.page_type,
                version=owner_new_version,
                links=owner_new_links,
                raw_source_id=owner.raw_source_id,
                service=owner.service or "unknown",
                source_url=owner.source_url,
            )
            try:
                await add_changelog(
                    db,
                    knowledge_id=owner.id,
                    version=owner_new_version,
                    change_type="lint-fix",
                    operator=sys_operator,
                    diff_summary=f"[[{doc_id}]] → [[deleted:{doc_id}]] (force delete cascade)",
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("[KNOWLEDGE_DELETE_FORCE] cascade changelog 실패: %s", e)
            try:
                append_log_entry(
                    operator=sys_operator,
                    change_type="update",
                    doc_id=owner.id,
                    version=owner_new_version,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("[KNOWLEDGE_DELETE_FORCE] cascade log 실패: %s", e)
            if owner.category:
                affected_categories.add(owner.category)
            # ChromaDB chunk-aware sync (P3) — cascade 후 owner 본문이 갱신됨
            owner_after = read_md_file(owner.id)
            if owner_after is not None:
                _sync_doc_to_chroma(owner_after)

    # 실제 삭제
    if not delete_md_file(doc_id):
        raise NotFoundError(
            "문서를 찾을 수 없습니다",
            details={"docId": doc_id},
        )

    # ChromaDB에서도 삭제 (best-effort)
    try:
        from ...services.embedding import get_vector_db
        vector_db = get_vector_db()
        vector_db.delete_document(doc_id)
    except Exception as e:
        logger.warning(f"ChromaDB 삭제 실패: {doc_id} - {e}")

    # changelog (delete)
    try:
        await add_changelog(
            db,
            knowledge_id=doc_id,
            version=existing.version or 1,
            change_type="delete",
            operator=operator,
            diff_summary=f"delete {doc_id} (force={force}) by {operator}",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[KNOWLEDGE_DELETE] changelog 적재 실패: %s", e)

    # _log + index
    try:
        append_log_entry(
            operator=operator,
            change_type="delete",
            doc_id=doc_id,
            version=existing.version or 1,
        )
        for cat in affected_categories:
            rebuild_index(cat)
    except Exception as e:  # noqa: BLE001
        logger.warning("[KNOWLEDGE_DELETE] log/index 갱신 실패: %s", e)

    return {
        "deleted": True,
        "docId": doc_id,
        "force": force,
        "cascadedBacklinks": backlink_ids if force else [],
    }


# ── 기존 sync/search/from-instance (유지) ──────────────────────────────────


def _run_bulk_sync():
    """백그라운드에서 전체 문서 동기화 실행"""
    from ...services.embedding import get_vector_db

    try:
        vector_db = get_vector_db()
    except Exception as e:
        with _bulk_sync_lock:
            _bulk_sync_state["status"] = "failed"
            _bulk_sync_state["error"] = str(e)
        return

    docs = list_md_files()
    with _bulk_sync_lock:
        _bulk_sync_state["total"] = len(docs)

    synced = 0
    failed = 0
    for doc in docs:
        try:
            content_hash = compute_hash(doc.content)
            meta: Dict[str, Any] = {
                "title": doc.title,
                "category": doc.category or "",
                "source": doc.source or "",
                "content_hash": content_hash,
            }
            if doc.source_url:
                meta["source_url"] = doc.source_url
            vector_db.add_document(
                doc_id=doc.id,
                content=doc.content,
                metadata=meta,
            )
            synced += 1
        except Exception as e:
            logger.error(f"문서 동기화 실패: {doc.id} - {e}")
            failed += 1

        with _bulk_sync_lock:
            _bulk_sync_state["synced"] = synced
            _bulk_sync_state["failed"] = failed

    with _bulk_sync_lock:
        _bulk_sync_state["status"] = "completed"


@router.post("/sync")
async def sync_documents(
    id: Optional[str] = Query(None, description="특정 문서 ID (없으면 전체 동기화)"),
    background_tasks: BackgroundTasks = None,
):
    """벡터 DB 동기화 (단일: 즉시, 전체: 백그라운드)"""
    from ...services.embedding import get_vector_db

    try:
        vector_db = get_vector_db()
    except Exception as e:
        raise AppException(
            f"벡터 DB 초기화 실패: {e}",
            code="VECTOR_DB_UNAVAILABLE",
            status_code=503,
        )

    if id:
        # 단일 문서 동기화 (기존 동기 방식 유지)
        doc = read_md_file(id)
        if not doc:
            raise NotFoundError(
                "문서를 찾을 수 없습니다",
                details={"docId": id},
            )

        content_hash = compute_hash(doc.content)
        single_meta: Dict[str, Any] = {
            "title": doc.title,
            "category": doc.category or "",
            "source": doc.source or "",
            "content_hash": content_hash,
        }
        if doc.source_url:
            single_meta["source_url"] = doc.source_url
        vector_db.add_document(
            doc_id=doc.id,
            content=doc.content,
            metadata=single_meta,
        )

        # 동기화 후 상태 재조회
        chroma_hashes = vector_db.get_all_document_hashes()
        updated_doc = read_md_file(id, chroma_hashes)
        return {
            "synced": 1,
            "document": _doc_to_response(updated_doc) if updated_doc else None,
        }
    else:
        # 전체 동기화: 이미 실행 중이면 중복 방지
        with _bulk_sync_lock:
            if _bulk_sync_state["status"] == "running":
                return {
                    "message": "이미 일괄 동기화가 진행 중입니다",
                    **_bulk_sync_state,
                }
            _bulk_sync_state["status"] = "running"
            _bulk_sync_state["total"] = 0
            _bulk_sync_state["synced"] = 0
            _bulk_sync_state["failed"] = 0
            _bulk_sync_state["started_at"] = time.time()
            _bulk_sync_state.pop("error", None)

        background_tasks.add_task(_run_bulk_sync)
        return {"message": "일괄 동기화가 시작되었습니다", "status": "running"}


# ``GET /sync/status`` 는 ``GET /{doc_id:path}`` 가로채기 방지를 위해 위쪽에서 정의.


@router.post("/search")
async def search_documents(request: KnowledgeSearchRequest):
    """유사도 검색 (로컬 ONNX 임베딩 + ChromaDB)"""
    from ...services.embedding import get_vector_db

    try:
        vector_db = get_vector_db()

        where_filter = None
        if request.category:
            where_filter = {"category": request.category}

        search_results = await vector_db.search_async(
            query=request.query,
            top_k=request.topK,
            where=where_filter,
        )

        # 파일에서 전체 문서 읽어서 응답 구성
        chroma_hashes = vector_db.get_all_document_hashes()
        results = []
        for sr in search_results:
            doc = read_md_file(sr.id, chroma_hashes)
            if doc:
                results.append({
                    "document": _doc_to_response(doc),
                    "score": sr.score,
                })

        return results

    except Exception as e:
        logger.error(f"벡터 검색 실패: {e}")
        # 폴백: 파일 내 텍스트 검색
        docs = list_md_files()

        if request.category:
            docs = [d for d in docs if d.category == request.category]

        docs = docs[:request.topK]

        return [
            {"document": _doc_to_response(doc), "score": 0.5}
            for doc in docs
        ]


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2b: 인스턴스 → 지식문서 프로모션 (CLI 명시 요청 전용)
# ─────────────────────────────────────────────────────────────────────────────

class KnowledgeFromInstanceRequest(BaseModel):
    """인스턴스(실행 결과)를 지식문서로 승격하는 요청.

    설계 원칙(섹션 6):
    - 자동 지식화 금지 — 사용자가 인스턴스를 검토한 뒤 CLI가 명시 호출한다.
    - 동일 title 이 존재하면 409 Conflict 를 반환해 CLI 가 suffix 로 재시도하도록 유도.
    """

    instanceId: str = Field(..., description="프로모션할 실행 인스턴스 ID")
    title: str = Field(..., min_length=1, max_length=200, description="지식문서 제목")
    category: Optional[str] = Field(default="", description="지식문서 카테고리")
    tags: List[str] = Field(default_factory=list, description="태그 리스트")


def _render_instance_markdown(
    title: str,
    execution: WorkflowExecution,
    entries: List[WarehouseEntry],
) -> str:
    """인스턴스 데이터를 읽기 좋은 마크다운으로 변환한다."""
    lines: List[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(
        f"> 이 문서는 실행 인스턴스 `{execution.id}` 에서 자동 프로모션되었습니다."
    )
    lines.append("")
    lines.append("## 실행 메타데이터")
    lines.append("")
    lines.append(f"- instanceId: `{execution.id}`")
    lines.append(f"- workflowId: `{execution.workflow_id}`")
    lines.append(
        f"- status: `{execution.status.value if execution.status else 'unknown'}`"
    )
    if execution.started_at:
        lines.append(f"- startedAt: `{execution.started_at.isoformat()}`")
    if execution.completed_at:
        lines.append(f"- completedAt: `{execution.completed_at.isoformat()}`")
    if execution.error_message:
        lines.append(f"- errorMessage: `{execution.error_message}`")
        if execution.error_node_id:
            lines.append(f"- errorNodeId: `{execution.error_node_id}`")
    lines.append("")

    # 입력
    if execution.input_data:
        lines.append("## 입력 (inputData)")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(execution.input_data, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    # 최종 출력
    if execution.output_data is not None:
        lines.append("## 최종 출력 (outputData)")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(execution.output_data, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    # 노드별 결과
    if execution.node_results:
        lines.append("## 노드별 결과 (nodeResults)")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(execution.node_results, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    # 창고 적재 항목
    if entries:
        lines.append(f"## 창고 적재 항목 ({len(entries)}건)")
        lines.append("")
        for idx, entry in enumerate(entries, 1):
            lines.append(f"### #{idx} — node `{entry.node_instance_id}`")
            lines.append("")
            if entry.created_at:
                lines.append(f"- createdAt: `{entry.created_at.isoformat()}`")
            if entry.dedup_key:
                lines.append(f"- dedupKey: `{entry.dedup_key}`")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(entry.data, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")

    return "\n".join(lines).strip() + "\n"


@router.post(
    "/from-instance",
    status_code=201,
    summary="인스턴스 → 지식문서 프로모션",
    description=(
        "CLI가 사용자의 명시 요청을 받아 실행 인스턴스를 지식문서로 승격한다. "
        "인스턴스의 ``outputData``, ``nodeResults``, 창고 적재 항목을 "
        "마크다운으로 포맷팅하여 ``data/knowledge`` 에 저장한다."
    ),
    response_description="생성된 지식문서의 camelCase 레코드",
)
async def promote_instance_to_knowledge(
    request: KnowledgeFromInstanceRequest,
    db: AsyncSession = Depends(get_db),
):
    """인스턴스 1건을 지식문서로 프로모션."""
    if not request.title.strip():
        raise ValidationError(
            "title 은 공백일 수 없습니다",
            details={"field": "title"},
        )

    # 1) 인스턴스 조회
    ex_result = await db.execute(
        select(WorkflowExecution).where(WorkflowExecution.id == request.instanceId)
    )
    execution: Optional[WorkflowExecution] = ex_result.scalar_one_or_none()
    if execution is None:
        raise NotFoundError(
            "실행 인스턴스를 찾을 수 없습니다",
            details={"instanceId": request.instanceId},
        )

    # 2) 해당 인스턴스의 창고 적재 항목 수집 (최대 100)
    entry_stmt = (
        select(WarehouseEntry)
        .where(WarehouseEntry.execution_id == request.instanceId)
        .order_by(WarehouseEntry.created_at.asc())
        .limit(100)
    )
    entries = list((await db.execute(entry_stmt)).scalars().all())

    # 3) 마크다운 렌더링
    content = _render_instance_markdown(request.title, execution, entries)

    # 4) 중복 title 감지 — 파일 시스템을 직접 점검한다.
    from ...services.knowledge_file_service import _knowledge_dir, _sanitize_filename
    import os as _os

    # 제목 정규화 로직은 knowledge_file_service.generate_doc_id 와 동일해야 한다.
    import re as _re
    sanitized = _re.sub(r'[^가-힣a-zA-Z0-9\s-]', '', request.title)
    sanitized = _re.sub(r'\s+', '-', sanitized.strip())
    sanitized = sanitized.lower() if sanitized.isascii() else sanitized
    sanitized = _sanitize_filename(sanitized) if sanitized else ""

    if sanitized:
        expected_path = _os.path.join(_knowledge_dir(), f"{sanitized}.md")
        if _os.path.exists(expected_path):
            raise ConflictError(
                "동일한 제목의 지식문서가 이미 존재합니다",
                details={
                    "title": request.title,
                    "existingDocId": sanitized,
                },
            )

    base_id = generate_doc_id(request.title)

    # 5) 파일 작성
    doc = write_md_file(
        doc_id=base_id,
        title=request.title,
        content=content,
        category=request.category or "",
        tags=request.tags,
        source=f"instance:{request.instanceId}",
        extra_metadata={
            "promotedFromInstance": request.instanceId,
            "workflowId": execution.workflow_id,
        },
    )

    # 6) ChromaDB 동기화 (best-effort — 실패해도 파일은 보존됨)
    try:
        from ...services.embedding import get_vector_db

        vector_db = get_vector_db()
        content_hash = compute_hash(content)
        vector_db.add_document(
            doc_id=doc.id,
            content=content,
            metadata={
                "title": doc.title,
                "category": doc.category or "",
                "source": doc.source or "",
                "content_hash": content_hash,
                "promoted_from_instance": request.instanceId,
            },
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[KNOWLEDGE_PROMOTE] ChromaDB 동기화 실패 — 파일은 보존됨: %s",
            e,
        )

    return _doc_to_response(doc)
