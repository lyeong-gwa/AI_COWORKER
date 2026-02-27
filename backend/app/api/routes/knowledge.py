"""
Knowledge Base API Routes

MD 파일 기반 지식 문서 관리 + ChromaDB 유사도 검색
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
import logging

from ...schemas.knowledge import (
    KnowledgeCreate, KnowledgeUpdate,
    KnowledgeSearchRequest,
)
from ...services.knowledge_file_service import (
    list_md_files, read_md_file, write_md_file, delete_md_file,
    generate_doc_id, compute_hash, KnowledgeFileDoc,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _doc_to_response(doc: KnowledgeFileDoc) -> dict:
    """KnowledgeFileDoc -> camelCase dict 응답"""
    resp = {
        "id": doc.id,
        "title": doc.title,
        "content": doc.content,
        "category": doc.category,
        "tags": doc.tags,
        "source": doc.source,
        "contentHash": doc.content_hash,
        "syncStatus": doc.sync_status,
        "createdAt": doc.created,
        "updatedAt": doc.updated,
    }
    # 도구-API 문서의 경우 api 메타데이터 포함
    if hasattr(doc, 'extra_metadata') and doc.extra_metadata.get('api'):
        resp["api"] = doc.extra_metadata["api"]
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


@router.get("")
async def list_documents(
    category: Optional[str] = Query(None, description="카테고리 필터"),
    sync_status: Optional[str] = Query(None, description="동기화 상태 필터"),
    q: Optional[str] = Query(None, description="검색어 (제목, 내용)"),
    skip: int = Query(0, ge=0, description="건너뛸 항목 수"),
    limit: int = Query(100, ge=1, le=500, description="최대 항목 수"),
):
    """문서 목록 조회 (폴더 스캔 + ChromaDB 해시 비교)"""
    chroma_hashes = _get_chroma_hashes()
    docs = list_md_files(chroma_hashes)

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
    """지식 문서의 고유 카테고리/태그 목록 반환"""
    docs = list_md_files()
    categories = sorted({d.category for d in docs if d.category})
    tags = sorted({t for d in docs for t in d.tags if t})
    return {"categories": categories, "tags": tags}


@router.get("/{doc_id}")
async def get_document(doc_id: str):
    """문서 상세 조회"""
    chroma_hashes = _get_chroma_hashes()
    doc = read_md_file(doc_id, chroma_hashes)

    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")

    return _doc_to_response(doc)


@router.post("", status_code=201)
async def create_document(data: KnowledgeCreate):
    """문서 생성 (MD 파일 작성)"""
    doc_id = generate_doc_id(data.title)

    extra_metadata = {}
    if data.api:
        extra_metadata["api"] = data.api

    doc = write_md_file(
        doc_id=doc_id,
        title=data.title,
        content=data.content,
        category=data.category or "",
        tags=data.tags,
        source=data.source or "",
        extra_metadata=extra_metadata if extra_metadata else None,
    )

    return _doc_to_response(doc)


@router.put("/{doc_id}")
async def update_document(doc_id: str, data: KnowledgeUpdate):
    """문서 수정 (MD 파일 덮어쓰기)"""
    existing = read_md_file(doc_id)
    if not existing:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")

    # Merge extra_metadata: update api if provided, otherwise keep existing
    extra_metadata = dict(existing.extra_metadata) if existing.extra_metadata else {}
    if data.api is not None:
        if data.api:
            extra_metadata["api"] = data.api
        else:
            extra_metadata.pop("api", None)

    doc = write_md_file(
        doc_id=doc_id,
        title=data.title,
        content=data.content,
        category=data.category or "",
        tags=data.tags,
        source=data.source or "",
        created=existing.created,
        extra_metadata=extra_metadata if extra_metadata else None,
    )

    return _doc_to_response(doc)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str):
    """문서 삭제 (파일 + ChromaDB)"""
    if not delete_md_file(doc_id):
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")

    # ChromaDB에서도 삭제
    try:
        from ...services.embedding import get_vector_db
        vector_db = get_vector_db()
        vector_db.delete_document(doc_id)
    except Exception as e:
        logger.warning(f"ChromaDB 삭제 실패: {doc_id} - {e}")


@router.post("/sync")
async def sync_documents(
    id: Optional[str] = Query(None, description="특정 문서 ID (없으면 전체 동기화)"),
):
    """벡터 DB 동기화 (단일 또는 전체)"""
    from ...services.embedding import get_vector_db

    try:
        vector_db = get_vector_db()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"벡터 DB 초기화 실패: {e}")

    if id:
        # 단일 문서 동기화
        doc = read_md_file(id)
        if not doc:
            raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")

        content_hash = compute_hash(doc.content)
        vector_db.add_document(
            doc_id=doc.id,
            content=doc.content,
            metadata={
                "title": doc.title,
                "category": doc.category or "",
                "source": doc.source or "",
                "content_hash": content_hash,
            },
        )

        # 동기화 후 상태 재조회
        chroma_hashes = vector_db.get_all_document_hashes()
        updated_doc = read_md_file(id, chroma_hashes)
        return {
            "synced": 1,
            "document": _doc_to_response(updated_doc) if updated_doc else None,
        }
    else:
        # 전체 동기화
        docs = list_md_files()
        synced_count = 0

        for doc in docs:
            try:
                content_hash = compute_hash(doc.content)
                vector_db.add_document(
                    doc_id=doc.id,
                    content=doc.content,
                    metadata={
                        "title": doc.title,
                        "category": doc.category or "",
                        "source": doc.source or "",
                        "content_hash": content_hash,
                    },
                )
                synced_count += 1
            except Exception as e:
                logger.error(f"문서 동기화 실패: {doc.id} - {e}")

        return {"synced": synced_count, "total": len(docs)}


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
