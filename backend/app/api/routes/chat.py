"""
Chat API Routes

AI 어시스턴트 채팅 API 엔드포인트
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...schemas.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    ChatHistoryResponse,
    ChatSession,
)
from ...services.agent_service import (
    process_chat_message,
    get_or_create_session,
    get_session_messages,
    _sessions,
)

router = APIRouter()


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    request: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    채팅 메시지 전송

    사용자 메시지를 받아 AI 응답을 반환합니다.
    컨텍스트(선택된 요소)가 있으면 해당 요소에 대한 작업을 수행할 수 있습니다.

    - **content**: 사용자 메시지
    - **context**: 선택된 요소 정보 (type, id)
    - **sessionId**: 세션 ID (대화 히스토리 유지용)
    """
    try:
        response = await process_chat_message(
            db=db,
            content=request.content,
            context=request.context,
            session_id=request.sessionId,
            mode=request.mode,
            action=request.action,
            knowledge_filter=request.knowledgeFilter,
        )
        return response

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"메시지 처리 중 오류 발생: {str(e)}"
        )


@router.get("/session/{session_id}", response_model=ChatHistoryResponse)
async def get_chat_history(session_id: str):
    """
    채팅 히스토리 조회

    특정 세션의 대화 히스토리를 반환합니다.
    """
    messages = get_session_messages(session_id)

    if not messages:
        raise HTTPException(
            status_code=404,
            detail="세션을 찾을 수 없습니다"
        )

    return ChatHistoryResponse(
        sessionId=session_id,
        messages=messages,
        totalCount=len(messages),
    )


@router.get("/sessions", response_model=List[ChatSession])
async def list_sessions():
    """
    활성 세션 목록 조회

    현재 활성화된 채팅 세션 목록을 반환합니다.
    """
    sessions = []
    for session_id, messages in _sessions.items():
        if messages:
            sessions.append(ChatSession(
                id=session_id,
                createdAt=messages[0]["timestamp"] if messages else "",
                lastMessageAt=messages[-1]["timestamp"] if messages else "",
                messageCount=len(messages),
            ))

    return sessions


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """
    세션 삭제

    특정 세션을 삭제합니다.
    """
    if session_id in _sessions:
        del _sessions[session_id]
        return {"message": "세션이 삭제되었습니다", "sessionId": session_id}

    raise HTTPException(
        status_code=404,
        detail="세션을 찾을 수 없습니다"
    )


@router.post("/session")
async def create_session():
    """
    새 세션 생성

    새로운 채팅 세션을 생성하고 ID를 반환합니다.
    """
    session_id = get_or_create_session()
    return {
        "sessionId": session_id,
        "message": "새 세션이 생성되었습니다"
    }
