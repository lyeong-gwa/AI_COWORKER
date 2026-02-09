"""
AI Node Model - AI 노드 (ATOMIC 패턴의 Molecule)

프론트엔드 타입 정의에 맞춤
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Text, DateTime, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class AINode(Base):
    """AI 노드 모델 (도구 + 프롬프트 + 스키마의 조합)"""
    __tablename__ = "ai_nodes"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="general", nullable=False)
    icon: Mapped[str] = mapped_column(String(10), default="🤖", nullable=False)
    color: Mapped[str] = mapped_column(String(50), default="text-blue-400", nullable=False)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    # 연결된 도구 ID 목록 (라이브러리 참조)
    linked_tool_ids: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    # 지식 베이스 설정
    # { linkedIds: string[], filters?: { ... }, maxTokens?: number }
    knowledge: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {"linkedIds": [], "filters": {}, "maxTokens": 2000},
        nullable=False,
    )

    # 프롬프트 (분리: systemPrompt + userPromptTemplate)
    system_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    user_prompt_template: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # 입력 스키마 (JSON Schema 형식)
    input_schema: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {"type": "object", "properties": {}, "required": []},
        nullable=False,
    )

    # 출력 스키마 (JSON Schema 형식)
    output_schema: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {"type": "object", "properties": {}, "required": []},
        nullable=False,
    )

    # 출력 강제 설정
    output_enforcement: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {
            "enabled": False,
            "includeSchemaInPrompt": False,
            "exampleOutput": None,
            "validationEnabled": False,
            "retryOnFailure": False,
            "maxRetries": 3,
        },
        nullable=False,
    )

    # LLM 설정
    llm_config: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {
            "model": "gpt-4o-mini",
            "temperature": 0.7,
            "maxTokens": 2000,
        },
        nullable=False,
    )

    # 활성화 여부
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<AINode {self.id}: {self.name}>"
