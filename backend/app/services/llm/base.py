"""
LLM Base Handler

모든 LLM 핸들러가 상속받는 추상 베이스 클래스
새로운 LLM 프로바이더 추가시 이 클래스를 상속받아 구현
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum


class LLMProvider(str, Enum):
    """지원하는 LLM 프로바이더"""
    OPENAI = "openai"
    AZURE = "azure"  # Azure OpenAI Service
    ANTHROPIC = "anthropic"
    CUSTOM_API = "custom_api"  # 타 시스템 API


@dataclass
class LLMMessage:
    """메시지 구조"""
    role: str  # system, user, assistant
    content: str


@dataclass
class LLMRequest:
    """LLM 요청 구조"""
    messages: List[LLMMessage]
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2000

    # 선택적 파라미터
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    stop: Optional[List[str]] = None

    # 메타데이터 (핸들러별 추가 설정)
    extra: Dict[str, Any] = field(default_factory=dict)

    # 로깅용 호출 유형 태그
    call_type: str = "unknown"

    @classmethod
    def simple(
        cls,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> "LLMRequest":
        """간단한 요청 생성 헬퍼"""
        messages = []
        if system_prompt:
            messages.append(LLMMessage(role="system", content=system_prompt))
        messages.append(LLMMessage(role="user", content=prompt))
        return cls(messages=messages, **kwargs)


@dataclass
class LLMResponse:
    """LLM 응답 구조"""
    content: str
    model: str

    # 토큰 사용량
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    # 메타데이터
    finish_reason: Optional[str] = None
    latency_ms: float = 0
    raw_response: Optional[Dict[str, Any]] = None

    @property
    def token_usage(self) -> Dict[str, int]:
        """토큰 사용량 딕셔너리"""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


class BaseLLMHandler(ABC):
    """
    LLM 핸들러 추상 베이스 클래스

    새로운 LLM 프로바이더를 추가하려면:
    1. 이 클래스를 상속받는 새 핸들러 클래스 생성
    2. _call_api() 메서드 구현 (필수)
    3. _build_request_body() 메서드 구현 (필수)
    4. _parse_response() 메서드 구현 (필수)
    5. LLMRegistry에 핸들러 등록

    Example:
        class MyCustomHandler(BaseLLMHandler):
            provider = LLMProvider.CUSTOM_API

            def _build_request_body(self, request: LLMRequest) -> Dict:
                # API 요청 본문 구성
                return {...}

            async def _call_api(self, body: Dict) -> Dict:
                # 실제 API 호출
                response = await httpx.post(...)
                return response.json()

            def _parse_response(self, raw: Dict) -> LLMResponse:
                # 응답 파싱
                return LLMResponse(content=raw['result'], ...)
    """

    # 서브클래스에서 오버라이드
    provider: LLMProvider = None
    default_model: str = None

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        Args:
            api_key: API 키 (없으면 환경변수에서 가져옴)
            base_url: API 베이스 URL (커스텀 엔드포인트용)
        """
        self.api_key = api_key
        self.base_url = base_url

    async def chat(self, request: LLMRequest) -> LLMResponse:
        """
        LLM 채팅 요청 실행

        이 메서드는 템플릿 메서드 패턴을 따름:
        1. 요청 본문 구성 (_build_request_body)
        2. API 호출 (_call_api)
        3. 응답 파싱 (_parse_response)
        4. 호출 로그 저장 (1질의 1로그파일)
        """
        import time
        from .llm_logger import save_llm_log

        # 모델 기본값 설정
        if not request.model:
            request.model = self.default_model

        # 로깅용 메시지 준비
        log_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in request.messages
        ]
        log_extra = {}
        if request.top_p is not None:
            log_extra["top_p"] = request.top_p
        if request.frequency_penalty is not None:
            log_extra["frequency_penalty"] = request.frequency_penalty
        if request.presence_penalty is not None:
            log_extra["presence_penalty"] = request.presence_penalty
        if request.stop:
            log_extra["stop"] = request.stop

        start_time = time.perf_counter()
        error_msg = None

        try:
            # 1. 요청 본문 구성
            body = self._build_request_body(request)

            # 2. API 호출
            raw_response = await self._call_api(body)

            # 3. 응답 파싱
            response = self._parse_response(raw_response)

            # 레이턴시 기록
            response.latency_ms = (time.perf_counter() - start_time) * 1000
            response.raw_response = raw_response

            # 4. 성공 로그 저장
            save_llm_log(
                call_type=request.call_type,
                provider=self.provider.value if self.provider else "unknown",
                model=request.model or "",
                messages=log_messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                response_content=response.content,
                finish_reason=response.finish_reason,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.total_tokens,
                latency_ms=response.latency_ms,
                extra_params=log_extra if log_extra else None,
            )

            return response

        except Exception as e:
            # 실패 로그 저장
            latency = (time.perf_counter() - start_time) * 1000
            save_llm_log(
                call_type=request.call_type,
                provider=self.provider.value if self.provider else "unknown",
                model=request.model or "",
                messages=log_messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                latency_ms=latency,
                error=str(e),
                extra_params=log_extra if log_extra else None,
            )
            raise

    async def simple_chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        call_type: str = "unknown",
    ) -> LLMResponse:
        """간단한 채팅 헬퍼"""
        request = LLMRequest.simple(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        request.call_type = call_type
        return await self.chat(request)

    @abstractmethod
    def _build_request_body(self, request: LLMRequest) -> Dict[str, Any]:
        """
        API 요청 본문 구성

        각 프로바이더의 API 형식에 맞게 요청 본문을 구성합니다.

        Args:
            request: LLM 요청 객체

        Returns:
            API 요청 본문 딕셔너리
        """
        pass

    @abstractmethod
    async def _call_api(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        실제 API 호출

        HTTP 요청을 보내고 응답을 반환합니다.

        Args:
            body: API 요청 본문

        Returns:
            API 응답 딕셔너리 (raw)
        """
        pass

    @abstractmethod
    def _parse_response(self, raw_response: Dict[str, Any]) -> LLMResponse:
        """
        API 응답 파싱

        프로바이더별 응답 형식을 표준 LLMResponse로 변환합니다.

        Args:
            raw_response: API 원본 응답

        Returns:
            표준화된 LLMResponse 객체
        """
        pass

    def _get_api_key(self) -> str:
        """API 키 가져오기 (인스턴스 변수 또는 환경변수)"""
        if self.api_key:
            return self.api_key

        from ...core.config import settings

        if self.provider == LLMProvider.OPENAI:
            key = settings.OPENAI_API_KEY
        elif self.provider == LLMProvider.ANTHROPIC:
            key = settings.ANTHROPIC_API_KEY
        elif self.provider == LLMProvider.CUSTOM_API:
            key = getattr(settings, 'CUSTOM_API_KEY', None)
        else:
            key = None

        if not key:
            raise ValueError(f"{self.provider.value} API 키가 설정되지 않았습니다")

        return key
