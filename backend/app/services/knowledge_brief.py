"""Knowledge Brief — Karpathy v2 P4 Consumer B (`.omc/plans/지식-karpathy-v2.md` §1.1).

Consumer B 핵심: 사용자가 CLI 로 AI 와 작업할 때 그 AI 가 _사용자의 작업 의도를
이해하는 데도_ 위키 지식을 사용. brief 응답은 페이지 단편이 아닌 _전체 페이지
+ 카테고리 인덱스 + 최근 변경이력_ 을 동봉하여 CLI 어시스턴트가 broadly
파악할 수 있게 한다.

차이 (Consumer A vs B):
  - A (knowledge 노드 / `/knowledge/search`) — top_k 4~7 정밀, 단편 청크 기반
  - B (`/knowledge/brief`) — page_type 가중 + indexes + log 동봉

설계 근거: §1.1 Consumer B, §6.1.7
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from ..core.config import _BACKEND_DIR, settings
from .knowledge_file_service import KnowledgeFileDoc, list_md_files, read_md_file

logger = logging.getLogger(__name__)


# page_type 가중치 — plan §1.1 Consumer B 우선순위
# Synthesis > Summary > Comparison > Entity > Concept
# 단 Concept 도 의도 파악에 중요하므로 1.0 유지.
_PAGE_TYPE_WEIGHTS: Dict[str, float] = {
    "Synthesis": 1.5,
    "Summary": 1.3,
    "Comparison": 1.1,
    "Concept": 1.0,
    "Entity": 0.9,
}


def _knowledge_dir() -> str:
    d = settings.KNOWLEDGE_DIR
    if not os.path.isabs(d):
        d = os.path.join(_BACKEND_DIR, d)
    os.makedirs(d, exist_ok=True)
    return d


def _read_index_md(category: str) -> Optional[str]:
    """`_index-{category}.md` 본문 읽기. 없으면 None."""
    p = os.path.join(_knowledge_dir(), category, f"_index-{category}.md")
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


_LOG_LINE_PATTERN = re.compile(
    r"^##\s*\[(?P<ts>[^\]]+)\]\s*"
    r"(?P<change>\S+)\s*\|\s*"
    r"(?P<id>[^|]+?)\s*\|\s*"
    r"v(?P<version>\S+)\s*\|\s*by\s*(?P<operator>.+)$"
)


def _read_recent_log(limit: int = 20) -> List[Dict[str, Any]]:
    """`_log.md` 최근 N행 파싱. 없거나 비어 있으면 []."""
    p = os.path.join(_knowledge_dir(), "_log.md")
    if not os.path.exists(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    parsed: List[Dict[str, Any]] = []
    for ln in lines:
        m = _LOG_LINE_PATTERN.match(ln)
        if not m:
            continue
        parsed.append({
            "timestamp": m.group("ts").strip(),
            "id": m.group("id").strip(),
            "version": m.group("version").strip(),
            "operator": m.group("operator").strip(),
            "summary": f"{m.group('change').strip()} | {m.group('id').strip()} | v{m.group('version').strip()} | by {m.group('operator').strip()}",
        })
    if limit > 0:
        parsed = parsed[-limit:]
    # 최신 순 (역순) — CLI 가독성
    parsed.reverse()
    return parsed


def _weight_for(page_type: str) -> float:
    return _PAGE_TYPE_WEIGHTS.get(page_type or "", 1.0)


async def build_brief(
    *,
    topic: Optional[str] = None,
    query: Optional[str] = None,
    categories: Optional[List[str]] = None,
    services: Optional[List[str]] = None,
    max_pages: int = 8,
    include_log: bool = True,
) -> Dict[str, Any]:
    """CLI 어시스턴트용 briefing 패키지 생성.

    동작 (사용자 지시):
      - `topic` 또는 `query` 중 하나는 필수. 둘 다 있으면 query 우선.
      - vector_db.search top 20 → page_type 가중치 부여 → 재정렬 → `max_pages` 만 선택.
      - pages 의 카테고리 set 의 `_index-{category}.md` 본문 동봉.
      - `include_log=True` 면 `_log.md` 최근 20행 파싱 → `recentChanges`.
      - `retrievalNotes` 에 메타 설명. Multi-service v3 P2 §2.5: 사용된 service 필터를 명시.

    Multi-service v3 P2 (`.omc/plans/지식-multi-service.md` §2.5):
      - ``services`` 파라미터 추가. None/빈 = 전체. ChromaDB where 는 단일 service
        만 직접 결합하고, 다중은 응답 후필터 (page 단위). categories 와 AND 결합.

    Returns:
        {
            pages: [{id, title, page_type, category, service, content, score, weightedScore, tags}],
            indexes: [{category, content}],
            recentChanges?: [{timestamp, id, version, operator, summary}],
            retrievalNotes: str,
        }
    """
    if not topic and not query:
        raise ValueError("topic 또는 query 중 하나는 반드시 지정해야 합니다.")
    q = (query or topic or "").strip()

    # P2 §2.5 — service 필터 정규화
    service_set: Optional[set] = None
    if services:
        service_set = {s for s in services if s}

    pages: List[Dict[str, Any]] = []
    retrieval_notes = (
        "Used page_type weighting (Synthesis x1.5, Summary x1.3, Comparison x1.1, "
        "Concept x1.0, Entity x0.9). Brief is intended for CLI agent task understanding."
    )
    if service_set:
        retrieval_notes += f" Service filter applied: {sorted(service_set)}."

    # ── 1. 검색 ─────────────────────────────────────────────────────────
    candidates: List[Dict[str, Any]] = []
    try:
        from .embedding import get_vector_db
        vd = get_vector_db()

        # ChromaDB where_filter 구성 — category + service 둘 다 단일이면 $and, 그 외는 후필터.
        cat_clause: Optional[Dict[str, Any]] = None
        if categories and len(categories) == 1:
            cat_clause = {"category": categories[0]}

        svc_clause: Optional[Dict[str, Any]] = None
        if service_set and len(service_set) == 1:
            only_svc = next(iter(service_set))
            svc_clause = {"service": only_svc}

        where_filter: Optional[Dict[str, Any]]
        if cat_clause and svc_clause:
            where_filter = {"$and": [cat_clause, svc_clause]}
        else:
            where_filter = cat_clause or svc_clause

        results = await vd.search_async(query=q, top_k=20, where=where_filter)
        for r in results:
            doc = read_md_file(r.id)
            if not doc:
                continue
            if categories and (doc.category or "") not in set(categories):
                continue
            if service_set and (doc.service or "unknown") not in service_set:
                continue
            w = _weight_for(doc.page_type or "")
            candidates.append({
                "doc": doc,
                "score": float(r.score),
                "weighted": float(r.score) * w,
            })
    except Exception as exc:  # noqa: BLE001
        logger.warning("[BRIEF] vector_db search 실패 — fallback: 카테고리/서비스 필터만: %s", exc)
        retrieval_notes += " (fallback: vector search unavailable, returning sample by filter)"
        # fallback: 파일 시스템에서 카테고리/서비스 필터만 적용해 상위 N건
        all_docs = list_md_files()
        if categories:
            cat_set = set(categories)
            all_docs = [d for d in all_docs if (d.category or "") in cat_set]
        if service_set:
            all_docs = [d for d in all_docs if (d.service or "unknown") in service_set]
        for d in all_docs[: max_pages * 2]:
            w = _weight_for(d.page_type or "")
            candidates.append({
                "doc": d,
                "score": 0.0,
                "weighted": w,
            })

    # ── 2. 재정렬 + 상위 max_pages 선택 ──────────────────────────────────
    candidates.sort(key=lambda c: c["weighted"], reverse=True)
    selected = candidates[: max(1, int(max_pages))]

    for it in selected:
        d: KnowledgeFileDoc = it["doc"]
        pages.append({
            "id": d.id,
            "title": d.title,
            "page_type": d.page_type,
            "category": d.category,
            "service": d.service or "unknown",  # NEW multi-service v3 P2 §2.5
            "content": d.content,
            "score": round(it["score"], 4),
            "weightedScore": round(it["weighted"], 4),
            "tags": list(d.tags or []),
            "version": d.version,
        })

    # ── 3. 카테고리 인덱스 동봉 ─────────────────────────────────────────
    cats_in_result: List[str] = []
    seen = set()
    for p in pages:
        c = p.get("category") or ""
        if c and c not in seen:
            seen.add(c)
            cats_in_result.append(c)
    # categories 인자가 지정되었다면 그 카테고리들의 인덱스도 항상 동봉
    if categories:
        for c in categories:
            if c and c not in seen:
                seen.add(c)
                cats_in_result.append(c)

    indexes: List[Dict[str, Any]] = []
    for cat in cats_in_result:
        body = _read_index_md(cat)
        if body is not None:
            indexes.append({"category": cat, "content": body})

    response: Dict[str, Any] = {
        "pages": pages,
        "indexes": indexes,
        "retrievalNotes": retrieval_notes,
    }

    if include_log:
        response["recentChanges"] = _read_recent_log(limit=20)

    return response


__all__ = ["build_brief"]
