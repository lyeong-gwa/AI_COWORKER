"""
AI Node Schemas (프론트엔드 타입에 맞춤 - camelCase)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class OutputEnforcementConfig(BaseModel):
    """출력 강제 설정"""
    enabled: bool = False
    includeSchemaInPrompt: bool = False
    exampleOutput: Optional[str] = None
    validationEnabled: bool = False
    retryOnFailure: bool = False
    maxRetries: int = Field(default=3, ge=1, le=10)


class LLMConfig(BaseModel):
    """LLM 모델 설정"""
    model: str = "gpt-4o-mini"
    temperature: float = Field(default=0.7, ge=0, le=2)
    maxTokens: int = Field(default=2000, ge=100, le=100000)


class KnowledgeConfig(BaseModel):
    """지식 베이스 설정"""
    linkedIds: List[str] = Field(default_factory=list)
    filters: Dict[str, Any] = Field(default_factory=dict)
    maxTokens: int = 2000


class NodeBase(BaseModel):
    """노드 기본 스키마"""
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1)
    category: str = Field(default="general", max_length=50)
    icon: str = Field(default="🤖", max_length=10)
    color: str = Field(default="text-blue-400", max_length=50)
    tags: List[str] = Field(default_factory=list)

    linkedToolIds: List[str] = Field(default_factory=list)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)

    systemPrompt: str = Field(default="")
    userPromptTemplate: str = Field(default="")

    inputSchema: Dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}, "required": []}
    )
    outputSchema: Dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}, "required": []}
    )

    outputEnforcement: OutputEnforcementConfig = Field(default_factory=OutputEnforcementConfig)
    llmConfig: LLMConfig = Field(default_factory=LLMConfig)

    isActive: bool = True


class NodeCreate(NodeBase):
    """노드 생성"""
    pass


class NodeUpdate(BaseModel):
    """노드 수정"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=50)
    icon: Optional[str] = Field(None, max_length=10)
    color: Optional[str] = Field(None, max_length=50)
    tags: Optional[List[str]] = None

    linkedToolIds: Optional[List[str]] = None
    knowledge: Optional[KnowledgeConfig] = None

    systemPrompt: Optional[str] = None
    userPromptTemplate: Optional[str] = None

    inputSchema: Optional[Dict[str, Any]] = None
    outputSchema: Optional[Dict[str, Any]] = None

    outputEnforcement: Optional[OutputEnforcementConfig] = None
    llmConfig: Optional[LLMConfig] = None

    isActive: Optional[bool] = None


class NodeResponse(BaseModel):
    """노드 응답 (camelCase)"""
    id: str
    name: str
    description: str
    category: str
    icon: str
    color: str
    tags: List[str]

    linkedToolIds: List[str] = Field(serialization_alias="linkedToolIds")
    knowledge: Dict[str, Any]

    systemPrompt: str = Field(serialization_alias="systemPrompt")
    userPromptTemplate: str = Field(serialization_alias="userPromptTemplate")

    inputSchema: Dict[str, Any] = Field(serialization_alias="inputSchema")
    outputSchema: Dict[str, Any] = Field(serialization_alias="outputSchema")

    outputEnforcement: Dict[str, Any] = Field(serialization_alias="outputEnforcement")
    llmConfig: Dict[str, Any] = Field(serialization_alias="llmConfig")

    isActive: bool = Field(serialization_alias="isActive")
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
            category=obj.category,
            icon=obj.icon,
            color=obj.color,
            tags=obj.tags,
            linkedToolIds=obj.linked_tool_ids,
            knowledge=obj.knowledge,
            systemPrompt=obj.system_prompt,
            userPromptTemplate=obj.user_prompt_template,
            inputSchema=obj.input_schema,
            outputSchema=obj.output_schema,
            outputEnforcement=obj.output_enforcement,
            llmConfig=obj.llm_config,
            isActive=obj.is_active,
            createdAt=obj.created_at,
            updatedAt=obj.updated_at,
        )


class NodeTestRequest(BaseModel):
    """노드 테스트 요청"""
    inputData: Dict[str, Any] = Field(default_factory=dict)
    mockToolResults: Optional[Dict[str, Any]] = None
    mockKnowledge: Optional[str] = None


class NodeTestResponse(BaseModel):
    """노드 테스트 응답"""
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None
    errorType: Optional[str] = None

    # 실행 로그
    logs: List[Dict[str, Any]] = Field(default_factory=list)

    # 중간 결과
    renderedPrompt: Optional[str] = None
    toolResults: Optional[Dict[str, Any]] = None
    llmResponse: Optional[str] = None

    # 검증 결과
    validationPassed: Optional[bool] = None
    validationErrors: Optional[List[str]] = None

    # 메트릭
    executionTimeMs: float = 0
    tokenUsage: Optional[Dict[str, int]] = None
