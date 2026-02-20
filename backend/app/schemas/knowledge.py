"""
Knowledge Document Schemas (파일 기반 - camelCase)
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class KnowledgeCreate(BaseModel):
    """지식 문서 생성"""
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    source: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class KnowledgeUpdate(BaseModel):
    """지식 문서 수정 (PUT - 전체 교체)"""
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    source: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class KnowledgeSearchRequest(BaseModel):
    """유사도 검색 요청"""
    query: str = Field(..., min_length=1)
    topK: int = Field(default=5, ge=1, le=20, alias="topK")
    category: Optional[str] = None
