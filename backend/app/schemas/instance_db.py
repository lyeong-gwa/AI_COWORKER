"""InstanceDB Schemas — 파일시스템 재설계 후 (schema·dedupKey 제거).

설계서: ``docs/instance-db-fs-redesign.md``.

요청/응답 모두 camelCase 컨벤션. JSON Schema 검증과 dedup_key 필드는
구 설계 잔재이므로 모두 제거되었다.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── 메타 CRUD ────────────────────────────────────────────────────────────


class InstanceDBCreate(BaseModel):
    """등록 요청."""

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    viewerHints: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "필드별 렌더러 힌트. key = record.data의 필드명, "
            "value = 렌더러 타입 (권장: 'markdown' | 'text' | 'tag' | 'code' | 'json'). "
            "미지정 필드는 plain text 렌더링."
        ),
    )

    model_config = ConfigDict(populate_by_name=True)


class InstanceDBUpdate(BaseModel):
    """수정 요청 — 모든 필드 Optional."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    viewerHints: Optional[Dict[str, str]] = Field(
        default=None,
        description=(
            "필드별 렌더러 힌트. key = record.data의 필드명, "
            "value = 렌더러 타입 (권장: 'markdown' | 'text' | 'tag' | 'code' | 'json'). "
            "미지정 필드는 plain text 렌더링."
        ),
    )

    model_config = ConfigDict(populate_by_name=True)


class InstanceDBResponse(BaseModel):
    """InstanceDB 메타 응답 (camelCase)."""

    id: str
    name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    viewerHints: Dict[str, str] = Field(default_factory=dict)
    createdBy: str = "cli"
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


# ── Record 응답 ────────────────────────────────────────────────────────────


class InstanceDBRecordResponse(BaseModel):
    """InstanceDBRecord 응답 (camelCase). 자유 JSON data + 출처 메타."""

    id: str
    instanceDbId: str
    data: Dict[str, Any]
    sourceWorkflowId: Optional[str] = None
    sourceExecutionId: Optional[str] = None
    sourceWarehouseId: Optional[str] = None
    createdAt: Optional[str] = None


class RecordListResponse(BaseModel):
    """records 리스트 페이지네이션 응답."""

    items: List[InstanceDBRecordResponse]
    total: int
    limit: int
    offset: int


class RecordBulkDeleteRequest(BaseModel):
    """records 다중 삭제 요청.

    ``recordIds`` 와 ``filter`` 둘 중 최소 하나는 비어있지 않아야 한다.
    둘 다 비어있으면 라우트에서 422 로 거부 (전체 wipe 사고 방지).
    둘 다 지정되면 OR 합집합으로 매치된다.
    """

    recordIds: Optional[List[str]] = Field(
        default=None,
        description="직접 지정할 record id 리스트. 존재하는 것만 삭제됨.",
    )
    filter: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "record.data 의 (key, value) 매치 조건. 모든 key 가 일치해야 매치 "
            "(AND 의미). 예: {\"board_id\": 2778}."
        ),
    )

    model_config = ConfigDict(populate_by_name=True)


class RecordBulkDeleteResponse(BaseModel):
    """records 다중 삭제 응답."""

    deletedCount: int
    deletedIds: List[str]


class RecordClearRequest(BaseModel):
    """records 전체 비우기 요청.

    ``confirmDbId`` 가 path 의 idb_id 와 정확히 일치해야만 진행 (실수 방지 안전 가드).
    """

    confirmDbId: str = Field(
        ...,
        description=(
            "삭제할 인스턴스DB 의 id 를 그대로 입력해야 한다. "
            "path 의 idb_id 와 불일치하면 422 로 거부된다."
        ),
    )


class RecordClearResponse(BaseModel):
    """records 전체 비우기 응답."""

    cleared: bool
    instanceDbId: str
    deletedCount: int


__all__ = [
    "InstanceDBCreate",
    "InstanceDBUpdate",
    "InstanceDBResponse",
    "InstanceDBRecordResponse",
    "RecordListResponse",
    "RecordBulkDeleteRequest",
    "RecordBulkDeleteResponse",
    "RecordClearRequest",
    "RecordClearResponse",
]
