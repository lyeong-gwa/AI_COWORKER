"""
Workflow Schemas (프론트엔드 타입에 맞춤 - camelCase)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

from ..models.workflow import WorkflowStatus, ExecutionStatus


# ─────────────────────────────────────────────────────────────────────────────
# Workflow Node & Connection
# ─────────────────────────────────────────────────────────────────────────────


class WorkflowNodeCreate(BaseModel):
    """워크플로우 노드 생성"""
    id: str
    nodeId: str  # 연결된 AINode ID
    definitionType: str = "ai-custom"
    aiNodeId: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    name: str
    orderIndex: int = 0  # 형제 노드 안정 순번 (자동 레이아웃 tie-break)
    configOverrides: Dict[str, Any] = Field(default_factory=dict)
    inputMapping: Dict[str, str] = Field(default_factory=dict)


class WorkflowNodeResponse(BaseModel):
    """워크플로우 노드 응답"""
    id: str
    nodeId: str = Field(serialization_alias="nodeId")
    definitionType: str = Field(default="ai-custom", serialization_alias="definitionType")
    aiNodeId: Optional[str] = Field(default=None, serialization_alias="aiNodeId")
    config: Dict[str, Any] = Field(default_factory=dict)
    name: str
    orderIndex: int = Field(default=0, serialization_alias="orderIndex")
    configOverrides: Dict[str, Any] = Field(serialization_alias="configOverrides")
    inputMapping: Dict[str, str] = Field(serialization_alias="inputMapping")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


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
    sourceHandle: Optional[str] = None
    targetHandle: Optional[str] = None
    condition: Optional[ConnectionCondition] = None


class WorkflowConnectionResponse(BaseModel):
    """워크플로우 연결선 응답"""
    id: str
    sourceNodeId: str = Field(serialization_alias="sourceNodeId")
    targetNodeId: str = Field(serialization_alias="targetNodeId")
    sourceHandle: Optional[str] = Field(None, serialization_alias="sourceHandle")
    targetHandle: Optional[str] = Field(None, serialization_alias="targetHandle")
    condition: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ─────────────────────────────────────────────────────────────────────────────
# Workflow CRUD
# ─────────────────────────────────────────────────────────────────────────────

class TriggerConfig(BaseModel):
    """트리거 설정"""
    type: str = "manual"  # manual, schedule, webhook, form
    config: Dict[str, Any] = Field(default_factory=dict)


class ScheduleConfigUpdate(BaseModel):
    """워크플로우 스케줄러 설정 갱신 요청 (PATCH /workflows/{id}/schedule).

    cronExpr 는 APScheduler/croniter 5-field 표준을 따른다.
    timezone 미지정 시 Asia/Seoul 유지.
    payload 는 cron 실행 시 워크플로우의 input_data 로 전달되는 트리거 입력값.
    None 이면 기존 payload 보존, 빈 dict 면 명시적으로 비움.
    """
    enabled: bool
    cronExpr: str = Field(..., min_length=1)
    timezone: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


class WorkflowBase(BaseModel):
    """워크플로우 기본 스키마"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    trigger: TriggerConfig = Field(default_factory=TriggerConfig)
    variables: Dict[str, Any] = Field(default_factory=dict)


