"""
Embedding Service Module

로컬 ONNX 모델을 사용한 텍스트 임베딩 서비스
외부 API 없이 완전 오프라인으로 동작
"""

from .onnx_embedding import ONNXEmbeddingService, get_embedding_service
from .vector_db import VectorDatabase, get_vector_db

__all__ = [
    'ONNXEmbeddingService',
    'get_embedding_service',
    'VectorDatabase',
    'get_vector_db',
]
