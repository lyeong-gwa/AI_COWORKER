"""Knowledge 청킹(Chunking) 파이프라인 — Karpathy v2 (P3).

설계 근거: `.omc/plans/지식-karpathy-v2.md` §7.

정책:
  - 문서 토큰 수 < 1024 → 단일 청크 (chunk_total=1)
  - 1024 이상 → 800 토큰 sliding window + 100 overlap
  - 토큰 카운터: ONNX 임베딩 모델(`onnx_embedding.py`)의 토크나이저를 재사용
    (tiktoken 의존 금지). 단, 임베딩 토크나이저는 MAX_LENGTH=256 으로 truncation
    설정되어 있으므로 본 모듈은 별도 인스턴스를 로드하여 truncation 을 끄고 사용.
  - 페이지 단위 메타데이터(`page_id`, `chunk_index`, `chunk_total`, `page_type`,
    `category`, `version`)는 vector_db 가 ChromaDB 메타에 부여한다.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


# ── 기본 파라미터 (계획서 §7) ──────────────────────────────────────────────

DEFAULT_THRESHOLD = 1024
DEFAULT_CHUNK_SIZE = 800
DEFAULT_OVERLAP = 100


# ── 카운팅 전용 토크나이저 (truncation 없음) ──────────────────────────────

_count_tokenizer = None
_count_lock = threading.Lock()


def _get_count_tokenizer():
    """카운팅 전용 토크나이저 — embedding 토크나이저와 _별개 인스턴스_.

    embedding 토크나이저는 MAX_LENGTH=256 으로 truncation 활성화되어 있어
    raw 토큰 수를 측정할 수 없다. 본 함수는 동일 tokenizer.json 을 로드하되
    truncation/padding 을 끈 인스턴스를 반환한다.

    실패 시 ``None`` 을 반환 — 호출자는 fallback 으로 단어 수 추정을 사용.
    """
    global _count_tokenizer
    if _count_tokenizer is not None:
        return _count_tokenizer

    with _count_lock:
        if _count_tokenizer is not None:
            return _count_tokenizer

        try:
            from tokenizers import Tokenizer
        except ImportError:
            logger.warning(
                "tokenizers 패키지 없음 → 단어 수 fallback. "
                "정확한 토큰 카운트가 필요하면 pip install tokenizers"
            )
            return None

        # 토크나이저 경로: embedding service 와 동일 모델 디렉토리.
        from ..core.config import settings, _BACKEND_DIR
        raw_path = getattr(settings, "ONNX_MODEL_PATH", None)
        if not raw_path:
            return None

        if not os.path.isabs(raw_path):
            model_path = os.path.join(_BACKEND_DIR, raw_path)
        else:
            model_path = raw_path

        tokenizer_file = Path(model_path) / "tokenizer.json"
        if not tokenizer_file.exists():
            logger.warning(
                f"tokenizer.json 없음 → 단어 수 fallback: {tokenizer_file}"
            )
            return None

        try:
            tok = Tokenizer.from_file(str(tokenizer_file))
            # truncation / padding 모두 끔 — 본 모듈은 _전체_ 토큰 수가 필요.
            try:
                tok.no_truncation()
            except Exception:  # noqa: BLE001
                pass
            try:
                tok.no_padding()
            except Exception:  # noqa: BLE001
                pass
            _count_tokenizer = tok
            logger.info(
                f"청킹 카운트 토크나이저 로드 완료 (truncation off): {tokenizer_file}"
            )
            return _count_tokenizer
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"카운트 토크나이저 로드 실패: {exc}")
            return None


def count_tokens(text: str) -> int:
    """ONNX 임베딩 모델 토크나이저로 ``text`` 의 토큰 수를 반환.

    실패 시 단어(공백 분할) 수 + 1 fallback (대략 보수적 상한).
    빈 문자열은 0.
    """
    if not text:
        return 0
    tok = _get_count_tokenizer()
    if tok is None:
        # fallback — 한글의 경우 단어 분할은 토큰 수의 ~25% 수준이라 보수적으로 4배.
        words = len(text.split())
        return max(words * 4, len(text) // 2)
    try:
        encoded = tok.encode(text)
        return len(encoded.ids)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"토큰 카운트 실패, fallback 사용: {exc}")
        words = len(text.split())
        return max(words * 4, len(text) // 2)


# ── Chunk dataclass ───────────────────────────────────────────────────────


@dataclass
class Chunk:
    """단일 청크.

    Attributes:
        chunk_index: 0-based 청크 순번 (단일 청크면 0).
        chunk_total: 동일 페이지 내 총 청크 수.
        text: 청크 본문 텍스트 (토큰 → 디코드 결과 또는 원문 substring).
        token_count: 청크의 토큰 수.
    """

    chunk_index: int
    chunk_total: int
    text: str
    token_count: int


# ── 청킹 핵심 함수 ────────────────────────────────────────────────────────


def _slice_by_tokens(
    text: str,
    chunk_size: int,
    overlap: int,
) -> List[Chunk]:
    """토크나이저 기반 sliding window 청킹.

    토크나이저가 사용 가능하면 token ids 를 decode 하여 정확한 토큰 경계 청크 생성.
    실패 시 문자열 길이 기반으로 균등 분할 fallback.
    """
    tok = _get_count_tokenizer()
    if tok is None:
        # fallback — 문자 길이를 ~4 곱한 토큰 추정값 기준 균등 분할.
        approx_char_per_token = 4
        char_per_chunk = max(chunk_size * approx_char_per_token, 100)
        char_overlap = max(overlap * approx_char_per_token, 1)
        return _slice_by_chars(text, char_per_chunk, char_overlap)

    try:
        encoded = tok.encode(text)
        ids = list(encoded.ids)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"청킹 시 인코딩 실패, char 분할 fallback: {exc}")
        return _slice_by_chars(text, chunk_size * 4, overlap * 4)

    total_tokens = len(ids)
    if total_tokens == 0:
        return [Chunk(chunk_index=0, chunk_total=1, text=text, token_count=0)]

    step = chunk_size - overlap
    if step <= 0:
        step = chunk_size

    pieces: List[List[int]] = []
    start = 0
    while start < total_tokens:
        end = min(start + chunk_size, total_tokens)
        pieces.append(ids[start:end])
        if end >= total_tokens:
            break
        start += step

    # decode 시도 — Tokenizers HF 의 decode 는 토큰 → 텍스트 복원. 실패 시 원문 fallback.
    chunk_texts: List[str] = []
    for piece in pieces:
        try:
            txt = tok.decode(piece, skip_special_tokens=True)
        except Exception:  # noqa: BLE001
            txt = ""
        if not txt:
            # fallback: 원문에서 비율로 자르기 (정확성 손실 허용).
            ratio_start = (pieces.index(piece) * step) / max(total_tokens, 1)
            ratio_end = min(1.0, (pieces.index(piece) * step + len(piece)) / max(total_tokens, 1))
            s = int(len(text) * ratio_start)
            e = int(len(text) * ratio_end)
            txt = text[s:e]
        chunk_texts.append(txt)

    total = len(chunk_texts)
    chunks: List[Chunk] = []
    for i, (piece, txt) in enumerate(zip(pieces, chunk_texts)):
        chunks.append(
            Chunk(
                chunk_index=i,
                chunk_total=total,
                text=txt,
                token_count=len(piece),
            )
        )
    return chunks


def _slice_by_chars(text: str, char_per_chunk: int, char_overlap: int) -> List[Chunk]:
    """fallback — 문자 길이 기반 균등 분할 (토크나이저 부재 시)."""
    if not text:
        return [Chunk(chunk_index=0, chunk_total=1, text=text, token_count=0)]

    step = char_per_chunk - char_overlap
    if step <= 0:
        step = char_per_chunk

    pieces: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + char_per_chunk, len(text))
        pieces.append(text[start:end])
        if end >= len(text):
            break
        start += step

    total = len(pieces)
    return [
        Chunk(
            chunk_index=i,
            chunk_total=total,
            text=p,
            token_count=max(len(p) // 4, 1),
        )
        for i, p in enumerate(pieces)
    ]


def chunk_document(
    content: str,
    threshold: int = DEFAULT_THRESHOLD,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> List[Chunk]:
    """문서 본문 → 청크 리스트.

    Args:
        content: 페이지 본문 (frontmatter 제외).
        threshold: 청킹 임계점. 토큰 수가 이 값 미만이면 단일 청크.
        chunk_size: 1024 이상일 때 청크당 토큰 수.
        overlap: 인접 청크 간 토큰 overlap.

    Returns:
        ``Chunk`` 리스트. 항상 최소 1개. 단일 청크인 경우 ``chunk_total=1``,
        ``chunk_index=0``.
    """
    if content is None:
        content = ""

    total_tokens = count_tokens(content)

    if total_tokens < threshold:
        return [
            Chunk(
                chunk_index=0,
                chunk_total=1,
                text=content,
                token_count=total_tokens,
            )
        ]

    return _slice_by_tokens(content, chunk_size, overlap)


__all__ = [
    "Chunk",
    "DEFAULT_THRESHOLD",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_OVERLAP",
    "count_tokens",
    "chunk_document",
]
