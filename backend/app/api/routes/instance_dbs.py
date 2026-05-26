"""InstanceDB Routes — 파일시스템 재설계 후 메타 CRUD + records 조회.

설계서: ``docs/instance-db-fs-redesign.md``.

엔드포인트:
- POST   /api/v1/instance-dbs                     메타 등록
- GET    /api/v1/instance-dbs                     목록 (검색 q)
- GET    /api/v1/instance-dbs/{id}                상세
- PUT    /api/v1/instance-dbs/{id}                수정
- DELETE /api/v1/instance-dbs/{id}                삭제 (폴더 통째)
- GET    /api/v1/instance-dbs/{id}/records        records 리스트
- GET    /api/v1/instance-dbs/{id}/records/{rid}  단일 record

참조 차단(``_count_workflow_references``) 로직은 그대로 유지 — 워크플로우의
instance-db-* / sorter rule 이 이 InstanceDB 를 참조하면 409. ``?force=true`` 로
우회 가능. WorkflowNode 조회를 위해 라우트는 store + AsyncSession 둘 다 의존.

응답은 camelCase 컨벤션을 따른다.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.exceptions import ConflictError, NotFoundError, ValidationError
from ...models.workflow import WorkflowNode
from ...schemas.instance_db import (
    InstanceDBCreate,
    InstanceDBRecordResponse,
    InstanceDBUpdate,
    RecordListResponse,
)
from ...services.instance_db_store import (
    InstanceDBStore,
    get_instance_db_store,
)

router = APIRouter()


# ── 직렬화 헬퍼 ────────────────────────────────────────────────────────────


def _camel_record(rec: dict, db_id: str) -> dict:
    """파일에서 읽은 record dict → API camelCase 응답.

    record 파일 내부에는 ``_source`` 객체로 출처가 묶여 있지만, API 응답은
    ``sourceWorkflowId`` 같은 평탄한 카멜키를 노출한다.
    """
    src = rec.get("_source") or {}
    return {
        "id": rec.get("id"),
        "instanceDbId": db_id,
        "data": rec.get("data") or {},
        "sourceWorkflowId": src.get("workflowId"),
        "sourceExecutionId": src.get("executionId"),
        "sourceWarehouseId": src.get("warehouseId"),
        "createdAt": rec.get("createdAt"),
    }


# ── 메타 CRUD ──────────────────────────────────────────────────────────────


@router.post(
    "",
    status_code=201,
    summary="인스턴스DB 등록",
    description=(
        "동질 record 컬렉션의 메타(이름·설명·태그)를 등록한다. "
        "name 중복은 409 CONFLICT. 폴더 ``{db_id}/`` 와 ``meta.json`` 이 생성된다."
    ),
)
async def create_instance_db(
    data: InstanceDBCreate,
    store: InstanceDBStore = Depends(get_instance_db_store),
):
    try:
        meta = await store.create_meta(
            name=data.name,
            description=data.description,
            tags=list(data.tags or []),
            viewer_hints=data.viewerHints or {},
        )
    except ValueError as err:
        msg = str(err)
        if msg.startswith("duplicate name"):
            raise ConflictError(
                "동일한 이름의 인스턴스DB가 이미 존재합니다",
                details={"name": data.name},
            )
        raise ValidationError(msg, details={"field": "name"})
    return meta


@router.get(
    "",
    summary="인스턴스DB 목록",
    description="검색어 ``q`` 가 있으면 name/description 부분 일치 (대소문자 무시).",
)
async def list_instance_dbs(
    q: Optional[str] = Query(None, description="이름·설명 부분 일치 검색"),
    store: InstanceDBStore = Depends(get_instance_db_store),
):
    return await store.list_meta(q=q)


@router.get("/{instance_db_id}", summary="인스턴스DB 상세")
async def get_instance_db(
    instance_db_id: str,
    store: InstanceDBStore = Depends(get_instance_db_store),
):
    meta = await store.get_meta(instance_db_id)
    if meta is None:
        raise NotFoundError(
            "인스턴스DB를 찾을 수 없습니다",
            details={"instanceDbId": instance_db_id},
        )
    return meta


@router.put(
    "/{instance_db_id}",
    summary="인스턴스DB 수정",
    description="name 중복 변경 요청 시 409 CONFLICT.",
)
async def update_instance_db(
    instance_db_id: str,
    data: InstanceDBUpdate,
    store: InstanceDBStore = Depends(get_instance_db_store),
):
    # 사전 존재 확인 — KeyError 를 404 envelope 으로 변환
    meta = await store.get_meta(instance_db_id)
    if meta is None:
        raise NotFoundError(
            "인스턴스DB를 찾을 수 없습니다",
            details={"instanceDbId": instance_db_id},
        )

    fields = data.model_dump(exclude_unset=True)
    try:
        updated = await store.update_meta(instance_db_id, **fields)
    except KeyError:
        raise NotFoundError(
            "인스턴스DB를 찾을 수 없습니다",
            details={"instanceDbId": instance_db_id},
        )
    except ValueError as err:
        msg = str(err)
        if msg.startswith("duplicate name"):
            raise ConflictError(
                "동일한 이름의 인스턴스DB가 이미 존재합니다",
                details={"name": fields.get("name")},
            )
        raise ValidationError(msg)
    return updated


@router.delete(
    "/{instance_db_id}",
    summary="인스턴스DB 삭제",
    description=(
        "폴더 통째 삭제 (모든 record 포함). 기본적으로 워크플로우의 "
        "instance-db-insert / instance-db-lookup 노드 또는 sorter rule 이 "
        "이 InstanceDB 를 참조하면 409 INSTANCE_DB_REFERENCED 로 차단한다. "
        "``?force=true`` 로 우회 가능."
    ),
)
async def delete_instance_db(
    instance_db_id: str,
    force: bool = Query(
        False,
        description="True 면 참조 검증을 우회하고 삭제를 강행한다",
    ),
    db: AsyncSession = Depends(get_db),
    store: InstanceDBStore = Depends(get_instance_db_store),
):
    meta = await store.get_meta(instance_db_id)
    if meta is None:
        raise NotFoundError(
            "인스턴스DB를 찾을 수 없습니다",
            details={"instanceDbId": instance_db_id},
        )

    if not force:
        ref_count = await _count_workflow_references(db, instance_db_id)
        if ref_count > 0:
            raise ConflictError(
                "이 인스턴스DB 를 참조하는 워크플로우 노드가 존재합니다",
                code="INSTANCE_DB_REFERENCED",
                details={
                    "refCount": ref_count,
                    "force": "set ?force=true to override",
                },
            )

    try:
        await store.delete_db(instance_db_id)
    except KeyError:
        raise NotFoundError(
            "인스턴스DB를 찾을 수 없습니다",
            details={"instanceDbId": instance_db_id},
        )
    return {"message": "삭제되었습니다", "id": instance_db_id}


# ── records 조회 ───────────────────────────────────────────────────────────


@router.get(
    "/{instance_db_id}/records",
    response_model=RecordListResponse,
    summary="records 리스트",
    description=(
        "limit/offset 페이지네이션. createdAt 내림차순. "
        "``sourceWorkflowId`` / ``sourceExecutionId`` 지정 시 AND 필터 적용."
    ),
)
async def list_records(
    instance_db_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sourceWorkflowId: Optional[str] = Query(None, alias="sourceWorkflowId"),
    sourceExecutionId: Optional[str] = Query(None, alias="sourceExecutionId"),
    store: InstanceDBStore = Depends(get_instance_db_store),
):
    try:
        items, total = await store.list_records(
            instance_db_id,
            limit=limit,
            offset=offset,
            source_workflow_id=sourceWorkflowId,
            source_execution_id=sourceExecutionId,
        )
    except KeyError:
        raise NotFoundError(
            "인스턴스DB를 찾을 수 없습니다",
            details={"instanceDbId": instance_db_id},
        )

    return RecordListResponse(
        items=[
            InstanceDBRecordResponse(**_camel_record(r, instance_db_id))
            for r in items
        ],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{instance_db_id}/records/{record_id}",
    response_model=InstanceDBRecordResponse,
    summary="record 단건 조회",
)
async def get_record(
    instance_db_id: str,
    record_id: str,
    store: InstanceDBStore = Depends(get_instance_db_store),
):
    try:
        rec = await store.get_record(instance_db_id, record_id)
    except KeyError:
        raise NotFoundError(
            "인스턴스DB를 찾을 수 없습니다",
            details={"instanceDbId": instance_db_id},
        )
    if rec is None:
        raise NotFoundError(
            "record를 찾을 수 없습니다",
            details={"instanceDbId": instance_db_id, "recordId": record_id},
        )
    return InstanceDBRecordResponse(**_camel_record(rec, instance_db_id))


@router.get(
    "/{instance_db_id}/records/{record_id}/export",
    summary="record 즉석 변환 다운로드",
    description=(
        "record 를 md / csv / html / xlsx 포맷으로 즉시 변환하여 스트림 응답으로 반환한다. "
        "변환 결과는 디스크에 저장되지 않는다. "
        "``field`` 가 지정되면 ``record.data[field]`` 만 변환하고, "
        "미지정 시 record 전체를 직렬화한다."
    ),
)
async def export_record_endpoint(
    instance_db_id: str,
    record_id: str,
    format: str = Query(..., description="변환 포맷: md | csv | html | xlsx"),
    field: Optional[str] = Query(None, description="record.data 의 특정 필드 키 (미지정 시 전체)"),
    store: InstanceDBStore = Depends(get_instance_db_store),
):
    # format 유효성 검사
    _VALID_FORMATS = {"md", "csv", "html", "xlsx"}
    if format not in _VALID_FORMATS:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 포맷: '{format}'. 지원 포맷: {sorted(_VALID_FORMATS)}",
        )

    # record 조회
    try:
        rec = await store.get_record(instance_db_id, record_id)
    except KeyError:
        raise NotFoundError(
            "인스턴스DB를 찾을 수 없습니다",
            details={"instanceDbId": instance_db_id},
        )
    if rec is None:
        raise NotFoundError(
            "record를 찾을 수 없습니다",
            details={"instanceDbId": instance_db_id, "recordId": record_id},
        )

    # viewerHints 추출
    meta = await store.get_meta(instance_db_id)
    viewer_hints: dict = (meta or {}).get("viewerHints") or {}

    # 변환
    from ...services.record_exporter import export_record
    try:
        content, mime_type, filename = export_record(
            rec,
            format,
            field=field,
            viewer_hints=viewer_hints,
        )
    except ImportError as e:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail=f"xlsx 변환에 필요한 openpyxl 패키지가 설치되어 있지 않습니다: {e}",
        )

    return Response(
        content=content,
        media_type=mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# ── 내부 헬퍼 ──────────────────────────────────────────────────────────────


async def _count_workflow_references(db: AsyncSession, instance_db_id: str) -> int:
    """``instance_db_id`` 를 참조하는 워크플로우 노드 개수를 in-memory 로 집계한다.

    검사 대상:
    - ``definition_type in ('instance-db-insert', 'instance-db-lookup')`` 인 노드의
      ``config['instanceDbId']`` 가 동일한 경우.
    - ``definition_type == 'sorter'`` 인 노드의 ``config['rules']`` 안에 dataSource
      ``'instance-db'`` rule 이 있고 그 rule 의 ``instanceDbId`` 가 동일한 경우.

    SQLite/PostgreSQL JSON path 차이를 흡수하기 위해 SQL 단계에서는 후보 노드들만
    얕게 좁힌 뒤 Python 메모리에서 config 를 검사한다.
    """
    candidate_types = ("instance-db-insert", "instance-db-lookup", "sorter")
    res = await db.execute(
        select(WorkflowNode).where(WorkflowNode.definition_type.in_(candidate_types))
    )
    nodes = res.scalars().all()

    count = 0
    for n in nodes:
        cfg = n.config if isinstance(n.config, dict) else {}
        dtype = n.definition_type
        if dtype in ("instance-db-insert", "instance-db-lookup"):
            if cfg.get("instanceDbId") == instance_db_id:
                count += 1
            continue
        rules = cfg.get("rules")
        if not isinstance(rules, list):
            continue
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            data_source = rule.get("dataSource") or "input"
            if not isinstance(data_source, str):
                continue
            if data_source.lower() != "instance-db":
                continue
            if rule.get("instanceDbId") == instance_db_id:
                count += 1
                break
    return count
