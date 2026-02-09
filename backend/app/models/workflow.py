"""
Workflow Models - 워크플로우 (ATOMIC 패턴의 Organism)

프론트엔드 타입 정의에 맞춤
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Text, DateTime, Boolean, Enum as SQLEnum, JSON, ForeignKey
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

    # 캔버스 뷰포트 설정
    viewport: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {"x": 0, "y": 0, "zoom": 1},
        nullable=False,
    )

    # 트리거 설정
    trigger: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {"type": "manual", "config": {}},
        nullable=False,
    )

    # 워크플로우 변수
    variables: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # 메타데이터
    tags: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

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

    # 노드 이름 (인스턴스별 커스텀 이름)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # 캔버스 위치 (position: {x, y} 형태로 저장)
    position: Mapped[Dict[str, float]] = mapped_column(
        JSON,
        default=lambda: {"x": 0, "y": 0},
        nullable=False,
    )

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
