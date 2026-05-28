"""
Workflow Models - 워크플로우 (ATOMIC 패턴의 Organism)

프론트엔드 타입 정의에 맞춤
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Text, DateTime, Boolean, Enum as SQLEnum, JSON, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from ..core.database import Base


class WorkflowStatus(str, enum.Enum):
    """워크플로우 상태"""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ExecutionStatus(str, enum.Enum):
    """실행 상태"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QueueItemStatus(str, enum.Enum):
    """큐 아이템 상태"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Workflow(Base):
    """워크플로우 모델"""
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[WorkflowStatus] = mapped_column(
        SQLEnum(WorkflowStatus),
        default=WorkflowStatus.DRAFT,
        nullable=False,
    )

    # 트리거 설정
    trigger: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {"type": "manual", "config": {}},
        nullable=False,
    )

    # 스케줄러 설정 (UI 토글 + cron 표현식). 기존 schedule-trigger 노드 메커니즘과 병행.
    # default 는 비활성 + 매시 정각 (Asia/Seoul). enabled=true 일 때만 APScheduler 등록.
    # payload: cron 실행 시 워크플로우의 트리거 입력값으로 전달되는 dict.
    schedule_config: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {
            "enabled": False,
            "cronExpr": "0 * * * *",
            "timezone": "Asia/Seoul",
            "payload": {},
        },
        nullable=False,
    )

    # 워크플로우 변수
    variables: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # 메타데이터
    tags: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    # 워크플로우 생성 주체 ('cli' | 'web')
    created_by: Mapped[str] = mapped_column(String(20), default='cli', nullable=False)

    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # 관계
    nodes: Mapped[List["WorkflowNode"]] = relationship(
        "WorkflowNode",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )
    connections: Mapped[List["WorkflowConnection"]] = relationship(
        "WorkflowConnection",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )
    executions: Mapped[List["WorkflowExecution"]] = relationship(
        "WorkflowExecution",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Workflow {self.id}: {self.name}>"


class WorkflowNode(Base):
    """워크플로우 내 노드 인스턴스"""
    __tablename__ = "workflow_nodes"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("workflows.id"), nullable=False
    )

    # 연결된 AINode ID (프론트엔드의 nodeId)
    node_id: Mapped[str] = mapped_column(String(50), nullable=False)

    # 노드 정의 타입 (manual/ai-custom/http-request 등)
    definition_type: Mapped[str] = mapped_column(String(50), default="ai-custom", nullable=False)

    # AI 노드 참조 ID (ai-custom일 때)
    ai_node_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # 노드별 설정 (JSON)
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # 조건 분기 (condition 타입용)
    branches: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # 노드 이름 (인스턴스별 커스텀 이름)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # 형제 노드 안정 순번 (자동 레이아웃에서 tie-break용)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 노드별 설정 오버라이드
    config_overrides: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # 입력 매핑 (이전 노드 출력 -> 현재 노드 입력)
    input_mapping: Mapped[Dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)

    # 관계
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="nodes")

    def __repr__(self) -> str:
        return f"<WorkflowNode {self.id}: {self.name}>"


class WorkflowConnection(Base):
    """노드 간 연결선"""
    __tablename__ = "workflow_connections"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("workflows.id"), nullable=False
    )

    # 소스/타겟
    source_node_id: Mapped[str] = mapped_column(String(50), nullable=False)
    target_node_id: Mapped[str] = mapped_column(String(50), nullable=False)

    # 엣지 핸들 (분류기 등 다중 출력 노드용)
    source_handle: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    target_handle: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # 조건 (선택적)
    condition: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # 관계
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="connections")

    def __repr__(self) -> str:
        return f"<WorkflowConnection {self.source_node_id} -> {self.target_node_id}>"


class WorkflowExecution(Base):
    """워크플로우 실행 기록"""
    __tablename__ = "workflow_executions"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("workflows.id"), nullable=False
    )

    status: Mapped[ExecutionStatus] = mapped_column(
        SQLEnum(ExecutionStatus),
        default=ExecutionStatus.PENDING,
        nullable=False,
    )

    # 실행 입력
    input_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # 최종 출력
    output_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # 노드별 실행 결과
    node_results: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # 에러 정보
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_node_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # 타임스탬프
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # 관계
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="executions")

    def __repr__(self) -> str:
        return f"<WorkflowExecution {self.id}: {self.status.value}>"


class WarehouseEntry(Base):
    """결과 노드(창고)에 축적되는 데이터"""
    __tablename__ = "warehouse_entries"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    node_instance_id: Mapped[str] = mapped_column(String(50), index=True)  # WorkflowNode.id
    execution_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    dedup_key: Mapped[Optional[str]] = mapped_column(String(128), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NodeQueueItem(Base):
    """공장 노드의 입력 큐 아이템 (FIFO)"""
    __tablename__ = "node_queue_items"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    node_instance_id: Mapped[str] = mapped_column(String(50), index=True)  # WorkflowNode.id
    execution_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[QueueItemStatus] = mapped_column(
        SQLEnum(QueueItemStatus), default=QueueItemStatus.PENDING, nullable=False
    )
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
