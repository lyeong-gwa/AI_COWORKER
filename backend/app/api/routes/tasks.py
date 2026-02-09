"""
Task API Routes (camelCase 응답)
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from ...core.database import get_db
from ...models.task import Task, TaskStatus
from ...schemas.task import TaskCreate, TaskUpdate, TaskResponse

router = APIRouter()


def to_camel_response(task: Task) -> dict:
    """Task ORM 객체를 camelCase dict로 변환"""
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status.value if task.status else None,
        "priority": task.priority.value if task.priority else None,
        "tags": task.tags,
        "assigneeId": task.assignee_id,
        "assigneeName": task.assignee_name,
        "dueDate": task.due_date.isoformat() if task.due_date else None,
        "relatedNodeId": task.related_node_id,
        "todos": task.todos,
        "comments": task.comments,
        "activityLog": task.activity_log,
        "references": task.references,
        "createdAt": task.created_at.isoformat() if task.created_at else None,
        "updatedAt": task.updated_at.isoformat() if task.updated_at else None,
    }


@router.get("")
async def list_tasks(
    status: Optional[TaskStatus] = Query(None, description="상태 필터"),
    q: Optional[str] = Query(None, description="검색어 (제목, 설명)"),
    priority: Optional[str] = Query(None, description="우선순위 필터"),
    skip: int = Query(0, ge=0, description="건너뛸 항목 수"),
    limit: int = Query(100, ge=1, le=500, description="최대 항목 수"),
    db: AsyncSession = Depends(get_db),
):
    """태스크 목록 조회"""
    query = select(Task)
    if status:
        query = query.where(Task.status == status)
    if priority:
        query = query.where(Task.priority == priority)
    if q:
        query = query.where(
            (Task.title.ilike(f"%{q}%")) | (Task.description.ilike(f"%{q}%"))
        )
    query = query.order_by(Task.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    tasks = result.scalars().all()

    return [to_camel_response(task) for task in tasks]


@router.get("/{task_id}")
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """태스크 상세 조회"""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="태스크를 찾을 수 없습니다")

    return to_camel_response(task)


@router.post("", status_code=201)
async def create_task(data: TaskCreate, db: AsyncSession = Depends(get_db)):
    """태스크 생성"""
    task = Task(
        id=f"task-{uuid.uuid4().hex[:8]}",
        title=data.title,
        description=data.description,
        status=data.status,
        priority=data.priority,
        tags=data.tags,
        assignee_id=data.assigneeId,
        assignee_name=data.assigneeName,
        due_date=data.dueDate,
        related_node_id=data.relatedNodeId,
        todos=[],
        comments=[],
        activity_log=[],
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    return to_camel_response(task)


@router.patch("/{task_id}")
async def update_task(
    task_id: str,
    data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
):
    """태스크 수정"""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="태스크를 찾을 수 없습니다")

    # 업데이트할 필드들 (camelCase -> snake_case 매핑)
    field_mapping = {
        "title": "title",
        "description": "description",
        "status": "status",
        "priority": "priority",
        "tags": "tags",
        "assigneeId": "assignee_id",
        "assigneeName": "assignee_name",
        "dueDate": "due_date",
        "relatedNodeId": "related_node_id",
        "todos": "todos",
        "comments": "comments",
        "activityLog": "activity_log",
    }

    update_data = data.model_dump(exclude_unset=True)
    for camel_key, value in update_data.items():
        snake_key = field_mapping.get(camel_key, camel_key)
        if hasattr(task, snake_key):
            setattr(task, snake_key, value)

    await db.commit()
    await db.refresh(task)

    return to_camel_response(task)


@router.patch("/{task_id}/status")
async def update_task_status(
    task_id: str,
    status: TaskStatus,
    db: AsyncSession = Depends(get_db),
):
    """태스크 상태 변경 (칸반 이동)"""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="태스크를 찾을 수 없습니다")

    task.status = status
    await db.commit()
    await db.refresh(task)

    return to_camel_response(task)


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """태스크 삭제"""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="태스크를 찾을 수 없습니다")

    await db.delete(task)
    await db.commit()
