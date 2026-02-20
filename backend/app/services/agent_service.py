"""
Agent Service

AI 어시스턴트의 핵심 로직
- 사용자 의도 파악
- 컨텍스트 기반 작업 수행
- 응답 생성
"""

import copy
import json
import uuid
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.task import Task, TaskStatus, TaskPriority
from ..models.tool import ToolDefinition
from ..models.node import AINode
from ..models.workflow import Workflow
from .knowledge_file_service import read_md_file
from ..schemas.chat import (
    ChatContextBase,
    DetectedIntent,
    AgentAction,
    ChatMessageResponse,
)
from .llm.registry import get_llm_handler
from .llm.base import LLMRequest, LLMMessage


# ─────────────────────────────────────────────────────────────────────────────
# 세션 저장소 (인메모리 - 추후 Redis/DB로 전환 가능)
# ─────────────────────────────────────────────────────────────────────────────

_sessions: Dict[str, List[Dict[str, Any]]] = {}


def get_or_create_session(session_id: Optional[str] = None) -> str:
    """세션 가져오기 또는 생성"""
    if session_id and session_id in _sessions:
        return session_id

    new_session_id = session_id or f"session-{uuid.uuid4().hex[:12]}"
    _sessions[new_session_id] = []
    return new_session_id


def add_message_to_session(session_id: str, role: str, content: str, **kwargs):
    """세션에 메시지 추가"""
    if session_id not in _sessions:
        _sessions[session_id] = []

    _sessions[session_id].append({
        "id": f"msg-{uuid.uuid4().hex[:8]}",
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        **kwargs
    })


def get_session_messages(session_id: str) -> List[Dict[str, Any]]:
    """세션 메시지 가져오기"""
    return _sessions.get(session_id, [])


# ─────────────────────────────────────────────────────────────────────────────
# 컨텍스트 로딩
# ─────────────────────────────────────────────────────────────────────────────

async def load_context_data(
    db: AsyncSession,
    context: ChatContextBase
) -> Optional[Dict[str, Any]]:
    """컨텍스트 타입에 따라 데이터 로드"""
    if context.type == 'none' or not context.id:
        return None

    try:
        if context.type == 'task':
            result = await db.execute(select(Task).where(Task.id == context.id))
            item = result.scalar_one_or_none()
            if item:
                # 최근 댓글 5개 (전체가 아닌 요약)
                recent_comments = []
                if item.comments:
                    for c in item.comments[-5:]:
                        recent_comments.append({
                            "author": c.get("authorName", ""),
                            "content": c.get("content", "")[:300],
                            "createdAt": c.get("createdAt", ""),
                        })
                # TODO 목록
                todos = []
                if item.todos:
                    for t in item.todos:
                        todos.append({
                            "text": t.get("text", ""),
                            "completed": t.get("completed", False),
                        })
                # 참조 지식 요약
                refs = []
                if item.references:
                    for r in item.references:
                        refs.append({
                            "docId": r.get("docId", ""),
                            "title": r.get("title", ""),
                            "category": r.get("category", ""),
                        })
                return {
                    "type": "task",
                    "id": item.id,
                    "title": item.title,
                    "description": item.description,
                    "status": item.status.value,
                    "priority": item.priority.value,
                    "assigneeName": item.assignee_name,
                    "dueDate": item.due_date.isoformat() if item.due_date else None,
                    "tags": item.tags,
                    "todos": todos,
                    "recentComments": recent_comments,
                    "references": refs,
                }

        elif context.type == 'tool':
            result = await db.execute(select(ToolDefinition).where(ToolDefinition.id == context.id))
            item = result.scalar_one_or_none()
            if item:
                return {
                    "type": "tool",
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "toolType": item.type,
                }

        elif context.type == 'node':
            result = await db.execute(select(AINode).where(AINode.id == context.id))
            item = result.scalar_one_or_none()
            if item:
                return {
                    "type": "node",
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "systemPrompt": item.system_prompt[:200] + "..." if len(item.system_prompt) > 200 else item.system_prompt,
                }

        elif context.type == 'workflow':
            result = await db.execute(select(Workflow).where(Workflow.id == context.id))
            item = result.scalar_one_or_none()
            if item:
                return {
                    "type": "workflow",
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "nodeCount": len(item.nodes) if item.nodes else 0,
                }

        elif context.type == 'document':
            item = read_md_file(context.id)
            if item:
                return {
                    "type": "document",
                    "id": item.id,
                    "title": item.title,
                    "content": item.content[:500] + "..." if len(item.content) > 500 else item.content,
                    "tags": item.tags,
                }

    except Exception as e:
        print(f"컨텍스트 로딩 오류: {e}")
        return None

    return None


# ─────────────────────────────────────────────────────────────────────────────
# 지식 베이스 검색 (RAG)
# ─────────────────────────────────────────────────────────────────────────────

async def search_knowledge_base(
    query: str,
    category: Optional[str] = None,
    top_k: int = 3,
    min_score: float = 0.3,
) -> List[Dict[str, Any]]:
    """벡터 DB에서 관련 지식 검색 (RAG)"""
    try:
        from .embedding.vector_db import get_vector_db
        vector_db = get_vector_db()

        where_filter = None
        if category:
            where_filter = {"category": category}

        results = await vector_db.search_async(
            query=query,
            top_k=top_k,
            where=where_filter,
            min_score=min_score,
        )

        # Deduplicate by title (keep highest score per title)
        seen_titles = {}
        for r in results:
            title = r.metadata.get("title", "")
            if not title:
                continue
            if title not in seen_titles or r.score > seen_titles[title]["score"]:
                seen_titles[title] = {
                    "id": r.id,
                    "content": r.content,
                    "score": r.score,
                    "metadata": r.metadata,
                }

        return list(seen_titles.values())
    except Exception as e:
        logger.warning(f"지식베이스 검색 오류: {type(e).__name__}: {e}")
        return []


def format_knowledge_context(results: List[Dict[str, Any]]) -> str:
    """검색 결과를 LLM 프롬프트용 텍스트로 포맷"""
    if not results:
        return ""

    lines = ["[관련 지식]"]
    for i, r in enumerate(results, 1):
        title = r.get("metadata", {}).get("title", "제목 없음")
        score = r.get("score", 0)
        content = r.get("content", "")
        lines.append(f"\n{i}. (유사도: {score:.2f}) {title}")
        lines.append(content)

    return "\n".join(lines)


async def generate_comment(
    task_title: str,
    task_description: str,
    knowledge_context: str = "",
) -> str:
    """지식 컨텍스트 기반으로 태스크 댓글(답변 초안) 생성"""
    try:
        handler = get_llm_handler()

        system_prompt = """당신은 업무 민원에 대한 답변을 작성하는 전문가입니다.
주어진 태스크 내용과 관련 지식을 참고하여 정중하고 전문적인 답변 초안을 작성하세요.

규칙:
- 관련 지식이 있으면 반드시 근거로 활용
- 구체적이고 실행 가능한 안내 제공
- 정중하지만 간결한 톤
- 확인된 사실만 언급, 추측은 "확인이 필요합니다"로 표현"""

        user_prompt = f"태스크 제목: {task_title}\n태스크 설명: {task_description}"
        if knowledge_context:
            user_prompt += f"\n\n{knowledge_context}"
        user_prompt += "\n\n위 내용을 바탕으로 답변 초안을 작성해주세요."

        response = await handler.simple_chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.5,
            max_tokens=800,
            call_type="comment_generation",
        )
        return response.content

    except Exception as e:
        print(f"댓글 생성 오류: {e}")
        return f"[자동 생성 답변] '{task_title}'에 대한 검토가 필요합니다. 관련 지식 베이스를 참고하여 답변을 작성해주세요."


