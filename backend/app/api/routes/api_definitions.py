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
from ...core.exceptions import NotFoundError
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

@router.get(
    "",
    summary="외부 API 명세 목록",
    description=(
        "CLI 가 등록한 외부 API 호출 템플릿(API Definition)을 반환한다. "
        "``api-call`` / ``ai-api-router`` 노드에서 ``apiDefinitionId`` 로 참조된다."
    ),
)
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
        raise NotFoundError(
            "API 정의를 찾을 수 없습니다",
            details={"apiDefinitionId": api_def_id},
        )
    return to_camel_response(api_def)


@router.post(
    "",
    summary="외부 API 명세 등록",
    description=(
        "CLI가 새로운 외부 API 호출 템플릿을 등록한다. "
        "``method``, ``urlTemplate``, ``headers``, ``bodyTemplate`` 등을 정의하며, "
        "워크플로우의 ``api-call`` / ``api-start`` 노드가 ``apiDefinitionId`` 로 참조한다."
    ),
)
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
        raise NotFoundError(
            "API 정의를 찾을 수 없습니다",
            details={"apiDefinitionId": api_def_id},
        )

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
        raise NotFoundError(
            "API 정의를 찾을 수 없습니다",
            details={"apiDefinitionId": api_def_id},
        )

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
        raise NotFoundError(
            "API 정의를 찾을 수 없습니다",
            details={"apiDefinitionId": api_def_id},
        )

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


@router.post(
    "/{api_def_id}/probe",
    summary="API 실행 + 응답 스키마 자동 저장 (워크플로우 작성 전 필수)",
    description=(
        "등록된 API 를 실제로 호출하고, 응답 JSON 구조를 분석하여 "
        "input_mapping 에 사용 가능한 ``$.path`` 목록을 반환한다. "
        "워크플로우 작성 전 반드시 이 엔드포인트를 호출하여 "
        "실제 응답 구조를 확인한 후 input_mapping 경로를 결정한다. "
        "분석 결과는 api_definitions.response_schema 에 자동 저장된다."
    ),
)
async def probe_api_definition(
    api_def_id: str,
    inputData: dict = Body(default_factory=dict, embed=True),
    db: AsyncSession = Depends(get_db),
):
    """API 실행 → 응답 구조 자동 추출 → response_schema 저장 → 매핑 경로 반환."""
    result = await db.execute(
        select(ApiDefinition).where(ApiDefinition.id == api_def_id)
    )
    api_def = result.scalar_one_or_none()
    if not api_def:
        raise NotFoundError(
            "API 정의를 찾을 수 없습니다",
            details={"apiDefinitionId": api_def_id},
        )

    import time
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
        api_result = await _execute_api_call(config, inputData, logs)
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "mappablePaths": [],
            "arrayGuide": [],
            "responseSchema": {},
        }

    execution_time = (time.perf_counter() - start_time) * 1000

    # 응답 구조 분석
    fields: list[dict] = []
    _analyze_json(api_result, fields)
    response_schema = {
        "fields": fields[:50],
        "example": api_result if not isinstance(api_result, str) else {},
    }

    # response_schema DB에 저장
    api_def.response_schema = response_schema
    await db.commit()

    # input_mapping 에 사용할 수 있는 $.path 목록 생성
    mappable_paths = _extract_mapping_paths(api_result)
    array_guide = _build_array_guide(api_result)

    return {
        "success": True,
        "apiDefId": api_def_id,
        "apiName": api_def.name,
        "executionTimeMs": round(execution_time, 1),
        "rawResponse": api_result,
        "mappablePaths": mappable_paths,
        "arrayGuide": array_guide,
        "schemaUpdated": True,
        "usage": (
            "input_mapping 작성 시 mappablePaths 의 path 값을 그대로 사용하세요. "
            "배열 필드는 unpacker 노드로 처리한 후 아이템 내 필드를 $.fieldName 으로 접근합니다."
        ),
    }


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


def _type_name(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "number"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _safe_example(value, max_len: int = 80):
    """직렬화 가능한 예시 값 반환 (배열/객체는 축약)."""
    if isinstance(value, dict):
        return {k: "..." for k in list(value.keys())[:3]}
    if isinstance(value, list):
        return f"[{len(value)} items]"
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len] + "..."
    return value


def _extract_mapping_paths(data, prefix: str = "$", depth: int = 0) -> list:
    """JSON 응답에서 input_mapping에 직접 쓸 수 있는 $.path 목록 생성.

    배열 항목은 첫 번째 아이템을 기준으로 인덱스($.arr.0.field) 경로도 포함한다.
    """
    if depth > 3:
        return []

    paths = []
    if not isinstance(data, dict):
        return paths

    for k, v in data.items():
        full = f"{prefix}.{k}"
        entry = {
            "path": full,
            "type": _type_name(v),
            "example": _safe_example(v),
        }
        paths.append(entry)

        if isinstance(v, dict) and depth < 2:
            paths.extend(_extract_mapping_paths(v, full, depth + 1))
        elif isinstance(v, list) and len(v) > 0:
            if isinstance(v[0], dict):
                # 첫 아이템 경로 (.0.) 포함
                for ik, iv in v[0].items():
                    paths.append({
                        "path": f"{full}.0.{ik}",
                        "type": _type_name(iv),
                        "example": _safe_example(iv),
                        "note": f"배열 첫 항목 직접 접근. 반복 처리 시 unpacker(arrayField={k}) → 다운스트림에서 $.{ik}",
                    })

    return paths


def _build_array_guide(data) -> list:
    """배열 필드에 대한 unpacker 사용 가이드 생성."""
    guide = []
    if not isinstance(data, dict):
        return guide

    for k, v in data.items():
        if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
            item_fields = list(v[0].keys())
            guide.append({
                "arrayPath": f"$.{k}",
                "arrayField": k,
                "itemCount": len(v),
                "itemFields": item_fields,
                "unpackerConfig": {
                    "arrayField": k,
                },
                "downstreamMapping": {
                    f: f"$.{f}" for f in item_fields[:5]
                },
                "note": (
                    f"unpacker 노드의 config.arrayField = '{k}' 으로 설정하면 "
                    f"각 항목이 개별 실행됩니다. "
                    f"다운스트림 노드에서 항목 필드는 $.{item_fields[0] if item_fields else 'field'} 형식으로 접근합니다."
                ),
            })

    return guide
