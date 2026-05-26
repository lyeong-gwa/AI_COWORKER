"""API 문서 기반 직접 호출 노드 핸들러 (LLM 없이 API 실행)"""
from typing import Any, Dict, List
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

import httpx
from sqlalchemy import select

from ...core.database import async_session_maker
from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext
from ..common import render_url_or_header


@NodeHandlerRegistry.register
class ApiCallHandler(NodeHandler):
    node_type = "api-call"
    category = "action"
    display_name = "API 호출"
    description = "API 정의를 기반으로 직접 HTTP 호출을 실행합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config
        api_def_id = config.get("apiDefinitionId")
        doc_id = config.get("docId")

        method = "GET"
        url_template = ""
        headers_raw = {}
        body_template = None
        auth_type = "none"
        auth_config = {}
        api_parameters: List[Dict[str, Any]] = []

        # 1. ApiDefinition DB에서 로드 (우선)
        if api_def_id:
            from ...models.api_definition import ApiDefinition
            async with async_session_maker() as api_db:
                result = await api_db.execute(
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
                api_parameters = api_def.parameters or []
            else:
                raise ValueError(f"API 정의를 찾을 수 없습니다: {api_def_id}")

        # 2. 레거시: 지식 문서에서 로드
        elif doc_id:
            from ...services.knowledge_file_service import read_md_file
            doc = read_md_file(doc_id)
            if not doc:
                raise ValueError(f"API 문서를 찾을 수 없습니다: {doc_id}")
            api_meta = doc.extra_metadata.get("api", {})
            if not api_meta:
                raise ValueError(f"API 메타데이터가 없습니다: {doc_id}")
            method = api_meta.get("method", "GET")
            url_template = api_meta.get("url", "")
            headers_raw = api_meta.get("headers", {})
            body_template = api_meta.get("bodyTemplate")
        else:
            raise ValueError("API 문서가 선택되지 않았습니다")

        # 우선순위: 업스트림 입력(input_data) > 노드 기본값(defaultParams)
        default_params = config.get('defaultParams', {}) or {}
        params = {**default_params, **(input_data or {})}

        # Render templates with params
        url = render_url_or_header(url_template, params, ctx.render_template)

        # API 정의의 query 파라미터를 URL에 자동 추가
        query_params = {}
        for p in api_parameters:
            if p.get('in') == 'query':
                p_name = p.get('name', '')
                if not p_name:
                    continue
                if p_name in params and params[p_name] not in (None, ""):
                    query_params[p_name] = str(params[p_name])
                elif p.get('default') not in (None, ""):
                    query_params[p_name] = str(p['default'])
        if query_params:
            parsed = urlparse(url)
            existing_qs = parse_qs(parsed.query, keep_blank_values=True)
            for k, v in query_params.items():
                existing_qs[k] = [v]
            new_qs = urlencode(existing_qs, doseq=True)
            url = urlunparse(parsed._replace(query=new_qs))

        rendered_headers = {}
        if isinstance(headers_raw, dict):
            rendered_headers = {
                k: render_url_or_header(str(v), params, ctx.render_template)
                for k, v in headers_raw.items()
            }

        # 인증 처리 (ApiDefinition에서 로드한 경우)
        if auth_type == "bearer":
            token = auth_config.get("token", "")
            rendered_token = render_url_or_header(token, params, ctx.render_template)
            if rendered_token:
                rendered_headers["Authorization"] = f"Bearer {rendered_token}"
        elif auth_type == "api_key":
            key_name = auth_config.get("headerName", "X-API-Key")
            key_value = auth_config.get("apiKey", "")
            rendered_headers[key_name] = render_url_or_header(key_value, params, ctx.render_template)

        # 빈 값 헤더 제거 (Bearer 뒤 토큰 없는 경우 등)
        rendered_headers = {
            k: v for k, v in rendered_headers.items()
            if v and str(v).strip() and str(v).strip() != "Bearer"
        }

        body = None
        if body_template and method.upper() in ['POST', 'PUT', 'PATCH']:
            body = ctx.render_template(body_template, params)

        # Execute HTTP request
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
