"""Knowledge Graph Builder — 임베딩 기반 의미 엣지 + Louvain community.

`.omc/plans/지식-그래프-재구성.md` Phase 1 산출물.

핵심 아이디어:
  1. wiki 페이지 + ChromaDB ``knowledge_v2`` 컬렉션 임베딩 재사용 (LLM 0 호출).
  2. explicit edge = 본문의 ``[[category/slug]]`` 파싱 (기존 link parser).
  3. implicit edge = cosine similarity > threshold + 페이지당 top N + explicit 중복 제외.
  4. networkx Louvain 으로 community 검출, 각 community 의 페이지 title 들에서
     TF-IDF top 3 키워드를 label 로 생성 (결정적, LLM 불필요).
  5. degree centrality 를 0~1 로 정규화하여 ``godScore`` 부여.

env knobs:
  - ``KNOWLEDGE_IMPLICIT_THRESHOLD`` (default 0.75)
  - ``KNOWLEDGE_IMPLICIT_MAX_PER_PAGE`` (default 5)

응답 형식: 계획서 §3.2 참고 (camelCase).
"""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .knowledge_file_service import KnowledgeFileDoc, list_md_files
from .knowledge_link_parser import parse_links

logger = logging.getLogger(__name__)


_DEFAULT_IMPLICIT_THRESHOLD = 0.75
_DEFAULT_IMPLICIT_MAX_PER_PAGE = 5

# 7색 팔레트 (계획서 §4.1 D10). community id 가 7 이상이면 modulo wrap.
_COMMUNITY_COLORS: List[str] = [
    "#22d3ee",  # cyan-400
    "#a78bfa",  # violet-400
    "#f472b6",  # pink-400
    "#fbbf24",  # amber-400
    "#34d399",  # emerald-400
    "#f87171",  # red-400
    "#60a5fa",  # blue-400
]


# ── env helpers ───────────────────────────────────────────────────────────


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.warning("env %s='%s' 파싱 실패 — default %s 사용", key, raw, default)
        return default


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("env %s='%s' 파싱 실패 — default %s 사용", key, raw, default)
        return default


# ── 임베딩 로딩 ───────────────────────────────────────────────────────────


