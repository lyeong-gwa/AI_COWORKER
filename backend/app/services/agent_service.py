"""
Agent Service

AI 어시스턴트의 핵심 로직
- 사용자 의도 파악
- 컨텍스트 기반 작업 수행
- 응답 생성
"""

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
from ..models.knowledge import KnowledgeDocument
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
            result = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == context.id))
            item = result.scalar_one_or_none()
            if item:
                return {
                    "type": "document",
                    "id": item.id,
                    "title": item.title,
                    "filename": item.filename,
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

        return [
            {
                "id": r.id,
                "content": r.content,
                "score": r.score,
                "metadata": r.metadata,
            }
            for r in results
        ]
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
        # 긴 내용은 앞부분만
        if len(content) > 800:
            content = content[:800] + "..."
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
        )
        return response.content

    except Exception as e:
        print(f"댓글 생성 오류: {e}")
        return f"[자동 생성 답변] '{task_title}'에 대한 검토가 필요합니다. 관련 지식 베이스를 참고하여 답변을 작성해주세요."


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
- search: 검색 요청 ("찾아줘", "검색해줘", "알려줘", "질문")
- chat: 일반 대화 (위에 해당하지 않음)

가능한 target 타입:
- task: 태스크
- tool: 도구
- node: 노드
- workflow: 워크플로우
- document: 문서

parameters 가이드:
- create + task인 경우: {"title": "제목", "description": "설명", "priority": "medium", "tags": ["태그"], "addComment": true/false}
- update + task인 경우: {"status": "상태값", "priority": "우선순위", "addComment": true/false}
- search + document인 경우: {"searchCategory": "카테고리명"} (예: "코드아이즈")
- addComment: 답변/코멘트도 함께 작성해달라는 요청 시 true

복합 요청 인식:
- "등록하고 답변도 달아줘" → create + addComment: true
- "태스크로 만들고 코멘트도 작성해줘" → create + addComment: true
- 메일/민원 내용이 포함된 경우 → create + task + addComment: true (메일 내용을 description으로)
- 서비스명이 언급되면 searchCategory에 해당 서비스명 추출 (예: "코드아이즈" → searchCategory: "코드아이즈")

응답 형식 (JSON만):
{
  "action": "create",
  "target": "task",
  "parameters": {"title": "민원: 점검결과 이상", "description": "...", "priority": "high", "tags": ["민원", "코드아이즈"], "addComment": true, "searchCategory": "코드아이즈"},
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
# 작업 실행
# ─────────────────────────────────────────────────────────────────────────────

async def execute_action(
    db: AsyncSession,
    intent: DetectedIntent,
    context: Optional[ChatContextBase],
    context_data: Optional[Dict[str, Any]]
) -> Optional[AgentAction]:
    """감지된 의도에 따라 작업 실행"""

    if intent.action == "chat":
        return None  # 일반 대화는 작업 없음

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

                # 제목 변경
                if "title" in params:
                    task.title = params["title"]

                # 설명 변경
                if "description" in params:
                    task.description = params["description"]

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
                    }
                )

        # 삭제 요청
        elif intent.action == "delete" and target_id:
            # 삭제는 확인 후 진행 (여기서는 미구현)
            return AgentAction(
                type="delete",
                target=target,
                targetId=target_id,
                success=False,
                error="삭제는 확인이 필요합니다. 정말 삭제하시겠습니까?"
            )

        # 태스크 생성
        elif intent.action == "create" and target == "task":
            params = intent.parameters
            new_id = f"task-{uuid.uuid4().hex[:8]}"

            new_task = Task(
                id=new_id,
                title=params.get("title", "새 태스크"),
                description=params.get("description", ""),
                status=TaskStatus.TODO,
                priority=TaskPriority(params.get("priority", "medium")) if params.get("priority") in ["low", "medium", "high", "urgent"] else TaskPriority.MEDIUM,
                tags=params.get("tags", []),
                todos=[],
                comments=[],
                references=[],
                activity_log=[
                    {
                        "id": f"log-{uuid.uuid4().hex[:8]}",
                        "userId": "ai-assistant",
                        "userName": "AI 어시스턴트",
                        "action": "태스크 생성",
                        "detail": "AI 어시스턴트가 자동으로 생성한 태스크입니다",
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
            search_query = params.get("query", "")

            # query가 없으면 원본 메시지에서 추출 (context_data에서)
            if not search_query and context_data:
                search_query = context_data.get("title", "")

            results = await search_knowledge_base(
                query=search_query or "정보",
                category=search_category,
            )

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
                            "preview": r["content"][:200] + "..." if len(r["content"]) > 200 else r["content"],
                        }
                        for r in results
                    ],
                }
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

응답 가이드:
- 한국어로 답변
- 간결하고 명확하게
- 작업 완료 시 결과를 확인시켜줌
- 친절하지만 과하지 않은 톤
- 지식 베이스의 정보가 제공되면 이를 근거로 정확한 답변 제공
- 민원/문의에 대해 전문적이고 정중한 답변 작성
- 태스크 생성/댓글 작성 결과를 사용자에게 명확히 안내
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

        request = LLMRequest(
            messages=messages,
            temperature=0.7,
            max_tokens=1000,
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

    # 3.5. 지식 검색 (RAG) - 서비스 관련 질문이면 자동 검색
    knowledge_context = ""
    search_category = intent.parameters.get("searchCategory")
    if search_category or intent.action == "search":
        knowledge_results = await search_knowledge_base(
            query=content,
            category=search_category,
        )
        knowledge_context = format_knowledge_context(knowledge_results)

    # 4. 작업 실행
    action = await execute_action(db, intent, context, context_data)

    # 5. 응답 생성
    session_messages = get_session_messages(session_id)
    response_content = await generate_response(content, context_data, action, session_messages, knowledge_context)

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
