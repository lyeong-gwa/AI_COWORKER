"""
Ticket Schemas - 티켓 CRUD 스키마 (camelCase)
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


ALLOWED_CATEGORIES = {"incident", "request", "question", "change"}
ALLOWED_PRIORITIES = {"low", "medium", "high", "critical"}
ALLOWED_STATUSES = {"open", "in_progress", "resolved", "closed"}


class TicketCreate(BaseModel):
    title: str
    description: str = ""
    category: str = "request"
    priority: str = "medium"
    status: str = "open"
    requester: str = ""
    assignee: Optional[str] = None
    slaDueAt: Optional[datetime] = None
    workflowExecutionId: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class TicketUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    requester: Optional[str] = None
    assignee: Optional[str] = None
    slaDueAt: Optional[datetime] = None
    workflowExecutionId: Optional[str] = None
    tags: Optional[List[str]] = None
    resolvedAt: Optional[datetime] = None


class TicketResponse(BaseModel):
    id: str
    title: str
    description: str
    category: str
    priority: str
    status: str
    requester: str
    assignee: Optional[str] = None
    slaDueAt: Optional[datetime] = Field(None, serialization_alias="slaDueAt")
    workflowExecutionId: Optional[str] = Field(None, serialization_alias="workflowExecutionId")
    tags: List[str]
    createdAt: datetime = Field(serialization_alias="createdAt")
    updatedAt: datetime = Field(serialization_alias="updatedAt")
    resolvedAt: Optional[datetime] = Field(None, serialization_alias="resolvedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
