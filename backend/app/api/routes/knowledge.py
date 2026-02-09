"""
Knowledge Base API Routes

로컬 ONNX 임베딩 + ChromaDB 벡터 검색
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
import logging

from ...core.database import get_db, async_session_maker
from ...models.knowledge import KnowledgeDocument, SyncStatus
from ...schemas.knowledge import (
    KnowledgeCreate, KnowledgeUpdate,
    KnowledgeSearchRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def to_camel_response(doc: KnowledgeDocument) -> dict:
    """KnowledgeDocument ORM 객체를 camelCase dict로 변환"""
    return {
        "id": doc.id,
        "title": doc.title,
        "filename": doc.filename,
        "content": doc.content,
        "summary": doc.summary,
        "vectorId": doc.vector_id,
        "syncStatus": doc.sync_status.value if doc.sync_status else None,
        "lastSyncedAt": doc.last_synced_at.isoformat() if doc.last_synced_at else None,
        "tokenCount": doc.token_count,
        "source": doc.source,
        "category": doc.category,
        "tags": doc.tags,
        "metadata": doc.doc_metadata,
        "createdAt": doc.created_at.isoformat() if doc.created_at else None,
        "updatedAt": doc.updated_at.isoformat() if doc.updated_at else None,
    }


@router.get("")
async def list_documents(
    category: Optional[str] = Query(None, description="카테고리 필터"),
    sync_status: Optional[SyncStatus] = Query(None, description="동기화 상태 필터"),
    q: Optional[str] = Query(None, description="검색어 (제목, 내용)"),
    skip: int = Query(0, ge=0, description="건너뛸 항목 수"),
    limit: int = Query(100, ge=1, le=500, description="최대 항목 수"),
    db: AsyncSession = Depends(get_db),
):
    """문서 목록 조회"""
    query = select(KnowledgeDocument)

    if category:
        query = query.where(KnowledgeDocument.category == category)
    if sync_status:
        query = query.where(KnowledgeDocument.sync_status == sync_status)
    if q:
        query = query.where(
            (KnowledgeDocument.title.ilike(f"%{q}%")) | (KnowledgeDocument.content.ilike(f"%{q}%"))
        )

    query = query.order_by(KnowledgeDocument.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    docs = result.scalars().all()
    return [to_camel_response(doc) for doc in docs]


@router.get("/{doc_id}")
async def get_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    """문서 상세 조회"""
    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")

    return to_camel_response(doc)


@router.post("", status_code=201)
async def create_document(
    data: KnowledgeCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """문서 생성"""
    # 토큰 수 계산 (간단한 추정: 문자수 / 4)
    token_count = len(data.content) // 4

    # 스키마 데이터를 모델 필드명으로 변환 (metadata -> doc_metadata)
    doc_data = data.model_dump()
    if "metadata" in doc_data:
        doc_data["doc_metadata"] = doc_data.pop("metadata")

    doc = KnowledgeDocument(
        id=f"doc-{uuid.uuid4().hex[:8]}",
        token_count=token_count,
        sync_status=SyncStatus.PENDING,
        **doc_data,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # 백그라운드에서 벡터 DB 동기화
    background_tasks.add_task(sync_document_to_vector_db, doc.id)

    return to_camel_response(doc)


@router.patch("/{doc_id}")
async def update_document(
    doc_id: str,
    data: KnowledgeUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """문서 수정"""
    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")

    update_data = data.model_dump(exclude_unset=True)

    # 스키마 필드명을 모델 필드명으로 변환 (metadata -> doc_metadata)
    if "metadata" in update_data:
        update_data["doc_metadata"] = update_data.pop("metadata")

    # 내용이 변경되면 토큰 수 재계산 및 재동기화
    if "content" in update_data:
        update_data["token_count"] = len(update_data["content"]) // 4
        update_data["sync_status"] = SyncStatus.PENDING

    for key, value in update_data.items():
        setattr(doc, key, value)

    await db.commit()
    await db.refresh(doc)

    # 재동기화 필요시 백그라운드 작업 추가
    if doc.sync_status == SyncStatus.PENDING:
        background_tasks.add_task(sync_document_to_vector_db, doc.id)

    return to_camel_response(doc)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """문서 삭제"""
    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")

    # 벡터 DB에서도 삭제
    background_tasks.add_task(delete_from_vector_db, doc.id)

    await db.delete(doc)
    await db.commit()


@router.post("/{doc_id}/sync")
async def sync_document(
    doc_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """문서 벡터 DB 동기화 (수동)"""
    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")

    doc.sync_status = SyncStatus.PENDING
    await db.commit()
    await db.refresh(doc)

    background_tasks.add_task(sync_document_to_vector_db, doc.id)

    return to_camel_response(doc)


@router.post("/search")
async def search_documents(
    request: KnowledgeSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    유사도 검색 (로컬 ONNX 임베딩 + ChromaDB)

    완전 오프라인으로 동작하며 외부 API 호출 없이
    로컬 모델로 임베딩을 생성하고 검색합니다.
    """
    from ...services.embedding import get_vector_db

    try:
        vector_db = get_vector_db()

        # 필터 조건
        where_filter = None
        if request.category:
            where_filter = {"category": request.category}

        # 벡터 검색
        search_results = await vector_db.search_async(
            query=request.query,
            top_k=request.top_k,
            where=where_filter,
        )

        # DB에서 문서 상세 정보 조회
        results = []
        for sr in search_results:
            result = await db.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.id == sr.id)
            )
            doc = result.scalar_one_or_none()

            if doc:
                results.append({
                    "document": to_camel_response(doc),
                    "score": sr.score,
                })

        return results

    except Exception as e:
        logger.error(f"벡터 검색 실패: {e}")
        # 폴백: 단순 텍스트 검색
        query = select(KnowledgeDocument)

        if request.category:
            query = query.where(KnowledgeDocument.category == request.category)

        query = query.limit(request.top_k)
        result = await db.execute(query)
        docs = result.scalars().all()

        return [
            {"document": to_camel_response(doc), "score": 0.5}
            for doc in docs
        ]


