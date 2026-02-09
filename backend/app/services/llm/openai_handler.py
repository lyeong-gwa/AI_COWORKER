"""
OpenAI LLM Handler

OpenAI Chat Completions API 핸들러
"""

from typing import Dict, Any
import httpx

from .base import BaseLLMHandler, LLMProvider, LLMRequest, LLMResponse


class OpenAIHandler(BaseLLMHandler):
    """
    OpenAI API 핸들러

    지원 모델:
    - gpt-4o, gpt-4o-mini
    - gpt-4-turbo, gpt-4
    - gpt-3.5-turbo
    """

    provider = LLMProvider.OPENAI
    default_model = "gpt-4o-mini"

    API_URL = "https://api.openai.com/v1/chat/completions"

    def _build_request_body(self, request: LLMRequest) -> Dict[str, Any]:
        """OpenAI API 요청 본문 구성"""
        body = {
            "model": request.model,
            "messages": [
                {"role": msg.role, "content": msg.content}
                for msg in request.messages
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        # 선택적 파라미터
        if request.top_p is not None:
            body["top_p"] = request.top_p
        if request.frequency_penalty is not None:
            body["frequency_penalty"] = request.frequency_penalty
        if request.presence_penalty is not None:
            body["presence_penalty"] = request.presence_penalty
        if request.stop:
            body["stop"] = request.stop

        # extra 파라미터 (response_format 등)
        if request.extra:
            body.update(request.extra)

        return body

    async def _call_api(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """OpenAI API 호출"""
        api_key = self._get_api_key()
        url = self.base_url or self.API_URL

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )

            if response.status_code != 200:
                error_detail = response.text
                raise RuntimeError(f"OpenAI API 오류 ({response.status_code}): {error_detail}")

            return response.json()

    def _parse_response(self, raw_response: Dict[str, Any]) -> LLMResponse:
        """OpenAI 응답 파싱"""
        choice = raw_response["choices"][0]
        usage = raw_response.get("usage", {})

        return LLMResponse(
            content=choice["message"]["content"],
            model=raw_response.get("model", ""),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            finish_reason=choice.get("finish_reason"),
        )
