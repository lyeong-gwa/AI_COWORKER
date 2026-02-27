"""
API Definition Routes - API 정의 CRUD 및 실행 엔드포인트
"""

import uuid
import time
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from ...core.database import get_db
from ...models.api_definition import ApiDefinition
from ...schemas.api_definition import (
    ApiDefinitionCreate,
    ApiDefinitionUpdate,
    ApiTestRequest,
    ApiCaptureRequest,
)
from ...schemas.tool import ToolTestResponse
from ...services.tool_executor import _execute_api_call

router = APIRouter()

# ── camelCase 변환 ──────────────────────────────────────────────────────────

CAMEL_TO_SNAKE = {
    "urlTemplate": "url_template",
    "bodyTemplate": "body_template",
    "authType": "auth_type",
    "authConfig": "auth_config",
    "responseSchema": "response_schema",
    "isActive": "is_active",
    "createdAt": "created_at",
    "updatedAt": "updated_at",
}

SNAKE_TO_CAMEL = {v: k for k, v in CAMEL_TO_SNAKE.items()}


def to_snake_case(data: dict) -> dict:
    """camelCase → snake_case 변환"""
    return {CAMEL_TO_SNAKE.get(k, k): v for k, v in data.items()}


def to_camel_response(api_def: ApiDefinition) -> dict:
    """ApiDefinition ORM → camelCase dict"""
    return {
        "id": api_def.id,
        "name": api_def.name,
        "description": api_def.description,
        "icon": api_def.icon,
        "color": api_def.color,
        "category": api_def.category,
        "tags": api_def.tags or [],
        "method": api_def.method,
        "urlTemplate": api_def.url_template,
        "headers": api_def.headers or {},
        "bodyTemplate": api_def.body_template,
        "authType": api_def.auth_type,
        "authConfig": api_def.auth_config or {},
        "parameters": api_def.parameters or [],
        "responseSchema": api_def.response_schema or {},
        "isActive": api_def.is_active,
        "createdAt": api_def.created_at.isoformat() if api_def.created_at else None,
        "updatedAt": api_def.updated_at.isoformat() if api_def.updated_at else None,
    }


# ── Non-parameterized routes first (to avoid FastAPI treating them as IDs) ──

@router.post("/test-api", response_model=ToolTestResponse)
async def test_raw_api(request: ApiTestRequest):
    """원시 API 테스트 (Postman 스타일)"""
    start_time = time.perf_counter()
    logs: list[str] = []

    config = {
        "method": request.method,
        "urlTemplate": request.url,
        "headers": request.headers,
        "bodyTemplate": request.bodyTemplate,
    }

    try:
        result = await _execute_api_call(config, request.inputData, logs)
        execution_time = (time.perf_counter() - start_time) * 1000
        return ToolTestResponse(
            success=True,
            output=result,
            executionTimeMs=execution_time,
            logs=logs,
        )
    except Exception as e:
        execution_time = (time.perf_counter() - start_time) * 1000
        return ToolTestResponse(
            success=False,
            error=str(e),
            executionTimeMs=execution_time,
            logs=logs,
        )


@router.post("/capture")
async def capture_response_schema(request: ApiCaptureRequest):
    """테스트 응답에서 자동 스키마 추출"""
    import re

    fields: list[dict] = []
    _analyze_json(request.responseData, fields)

    # URL 템플릿에서 파라미터 추출
    parameters: list[dict] = []
    if request.urlTemplate:
        matches = re.findall(r'\{\{([^}]+)\}\}', request.urlTemplate)
        for var_name in matches:
            parameters.append({
                "name": var_name.strip(),
                "in": "path",
                "type": "string",
                "required": True,
                "description": "",
                "default": None,
            })

    return {
        "parameters": parameters,
        "responseSchema": {
            "fields": fields[:30],  # 최대 30개 필드
            "example": request.responseData,
        },
    }


# ── CRUD Endpoints ──────────────────────────────────────────────────────────

