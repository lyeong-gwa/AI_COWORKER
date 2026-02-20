"""
Vector Database Service

ChromaDB를 사용한 벡터 데이터베이스
로컬 ONNX 임베딩과 함께 완전 오프라인으로 동작
"""

import os
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """검색 결과"""
    id: str
    content: str
    score: float
    metadata: Dict[str, Any]


class VectorDatabase:
    """
    ChromaDB 기반 벡터 데이터베이스

    로컬 ONNX 임베딩과 함께 사용하여
    완전 오프라인 유사도 검색을 제공합니다.

    Example:
        db = VectorDatabase()

        # 문서 추가
        db.add_document("doc-1", "Python은 프로그래밍 언어입니다.", {"category": "tech"})

        # 검색
        results = db.search("프로그래밍", top_k=5)
    """

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        collection_name: str = "knowledge_base",
    ):
        """
        Args:
            persist_dir: 데이터 저장 경로
            collection_name: 컬렉션 이름
        """
        self.persist_dir = persist_dir or os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
        self.collection_name = collection_name

        self._client = None
        self._collection = None
        self._embedding_service = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """데이터베이스 초기화 (지연 로딩)"""
        if self._initialized:
            return

        try:
            import chromadb
            from chromadb.config import Settings

            # ChromaDB 클라이언트 생성
            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                ),
            )

            # 임베딩 서비스 로드
            from .onnx_embedding import get_embedding_service
            self._embedding_service = get_embedding_service()

            # 커스텀 임베딩 함수 생성
            class LocalEmbeddingFunction:
                def __init__(self, service):
                    self.service = service

                def __call__(self, input: List[str]) -> List[List[float]]:
                    return self.service.embed_batch(input)

            # 컬렉션 생성/로드
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=LocalEmbeddingFunction(self._embedding_service),
                metadata={"hnsw:space": "cosine"},
            )

            self._initialized = True
            logger.info(f"벡터 DB 초기화 완료: {self.persist_dir}/{self.collection_name}")

        except ImportError:
            raise ImportError(
                "chromadb가 설치되지 않았습니다.\n"
                "pip install chromadb 로 설치하세요."
            )
        except Exception as e:
            raise RuntimeError(f"벡터 DB 초기화 실패: {e}")

    def add_document(
        self,
        doc_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        문서 추가/업데이트

        Args:
            doc_id: 문서 ID
            content: 문서 내용
            metadata: 메타데이터 (category, tags 등)
        """
        self._ensure_initialized()

        # 메타데이터 정리 (ChromaDB는 문자열/숫자만 지원)
        clean_metadata = {}
        if metadata:
            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    clean_metadata[key] = value
                elif isinstance(value, list):
                    clean_metadata[key] = ",".join(str(v) for v in value)
                else:
                    clean_metadata[key] = str(value)

        self._collection.upsert(
            ids=[doc_id],
            documents=[content],
            metadatas=[clean_metadata] if clean_metadata else None,
        )

        logger.debug(f"문서 추가/업데이트: {doc_id}")

    def add_documents(
        self,
        documents: List[Dict[str, Any]],
    ) -> None:
        """
        배치 문서 추가

        Args:
            documents: [{"id": ..., "content": ..., "metadata": ...}, ...]
        """
        self._ensure_initialized()

        ids = [doc["id"] for doc in documents]
        contents = [doc["content"] for doc in documents]
        metadatas = []

        for doc in documents:
            meta = doc.get("metadata", {})
            clean_meta = {}
            for key, value in meta.items():
                if isinstance(value, (str, int, float, bool)):
                    clean_meta[key] = value
                elif isinstance(value, list):
                    clean_meta[key] = ",".join(str(v) for v in value)
                else:
                    clean_meta[key] = str(value)
            metadatas.append(clean_meta)

        self._collection.upsert(
            ids=ids,
            documents=contents,
            metadatas=metadatas if any(metadatas) else None,
        )

        logger.info(f"배치 문서 추가: {len(documents)}건")

    def delete_document(self, doc_id: str) -> None:
        """문서 삭제"""
        self._ensure_initialized()
        self._collection.delete(ids=[doc_id])
        logger.debug(f"문서 삭제: {doc_id}")

    def search(
        self,
        query: str,
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
        min_score: float = 0.0,
    ) -> List[SearchResult]:
        """
        유사도 검색

        Args:
            query: 검색 쿼리
            top_k: 반환할 결과 수
            where: 필터 조건 (예: {"category": "tech"})
            min_score: 최소 유사도 점수

        Returns:
            검색 결과 리스트
        """
        self._ensure_initialized()

        results = self._collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        search_results = []

        if results and results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                # ChromaDB는 거리(distance)를 반환, 코사인의 경우 유사도 = 1 - distance
                distance = results["distances"][0][i] if results["distances"] else 0
                score = 1 - distance  # 코사인 유사도로 변환

                if score >= min_score:
                    search_results.append(SearchResult(
                        id=doc_id,
                        content=results["documents"][0][i] if results["documents"] else "",
                        score=score,
                        metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                    ))

        return search_results

    async def search_async(
        self,
        query: str,
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
        min_score: float = 0.0,
    ) -> List[SearchResult]:
        """비동기 검색"""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.search(query, top_k, where, min_score)
        )

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """문서 조회"""
        self._ensure_initialized()

        result = self._collection.get(
            ids=[doc_id],
            include=["documents", "metadatas"],
        )

        if result and result["ids"]:
            return {
                "id": result["ids"][0],
                "content": result["documents"][0] if result["documents"] else "",
                "metadata": result["metadatas"][0] if result["metadatas"] else {},
            }

        return None

    def count(self) -> int:
        """문서 수"""
        self._ensure_initialized()
        return self._collection.count()

    def get_all_document_hashes(self) -> Dict[str, str]:
        """모든 문서의 content_hash 조회

        Returns:
            Dict[str, str]: {doc_id: content_hash}
        """
        self._ensure_initialized()

        try:
            # ChromaDB에서 모든 문서 메타데이터 가져오기
            all_data = self._collection.get(
                include=["metadatas"],
            )

            result = {}
            if all_data and all_data["ids"]:
                for i, doc_id in enumerate(all_data["ids"]):
                    meta = all_data["metadatas"][i] if all_data["metadatas"] else {}
                    if meta and "content_hash" in meta:
                        result[doc_id] = meta["content_hash"]

            return result
        except Exception as e:
            logger.warning(f"문서 해시 조회 실패: {e}")
            return {}

    def reset(self) -> None:
        """컬렉션 초기화 (모든 데이터 삭제)"""
        self._ensure_initialized()
        self._client.delete_collection(self.collection_name)
        self._collection = self._client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.warning(f"벡터 DB 초기화됨: {self.collection_name}")


# ─────────────────────────────────────────────────────────────────────────────
# 싱글톤 인스턴스
# ─────────────────────────────────────────────────────────────────────────────

_vector_db: Optional[VectorDatabase] = None


def get_vector_db() -> VectorDatabase:
    """벡터 DB 싱글톤 인스턴스"""
    global _vector_db
    if _vector_db is None:
        _vector_db = VectorDatabase()
    return _vector_db
