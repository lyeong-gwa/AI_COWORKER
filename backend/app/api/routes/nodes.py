"""
AI Node API Routes
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from ...core.database import get_db
from ...models.node import AINode
from ...schemas.node import (
    NodeCreate, NodeUpdate,
    NodeTestRequest, NodeTestResponse,
)
from ...services.node_executor import execute_node

router = APIRouter()


def to_camel_response(node: AINode) -> dict:
    """AINode ORM 객체를 camelCase dict로 변환"""
    return {
        "id": node.id,
        "name": node.name,
        "description": node.description,
        "category": node.category,
        "icon": node.icon,
        "color": node.color,
        "tags": node.tags,
        "linkedToolIds": node.linked_tool_ids,
        "knowledge": node.knowledge,
        "systemPrompt": node.system_prompt,
        "userPromptTemplate": node.user_prompt_template,
        "inputSchema": node.input_schema,
        "outputSchema": node.output_schema,
        "outputEnforcement": node.output_enforcement,
        "llmConfig": node.llm_config,
        "isActive": node.is_active,
        "createdAt": node.created_at.isoformat() if node.created_at else None,
        "updatedAt": node.updated_at.isoformat() if node.updated_at else None,
    }


@router.get("")
async def list_nodes(
    category: Optional[str] = Query(None, description="카테고리 필터"),
    is_active: Optional[bool] = Query(None, description="활성화 상태 필터"),
    q: Optional[str] = Query(None, description="검색어 (이름, 설명)"),
    skip: int = Query(0, ge=0, description="건너뛸 항목 수"),
    limit: int = Query(100, ge=1, le=500, description="최대 항목 수"),
    db: AsyncSession = Depends(get_db),
):
    """노드 목록 조회"""
    query = select(AINode)

    if category:
        query = query.where(AINode.category == category)
    if is_active is not None:
        query = query.where(AINode.is_active == is_active)
    if q:
        query = query.where(
            (AINode.name.ilike(f"%{q}%")) | (AINode.description.ilike(f"%{q}%"))
        )

    query = query.order_by(AINode.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)

    nodes = result.scalars().all()
    return [to_camel_response(node) for node in nodes]


@router.get("/{node_id}")
async def get_node(node_id: str, db: AsyncSession = Depends(get_db)):
    """노드 상세 조회"""
    result = await db.execute(select(AINode).where(AINode.id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="노드를 찾을 수 없습니다")

    return to_camel_response(node)


@router.post("", status_code=201)
async def create_node(data: NodeCreate, db: AsyncSession = Depends(get_db)):
    """노드 생성"""
    node_data = data.model_dump(by_alias=False)

    # model_config_data를 model_config로 변환
    if 'model_config_data' in node_data:
        node_data['model_config'] = node_data.pop('model_config_data')

    node = AINode(
        id=f"node-{uuid.uuid4().hex[:8]}",
        **node_data,
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)

    return to_camel_response(node)


@router.patch("/{node_id}")
async def update_node(
    node_id: str,
    data: NodeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """노드 수정"""
    result = await db.execute(select(AINode).where(AINode.id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="노드를 찾을 수 없습니다")

    update_data = data.model_dump(exclude_unset=True, by_alias=False)

    # model_config_data를 model_config로 변환
    if 'model_config_data' in update_data:
        update_data['model_config'] = update_data.pop('model_config_data')

    for key, value in update_data.items():
        setattr(node, key, value)

    await db.commit()
    await db.refresh(node)

    return to_camel_response(node)


@router.delete("/{node_id}", status_code=204)
async def delete_node(node_id: str, db: AsyncSession = Depends(get_db)):
    """노드 삭제"""
    result = await db.execute(select(AINode).where(AINode.id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="노드를 찾을 수 없습니다")

    await db.delete(node)
    await db.commit()


@router.post("/{node_id}/test", response_model=NodeTestResponse)
async def test_node(
    node_id: str,
    request: NodeTestRequest,
    db: AsyncSession = Depends(get_db),
):
    """노드 테스트 실행"""
    result = await db.execute(select(AINode).where(AINode.id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(status_code=404, detail="노드를 찾을 수 없습니다")

    # 노드 실행
    exec_result = await execute_node(
        node=node,
        input_data=request.input_data,
        mock_tool_results=request.mock_tool_results,
        mock_knowledge=request.mock_knowledge,
        db=db,
    )

    return exec_result
