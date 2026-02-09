"""
Tool Definition Schemas (프론트엔드 타입에 맞춤 - camelCase)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from ..models.tool import ToolType


class ToolBase(BaseModel):
    """도구 기본 스키마"""
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1)
    icon: str = Field(default="🔧", max_length=10)
    color: str = Field(default="text-gray-400", max_length=50)
    type: ToolType
    config: Dict[str, Any]
    tags: List[str] = Field(default_factory=list)


class ToolCreate(ToolBase):
    """도구 생성"""
    pass


class ToolUpdate(BaseModel):
    """도구 수정"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = Field(None, max_length=10)
    color: Optional[str] = Field(None, max_length=50)
    config: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class ToolResponse(BaseModel):
    """도구 응답 (camelCase)"""
    id: str
    name: str
    description: str
    type: ToolType
    icon: str
    color: str
    config: Dict[str, Any]
    tags: List[str]
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
            name=obj.name,
            description=obj.description,
            type=obj.type,
            icon=obj.icon,
            color=obj.color,
            config=obj.config,
            tags=obj.tags,
            createdAt=obj.created_at,
            updatedAt=obj.updated_at,
        )


class ToolTestRequest(BaseModel):
    """도구 테스트 요청"""
    inputData: Dict[str, Any] = Field(default_factory=dict)


class ToolTestResponse(BaseModel):
    """도구 테스트 응답"""
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None
    executionTimeMs: float = 0
    logs: List[str] = Field(default_factory=list)
