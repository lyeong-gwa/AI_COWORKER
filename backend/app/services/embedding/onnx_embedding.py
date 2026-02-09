"""
ONNX Embedding Service

로컬 ONNX 모델을 사용한 텍스트 임베딩 서비스
PyTorch 없이 onnxruntime + tokenizers만으로 동작

필수 패키지:
    pip install onnxruntime tokenizers numpy

모델 디렉토리 구조:
    {ONNX_MODEL_PATH}/
    ├── model.onnx        # ONNX 모델 파일
    └── tokenizer.json    # HuggingFace 토크나이저
"""

import numpy as np
from typing import List, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ONNXEmbeddingService:
    """
    ONNX Runtime 기반 텍스트 임베딩 서비스

    PyTorch/sentence-transformers 없이 동작하며
    onnxruntime + tokenizers만으로 임베딩을 생성합니다.

    Example:
        service = ONNXEmbeddingService()
        embedding = service.embed("안녕하세요")
        embeddings = service.embed_batch(["텍스트1", "텍스트2"])
    """

    MAX_LENGTH = 256  # all-MiniLM-L6-v2 기본 max_length

    def __init__(
        self,
        model_path: Optional[str] = None,
    ):
        """
        Args:
            model_path: ONNX 모델 디렉토리 경로 (model.onnx + tokenizer.json)
        """
        from ...core.config import settings

        self.model_path = model_path or getattr(settings, 'ONNX_MODEL_PATH', None)

        self._session = None
        self._tokenizer = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """모델 초기화 (지연 로딩)"""
        if self._initialized:
            return

        # 1. 패키지 확인
        try:
            import onnxruntime as ort
        except ImportError:
            raise ImportError(
                "onnxruntime이 설치되지 않았습니다.\n"
                "pip install onnxruntime 로 설치하세요."
            )

        try:
            from tokenizers import Tokenizer
        except ImportError:
            raise ImportError(
                "tokenizers가 설치되지 않았습니다.\n"
                "pip install tokenizers 로 설치하세요."
            )

        # 2. 모델 경로 확인
        if not self.model_path:
            raise ValueError(
                "ONNX_MODEL_PATH가 설정되지 않았습니다.\n"
                ".env 파일에 ONNX_MODEL_PATH를 설정하세요.\n"
                "예: ONNX_MODEL_PATH=./models/onnx/sentence-transformers_all-MiniLM-L6-v2"
            )

        model_dir = Path(self.model_path)
        onnx_file = model_dir / "model.onnx"
        tokenizer_file = model_dir / "tokenizer.json"

        if not onnx_file.exists():
            raise FileNotFoundError(
                f"ONNX 모델 파일을 찾을 수 없습니다: {onnx_file}\n"
                f"모델 디렉토리에 model.onnx 파일이 있는지 확인하세요."
            )

        if not tokenizer_file.exists():
            raise FileNotFoundError(
                f"토크나이저 파일을 찾을 수 없습니다: {tokenizer_file}\n"
                f"모델 디렉토리에 tokenizer.json 파일이 있는지 확인하세요."
            )

        # 3. 모델 로드
        try:
            self._session = ort.InferenceSession(
                str(onnx_file),
                providers=['CPUExecutionProvider'],
            )
            self._tokenizer = Tokenizer.from_file(str(tokenizer_file))

            # 토크나이저 max_length 설정
            self._tokenizer.enable_truncation(max_length=self.MAX_LENGTH)
            self._tokenizer.enable_padding(length=None)  # 동적 패딩

            # 입력 이름 확인
            self._input_names = [inp.name for inp in self._session.get_inputs()]

            self._initialized = True
            logger.info(
                f"ONNX 임베딩 서비스 초기화 완료: {onnx_file} "
                f"(입력: {self._input_names})"
            )

        except Exception as e:
            raise RuntimeError(
                f"ONNX 모델 로드 실패: {e}\n"
                f"모델 경로: {self.model_path}"
            )

    def _mean_pool_and_normalize(
        self,
        token_embeddings: np.ndarray,
        attention_mask: np.ndarray,
    ) -> np.ndarray:
        """Mean Pooling + L2 정규화"""
        # attention_mask 확장: (batch, seq_len) → (batch, seq_len, hidden_dim)
        mask = attention_mask[..., np.newaxis].astype(np.float32)

        # 마스크 적용 후 평균
        masked = token_embeddings * mask
        summed = masked.sum(axis=1)
        counted = mask.sum(axis=1).clip(min=1e-9)
        mean_pooled = summed / counted

        # L2 정규화
        norm = np.linalg.norm(mean_pooled, axis=1, keepdims=True).clip(min=1e-9)
        return mean_pooled / norm

    def embed(self, text: str) -> List[float]:
        """
        단일 텍스트 임베딩

        Args:
            text: 임베딩할 텍스트

        Returns:
            임베딩 벡터 (리스트)
        """
        self._ensure_initialized()

        # 토크나이즈
        encoded = self._tokenizer.encode(text)
        input_ids = np.array([encoded.ids], dtype=np.int64)
        attention_mask = np.array([encoded.attention_mask], dtype=np.int64)

        # ONNX 입력 구성
        feeds = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }
        if "token_type_ids" in self._input_names:
            feeds["token_type_ids"] = np.array([encoded.type_ids], dtype=np.int64)

        # 추론
        outputs = self._session.run(None, feeds)
        token_embeddings = outputs[0]  # (1, seq_len, hidden_dim)

        # Mean Pooling + 정규화
        result = self._mean_pool_and_normalize(token_embeddings, attention_mask)
        return result[0].tolist()

    def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        배치 텍스트 임베딩

        Args:
            texts: 임베딩할 텍스트 리스트
            batch_size: 배치 크기

        Returns:
            임베딩 벡터 리스트
        """
        self._ensure_initialized()

        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]

            # 배치 토크나이즈
            encoded_batch = self._tokenizer.encode_batch(batch_texts)

            # 패딩된 배치 구성 (가장 긴 시퀀스에 맞춤)
            max_len = max(len(enc.ids) for enc in encoded_batch)

            input_ids = np.zeros((len(batch_texts), max_len), dtype=np.int64)
            attention_mask = np.zeros((len(batch_texts), max_len), dtype=np.int64)
            token_type_ids = np.zeros((len(batch_texts), max_len), dtype=np.int64)

            for j, enc in enumerate(encoded_batch):
                length = len(enc.ids)
                input_ids[j, :length] = enc.ids
                attention_mask[j, :length] = enc.attention_mask
                token_type_ids[j, :length] = enc.type_ids

            # ONNX 입력 구성
            feeds = {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
            }
            if "token_type_ids" in self._input_names:
                feeds["token_type_ids"] = token_type_ids

            # 추론
            outputs = self._session.run(None, feeds)
            token_embeddings = outputs[0]  # (batch, seq_len, hidden_dim)

            # Mean Pooling + 정규화
            batch_result = self._mean_pool_and_normalize(token_embeddings, attention_mask)
            all_embeddings.extend(batch_result.tolist())

        return all_embeddings

    @property
    def embedding_dim(self) -> int:
        """임베딩 벡터 차원"""
        self._ensure_initialized()
        output_shape = self._session.get_outputs()[0].shape
        return output_shape[-1] if output_shape[-1] is not None else 384

    async def embed_async(self, text: str) -> List[float]:
        """비동기 단일 임베딩 (스레드 풀 사용)"""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed, text)

    async def embed_batch_async(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """비동기 배치 임베딩"""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.embed_batch(texts, batch_size)
        )

    def similarity(self, text1: str, text2: str) -> float:
        """두 텍스트 간 코사인 유사도"""
        emb1 = np.array(self.embed(text1))
        emb2 = np.array(self.embed(text2))
        return float(np.dot(emb1, emb2))


# ─────────────────────────────────────────────────────────────────────────────
# 싱글톤 인스턴스
# ─────────────────────────────────────────────────────────────────────────────

_embedding_service: Optional[ONNXEmbeddingService] = None


def get_embedding_service() -> ONNXEmbeddingService:
    """임베딩 서비스 싱글톤 인스턴스"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = ONNXEmbeddingService()
    return _embedding_service
