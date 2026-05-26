"""
API Definition Schemas - API 정의 CRUD 스키마
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class ApiParamSchema(BaseModel):
    """API 파라미터 정의"""
    name: str
    location: str = Field(alias="in", default="query")  # path, query, header, body
    type: str = "string"
    required: bool = False
    description: str = ""
    default: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class ResponseFieldSchema(BaseModel):
    """응답 필드 정의"""
    field: str
    type: str = "string"
    description: str = ""


class ApiDefinitionCreate(BaseModel):
    """API 정의 생성 요청"""
    name: str
    description: str = ""
    icon: str = "🌐"
    color: str = "text-cyan-400"
    category: str = ""
    tags: List[str] = Field(default_factory=list)
    method: str = "GET"
    urlTemplate: str
    headers: Dict[str, str] = Field(default_factory=dict)
    bodyTemplate: Optional[str] = None
    authType: str = "none"
    authConfig: Dict[str, Any] = Field(default_factory=dict)
    parameters: List[Dict[str, Any]] = Field(default_factory=list)
    responseSchema: Dict[str, Any] = Field(default_factory=dict)


class ApiDefinitionUpdate(BaseModel):
    """API 정의 수정 요청 (모든 필드 Optional)"""
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    method: Optional[str] = None
    urlTemplate: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    bodyTemplate: Optional[str] = None
    authType: Optional[str] = None
    authConfig: Optional[Dict[str, Any]] = None
    parameters: Optional[List[Dict[str, Any]]] = None
    responseSchema: Optional[Dict[str, Any]] = None
    isActive: Optional[bool] = None


class ApiTestRequest(BaseModel):
    """API 테스트 호출 요청"""
    method: str = "GET"
    url: str
    headers: Dict[str, str] = Field(default_factory=dict)
    bodyTemplate: Optional[str] = None
    inputData: Dict[str, Any] = Field(default_factory=dict)


class ApiCaptureRequest(BaseModel):
    """테스트 응답에서 스키마 자동 추출 요청"""
    responseData: Any
    urlTemplate: str = ""
