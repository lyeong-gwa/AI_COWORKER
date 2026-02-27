"""
API Definition Model - API 정의 라이브러리
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Text, DateTime, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column
import enum

from ..core.database import Base


class AuthType(str, enum.Enum):
    """인증 타입"""
    NONE = "none"
    BEARER = "bearer"
    BASIC = "basic"
    API_KEY = "api_key"


class ApiDefinition(Base):
    """API 정의 모델 - 구조화된 API 규격 관리"""
    __tablename__ = "api_definitions"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    icon: Mapped[str] = mapped_column(String(10), default="🌐", nullable=False)
    color: Mapped[str] = mapped_column(String(50), default="text-cyan-400", nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    # HTTP 요청 정의
    method: Mapped[str] = mapped_column(String(10), default="GET", nullable=False)
    url_template: Mapped[str] = mapped_column(Text, nullable=False)
    headers: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    body_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 인증
    auth_type: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    auth_config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # 파라미터 정의 (구조화)
    # [{name, in(path/query/header/body), type, required, description, default}]
    parameters: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    # 응답 정의
    # {fields: [{field, type, description}], example: any}
    response_schema: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # 메타
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<ApiDefinition {self.id}: {self.name} ({self.method} {self.url_template[:50]})>"
