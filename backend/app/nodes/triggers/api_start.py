"""API 시작 노드 핸들러 — 외부 API 호출 후 응답을 출력으로 전달"""
from typing import Any, Dict

import httpx
from sqlalchemy import select

from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class ApiStartHandler(NodeHandler):
    node_type = "api-start"
    category = "trigger"
    display_name = "API 시작"
    description = "API 정의를 읽어 호출하고 응답을 반환합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config or {}
        api_def_id = config.get('apiDefinitionId')
        doc_id = config.get('docId')
        default_params = config.get('defaultParams', {})

        # 수동 트리거 입력과 기본 파라미터 병합 (벨트 데이터가 우선)
        params = {**default_params, **input_data}

        method = 'GET'
        url_template = ''
        headers_raw = {}
        body_template = None
        auth_type = 'none'
        auth_config = {}

        # 1. ApiDefinition DB에서 로드 (우선)
        if api_def_id:
            from ...models.api_definition import ApiDefinition
            result = await ctx.db.execute(
                select(ApiDefinition).where(ApiDefinition.id == api_def_id)
            )
            api_def = result.scalar_one_or_none()
            if api_def:
                method = api_def.method
                url_template = api_def.url_template
                headers_raw = api_def.headers or {}
                body_template = api_def.body_template
                auth_type = api_def.auth_type
                auth_config = api_def.auth_config or {}
            else:
                return {"error": f"API 정의를 찾을 수 없습니다: {api_def_id}", "status": 0, "data": None}

        # 2. 레거시: 지식 문서에서 로드
        elif doc_id:
            from ...services.knowledge_file_service import read_md_file
            doc = read_md_file(doc_id)
            if not doc:
                return {"error": f"API 문서를 찾을 수 없습니다: {doc_id}", "status": 0, "data": None}
            api_meta = doc.extra_metadata.get('api', {})
            if not api_meta:
                return {"error": "API 메타데이터가 없습니다", "status": 0, "data": None}
            method = api_meta.get('method', 'GET')
            url_template = api_meta.get('url', '')
            headers_raw = api_meta.get('headers', {})
            body_template = api_meta.get('bodyTemplate')
        else:
            return {"error": "API 문서가 선택되지 않았습니다", "status": 0, "data": None}

        # 파라미터로 템플릿 렌더링
        url = ctx.render_template(url_template, params)

        rendered_headers = {}
        if isinstance(headers_raw, dict):
            rendered_headers = {
                k: ctx.render_template(str(v), params)
                for k, v in headers_raw.items()
            }

        # 인증 처리 (ApiDefinition에서 로드한 경우)
        if auth_type == 'bearer':
            token = auth_config.get('token', '')
            rendered_token = ctx.render_template(token, params)
            if rendered_token:
                rendered_headers['Authorization'] = f"Bearer {rendered_token}"
        elif auth_type == 'api_key':
            key_name = auth_config.get('headerName', 'X-API-Key')
            key_value = auth_config.get('apiKey', '')
            rendered_headers[key_name] = ctx.render_template(key_value, params)

        # 빈 값 헤더 제거 (Bearer 뒤 토큰 없는 경우 등)
        rendered_headers = {
            k: v for k, v in rendered_headers.items()
            if v and str(v).strip() and str(v).strip() != "Bearer"
        }

        body = None
        if body_template and method.upper() in ['POST', 'PUT', 'PATCH']:
            body = ctx.render_template(body_template, params)

        # HTTP 요청 실행
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                headers=rendered_headers,
                content=body,
            )

            try:
                response_data = response.json()
            except Exception:
                response_data = response.text

            return {
                "status": response.status_code,
                "data": response_data,
            }