def _load_page_embeddings(page_ids: List[str]) -> Dict[str, np.ndarray]:
    """ChromaDB ``knowledge_v2`` 에서 page_id 별 평균 임베딩을 로드.

    - 단일 청크면 그 청크 임베딩 그대로.
    - 다중 청크면 같은 ``page_id`` 의 모든 청크 임베딩을 평균 (L2 정규화 후 반환).
    - ChromaDB 에 없는 page_id 는 키 누락 (caller 가 처리).
    - 비정상 차원/NaN 행은 스킵.
    """
    if not page_ids:
        return {}

    try:
        from .embedding import get_vector_db
    except Exception as exc:  # noqa: BLE001
        logger.warning("vector_db import 실패: %s", exc)
        return {}

    try:
        vd = get_vector_db()
        vd._ensure_initialized()
    except Exception as exc:  # noqa: BLE001
        logger.warning("vector_db 초기화 실패: %s", exc)
        return {}

    # 전체 컬렉션을 한 번에 가져오는 게 가장 단순하고 효율적이다 (66 페이지 규모).
    try:
        res = vd._collection.get(include=["embeddings", "metadatas"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("vector_db get 실패: %s", exc)
        return {}

    ids = list(res.get("ids") or [])
    embs_raw = res.get("embeddings")
    metas = list(res.get("metadatas") or [])

    if embs_raw is None or len(embs_raw) == 0:
        return {}

    target = set(page_ids)
    buckets: Dict[str, List[np.ndarray]] = defaultdict(list)

    for i, row_id in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        # page_id 우선 — 단일 청크 row 의 경우 page_id 메타가 있으면 그것이 정답.
        page_id: Optional[str] = None
        if isinstance(meta, dict) and meta.get("page_id"):
            page_id = str(meta["page_id"])
        elif isinstance(row_id, str):
            if "#chunk-" in row_id:
                page_id = row_id.split("#chunk-", 1)[0]
            else:
                page_id = row_id

        if not page_id or page_id not in target:
            continue

        try:
            vec = np.asarray(embs_raw[i], dtype=np.float32)
        except Exception:  # noqa: BLE001
            continue
        if vec.ndim != 1 or vec.size == 0 or not np.all(np.isfinite(vec)):
            continue
        buckets[page_id].append(vec)

    out: Dict[str, np.ndarray] = {}
    for pid, vecs in buckets.items():
        if not vecs:
            continue
        # 차원 일관성 검사 — 다른 차원 섞이면 가장 흔한 차원만 채택.
        dims = [v.shape[0] for v in vecs]
        if len(set(dims)) > 1:
            from collections import Counter

            common_dim, _ = Counter(dims).most_common(1)[0]
            vecs = [v for v in vecs if v.shape[0] == common_dim]
            if not vecs:
                continue

        avg = np.mean(np.stack(vecs, axis=0), axis=0)
        norm = float(np.linalg.norm(avg))
        if norm > 0:
            avg = avg / norm
        out[pid] = avg.astype(np.float32)

    return out


# ── TF-IDF 키워드 (community label) ───────────────────────────────────────


_KEYWORD_TOKEN_RE = re.compile(r"[A-Za-z가-힣0-9]{2,}")
_KOREAN_STOPWORDS = {
    "그리고", "그러나", "또는", "이것", "저것", "위한", "관련", "관리",
    "사용", "있는", "있다", "하기", "되는", "수행", "처리", "통한",
    "통해", "대한", "대해", "기준", "기반", "이용", "방법", "정의",
    "내용", "확인", "필요", "안내", "지원", "서비스", "기능",
}
_ENGLISH_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "are", "was",
    "but", "not", "you", "your", "all", "use", "using", "based", "into",
    "about", "into", "have", "has", "had",
}


def _tokenize_titles_for_tfidf(titles: List[str]) -> List[str]:
    """TF-IDF 입력용 'document' 생성. 각 community 의 title 들을 하나의 문서로 본다."""
    docs: List[str] = []
    for t in titles:
        if not t:
            docs.append("")
            continue
        toks = _KEYWORD_TOKEN_RE.findall(t)
        cleaned = [
            tok for tok in toks
            if tok.lower() not in _ENGLISH_STOPWORDS and tok not in _KOREAN_STOPWORDS
        ]
        docs.append(" ".join(cleaned))
    return docs


def _build_community_labels(
    communities: List[List[str]],
    titles_by_id: Dict[str, str],
    *,
    top_k: int = 3,
) -> List[str]:
    """각 community 의 라벨을 TF-IDF top-k 키워드 join 으로 생성.

    sklearn 미설치 시에는 단순 빈도 기반 fallback (그래도 결정적).
    """
    if not communities:
        return []

    # community 별 title 모음을 1개 문서로
    docs_per_community: List[str] = []
    for members in communities:
        member_titles = [titles_by_id.get(mid, "") for mid in members]
        token_docs = _tokenize_titles_for_tfidf(member_titles)
        docs_per_community.append(" ".join(token_docs).strip())

    # 전부 빈 문서면 fallback
    if all(not d for d in docs_per_community):
        return [f"community-{i}" for i in range(len(communities))]

    labels: List[str] = []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        # 코퍼스 size 1 이면 sklearn 이 죽으므로 분기
        if len(docs_per_community) == 1:
            tokens = [t for t in docs_per_community[0].split() if t]
            from collections import Counter

            common = [tok for tok, _ in Counter(tokens).most_common(top_k)]
            return [" · ".join(common) if common else "community-0"]

        # min_df=1 — 짧은 코퍼스 보호. token pattern 은 위 tokenizer 와 정합.
        vectorizer = TfidfVectorizer(
            min_df=1,
            token_pattern=r"(?u)[A-Za-z가-힣0-9]{2,}",
        )
        matrix = vectorizer.fit_transform(docs_per_community)
        feature_names = vectorizer.get_feature_names_out()

        for i, members in enumerate(communities):
            row = matrix.getrow(i).toarray().ravel()
            if row.size == 0 or float(row.sum()) == 0.0:
                labels.append(f"community-{i}")
                continue
            top_idx = np.argsort(row)[::-1][:top_k]
            words = [str(feature_names[j]) for j in top_idx if row[j] > 0]
            labels.append(" · ".join(words) if words else f"community-{i}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("TF-IDF 라벨 생성 실패, 빈도 fallback: %s", exc)
        from collections import Counter

        for i, doc in enumerate(docs_per_community):
            tokens = [t for t in doc.split() if t]
            common = [tok for tok, _ in Counter(tokens).most_common(top_k)]
            labels.append(" · ".join(common) if common else f"community-{i}")

    return labels


# ── 필터 ─────────────────────────────────────────────────────────────────


def _apply_filters(
    docs: List[KnowledgeFileDoc],
    *,
    service: Optional[str],
    page_type: Optional[str],
    category: Optional[str],
) -> List[KnowledgeFileDoc]:
    out: List[KnowledgeFileDoc] = []
    for d in docs:
        if service and (d.service or "unknown") != service:
            continue
        if page_type and d.page_type != page_type:
            continue
        if category and d.category != category:
            continue
        out.append(d)
    return out


# ── core: build_graph ─────────────────────────────────────────────────────


def build_graph(
    *,
    service: Optional[str] = None,
    page_type: Optional[str] = None,
    category: Optional[str] = None,
    implicit_threshold: Optional[float] = None,
    implicit_max_per_page: Optional[int] = None,
) -> Dict[str, Any]:
    """위키 페이지 그래프를 구성하여 dict (camelCase) 응답으로 반환.

    Returns:
        {
            "nodes": [...],
            "edges": [...],
            "communities": [...],
            "meta": {"implicitThreshold": ..., "implicitMaxPerPage": ...,
                     "explicitEdgeCount": int, "implicitEdgeCount": int,
                     "communityCount": int},
        }
    """
    if implicit_threshold is None:
        implicit_threshold = _env_float(
            "KNOWLEDGE_IMPLICIT_THRESHOLD", _DEFAULT_IMPLICIT_THRESHOLD
        )
    if implicit_max_per_page is None:
        implicit_max_per_page = _env_int(
            "KNOWLEDGE_IMPLICIT_MAX_PER_PAGE", _DEFAULT_IMPLICIT_MAX_PER_PAGE
        )

    all_docs = list_md_files()
    kept_docs = _apply_filters(
        all_docs,
        service=service,
        page_type=page_type,
        category=category,
    )

    # 빈 그래프 처리
    if not kept_docs:
        return {
            "nodes": [],
            "edges": [],
            "communities": [],
            "meta": {
                "implicitThreshold": float(implicit_threshold),
                "implicitMaxPerPage": int(implicit_max_per_page),
                "explicitEdgeCount": 0,
                "implicitEdgeCount": 0,
                "communityCount": 0,
            },
        }

    kept_ids = [d.id for d in kept_docs]
    kept_id_set = set(kept_ids)
    title_by_id = {d.id: d.title for d in kept_docs}
    doc_by_id = {d.id: d for d in kept_docs}
    service_by_id = {d.id: (d.service or "unknown") for d in kept_docs}

    # backlink 카운트: 필터링된 페이지 내부 + 외부에서 들어오는 것 모두 — 필터된 집합의
    # in-degree 만 노출하면 충분 (계획서 응답형식에 단일 카운트). 정합성을 위해
    # 외부 페이지의 link 도 포함 (filter 무관 전체 기준).
    backlink_counts: Dict[str, int] = {pid: 0 for pid in kept_ids}
    for d in all_docs:
        for raw_target in (d.links or []):
            if raw_target in backlink_counts and raw_target != d.id:
                backlink_counts[raw_target] += 1

    # ── 1. explicit edges (재파싱 — frontmatter 의 links 와 일관성 보장) ──
    explicit_pairs: set[Tuple[str, str]] = set()
    explicit_edges: List[Dict[str, Any]] = []
    for d in kept_docs:
        # frontmatter 의 links 가 이미 있지만, 안전을 위해 재파싱 (deleted: 등 처리).
        targets = parse_links(d.content) or list(d.links or [])
        # dedup
        seen_targets: set[str] = set()
        for target in targets:
            if not target or target == d.id:
                continue
            if target in seen_targets:
                continue
            seen_targets.add(target)

            is_broken = target not in {x.id for x in all_docs}
            # implicit 후보에서 제외하기 위해 explicit 쌍은 양방향으로 기록.
            pair = tuple(sorted([d.id, target]))
            explicit_pairs.add(pair)  # type: ignore[arg-type]

            from_service = service_by_id.get(d.id, d.service or "unknown")
            to_service = (
                doc_by_id[target].service if target in doc_by_id
                else next(
                    (x.service or "unknown" for x in all_docs if x.id == target),
                    None,
                )
            )
            cross_service = (to_service is not None) and (to_service != from_service)

            explicit_edges.append({
                "from": d.id,
                "to": target,
                "isBroken": bool(is_broken),
                "crossService": bool(cross_service),
                "kind": "explicit",
                "weight": 1.0,
                "similarity": None,
            })

    # ── 2. implicit edges (cosine 기반) ───────────────────────────────────
    implicit_edges: List[Dict[str, Any]] = []
    embeddings = _load_page_embeddings(kept_ids)

    # 임베딩이 있는 페이지만 implicit 후보. 누락 페이지는 노드만 등록.
    embedded_ids = [pid for pid in kept_ids if pid in embeddings]

    if len(embedded_ids) >= 2:
        matrix = np.stack([embeddings[pid] for pid in embedded_ids], axis=0)
        # 이미 L2 정규화됨 → 내적 = cosine.
        sim = matrix @ matrix.T
        # 자기자신은 0 으로
        np.fill_diagonal(sim, 0.0)

        n = len(embedded_ids)
        # 각 행에서 threshold 초과 + explicit 중복 제외 + top-N 선택.
        added_pairs: set[Tuple[str, str]] = set()

        for i in range(n):
            from_id = embedded_ids[i]
            # (sim, j) 페어를 추려 top-N
            row = sim[i]
            order = np.argsort(row)[::-1]
            picked = 0
            for j in order:
                if j == i:
                    continue
                score = float(row[j])
                if score < implicit_threshold:
                    break  # 정렬되어 있으니 더 아래는 다 작음
                to_id = embedded_ids[int(j)]

                pair = tuple(sorted([from_id, to_id]))
                if pair in explicit_pairs:
                    continue  # explicit 우선
                if pair in added_pairs:
                    # 이미 다른 쪽 페이지에서 추가됨 — implicit 은 무방향이므로 1회만 출력
                    picked += 1
                    if picked >= implicit_max_per_page:
                        break
                    continue

                from_service = service_by_id.get(from_id, "unknown")
                to_service = service_by_id.get(to_id, "unknown")
                implicit_edges.append({
                    "from": from_id,
                    "to": to_id,
                    "isBroken": False,
                    "crossService": bool(from_service != to_service),
                    "kind": "implicit",
                    "weight": float(score),
                    "similarity": float(score),
                })
                added_pairs.add(pair)  # type: ignore[arg-type]
                picked += 1
                if picked >= implicit_max_per_page:
                    break

    # ── 3. networkx graph + Louvain community ─────────────────────────────
    import networkx as nx
    from networkx.algorithms.community import louvain_communities

    g = nx.Graph()
    for pid in kept_ids:
        g.add_node(pid)
    # 무방향 + weight: explicit=1.0, implicit=similarity. broken edge 도 community
    # 계산에는 약하게 기여 (target 이 kept 에 없으면 자동 skip).
    for e in explicit_edges:
        if e["to"] in kept_id_set:
            # 양방향 중복 방지 — networkx 가 multi-edge 거부 (Graph)
            if g.has_edge(e["from"], e["to"]):
                continue
            g.add_edge(e["from"], e["to"], weight=float(e["weight"]))
    for e in implicit_edges:
        if e["from"] in kept_id_set and e["to"] in kept_id_set:
            if g.has_edge(e["from"], e["to"]):
                continue
            g.add_edge(e["from"], e["to"], weight=float(e["weight"]))

    # Louvain — networkx 3.x. 단일 노드면 자기 자신이 community.
    communities_raw: List[List[str]] = []
    if g.number_of_nodes() > 0:
        try:
            comms = louvain_communities(g, weight="weight", resolution=1.0, seed=42)
            communities_raw = [sorted(list(c)) for c in comms]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Louvain 실패, 노드 1개씩 단일 community fallback: %s", exc)
            communities_raw = [[pid] for pid in kept_ids]

    # community id 할당 (size desc → 안정적)
    communities_raw.sort(key=lambda c: (-len(c), c[0] if c else ""))
    community_of: Dict[str, int] = {}
    for cid, members in enumerate(communities_raw):
        for m in members:
            community_of[m] = cid

    # ── 4. degree centrality → godScore (0~1 normalize) ───────────────────
    god_scores: Dict[str, float] = {}
    if g.number_of_nodes() > 0:
        centrality = nx.degree_centrality(g)  # nx 가 (n-1) 로 자동 정규화
        # nx degree_centrality 값 자체가 [0,1] 이지만 small graph 에서 max 가 1 일 수
        # 있으므로 max 기준 재정규화로 분포를 0~1 로 안정화한다.
        if centrality:
            max_c = max(centrality.values()) if centrality else 0.0
            if max_c > 0:
                god_scores = {nid: float(v) / float(max_c) for nid, v in centrality.items()}
            else:
                god_scores = {nid: 0.0 for nid in centrality.keys()}

    # ── 5. community labels (TF-IDF) ──────────────────────────────────────
    community_labels = _build_community_labels(communities_raw, title_by_id)

    # ── 6. nodes 응답 구성 ────────────────────────────────────────────────
    nodes: List[Dict[str, Any]] = []
    for d in sorted(kept_docs, key=lambda x: x.id):
        nid = d.id
        node_degree = int(g.degree(nid)) if g.has_node(nid) else 0
        nodes.append({
            "id": d.id,
            "title": d.title,
            "pageType": d.page_type,
            "category": d.category,
            "service": d.service or "unknown",
            "linksCount": len(d.links or []),
            "backlinksCount": int(backlink_counts.get(d.id, 0)),
            "community": int(community_of.get(d.id, -1)),
            "godScore": float(god_scores.get(d.id, 0.0)),
            "degree": node_degree,
        })

    # ── 7. edges 정렬 ─────────────────────────────────────────────────────
    # (from, to) 기준 단순 정렬. 기존 P3 테스트와의 호환성 유지를 위함이며,
    # client 가 kind 별로 필터링하려면 응답 객체의 ``kind`` 필드를 참조.
    all_edges = explicit_edges + implicit_edges
    all_edges.sort(key=lambda e: (e["from"], e["to"], e["kind"]))

    # ── 8. communities 응답 구성 ──────────────────────────────────────────
    communities_resp: List[Dict[str, Any]] = []
    for cid, members in enumerate(communities_raw):
        if not members:
            continue
        color = _COMMUNITY_COLORS[cid % len(_COMMUNITY_COLORS)]
        label = community_labels[cid] if cid < len(community_labels) else f"community-{cid}"
        communities_resp.append({
            "id": int(cid),
            "label": label,
            "size": int(len(members)),
            "color": color,
        })

    return {
        "nodes": nodes,
        "edges": all_edges,
        "communities": communities_resp,
        "meta": {
            "implicitThreshold": float(implicit_threshold),
            "implicitMaxPerPage": int(implicit_max_per_page),
            "explicitEdgeCount": int(len(explicit_edges)),
            "implicitEdgeCount": int(len(implicit_edges)),
            "communityCount": int(len(communities_resp)),
        },
    }


__all__ = ["build_graph"]
