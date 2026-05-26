"""
AI Node API Routes
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from ...core.database import get_db
from ...core.exceptions import ConflictError, NotFoundError
from ...models.node import AINode
from ...schemas.node import (
    NodeCreate, NodeUpdate,
    NodeTestRequest, NodeTestResponse,
)
from ...services.node_executor import execute_node
from ...nodes.catalog import NodeCatalogEntry, get_catalog

router = APIRouter()


@router.get(
    "/catalog",
    response_model=List[NodeCatalogEntry],
    summary="범용 노드 카탈로그 조회",
    description=(
        "CLI(Claude Code 등)가 워크플로우 조립 전에 호출하여 사용 가능한 노드의 "
        "스펙(inputs/outputs/config/useCases/connectsWellWith)을 조회하는 엔드포인트. "
        "현재 13종(11종 범용 + 인스턴스DB Phase A 2종)을 반환한다."
    ),
)
async def list_catalog() -> List[NodeCatalogEntry]:
    """Return the full node catalog (13 entries: 11 general-purpose + 2 instance-db)."""
    return get_catalog()

# camelCase → snake_case 매핑
CAMEL_TO_SNAKE = {
    "systemPrompt": "system_prompt",
    "userPromptTemplate": "user_prompt_template",
    "inputSchema": "input_schema",
    "outputSchema": "output_schema",
    "outputEnforcement": "output_enforcement",
    "llmConfig": "llm_config",
    "isActive": "is_active",
}


def to_snake_case(data: dict) -> dict:
    """camelCase 키를 snake_case로 변환"""
    return {CAMEL_TO_SNAKE.get(k, k): v for k, v in data.items()}


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


@router.get(
    "",
    summary="커스텀 AI 노드 목록 조회",
    description=(
        "CLI가 등록한 커스텀 AI 노드(``ai-custom`` defType)의 목록을 반환한다. "
        "카탈로그의 내장 11종과는 별개로, 워크플로우 노드는 이 목록의 ID 를 "
        "``aiNodeId`` 로 참조한다."
    ),
)
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


@router.get(
    "/{node_id}",
    summary="커스텀 AI 노드 상세 조회",
)
async def get_node(node_id: str, db: AsyncSession = Depends(get_db)):
    """노드 상세 조회"""
    result = await db.execute(select(AINode).where(AINode.id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise NotFoundError(
            "노드를 찾을 수 없습니다",
            details={"nodeId": node_id},
        )

    return to_camel_response(node)


@router.post(
    "",
    status_code=201,
    summary="커스텀 AI 노드 등록",
    description=(
        "CLI가 ``systemPrompt`` 기반 커스텀 AI 프롬프트를 플랫폼에 등록한다. "
        "등록된 노드는 이후 워크플로우의 ``ai-custom`` defType 노드에서 "
        "``aiNodeId`` 로 참조되어 실행 시 프롬프트 템플릿을 공급한다. "
        "\n\n"
        "**중복 방지**: 동일한 ``name`` 이 이미 존재하면 409 Conflict 를 반환한다. "
        "필요 시 CLI가 suffix 를 붙이거나 ``PATCH`` 로 기존 레코드를 갱신하도록 유도한다."
    ),
    response_description="생성된 커스텀 AI 노드의 전체 레코드 (camelCase)",
)
async def create_node(data: NodeCreate, db: AsyncSession = Depends(get_db)):
    """커스텀 AI 노드 생성 (중복 name 검사 포함)."""
    # 이름 중복 체크 — CLI가 동일 프롬프트를 반복 등록하지 않도록.
    dup = await db.execute(select(AINode).where(AINode.name == data.name))
    if dup.scalar_one_or_none() is not None:
        raise ConflictError(
            "동일한 이름의 커스텀 AI 노드가 이미 존재합니다",
            details={"name": data.name},
        )

    node_data = to_snake_case(data.model_dump(by_alias=False))

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
        raise NotFoundError(
            "노드를 찾을 수 없습니다",
            details={"nodeId": node_id},
        )

    update_data = to_snake_case(data.model_dump(exclude_unset=True, by_alias=False))

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
        raise NotFoundError(
            "노드를 찾을 수 없습니다",
            details={"nodeId": node_id},
        )

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
        raise NotFoundError(
            "노드를 찾을 수 없습니다",
            details={"nodeId": node_id},
        )

    # 노드 실행
    exec_result = await execute_node(
        node=node,
        input_data=request.inputData,
        db=db,
    )

    return exec_result
