"""
Ticket Routes - ITO 티켓 CRUD 및 통계
"""

import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional

from ...core.database import get_db
from ...models.ticket import Ticket
from ...schemas.ticket import (
    TicketCreate, TicketUpdate,
    ALLOWED_CATEGORIES, ALLOWED_PRIORITIES, ALLOWED_STATUSES,
)
from ...services.audit import log as audit_log

router = APIRouter()


def ticket_to_camel(t: Ticket) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "category": t.category,
        "priority": t.priority,
        "status": t.status,
        "requester": t.requester,
        "assignee": t.assignee,
        "slaDueAt": t.sla_due_at.isoformat() if t.sla_due_at else None,
        "workflowExecutionId": t.workflow_execution_id,
        "tags": t.tags or [],
        "createdAt": t.created_at.isoformat() if t.created_at else None,
        "updatedAt": t.updated_at.isoformat() if t.updated_at else None,
        "resolvedAt": t.resolved_at.isoformat() if t.resolved_at else None,
    }


def _validate_enums(data: dict):
    if "category" in data and data["category"] is not None and data["category"] not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category는 {ALLOWED_CATEGORIES} 중 하나여야 합니다")
    if "priority" in data and data["priority"] is not None and data["priority"] not in ALLOWED_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"priority는 {ALLOWED_PRIORITIES} 중 하나여야 합니다")
    if "status" in data and data["status"] is not None and data["status"] not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail=f"status는 {ALLOWED_STATUSES} 중 하나여야 합니다")


# ── 통계 (parameterized 앞에 배치) ────────────────────────

@router.get("/stats")
async def ticket_stats(db: AsyncSession = Depends(get_db)):
    """카테고리/상태/우선순위별 count, SLA 초과 수"""
    all_rows = (await db.execute(select(Ticket))).scalars().all()

    by_cat: dict = {}
    by_status: dict = {}
    by_priority: dict = {}
    sla_breach = 0
    now = datetime.utcnow()

    for t in all_rows:
        by_cat[t.category] = by_cat.get(t.category, 0) + 1
        by_status[t.status] = by_status.get(t.status, 0) + 1
        by_priority[t.priority] = by_priority.get(t.priority, 0) + 1
        if t.sla_due_at and t.sla_due_at < now and t.status not in ("resolved", "closed"):
            sla_breach += 1

    return {
        "total": len(all_rows),
        "byCategory": by_cat,
        "byStatus": by_status,
        "byPriority": by_priority,
        "slaBreach": sla_breach,
    }


# ── CRUD ─────────────────────────────────────────────────

@router.get("")
async def list_tickets(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    assignee: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(Ticket).order_by(Ticket.created_at.desc())
    if status:
        query = query.where(Ticket.status == status)
    if category:
        query = query.where(Ticket.category == category)
    if priority:
        query = query.where(Ticket.priority == priority)
    if assignee:
        query = query.where(Ticket.assignee == assignee)
    rows = (await db.execute(query)).scalars().all()
    return [ticket_to_camel(t) for t in rows]


@router.post("")
async def create_ticket(data: TicketCreate, db: AsyncSession = Depends(get_db)):
    payload = data.model_dump()
    _validate_enums(payload)

    ticket = Ticket(
        id=f"tkt-{uuid.uuid4().hex[:8]}",
        title=payload["title"],
        description=payload.get("description", ""),
        category=payload.get("category", "request"),
        priority=payload.get("priority", "medium"),
        status=payload.get("status", "open"),
        requester=payload.get("requester", ""),
        assignee=payload.get("assignee"),
        sla_due_at=payload.get("slaDueAt"),
        workflow_execution_id=payload.get("workflowExecutionId"),
        tags=payload.get("tags") or [],
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    await audit_log(db, "system", "ticket.create", "ticket", ticket.id, {"title": ticket.title, "category": ticket.category})
    return ticket_to_camel(ticket)


@router.get("/{ticket_id}")
async def get_ticket(ticket_id: str, db: AsyncSession = Depends(get_db)):
    t = (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="티켓을 찾을 수 없습니다")
    return ticket_to_camel(t)


@router.patch("/{ticket_id}")
async def update_ticket(ticket_id: str, data: TicketUpdate, db: AsyncSession = Depends(get_db)):
    t = (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="티켓을 찾을 수 없습니다")

    payload = data.model_dump(exclude_unset=True)
    _validate_enums(payload)

    field_map = {
        "title": "title",
        "description": "description",
        "category": "category",
        "priority": "priority",
        "status": "status",
        "requester": "requester",
        "assignee": "assignee",
        "slaDueAt": "sla_due_at",
        "workflowExecutionId": "workflow_execution_id",
        "tags": "tags",
        "resolvedAt": "resolved_at",
    }
    for k, v in payload.items():
        col = field_map.get(k)
        if col:
            setattr(t, col, v)

    # status가 resolved로 변경되면 resolved_at 자동 기록
    if payload.get("status") == "resolved" and not t.resolved_at:
        t.resolved_at = datetime.utcnow()

    await db.commit()
    await db.refresh(t)
    await audit_log(db, "system", "ticket.update", "ticket", t.id, {"changes": list(payload.keys())})
    return ticket_to_camel(t)


@router.delete("/{ticket_id}")
async def delete_ticket(ticket_id: str, db: AsyncSession = Depends(get_db)):
    t = (await db.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="티켓을 찾을 수 없습니다")
    await db.delete(t)
    await db.commit()
    return {"message": "삭제되었습니다"}