@router.get("")
async def list_api_definitions(
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """API 정의 목록 조회"""
    query = select(ApiDefinition).order_by(ApiDefinition.created_at.desc())
    if category:
        query = query.where(ApiDefinition.category == category)
    result = await db.execute(query)
    api_defs = result.scalars().all()
    return [to_camel_response(d) for d in api_defs]


@router.get("/{api_def_id}")
async def get_api_definition(
    api_def_id: str,
    db: AsyncSession = Depends(get_db),
):
    """API 정의 단건 조회"""
    result = await db.execute(
        select(ApiDefinition).where(ApiDefinition.id == api_def_id)
    )
    api_def = result.scalar_one_or_none()
    if not api_def:
        raise HTTPException(status_code=404, detail="API 정의를 찾을 수 없습니다")
    return to_camel_response(api_def)


@router.post("")
async def create_api_definition(
    data: ApiDefinitionCreate,
    db: AsyncSession = Depends(get_db),
):
    """API 정의 생성"""
    api_def_id = f"api-{uuid.uuid4().hex[:8]}"

    snake_data = to_snake_case(data.model_dump())

    api_def = ApiDefinition(id=api_def_id, **snake_data)
    db.add(api_def)
    await db.commit()
    await db.refresh(api_def)
    return to_camel_response(api_def)


@router.patch("/{api_def_id}")
async def update_api_definition(
    api_def_id: str,
    data: ApiDefinitionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """API 정의 수정"""
    result = await db.execute(
        select(ApiDefinition).where(ApiDefinition.id == api_def_id)
    )
    api_def = result.scalar_one_or_none()
    if not api_def:
        raise HTTPException(status_code=404, detail="API 정의를 찾을 수 없습니다")

    update_data = data.model_dump(exclude_unset=True)
    snake_data = to_snake_case(update_data)

    for key, value in snake_data.items():
        setattr(api_def, key, value)

    await db.commit()
    await db.refresh(api_def)
    return to_camel_response(api_def)


@router.delete("/{api_def_id}")
async def delete_api_definition(
    api_def_id: str,
    db: AsyncSession = Depends(get_db),
):
    """API 정의 삭제"""
    result = await db.execute(
        select(ApiDefinition).where(ApiDefinition.id == api_def_id)
    )
    api_def = result.scalar_one_or_none()
    if not api_def:
        raise HTTPException(status_code=404, detail="API 정의를 찾을 수 없습니다")

    await db.delete(api_def)
    await db.commit()
    return {"message": "삭제되었습니다"}


# ── Execution Endpoints ─────────────────────────────────────────────────────

@router.post("/{api_def_id}/execute", response_model=ToolTestResponse)
async def execute_api_definition(
    api_def_id: str,
    inputData: dict = Body(default_factory=dict, embed=True),
    db: AsyncSession = Depends(get_db),
):
    """API 정의 기반 호출 실행"""
    result = await db.execute(
        select(ApiDefinition).where(ApiDefinition.id == api_def_id)
    )
    api_def = result.scalar_one_or_none()
    if not api_def:
        raise HTTPException(status_code=404, detail="API 정의를 찾을 수 없습니다")

    start_time = time.perf_counter()
    logs: list[str] = []

    config = {
        "method": api_def.method,
        "urlTemplate": api_def.url_template,
        "headers": api_def.headers or {},
        "bodyTemplate": api_def.body_template,
        "authType": api_def.auth_type,
        "authConfig": api_def.auth_config or {},
    }

    try:
        logs.append(f"[API_DEF] {api_def.name} (id={api_def.id})")
        api_result = await _execute_api_call(config, inputData, logs)
        execution_time = (time.perf_counter() - start_time) * 1000
        return ToolTestResponse(
            success=True,
            output=api_result,
            executionTimeMs=execution_time,
            logs=logs,
        )
    except Exception as e:
        execution_time = (time.perf_counter() - start_time) * 1000
        return ToolTestResponse(
            success=False,
            error=str(e),
            executionTimeMs=execution_time,
            logs=logs,
        )


# ── Helpers ─────────────────────────────────────────────────────────────────

def _analyze_json(data, fields: list, prefix: str = ""):
    """JSON 구조를 재귀적으로 분석하여 필드 목록 생성"""
    if isinstance(data, list):
        if len(data) > 0:
            _analyze_json(data[0], fields, prefix + "[]." if prefix else "[].")
        return

    if isinstance(data, dict):
        for key, value in data.items():
            full_key = f"{prefix}{key}" if prefix else key
            if isinstance(value, list):
                fields.append({"field": full_key, "type": "array", "description": ""})
                if len(value) > 0 and isinstance(value[0], dict):
                    _analyze_json(value[0], fields, f"{full_key}[].")
            elif isinstance(value, dict):
                fields.append({"field": full_key, "type": "object", "description": ""})
                if prefix.count('.') < 2:  # 최대 3레벨 깊이
                    _analyze_json(value, fields, f"{full_key}.")
            else:
                type_name = "null" if value is None else type(value).__name__
                type_map = {
                    "str": "string",
                    "int": "number",
                    "float": "number",
                    "bool": "boolean",
                }
                fields.append({
                    "field": full_key,
                    "type": type_map.get(type_name, type_name),
                    "description": "",
                })
