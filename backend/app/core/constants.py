"""
공유 상수 정의

워크플로우 노드 타입, 벨트 데이터 키, 필드 매핑 접두사 등
코드베이스 전반에서 사용되는 상수를 한 곳에 정의합니다.
"""

from enum import Enum


class NodeDefType(str, Enum):
    """워크플로우 노드 정의 타입.

    ── 분류 ──
    [CATALOG]    redesign-plan.md 섹션 4의 범용 노드 11종. app/nodes/catalog.py에 등재.
    [ENGINE]     workflow_engine.py가 직접 참조하므로 유지 필수.
    [LEGACY]     과거 도메인 이전부터 남은 핸들러. Phase 2c 이후 카탈로그 편입 또는 삭제 재검토.
    """

    # ── 트리거 ────────────────────────────────────────────────────────────
    FORM_START = "form-start"        # [CATALOG] starter
    API_START = "api-start"          # [CATALOG] starter
    # TODO(Phase 추가 시 재검토): 아래 레거시 트리거는 TRIGGER_TYPES 집합에서 참조되므로
    # 실행 엔진의 start-node 탐지가 레거시 워크플로우에도 호환되도록 유지한다.
    MANUAL = "manual"                # [LEGACY] trigger pass-through
    SCHEDULE = "schedule"            # [LEGACY] alias of MANUAL
    SCHEDULE_TRIGGER = "schedule-trigger"  # [LEGACY] scheduler cron 진입
    WEBHOOK = "webhook"              # [LEGACY] alias of MANUAL
    FORM = "form"                    # [LEGACY] alias of FORM_START

    # ── AI ────────────────────────────────────────────────────────────────
    AI_CUSTOM = "ai-custom"          # [CATALOG] ai
    AI_API_ROUTER = "ai-api-router"  # [CATALOG] ai
    # TODO(Phase 추가 시 재검토): AI_NODE_TYPES 집합에서 참조. 실행 시 AiCustomHandler로 위임.
    AI_CHAT = "ai-chat"              # [LEGACY]
    AI_CLASSIFY = "ai-classify"      # [LEGACY]
    AI_EXTRACT = "ai-extract"        # [LEGACY]
    AI_SUMMARIZE = "ai-summarize"    # [LEGACY]

    # ── 로직 ──────────────────────────────────────────────────────────────
    SORTER = "sorter"                # [CATALOG][ENGINE] logic, 핸들 라우팅
    UNPACKER = "unpacker"            # [CATALOG][ENGINE] logic, 배열 언팩 반복
    MAPPER = "mapper"                # [CATALOG] logic
    # TODO(Phase 추가 시 재검토): 아래는 레거시 로직 노드. workflow_engine은 CONDITION만 참조.
    CONDITION = "condition"          # [ENGINE][LEGACY] 조건 분기 (TODO 분기 구현 대기)
    SWITCH = "switch"                # [LEGACY]
    LOOP = "loop"                    # [LEGACY] 미구현 (TODO)
    MERGE = "merge"                  # [LEGACY]

    # ── 변환 ──────────────────────────────────────────────────────────────
    # TODO(Phase 추가 시 재검토): 범용 11종에 미포함. 핸들러는 존재.
    SET_VARIABLE = "set-variable"    # [LEGACY]
    CODE = "code"                    # [LEGACY] RestrictedPython 샌드박스
    JSON_PARSE = "json-parse"        # [LEGACY]

    # ── 액션 ──────────────────────────────────────────────────────────────
    API_CALL = "api-call"            # [CATALOG] action
    KNOWLEDGE = "knowledge"          # [CATALOG] action, RAG
    INSTANCE_DB_INSERT = "instance-db-insert"  # [CATALOG] action — Phase A 등재, 핸들러는 Phase B
    INSTANCE_DB_LOOKUP = "instance-db-lookup"  # [CATALOG] action — Phase A 등재, 핸들러는 Phase B
    # TODO(Phase 추가 시 재검토): 레거시 액션. API_CALL로 대부분 대체 가능.
    HTTP_REQUEST = "http-request"    # [LEGACY]
    SEND_EMAIL = "send-email"        # [LEGACY] 미구현

    # ── 출력 ──────────────────────────────────────────────────────────────
    RESULT = "result"                # [CATALOG][ENGINE] output, 창고 저장
    MARKDOWN_VIEWER = "markdown-viewer"  # [CATALOG][ENGINE] output, UI 렌더
    # TODO(Phase 추가 시 재검토): 레거시 출력 노드.
    OUTPUT_LOG = "output-log"        # [LEGACY]
    OUTPUT_WEBHOOK = "output-webhook"  # [LEGACY]


# 트리거(시작) 노드 타입 집합
TRIGGER_TYPES = {
    NodeDefType.MANUAL,
    NodeDefType.SCHEDULE,
    NodeDefType.SCHEDULE_TRIGGER,
    NodeDefType.WEBHOOK,
    NodeDefType.FORM,
    NodeDefType.FORM_START,
    NodeDefType.API_START,
}

# 트리거 타입 문자열 집합 (DB 값과 비교용)
TRIGGER_TYPE_VALUES = {t.value for t in TRIGGER_TYPES}

# AI 처리 노드 타입 집합
AI_NODE_TYPES = {
    NodeDefType.AI_CHAT,
    NodeDefType.AI_CLASSIFY,
    NodeDefType.AI_EXTRACT,
    NodeDefType.AI_SUMMARIZE,
    NodeDefType.AI_CUSTOM,
    NodeDefType.AI_API_ROUTER,
}

# AI 타입 문자열 집합
AI_NODE_TYPE_VALUES = {t.value for t in AI_NODE_TYPES}


# 범용 노드 카탈로그 13종 (redesign-plan.md 섹션 4 + 인스턴스DB Phase A 확장)
# Phase 2a에서 확정된 Single Source of Truth — 실제 엔트리는 app/nodes/catalog.py 참조.
# 인스턴스DB 도입(Phase A)으로 11→13종으로 확장. 도메인 특화가 아닌 인프라 자원 노드.
CATALOG_NODE_TYPES = {
    NodeDefType.FORM_START,
    NodeDefType.API_START,
    NodeDefType.AI_CUSTOM,
    NodeDefType.AI_API_ROUTER,
    NodeDefType.SORTER,
    NodeDefType.UNPACKER,
    NodeDefType.MAPPER,
    NodeDefType.API_CALL,
    NodeDefType.KNOWLEDGE,
    NodeDefType.RESULT,
    NodeDefType.MARKDOWN_VIEWER,
    NodeDefType.INSTANCE_DB_INSERT,
    NodeDefType.INSTANCE_DB_LOOKUP,
}

# 카탈로그 타입 문자열 집합
CATALOG_NODE_TYPE_VALUES = {t.value for t in CATALOG_NODE_TYPES}


class BeltKey:
    """벨트 데이터 특수 키"""

    PASSTHROUGH = "_passthrough"
    SORTER_HANDLE = "__sorterHandle"
    UNPACK_ITEMS = "__unpackItems"
    KNOWLEDGE_ERROR = "_knowledgeError"
    OUTPUT = "_output"


# 필드 매핑 접두사
FIELD_MAPPING_PREFIX = "$."

# Knowledge 검색 기본값
KNOWLEDGE_MIN_RESULTS = 4
KNOWLEDGE_MAX_RESULTS = 7
KNOWLEDGE_DEFAULT_TOP_K = 10
