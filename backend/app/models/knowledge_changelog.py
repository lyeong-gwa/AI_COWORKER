"""
KnowledgeChangelogEntry Model — version 이력 (Knowledge v2).

페이지(`KnowledgeFileDoc`) 의 변경 1건당 1행이 적재된다.
`diff_summary` 는 LLM 이 생성하는 한 줄 요약 (fallback: "version bumped").
body 전체 스냅샷은 git 의존(`data/` 가 git 추적된다는 가정 — plan §14 리스크 참조).

설계 근거: `.omc/plans/지식-karpathy-v2.md` §5.2, §10 step 1~6, D10.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class KnowledgeChangelogEntry(Base):
    """지식 페이지 변경이력 1행.

    `change_type` 은 plan 에 정의된 enum 값 중 하나:
      - "create"     : 페이지 신규 생성
      - "update"     : PUT 으로 본문/메타 변경 (version +1)
      - "delete"     : 페이지 삭제
      - "lint-fix"   : lint 가 자동 정정 (operator="system:lint")
    """

    __tablename__ = "knowledge_changelog_entries"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # uuid4 hex
    knowledge_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)  # "{category}/{slug}"
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    operator: Mapped[str] = mapped_column(String(100), default="cli", nullable=False)
    diff_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    change_type: Mapped[str] = mapped_column(String(20), default="update", nullable=False)

    def __repr__(self) -> str:  # noqa: D401
        return (
            f"<KnowledgeChangelogEntry {self.id}: {self.knowledge_id} "
            f"v{self.version} {self.change_type}>"
        )
