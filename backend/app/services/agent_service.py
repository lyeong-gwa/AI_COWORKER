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

from ..models.node import AINode
from ..models.workflow import Workflow
from .knowledge_file_service import read_md_file, write_md_file, compute_hash, generate_doc_id
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
        if context.type == 'node':
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


async def generate_document_update(
    existing_content: str,
    existing_title: str,
    existing_tags: list,
    existing_category: str,
    user_instruction: str,
) -> dict:
    """기존 문서를 사용자 지시에 따라 수정한 결과를 LLM으로 생성"""
    try:
        handler = get_llm_handler()

        system_prompt = """당신은 지식 문서를 편집하는 전문가이자, 문서 맥락을 분석하는 검토자입니다.

## 작업 순서
1. **맥락 분석**: 문서 전체를 읽고, 사용자의 수정 지시와 관련된 모든 데이터를 파악합니다.
2. **충돌/문제 감지**: 수정 적용 시 발생할 수 있는 문제를 식별합니다:
   - 중복 값 (예: 동일 IP가 다른 서버에 이미 할당됨)
   - 논리적 불일치 (예: 쌍 구성, 참조 관계 깨짐)
   - 데이터 정합성 문제 (예: 요약 테이블과 상세 테이블 불일치)
   - 기타 문맥상 의심되는 사항
3. **수정 수행**: 문제가 없거나 사소한 경우에만 수정을 반영합니다.

## 핵심 규칙
- 충돌이 발견되면 warnings에 구체적으로 기술하고 hasConflict를 true로 설정
- 충돌이 있을 때는 updatedContent에 원본을 그대로 유지 (수정 적용하지 않음)
- 충돌이 없을 때만 실제 수정을 반영한 updatedContent를 반환
- 수정 시 관련된 모든 위치를 함께 수정 (예: 요약 테이블, 쌍 구성 테이블 등)
- 마크다운 형식 유지

반드시 아래 JSON 형식으로만 응답하세요:
{
  "updatedContent": "수정된 전체 문서 내용 (충돌 시 원본 그대로)",
  "updatedTitle": "수정된 제목 (변경 없으면 null)",
  "updatedTags": ["수정된 태그 목록 (변경 없으면 null)"],
  "updatedCategory": "수정된 카테고리 (변경 없으면 null)",
  "changeDescription": "변경 내용 요약",
  "warnings": ["감지된 문제나 충돌 사항 목록 (없으면 빈 배열)"],
  "hasConflict": false
}

updatedTitle, updatedTags, updatedCategory는 사용자가 명시적으로 변경을 요청한 경우에만 값을 넣고, 그렇지 않으면 null로 두세요."""

        user_prompt = f"""기존 문서 정보:
- 제목: {existing_title}
- 카테고리: {existing_category}
- 태그: {', '.join(existing_tags)}

기존 문서 내용:
{existing_content}

사용자 수정 지시:
{user_instruction}"""

        response = await handler.simple_chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=4000,
            call_type="document_update",
        )

        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        if not content.startswith("{"):
            start_idx = content.find("{")
            end_idx = content.rfind("}")
            if start_idx != -1 and end_idx != -1:
                content = content[start_idx:end_idx + 1]

        return json.loads(content)

    except Exception as e:
        logger.warning(f"문서 수정 생성 실패: {e}")
        return None


