"""
Knowledge Document Schemas (프론트엔드 타입에 맞춤 - camelCase)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from ..models.knowledge import SyncStatus


class KnowledgeBase(BaseModel):
    """지식 문서 기본 스키마"""
    title: str = Field(..., min_length=1, max_length=200)
    filename: Optional[str] = None
    content: str = Field(..., min_length=1)
    summary: Optional[str] = None
    source: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeCreate(KnowledgeBase):
    """지식 문서 생성"""
    pass


class KnowledgeUpdate(BaseModel):
    """지식 문서 수정"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    filename: Optional[str] = None
    content: Optional[str] = Field(None, min_length=1)
    summary: Optional[str] = None
    source: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class KnowledgeResponse(BaseModel):
    """지식 문서 응답 (camelCase)"""
    id: str
    title: str
    filename: Optional[str] = None
    content: str
    summary: Optional[str] = None
    vectorId: Optional[str] = Field(None, serialization_alias="vectorId")
    syncStatus: SyncStatus = Field(serialization_alias="syncStatus")
    lastSyncedAt: Optional[datetime] = Field(None, serialization_alias="lastSyncedAt")
    tokenCount: int = Field(serialization_alias="tokenCount")
    source: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    createdAt: datetime = Field(serialization_alias="createdAt")
    updatedAt: datetime = Field(serialization_alias="updatedAt")

    class Config:
        from_attributes = True
        populate_by_name = True

    @classmethod
    def from_orm_with_camel(cls, obj):
        """ORM 객체를 camelCase 응답으로 변환"""
        return cls(
            id=obj.id,
            title=obj.title,
            filename=obj.filename,
            content=obj.content,
            summary=obj.summary,
            vectorId=obj.vector_id,
            syncStatus=obj.sync_status,
            lastSyncedAt=obj.last_synced_at,
            tokenCount=obj.token_count,
            source=obj.source,
            category=obj.category,
            tags=obj.tags,
            metadata=obj.doc_metadata,  # 모델에서는 doc_metadata (metadata는 SQLAlchemy 예약어)
            createdAt=obj.created_at,
            updatedAt=obj.updated_at,
        )


class KnowledgeSearchRequest(BaseModel):
    """유사도 검색 요청"""
    query: str = Field(..., min_length=1)
    topK: int = Field(default=5, ge=1, le=20, alias="topK")
    category: Optional[str] = None


class KnowledgeSearchResult(BaseModel):
    """유사도 검색 결과"""
    document: KnowledgeResponse
    score: float
