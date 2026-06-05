"""워크플로우 생성 추적 로그(generation trace) 서비스.

각 generate_workflow 호출의 전 단계(LLM 입출력·검증 이력·최종 draft)를
append-only JSONL 파일에 기록한다. 운영자가 폐쇄망 환경에서 사후 진단할 수 있도록 설계.

파일 위치: backend/logs/workflow_generation.jsonl
"""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 로그 파일 경로 (테스트에서 monkeypatch로 교체 가능) ──────────────────────
# 이 변수를 직접 참조해 경로를 결정하므로, 테스트에서 이 모듈 속성을 교체해 격리한다.
_DEFAULT_LOG_DIR = Path(__file__).resolve().parents[3] / "logs"
_DEFAULT_LOG_FILE_NAME = "workflow_generation.jsonl"

# 실제 사용 경로 — 테스트에서 아래 함수를 통해 override 한다.
_log_file_path: Optional[Path] = None


def get_log_file_path() -> Path:
    """현재 설정된 로그 파일 경로를 반환한다."""
    if _log_file_path is not None:
        return _log_file_path
    return _DEFAULT_LOG_DIR / _DEFAULT_LOG_FILE_NAME


def set_log_file_path(path: Path) -> None:
    """로그 파일 경로를 교체한다. 테스트 격리용."""
    global _log_file_path
    _log_file_path = path


def reset_log_file_path() -> None:
    """로그 파일 경로를 기본값으로 되돌린다."""
    global _log_file_path
    _log_file_path = None


# ── 최대 truncate 길이 ────────────────────────────────────────────────────────
_MAX_TEXT_LEN = 20_000
_TRUNCATE_SUFFIX = "...[truncated]"


def _truncate(text: str, max_len: int = _MAX_TEXT_LEN) -> str:
    """진단용 텍스트를 max_len 자에서 truncate 한다."""
    if text and len(text) > max_len:
        return text[:max_len] + _TRUNCATE_SUFFIX
    return text


# ── 공개 API ──────────────────────────────────────────────────────────────────


def append_trace(trace: dict) -> None:
    """trace dict 를 JSONL 파일에 한 줄 추가한다.

    - 디렉토리가 없으면 자동 생성한다.
    - 예외는 전부 삼킨다 — 로깅 실패가 생성 자체를 깨뜨리면 안 된다.
    """
    try:
        log_path = get_log_file_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(trace, ensure_ascii=False)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
    except Exception as exc:  # noqa: BLE001
        logger.debug("generation trace 저장 실패(무시): %s", exc)


def read_traces(limit: int = 50) -> List[Dict]:
    """최신순 trace 요약 리스트를 반환한다.

    파일의 마지막 limit 줄을 deque 로 효율적으로 읽어 파싱한다.
    요약 필드: traceId, createdAt, mode, description(앞 120자),
              attempts, result, errorCount, warningCount, nodeCount.
    """
    try:
        log_path = get_log_file_path()
        if not log_path.exists():
            return []

        # 마지막 N 줄만 읽기 (deque(maxlen) 활용)
        with log_path.open("r", encoding="utf-8") as fh:
            last_lines = deque(fh, maxlen=limit)

        summaries: List[Dict] = []
        for line in reversed(list(last_lines)):  # 최신순(파일 끝 → 앞)
            line = line.strip()
            if not line:
                continue
            try:
                trace = json.loads(line)
                final_val = trace.get("finalValidation") or {}
                summaries.append({
                    "traceId": trace.get("traceId"),
                    "createdAt": trace.get("createdAt"),
                    "mode": trace.get("mode"),
                    "description": (trace.get("description") or "")[:120],
                    "attempts": trace.get("attempts", 0),
                    "result": trace.get("result"),
                    "errorCount": final_val.get("errorCount", 0),
                    "warningCount": final_val.get("warningCount", 0),
                    "nodeCount": len((trace.get("finalDraft") or {}).get("nodes", [])),
                })
            except (json.JSONDecodeError, Exception) as exc:
                logger.debug("trace 줄 파싱 실패(무시): %s", exc)
                continue

        return summaries

    except Exception as exc:  # noqa: BLE001
        logger.debug("read_traces 실패(무시): %s", exc)
        return []


def get_trace(trace_id: str) -> Optional[Dict]:
    """trace_id 에 해당하는 전체 trace 1건을 반환한다. 없으면 None."""
    try:
        log_path = get_log_file_path()
        if not log_path.exists():
            return None

        with log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    trace = json.loads(line)
                    if trace.get("traceId") == trace_id:
                        return trace
                except (json.JSONDecodeError, Exception):
                    continue

        return None

    except Exception as exc:  # noqa: BLE001
        logger.debug("get_trace 실패(무시): %s", exc)
        return None


