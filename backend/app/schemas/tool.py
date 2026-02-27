"""
Tool Schemas - API 문서 실행용 스키마
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ApiDocExecuteRequest(BaseModel):
    """지식 문서 기반 API 실행 요청"""
    docId: str = Field(..., description="도구-API 지식 문서 ID")
    inputData: Dict[str, Any] = Field(default_factory=dict, description="템플릿 변수 데이터")


class ToolTestResponse(BaseModel):
    """API 실행 응답"""
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None
    executionTimeMs: float = 0
    logs: List[str] = Field(default_factory=list)
