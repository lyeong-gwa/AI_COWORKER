"""Audit Log Service - 감사 로그 기록 유틸"""

import uuid
import logging
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit_log import AuditLog

logger = logging.getLogger(__name__)


async def log(
    db: AsyncSession,
    actor: str,
    action: str,
    target_type: str,
    target_id: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """감사 로그 1건 기록. 실패해도 메인 트랜잭션에 영향 주지 않게 best-effort."""
    try:
        entry = AuditLog(
            id=f"aud-{uuid.uuid4().hex[:10]}",
            actor=actor or "system",
            action=action,
            target_type=target_type or "",
            target_id=str(target_id or ""),
            details=details,
        )
        db.add(entry)
        await db.commit()
    except Exception as e:
        logger.warning(f"[AUDIT] 로그 기록 실패: {e}")
        try:
            await db.rollback()
        except Exception:
            pass
