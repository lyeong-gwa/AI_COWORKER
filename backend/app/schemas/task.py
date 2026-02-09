"""
Task Schemas (프론트엔드 타입에 맞춤 - camelCase)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from ..models.task import TaskStatus, TaskPriority


# ─────────────────────────────────────────────────────────────────────────────
# 하위 리소스 스키마
# ─────────────────────────────────────────────────────────────────────────────

class TodoItem(BaseModel):
    """할 일 항목"""
    id: str
    text: str
    completed: bool = False


class Comment(BaseModel):
    """댓글"""
    id: str
    authorId: str
    authorName: str
    content: str
    createdAt: str


class ActivityLog(BaseModel):
    """활동 로그"""
    id: str
    userId: str
    userName: str
    action: str
    detail: Optional[str] = None
    timestamp: str


class ReferenceDoc(BaseModel):
    """참조 지식 문서"""
    docId: str
    title: str
    content: str
    category: str = ""
    score: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Task CRUD 스키마
# ─────────────────────────────────────────────────────────────────────────────

class TaskBase(BaseModel):
    """태스크 기본 스키마"""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    tags: List[str] = Field(default_factory=list)
    assigneeId: Optional[str] = Field(None, alias="assigneeId")
    assigneeName: Optional[str] = Field(None, alias="assigneeName")
    dueDate: Optional[datetime] = Field(None, alias="dueDate")
    relatedNodeId: Optional[str] = Field(None, alias="relatedNodeId")


class TaskCreate(TaskBase):
    """태스크 생성"""
    status: TaskStatus = TaskStatus.BACKLOG


class TaskUpdate(BaseModel):
    """태스크 수정"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    tags: Optional[List[str]] = None
    assigneeId: Optional[str] = Field(None, alias="assigneeId")
    assigneeName: Optional[str] = Field(None, alias="assigneeName")
    dueDate: Optional[datetime] = Field(None, alias="dueDate")
    relatedNodeId: Optional[str] = Field(None, alias="relatedNodeId")
    todos: Optional[List[TodoItem]] = None
    comments: Optional[List[Comment]] = None
    activityLog: Optional[List[ActivityLog]] = Field(None, alias="activityLog")


class TaskResponse(BaseModel):
    """태스크 응답 (camelCase)"""
    id: str
    title: str
    description: Optional[str] = None
    status: TaskStatus
    priority: TaskPriority
    tags: List[str]
    assigneeId: Optional[str] = Field(None, serialization_alias="assigneeId")
    assigneeName: Optional[str] = Field(None, serialization_alias="assigneeName")
    dueDate: Optional[datetime] = Field(None, serialization_alias="dueDate")
    relatedNodeId: Optional[str] = Field(None, serialization_alias="relatedNodeId")
    todos: List[Dict[str, Any]] = Field(default_factory=list)
    comments: List[Dict[str, Any]] = Field(default_factory=list)
    activityLog: List[Dict[str, Any]] = Field(default_factory=list, serialization_alias="activityLog")
    references: List[Dict[str, Any]] = Field(default_factory=list)
    createdAt: datetime = Field(serialization_alias="createdAt")
    updatedAt: datetime = Field(serialization_alias="updatedAt")

    class Config:
        from_attributes = True
        populate_by_name = True

    @classmethod
    def from_orm_with_camel(cls, obj):
        """ORM 객체를 camelCase 응답으로 변환"""
        return cls(
            id=obj.id,
            title=obj.title,
            description=obj.description,
            status=obj.status,
            priority=obj.priority,
            tags=obj.tags,
            assigneeId=obj.assignee_id,
            assigneeName=obj.assignee_name,
            dueDate=obj.due_date,
            relatedNodeId=obj.related_node_id,
            todos=obj.todos,
            comments=obj.comments,
            activityLog=obj.activity_log,
            references=obj.references,
            createdAt=obj.created_at,
            updatedAt=obj.updated_at,
        )
