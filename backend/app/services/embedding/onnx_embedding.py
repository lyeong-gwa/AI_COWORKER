"""
ONNX Embedding Service

로컬 ONNX 모델을 사용한 텍스트 임베딩 서비스
sentence-transformers 모델 기반

지원 모델:
- sentence-transformers/all-MiniLM-L6-v2 (기본, 경량)
- sentence-transformers/all-mpnet-base-v2 (고성능)
- sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (다국어)
"""

import os
import numpy as np
from typing import List, Optional, Union
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ONNXEmbeddingService:
    """
    ONNX 기반 텍스트 임베딩 서비스

    완전 오프라인으로 동작하며 외부 API 호출 없이
    로컬에서 텍스트를 벡터로 변환합니다.

    Example:
        service = ONNXEmbeddingService()
        embedding = service.embed("안녕하세요")
        embeddings = service.embed_batch(["텍스트1", "텍스트2"])
    """

    DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 차원

    def __init__(
        self,
        model_path: Optional[str] = None,
        model_name: Optional[str] = None,
        cache_dir: Optional[str] = None,
    ):
        """
        Args:
            model_path: 이미 다운로드된 모델 경로 (ONNX_MODEL_PATH 환경변수)
            model_name: HuggingFace 모델명 (자동 다운로드)
            cache_dir: 모델 캐시 디렉토리
        """
        self.model_path = model_path or os.getenv("ONNX_MODEL_PATH")
        self.model_name = model_name or self.DEFAULT_MODEL
        self.cache_dir = cache_dir or os.getenv("MODEL_CACHE_DIR", "./models")

        self._model = None
        self._tokenizer = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """모델 초기화 (지연 로딩)"""
        if self._initialized:
            return

        # 1. 패키지 import 확인
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers가 설치되지 않았습니다.\n"
                "pip install sentence-transformers 로 설치하세요."
            )

        # 2. 모델 로드
        try:
            if self.model_path and os.path.exists(self.model_path):
                logger.info(f"로컬 모델 로드: {self.model_path}")
                self._model = SentenceTransformer(self.model_path)
            else:
                logger.info(f"모델 다운로드/로드: {self.model_name}")
                self._model = SentenceTransformer(
                    self.model_name,
                    cache_folder=self.cache_dir,
                )

                # 다운로드된 모델 경로 저장
                if not self.model_path:
                    model_cache_path = Path(self.cache_dir) / self.model_name.replace("/", "_")
                    self.model_path = str(model_cache_path)

            self._initialized = True
            logger.info(f"임베딩 서비스 초기화 완료 (차원: {self.embedding_dim})")

        except Exception as e:
            raise RuntimeError(
                f"임베딩 모델 로드 실패: {e}\n"
                f"모델 경로: {self.model_path}\n"
                f"의존성 확인: pip install sentence-transformers torch transformers"
            )

    @property
    def embedding_dim(self) -> int:
        """임베딩 벡터 차원"""
        self._ensure_initialized()
        return self._model.get_sentence_embedding_dimension()

    def embed(self, text: str) -> List[float]:
        """
        단일 텍스트 임베딩

        Args:
            text: 임베딩할 텍스트

        Returns:
            임베딩 벡터 (리스트)
        """
        self._ensure_initialized()

        embedding = self._model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        return embedding.tolist()

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

        embeddings = self._model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 100,
        )

        return embeddings.tolist()

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
        """
        두 텍스트 간 코사인 유사도

        Args:
            text1: 첫 번째 텍스트
            text2: 두 번째 텍스트

        Returns:
            유사도 점수 (0~1)
        """
        emb1 = np.array(self.embed(text1))
        emb2 = np.array(self.embed(text2))

        # 이미 정규화되어 있으므로 내적만 계산
        return float(np.dot(emb1, emb2))

    def save_model(self, path: str) -> None:
        """모델을 로컬에 저장"""
        self._ensure_initialized()
        self._model.save(path)
        logger.info(f"모델 저장 완료: {path}")


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
