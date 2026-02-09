"""
Task Model - 칸반 보드 태스크

프론트엔드 타입 정의에 맞춤
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Text, DateTime, Enum as SQLEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column
import enum

from ..core.database import Base


class TaskStatus(str, enum.Enum):
    """태스크 상태 (프론트엔드 칸반 컬럼)"""
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in-progress"
    REVIEW = "review"
    DONE = "done"


class TaskPriority(str, enum.Enum):
    """태스크 우선순위"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Task(Base):
    """태스크 모델 (프론트엔드 Task 타입에 맞춤)"""
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus),
        default=TaskStatus.BACKLOG,
        nullable=False,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        SQLEnum(TaskPriority),
        default=TaskPriority.MEDIUM,
        nullable=False,
    )

    # 담당자
    assignee_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    assignee_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # 메타데이터
    tags: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 연관 노드
    related_node_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # 하위 리소스 (JSON으로 저장)
    # TodoItem: { id, text, completed }
    todos: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    # Comment: { id, authorId, authorName, content, createdAt }
    comments: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    # ActivityLog: { id, userId, userName, action, details, createdAt }
    activity_log: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    # ReferenceDoc: { docId, title, content, category, score }
    references: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<Task {self.id}: {self.title}>"
