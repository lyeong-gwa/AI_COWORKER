"""
LLM Client Service (레거시 호환)

이 모듈은 기존 코드와의 호환성을 위해 유지됩니다.
새 코드는 app.services.llm 모듈을 직접 사용하세요.

Example:
    # 새로운 방식 (권장)
    from app.services.llm import get_llm_handler, chat

    handler = get_llm_handler()
    response = await handler.simple_chat("안녕하세요")

    # 또는 간단히
    response = await chat("안녕하세요", provider="openai")

    # 레거시 방식 (호환성 유지)
    from app.services.llm_client import call_llm

    response, usage = await call_llm("안녕하세요", provider="openai")
"""

from typing import Dict, Tuple, Optional

from .llm import get_llm_handler, LLMRequest, LLMMessage


async def call_llm(
    prompt: str,
    provider: str = "openai",
    model: str = "gpt-4o-mini",
    temperature: float = 0.7,
    max_tokens: int = 2000,
    system_prompt: Optional[str] = None,
) -> Tuple[str, Dict[str, int]]:
    """
    LLM API 호출 (레거시 호환 함수)

    새 코드는 app.services.llm 모듈을 사용하세요.

    Args:
        prompt: 사용자 프롬프트
        provider: 프로바이더 (openai, anthropic, custom_api)
        model: 모델명
        temperature: 온도
        max_tokens: 최대 토큰
        system_prompt: 시스템 프롬프트

    Returns:
        Tuple[str, Dict]: (응답 텍스트, 토큰 사용량)
    """
    handler = get_llm_handler(provider)

    response = await handler.simple_chat(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    return response.content, response.token_usage
