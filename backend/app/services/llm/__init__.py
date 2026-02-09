"""
LLM Service Module

핸들러 패턴을 사용한 LLM 프로바이더 추상화
- 환경변수로 프로바이더 선택
- 새 프로바이더 추가시 핸들러만 구현하면 됨
"""

from .base import BaseLLMHandler, LLMRequest, LLMResponse, LLMProvider, LLMMessage
from .registry import LLMRegistry, get_llm_handler, chat
from .openai_handler import OpenAIHandler
from .azure_handler import AzureOpenAIHandler
from .anthropic_handler import AnthropicHandler
from .custom_api_handler import CustomAPIHandler

__all__ = [
    # Base
    'BaseLLMHandler',
    'LLMRequest',
    'LLMResponse',
    'LLMMessage',
    'LLMProvider',
    # Registry
    'LLMRegistry',
    'get_llm_handler',
    'chat',
    # Handlers
    'OpenAIHandler',
    'AzureOpenAIHandler',
    'AnthropicHandler',
    'CustomAPIHandler',
]
