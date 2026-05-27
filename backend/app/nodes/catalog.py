"""
Node Catalog — CLI가 워크플로우를 조립할 때 참조하는 Single Source of Truth.

LLM CLI(Claude Code 등)가 `GET /api/v1/nodes/catalog`로 조회하여
사용 가능한 노드의 스펙(inputs/outputs/config/useCases/connectsWellWith)을
파악한다. 프론트엔드 노드 뷰어도 동일 데이터를 사용할 수 있다.

범용 노드 13종을 노출한다 (도메인 특화 노드 금지):
- 11종 핵심 (form-start, api-start, ai-custom, ai-api-router, sorter, unpacker,
  mapper, api-call, knowledge, result, markdown-viewer)
- 2종 인스턴스DB (instance-db-insert, instance-db-lookup) — Phase A에서 메타만 등록,
  실제 핸들러는 Phase B에서 등록.
"""

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


# ── 스키마 정의 ────────────────────────────────────────────────────────────

IOType = Literal["string", "number", "boolean", "array", "object", "any"]
ConfigType = Literal["string", "number", "boolean", "array", "object"]
Category = Literal["starter", "ai", "logic", "action", "output"]


class NodeIOField(BaseModel):
    """노드의 입력/출력 필드 스펙."""

    name: str
    type: IOType
    required: bool = False
    description: str
    example: Optional[Any] = None


class NodeConfigField(BaseModel):
    """노드 설정 필드 스펙."""

    name: str
    type: ConfigType
    default: Optional[Any] = None
    description: str
    required: bool = False


class NodeCatalogEntry(BaseModel):
    """카탈로그 단일 엔트리 — 한 노드 타입의 모든 메타를 담는다."""

    defType: str = Field(..., description="NodeDefType enum value (예: 'form-start')")
    label: str = Field(..., description="UI에 표시될 사람 읽기용 이름")
    category: Category
    purpose: str = Field(
        ...,
        description="1-2 문장. CLI가 이 노드의 용도를 판단할 근거가 된다.",
    )
    inputs: List[NodeIOField] = Field(default_factory=list)
    outputs: List[NodeIOField] = Field(default_factory=list)
    config: List[NodeConfigField] = Field(default_factory=list)
    useCases: List[str] = Field(
        default_factory=list,
        description="이 노드를 언제 쓰는지 보여주는 구체적 시나리오 (few-shot 힌트)",
    )
    connectsWellWith: List[str] = Field(
        default_factory=list,
        description="다음 단계로 자주 이어지는 노드의 defType 리스트",
    )
    requiresUpstream: bool = Field(
        default=True,
        description="starter 노드는 False. 그 외는 True",
    )
    producesArray: bool = Field(
        default=False,
        description="출력이 배열인지 여부 (unpacker 연결 필요 판단)",
    )


# ── 카탈로그 정의 ──────────────────────────────────────────────────────────

