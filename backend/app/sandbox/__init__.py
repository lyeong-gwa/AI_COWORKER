"""
Sandbox Module - 안전한 코드 실행 환경

RestrictedPython을 사용하여 사용자 코드를 안전하게 실행합니다.
"""

from .executor import (
    SandboxedExecutor,
    ExpressionEvaluator,
    ExecutionResult,
    execute_code,
    get_executor,
    SandboxViolationError,
    TimeoutError,
    ALLOWED_MODULES,
    ALLOWED_BUILTINS,
)

__all__ = [
    'SandboxedExecutor',
    'ExpressionEvaluator',
    'ExecutionResult',
    'execute_code',
    'get_executor',
    'SandboxViolationError',
    'TimeoutError',
    'ALLOWED_MODULES',
    'ALLOWED_BUILTINS',
]
