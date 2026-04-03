"""지식 검색 노드 핸들러"""
from typing import Any, Dict

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

            # ChromaDB 필터 구성
            where_filter = None
            if categories:
                if len(categories) == 1:
                    where_filter = {'category': categories[0]}
                else:
                    where_filter = {'category': {'$in': categories}}

            # 검색 실행
            results = vector_db.search(
                query=query,
                top_k=max_results,
                where=where_filter,
            )

            knowledge_items = []
            for sr in results:
                item = {
                    'id': sr.id,
                    'content': sr.content,
                    'score': sr.score,
                    'title': sr.metadata.get('title', sr.id),
                    'category': sr.metadata.get('category', ''),
                    'tags': sr.metadata.get('tags', ''),
                }

                # 태그 필터 (벡터 DB 필터가 지원하지 않는 태그 교차 필터링)
                if tags:
                    item_tags = item.get('tags', '')
                    if isinstance(item_tags, str):
                        item_tags = [t.strip() for t in item_tags.split(',') if t.strip()]
                    if not any(t in item_tags for t in tags):
                        continue

                knowledge_items.append(item)

            # 지식 검색 결과 + 카테고리 반환 (입력 데이터는 _passthrough로 프레임워크가 처리)
            result = {'knowledge': knowledge_items}
            if categories:
                result['search_categories'] = categories
            return result

        except Exception as e:
            # 검색 실패 시 빈 결과 + 에러 정보 (입력 데이터는 _passthrough로 처리)
            return {'knowledge': [], BeltKey.KNOWLEDGE_ERROR: str(e)}