CATALOG: List[NodeCatalogEntry] = [
    # ── starter ───────────────────────────────────────────────────────────
    NodeCatalogEntry(
        defType="form-start",
        label="폼 시작",
        category="starter",
        purpose=(
            "사용자가 웹에서 실행 버튼을 누르면 입력 폼을 렌더하여 워크플로우를 "
            "시작하는 트리거. 사용자 입력이 후속 노드의 입력 데이터가 된다."
        ),
        inputs=[],
        outputs=[
            NodeIOField(
                name="<사용자_정의_필드>",
                type="any",
                required=False,
                description=(
                    "config.fields에 정의한 각 필드가 그대로 출력 키가 된다. "
                    "config.fields가 비어 있으면 다운스트림 AI 노드의 inputSchema에서 자동 도출한다."
                ),
            ),
        ],
        config=[
            NodeConfigField(
                name="mode",
                type="string",
                default="manual",
                description="'manual' (수동 실행 버튼) 또는 'schedule' (스케줄러 데몬 연동 예정)",
                required=False,
            ),
            NodeConfigField(
                name="scheduleConfig",
                type="object",
                default=None,
                description=(
                    "mode='schedule'일 때 사용. {type: 'hourly'|'daily'|'weekly'|'monthly', "
                    "hour, minute, dayOfWeek, dayOfMonth}"
                ),
                required=False,
            ),
            NodeConfigField(
                name="fields",
                type="array",
                default=[],
                description=(
                    "렌더할 폼 필드 리스트. 각 요소: {name, label, type: 'string'|'number'|'boolean', required}. "
                    "비우면 다운스트림 AI 노드의 inputSchema에서 자동 도출한다."
                ),
                required=False,
            ),
            NodeConfigField(
                name="defaultValues",
                type="object",
                default={},
                description="각 필드의 초기값 (선택)",
                required=False,
            ),
        ],
        useCases=[
            "사용자가 질문을 입력하고 AI가 답변하는 Q&A 워크플로우의 시작점",
            "티켓 번호·키워드 등을 받아 조회/분류 파이프라인을 시작",
            "보고서 제목·대상기간을 받아 생성 파이프라인을 시작",
        ],
        connectsWellWith=["ai-custom", "knowledge", "api-call", "ai-api-router", "mapper", "sorter"],
        requiresUpstream=False,
        producesArray=False,
    ),
    NodeCatalogEntry(
        defType="api-start",
        label="API 시작",
        category="starter",
        purpose=(
            "등록된 API 명세를 호출한 결과로 워크플로우를 시작하는 트리거. "
            "외부 시스템에서 주기적으로 수집해야 하는 데이터의 진입점으로 사용."
        ),
        inputs=[],
        outputs=[
            NodeIOField(
                name="status",
                type="number",
                required=True,
                description="HTTP 상태 코드",
                example=200,
            ),
            NodeIOField(
                name="data",
                type="object",
                required=True,
                description=(
                    "API 응답 본문. 응답이 JSON이 아니면 문자열이다. "
                    "API 명세의 response_schema에 정의된 필드 구조를 따른다."
                ),
            ),
        ],
        config=[
            NodeConfigField(
                name="apiDefinitionId",
                type="string",
                default=None,
                description="등록된 API 명세의 ID (POST /api/v1/api-definitions 로 먼저 등록)",
                required=True,
            ),
            NodeConfigField(
                name="mode",
                type="string",
                default="manual",
                description="'manual' 또는 'schedule'",
                required=False,
            ),
            NodeConfigField(
                name="scheduleConfig",
                type="object",
                default=None,
                description="스케줄 실행 설정 (form-start와 동일 스키마)",
                required=False,
            ),
            NodeConfigField(
                name="defaultParams",
                type="object",
                default={},
                description=(
                    "API 호출에 사용할 기본 파라미터. url_template의 {{변수}}와 "
                    "parameters[in=query/path/body]에 매핑된다."
                ),
                required=False,
            ),
        ],
        useCases=[
            "목업API에서 문의글 목록을 주기적으로 수집",
            "외부 티켓/이슈 시스템에서 신규 항목을 가져와 후속 처리",
            "웹훅 대신 풀(polling) 방식으로 외부 데이터 스냅샷 확보",
        ],
        connectsWellWith=["unpacker", "sorter", "mapper", "ai-custom", "result"],
        requiresUpstream=False,
        producesArray=False,
    ),
    # ── ai ────────────────────────────────────────────────────────────────
    NodeCatalogEntry(
        defType="ai-custom",
        label="AI 커스텀",
        category="ai",
        purpose=(
            "등록된 커스텀 AI 노드(ai_nodes 테이블)를 실행하거나, 노드 config에 "
            "프롬프트를 직접 설정하여 LLM을 호출한다. 입력 스키마 기반 자동 타입 변환과 "
            "노드 인스턴스별 FIFO 큐잉을 제공한다."
        ),
        inputs=[
            NodeIOField(
                name="<ai_node.input_schema에_정의된_필드>",
                type="any",
                required=False,
                description=(
                    "ai_node_id가 연결된 경우 해당 AI 노드의 input_schema.properties 키들이 입력이 된다. "
                    "업스트림 벨트 데이터에서 자동 매핑되며, dict/list는 JSON 문자열로 강제 변환된다."
                ),
            ),
        ],
        outputs=[
            NodeIOField(
                name="<ai_node.output_schema에_정의된_필드>",
                type="any",
                required=False,
                description=(
                    "ai_node_id가 연결된 경우 output_schema.properties 구조를 따른다. "
                    "연결되지 않은 경우 {'response': string} 형태로 반환된다."
                ),
            ),
        ],
        config=[
            NodeConfigField(
                name="ai_node_id",
                type="string",
                default=None,
                description=(
                    "사용할 커스텀 AI 노드의 ID (POST /api/v1/nodes 로 먼저 등록). "
                    "비어있으면 아래 prompt/systemPrompt로 직접 호출."
                ),
                required=False,
            ),
            NodeConfigField(
                name="prompt",
                type="string",
                default="",
                description="사용자 프롬프트 템플릿 ({{변수}} 치환 지원). ai_node_id 없을 때만 사용.",
                required=False,
            ),
            NodeConfigField(
                name="systemPrompt",
                type="string",
                default=None,
                description="시스템 프롬프트 ({{변수}} 치환 지원). ai_node_id 없을 때만 사용.",
                required=False,
            ),
            NodeConfigField(
                name="model",
                type="string",
                default="gpt-4o-mini",
                description="LLM 모델명 (ai_node_id 없을 때만 사용)",
                required=False,
            ),
            NodeConfigField(
                name="provider",
                type="string",
                default="openai",
                description="'openai' | 'anthropic' (ai_node_id 없을 때만 사용)",
                required=False,
            ),
            NodeConfigField(
                name="temperature",
                type="number",
                default=0.7,
                description="LLM 온도 (ai_node_id 없을 때만 사용)",
                required=False,
            ),
            NodeConfigField(
                name="maxTokens",
                type="number",
                default=2000,
                description="LLM 최대 출력 토큰 (ai_node_id 없을 때만 사용)",
                required=False,
            ),
        ],
        useCases=[
            "사용자 입력을 특정 업무 도메인 언어로 분류/태깅",
            "여러 지식문서와 질문을 받아 답변 본문(마크다운) 생성",
            "API 응답 데이터를 사람이 읽기 좋은 요약문으로 가공",
            "구조화된 JSON 출력을 output_schema로 강제하여 후속 노드가 안정적으로 소비",
        ],
        connectsWellWith=["markdown-viewer", "result", "sorter", "mapper", "api-call"],
        requiresUpstream=True,
        producesArray=False,
    ),
    NodeCatalogEntry(
        defType="ai-api-router",
        label="AI API 라우터",
        category="ai",
        purpose=(
            "입력 데이터를 AI가 분석하여 등록된 여러 API 명세 중 가장 적절한 것을 "
            "선택·호출하고 응답을 반환한다. 명확한 목적과 필수 파라미터가 모두 갖춰져야만 호출한다."
        ),
        inputs=[
            NodeIOField(
                name="<임의>",
                type="any",
                required=False,
                description="업스트림 벨트 데이터 전체. AI가 판단 근거로 사용한다.",
            ),
        ],
        outputs=[
            NodeIOField(
                name="api_route",
                type="object",
                required=True,
                description=(
                    "라우팅 결과. 구조: "
                    "{called: boolean, reason: string, apiId: string|null, apiName: string|null, "
                    "request: {method, url, parameters, body}|null, "
                    "response: {status, data}|null}"
                ),
            ),
        ],
        config=[
            NodeConfigField(
                name="prompt",
                type="string",
                default="",
                description="AI에게 전달할 추가 지시사항 ({{변수}} 치환 지원, 선택)",
                required=False,
            ),
            NodeConfigField(
                name="apiIds",
                type="array",
                default=[],
                description=(
                    "후보로 제공할 API 정의 ID 리스트. 비우면 모든 활성 API 중에서 선택한다."
                ),
                required=False,
            ),
        ],
        useCases=[
            "사용자의 자연어 질문이 '티켓 조회'인지 '권한 요청'인지 판단해 해당 API 호출",
            "여러 업무 시스템 중 입력 맥락에 맞는 하나만 자동으로 호출",
            "'적절한 API가 없다'는 판단도 명시적으로 받아 안내 메시지로 대체",
        ],
        connectsWellWith=["ai-custom", "markdown-viewer", "result", "sorter"],
        requiresUpstream=True,
        producesArray=False,
    ),
    # ── logic ─────────────────────────────────────────────────────────────
    NodeCatalogEntry(
        defType="sorter",
        label="분류기",
        category="logic",
        purpose=(
            "config.rules의 조건을 순차 평가하여 매칭된 규칙의 handle로만 다운스트림을 통과시킨다. "
            "어떤 규칙에도 맞지 않으면 'default' handle로 흐른다. 선택적으로 창고 축적과 중복 필터를 수행한다."
        ),
        inputs=[
            NodeIOField(
                name="<임의>",
                type="any",
                required=False,
                description="업스트림 벨트 데이터. rules[].field에서 dot-path로 값을 추출해 평가.",
            ),
        ],
        outputs=[
            NodeIOField(
                name="__sorterHandle",
                type="string",
                required=True,
                description=(
                    "실행 엔진이 라우팅에 사용하는 내부 키. 'rule-<id>' 또는 'default' 또는 "
                    "중복 감지 시 '__skip__'. 다운스트림 소비용 필드가 아님."
                ),
            ),
        ],
        config=[
            NodeConfigField(
                name="rules",
                type="array",
                default=[],
                description=(
                    "분류 규칙 리스트. 각 요소는 dataSource 에 따라 두 가지 형식 중 하나. "
                    "출력 handle id 는 모두 'rule-<id>'. "
                    "(A) dataSource='input' (기본): "
                    "{id, dataSource?: 'input', field: string (dot-path), "
                    "operator: 'equals'|'notEquals'|'contains'|'startsWith'|'endsWith'|"
                    "'greaterThan'|'lessThan'|'exists'|'notExists'|'regex', "
                    "value: string}. "
                    "(B) dataSource='instance-db' (확장): "
                    "{id, dataSource: 'instance-db', instanceDbId: string, "
                    "filterTemplate?: object (record.data 와 dot-path 동등 비교, "
                    "각 값 {{변수}} 치환 — 비어있으면 1건이라도 있으면 exists 매칭), "
                    "condition: 'exists' | 'not_exists' (기본 exists)}. "
                    "후방 호환: dataSource 미지정 rule 은 'input' 으로 해석."
                ),
                required=True,
            ),
            NodeConfigField(
                name="dedup",
                type="object",
                default={},
                description=(
                    "중복 필터(선택). {enabled: bool, warehouseNodeId: string, matchField: string}. "
                    "enabled=true면 참조 창고에 matchField 값이 이미 있으면 skip handle로 보낸다."
                ),
                required=False,
            ),
        ],
        useCases=[
            "티켓 카테고리에 따라 '인프라', '권한관리', '장비' 등 개별 처리 라인으로 분기",
            "이미 처리된 항목(창고에 존재)을 중복 필터로 제거",
            "우선순위 상/중/하 별로 다른 다운스트림 체인 호출",
        ],
        connectsWellWith=["ai-custom", "api-call", "knowledge", "mapper", "result"],
        requiresUpstream=True,
        producesArray=False,
    ),
    NodeCatalogEntry(
        defType="unpacker",
        label="언패커",
        category="logic",
        purpose=(
            "배열 필드를 개별 아이템으로 풀어 각 아이템마다 다운스트림 체인 전체를 반복 실행한다. "
            "API로 받은 리스트 데이터를 아이템 단위로 처리할 때 사용."
        ),
        inputs=[
            NodeIOField(
                name="<arrayField로_지정한_경로>",
                type="array",
                required=True,
                description=(
                    "config.arrayField (dot-path)가 가리키는 위치에 배열이 있어야 한다. "
                    "예: 'data' 또는 'data.items'."
                ),
            ),
        ],
        outputs=[
            NodeIOField(
                name="items",
                type="array",
                required=True,
                description="언팩된 원본 배열 (요약 조회용)",
            ),
            NodeIOField(
                name="count",
                type="number",
                required=True,
                description="배열 길이",
            ),
            NodeIOField(
                name="<각_아이템의_키들>",
                type="any",
                required=False,
                description=(
                    "각 반복 실행에서 아이템의 키가 다운스트림 벨트에 최상위로 주입된다. "
                    "아이템이 dict가 아니면 {value: <원본>}로 감싸진다. "
                    "_item_index (현재 인덱스)와 _item_total (전체 개수)도 함께 주입된다."
                ),
            ),
        ],
        config=[
            NodeConfigField(
                name="arrayField",
                type="string",
                default="",
                description=(
                    "배열이 있는 경로 (dot-path 지원, 예: 'data' 또는 'data.items'). "
                    "업스트림 벨트 데이터 기준."
                ),
                required=True,
            ),
        ],
        useCases=[
            "api-start에서 받은 {data: [...]} 응답을 각 레코드 단위로 AI에 전달",
            "knowledge 검색 결과 배열을 순회하며 개별 처리",
            "상위 노드가 생성한 질문 리스트를 각각 실행",
        ],
        connectsWellWith=["ai-custom", "api-call", "knowledge", "mapper", "sorter", "result"],
        requiresUpstream=True,
        producesArray=True,
    ),
    NodeCatalogEntry(
        defType="mapper",
        label="매퍼",
        category="logic",
        purpose=(
            "이전에 축적된 창고(warehouse) 데이터에서 동일한 키 값을 가진 항목을 찾아 "
            "현재 입력에 병합한다. 키 기반 조인과 유사하며 과거 실행 결과 참조에 유용."
        ),
        inputs=[
            NodeIOField(
                name="<matchKey로_지정한_경로>",
                type="any",
                required=True,
                description=(
                    "config.matchKey (dot-path)가 가리키는 값이 조인 키로 쓰인다. "
                    "값이 없으면 빈 매칭으로 처리."
                ),
            ),
        ],
        outputs=[
            NodeIOField(
                name="matchedItems",
                type="array",
                required=True,
                description=(
                    "창고에서 조회된 일치 항목들의 data 리스트. "
                    "config.outputField로 키 이름 커스터마이즈 가능 (기본 'matchedItems')."
                ),
            ),
            NodeIOField(
                name="matchedCount",
                type="number",
                required=True,
                description="일치 항목 개수",
            ),
        ],
        config=[
            NodeConfigField(
                name="warehouseNodeId",
                type="string",
                default="",
                description=(
                    "참조할 창고 역할 노드(result/markdown-viewer/sorter)의 instance id. "
                    "해당 노드가 실행 시 축적한 WarehouseEntry를 조회한다."
                ),
                required=True,
            ),
            NodeConfigField(
                name="matchKey",
                type="string",
                default="",
                description=(
                    "매칭 키 경로 (dot-path 지원). 입력과 창고 데이터 양쪽에서 동일 경로 값을 비교."
                ),
                required=True,
            ),
            NodeConfigField(
                name="outputField",
                type="string",
                default="matchedItems",
                description="매칭 결과를 담을 출력 필드명",
                required=False,
            ),
        ],
        useCases=[
            "현재 티켓과 동일 category의 과거 티켓을 불러와 AI에 참고 자료로 전달",
            "사용자ID로 해당 사용자의 과거 요청 이력을 조회",
            "API 응답의 특정 필드 값으로 창고 레코드를 찾아 상세 정보 병합",
        ],
        connectsWellWith=["ai-custom", "markdown-viewer", "result"],
        requiresUpstream=True,
        producesArray=False,
    ),
    # ── action ────────────────────────────────────────────────────────────
    NodeCatalogEntry(
        defType="api-call",
        label="API 호출",
        category="action",
        purpose=(
            "등록된 API 명세를 참조하여 외부 API를 직접 호출한다. AI 판단 없이 정해진 API를 "
            "실행하는 경우 사용(반면 ai-api-router는 AI가 API를 선택)."
        ),
        inputs=[
            NodeIOField(
                name="<API_명세의_parameters_이름들>",
                type="any",
                required=False,
                description=(
                    "api-definition의 parameters[].name과 url_template의 {{변수}}가 매핑된다. "
                    "입력 벨트 데이터 > config.defaultParams 순서로 우선순위."
                ),
            ),
        ],
        outputs=[
            NodeIOField(
                name="status",
                type="number",
                required=True,
                description="HTTP 상태 코드",
            ),
            NodeIOField(
                name="data",
                type="object",
                required=True,
                description=(
                    "API 응답 본문. JSON 파싱 실패 시 문자열. API 명세의 response_schema 구조를 따른다."
                ),
            ),
        ],
        config=[
            NodeConfigField(
                name="apiDefinitionId",
                type="string",
                default=None,
                description="호출할 API 명세의 ID (POST /api/v1/api-definitions 로 먼저 등록)",
                required=True,
            ),
            NodeConfigField(
                name="defaultParams",
                type="object",
                default={},
                description="업스트림 입력이 비어있을 때 사용할 기본 파라미터 값",
                required=False,
            ),
        ],
        useCases=[
            "분류기 분기 후 인프라 티켓만 담당부서 API로 전달",
            "사용자 입력으로부터 추출한 ID로 외부 시스템 레코드 생성/수정",
            "주기적 데이터 수집에서 후속 상세 조회 단계",
        ],
        connectsWellWith=["ai-custom", "unpacker", "sorter", "mapper", "result", "markdown-viewer"],
        requiresUpstream=True,
        producesArray=False,
    ),
    NodeCatalogEntry(
        defType="knowledge",
        label="지식 검색",
        category="action",
        purpose=(
            "지식베이스(ChromaDB 벡터 DB)에서 RAG 방식 유사도 검색을 수행한다. "
            "AI 노드에 전달할 컨텍스트(참고 문서)를 확보할 때 사용."
        ),
        inputs=[
            NodeIOField(
                name="<searchField로_지정한_경로>",
                type="string",
                required=False,
                description=(
                    "config.searchField가 가리키는 문자열이 검색 쿼리가 된다. "
                    "미지정 시 입력의 모든 문자열 값을 공백으로 연결해 쿼리로 사용."
                ),
            ),
        ],
        outputs=[
            NodeIOField(
                name="knowledge",
                type="array",
                required=True,
                description=(
                    "검색 결과 배열. 각 요소: "
                    "{id: string, content: string, score: number, title: string, category: string, "
                    "service: string (multi-service v3 P2), tags: string, page_type: string, "
                    "version: number, links: array, source_url: string|null}. "
                    "source_url: 외부 참고 URL. null 인 페이지는 LLM 이 URL 을 만들어내지 "
                    "않도록 system prompt 가 차단해야 한다."
                ),
            ),
            NodeIOField(
                name="search_categories",
                type="array",
                required=False,
                description="실제 필터에 사용된 카테고리 (config.categories 설정 시)",
            ),
            NodeIOField(
                name="search_services",
                type="array",
                required=False,
                description=(
                    "Multi-service v3 P2 — 실제 필터에 사용된 service 리스트 "
                    "(config.services 설정 시에만 노출)"
                ),
            ),
        ],
        config=[
            NodeConfigField(
                name="searchField",
                type="string",
                default="",
                description=(
                    "검색어를 뽑을 입력 필드 경로 (dot-path). "
                    "비우면 입력 dict의 모든 문자열 값을 연결해 쿼리 구성."
                ),
                required=False,
            ),
            NodeConfigField(
                name="categories",
                type="array",
                default=[],
                description="검색을 제한할 카테고리 리스트 (ChromaDB where 필터)",
                required=False,
            ),
            NodeConfigField(
                name="services",
                type="array",
                default=[],
                description=(
                    "Multi-service v3 P2 — 검색을 제한할 service id 리스트 "
                    "(_schema.yaml services enum). 다중 시 ChromaDB $in, "
                    "categories/pageTypes 와 결합 시 $and 로 적용된다."
                ),
                required=False,
            ),
            NodeConfigField(
                name="tags",
                type="array",
                default=[],
                description="결과에 교차해 유지할 태그 리스트 (후처리 필터)",
                required=False,
            ),
            NodeConfigField(
                name="maxResults",
                type="number",
                default=5,
                description=(
                    "최대 반환 개수 (실제로 KNOWLEDGE_MIN_RESULTS=4 이상, "
                    "KNOWLEDGE_MAX_RESULTS=7 이하로 클램프됨)"
                ),
                required=False,
            ),
            NodeConfigField(
                name="pageTypes",
                type="array",
                default=[],
                description=(
                    "Karpathy v2 P3 — Summary/Entity/Concept/Comparison/Synthesis 필터. "
                    "categories 와 결합 시 $and 로 적용된다."
                ),
                required=False,
            ),
            NodeConfigField(
                name="minScore",
                type="number",
                default=0.0,
                description=(
                    "Karpathy v2 P3 — 임계 score (cosine 유사도). 이 값 미만 결과는 제거된다."
                ),
                required=False,
            ),
            NodeConfigField(
                name="expandBacklinks",
                type="boolean",
                default=False,
                description=(
                    "Karpathy v2 P3 — true 면 hit 페이지의 1-hop backlink 페이지를 "
                    "추가 반환 (item.isBacklinkExpansion=true 마킹)."
                ),
                required=False,
            ),
        ],
        useCases=[
            "사용자 질문에 대한 유사 FAQ/매뉴얼 조회 후 AI에 컨텍스트로 주입",
            "특정 카테고리(예: '인프라') 문서만 한정해 RAG 검색",
            "티켓 내용을 기반으로 과거 처리 사례 참고 자료 확보",
            "Karpathy v2 — Summary/Entity 만 검색하여 운영 답변 컨텍스트 최소화 (pageTypes)",
            "Karpathy v2 — hit 페이지의 backlink 1-hop 자동 동반 (expandBacklinks)",
            "Multi-service v3 — 단일 서비스 작업 컨텍스트에서 services=['codeeyes'] 로 노이즈 차단",
        ],
        connectsWellWith=["ai-custom", "markdown-viewer", "result"],
        requiresUpstream=True,
        producesArray=True,
    ),
    # ── action: instance-db ───────────────────────────────────────────────
    # Phase A: 카탈로그 메타만 노출. 실제 핸들러는 Phase B에서 등록.
    NodeCatalogEntry(
        defType="instance-db-insert",
        label="인스턴스DB 적재",
        category="action",
        purpose=(
            "창고 entry 또는 임의 dict를 지정 인스턴스DB의 record(JSON 파일)로 추가한다. "
            "자유 JSON — 스키마 검증 없음. 중복 차단은 노드/사용자 책임. "
            "인스턴스DB 자원은 인프라 노드이므로 'CLAUDE.md 도메인 특화 노드 금지' "
            "원칙과 무관하게 신설된다."
        ),
        inputs=[
            NodeIOField(
                name="<임의>",
                type="any",
                required=False,
                description=(
                    "config.sourceMode 에 따라 해석된다. "
                    "'warehouse'면 직전 단계의 창고 entry, 'input'이면 dataTemplate 매핑 결과, "
                    "'auto'면 입력 dict 자체를 record 본체로 사용."
                ),
            ),
        ],
        outputs=[
            NodeIOField(
                name="recordId",
                type="string",
                required=True,
                description="삽입된 record의 id (rec-{8hex}).",
            ),
            NodeIOField(
                name="instanceDbId",
                type="string",
                required=True,
                description="대상 InstanceDB id.",
            ),
        ],
        config=[
            NodeConfigField(
                name="instanceDbId",
                type="string",
                default=None,
                description="대상 InstanceDB id (idb-...). POST /api/v1/instance-dbs 로 먼저 등록.",
                required=True,
            ),
            NodeConfigField(
                name="sourceMode",
                type="string",
                default="auto",
                description=(
                    "'warehouse' (직전 창고 entry 사용) | 'input' (dataTemplate 매핑) | "
                    "'auto' (입력 dict 자체)"
                ),
                required=False,
            ),
            NodeConfigField(
                name="dataTemplate",
                type="object",
                default=None,
                description=(
                    "input 모드에서 record 본체로 매핑할 템플릿. {{변수}} 치환 후 "
                    "record.data 가 된다."
                ),
                required=False,
            ),
        ],
        useCases=[
            "답변한 board_id 누적 (응답 완료된 티켓을 record로 마킹)",
            "처리 결과를 동질 데이터셋으로 누적해 후속 분석 자료화",
            "AI 분류 결과를 자유 JSON 형태로 보관",
        ],
        connectsWellWith=["result", "ai-custom", "api-call"],
        requiresUpstream=True,
        producesArray=False,
    ),
    NodeCatalogEntry(
        defType="instance-db-lookup",
        label="인스턴스DB 조회",
        category="action",
        purpose=(
            "지정 인스턴스DB에서 filterTemplate 동등 비교로 record 다건 조회하여 "
            "다운스트림에 출력한다. filterTemplate 가 비어있으면 최근 record 를 "
            "limit 만큼 반환. 인스턴스DB 자원은 인프라 노드이므로 'CLAUDE.md 도메인 "
            "특화 노드 금지' 원칙과 무관하게 신설된다."
        ),
        inputs=[
            NodeIOField(
                name="<임의>",
                type="any",
                required=False,
                description="filterTemplate 의 {{변수}} 치환에 사용되는 업스트림 벨트 데이터.",
            ),
        ],
        outputs=[
            NodeIOField(
                name="found",
                type="boolean",
                required=True,
                description="매칭 record 가 1건이라도 있는지 여부 (count > 0)",
            ),
            NodeIOField(
                name="count",
                type="number",
                required=True,
                description="매칭 record 개수 (limit 이내)",
            ),
            NodeIOField(
                name="record",
                type="object",
                required=False,
                description="첫 매칭 record.data (없으면 null)",
            ),
            NodeIOField(
                name="records",
                type="array",
                required=False,
                description="매칭 record.data 배열 (createdAt 내림차순, limit 적용)",
            ),
        ],
        config=[
            NodeConfigField(
                name="instanceDbId",
                type="string",
                default=None,
                description="조회 대상 InstanceDB id (idb-...)",
                required=True,
            ),
            NodeConfigField(
                name="filterTemplate",
                type="object",
                default=None,
                description=(
                    "record.data 와의 dot-path 동등 비교 객체. 각 값은 {{변수}} 치환 후 "
                    "AND 매칭. 비어있거나 누락이면 limit 만 적용 (모두 매칭)."
                ),
                required=False,
            ),
            NodeConfigField(
                name="limit",
                type="number",
                default=10,
                description="최대 반환 개수",
                required=False,
            ),
        ],
        useCases=[
            "이전 처리 record 재가공 (특정 boardId/카테고리 등 filter 매칭)",
            "분류기에서 사용할 lookup — 이미 처리된 항목 식별",
            "최근 record N건을 받아 통계·재처리 자료 확보",
        ],
        connectsWellWith=["sorter", "ai-custom"],
        requiresUpstream=True,
        producesArray=False,
    ),
    # ── output ────────────────────────────────────────────────────────────
    NodeCatalogEntry(
        defType="result",
        label="결과",
        category="output",
        purpose=(
            "실행 결과를 창고(WarehouseEntry)에 인스턴스 단위로 저장한다. "
            "다른 실행에서 mapper로 참조하거나, 사용자 검토 후 지식베이스로 프로모션할 수 있다."
        ),
        inputs=[
            NodeIOField(
                name="<임의>",
                type="any",
                required=True,
                description=(
                    "창고에 저장할 데이터. dict가 아니면 {value: <원본>}로 감싸진다."
                ),
            ),
        ],
        outputs=[
            NodeIOField(
                name="<입력과_동일>",
                type="any",
                required=False,
                description="pass-through. 리프 노드가 아닐 경우 다음 노드로 그대로 전달된다.",
            ),
        ],
        config=[
            NodeConfigField(
                name="dedupKeyTemplate",
                type="string",
                default=None,
                description=(
                    "중복 감지용 키 템플릿 (선택). {{변수}} 치환 후 해시되어 WarehouseEntry.dedup_key에 저장. "
                    "다른 실행의 warehouse-query 노드가 이 키로 존재 여부를 조회할 수 있다."
                ),
                required=False,
            ),
        ],
        useCases=[
            "실행 최종 산출물을 영속 저장하여 나중에 조회/프로모션",
            "단계별 중간 산출물을 창고에 축적하여 후속 매퍼가 조인",
            "dedup_key로 '이미 처리된 이슈' 감지",
        ],
        connectsWellWith=["markdown-viewer"],
        requiresUpstream=True,
        producesArray=False,
    ),
    NodeCatalogEntry(
        defType="markdown-viewer",
        label="마크다운 뷰어",
        category="output",
        purpose=(
            "입력의 특정 필드 또는 전체를 마크다운으로 UI에 렌더한다. "
            "내부 동작은 result와 동일하게 창고에 저장하며 UI 표시를 겸한다."
        ),
        inputs=[
            NodeIOField(
                name="<displayKey로_지정한_필드_또는_임의>",
                type="any",
                required=True,
                description=(
                    "config.displayKey가 가리키는 필드를 UI에 마크다운으로 렌더한다. "
                    "미지정 시 입력 전체를 JSON으로 표시."
                ),
            ),
        ],
        outputs=[
            NodeIOField(
                name="<입력과_동일>",
                type="any",
                required=False,
                description="pass-through. 내부적으로 result와 동일하게 창고 저장도 수행한다.",
            ),
        ],
        config=[
            NodeConfigField(
                name="displayKey",
                type="string",
                default=None,
                description="UI에 마크다운으로 렌더할 입력 필드 경로 (dot-path)",
                required=False,
            ),
            NodeConfigField(
                name="dedupKeyTemplate",
                type="string",
                default=None,
                description="result 노드와 동일한 중복 키 설정 (선택)",
                required=False,
            ),
        ],
        useCases=[
            "AI가 생성한 답변 본문(response 필드)을 사용자에게 즉시 표시",
            "api-api-router의 응답 데이터를 사람이 읽을 수 있는 문서로 요약 표시",
            "인스턴스 상세 페이지에서 최종 산출물을 마크다운으로 조회",
        ],
        connectsWellWith=[],
        requiresUpstream=True,
        producesArray=False,
    ),
]


# ── 조회 API ───────────────────────────────────────────────────────────────


def get_catalog() -> List[NodeCatalogEntry]:
    """전체 카탈로그 반환."""
    return CATALOG


def get_entry(def_type: str) -> Optional[NodeCatalogEntry]:
    """defType으로 단일 엔트리 조회. 없으면 None."""
    return next((e for e in CATALOG if e.defType == def_type), None)


__all__ = [
    "NodeIOField",
    "NodeConfigField",
    "NodeCatalogEntry",
    "CATALOG",
    "get_catalog",
    "get_entry",
]
