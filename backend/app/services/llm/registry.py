"""
LLM Handler Registry

핸들러 등록 및 선택 관리
환경변수 기반 프로바이더 자동 선택
"""

from typing import Dict, Type, Optional
import os
import logging

from .base import BaseLLMHandler, LLMProvider

logger = logging.getLogger(__name__)


class LLMRegistry:
    """
    LLM 핸들러 레지스트리

    핸들러 등록, 조회, 환경변수 기반 자동 선택을 관리합니다.
    """

    _handlers: Dict[str, Type[BaseLLMHandler]] = {}
    _instances: Dict[str, BaseLLMHandler] = {}

    @classmethod
    def register(cls, provider: str, handler_class: Type[BaseLLMHandler]) -> None:
        """
        핸들러 등록

        Args:
            provider: 프로바이더 이름 (예: "openai", "anthropic", "custom_api")
            handler_class: 핸들러 클래스
        """
        cls._handlers[provider.lower()] = handler_class

    @classmethod
    def get(
        cls,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        use_cache: bool = True,
    ) -> BaseLLMHandler:
        """
        핸들러 인스턴스 가져오기

        Args:
            provider: 프로바이더 이름 (None이면 환경변수에서 결정)
            api_key: API 키 (선택)
            base_url: 베이스 URL (선택)
            use_cache: 캐시된 인스턴스 사용 여부

        Returns:
            LLM 핸들러 인스턴스
        """
        # EXTERNAL_LLM 자동 감지 (OpenAI 호환 우회 시스템)
        # 명시적 api_key/base_url이 없을 때만 적용
        if api_key is None and base_url is None:
            external_llm = os.getenv("EXTERNAL_LLM") or ""
            if external_llm and external_llm.lower() not in ("", "false", "openai"):
                ext_key = os.getenv("EXTERNAL_LLM_API_KEY")
                ext_url = os.getenv("EXTERNAL_LLM_API_URL")
                if ext_key and ext_url:
                    if provider is None or provider.lower() == "openai":
                        api_key = ext_key
                        base_url = ext_url
                        provider = "openai"  # OpenAI 호환 핸들러 사용
                        logger.info(
                            f"EXTERNAL_LLM 활성: {ext_url} (OpenAI 호환 모드)"
                        )

        # 프로바이더 결정
        if provider is None:
            provider = cls._get_default_provider()

        provider = provider.lower()

        # 캐시 확인
        cache_key = f"{provider}:{api_key or ''}:{base_url or ''}"
        if use_cache and cache_key in cls._instances:
            return cls._instances[cache_key]

        # 핸들러 클래스 조회
        if provider not in cls._handlers:
            available = list(cls._handlers.keys())
            raise ValueError(
                f"알 수 없는 LLM 프로바이더: {provider}\n"
                f"사용 가능한 프로바이더: {available}"
            )

        handler_class = cls._handlers[provider]

        # 인스턴스 생성
        instance = handler_class(api_key=api_key, base_url=base_url)

        # 캐시 저장
        if use_cache:
            cls._instances[cache_key] = instance

        return instance

    @classmethod
    def _get_default_provider(cls) -> str:
        """환경변수에서 기본 프로바이더 결정"""
        from ...core.config import settings

        # 1. 명시적 설정 확인
        default = getattr(settings, 'DEFAULT_LLM_PROVIDER', None)
        if default:
            return default

        # 2. EXTERNAL_LLM 플래그 확인 (우회 시스템)
        external_llm = os.getenv('EXTERNAL_LLM') or ""
        if external_llm and external_llm.lower() not in ("", "false", "openai"):
            if os.getenv('EXTERNAL_LLM_API_KEY') and os.getenv('EXTERNAL_LLM_API_URL'):
                return 'openai'  # OpenAI 호환 (base_url은 get()에서 처리)

        # 3. API 키 존재 여부로 자동 결정 (우선순위 순)
        if os.getenv('CUSTOM_API_URL') and os.getenv('CUSTOM_API_KEY'):
            return 'custom_api'
        elif os.getenv('AZURE_OPENAI_ENDPOINT') and os.getenv('AZURE_OPENAI_API_KEY'):
            return 'azure'
        elif os.getenv('OPENAI_API_KEY') or getattr(settings, 'OPENAI_API_KEY', None):
            return 'openai'
        elif os.getenv('ANTHROPIC_API_KEY') or getattr(settings, 'ANTHROPIC_API_KEY', None):
            return 'anthropic'

        raise ValueError(
            "사용 가능한 LLM 프로바이더가 없습니다.\n"
            "환경변수를 설정하세요:\n"
            "- OPENAI_API_KEY (OpenAI)\n"
            "- AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY (Azure)\n"
            "- ANTHROPIC_API_KEY (Anthropic)\n"
            "- CUSTOM_API_URL + CUSTOM_API_KEY (타 시스템)\n"
            "- EXTERNAL_LLM + EXTERNAL_LLM_API_KEY + EXTERNAL_LLM_API_URL (우회 LLM)"
        )

    @classmethod
    def list_providers(cls) -> list:
        """등록된 프로바이더 목록"""
        return list(cls._handlers.keys())

    @classmethod
    def clear_cache(cls) -> None:
        """인스턴스 캐시 초기화"""
        cls._instances.clear()


# ─────────────────────────────────────────────────────────────────────────────
# 핸들러 자동 등록
# ─────────────────────────────────────────────────────────────────────────────

def _register_handlers():
    """기본 핸들러들 등록"""
    from .openai_handler import OpenAIHandler
    from .azure_handler import AzureOpenAIHandler
    from .anthropic_handler import AnthropicHandler
    from .custom_api_handler import CustomAPIHandler

    LLMRegistry.register("openai", OpenAIHandler)
    LLMRegistry.register("azure", AzureOpenAIHandler)
    LLMRegistry.register("anthropic", AnthropicHandler)
    LLMRegistry.register("custom_api", CustomAPIHandler)


# 모듈 로드시 자동 등록
_register_handlers()


# ─────────────────────────────────────────────────────────────────────────────
# 편의 함수
# ─────────────────────────────────────────────────────────────────────────────

def get_llm_handler(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> BaseLLMHandler:
    """
    LLM 핸들러 가져오기 (편의 함수)

    Args:
        provider: 프로바이더 이름 ("openai", "anthropic", "custom_api")
                  None이면 환경변수 기반 자동 선택
        api_key: API 키 (선택)
        base_url: 커스텀 엔드포인트 URL (선택)

    Returns:
        LLM 핸들러 인스턴스

    Example:
        # 환경변수 기반 자동 선택
        handler = get_llm_handler()

        # 명시적 프로바이더 지정
        handler = get_llm_handler("openai")

        # 커스텀 API 사용
        handler = get_llm_handler("custom_api")

        # 채팅 요청
        response = await handler.simple_chat("안녕하세요")
        print(response.content)
    """
    return LLMRegistry.get(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
    )


async def chat(
    prompt: str,
    system_prompt: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2000,
):
    """
    간단한 채팅 함수 (편의 함수)

    Args:
        prompt: 사용자 프롬프트
        system_prompt: 시스템 프롬프트 (선택)
        provider: LLM 프로바이더 (선택)
        model: 모델명 (선택)
        temperature: 온도 (0~2)
        max_tokens: 최대 토큰

    Returns:
        LLMResponse

    Example:
        response = await chat("오늘 날씨 어때?")
        print(response.content)
    """
    handler = get_llm_handler(provider)
    return await handler.simple_chat(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
