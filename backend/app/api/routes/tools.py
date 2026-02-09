"""
Tool Library API Routes
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from ...core.database import get_db
from ...models.tool import ToolDefinition, ToolType
from ...schemas.tool import ToolCreate, ToolUpdate, ToolTestRequest, ToolTestResponse
from ...services.tool_executor import execute_tool

router = APIRouter()


def to_camel_response(tool: ToolDefinition) -> dict:
    """ToolDefinition ORM 객체를 camelCase dict로 변환"""
    return {
        "id": tool.id,
        "name": tool.name,
        "description": tool.description,
        "type": tool.type.value if tool.type else None,
        "icon": tool.icon,
        "color": tool.color,
        "config": tool.config,
        "tags": tool.tags,
        "createdAt": tool.created_at.isoformat() if tool.created_at else None,
        "updatedAt": tool.updated_at.isoformat() if tool.updated_at else None,
    }


@router.get("")
async def list_tools(
    type: Optional[ToolType] = Query(None, description="도구 타입 필터"),
    tag: Optional[str] = Query(None, description="태그 필터"),
    q: Optional[str] = Query(None, description="검색어 (이름, 설명)"),
    skip: int = Query(0, ge=0, description="건너뛸 항목 수"),
    limit: int = Query(100, ge=1, le=500, description="최대 항목 수"),
    db: AsyncSession = Depends(get_db),
):
    """도구 목록 조회"""
    query = select(ToolDefinition)

    if type:
        query = query.where(ToolDefinition.type == type)
    if q:
        query = query.where(
            (ToolDefinition.name.ilike(f"%{q}%")) | (ToolDefinition.description.ilike(f"%{q}%"))
        )

    query = query.order_by(ToolDefinition.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    tools = result.scalars().all()

    # 태그 필터 (JSON 필드라서 Python에서 필터링)
    if tag:
        tools = [t for t in tools if tag in t.tags]

    return [to_camel_response(t) for t in tools]


@router.get("/{tool_id}")
async def get_tool(tool_id: str, db: AsyncSession = Depends(get_db)):
    """도구 상세 조회"""
    result = await db.execute(
        select(ToolDefinition).where(ToolDefinition.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise HTTPException(status_code=404, detail="도구를 찾을 수 없습니다")

    return to_camel_response(tool)


@router.post("", status_code=201)
async def create_tool(data: ToolCreate, db: AsyncSession = Depends(get_db)):
    """도구 생성"""
    tool = ToolDefinition(
        id=f"tool-{uuid.uuid4().hex[:8]}",
        **data.model_dump(),
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)

    return to_camel_response(tool)


@router.patch("/{tool_id}")
async def update_tool(
    tool_id: str,
    data: ToolUpdate,
    db: AsyncSession = Depends(get_db),
):
    """도구 수정"""
    result = await db.execute(
        select(ToolDefinition).where(ToolDefinition.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise HTTPException(status_code=404, detail="도구를 찾을 수 없습니다")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(tool, key, value)

    await db.commit()
    await db.refresh(tool)

    return to_camel_response(tool)


@router.delete("/{tool_id}", status_code=204)
async def delete_tool(tool_id: str, db: AsyncSession = Depends(get_db)):
    """도구 삭제"""
    result = await db.execute(
        select(ToolDefinition).where(ToolDefinition.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise HTTPException(status_code=404, detail="도구를 찾을 수 없습니다")

    await db.delete(tool)
    await db.commit()


@router.post("/{tool_id}/test", response_model=ToolTestResponse)
async def test_tool(
    tool_id: str,
    request: ToolTestRequest,
    db: AsyncSession = Depends(get_db),
):
    """도구 테스트 실행"""
    result = await db.execute(
        select(ToolDefinition).where(ToolDefinition.id == tool_id)
    )
    tool = result.scalar_one_or_none()

    if not tool:
        raise HTTPException(status_code=404, detail="도구를 찾을 수 없습니다")

    # 도구 실행
    exec_result = await execute_tool(tool, request.input_data)

    return ToolTestResponse(
        success=exec_result.success,
        output=exec_result.output,
        error=exec_result.error,
        execution_time_ms=exec_result.execution_time_ms,
        logs=exec_result.logs,
    )
