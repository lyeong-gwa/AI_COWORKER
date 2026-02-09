"""
Knowledge Document Model - 지식 베이스 문서

프론트엔드 타입 정의에 맞춤
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Text, DateTime, Integer, Enum as SQLEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column
import enum

from ..core.database import Base


class SyncStatus(str, enum.Enum):
    """벡터 DB 동기화 상태"""
    SYNCED = "synced"
    PENDING = "pending"
    ERROR = "error"


class KnowledgeDocument(Base):
    """지식 베이스 문서 모델 (1문서 = 1청크)"""
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    filename: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # 원본 파일명
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 벡터 DB 연동
    vector_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sync_status: Mapped[SyncStatus] = mapped_column(
        SQLEnum(SyncStatus),
        default=SyncStatus.PENDING,
        nullable=False,
    )
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 메타데이터
    source: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    doc_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)  # 'metadata'는 SQLAlchemy 예약어

    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<KnowledgeDocument {self.id}: {self.title}>"
