"""
Custom API LLM Handler

타 시스템 API를 통한 LLM 질의응답 핸들러

═══════════════════════════════════════════════════════════════════════════════
                            구현 가이드
═══════════════════════════════════════════════════════════════════════════════

타 시스템 API 양식이 확정되면 아래 3개 메서드만 수정하면 됩니다:

1. _build_request_body() - API 요청 본문 구성
   - 타 시스템 API가 요구하는 형식에 맞게 요청 데이터 구성

2. _call_api() - API 호출
   - 엔드포인트 URL, 헤더, 인증 방식 설정

3. _parse_response() - 응답 파싱
   - 타 시스템 응답을 표준 LLMResponse로 변환

═══════════════════════════════════════════════════════════════════════════════

환경변수 설정:
    CUSTOM_API_URL      - API 엔드포인트 URL
    CUSTOM_API_KEY      - API 인증 키
    CUSTOM_API_MODEL    - 기본 모델명 (선택)
    CUSTOM_API_TIMEOUT  - 타임아웃 초 (선택, 기본 60)
"""

from typing import Dict, Any, Optional
import httpx
import os

from .base import BaseLLMHandler, LLMProvider, LLMRequest, LLMResponse


class CustomAPIHandler(BaseLLMHandler):
    """
    타 시스템 API 핸들러

    API 양식 확정 후 아래 메서드들을 수정하세요.
    """

    provider = LLMProvider.CUSTOM_API
    default_model = os.getenv("CUSTOM_API_MODEL", "default")

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        super().__init__(api_key, base_url)

        # 환경변수에서 설정 로드
        self.base_url = base_url or os.getenv("CUSTOM_API_URL")
        self.timeout = int(os.getenv("CUSTOM_API_TIMEOUT", "60"))

        if not self.base_url:
            raise ValueError(
                "CUSTOM_API_URL 환경변수가 설정되지 않았습니다.\n"
                "타 시스템 API URL을 설정해주세요."
            )

    # ═══════════════════════════════════════════════════════════════════════════
    #                    아래 메서드들을 API 양식에 맞게 수정하세요
    # ═══════════════════════════════════════════════════════════════════════════

    def _build_request_body(self, request: LLMRequest) -> Dict[str, Any]:
        """
        ┌─────────────────────────────────────────────────────────────────────┐
        │  API 요청 본문 구성                                                   │
        │                                                                     │
        │  타 시스템 API 양식에 맞게 이 메서드를 수정하세요.                       │
        │                                                                     │
        │  현재는 일반적인 형식으로 구현되어 있습니다.                             │
        │  실제 API 문서를 확인하고 필드명과 구조를 맞춰주세요.                     │
        └─────────────────────────────────────────────────────────────────────┘
        """
        # 메시지 변환
        messages = []
        system_prompt = None

        for msg in request.messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        # ───────────────────────────────────────────────────────────────────────
        # TODO: 타 시스템 API 양식에 맞게 아래 body 구조를 수정하세요
        # ───────────────────────────────────────────────────────────────────────
        body = {
            # 예시 필드들 - 실제 API 스펙에 맞게 변경
            "model": request.model or self.default_model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        if system_prompt:
            body["system"] = system_prompt  # 또는 API가 요구하는 필드명

        # extra 파라미터 (API별 추가 설정)
        if request.extra:
            body.update(request.extra)

        return body

    async def _call_api(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        ┌─────────────────────────────────────────────────────────────────────┐
        │  API 호출                                                           │
        │                                                                     │
        │  타 시스템 API의 인증 방식과 헤더를 맞춰주세요.                         │
        │                                                                     │
        │  일반적인 인증 방식:                                                  │
        │  - Bearer Token: Authorization: Bearer {token}                      │
        │  - API Key: X-API-Key: {key} 또는 api_key 파라미터                   │
        │  - Basic Auth: Authorization: Basic {base64}                        │
        └─────────────────────────────────────────────────────────────────────┘
        """
        api_key = self._get_api_key()

        # ───────────────────────────────────────────────────────────────────────
        # TODO: 타 시스템 API 인증 방식에 맞게 헤더를 수정하세요
        # ───────────────────────────────────────────────────────────────────────
        headers = {
            "Content-Type": "application/json",
            # 인증 헤더 (아래 중 하나 선택하거나 API 스펙에 맞게 수정)
            "Authorization": f"Bearer {api_key}",
            # "X-API-Key": api_key,
        }

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
        ┌─────────────────────────────────────────────────────────────────────┐
        │  응답 파싱                                                           │
        │                                                                     │
        │  타 시스템 API 응답 구조에 맞게 파싱 로직을 수정하세요.                  │
        │                                                                     │
        │  필수로 추출해야 할 데이터:                                            │
        │  - content: LLM 응답 텍스트                                          │
        │  - model: 사용된 모델명                                               │
        │                                                                     │
        │  선택적 데이터:                                                       │
        │  - prompt_tokens, completion_tokens: 토큰 사용량                      │
        │  - finish_reason: 종료 이유                                          │
        └─────────────────────────────────────────────────────────────────────┘
        """
        # ───────────────────────────────────────────────────────────────────────
        # TODO: 타 시스템 API 응답 구조에 맞게 수정하세요
        # ───────────────────────────────────────────────────────────────────────

        # 예시 1: OpenAI 호환 형식
        # content = raw_response["choices"][0]["message"]["content"]

        # 예시 2: 간단한 형식
        # content = raw_response["response"]
        # content = raw_response["result"]["text"]

        # 예시 3: 중첩된 형식
        # content = raw_response["data"]["output"]["text"]

        # 현재 구현 (일반적인 형식 - 실제 API에 맞게 수정 필요)
        content = self._extract_content(raw_response)
        model = raw_response.get("model", self.default_model)

        # 토큰 사용량 (API가 제공하는 경우)
        usage = raw_response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)

        return LLMResponse(
            content=content,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            finish_reason=raw_response.get("finish_reason") or raw_response.get("stop_reason"),
        )

    def _extract_content(self, raw_response: Dict[str, Any]) -> str:
        """
        응답에서 콘텐츠 추출 (여러 형식 시도)

        API 양식 확정 후 이 메서드를 간소화하거나
        _parse_response에서 직접 추출하세요.
        """
        # 시도할 경로들 (우선순위 순)
        content_paths = [
            # OpenAI 호환
            lambda r: r["choices"][0]["message"]["content"],
            # Anthropic 호환
            lambda r: r["content"][0]["text"],
            # 간단한 형식
            lambda r: r["response"],
            lambda r: r["result"],
            lambda r: r["text"],
            lambda r: r["output"],
            # 중첩 형식
            lambda r: r["data"]["response"],
            lambda r: r["data"]["text"],
            lambda r: r["result"]["text"],
            lambda r: r["result"]["content"],
        ]

        for extract in content_paths:
            try:
                content = extract(raw_response)
                if content and isinstance(content, str):
                    return content
            except (KeyError, IndexError, TypeError):
                continue

        # 모든 시도 실패시 전체 응답을 문자열로
        raise ValueError(
            f"응답에서 콘텐츠를 추출할 수 없습니다. "
            f"_parse_response 메서드를 API 양식에 맞게 수정하세요.\n"
            f"응답 구조: {list(raw_response.keys())}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
#                           사용 예시
# ═══════════════════════════════════════════════════════════════════════════════
#
# 1. 환경변수 설정:
#    CUSTOM_API_URL=https://your-system.com/api/llm/chat
#    CUSTOM_API_KEY=your-api-key
#
# 2. 코드에서 사용:
#    from app.services.llm import get_llm_handler
#
#    handler = get_llm_handler("custom_api")
#    response = await handler.simple_chat(
#        prompt="안녕하세요",
#        system_prompt="친절하게 답변하세요",
#    )
#    print(response.content)
#
# ═══════════════════════════════════════════════════════════════════════════════
