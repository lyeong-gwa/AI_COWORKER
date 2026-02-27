"""
공유 상수 정의

워크플로우 노드 타입, 벨트 데이터 키, 필드 매핑 접두사 등
코드베이스 전반에서 사용되는 상수를 한 곳에 정의합니다.
"""

from enum import Enum


class NodeDefType(str, Enum):
    """워크플로우 노드 정의 타입"""

    # 트리거
    MANUAL = "manual"
    SCHEDULE = "schedule"
    WEBHOOK = "webhook"
    FORM = "form"
    FORM_START = "form-start"
    API_START = "api-start"

    # AI
    AI_CUSTOM = "ai-custom"
    AI_CHAT = "ai-chat"
    AI_CLASSIFY = "ai-classify"
    AI_EXTRACT = "ai-extract"
    AI_SUMMARIZE = "ai-summarize"

    # 로직
    CONDITION = "condition"
    SWITCH = "switch"
    LOOP = "loop"
    MERGE = "merge"
    SORTER = "sorter"
    UNPACKER = "unpacker"

    # 변환
    SET_VARIABLE = "set-variable"
    CODE = "code"
    JSON_PARSE = "json-parse"

    # 액션
    HTTP_REQUEST = "http-request"
    SEND_EMAIL = "send-email"
    API_CALL = "api-call"
    KNOWLEDGE = "knowledge"

    # 출력
    RESULT = "result"
    MARKDOWN_VIEWER = "markdown-viewer"
    OUTPUT_LOG = "output-log"
    OUTPUT_WEBHOOK = "output-webhook"


# 트리거(시작) 노드 타입 집합
TRIGGER_TYPES = {
    NodeDefType.MANUAL,
    NodeDefType.SCHEDULE,
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
}

# AI 타입 문자열 집합
AI_NODE_TYPE_VALUES = {t.value for t in AI_NODE_TYPES}


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