# ─────────────────────────────────────────────────────────────────────────────
# Background Tasks
# ─────────────────────────────────────────────────────────────────────────────

async def sync_document_to_vector_db(doc_id: str):
    """
    벡터 DB 동기화 (백그라운드)

    1. 문서 조회
    2. 로컬 ONNX 모델로 임베딩 생성
    3. ChromaDB에 upsert
    4. 동기화 상태 업데이트
    """
    from ...services.embedding import get_vector_db

    try:
        async with async_session_maker() as db:
            # 1. 문서 조회
            result = await db.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
            )
            doc = result.scalar_one_or_none()

            if not doc:
                logger.warning(f"동기화 대상 문서 없음: {doc_id}")
                return

            # 2-3. 벡터 DB에 추가 (임베딩은 자동 생성됨)
            vector_db = get_vector_db()
            vector_db.add_document(
                doc_id=doc.id,
                content=doc.content,
                metadata={
                    "title": doc.title,
                    "category": doc.category or "",
                    "source": doc.source or "",
                },
            )

            # 4. 동기화 상태 업데이트
            doc.vector_id = doc.id  # ChromaDB는 동일 ID 사용
            doc.sync_status = SyncStatus.SYNCED
            await db.commit()

            logger.info(f"벡터 DB 동기화 완료: {doc_id}")

    except Exception as e:
        logger.error(f"벡터 DB 동기화 실패: {doc_id} - {e}")

        # 에러 상태 업데이트
        try:
            async with async_session_maker() as db:
                result = await db.execute(
                    select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
                )
                doc = result.scalar_one_or_none()
                if doc:
                    doc.sync_status = SyncStatus.ERROR
                    await db.commit()
        except Exception:
            pass


async def delete_from_vector_db(doc_id: str):
    """벡터 DB에서 삭제 (백그라운드)"""
    from ...services.embedding import get_vector_db

    try:
        vector_db = get_vector_db()
        vector_db.delete_document(doc_id)
        logger.info(f"벡터 DB에서 삭제: {doc_id}")
    except Exception as e:
        logger.error(f"벡터 DB 삭제 실패: {doc_id} - {e}")
