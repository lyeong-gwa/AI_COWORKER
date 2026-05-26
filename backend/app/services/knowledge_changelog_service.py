"""KnowledgeChangelogEntry CRUD helper — Karpathy v2 (P2).

설계 근거: `.omc/plans/지식-karpathy-v2.md` §5.2, §6.2, D10.

PUT/DELETE 시 1 행을 적재한다. ``diff_summary`` 는 P2 에서는 fallback 문자열
(예: ``v2→v3 by cli``) 만 기록하며, LLM 기반 요약 생성은 P4 의 몫.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.knowledge_changelog import KnowledgeChangelogEntry


ALLOWED_CHANGE_TYPES = {"create", "update", "delete", "lint-fix"}


async def add_changelog(
    db: AsyncSession,
    knowledge_id: str,
    version: int,
    change_type: str,
    operator: str = "cli",
    diff_summary: Optional[str] = None,
    *,
    commit: bool = True,
) -> KnowledgeChangelogEntry:
    """changelog 1 행 적재.

    ``commit=False`` 면 호출자가 트랜잭션을 결합한다 (force delete 다중 행 등).
    fallback diff_summary: ``"v{version} by {operator}"`` — LLM 호출 없이 즉시 기록.
    """
    if change_type not in ALLOWED_CHANGE_TYPES:
        raise ValueError(
            f"change_type 은 {sorted(ALLOWED_CHANGE_TYPES)} 중 하나여야 합니다 (got {change_type!r})"
        )

    summary = diff_summary if diff_summary is not None else f"v{version} by {operator}"
    row = KnowledgeChangelogEntry(
        id=uuid.uuid4().hex,
        knowledge_id=knowledge_id,
        version=int(version),
        timestamp=datetime.utcnow(),
        operator=operator or "cli",
        diff_summary=summary,
        change_type=change_type,
    )
    db.add(row)
    if commit:
        await db.commit()
        await db.refresh(row)
    else:
        await db.flush()
    return row


__all__ = ["add_changelog", "ALLOWED_CHANGE_TYPES"]
