"""
Azure AI Foundry LLM Handler

Azure OpenAI Service 핸들러
"""

from typing import Dict, Any, Optional
import httpx
import os

from .base import BaseLLMHandler, LLMProvider, LLMRequest, LLMResponse


class AzureOpenAIHandler(BaseLLMHandler):
    """
    Azure OpenAI Service 핸들러

    Azure AI Foundry를 통한 OpenAI 모델 사용

    환경변수:
        AZURE_OPENAI_ENDPOINT: Azure OpenAI 엔드포인트
        AZURE_OPENAI_API_KEY: API 키
        AZURE_OPENAI_DEPLOYMENT: 배포명 (모델명 대신 사용)
        AZURE_OPENAI_API_VERSION: API 버전 (기본: 2024-02-15-preview)
    """

    provider = LLMProvider.OPENAI  # OpenAI 호환
    default_model = "gpt-4o-mini"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        deployment: Optional[str] = None,
        api_version: Optional[str] = None,
    ):
        super().__init__(api_key, base_url)

        # Azure 설정 로드
        self.endpoint = base_url or os.getenv("AZURE_OPENAI_ENDPOINT")
        self.deployment = deployment or os.getenv("AZURE_OPENAI_DEPLOYMENT")
        self.api_version = api_version or os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

        if not self.endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT가 설정되지 않았습니다")
        if not self.deployment:
            raise ValueError("AZURE_OPENAI_DEPLOYMENT가 설정되지 않았습니다")

    def _get_api_key(self) -> str:
        """Azure API 키 가져오기"""
        if self.api_key:
            return self.api_key

        key = os.getenv("AZURE_OPENAI_API_KEY")
        if not key:
            raise ValueError("AZURE_OPENAI_API_KEY가 설정되지 않았습니다")
        return key

    def _build_request_body(self, request: LLMRequest) -> Dict[str, Any]:
        """Azure OpenAI API 요청 본문 구성"""
        body = {
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

        # extra 파라미터
        if request.extra:
            body.update(request.extra)

        return body

    async def _call_api(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Azure OpenAI API 호출"""
        api_key = self._get_api_key()

        # Azure 엔드포인트 URL 구성
        url = (
            f"{self.endpoint.rstrip('/')}/openai/deployments/{self.deployment}"
            f"/chat/completions?api-version={self.api_version}"
        )

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                url,
                headers={
                    "api-key": api_key,
                    "Content-Type": "application/json",
                },
                json=body,
            )

            if response.status_code != 200:
                error_detail = response.text
                raise RuntimeError(f"Azure OpenAI API 오류 ({response.status_code}): {error_detail}")

            return response.json()

    def _parse_response(self, raw_response: Dict[str, Any]) -> LLMResponse:
        """Azure OpenAI 응답 파싱 (OpenAI와 동일)"""
        choice = raw_response["choices"][0]
        usage = raw_response.get("usage", {})

        return LLMResponse(
            content=choice["message"]["content"],
            model=raw_response.get("model", self.deployment),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            finish_reason=choice.get("finish_reason"),
        )
