"""
RawSource Model — Layer 1 of Karpathy LLM Wiki (Knowledge v2).

원본 파일(불변 blob)에 대한 메타데이터를 보관한다. 실제 바이너리는
`backend/data/knowledge-raw/{yyyy}/{mm}/{uuid}.{ext}` 에 저장되고,
본 테이블은 search/dedup/계보(lineage) 추적을 위한 인덱스 역할이다.

설계 근거: `.omc/plans/지식-karpathy-v2.md` §5.2, §10 step 1~6.
"""

from datetime import datetime
from typing import List
from sqlalchemy import String, DateTime, JSON, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class RawSource(Base):
    """원본 파일 메타 (Layer 1).

    `derived_knowledge_ids` 는 본 raw 로부터 큐레이션된 wiki 페이지 id 목록(`{category}/{slug}`).
    blob 자체는 `original_blob_path` 가 가리키는 파일에 저장되어 불변.
    """

    __tablename__ = "knowledge_raw_sources"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # uuid4 hex
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime: Mapped[str] = mapped_column(String(100), default="application/octet-stream", nullable=False)
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), index=True, nullable=False)  # SHA-256 hex
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    original_blob_path: Mapped[str] = mapped_column(Text, nullable=False)
    derived_knowledge_ids: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    def __repr__(self) -> str:  # noqa: D401
        return f"<RawSource {self.id}: {self.filename} ({self.mime}, {self.size}B)>"
