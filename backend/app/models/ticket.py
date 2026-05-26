"""
Ticket Model - ITO 티켓 관리
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
import enum

from ..core.database import Base


class TicketCategory(str, enum.Enum):
    INCIDENT = "incident"
    REQUEST = "request"
    QUESTION = "question"
    CHANGE = "change"


class TicketPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Ticket(Base):
    """ITO 티켓 모델"""
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # enum 필드는 문자열로 저장 (SQLite 호환, 값 검증은 스키마에서)
    category: Mapped[str] = mapped_column(String(30), default="request", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False)

    requester: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    assignee: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    sla_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    workflow_execution_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    tags: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<Ticket {self.id}: {self.title[:30]} [{self.status}]>"
