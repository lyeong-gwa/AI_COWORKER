"""
Tool Definition Model - 도구 라이브러리
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Text, DateTime, Enum as SQLEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column
import enum

from ..core.database import Base


class ToolType(str, enum.Enum):
    """도구 타입"""
    API_CALL = "api_call"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    CODE_EXECUTE = "code_execute"
    DATABASE_QUERY = "database_query"


class ToolDefinition(Base):
    """도구 정의 모델 (ATOMIC 패턴의 Atom)"""
    __tablename__ = "tool_definitions"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str] = mapped_column(String(10), default="🔧", nullable=False)
    color: Mapped[str] = mapped_column(String(50), default="text-gray-400", nullable=False)

    # 도구 타입
    type: Mapped[ToolType] = mapped_column(
        SQLEnum(ToolType),
        nullable=False,
    )

    # 타입별 설정 (JSON으로 저장)
    # api_call: {method, urlTemplate, headers, bodyTemplate, authType, authConfig}
    # file_read: {pathTemplate, encoding}
    # file_write: {pathTemplate, mode}
    # code_execute: {language, code, inputMapping}
    # database_query: {connectionId, queryTemplate}
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # 메타데이터
    tags: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<ToolDefinition {self.id}: {self.name} ({self.type.value})>"