async def generate_document_content(
    user_instruction: str,
    title_hint: str = "",
    category_hint: str = "",
    tags_hint: list = None,
    content_hint: str = "",
) -> dict:
    """사용자 지시로부터 새 지식 문서 구조를 LLM으로 생성"""
    try:
        handler = get_llm_handler()

        system_prompt = """당신은 지식 문서를 체계적으로 작성하는 전문가입니다.
사용자의 요청을 분석하여 구조화된 지식 문서를 생성합니다.

사용자가 등록한 카테고리를 활용하거나, 요청 내용에 맞는 새 카테고리명을 사용할 수 있습니다.

반드시 아래 JSON 형식으로만 응답하세요:
{
  "title": "문서 제목",
  "category": "카테고리",
  "tags": ["태그1", "태그2"],
  "content": "마크다운 형식의 문서 본문"
}

규칙:
- 제목은 간결하고 명확하게
- 태그는 2~5개
- 본문은 마크다운 형식으로 체계적으로 작성
- 사용자가 제공한 힌트가 있으면 반영"""

        user_prompt = f"문서 생성 요청:\n{user_instruction}"
        if title_hint:
            user_prompt += f"\n제목 힌트: {title_hint}"
        if category_hint:
            user_prompt += f"\n카테고리 힌트: {category_hint}"
        if tags_hint:
            user_prompt += f"\n태그 힌트: {', '.join(tags_hint)}"
        if content_hint:
            user_prompt += f"\n내용 힌트: {content_hint}"

        response = await handler.simple_chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=2000,
            call_type="document_creation",
        )

        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        if not content.startswith("{"):
            start_idx = content.find("{")
            end_idx = content.rfind("}")
            if start_idx != -1 and end_idx != -1:
                content = content[start_idx:end_idx + 1]

        return json.loads(content)

    except Exception as e:
        logger.warning(f"문서 내용 생성 실패: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 구조화된 의도 해석 (mode + action 기반)
# ─────────────────────────────────────────────────────────────────────────────

def resolve_structured_intent(
    mode: Optional[str],
    action: Optional[str],
    content: str,
    context_data: Optional[Dict[str, Any]],
) -> Optional[DetectedIntent]:
    """Frontend에서 mode + action을 명시적으로 전송한 경우, LLM intent detection을 건너뛰고 직접 라우팅"""
    if not mode or mode == 'general':
        return None  # LLM fallback

    if mode == 'knowledge':
        if action in ('search', 'ask'):
            return DetectedIntent(action='search', target='document', parameters={'query': content}, confidence=1.0)
        if action == 'modify':
            return DetectedIntent(action='update', target='document', parameters={'updateInstruction': content}, confidence=1.0)
        # default: search knowledge
        return DetectedIntent(action='search', target='document', parameters={'query': content}, confidence=0.9)

    elif mode == 'node':
        if action == 'modify':
            return DetectedIntent(action='update', target='node', parameters={}, confidence=1.0)
        return DetectedIntent(action='explain', target='node', parameters={}, confidence=0.9)

    elif mode == 'workflow':
        if action == 'modify':
            return DetectedIntent(action='update', target='workflow', parameters={}, confidence=1.0)
        return DetectedIntent(action='explain', target='workflow', parameters={}, confidence=0.9)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# 의도 감지
# ─────────────────────────────────────────────────────────────────────────────

INTENT_DETECTION_PROMPT = """당신은 사용자의 의도를 파악하는 AI입니다.
사용자 메시지와 선택된 컨텍스트를 분석하여 의도를 JSON으로 반환하세요.

가능한 action 타입:
- explain: 설명 요청 ("이게 뭐야?", "설명해줘")
- view: 조회 요청 ("보여줘", "목록")
- create: 생성 요청 ("만들어줘", "추가해줘", "등록해줘")
- update: 수정 요청 ("변경해줘", "수정해줘", "상태를 ~로")
- delete: 삭제 요청 ("삭제해줘", "제거해줘")
- execute: 실행 요청 ("실행해줘", "테스트해줘")
- search: 검색/문의/질문 ("찾아줘", "검색해줘", "알려줘", "~은 어떻게 하나요?", "~이 뭐야?", 업무 관련 질문)
- fill_form: 양식 채우기 요청 ("~양식에 맞춰서 작성해줘", "~표로 정리해줘", "~양식으로 만들어줘", "~표 채워줘")
- chat: 일반 대화 (위에 해당하지 않음)

가능한 target 타입:
- node: 노드
- workflow: 워크플로우
- document: 문서

사용자가 등록한 카테고리를 문맥에서 추론하여 searchCategory에 사용하세요.

parameters 가이드:
- search + document인 경우: {"query": "검색 키워드", "searchCategory": "카테고리명(옵션)"}
- fill_form인 경우: {"formQuery": "양식명", "dataQuery": "데이터 검색어", "dataCategory": "데이터카테고리"}
  - formQuery: 양식 카테고리에서 검색할 양식명
  - dataQuery: 데이터 카테고리에서 검색할 키워드
  - dataCategory: 데이터를 검색할 카테고리
- update + document인 경우: {"updateInstruction": "수정 지시 원문"}
- create + document인 경우: {"title": "문서 제목", "category": "카테고리", "tags": ["태그"], "contentHint": "내용 힌트"}

검색 예시:
- "업무 프로세스 절차가 어떻게 되나요?" → action: "search", target: "document", parameters: {"query": "업무 프로세스 절차"}
- "권한 신청은 어떻게 하나요?" → action: "search", target: "document", parameters: {"query": "권한 신청 절차"}

양식 채우기 예시:
- "업무 현황을 양식에 맞춰 작성해줘" → action: "fill_form", target: "document", parameters: {"formQuery": "업무현황표", "dataQuery": "업무 진행 현황"}
- "보고서 양식으로 정리해줘" → action: "fill_form", target: "document", parameters: {"formQuery": "보고서", "dataQuery": "보고 내용"}

문서 수정 예시:
- "이 항목의 값을 변경해줘" → action: "update", target: "document", parameters: {"updateInstruction": "항목 값 변경"}
- "이 문서 제목을 바꿔줘" → action: "update", target: "document", parameters: {"updateInstruction": "제목 변경"}

문서 생성 예시:
- "업무 매뉴얼 문서를 만들어줘" → action: "create", target: "document", parameters: {"title": "업무 매뉴얼", "contentHint": "업무 절차"}
- "회의록 문서 만들어줘" → action: "create", target: "document", parameters: {"title": "회의록", "contentHint": "회의 내용"}

응답 형식 (JSON만):
{
  "action": "search",
  "target": "document",
  "parameters": {"query": "업무 프로세스 절차"},
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

    target = intent.target or (context.type if context and context.type != 'none' else None)
    target_id = context.id if context and context.type != 'none' else None

    # 컨텍스트 타입 기반 target 보정: context가 document인데 LLM이 task로 잘못 분류한 경우
    if context and context.type == 'document' and intent.action in ("update", "create", "delete") and target != "document":
        logger.info(f"[TARGET-OVERRIDE] target '{target}' → 'document' (context.type=document)")
        target = "document"

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

        # 문서 수정
        elif intent.action == "update" and target == "document" and target_id:
            params = intent.parameters
            doc = read_md_file(target_id)
            if not doc:
                return AgentAction(
                    type="update", target="document",
                    targetId=target_id,
                    success=False, error="문서를 찾을 수 없습니다."
                )

            update_instruction = params.get("updateInstruction", original_message)
            updated = await generate_document_update(
                existing_content=doc.content,
                existing_title=doc.title,
                existing_tags=doc.tags,
                existing_category=doc.category,
                user_instruction=update_instruction,
            )

            if not updated:
                return AgentAction(
                    type="update", target="document",
                    targetId=target_id,
                    success=False, error="문서 수정 내용 생성에 실패했습니다."
                )

            warnings = updated.get("warnings", [])
            has_conflict = updated.get("hasConflict", False)

            # 충돌이 감지된 경우: 수정을 보류하고 경고 반환
            if has_conflict and warnings:
                warning_text = "\n".join(f"⚠️ {w}" for w in warnings)
                return AgentAction(
                    type="update", target="document",
                    targetId=target_id,
                    success=False,
                    error=f"문서 수정 시 다음 문제가 감지되었습니다:\n{warning_text}\n\n수정을 적용하려면 충돌을 해결한 후 다시 요청해주세요.",
                    result={"warnings": warnings, "hasConflict": True}
                )

            new_title = updated.get("updatedTitle") or doc.title
            new_tags = updated.get("updatedTags") or doc.tags
            new_category = updated.get("updatedCategory") or doc.category
            new_content = updated.get("updatedContent", doc.content)
            change_desc = updated.get("changeDescription", "문서가 수정되었습니다.")

            write_md_file(
                doc_id=target_id,
                title=new_title,
                content=new_content,
                category=new_category,
                tags=new_tags,
                source=doc.source,
                created=doc.created,
            )

            # ChromaDB 동기화
            try:
                from .embedding.vector_db import get_vector_db
                vector_db = get_vector_db()
                vector_db.add_document(
                    doc_id=target_id,
                    content=new_content,
                    metadata={
                        "title": new_title,
                        "category": new_category,
                        "tags": new_tags,
                        "content_hash": compute_hash(new_content),
                    },
                )
            except Exception as e:
                logger.warning(f"ChromaDB 동기화 실패: {e}")

            return AgentAction(
                type="update",
                target="document",
                targetId=target_id,
                success=True,
                result={
                    "title": new_title,
                    "changeDescription": change_desc,
                    "category": new_category,
                    "tags": new_tags,
                }
            )

        # 문서 생성
        elif intent.action == "create" and target == "document":
            params = intent.parameters
            generated = await generate_document_content(
                user_instruction=original_message,
                title_hint=params.get("title", ""),
                category_hint=params.get("category", ""),
                tags_hint=params.get("tags"),
                content_hint=params.get("contentHint", ""),
            )

            if not generated:
                return AgentAction(
                    type="create", target="document",
                    success=False, error="문서 내용 생성에 실패했습니다."
                )

            doc_title = generated.get("title", params.get("title", "새 문서"))
            doc_category = generated.get("category", params.get("category", ""))
            doc_tags = generated.get("tags", params.get("tags", []))
            doc_content = generated.get("content", "")

            doc_id = generate_doc_id(doc_title)

            write_md_file(
                doc_id=doc_id,
                title=doc_title,
                content=doc_content,
                category=doc_category,
                tags=doc_tags,
                source="ai-assistant",
            )

            # ChromaDB 동기화
            try:
                from .embedding.vector_db import get_vector_db
                vector_db = get_vector_db()
                vector_db.add_document(
                    doc_id=doc_id,
                    content=doc_content,
                    metadata={
                        "title": doc_title,
                        "category": doc_category,
                        "tags": doc_tags,
                        "content_hash": compute_hash(doc_content),
                    },
                )
            except Exception as e:
                logger.warning(f"ChromaDB 동기화 실패: {e}")

            return AgentAction(
                type="create",
                target="document",
                targetId=doc_id,
                success=True,
                result={
                    "docId": doc_id,
                    "title": doc_title,
                    "category": doc_category,
                    "tags": doc_tags,
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
    mode: Optional[str] = None,
    action: Optional[str] = None,
    knowledge_filter: Optional[Dict[str, Any]] = None,
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

    # 3. 의도 감지 (구조화된 모드 우선, fallback으로 LLM)
    intent = resolve_structured_intent(mode, action, content, context_data)
    if intent is None:
        intent = await detect_intent(content, context_data)
    logger.info(f"[INTENT] action={intent.action}, target={intent.target}, params={intent.parameters}, conf={intent.confidence}")

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
        if not data_category and knowledge_filter:
            data_category = knowledge_filter.get("category")

        # LLM이 파라미터를 설정하지 못한 경우 메시지에서 자동 추출
        if not form_query:
            # "업무양식" → "업무양식" 등 '표'/'양식'으로 끝나는 단어 추출
            import re
            form_match = re.search(r'([\w]+(?:표|양식))', content)
            form_query = form_match.group(1) if form_match else "양식"
        if not data_query:
            data_query = content
        if not data_category:
            # 카테고리 미지정 시 빈 값 유지 (전체 카테고리에서 검색)
            pass

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
        # knowledge_filter가 있으면 필터 범위 내 검색
        rag_category = search_category
        if not rag_category and knowledge_filter:
            rag_category = knowledge_filter.get("category")
        knowledge_results = await search_knowledge_base(
            query=content,
            category=rag_category if rag_category else None,
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
