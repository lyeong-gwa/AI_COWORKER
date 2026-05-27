"""
Knowledge Document Schemas (파일 기반 - camelCase)

Karpathy v2 (`.omc/plans/지식-karpathy-v2.md` §6.2):
  - POST 요청 시 `page_type` 필수 (5종 enum).
  - `category` + `slug` 가 필수로 격상되어 `id = "{category}/{slug}"` 강제.
  - PUT 은 부분 업데이트 — 모든 필드 optional. `page_type` / `category` 변경 시 enum 검증.

Multi-service v3 (`.omc/plans/지식-multi-service.md` §5.3 — P1):
  - ``KnowledgeCreate.service`` 필수. ``_schema.yaml.services`` enum 강제.
  - ``KnowledgeUpdate.service`` 선택. 제공 시 동일 enum 검증.
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator

PageType = Literal["Summary", "Entity", "Concept", "Comparison", "Synthesis"]


def _validate_service_field(value: Optional[str]) -> Optional[str]:
    """Pydantic field validator 가 사용. None 은 통과 (Update 의 미지정 처리),
    빈 문자열·미정의 service id 는 ``SchemaValidationError`` → FastAPI 422.
    """
    if value is None:
        return value
    # 지연 import — 순환 의존 방지.
    from ..services.knowledge_schema import validate_service

    return validate_service(value)


class KnowledgeCreate(BaseModel):
    """지식 문서 생성 — Karpathy v2 + multi-service v3 요청 스키마.

    필수 신규 필드:
      - ``service``: ``_schema.yaml`` services enum id (필수, multi-service v3).
      - ``page_type``: 5종 enum (Summary/Entity/Concept/Comparison/Synthesis)
      - ``category``: ``_schema.yaml`` 의 카테고리 id (P2 에서 enum 강제, legacy WARN+통과)
      - ``slug``: 영문 kebab-case (`^[a-z0-9]+(-[a-z0-9]+)*$`). 한글 불가.

    ``id`` 는 서버가 ``{category}/{slug}`` 로 자동 생성한다 (요청에 포함 불가).
    """

    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    service: str = Field(
        ...,
        min_length=1,
        description="_schema.yaml services enum 의 id (예: 'codeeyes'). 'unknown' 은 sentinel.",
    )
    category: str = Field(..., min_length=1, description="_schema.yaml 에 정의된 카테고리 id")
    slug: str = Field(..., min_length=1, max_length=64, description="영문 kebab-case (한글 금지)")
    page_type: PageType = Field(..., description="5종 enum 강제")
    tags: List[str] = Field(default_factory=list)
    source: Optional[str] = None
    source_url: Optional[str] = Field(
        default=None,
        description=(
            "외부 참고 URL (LLM 의 URL hallucination 차단용). 명시 지정 시 frontmatter "
            "에 보존, 응답에 노출. None/빈 문자열이면 frontmatter 미기재 → LLM 은 URL "
            "을 만들어내지 않는다."
        ),
    )
    raw_source_id: Optional[str] = Field(default=None, description="RawSource FK (선택)")
    api: Optional[Dict[str, Any]] = None
    operator: Optional[str] = Field(default="cli", description="changelog operator 식별자")

    @field_validator("service")
    @classmethod
    def _check_service(cls, v: str) -> str:
        return _validate_service_field(v)


class KnowledgeUpdate(BaseModel):
    """지식 문서 수정 (PUT — 부분 업데이트).

    모든 필드 optional. 제공된 필드만 갱신. ``page_type`` / ``category`` 변경 시
    P2 에서 enum 검증. ``slug`` 변경은 P2 범위 밖 (id 가 곧 파일경로이므로 별도 rename API 가 필요).

    multi-service v3: ``service`` 가 제공되면 enum 검증 후 frontmatter 에 반영.
    """

    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    content: Optional[str] = Field(default=None, min_length=1)
    service: Optional[str] = Field(default=None, min_length=1)
    category: Optional[str] = Field(default=None, min_length=1)
    page_type: Optional[PageType] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = None
    source_url: Optional[str] = Field(
        default=None,
        description=(
            "외부 참고 URL (LLM URL hallucination 차단). 빈 문자열을 보내면 frontmatter "
            "에서 제거된다. None 은 '미변경' 의미."
        ),
    )
    raw_source_id: Optional[str] = None
    api: Optional[Dict[str, Any]] = None
    operator: Optional[str] = Field(default="cli", description="changelog operator 식별자")

    @field_validator("service")
    @classmethod
    def _check_service(cls, v: Optional[str]) -> Optional[str]:
        return _validate_service_field(v)


class KnowledgeSearchRequest(BaseModel):
    """유사도 검색 요청"""
    query: str = Field(..., min_length=1)
    topK: int = Field(default=5, ge=1, le=20, alias="topK")
    category: Optional[str] = None
