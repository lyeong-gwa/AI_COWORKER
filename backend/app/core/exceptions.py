"""Unified error handling for the CLI-facing REST API.

Phase 2b introduces a canonical error envelope so CLI clients (Claude Code and
similar) can machine-parse failures without scraping FastAPI's default payload.

Envelope shape (HTTP response body):

    {
        "error": {
            "code":    "<SCREAMING_SNAKE>",
            "message": "<human readable>",
            "details": { ... optional context ... }
        }
    }

Design notes
------------
* We keep ``fastapi.HTTPException`` usages intact in legacy routes for now.
  The registered handlers translate BOTH ``AppException`` AND ``HTTPException``
  / ``RequestValidationError`` into the same envelope so CLI parsing is uniform.
* New routes should prefer raising ``AppException`` subclasses.
* Do NOT leak stack traces to clients — the 500 handler hides details but logs
  them server-side.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


# ── Exception classes ──────────────────────────────────────────────────────


class AppException(Exception):
    """Base class for all domain-level errors that should reach the client.

    ``code`` is a stable identifier the CLI can match on (e.g. ``NOT_FOUND``).
    ``message`` is human-readable (Korean OK).
    ``details`` is optional structured context (IDs, field names, etc).
    ``status_code`` drives the HTTP response status.
    """

    code: str = "APP_ERROR"
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details: Dict[str, Any] = details or {}

    def to_envelope(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class NotFoundError(AppException):
    """404 — 리소스를 찾을 수 없음."""

    code = "NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND


class ValidationError(AppException):
    """422 — 입력 검증 실패 (도메인 규칙)."""

    code = "VALIDATION_ERROR"
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class ConflictError(AppException):
    """409 — 중복/충돌."""

    code = "CONFLICT"
    status_code = status.HTTP_409_CONFLICT


class RateLimitError(AppException):
    """429 — 호출 제한 초과."""

    code = "RATE_LIMIT"
    status_code = status.HTTP_429_TOO_MANY_REQUESTS


class InternalError(AppException):
    """500 — 명시적으로 내부 에러를 보고할 때."""

    code = "INTERNAL_ERROR"
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


# ── Handlers ───────────────────────────────────────────────────────────────


def _envelope(code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    }


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_envelope())


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Translate legacy ``HTTPException`` raises into the canonical envelope.

    We derive a stable code from the HTTP status (e.g. ``HTTP_404``) so CLI
    consumers can branch on it even before every call site migrates to
    ``AppException``.
    """
    code = f"HTTP_{exc.status_code}"
    if exc.status_code == 404:
        code = "NOT_FOUND"
    elif exc.status_code == 409:
        code = "CONFLICT"
    elif exc.status_code == 400:
        code = "BAD_REQUEST"
    elif exc.status_code == 401:
        code = "UNAUTHORIZED"
    elif exc.status_code == 403:
        code = "FORBIDDEN"
    elif exc.status_code == 422:
        code = "VALIDATION_ERROR"
    elif exc.status_code == 429:
        code = "RATE_LIMIT"
    elif exc.status_code >= 500:
        code = "INTERNAL_ERROR"

    message = exc.detail if isinstance(exc.detail, str) else "요청 처리에 실패했습니다"
    details: Dict[str, Any] = {}
    if not isinstance(exc.detail, str) and exc.detail is not None:
        details["detail"] = exc.detail

    return JSONResponse(status_code=exc.status_code, content=_envelope(code, message, details))


def _sanitize_pydantic_errors(errors: list[Any]) -> list[Any]:
    """Pydantic v2 errors() 는 ``ctx.error`` 에 ValueError 같은 비-직렬화 객체를 담을 수 있다.

    JSONResponse 직렬화가 깨지지 않도록 알 수 없는 객체를 ``str(...)`` 으로 평탄화한다.
    """

    def _safe(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: _safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_safe(v) for v in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        # ValueError 등 — 메시지로 평탄화
        return str(value)

    return [_safe(e) for e in errors]


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Pydantic/FastAPI 입력 검증 실패."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_envelope(
            "VALIDATION_ERROR",
            "요청 본문 검증에 실패했습니다",
            {"errors": _sanitize_pydantic_errors(exc.errors())},
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all so unexpected errors still follow the envelope."""
    logger.exception("[UNHANDLED] %s %s — %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_envelope(
            "INTERNAL_ERROR",
            "예기치 못한 서버 오류가 발생했습니다",
            {"type": exc.__class__.__name__},
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all unified handlers onto the FastAPI app."""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


__all__ = [
    "AppException",
    "NotFoundError",
    "ValidationError",
    "ConflictError",
    "RateLimitError",
    "InternalError",
    "register_exception_handlers",
]
