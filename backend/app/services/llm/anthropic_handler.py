"""
Anthropic LLM Handler

Anthropic Messages API 핸들러
"""

from typing import Dict, Any
import httpx

from .base import BaseLLMHandler, LLMProvider, LLMRequest, LLMResponse


class AnthropicHandler(BaseLLMHandler):
    """
    Anthropic API 핸들러

    지원 모델:
    - claude-3-5-sonnet-20241022
    - claude-3-opus-20240229
    - claude-3-sonnet-20240229
    - claude-3-haiku-20240307
    """

    provider = LLMProvider.ANTHROPIC
    default_model = "claude-3-5-sonnet-20241022"

    API_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def _build_request_body(self, request: LLMRequest) -> Dict[str, Any]:
        """Anthropic API 요청 본문 구성"""
        # 시스템 메시지 분리 (Anthropic은 별도 필드)
        system_content = None
        messages = []

        for msg in request.messages:
            if msg.role == "system":
                system_content = msg.content
            else:
                messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        body = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens,
        }

        # 시스템 프롬프트
        if system_content:
            body["system"] = system_content

        # temperature (Anthropic은 0~1 범위)
        if request.temperature is not None:
            body["temperature"] = min(request.temperature, 1.0)

        # 선택적 파라미터
        if request.top_p is not None:
            body["top_p"] = request.top_p
        if request.stop:
            body["stop_sequences"] = request.stop

        # extra 파라미터
        if request.extra:
            body.update(request.extra)

        return body

    async def _call_api(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Anthropic API 호출"""
        api_key = self._get_api_key()
        url = self.base_url or self.API_URL

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                url,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": self.API_VERSION,
                    "Content-Type": "application/json",
                },
                json=body,
            )

            if response.status_code != 200:
                error_detail = response.text
                raise RuntimeError(f"Anthropic API 오류 ({response.status_code}): {error_detail}")

            return response.json()

    def _parse_response(self, raw_response: Dict[str, Any]) -> LLMResponse:
        """Anthropic 응답 파싱"""
        content_blocks = raw_response.get("content", [])
        content = ""

        for block in content_blocks:
            if block.get("type") == "text":
                content += block.get("text", "")

        usage = raw_response.get("usage", {})

        return LLMResponse(
            content=content,
            model=raw_response.get("model", ""),
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            finish_reason=raw_response.get("stop_reason"),
        )
