"""
Chat API Schemas

채팅 에이전트 API 요청/응답 스키마
프론트엔드 ChatContext 타입과 호환
"""

from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# Context Types (프론트엔드 ChatContextType과 매칭)
# ─────────────────────────────────────────────────────────────────────────────

class ChatContextBase(BaseModel):
    """선택된 요소 컨텍스트 (프론트엔드에서 전달)"""
    type: Literal['none', 'task', 'tool', 'node', 'workflow', 'document']
    id: Optional[str] = None  # type이 'none'이 아닐 때 요소 ID


# ─────────────────────────────────────────────────────────────────────────────
# Request Schemas
# ─────────────────────────────────────────────────────────────────────────────

class ChatMessageRequest(BaseModel):
    """채팅 메시지 요청"""
    content: str = Field(..., min_length=1, max_length=4000, description="사용자 메시지")
    context: Optional[ChatContextBase] = Field(
        default=None,
        description="선택된 요소 컨텍스트 (task, tool, node, workflow, document)"
    )
    sessionId: Optional[str] = Field(
        default=None,
        description="세션 ID (없으면 새 세션 생성)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "content": "이 태스크의 상태를 '진행 중'으로 변경해줘",
                "context": {
                    "type": "task",
                    "id": "task-123"
                },
                "sessionId": "session-abc"
            }
        }


# ─────────────────────────────────────────────────────────────────────────────
# Response Schemas
# ─────────────────────────────────────────────────────────────────────────────

class AgentAction(BaseModel):
    """에이전트가 수행한 작업 결과"""
    type: Literal['explain', 'view', 'create', 'update', 'delete', 'execute', 'search']
    target: str = Field(..., description="작업 대상 (예: 'task', 'workflow')")
    targetId: Optional[str] = Field(None, description="작업 대상 ID")
    success: bool = Field(True, description="작업 성공 여부")
    result: Optional[Dict[str, Any]] = Field(None, description="작업 결과 데이터")
    error: Optional[str] = Field(None, description="에러 메시지")


class ChatMessageResponse(BaseModel):
    """채팅 응답"""
    id: str = Field(..., description="메시지 ID")
    role: Literal['assistant'] = 'assistant'
    content: str = Field(..., description="AI 응답 메시지")
    timestamp: str = Field(..., description="응답 시간 (ISO 8601)")

    # 에이전트 작업 결과 (선택적)
    action: Optional[AgentAction] = Field(
        None,
        description="에이전트가 수행한 작업 (있는 경우)"
    )

    # 세션 정보
    sessionId: str = Field(..., description="세션 ID")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "msg-456",
                "role": "assistant",
                "content": "네, 'API 연동 작업' 태스크를 '진행 중' 상태로 변경했습니다.",
                "timestamp": "2024-01-15T10:30:00Z",
                "action": {
                    "type": "update",
                    "target": "task",
                    "targetId": "task-123",
                    "success": True,
                    "result": {"status": "in-progress"}
                },
                "sessionId": "session-abc"
            }
        }


# ─────────────────────────────────────────────────────────────────────────────
# Session Schemas
# ─────────────────────────────────────────────────────────────────────────────

class ChatSession(BaseModel):
    """채팅 세션 정보"""
    id: str
    createdAt: str
    lastMessageAt: str
    messageCount: int


class ChatHistoryResponse(BaseModel):
    """채팅 히스토리 응답"""
    sessionId: str
    messages: List[Dict[str, Any]]  # ChatMessage 형식
    totalCount: int


# ─────────────────────────────────────────────────────────────────────────────
# Intent Detection (내부용)
# ─────────────────────────────────────────────────────────────────────────────

class DetectedIntent(BaseModel):
    """감지된 사용자 의도 (내부용)"""
    action: Literal['explain', 'view', 'create', 'update', 'delete', 'execute', 'search', 'chat']
    target: Optional[str] = None  # task, tool, node, workflow, document
    parameters: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(0.0, ge=0, le=1)