class WorkflowCreate(WorkflowBase):
    """워크플로우 생성"""
    createdBy: str = Field(default="cli")  # 'cli' | 'web'
    nodes: List[WorkflowNodeCreate] = Field(default_factory=list)
    connections: List[WorkflowConnectionCreate] = Field(default_factory=list)
    # 이 워크플로우를 생성한 채팅 추적(generation trace) id 목록.
    # 모델 컬럼 generation_trace_ids 로 매핑된다. 생략 시 빈 리스트.
    generationTraceIds: List[str] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    """워크플로우 수정"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    status: Optional[WorkflowStatus] = None
    tags: Optional[List[str]] = None
    trigger: Optional[TriggerConfig] = None
    variables: Optional[Dict[str, Any]] = None
    nodes: Optional[List[WorkflowNodeCreate]] = None
    connections: Optional[List[WorkflowConnectionCreate]] = None
    # 새로 추가할 채팅 추적 id 목록. 제공 시 기존 목록에 순서 보존·중복 제거로 append 된다.
    # 생략(None) 하면 기존 목록을 보존한다.
    generationTraceIds: Optional[List[str]] = None


class WorkflowResponse(BaseModel):
    """워크플로우 응답 (camelCase)"""
    id: str
    name: str
    description: Optional[str] = None
    status: WorkflowStatus
    tags: List[str]
    trigger: Dict[str, Any]
    variables: Dict[str, Any]
    createdBy: str = Field(default="cli", serialization_alias="createdBy")
    nodes: List[WorkflowNodeResponse]
    connections: List[WorkflowConnectionResponse]
    generationTraceIds: List[str] = Field(
        default_factory=list, serialization_alias="generationTraceIds"
    )
    createdAt: datetime = Field(serialization_alias="createdAt")
    updatedAt: datetime = Field(serialization_alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class WorkflowSummaryResponse(BaseModel):
    """워크플로우 요약 (목록용)"""
    id: str
    name: str
    description: Optional[str] = None
    status: WorkflowStatus
    tags: List[str]
    nodeCount: int = Field(serialization_alias="nodeCount")
    createdBy: str = Field(default="cli", serialization_alias="createdBy")
    createdAt: datetime = Field(serialization_alias="createdAt")
    updatedAt: datetime = Field(serialization_alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


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

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ExecutionLogEvent(BaseModel):
    """실행 로그 이벤트 (SSE용)"""
    eventType: str  # node_start, node_complete, node_error, execution_complete
    timestamp: datetime
    nodeId: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Warehouse (창고 데이터)
# ─────────────────────────────────────────────────────────────────────────────

class WarehouseEntryResponse(BaseModel):
    """창고 항목 응답"""
    id: str
    nodeInstanceId: str = Field(serialization_alias="nodeInstanceId")
    executionId: Optional[str] = Field(None, serialization_alias="executionId")
    data: Dict[str, Any]
    createdAt: datetime = Field(serialization_alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class WarehouseListResponse(BaseModel):
    """창고 데이터 목록 응답"""
    items: List[WarehouseEntryResponse]
    total: int
    nodeInstanceId: str = Field(serialization_alias="nodeInstanceId")


# ─────────────────────────────────────────────────────────────────────────────
# Node Queue (공장 노드 입력 큐)
# ─────────────────────────────────────────────────────────────────────────────

class QueueItemResponse(BaseModel):
    """큐 아이템 응답"""
    id: str
    nodeInstanceId: str = Field(serialization_alias="nodeInstanceId")
    executionId: Optional[str] = Field(None, serialization_alias="executionId")
    data: Dict[str, Any]
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    createdAt: datetime = Field(serialization_alias="createdAt")
    processedAt: Optional[datetime] = Field(None, serialization_alias="processedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class QueueListResponse(BaseModel):
    """큐 목록 응답"""
    items: List[QueueItemResponse]
    total: int
    pending: int
    processing: int
    nodeInstanceId: str = Field(serialization_alias="nodeInstanceId")


class FactoryMapUpdate(BaseModel):
    """팩토리 맵 업데이트"""
    nodes: Optional[List[WorkflowNodeCreate]] = None
    connections: Optional[List[WorkflowConnectionCreate]] = None


class WorkflowValidateRequest(BaseModel):
    """워크플로우 구조 사전 검증 요청 (POST /workflows/validate).

    저장 없이 nodes + connections 만 받아 validate_workflow_structure 를 실행한다.
    """
    nodes: List[WorkflowNodeCreate] = Field(default_factory=list)
    connections: List[WorkflowConnectionCreate] = Field(default_factory=list)


class WorkflowGenerateRequest(BaseModel):
    """워크플로우 자동 생성 요청 (POST /workflows/generate).

    사용자 자연어 설명으로부터 draft를 생성한다. 저장은 하지 않는다.
    baseDraft가 있거나 mode in ('edit','refine')이면 수정 모드로 동작.
    """
    description: str = Field(..., min_length=1, description="자동화하려는 업무를 자연어로 설명")
    mode: str = Field(default="create", description="'create' (신규) | 'edit'/'refine' (기존 수정)")
    baseWorkflowId: Optional[str] = Field(default=None, description="mode='edit'일 때 기준 워크플로우 ID")
    history: Optional[List[Any]] = Field(default=None, description="대화 이력 (수정 모드 컨텍스트용)")
    baseDraft: Optional[Dict[str, Any]] = Field(
        default=None,
        description="수정 모드에서 기준이 되는 현재 워크플로우 draft JSON (nodes/connections/name/description 포함)",
    )
