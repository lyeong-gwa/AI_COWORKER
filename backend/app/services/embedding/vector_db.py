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


def _page_id_from_row(row_id: str, metadata: Optional[Dict[str, Any]]) -> str:
    """ChromaDB row id → page id 추론.

    우선순위:
      1) metadata['page_id'] (P3 청크 메타가 있는 경우)
      2) row_id 에서 ``#chunk-`` suffix 제거 (다중 청크)
      3) row_id 그대로 (단일 청크 / legacy)
    """
    if metadata and isinstance(metadata, dict) and metadata.get("page_id"):
        return str(metadata["page_id"])
    if "#chunk-" in row_id:
        return row_id.split("#chunk-", 1)[0]
    return row_id


def _dedup_to_pages(
    results: Dict[str, Any],
    top_k: int,
    min_score: float,
) -> List["SearchResult"]:
    """ChromaDB query result → page 단위 dedup, max-score 채택.

    동일 ``page_id`` 의 여러 청크 hit 시 가장 높은 score 의 청크를 채택하며,
    그 청크의 ``content`` 와 ``metadata`` 를 응답에 사용한다.
    응답 id 는 ``page_id`` 로 통일된다 (caller 호환성).
    """
    out: Dict[str, "SearchResult"] = {}

    if not results or not results.get("ids") or not results["ids"][0]:
        return []

    ids_row = results["ids"][0]
    distances_row = results.get("distances", [[]])[0] if results.get("distances") else []
    docs_row = results.get("documents", [[]])[0] if results.get("documents") else []
    metas_row = results.get("metadatas", [[]])[0] if results.get("metadatas") else []

    for i, row_id in enumerate(ids_row):
        distance = distances_row[i] if i < len(distances_row) else 0.0
        score = 1 - distance
        if score < min_score:
            continue

        meta = metas_row[i] if i < len(metas_row) else {}
        content = docs_row[i] if i < len(docs_row) else ""
        page_id = _page_id_from_row(row_id, meta)

        prev = out.get(page_id)
        if prev is None or score > prev.score:
            out[page_id] = SearchResult(
                id=page_id,
                content=content,
                score=score,
                metadata=meta or {},
            )

    # max-score DESC 정렬 → top_k
    ranked = sorted(out.values(), key=lambda r: r.score, reverse=True)
    return ranked[:top_k]


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
        collection_name: Optional[str] = None,
    ):
        """
        Args:
            persist_dir: 데이터 저장 경로
            collection_name: 컬렉션 이름. ``None`` 이면 환경변수
                ``KNOWLEDGE_COLLECTION_NAME`` (default: ``knowledge_v2``) 사용.

        Karpathy v2 (`.omc/plans/지식-karpathy-v2.md` §10 step 5, D15):
            기존 ``knowledge`` (v1) 컬렉션은 drop 하지 않고 보존한다.
            신규 컬렉션 ``knowledge_v2`` 가 default 가 되며, 30일 후 v1 정리 옵션을
            P6 에서 별도 검토한다.
        """
        from ...core.config import _BACKEND_DIR
        raw_dir = persist_dir or os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
        self.persist_dir = os.path.join(_BACKEND_DIR, raw_dir) if not os.path.isabs(raw_dir) else raw_dir
        # env 토글 가능. 미설정 시 v2 가 default. (v1 = "knowledge", v2 = "knowledge_v2")
        self.collection_name = (
            collection_name
            or os.getenv("KNOWLEDGE_COLLECTION_NAME")
            or "knowledge_v2"
        )

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
        """문서 추가/업데이트 (chunk-aware — Karpathy v2 P3 §7).

        문서 토큰 수 ≥ 1024 면 청킹·다중 row 저장. 단일 청크면 기존 id 그대로
        upsert. 다중 청크는 ``{doc_id}#chunk-{idx}`` 의 자식 row.

        하위호환: 단일 청크는 기존 호출과 동일한 id 와 메타 구조를 사용한다.
        """
        from ..knowledge_chunker import chunk_document

        self._ensure_initialized()

        # 메타데이터 정리 (ChromaDB는 문자열/숫자/bool 만 지원)
        clean_metadata: Dict[str, Any] = {}
        if metadata:
            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    clean_metadata[key] = value
                elif isinstance(value, list):
                    clean_metadata[key] = ",".join(str(v) for v in value)
                else:
                    clean_metadata[key] = str(value)

        chunks = chunk_document(content)

        # 동일 page_id 의 _기존_ 청크들을 먼저 제거하여 N→M 변동 시 잔재 방지.
        try:
            existing = self._collection.get(where={"page_id": doc_id}, include=[])
            if existing and existing.get("ids"):
                self._collection.delete(ids=list(existing["ids"]))
        except Exception:  # noqa: BLE001
            # 메타 인덱스 없는 row(legacy) 는 page_id where 가 0 건일 수 있음 — 무시.
            pass
        # 단일 청크 / 기존 row 호환을 위해 단순 id 도 명시 삭제 (있으면).
        try:
            self._collection.delete(ids=[doc_id])
        except Exception:  # noqa: BLE001
            pass

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict] = []
        total = len(chunks)
        for ch in chunks:
            chunk_meta = dict(clean_metadata)
            # P3 §7 — chunk 메타 표준
            chunk_meta["page_id"] = doc_id
            chunk_meta["chunk_index"] = int(ch.chunk_index)
            chunk_meta["chunk_total"] = int(total)
            if total == 1:
                row_id = doc_id
            else:
                row_id = f"{doc_id}#chunk-{ch.chunk_index}"
            ids.append(row_id)
            documents.append(ch.text)
            metadatas.append(chunk_meta)

        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        logger.debug(f"문서 추가/업데이트: {doc_id} (chunks={total})")

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

    def search(
        self,
        query: str,
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
        min_score: float = 0.0,
    ) -> List[SearchResult]:
        """유사도 검색 (chunk-aware page 단위 dedup — Karpathy v2 P3).

        하나의 page 가 여러 청크로 hit 되면 max-score 청크를 채택하여 한 번만 반환한다.
        반환된 ``SearchResult.id`` 는 항상 page_id (``{category}/{slug}``) 이며,
        ``metadata`` 에는 청크 메타가 보존된다.
        """
        self._ensure_initialized()

        # dedup 손실 방지를 위해 internal pool 을 top_k * 3 으로 넉넉히 확보.
        internal_k = max(top_k * 3, top_k + 5)

        results = self._collection.query(
            query_texts=[query],
            n_results=internal_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        return _dedup_to_pages(results, top_k=top_k, min_score=min_score)

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
        """모든 문서의 content_hash 조회 (page 단위 — Karpathy v2 P3).

        chunk-aware 도입 후 ChromaDB row 는 page 단위 또는 ``{page_id}#chunk-N``.
        본 메서드는 ``page_id`` 키 기준으로 dedup 한 ``content_hash`` 를 반환한다.

        Returns:
            Dict[str, str]: ``{page_id: content_hash}``
        """
        self._ensure_initialized()

        try:
            all_data = self._collection.get(include=["metadatas"])

            result: Dict[str, str] = {}
            if all_data and all_data.get("ids"):
                for i, row_id in enumerate(all_data["ids"]):
                    meta = all_data["metadatas"][i] if all_data["metadatas"] else {}
                    if not meta:
                        continue
                    page_id = _page_id_from_row(row_id, meta)
                    h = meta.get("content_hash")
                    if h is None:
                        continue
                    # 다중 청크라면 같은 page_id 반복 — 한 번만 등록 (동일 hash 가정).
                    if page_id not in result:
                        result[page_id] = h

            return result
        except Exception as e:
            logger.warning(f"문서 해시 조회 실패: {e}")
            return {}

    def delete_document(self, doc_id: str) -> None:
        """문서 삭제 (chunk-aware — page_id 기준 모든 청크 일괄 삭제).

        기존 호출자는 ``doc_id = page_id`` 이지만 P3 청크 분리 후에는 다수의
        ``{page_id}#chunk-N`` row 가 동시에 존재할 수 있다. ``where page_id`` 로
        전체를 일괄 삭제한 뒤, 단일 청크 호환(id == page_id)도 명시 삭제한다.
        """
        # 위에서 정의되었던 단순 delete 를 chunk-aware 로 override.
        self._ensure_initialized()
        try:
            existing = self._collection.get(where={"page_id": doc_id}, include=[])
            if existing and existing.get("ids"):
                self._collection.delete(ids=list(existing["ids"]))
        except Exception:  # noqa: BLE001
            pass
        try:
            self._collection.delete(ids=[doc_id])
        except Exception:  # noqa: BLE001
            pass
        logger.debug(f"문서 삭제(chunk-aware): {doc_id}")

    def reset(self) -> None:
        """컬렉션 초기화 (모든 데이터 삭제).

        Karpathy v2 P3: 청킹 도입으로 메타 스키마가 변경되어 v2 컬렉션을 재생성할 때
        호출. 임베딩 함수는 동일 ONNX 서비스로 재바인딩한다.
        v1 (``knowledge``) 컬렉션에는 영향을 주지 않는다 (별개 컬렉션).
        """
        self._ensure_initialized()

        # 임베딩 함수를 재바인딩하기 위해 클로저로 다시 정의.
        class LocalEmbeddingFunction:
            def __init__(self, service):
                self.service = service

            def __call__(self, input: List[str]) -> List[List[float]]:
                return self.service.embed_batch(input)

        embed_fn = LocalEmbeddingFunction(self._embedding_service)

        try:
            self._client.delete_collection(self.collection_name)
        except Exception:  # noqa: BLE001
            pass
        self._collection = self._client.create_collection(
            name=self.collection_name,
            embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
        logger.warning(f"벡터 DB 초기화됨: {self.collection_name}")

    def reindex_all_v2_documents(self) -> Dict[str, int]:
        """v2 디렉토리(``data/knowledge/{category}/{slug}.md``) 전체를 재인덱싱.

        Karpathy v2 P3 §3.4 — chunk-aware schema 도입으로 기존 v2 row 가 호환되지
        않을 수 있어, 운영자 명시 호출 시 collection 을 drop+recreate 한 뒤
        모든 페이지를 다시 청크-aware 로 적재한다.

        Returns:
            ``{"total": N, "synced": M, "failed": K}``
        """
        # 순환 import 회피 — 함수 내부 import.
        from ..knowledge_file_service import list_md_files, compute_hash

        self._ensure_initialized()
        try:
            self.reset()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"reset 실패 (계속 진행): {exc}")

        docs = list_md_files()
        synced = 0
        failed = 0
        for doc in docs:
            try:
                content_hash = compute_hash(doc.content)
                meta: Dict[str, Any] = {
                    "title": doc.title,
                    "category": doc.category or "",
                    "source": doc.source or "",
                    "content_hash": content_hash,
                    "page_type": doc.page_type or "Summary",
                    "version": doc.version or 1,
                }
                self.add_document(
                    doc_id=doc.id,
                    content=doc.content,
                    metadata=meta,
                )
                synced += 1
            except Exception as exc:  # noqa: BLE001
                logger.error(f"재인덱싱 실패: {doc.id} - {exc}")
                failed += 1

        return {"total": len(docs), "synced": synced, "failed": failed}


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
