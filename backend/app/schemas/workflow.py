"""
Workflow Schemas (프론트엔드 타입에 맞춤 - camelCase)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from ..models.workflow import WorkflowStatus, ExecutionStatus


# ─────────────────────────────────────────────────────────────────────────────
# Workflow Node & Connection
# ─────────────────────────────────────────────────────────────────────────────

class Position(BaseModel):
    """캔버스 위치"""
    x: float = 0
    y: float = 0


class WorkflowNodeCreate(BaseModel):
    """워크플로우 노드 생성"""
    id: str
    nodeId: str  # 연결된 AINode ID
    name: str
    position: Position = Field(default_factory=Position)
    configOverrides: Dict[str, Any] = Field(default_factory=dict)
    inputMapping: Dict[str, str] = Field(default_factory=dict)


class WorkflowNodeResponse(BaseModel):
    """워크플로우 노드 응답"""
    id: str
    nodeId: str = Field(serialization_alias="nodeId")
    name: str
    position: Dict[str, float]
    configOverrides: Dict[str, Any] = Field(serialization_alias="configOverrides")
    inputMapping: Dict[str, str] = Field(serialization_alias="inputMapping")

    class Config:
        from_attributes = True
        populate_by_name = True


class ConnectionCondition(BaseModel):
    """연결 조건"""
    field: str
    operator: str
    value: Any


class WorkflowConnectionCreate(BaseModel):
    """워크플로우 연결선 생성"""
    id: str
    sourceNodeId: str
    targetNodeId: str
    condition: Optional[ConnectionCondition] = None


class WorkflowConnectionResponse(BaseModel):
    """워크플로우 연결선 응답"""
    id: str
    sourceNodeId: str = Field(serialization_alias="sourceNodeId")
    targetNodeId: str = Field(serialization_alias="targetNodeId")
    condition: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
        populate_by_name = True


# ─────────────────────────────────────────────────────────────────────────────
# Workflow CRUD
# ─────────────────────────────────────────────────────────────────────────────

class TriggerConfig(BaseModel):
    """트리거 설정"""
    type: str = "manual"  # manual, schedule, webhook
    config: Dict[str, Any] = Field(default_factory=dict)


class ViewportConfig(BaseModel):
    """캔버스 뷰포트"""
    x: float = 0
    y: float = 0
    zoom: float = 1


class WorkflowBase(BaseModel):
    """워크플로우 기본 스키마"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    viewport: ViewportConfig = Field(default_factory=ViewportConfig)
    trigger: TriggerConfig = Field(default_factory=TriggerConfig)
    variables: Dict[str, Any] = Field(default_factory=dict)


class WorkflowCreate(WorkflowBase):
    """워크플로우 생성"""
    nodes: List[WorkflowNodeCreate] = Field(default_factory=list)
    connections: List[WorkflowConnectionCreate] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    """워크플로우 수정"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    status: Optional[WorkflowStatus] = None
    tags: Optional[List[str]] = None
    viewport: Optional[ViewportConfig] = None
    trigger: Optional[TriggerConfig] = None
    variables: Optional[Dict[str, Any]] = None
    nodes: Optional[List[WorkflowNodeCreate]] = None
    connections: Optional[List[WorkflowConnectionCreate]] = None


class WorkflowResponse(BaseModel):
    """워크플로우 응답 (camelCase)"""
    id: str
    name: str
    description: Optional[str] = None
    status: WorkflowStatus
    tags: List[str]
    viewport: Dict[str, Any]
    trigger: Dict[str, Any]
    variables: Dict[str, Any]
    nodes: List[WorkflowNodeResponse]
    connections: List[WorkflowConnectionResponse]
    createdAt: datetime = Field(serialization_alias="createdAt")
    updatedAt: datetime = Field(serialization_alias="updatedAt")

    class Config:
        from_attributes = True
        populate_by_name = True


class WorkflowSummaryResponse(BaseModel):
    """워크플로우 요약 (목록용)"""
    id: str
    name: str
    description: Optional[str] = None
    status: WorkflowStatus
    tags: List[str]
    nodeCount: int = Field(serialization_alias="nodeCount")
    createdAt: datetime = Field(serialization_alias="createdAt")
    updatedAt: datetime = Field(serialization_alias="updatedAt")

    class Config:
        from_attributes = True
        populate_by_name = True


# ─────────────────────────────────────────────────────────────────────────────
# Execution
# ─────────────────────────────────────────────────────────────────────────────

class ExecutionCreate(BaseModel):
    """실행 생성"""
    inputData: Dict[str, Any] = Field(default_factory=dict)


class NodeExecutionResult(BaseModel):
    """노드 실행 결과"""
    nodeId: str
    status: str  # pending, running, completed, failed, skipped
    inputData: Optional[Dict[str, Any]] = None
    outputData: Optional[Any] = None
    error: Optional[str] = None
    startTime: Optional[datetime] = None
    endTime: Optional[datetime] = None
    logs: List[str] = Field(default_factory=list)


class ExecutionResponse(BaseModel):
    """실행 응답 (camelCase)"""
    id: str
    workflowId: str = Field(serialization_alias="workflowId")
    status: ExecutionStatus
    inputData: Dict[str, Any] = Field(serialization_alias="inputData")
    outputData: Optional[Dict[str, Any]] = Field(None, serialization_alias="outputData")
    nodeResults: Dict[str, Any] = Field(default_factory=dict, serialization_alias="nodeResults")
    errorMessage: Optional[str] = Field(None, serialization_alias="errorMessage")
    errorNodeId: Optional[str] = Field(None, serialization_alias="errorNodeId")
    startedAt: Optional[datetime] = Field(None, serialization_alias="startedAt")
    completedAt: Optional[datetime] = Field(None, serialization_alias="completedAt")
    createdAt: datetime = Field(serialization_alias="createdAt")

    class Config:
        from_attributes = True
        populate_by_name = True


class ExecutionLogEvent(BaseModel):
    """실행 로그 이벤트 (SSE용)"""
    eventType: str  # node_start, node_complete, node_error, execution_complete
    timestamp: datetime
    nodeId: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
