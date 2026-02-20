"""
LLM 호출 로거

1질의 1로그파일 원칙 — 모든 LLM API 호출의 프롬프트와 응답을 개별 파일로 저장
"""

import os
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

# 로그 디렉토리 (backend/logs/llm/)
LOG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "logs" / "llm"


def _ensure_log_dir():
    """로그 디렉토리 생성"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def save_llm_log(
    call_type: str,
    provider: str,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    response_content: Optional[str] = None,
    finish_reason: Optional[str] = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    latency_ms: float = 0,
    error: Optional[str] = None,
    extra_params: Optional[Dict[str, Any]] = None,
):
    """
    LLM 호출 로그를 개별 JSON 파일로 저장

    Args:
        call_type: 호출 유형 (intent_detection, response_generation, comment_generation 등)
        provider: LLM 프로바이더 (openai, anthropic, custom_api 등)
        model: 사용된 모델명
        messages: 전송된 메시지 리스트 [{role, content}, ...]
        temperature: 온도 파라미터
        max_tokens: 최대 토큰 수
        response_content: LLM 응답 텍스트
        finish_reason: 종료 사유
        prompt_tokens: 프롬프트 토큰 수
        completion_tokens: 응답 토큰 수
        total_tokens: 전체 토큰 수
        latency_ms: 응답 시간 (ms)
        error: 에러 메시지 (실패시)
        extra_params: 추가 파라미터 (top_p 등)
    """
    try:
        _ensure_log_dir()

        now = datetime.now()
        call_id = uuid.uuid4().hex[:8]

        # 파일명: YYYYMMDD_HHmmss_ms_calltype.json
        filename = f"{now.strftime('%Y%m%d_%H%M%S')}_{now.strftime('%f')[:3]}_{call_type}.json"
        filepath = LOG_DIR / filename

        log_data = {
            "timestamp": now.isoformat(),
            "call_id": call_id,
            "call_type": call_type,
            "provider": provider,
            "model": model,
            "request": {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "other_params": extra_params or {},
            },
            "response": {
                "content": response_content,
                "finish_reason": finish_reason,
                "token_usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                },
                "latency_ms": round(latency_ms, 2),
            },
            "error": error,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)

    except Exception as e:
        # 로깅 실패는 서비스에 영향을 주지 않도록 조용히 처리
        print(f"[LLM Logger] 로그 저장 실패: {e}")