def get_traces_by_ids(trace_ids: List[str]) -> List[Dict]:
    """주어진 trace_id 목록에 해당하는 전체 trace dict 들을 반환한다.

    - 반환 순서는 입력 ``trace_ids`` 와 동일하다 (대화 순서 보존).
    - 존재하지 않는 id 는 건너뛴다.
    - 파일을 단 한 번만 읽어(single-pass) 필요한 trace 만 수집한 뒤
      입력 순서대로 재정렬한다.
    """
    if not trace_ids:
        return []

    wanted = set(trace_ids)
    found: Dict[str, Dict] = {}

    try:
        log_path = get_log_file_path()
        if not log_path.exists():
            return []

        with log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    trace = json.loads(line)
                except (json.JSONDecodeError, Exception):
                    continue
                tid = trace.get("traceId")
                if tid in wanted and tid not in found:
                    # 같은 id 가 중복 기록되어 있으면 첫(가장 오래된) 항목을 사용.
                    found[tid] = trace
                    if len(found) == len(wanted):
                        break
    except Exception as exc:  # noqa: BLE001
        logger.debug("get_traces_by_ids 실패(무시): %s", exc)
        return []

    # 입력 순서대로 재정렬, 없는 id 는 생략
    return [found[tid] for tid in trace_ids if tid in found]


def trace_to_conversation_item(trace: Dict) -> Dict:
    """trace dict 1건을 대화(conversation) 요약 항목으로 변환한다.

    반환 필드:
      traceId, createdAt, mode, userMessage, assistantMessage,
      attempts, result, errorCount, warningCount.

    errorCount/warningCount 는 finalValidation 에서 파생한다.
    userMessage 는 신규 필드이며, 구버전 trace 호환을 위해
    없으면 description 으로 폴백한다.
    """
    final_val = trace.get("finalValidation") or {}
    user_message = trace.get("userMessage")
    if user_message is None:
        user_message = trace.get("description")
    return {
        "traceId": trace.get("traceId"),
        "createdAt": trace.get("createdAt"),
        "mode": trace.get("mode"),
        "userMessage": user_message or "",
        "assistantMessage": trace.get("assistantMessage") or "",
        "attempts": trace.get("attempts", 0),
        "result": trace.get("result"),
        "errorCount": final_val.get("errorCount", 0),
        "warningCount": final_val.get("warningCount", 0),
    }


# ── LLM 호출 추적 프록시 ──────────────────────────────────────────────────────


class _TracingHandlerProxy:
    """LLM 핸들러의 chat() 를 래핑하여 호출 기록을 수집하는 경량 프록시.

    사용법::

        proxy = TracingHandlerProxy(handler)
        resp = await proxy.chat(req)
        calls = proxy.llm_calls  # [{callType, systemPrompt, prompt, response, ...}]
    """

    def __init__(self, handler: object) -> None:
        self._handler = handler
        self.llm_calls: List[Dict] = []

    async def chat(self, req: object) -> object:
        """handler.chat 을 위임하고 호출 정보를 llm_calls 에 기록한다."""
        import time

        # ── 프롬프트 추출 ────────────────────────────────────────────────────
        call_type: str = getattr(req, "call_type", "unknown") or "unknown"
        system_prompt: str = ""
        user_prompt: str = ""
        messages = getattr(req, "messages", None) or []
        for msg in messages:
            role = getattr(msg, "role", "") or ""
            content = getattr(msg, "content", "") or ""
            if role == "system":
                system_prompt = _truncate(content)
            elif role == "user":
                # 여러 user 메시지가 있으면 마지막이 실제 프롬프트
                user_prompt = _truncate(content)

        t0 = time.perf_counter()
        ok = False
        response_content: str = ""
        token_usage = None

        try:
            resp = await self._handler.chat(req)
            ok = True
            response_content = _truncate(getattr(resp, "content", "") or "")
            # token_usage 프로퍼티가 있으면 가져온다
            try:
                token_usage = getattr(resp, "token_usage", None)
            except Exception:
                token_usage = None
            return resp
        except Exception:
            ok = False
            raise
        finally:
            duration_ms = (time.perf_counter() - t0) * 1000
            self.llm_calls.append({
                "callType": call_type,
                "systemPrompt": system_prompt,
                "prompt": user_prompt,
                "response": response_content,
                "tokenUsage": token_usage,
                "durationMs": round(duration_ms, 2),
                "ok": ok,
            })

    def __getattr__(self, name: str) -> object:
        """chat 이외의 속성 접근은 원 handler 에 위임한다."""
        return getattr(self._handler, name)


def make_tracing_proxy(handler: object) -> _TracingHandlerProxy:
    """handler 를 래핑한 TracingHandlerProxy 를 반환한다."""
    return _TracingHandlerProxy(handler)


__all__ = [
    "append_trace",
    "read_traces",
    "get_trace",
    "get_traces_by_ids",
    "trace_to_conversation_item",
    "make_tracing_proxy",
    "get_log_file_path",
    "set_log_file_path",
    "reset_log_file_path",
]
