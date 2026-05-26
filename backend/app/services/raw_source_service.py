"""RawSource (Layer 1) 저장/조회 helper — Karpathy v2 (P2).

설계 근거: `.omc/plans/지식-karpathy-v2.md` §6.1 (POST /knowledge/raw), §5.2.

원본 파일(blob) 을 `backend/data/knowledge-raw/{yyyy}/{mm}/{uuid}.{ext}` 에 저장하고,
DB 의 `knowledge_raw_sources` 테이블에 메타데이터를 1 행 적재.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import _BACKEND_DIR
from ..models.knowledge_raw import RawSource


# 최대 파일 크기 — plan §6.1 의 보안 가드 (20 MiB)
MAX_RAW_FILE_BYTES = 20 * 1024 * 1024


def _raw_root() -> str:
    """`backend/data/knowledge-raw` 절대경로 (없으면 생성)."""
    root = os.path.join(_BACKEND_DIR, "data", "knowledge-raw")
    os.makedirs(root, exist_ok=True)
    return root


def _ext_from_filename(filename: str) -> str:
    """파일명에서 확장자만 (점 포함, lowercase). 없으면 빈 문자열."""
    _, ext = os.path.splitext(filename or "")
    return ext.lower()


def _now_partition() -> tuple[str, str]:
    """``YYYY``, ``MM`` 파티션 키."""
    now = datetime.utcnow()
    return f"{now.year:04d}", f"{now.month:02d}"


async def save_raw_source(
    db: AsyncSession,
    *,
    filename: str,
    mime: str,
    blob: bytes,
    derived_knowledge_ids: Optional[list[str]] = None,
) -> RawSource:
    """blob 을 디스크에 저장하고 RawSource 1 행을 적재.

    Returns: 적재된 ``RawSource`` (id 포함).
    """
    if blob is None:
        raise ValueError("blob 이 비어 있습니다")
    size = len(blob)
    if size > MAX_RAW_FILE_BYTES:
        raise ValueError(
            f"파일 크기 {size} 바이트가 한계 {MAX_RAW_FILE_BYTES} 바이트를 초과합니다"
        )

    raw_id = uuid.uuid4().hex
    yyyy, mm = _now_partition()
    ext = _ext_from_filename(filename)

    target_dir = os.path.join(_raw_root(), yyyy, mm)
    os.makedirs(target_dir, exist_ok=True)
    target_file = os.path.join(target_dir, f"{raw_id}{ext}")

    with open(target_file, "wb") as f:
        f.write(blob)

    sha = hashlib.sha256(blob).hexdigest()

    # original_blob_path 는 backend/ 기준 상대경로로 보관 — DB portability.
    rel_blob_path = os.path.relpath(target_file, _BACKEND_DIR).replace("\\", "/")

    row = RawSource(
        id=raw_id,
        filename=filename or f"upload-{raw_id}",
        mime=mime or "application/octet-stream",
        size=size,
        content_hash=sha,
        uploaded_at=datetime.utcnow(),
        original_blob_path=rel_blob_path,
        derived_knowledge_ids=list(derived_knowledge_ids or []),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


def raw_source_to_dict(row: RawSource) -> dict:
    """RawSource → camelCase dict 응답 (API 직렬화 공통화)."""
    return {
        "id": row.id,
        "filename": row.filename,
        "mime": row.mime,
        "size": row.size,
        "contentHash": row.content_hash,
        "uploadedAt": row.uploaded_at.isoformat() if row.uploaded_at else None,
        "originalBlobPath": row.original_blob_path,
        "derivedKnowledgeIds": list(row.derived_knowledge_ids or []),
    }


__all__ = ["save_raw_source", "raw_source_to_dict", "MAX_RAW_FILE_BYTES"]
