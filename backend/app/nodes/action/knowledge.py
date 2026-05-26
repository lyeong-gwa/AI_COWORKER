"""지식 검색 노드 핸들러

Karpathy v2 P3 (`.omc/plans/지식-karpathy-v2.md` §6.3):
  - 신규 config: ``pageTypes`` (list), ``minScore`` (float), ``expandBacklinks`` (bool)
  - 응답에 ``page_type``, ``version``, ``links``, ``search_page_types`` 추가
  - ``categories`` 와 ``pageTypes`` 결합 시 ChromaDB ``$and`` 사용
  - ``expandBacklinks=true`` → hit 의 1-hop backlink 페이지를 추가 (``isBacklinkExpansion=true``)

Multi-service v3 P2 (`.omc/plans/지식-multi-service.md` §2.6):
  - 신규 config: ``services`` (list)
  - ``categories`` / ``pageTypes`` / ``services`` 모두 동시 결합 가능 (``$and``)
  - 응답 페이로드 item 에 ``service`` 필드 추가
  - 응답 result 에 ``search_services`` 추가 (config.services 설정 시)
"""
from typing import Any, Dict, List, Optional

from ...core.constants import BeltKey, KNOWLEDGE_MIN_RESULTS, KNOWLEDGE_MAX_RESULTS
from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class KnowledgeHandler(NodeHandler):
    node_type = "knowledge"
    category = "action"
    display_name = "지식 검색"
    description = "지식 베이스에서 유사 문서를 검색합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config or {}
        search_field = config.get('searchField', '')
        # Support new multi-category format with backward compat for single category
        categories = config.get('categories', [])
        if not categories:
            old_cat = config.get('category', '')
            if old_cat:
                categories = [old_cat]
        tags = config.get('tags', [])
        max_results = min(
            KNOWLEDGE_MAX_RESULTS,
            max(KNOWLEDGE_MIN_RESULTS, config.get('maxResults', 5)),
        )

        # ── Karpathy v2 P3 신규 파라미터 ───────────────────────────────────
        page_types_cfg = config.get('pageTypes', []) or []
        if not isinstance(page_types_cfg, list):
            page_types_cfg = []
        page_types: List[str] = [str(pt) for pt in page_types_cfg if pt]

        # ── Multi-service v3 P2 §2.6 신규 파라미터 ─────────────────────────
        services_cfg = config.get('services', []) or []
        if isinstance(services_cfg, str):
            services_cfg = [services_cfg] if services_cfg else []
        if not isinstance(services_cfg, list):
            services_cfg = []
        services: List[str] = [str(s) for s in services_cfg if s]

        try:
            min_score = float(config.get('minScore', 0.0))
        except (TypeError, ValueError):
            min_score = 0.0

        expand_backlinks = bool(config.get('expandBacklinks', False))

        flat_input = input_data

        # 입력 데이터에서 검색 쿼리 추출
        query = ''
        if search_field:
            val = ctx.get_nested_value(flat_input, search_field)
            if val is not None:
                query = str(val)

        if not query:
            # Fallback: 플래트닝된 데이터의 모든 문자열 값을 결합
            str_values = [str(v) for v in flat_input.values() if isinstance(v, str)]
            query = ' '.join(str_values)

        if not query:
            # 카테고리가 설정된 경우, 카테고리명으로 검색 (전체 카테고리 문서 조회)
            if categories:
                query = ' '.join(categories)
            else:
                return {'knowledge': [], BeltKey.KNOWLEDGE_ERROR: '검색 쿼리를 추출할 수 없습니다'}

        # 벡터 DB로 유사도 검색
        from ...services.embedding.vector_db import get_vector_db

        try:
            vector_db = get_vector_db()

            # ChromaDB 필터 구성 — categories + pageTypes + services 결합 시 $and 사용
            # (Multi-service v3 P2 §2.6 — services 추가)
            cat_filter: Optional[Dict[str, Any]] = None
            if categories:
                if len(categories) == 1:
                    cat_filter = {'category': categories[0]}
                else:
                    cat_filter = {'category': {'$in': categories}}

            pt_filter: Optional[Dict[str, Any]] = None
            if page_types:
                if len(page_types) == 1:
                    pt_filter = {'page_type': page_types[0]}
                else:
                    pt_filter = {'page_type': {'$in': page_types}}

            svc_filter: Optional[Dict[str, Any]] = None
            if services:
                if len(services) == 1:
                    svc_filter = {'service': services[0]}
                else:
                    svc_filter = {'service': {'$in': services}}

            clauses = [c for c in (cat_filter, pt_filter, svc_filter) if c]
            if len(clauses) >= 2:
                where_filter = {'$and': clauses}
            elif len(clauses) == 1:
                where_filter = clauses[0]
            else:
                where_filter = None

            # 검색 실행 (chunk-aware dedup 은 vector_db.search 가 내부 처리)
            results = vector_db.search(
                query=query,
                top_k=max_results,
                where=where_filter,
                min_score=min_score,
            )

            knowledge_items: List[Dict[str, Any]] = []
            seen_ids: set[str] = set()

            for sr in results:
                # P3 §6.3 응답 — page_type / version / links 노출
                item = self._build_item(sr)

                # 태그 필터 (벡터 DB 필터가 지원하지 않는 태그 교차 필터링)
                if tags:
                    item_tags = item.get('tags', '')
                    if isinstance(item_tags, str):
                        item_tags = [t.strip() for t in item_tags.split(',') if t.strip()]
                    if not any(t in item_tags for t in tags):
                        continue

                # min_score 는 vector_db.search 가 1차 필터 (chunk-level).
                # page-level 결과 score 도 한 번 더 확인 (안전망).
                if sr.score < min_score:
                    continue

                knowledge_items.append(item)
                seen_ids.add(item['id'])

            # 1-hop backlink 확장 (P3 §6.3 expandBacklinks)
            if expand_backlinks and knowledge_items:
                expansion = self._expand_backlinks(
                    page_ids=[it['id'] for it in knowledge_items],
                    already=seen_ids,
                    category_filter=categories,
                    page_type_filter=page_types,
                )
                knowledge_items.extend(expansion)

            # 지식 검색 결과 + 카테고리/페이지타입/서비스 반환
            result: Dict[str, Any] = {'knowledge': knowledge_items}
            if categories:
                result['search_categories'] = categories
            if page_types:
                result['search_page_types'] = page_types
            if services:
                # Multi-service v3 P2 §2.6 — 사용된 service 필터 노출
                result['search_services'] = services
            return result

        except Exception as e:
            # 검색 실패 시 빈 결과 + 에러 정보 (입력 데이터는 _passthrough로 처리)
            return {'knowledge': [], BeltKey.KNOWLEDGE_ERROR: str(e)}

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _build_item(sr: Any) -> Dict[str, Any]:
        """SearchResult → response item (P3 §6.3 + multi-service v3 P2 §2.6 응답 shape).

        ``page_type``, ``version``, ``links``, ``service`` 노출. 메타에 없으면 default.
        """
        meta = sr.metadata or {}

        # links 는 ChromaDB 가 list → "a,b" 문자열로 저장. 다시 split.
        links_raw = meta.get('links', '')
        if isinstance(links_raw, str):
            links_list = [s.strip() for s in links_raw.split(',') if s.strip()]
        elif isinstance(links_raw, list):
            links_list = [str(s) for s in links_raw]
        else:
            links_list = []

        try:
            version_v = int(meta.get('version', 1))
        except (TypeError, ValueError):
            version_v = 1

        return {
            'id': sr.id,
            'title': meta.get('title', sr.id),
            'content': sr.content,
            'score': sr.score,
            'category': meta.get('category', ''),
            'service': meta.get('service', 'unknown'),
            'tags': meta.get('tags', ''),
            'page_type': meta.get('page_type', 'Summary'),
            'version': version_v,
            'links': links_list,
        }

    @staticmethod
    def _expand_backlinks(
        page_ids: List[str],
        already: set,
        category_filter: List[str],
        page_type_filter: List[str],
    ) -> List[Dict[str, Any]]:
        """hit 페이지를 가리키는 1-hop backlink 페이지를 추가.

        파일 스캔으로 ``[[page_id]]`` 보유 페이지 검출. 동일 카테고리/페이지타입
        필터가 있으면 추가 결과에도 동일 필터를 적용.
        """
        from ...services.knowledge_file_service import list_md_files
        from ...services.knowledge_link_parser import has_link_to

        all_docs = list_md_files()
        cat_set = set(category_filter or [])
        pt_set = set(page_type_filter or [])

        out: List[Dict[str, Any]] = []
        seen_local: set = set(already)
        for target_id in page_ids:
            for d in all_docs:
                if d.id in seen_local:
                    continue
                if cat_set and d.category not in cat_set:
                    continue
                if pt_set and d.page_type not in pt_set:
                    continue
                if has_link_to(d.content, target_id):
                    out.append({
                        'id': d.id,
                        'title': d.title,
                        'content': d.content,
                        'score': 0.0,
                        'category': d.category,
                        'service': d.service or 'unknown',
                        'tags': ','.join(d.tags) if d.tags else '',
                        'page_type': d.page_type,
                        'version': d.version,
                        'links': list(d.links),
                        'isBacklinkExpansion': True,
                    })
                    seen_local.add(d.id)
        return out
