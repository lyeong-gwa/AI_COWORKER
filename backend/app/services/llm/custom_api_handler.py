"""
Custom API LLM Handler (Dify/Agent Builder 호환)

Agent Builder(Dify) 스타일 API를 통한 LLM 질의응답 핸들러

API 형식:
    POST /v1/chat-messages
    Authorization: Bearer {API_KEY}
    {
        "inputs": {},
        "query": "사용자 질문",
        "response_mode": "blocking",
        "conversation_id": "",
        "user": "ai-assistant"
    }

Blocking 응답 형식:
    {
        "event": "message",
        "message_id": "...",
        "conversation_id": "...",
        "answer": "LLM 응답 텍스트",
        "metadata": {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 200,
                "total_tokens": 300
            }
        },
        "created_at": 1234567890
    }

환경변수 설정:
    CUSTOM_API_URL      - API 엔드포인트 URL (예: https://api.example.com/v1/chat-messages)
    CUSTOM_API_KEY      - API 인증 키 (Bearer Token)
    CUSTOM_API_MODEL    - 기본 모델명 (선택, 기본: "default")
    CUSTOM_API_TIMEOUT  - 타임아웃 초 (선택, 기본 60)
"""

from typing import Dict, Any, Optional
import httpx
import logging

from .base import BaseLLMHandler, LLMProvider, LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class CustomAPIHandler(BaseLLMHandler):
    """
    Agent Builder(Dify) 스타일 API 핸들러

    blocking 모드로 순수 LLM 질의응답을 처리합니다.
    """

    provider = LLMProvider.CUSTOM_API
    default_model = "default"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        super().__init__(api_key, base_url)

        from ...core.config import settings

        # settings 객체에서 설정 로드 (.env → pydantic-settings)
        self.base_url = base_url or getattr(settings, 'CUSTOM_API_URL', None)
        self.timeout = getattr(settings, 'CUSTOM_API_TIMEOUT', 60)
        self.default_model = getattr(settings, 'CUSTOM_API_MODEL', None) or "default"

        if not self.base_url:
            raise ValueError(
                "CUSTOM_API_URL 환경변수가 설정되지 않았습니다.\n"
                "API 엔드포인트 URL을 설정해주세요.\n"
                "예: CUSTOM_API_URL=https://api.example.com/v1/chat-messages"
            )

    def _build_request_body(self, request: LLMRequest) -> Dict[str, Any]:
        """
        Dify/Agent Builder API 요청 본문 구성

        내부 messages(system/user/assistant) 형식을
        Dify의 단일 query 문자열로 변환합니다.
        """
        system_prompt = None
        conversation_parts = []

        for msg in request.messages:
            if msg.role == "system":
                system_prompt = msg.content
            elif msg.role == "assistant":
                conversation_parts.append(f"[AI 응답]\n{msg.content}")
            else:
                conversation_parts.append(msg.content)

        # query 구성: system prompt이 있으면 지시사항으로 앞에 추가
        query = "\n\n".join(conversation_parts) if conversation_parts else ""
        if system_prompt:
            query = f"[시스템 지시]\n{system_prompt}\n\n[사용자 질문]\n{query}"

        body = {
            "inputs": {},
            "query": query,
            "response_mode": "blocking",
            "conversation_id": "",
            "user": "ai-assistant",
        }

        return body

    async def _call_api(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dify/Agent Builder API 호출

        Bearer Token 인증으로 POST 요청을 보냅니다.
        """
        api_key = self._get_api_key()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        logger.info(f"Custom API 호출: {self.base_url}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.base_url,
                headers=headers,
                json=body,
            )

            if response.status_code != 200:
                error_detail = response.text
                raise RuntimeError(
                    f"Custom API 오류 ({response.status_code}): {error_detail}"
                )

            return response.json()

    def _parse_response(self, raw_response: Dict[str, Any]) -> LLMResponse:
        """
        Dify/Agent Builder blocking 응답 파싱

        'answer' 필드에서 LLM 응답 텍스트를 추출하고,
        'metadata.usage'에서 토큰 사용량을 추출합니다.
        """
        # 응답 텍스트 추출
        content = raw_response.get("answer", "")
        if not content:
            raise ValueError(
                f"API 응답에 'answer' 필드가 없습니다.\n"
                f"응답 키: {list(raw_response.keys())}"
            )

        # 토큰 사용량 (metadata.usage에서 추출)
        metadata = raw_response.get("metadata", {})
        usage = metadata.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

        return LLMResponse(
            content=content,
            model=self.default_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            finish_reason="stop",
        )