async def generate_structured_task(
    user_message: str,
    knowledge_context: str = "",
) -> dict:
    """사용자 메시지와 지식 컨텍스트를 기반으로 구조화된 태스크 내용 생성"""
    try:
        print(f"[generate_structured_task] Starting LLM call for: {user_message[:100]}")
        handler = get_llm_handler()

        system_prompt = """당신은 업무 태스크를 체계적으로 정리하는 전문가입니다.
사용자의 요청 메시지를 분석하여 주간보고 스타일의 전문적인 업무 문서로 변환합니다.

반드시 아래 JSON 형식으로만 응답하세요:
{
  "title": "간결한 태스크 제목 (50자 이내)",
  "description": "**개요**\\n1-2문장으로 업무 배경 및 목적 요약\\n\\n**상세 내용**\\n- 구체적 작업 항목 1\\n- 구체적 작업 항목 2\\n- 구체적 작업 항목 3\\n\\n**담당/일정**\\n| 항목 | 내용 |\\n|------|------|\\n| 담당자 | 홍길동 |\\n| 기한 | 2026-02-20 |\\n| 관련 부서 | 인프라팀 |\\n\\n**완료 조건**\\n- 완료로 판단할 수 있는 구체적 기준 1\\n- 완료로 판단할 수 있는 구체적 기준 2",
  "todos": ["구체적 액션아이템1", "구체적 액션아이템2", "구체적 액션아이템3"],
  "priority": "medium",
  "tags": ["태그1", "태그2"],
  "assignee": "담당자명 (없으면 빈문자열)",
  "dueDate": "YYYY-MM-DD (없으면 빈문자열)"
}

규칙:
- description은 주간보고 형식의 마크다운으로 작성
  * **개요**: 1-2문장 업무 배경 요약
  * **상세 내용**: bullet points로 구체적 작업 항목 나열
  * **담당/일정**: 담당자, 기한, 관련 부서를 표(table) 형식으로 정리
  * **완료 조건**: 어떤 상태가 되어야 완료인지 명시
- todos는 구체적이고 실행 가능한 액션아이템 3~5개
- priority: 긴급도에 따라 low/medium/high/urgent
- tags: 업무 분류에 도움되는 키워드 2~4개
- assignee: 사용자 메시지에서 담당자 추출 (없으면 빈문자열)
- dueDate: 사용자 메시지에서 기한 추출하여 YYYY-MM-DD 형식으로 (없으면 빈문자열)
- 지식 컨텍스트가 제공되면 상세 내용에 반영"""

        user_prompt = f"사용자 요청:\n{user_message}"
        if knowledge_context:
            user_prompt += f"\n\n{knowledge_context}"

        response = await handler.simple_chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=1000,
            call_type="task_structuring",
        )

        print(f"[generate_structured_task] LLM response: {response.content[:200]}")

        import json as _json
        content = response.content.strip()

        # JSON 블록 추출 (마크다운 코드 블록)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        # 추가 JSON 추출: 첫 { 부터 마지막 } 까지
        if not content.startswith("{"):
            start_idx = content.find("{")
            end_idx = content.rfind("}")
            if start_idx != -1 and end_idx != -1:
                content = content[start_idx:end_idx + 1]

        # JSON 파싱 시도
        try:
            result = _json.loads(content)
            print(f"[generate_structured_task] Parsed JSON keys: {list(result.keys())}")
            return result
        except _json.JSONDecodeError as json_err:
            print(f"[generate_structured_task] JSON parse failed: {json_err}")
            print(f"[generate_structured_task] Failed content: {content[:500]}")
            raise

    except Exception as e:
        print(f"[generate_structured_task] ERROR: {type(e).__name__}: {e}")
        logger.warning(f"구조화된 태스크 생성 실패: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 의도 감지
# ─────────────────────────────────────────────────────────────────────────────

INTENT_DETECTION_PROMPT = """당신은 사용자의 의도를 파악하는 AI입니다.
사용자 메시지와 선택된 컨텍스트를 분석하여 의도를 JSON으로 반환하세요.

가능한 action 타입:
- explain: 설명 요청 ("이게 뭐야?", "설명해줘")
- view: 조회 요청 ("보여줘", "목록")
- create: 생성 요청 ("만들어줘", "추가해줘", "등록해줘", "태스크로 만들어줘")
- update: 수정 요청 ("변경해줘", "수정해줘", "상태를 ~로")
- delete: 삭제 요청 ("삭제해줘", "제거해줘")
- execute: 실행 요청 ("실행해줘", "테스트해줘")
- search: 검색/문의/질문 ("찾아줘", "검색해줘", "알려줘", "~은 어떻게 하나요?", "~이 뭐야?", 업무/서비스 관련 질문)
- fill_form: 양식 채우기 요청 ("~양식에 맞춰서 작성해줘", "~표로 정리해줘", "~양식으로 만들어줘", "~표 채워줘")
- chat: 일반 대화 (위에 해당하지 않음)

가능한 target 타입:
- task: 태스크
- tool: 도구
- node: 노드
- workflow: 워크플로우
- document: 문서

현재 등록된 카테고리:
- 소스코드검증: 코드아이즈 서비스 관련 지식 (스펙, 인프라, 수용, 권한, 플러그인 등)
- 양식: 엑셀 양식 템플릿 (서버현황표, 인프라요약표, 서비스정보표, 서버쌍구성표 등)
서비스명이 명시되지 않아도 문의 내용으로 카테고리 추론

parameters 가이드:
- create + task인 경우: {"title": "제목", "description": "설명", "priority": "medium", "tags": ["태그"], "addComment": true/false}
- update + task인 경우:
  * 기본: {"status": "상태값", "priority": "우선순위", "title": "새 제목", "description": "새 설명"}
  * 담당자: {"assigneeName": "홍길동"}
  * 마감일: {"dueDate": "2026-03-15"}
  * 태그 교체: {"tags": ["태그1", "태그2"]}
  * 태그 추가: {"addTags": ["긴급"]}
  * 태그 제거: {"removeTags": ["완료"]}
  * TODO 전체완료/해제: {"todoAction": "complete_all"} / {"todoAction": "uncomplete_all"}
  * TODO 개별 완료/토글: {"todoAction": "complete", "todoIndices": [0,1,2]} / {"todoAction": "toggle", "todoIndices": [0]}
  * TODO 추가: {"todoAction": "add", "todoText": "새 할일 항목"}
  * TODO 삭제: {"todoAction": "remove", "todoIndices": [1]}
  * TODO 수정: {"todoAction": "edit", "todoIndex": 1, "todoText": "수정된 텍스트"}
  * TODO 개별해제: {"todoAction": "uncomplete", "todoIndices": [0,1]}
  * 댓글(RAG): {"addComment": true}
  * 댓글 수동추가: {"commentContent": "직접 작성한 댓글 내용"}
  * 댓글 삭제: {"commentAction": "delete", "commentIndex": 1}
  * 활동이력 추가: {"activityAction": "add", "activityDetail": "검토 시작"}
  * 활동이력 삭제: {"activityAction": "delete", "activityIndex": 0}
  * 참조 추가(RAG): {"referenceAction": "add", "referenceQuery": "관련 문서 검색어"}
  * 참조 제거: {"referenceAction": "remove", "referenceIndex": 0}
- delete + task인 경우: {} (확인 절차 진행)
- view + task (목록 조회, target_id 없음): {"statusFilter": "todo", "priorityFilter": "high", "listQuery": "검색어"}
- search + document인 경우: {"query": "검색 키워드", "searchCategory": "소스코드검증"}
- fill_form인 경우: {"formQuery": "양식명", "dataQuery": "데이터 검색어", "dataCategory": "데이터카테고리"}
  - formQuery: 양식 카테고리에서 검색할 양식명 (예: "서버현황표", "인프라요약표")
  - dataQuery: 데이터 카테고리에서 검색할 키워드 (예: "소스코드검증 인프라 스펙")
  - dataCategory: 데이터를 검색할 카테고리 (예: "소스코드검증")
- addComment: 답변/코멘트도 함께 작성해달라는 요청 시 true

검색 예시:
- "ITO 서비스 수용신청은 어떻게 하나요?" → action: "search", target: "document", parameters: {"query": "ITO 서비스 수용신청 절차", "searchCategory": "소스코드검증"}
- "권한 추가 요청하려면요?" → action: "search", target: "document", parameters: {"query": "권한 추가 요청", "searchCategory": "소스코드검증"}
- "플러그인 에러가 났는데요" → action: "search", target: "document", parameters: {"query": "플러그인 에러", "searchCategory": "소스코드검증"}

TODO 예시:
- "할일 다 체크해줘" → action: "update", target: "task", parameters: {"todoAction": "complete_all"}
- "3번째 할일 체크해줘" → action: "update", target: "task", parameters: {"todoAction": "complete", "todoIndices": [2]}
- "TODO 전부 완료 처리해줘" → action: "update", target: "task", parameters: {"todoAction": "complete_all"}
- "1번, 2번, 3번 할일 체크" → action: "update", target: "task", parameters: {"todoAction": "complete", "todoIndices": [0, 1, 2]}
- "할일 체크 다 해제해줘" → action: "update", target: "task", parameters: {"todoAction": "uncomplete_all"}

담당자/마감일/태그 예시:
- "담당자를 홍길동으로 변경해줘" → action: "update", target: "task", parameters: {"assigneeName": "홍길동"}
- "마감일을 2026-03-15로 설정해줘" → action: "update", target: "task", parameters: {"dueDate": "2026-03-15"}
- "태그에 '긴급' 추가해줘" → action: "update", target: "task", parameters: {"addTags": ["긴급"]}
- "태그에서 '완료' 제거해줘" → action: "update", target: "task", parameters: {"removeTags": ["완료"]}
- "태그를 ['백엔드', 'API']로 변경해줘" → action: "update", target: "task", parameters: {"tags": ["백엔드", "API"]}

TODO 개별 조작 예시:
- "할일에 '코드 리뷰' 추가해줘" → action: "update", target: "task", parameters: {"todoAction": "add", "todoText": "코드 리뷰"}
- "2번째 할일 삭제해줘" → action: "update", target: "task", parameters: {"todoAction": "remove", "todoIndices": [1]}
- "3번째 할일을 '테스트 완료'로 수정해줘" → action: "update", target: "task", parameters: {"todoAction": "edit", "todoIndex": 2, "todoText": "테스트 완료"}
- "1번, 2번 할일 체크 해제해줘" → action: "update", target: "task", parameters: {"todoAction": "uncomplete", "todoIndices": [0, 1]}

댓글/활동이력/참조 예시:
- "댓글에 '확인 완료' 추가해줘" → action: "update", target: "task", parameters: {"commentContent": "확인 완료"}
- "2번째 댓글 삭제해줘" → action: "update", target: "task", parameters: {"commentAction": "delete", "commentIndex": 1}
- "활동이력에 '검토 시작' 추가해줘" → action: "update", target: "task", parameters: {"activityAction": "add", "activityDetail": "검토 시작"}
- "1번째 활동이력 삭제해줘" → action: "update", target: "task", parameters: {"activityAction": "delete", "activityIndex": 0}
- "관련 문서 참조 추가해줘" → action: "update", target: "task", parameters: {"referenceAction": "add", "referenceQuery": "관련 문서"}
- "1번째 참조 제거해줘" → action: "update", target: "task", parameters: {"referenceAction": "remove", "referenceIndex": 0}

태스크 삭제/목록 예시:
- "이 태스크 삭제해줘" → action: "delete", target: "task", parameters: {}
- "태스크 목록 보여줘" → action: "view", target: "task", parameters: {}
- "진행중인 태스크 목록" → action: "view", target: "task", parameters: {"statusFilter": "in-progress"}
- "긴급 태스크 목록" → action: "view", target: "task", parameters: {"priorityFilter": "urgent"}

양식 채우기 예시:
- "소스코드검증 스펙을 서버현황표 양식에 맞춰서 작성해줘" → action: "fill_form", target: "document", parameters: {"formQuery": "서버현황표", "dataQuery": "소스코드검증 서비스 인프라 스펙", "dataCategory": "소스코드검증"}
- "인프라 정보를 서비스정보표로 정리해줘" → action: "fill_form", target: "document", parameters: {"formQuery": "서비스정보표", "dataQuery": "소스코드검증 인프라 스펙", "dataCategory": "소스코드검증"}
- "서버 쌍 구성을 양식에 맞춰 알려줘" → action: "fill_form", target: "document", parameters: {"formQuery": "서버쌍구성표", "dataQuery": "소스코드검증 서버 쌍 구성", "dataCategory": "소스코드검증"}
- "코드아이즈 인프라요약표 채워줘" → action: "fill_form", target: "document", parameters: {"formQuery": "인프라요약표", "dataQuery": "소스코드검증 인프라", "dataCategory": "소스코드검증"}

복합 요청 인식:
- "등록하고 답변도 달아줘" → create + addComment: true
- "태스크로 만들고 코멘트도 작성해줘" → create + addComment: true
- 메일/민원 내용이 포함된 경우 → create + task + addComment: true (메일 내용을 description으로)
- 서비스명이 언급되면 searchCategory에 해당 서비스명 추출 (예: "코드아이즈" → searchCategory: "소스코드검증")

응답 형식 (JSON만):
{
  "action": "create",
  "target": "task",
  "parameters": {"title": "민원: 점검결과 이상", "description": "...", "priority": "high", "tags": ["민원", "소스코드검증"], "addComment": true, "searchCategory": "소스코드검증"},
  "confidence": 0.9
}
"""


async def detect_intent(
    message: str,
    context_data: Optional[Dict[str, Any]]
) -> DetectedIntent:
    """LLM을 사용하여 사용자 의도 감지"""
    try:
        handler = get_llm_handler()

        user_prompt = f"사용자 메시지: {message}"
        if context_data:
            user_prompt += f"\n\n선택된 컨텍스트:\n{json.dumps(context_data, ensure_ascii=False, indent=2)}"

        response = await handler.simple_chat(
            prompt=user_prompt,
            system_prompt=INTENT_DETECTION_PROMPT,
            temperature=0.1,
            max_tokens=500,
            call_type="intent_detection",
        )

        # JSON 파싱
        content = response.content.strip()
        # 코드 블록 제거
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        intent_data = json.loads(content)
        return DetectedIntent(**intent_data)

    except Exception as e:
        print(f"의도 감지 오류: {e}")
        # 기본값: 일반 대화
        return DetectedIntent(action="chat", confidence=0.5)


# ─────────────────────────────────────────────────────────────────────────────
# 감사 이력 자동화 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _append_activity_log(task, action: str, detail: str = ""):
    """태스크에 감사 이력 자동 추가 (JSON 컬럼 변경 감지용 deepcopy + flag_modified)"""
    from sqlalchemy.orm.attributes import flag_modified
    updated = copy.deepcopy(task.activity_log or [])
    updated.append({
        "id": f"log-{uuid.uuid4().hex[:8]}",
        "userId": "ai-assistant",
        "userName": "AI 어시스턴트",
        "action": action,
        "detail": detail,
        "timestamp": datetime.utcnow().isoformat(),
    })
    task.activity_log = updated
    flag_modified(task, "activity_log")


# 삭제 확인용 보류 작업 저장소 (세션별)
_pending_actions: Dict[str, Dict[str, Any]] = {}


# ─────────────────────────────────────────────────────────────────────────────
# 작업 실행
# ─────────────────────────────────────────────────────────────────────────────

async def execute_action(
    db: AsyncSession,
    intent: DetectedIntent,
    context: Optional[ChatContextBase],
    context_data: Optional[Dict[str, Any]],
    original_message: str = "",
    session_id: str = "",
) -> Optional[AgentAction]:
    """감지된 의도에 따라 작업 실행"""

    if intent.action == "chat":
        return None  # 일반 대화는 작업 없음

    # 삭제 확인 응답 처리 (2턴 대화)
    if session_id and session_id in _pending_actions:
        pending = _pending_actions[session_id]
        if pending.get("type") == "delete_task":
            affirmative = any(kw in original_message for kw in ["네", "응", "예", "맞아", "삭제해", "확인", "ㅇㅇ", "yes", "y"])
            if affirmative:
                del _pending_actions[session_id]
                try:
                    result = await db.execute(select(Task).where(Task.id == pending["target_id"]))
                    task = result.scalar_one_or_none()
                    if task:
                        task_title = task.title
                        await db.delete(task)
                        await db.commit()
                        return AgentAction(
                            type="delete",
                            target="task",
                            targetId=pending["target_id"],
                            success=True,
                            result={"deleted": True, "title": task_title}
                        )
                    else:
                        return AgentAction(
                            type="delete", target="task",
                            targetId=pending["target_id"],
                            success=False, error="태스크를 찾을 수 없습니다."
                        )
                except Exception as e:
                    return AgentAction(
                        type="delete", target="task",
                        targetId=pending["target_id"],
                        success=False, error=str(e)
                    )
            else:
                del _pending_actions[session_id]
                return AgentAction(
                    type="delete", target="task",
                    success=False, error="삭제가 취소되었습니다."
                )

    target = intent.target or (context.type if context and context.type != 'none' else None)
    target_id = context.id if context and context.type != 'none' else None

    if not target:
        return None

    try:
        # 설명 요청
        if intent.action == "explain":
            return AgentAction(
                type="explain",
                target=target,
                targetId=target_id,
                success=True,
                result=context_data
            )

        # 조회 요청
        elif intent.action == "view":
            return AgentAction(
                type="view",
                target=target,
                targetId=target_id,
                success=True,
                result=context_data
            )

        # 수정 요청
        elif intent.action == "update" and target == "task" and target_id:
            params = intent.parameters
            result = await db.execute(select(Task).where(Task.id == target_id))
            task = result.scalar_one_or_none()

            if task:
                # 상태 변경
                if "status" in params:
                    status_map = {
                        "backlog": TaskStatus.BACKLOG,
                        "todo": TaskStatus.TODO,
                        "in-progress": TaskStatus.IN_PROGRESS,
                        "진행 중": TaskStatus.IN_PROGRESS,
                        "진행중": TaskStatus.IN_PROGRESS,
                        "review": TaskStatus.REVIEW,
                        "검토": TaskStatus.REVIEW,
                        "done": TaskStatus.DONE,
                        "완료": TaskStatus.DONE,
                    }
                    new_status = params["status"]
                    if new_status in status_map:
                        task.status = status_map[new_status]
                        _append_activity_log(task, "상태 변경", f"AI가 상태를 '{new_status}'(으)로 변경")

                # 우선순위 변경
                if "priority" in params:
                    priority_map = {
                        "low": TaskPriority.LOW,
                        "medium": TaskPriority.MEDIUM,
                        "high": TaskPriority.HIGH,
                        "urgent": TaskPriority.URGENT,
                    }
                    new_priority = params["priority"]
                    if new_priority in priority_map:
                        task.priority = priority_map[new_priority]
                        _append_activity_log(task, "우선순위 변경", f"AI가 우선순위를 '{new_priority}'(으)로 변경")

                # 제목 변경
                if "title" in params:
                    task.title = params["title"]
                    _append_activity_log(task, "제목 변경", f"AI가 제목을 '{params['title']}'(으)로 변경")

                # 설명 변경
                if "description" in params:
                    task.description = params["description"]
                    _append_activity_log(task, "설명 변경", "AI가 설명을 변경")

                # TODO 액션
                if "todoAction" in params:
                    todo_action = params["todoAction"]
                    if task.todos:
                        updated_todos = copy.deepcopy(task.todos)  # deep copy to trigger SQLAlchemy change detection
                        if todo_action == "complete_all":
                            for t in updated_todos:
                                t["completed"] = True
                        elif todo_action == "uncomplete_all":
                            for t in updated_todos:
                                t["completed"] = False
                        elif todo_action == "add":
                            new_text = params.get("todoText", "")
                            if new_text:
                                updated_todos.append({
                                    "id": f"todo-{uuid.uuid4().hex[:8]}",
                                    "text": new_text,
                                    "completed": False,
                                })
                        elif todo_action == "remove":
                            indices = sorted(params.get("todoIndices", []), reverse=True)
                            for idx in indices:
                                if 0 <= idx < len(updated_todos):
                                    del updated_todos[idx]
                        elif todo_action == "edit":
                            idx = params.get("todoIndex")
                            new_text = params.get("todoText", "")
                            if idx is not None and 0 <= idx < len(updated_todos) and new_text:
                                updated_todos[idx]["text"] = new_text
                        elif todo_action == "uncomplete":
                            indices = params.get("todoIndices", [])
                            for idx in indices:
                                if 0 <= idx < len(updated_todos):
                                    updated_todos[idx]["completed"] = False
                        elif todo_action in ("complete", "toggle"):
                            indices = params.get("todoIndices", [])
                            for idx in indices:
                                if 0 <= idx < len(updated_todos):
                                    if todo_action == "complete":
                                        updated_todos[idx]["completed"] = True
                                    else:
                                        updated_todos[idx]["completed"] = not updated_todos[idx]["completed"]
                        task.todos = updated_todos
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(task, "todos")
                        logger.info(f"[TODO-UPDATE] action={todo_action}, todos_count={len(updated_todos)}, completed=[{', '.join(str(t.get('completed')) for t in updated_todos)}]")
                        _append_activity_log(task, "TODO 변경", f"AI가 TODO를 변경 (action={todo_action})")

                # 댓글 추가 요청
                if params.get("addComment"):
                    search_category = params.get("searchCategory")
                    search_query = task.description or task.title

                    knowledge_results = await search_knowledge_base(
                        query=search_query,
                        category=search_category,
                    )
                    knowledge_context = format_knowledge_context(knowledge_results)

                    comment_content = await generate_comment(
                        task_title=task.title,
                        task_description=task.description or "",
                        knowledge_context=knowledge_context,
                    )

                    if not task.comments:
                        task.comments = []
                    task.comments = task.comments + [
                        {
                            "id": f"comment-{uuid.uuid4().hex[:8]}",
                            "authorId": "ai-assistant",
                            "authorName": "AI 어시스턴트",
                            "content": comment_content,
                            "createdAt": datetime.utcnow().isoformat(),
                        }
                    ]

                # 담당자 변경
                if "assigneeName" in params:
                    task.assignee_name = params["assigneeName"]
                    _append_activity_log(task, "담당자 변경", f"AI가 담당자를 '{params['assigneeName']}'(으)로 변경")

                # 마감일 변경
                if "dueDate" in params:
                    due_str = params["dueDate"]
                    parsed_due = None
                    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"]:
                        try:
                            parsed_due = datetime.strptime(due_str, fmt)
                            break
                        except ValueError:
                            continue
                    if parsed_due:
                        task.due_date = parsed_due
                        _append_activity_log(task, "마감일 변경", f"AI가 마감일을 '{due_str}'(으)로 변경")

                # 태그 교체
                if "tags" in params and isinstance(params["tags"], list):
                    task.tags = params["tags"]
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(task, "tags")
                    _append_activity_log(task, "태그 변경", f"AI가 태그를 {params['tags']}(으)로 변경")

                # 태그 추가
                if "addTags" in params:
                    updated_tags = copy.deepcopy(task.tags or [])
                    for t in params["addTags"]:
                        if t not in updated_tags:
                            updated_tags.append(t)
                    task.tags = updated_tags
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(task, "tags")
                    _append_activity_log(task, "태그 추가", f"AI가 태그 {params['addTags']}을(를) 추가")

                # 태그 제거
                if "removeTags" in params:
                    updated_tags = copy.deepcopy(task.tags or [])
                    for t in params["removeTags"]:
                        if t in updated_tags:
                            updated_tags.remove(t)
                    task.tags = updated_tags
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(task, "tags")
                    _append_activity_log(task, "태그 제거", f"AI가 태그 {params['removeTags']}을(를) 제거")

                # 댓글 수동 추가
                if "commentContent" in params:
                    updated_comments = copy.deepcopy(task.comments or [])
                    updated_comments.append({
                        "id": f"comment-{uuid.uuid4().hex[:8]}",
                        "authorId": "ai-assistant",
                        "authorName": "AI 어시스턴트",
                        "content": params["commentContent"],
                        "createdAt": datetime.utcnow().isoformat(),
                    })
                    task.comments = updated_comments
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(task, "comments")
                    _append_activity_log(task, "댓글 추가", f"AI가 댓글 추가: '{params['commentContent'][:50]}'")

                # 댓글 삭제
                if params.get("commentAction") == "delete":
                    updated_comments = copy.deepcopy(task.comments or [])
                    comment_index = params.get("commentIndex")
                    comment_id = params.get("commentId")
                    removed = False
                    if comment_id:
                        updated_comments = [c for c in updated_comments if c.get("id") != comment_id]
                        removed = True
                    elif comment_index is not None and 0 <= comment_index < len(updated_comments):
                        del updated_comments[comment_index]
                        removed = True
                    if removed:
                        task.comments = updated_comments
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(task, "comments")
                        _append_activity_log(task, "댓글 삭제", "AI가 댓글을 삭제")

                # 활동이력 추가
                if params.get("activityAction") == "add":
                    detail = params.get("activityDetail", "")
                    _append_activity_log(task, "사용자 이력 추가", detail)

                # 활동이력 삭제
                if params.get("activityAction") == "delete":
                    updated_log = copy.deepcopy(task.activity_log or [])
                    activity_index = params.get("activityIndex")
                    activity_id = params.get("activityId")
                    removed = False
                    if activity_id:
                        updated_log = [a for a in updated_log if a.get("id") != activity_id]
                        removed = True
                    elif activity_index is not None and 0 <= activity_index < len(updated_log):
                        del updated_log[activity_index]
                        removed = True
                    if removed:
                        task.activity_log = updated_log
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(task, "activity_log")

                # 참조 추가 (RAG 검색)
                if params.get("referenceAction") == "add":
                    ref_query = params.get("referenceQuery", task.title)
                    ref_results = await search_knowledge_base(query=ref_query, top_k=3)
                    if ref_results:
                        updated_refs = copy.deepcopy(task.references or [])
                        existing_ids = {r.get("docId") for r in updated_refs}
                        for r in ref_results:
                            doc_id = r.get("id", "")
                            if doc_id not in existing_ids:
                                updated_refs.append({
                                    "docId": doc_id,
                                    "title": r.get("metadata", {}).get("title", ""),
                                    "content": r.get("content", "")[:500],
                                    "category": r.get("metadata", {}).get("category", ""),
                                    "score": round(r.get("score", 0), 2),
                                })
                        task.references = updated_refs
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(task, "references")
                        _append_activity_log(task, "참조 추가", f"AI가 {len(ref_results)}건의 관련 문서를 참조로 추가")

                # 참조 제거
                if params.get("referenceAction") == "remove":
                    updated_refs = copy.deepcopy(task.references or [])
                    ref_index = params.get("referenceIndex")
                    ref_doc_id = params.get("referenceDocId")
                    removed = False
                    if ref_doc_id:
                        updated_refs = [r for r in updated_refs if r.get("docId") != ref_doc_id]
                        removed = True
                    elif ref_index is not None and 0 <= ref_index < len(updated_refs):
                        del updated_refs[ref_index]
                        removed = True
                    if removed:
                        task.references = updated_refs
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(task, "references")
                        _append_activity_log(task, "참조 제거", "AI가 참조를 제거")

                await db.commit()

                return AgentAction(
                    type="update",
                    target="task",
                    targetId=target_id,
                    success=True,
                    result={
                        "status": task.status.value,
                        "priority": task.priority.value,
                        "title": task.title,
                        "assigneeName": task.assignee_name,
                        "dueDate": task.due_date.isoformat() if task.due_date else None,
                        "tags": task.tags,
                        "todosUpdated": "todoAction" in params,
                        "commentsUpdated": "commentContent" in params or params.get("commentAction") == "delete",
                        "referencesUpdated": params.get("referenceAction") in ("add", "remove"),
                    }
                )

        # 삭제 요청 (2턴 확인 플로우)
        elif intent.action == "delete" and target == "task" and target_id:
            if session_id:
                _pending_actions[session_id] = {
                    "type": "delete_task",
                    "target_id": target_id,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            return AgentAction(
                type="delete",
                target="task",
                targetId=target_id,
                success=False,
                error="정말 이 태스크를 삭제하시겠습니까? '네' 또는 '아니오'로 답해주세요."
            )

        # 태스크 목록 조회
        elif intent.action == "view" and target == "task" and not target_id:
            params = intent.parameters
            query = select(Task)
            status_filter = params.get("statusFilter")
            priority_filter = params.get("priorityFilter")
            if status_filter:
                status_map = {
                    "backlog": TaskStatus.BACKLOG, "todo": TaskStatus.TODO,
                    "in-progress": TaskStatus.IN_PROGRESS, "진행중": TaskStatus.IN_PROGRESS,
                    "review": TaskStatus.REVIEW, "done": TaskStatus.DONE, "완료": TaskStatus.DONE,
                }
                if status_filter in status_map:
                    query = query.where(Task.status == status_map[status_filter])
            if priority_filter:
                priority_map = {
                    "low": TaskPriority.LOW, "medium": TaskPriority.MEDIUM,
                    "high": TaskPriority.HIGH, "urgent": TaskPriority.URGENT,
                }
                if priority_filter in priority_map:
                    query = query.where(Task.priority == priority_map[priority_filter])
            query = query.order_by(Task.updated_at.desc()).limit(20)
            result = await db.execute(query)
            tasks = result.scalars().all()
            task_list = [
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status.value,
                    "priority": t.priority.value,
                    "assigneeName": t.assignee_name,
                    "dueDate": t.due_date.isoformat() if t.due_date else None,
                    "tags": t.tags,
                }
                for t in tasks
            ]
            return AgentAction(
                type="view",
                target="task",
                success=True,
                result={"tasks": task_list, "count": len(task_list)}
            )

        # 태스크 생성
        elif intent.action == "create" and target == "task":
            params = intent.parameters
            new_id = f"task-{uuid.uuid4().hex[:8]}"

            # 구조화된 태스크 생성 시도
            search_category = params.get("searchCategory")
            pre_knowledge = ""
            if search_category:
                pre_results = await search_knowledge_base(
                    query=params.get("description", params.get("title", "")),
                    category=search_category,
                )
                pre_knowledge = format_knowledge_context(pre_results)

            structured = await generate_structured_task(
                user_message=original_message or "",
                knowledge_context=pre_knowledge,
            )

            if structured:
                task_title = structured.get("title", params.get("title", "새 태스크"))
                task_desc = structured.get("description", params.get("description", ""))
                task_priority = structured.get("priority", params.get("priority", "medium"))
                task_tags = structured.get("tags", params.get("tags", []))
                task_todos = [
                    {"id": f"todo-{uuid.uuid4().hex[:8]}", "text": t, "completed": False}
                    for t in structured.get("todos", [])
                ]
                task_assignee = structured.get("assignee", "")
                task_due_date_str = structured.get("dueDate", "")
                # Parse dueDate string to datetime if provided
                task_due_date = None
                if task_due_date_str:
                    try:
                        # Try common date formats
                        for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"]:
                            try:
                                task_due_date = datetime.strptime(task_due_date_str, fmt)
                                break
                            except ValueError:
                                continue
                    except Exception:
                        task_due_date = None
            else:
                task_title = params.get("title", "새 태스크")
                task_desc = params.get("description", "")
                task_priority = params.get("priority", "medium")
                task_tags = params.get("tags", [])
                task_todos = []
                task_assignee = params.get("assigneeName", "")
                task_due_date = None

            new_task = Task(
                id=new_id,
                title=task_title,
                description=task_desc,
                status=TaskStatus.TODO,
                priority=TaskPriority(task_priority) if task_priority in ["low", "medium", "high", "urgent"] else TaskPriority.MEDIUM,
                tags=task_tags,
                todos=task_todos,
                assignee_name=task_assignee if task_assignee else None,
                due_date=task_due_date,
                comments=[],
                references=[],
                activity_log=[
                    {
                        "id": f"log-{uuid.uuid4().hex[:8]}",
                        "userId": "ai-assistant",
                        "userName": "AI 어시스턴트",
                        "action": "태스크 생성",
                        "detail": "AI 어시스턴트가 구조화된 템플릿으로 생성한 태스크입니다",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                ],
            )

            db.add(new_task)

            comment_added = False
            knowledge_used = False

            # addComment가 요청된 경우 → 지식 검색 + 댓글 생성
            if params.get("addComment"):
                search_category = params.get("searchCategory")
                search_query = params.get("description", params.get("title", ""))

                knowledge_results = await search_knowledge_base(
                    query=search_query,
                    category=search_category,
                )
                knowledge_context = format_knowledge_context(knowledge_results)

                if knowledge_results:
                    knowledge_used = True

                comment_content = await generate_comment(
                    task_title=new_task.title,
                    task_description=new_task.description,
                    knowledge_context=knowledge_context,
                )

                new_task.comments = [
                    {
                        "id": f"comment-{uuid.uuid4().hex[:8]}",
                        "authorId": "ai-assistant",
                        "authorName": "AI 어시스턴트",
                        "content": comment_content,
                        "createdAt": datetime.utcnow().isoformat(),
                    }
                ]
                comment_added = True

            # 지식 사용 시 활동 이력에 추론 근거 추가
            if knowledge_used and knowledge_results:
                doc_titles = [r.get("metadata", {}).get("title", "?") for r in knowledge_results]
                scores = [f"{r.get('score', 0):.2f}" for r in knowledge_results]
                detail_lines = ["**AI 추론 근거:**"]
                detail_lines.append(f"- 검색 카테고리: {search_category or '전체'}")
                detail_lines.append(f"- 참조 지식 문서:")
                for title, score in zip(doc_titles, scores):
                    detail_lines.append(f"  - {title} (유사도: {score})")
                detail_lines.append(f"- 자동 댓글 생성: {'예' if comment_added else '아니오'}")

                new_task.activity_log = new_task.activity_log + [
                    {
                        "id": f"log-{uuid.uuid4().hex[:8]}",
                        "userId": "ai-assistant",
                        "userName": "AI 어시스턴트",
                        "action": "지식 기반 추론",
                        "detail": "\n".join(detail_lines),
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                ]

                new_task.references = [
                    {
                        "docId": r.get("id", ""),
                        "title": r.get("metadata", {}).get("title", ""),
                        "content": r.get("content", "")[:500],
                        "category": r.get("metadata", {}).get("category", ""),
                        "score": round(r.get("score", 0), 2),
                    }
                    for r in knowledge_results
                ]

            await db.commit()

            return AgentAction(
                type="create",
                target="task",
                targetId=new_id,
                success=True,
                result={
                    "taskId": new_id,
                    "title": new_task.title,
                    "commentAdded": comment_added,
                    "knowledgeUsed": knowledge_used,
                    "knowledgeDocs": [
                        {"title": r.get("metadata", {}).get("title", ""), "score": round(r.get("score", 0), 2)}
                        for r in knowledge_results
                    ] if knowledge_used else [],
                }
            )

        # 지식 검색
        elif intent.action == "search" and target == "document":
            params = intent.parameters
            search_category = params.get("searchCategory")
            search_query = params.get("query", "") or original_message

            logger.info(f"[RAG-ACTION] query='{search_query}', category='{search_category}', params={params}")

            results = await search_knowledge_base(
                query=search_query or "정보",
                category=search_category,
            )
            logger.info(f"[RAG-ACTION] results={len(results)}")

            return AgentAction(
                type="search",
                target="document",
                success=True,
                result={
                    "resultCount": len(results),
                    "results": [
                        {
                            "id": r["id"],
                            "title": r.get("metadata", {}).get("title", ""),
                            "score": round(r["score"], 3),
                            "content": r["content"],
                        }
                        for r in results
                    ],
                }
            )

        # 양식 채우기 (fill_form) - RAG에서 처리되므로 별도 action은 없음
        elif intent.action == "fill_form":
            return AgentAction(
                type="fill_form",
                target="document",
                success=True,
                result={"message": "양식 채우기 요청이 처리되었습니다."}
            )

    except Exception as e:
        return AgentAction(
            type=intent.action,
            target=target or "unknown",
            targetId=target_id,
            success=False,
            error=str(e)
        )

    return None


# ─────────────────────────────────────────────────────────────────────────────
# 응답 생성
# ─────────────────────────────────────────────────────────────────────────────

ASSISTANT_SYSTEM_PROMPT = """당신은 'AI 업무도우미'의 AI 어시스턴트입니다.
사용자의 업무 관리를 돕는 친절하고 유능한 비서 역할을 합니다.

주요 기능:
- 태스크(Task) 관리: 생성, 상태 변경, 우선순위 조정, 댓글 작성
- 도구(Tool) 설명 및 활용
- AI 노드(Node) 설정 및 설명
- 워크플로우(Workflow) 관리 및 실행
- 지식 문서(Document) 검색 및 참조
- 양식 채우기: 양식 템플릿에 맞춰 데이터를 마크다운 표로 작성

응답 가이드:
- 한국어로 답변
- 간결하고 명확하게
- 작업 완료 시 결과를 확인시켜줌
- 친절하지만 과하지 않은 톤
- 지식 베이스의 정보가 제공되면 이를 근거로 정확한 답변 제공
- 민원/문의에 대해 전문적이고 정중한 답변 작성
- 태스크 생성/댓글 작성 결과를 사용자에게 명확히 안내
- 양식 채우기 요청 시: 양식 템플릿의 테이블 구조를 그대로 사용하고, 데이터에서 해당 값을 채워서 완성된 마크다운 표로 응답
- 양식의 빈 필드(괄호로 표시된 부분)를 실제 데이터로 치환하여 작성
"""


async def generate_response(
    message: str,
    context_data: Optional[Dict[str, Any]],
    action: Optional[AgentAction],
    session_messages: List[Dict[str, Any]],
    knowledge_context: str = "",
) -> str:
    """LLM을 사용하여 응답 생성"""
    try:
        handler = get_llm_handler()

        # 메시지 히스토리 구성 (최근 10개)
        messages = [LLMMessage(role="system", content=ASSISTANT_SYSTEM_PROMPT)]

        # 지식 컨텍스트 주입
        if knowledge_context:
            if action and action.type == "fill_form":
                messages.append(LLMMessage(
                    role="system",
                    content=f"{knowledge_context}\n\n위 양식 템플릿의 테이블 구조를 사용하되, 괄호 안의 플레이스홀더를 [채울 데이터]의 실제 값으로 치환하여 완성된 마크다운 표를 작성하세요. 데이터에 없는 항목은 '-'로 표시하세요."
                ))
            else:
                messages.append(LLMMessage(
                    role="system",
                    content=f"[참고 지식]\n{knowledge_context}\n\n위 지식을 참고하여 정확하고 근거 있는 답변을 제공하세요."
                ))

        for msg in session_messages[-10:]:
            messages.append(LLMMessage(
                role=msg["role"],
                content=msg["content"]
            ))

        # 현재 사용자 메시지
        user_content = message
        if context_data:
            user_content += f"\n\n[선택된 항목: {context_data.get('type', '')} - {context_data.get('title') or context_data.get('name', '')}]"

        messages.append(LLMMessage(role="user", content=user_content))

        # 작업 결과가 있으면 시스템 메시지로 추가
        if action:
            if action.success:
                action_info = f"[시스템] 작업 완료: {action.type} on {action.target}"
                if action.result:
                    action_info += f"\n결과: {json.dumps(action.result, ensure_ascii=False)}"
            else:
                action_info = f"[시스템] 작업 실패: {action.error}"
            messages.append(LLMMessage(role="system", content=action_info))

        # 양식 채우기는 표가 길 수 있으므로 토큰 증가
        max_tokens = 2000 if (action and action.type == "fill_form") else 1000
        request = LLMRequest(
            messages=messages,
            temperature=0.7,
            max_tokens=max_tokens,
            call_type="response_generation",
        )

        response = await handler.chat(request)
        return response.content

    except Exception as e:
        print(f"응답 생성 오류: {e}")
        # LLM 연결 실패 시 기본 응답
        if action and action.success:
            return f"작업이 완료되었습니다. ({action.type}: {action.target})"
        elif action and not action.success:
            return f"작업 중 문제가 발생했습니다: {action.error}"
        else:
            return "죄송합니다. 현재 AI 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해주세요."


# ─────────────────────────────────────────────────────────────────────────────
# 메인 처리 함수
# ─────────────────────────────────────────────────────────────────────────────

async def process_chat_message(
    db: AsyncSession,
    content: str,
    context: Optional[ChatContextBase] = None,
    session_id: Optional[str] = None,
) -> ChatMessageResponse:
    """
    채팅 메시지 처리 메인 함수

    1. 세션 관리
    2. 컨텍스트 로딩
    3. 의도 감지
    4. 작업 실행
    5. 응답 생성
    """
    # 1. 세션 관리
    session_id = get_or_create_session(session_id)
    add_message_to_session(session_id, "user", content)

    # 2. 컨텍스트 로딩
    context_data = None
    if context and context.type != 'none':
        context_data = await load_context_data(db, context)

    # 3. 의도 감지
    intent = await detect_intent(content, context_data)
    logger.info(f"[INTENT] action={intent.action}, target={intent.target}, params={intent.parameters}, conf={intent.confidence}")

    # 3.1. TODO 키워드 오버라이드 - LLM이 todoAction을 누락하는 경우 보완
    if context and context.type == 'task' and context.id:
        is_todo_request = any(kw in content for kw in ["할일", "TODO", "todo", "체크", "완료 처리", "체크해", "완료해"])
        if is_todo_request and "todoAction" not in intent.parameters:
            is_all = any(kw in content for kw in ["전부", "모두", "다 ", "전체", "다해", "전부다", "3개"])
            is_uncheck = any(kw in content for kw in ["해제", "취소", "체크 해제", "체크해제"])
            if is_all:
                todo_action = "uncomplete_all" if is_uncheck else "complete_all"
            else:
                todo_action = "uncomplete" if is_uncheck else "complete"
            intent = DetectedIntent(
                action="update",
                target="task",
                parameters={**intent.parameters, "todoAction": todo_action},
                confidence=intent.confidence,
            )
            logger.info(f"[TODO-OVERRIDE] todoAction={todo_action} injected")

    # 3.5. 지식 검색 (RAG) - 질문이나 문의는 자동 검색
    knowledge_context = ""
    knowledge_results = []
    search_category = intent.parameters.get("searchCategory")
    # search 액션이거나, 카테고리가 있거나, 질문형 메시지인 경우 RAG 실행
    is_question = any(kw in content for kw in ["?", "어떻게", "왜", "알려", "문의", "질문", "방법", "절차", "가이드", "안내", "하나요", "인가요", "인지요", "나요", "할까", "할까요", "뭐야", "뭔가요", "무엇"])
    is_form_fill = intent.action == "fill_form" or any(kw in content for kw in ["양식", "양식에 맞", "표로 정리", "표 채워", "양식으로"])
    logger.info(f"[RAG] search_category={search_category}, is_question={is_question}, is_form_fill={is_form_fill}, action={intent.action}")

    # 양식 채우기가 키워드로 감지되었으나 LLM이 다른 액션으로 분류한 경우 → fill_form으로 강제 오버라이드
    if is_form_fill and intent.action != "fill_form":
        logger.info(f"[RAG-OVERRIDE] intent.action '{intent.action}' → 'fill_form' (양식 키워드 감지)")
        intent = DetectedIntent(
            action="fill_form",
            target="document",
            parameters=intent.parameters,
            confidence=intent.confidence,
        )

    if is_form_fill:
        # 2단계 크로스 카테고리 RAG: "양식" 카테고리에서 템플릿 + 데이터 카테고리에서 스펙
        form_query = intent.parameters.get("formQuery", "")
        data_query = intent.parameters.get("dataQuery", "")
        data_category = intent.parameters.get("dataCategory", search_category)

        # LLM이 파라미터를 설정하지 못한 경우 메시지에서 자동 추출
        if not form_query:
            # "서버현황표 양식" → "서버현황표" 추출
            import re
            form_match = re.search(r'([\w]+(?:표|양식))', content)
            form_query = form_match.group(1) if form_match else "양식"
        if not data_query:
            data_query = content
        if not data_category:
            # 서비스명 키워드로 카테고리 추론
            if any(kw in content for kw in ["소스코드검증", "코드아이즈", "CodeEyes", "ceyes"]):
                data_category = "소스코드검증"

        # 1) 양식 템플릿: 항상 category="양식"에서 검색
        form_results = await search_knowledge_base(
            query=form_query,
            category="양식",
            top_k=2,
            min_score=0.15,
        )
        # 2) 채울 데이터: 다중 전략으로 검색
        # 전략 A: 벡터 유사도 검색 (원본 쿼리)
        data_results_vec = await search_knowledge_base(
            query=data_query,
            category=data_category if data_category else None,
            top_k=5,
            min_score=0.1,
        )
        # 전략 B: 양식 컬럼 키워드 기반 보조 검색
        form_col_query = ""
        if form_results:
            form_content = form_results[0].get("content", "")
            import re as _re
            headers = _re.findall(r'\|\s*([^|\n]+?)\s*(?=\|)', form_content)
            # 테이블 헤더에서 의미 있는 컬럼명만 추출 (구분, 순번 등 제외)
            meaningful = [h.strip() for h in headers if h.strip() and h.strip() not in ["구분", "---", "번호"]]
            if meaningful:
                form_col_query = f"{data_category or ''} " + " ".join(meaningful[:5])
        if form_col_query:
            data_results_col = await search_knowledge_base(
                query=form_col_query,
                category=data_category if data_category else None,
                top_k=5,
                min_score=0.1,
            )
        else:
            data_results_col = []

        # 전략 C: 제목 키워드 직접 매칭 (벡터 검색이 놓칠 수 있는 문서 보완)
        # "스펙", "인프라", "서버" 등 핵심 키워드가 제목에 포함된 문서를 직접 검색
        title_keywords = ["스펙", "인프라", "서버", "구성", "현황"]
        data_results_title = []
        if data_category:
            title_search_query = f"{data_category} 서버 인프라 스펙 구성 IP 호스트명"
            data_results_title = await search_knowledge_base(
                query=title_search_query,
                category=data_category,
                top_k=5,
                min_score=0.1,
            )

        # 세 검색 결과 병합 (중복 제거, 최고 점수 유지)
        seen = {}
        for r in data_results_vec + data_results_col + data_results_title:
            rid = r.get("id", "")
            if not rid:
                continue
            if rid not in seen or r.get("score", 0) > seen[rid].get("score", 0):
                seen[rid] = r
        # 점수 순 정렬, 상위 5개
        data_results = sorted(seen.values(), key=lambda x: x.get("score", 0), reverse=True)[:5]

        logger.info(f"[RAG-FORM] form_query='{form_query}' (양식), data_query='{data_query}' ({data_category}), form_results={len(form_results)}, data_results={len(data_results)}")

        # 양식과 데이터를 구분하여 포맷
        parts = []
        if form_results:
            parts.append("[요청된 양식 템플릿]")
            for i, r in enumerate(form_results, 1):
                title = r.get("metadata", {}).get("title", "제목 없음")
                parts.append(f"\n{i}. {title}")
                parts.append(r.get("content", ""))
        if data_results:
            parts.append("\n[채울 데이터]")
            for i, r in enumerate(data_results, 1):
                title = r.get("metadata", {}).get("title", "제목 없음")
                parts.append(f"\n{i}. {title}")
                parts.append(r.get("content", ""))
        knowledge_context = "\n".join(parts)

        # knowledge_results를 합쳐서 출처 표시용으로 통합
        knowledge_results = form_results + data_results

    elif search_category or intent.action == "search" or is_question:
        knowledge_results = await search_knowledge_base(
            query=content,
            category=search_category if search_category else None,
        )
        knowledge_context = format_knowledge_context(knowledge_results)
        logger.info(f"[RAG] knowledge_results={len(knowledge_results)}, context_len={len(knowledge_context)}")

    # 4. 작업 실행
    action = await execute_action(db, intent, context, context_data, original_message=content, session_id=session_id)

    # 5. 응답 생성
    session_messages = get_session_messages(session_id)
    response_content = await generate_response(content, context_data, action, session_messages, knowledge_context)

    # 5.5. 참조 지식 출처 표시
    if knowledge_context and knowledge_results:
        sources = []
        for r in knowledge_results:
            title = r.get("metadata", {}).get("title", "제목 없음")
            doc_id = r.get("id", "")
            score = r.get("score", 0)
            sources.append(f"- [{title}](/knowledge?doc={doc_id}) (유사도 {score:.0%})")
        if sources:
            response_content += "\n\n---\n📚 **참조 지식**\n" + "\n".join(sources)

    # 응답을 세션에 추가
    add_message_to_session(session_id, "assistant", response_content)

    # 응답 생성
    return ChatMessageResponse(
        id=f"msg-{uuid.uuid4().hex[:8]}",
        role="assistant",
        content=response_content,
        timestamp=datetime.utcnow().isoformat() + "Z",
        action=action,
        sessionId=session_id,
    )
