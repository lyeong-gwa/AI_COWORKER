"""AI API 라우터 — 프롬프트 분석 후 적절한 API 자동 호출"""
import json
from typing import Any

import httpx
from sqlalchemy import select

from ...core.database import async_session_maker
from ...models.api_definition import ApiDefinition
from ...services.llm import chat
from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext
from ..common import render_url_or_header


def _api_def_from_snapshot(snap: dict) -> ApiDefinition:
    """apiSpecSnapshot dict → 세션에 추가하지 않는 transient ApiDefinition.

    이후 카탈로그 구성·실행 코드가 ORM 속성(.url_template 등)을 그대로 사용하도록
    스냅샷의 camelCase 키를 ORM 컬럼에 매핑한다. 불완전한 스냅샷은 ValueError.
    """
    if not isinstance(snap, dict):
        raise ValueError("apiSpecSnapshots 항목이 올바른 형식이 아닙니다")
    url_template = snap.get("urlTemplate")
    if not url_template:
        raise ValueError("apiSpecSnapshots 항목에 urlTemplate 이 없습니다")
    return ApiDefinition(
        id=snap.get("id") or "",
        name=snap.get("name") or "",
        description=snap.get("description") or "",
        method=snap.get("method") or "GET",
        url_template=url_template,
        headers=snap.get("headers") or {},
        body_template=snap.get("bodyTemplate"),
        auth_type=snap.get("authType") or "none",
        auth_config=snap.get("authConfig") or {},
        parameters=snap.get("parameters") or [],
        response_schema=snap.get("responseSchema") or {},
        is_active=True,
    )


@NodeHandlerRegistry.register
class AiApiRouterHandler(NodeHandler):
    node_type = "ai-api-router"
    category = "action"
    display_name = "AI API 라우터"
    description = "AI가 입력을 분석하여 적절한 API를 판단하고 자동 호출합니다"

    async def execute(self, node, input_data, ctx: ExecutionContext) -> Any:
        config = node.config

        snapshots = config.get("apiSpecSnapshots")

        # 0. 동결된 스냅샷 우선 (snapshot-first; 라이브 DB 조회 생략)
        if snapshots is not None:
            if not isinstance(snapshots, list):
                raise ValueError("apiSpecSnapshots 가 올바른 형식이 아닙니다")
            api_defs = [_api_def_from_snapshot(s) for s in snapshots]
        else:
            # 1. Load all active API definitions (스냅샷 없을 때 — 마이그레이션 이전 호환)
            async with async_session_maker() as api_db:
                result = await api_db.execute(
                    select(ApiDefinition).where(ApiDefinition.is_active == True)
                )
                api_defs = result.scalars().all()

            # Filter by selected API IDs (if configured)
            selected_ids = config.get("apiIds", [])
            if selected_ids:
                api_defs = [d for d in api_defs if d.id in selected_ids]

        if not api_defs:
            return {
                "api_route": {
                    "called": False,
                    "reason": "사용 가능한 API 정의가 없습니다",
                    "apiId": None,
                    "apiName": None,
                    "request": None,
                    "response": None,
                },
            }

        # 2. Build API catalog for LLM (including response_schema)
        api_catalog = []
        for api_def in api_defs:
            params_desc = []
            for p in (api_def.parameters or []):
                req = "필수" if p.get("required") else "선택"
                params_desc.append(
                    f"  - {p['name']} ({p.get('type', 'string')}, {req}, {p.get('in', 'body')}): {p.get('description', '')}"
                )

            entry = (
                f"[API ID: {api_def.id}]\n"
                f"이름: {api_def.name}\n"
                f"설명: {api_def.description}\n"
                f"메서드: {api_def.method} {api_def.url_template}\n"
                f"파라미터:\n" + ("\n".join(params_desc) if params_desc else "  (없음)")
            )

            # 응답 스키마 추가
            resp_schema = api_def.response_schema or {}
            resp_fields = resp_schema.get("fields", [])
            if resp_fields:
                resp_lines = []
                for f in resp_fields:
                    resp_lines.append(
                        f"  - {f.get('field', '')} ({f.get('type', 'string')}): {f.get('description', '')}"
                    )
                entry += f"\n응답 구조:\n" + "\n".join(resp_lines)

            resp_example = resp_schema.get("example")
            if resp_example:
                entry += f"\n응답 예시: {json.dumps(resp_example, ensure_ascii=False, default=str)}"

            api_catalog.append(entry)

        catalog_text = "\n\n---\n\n".join(api_catalog)

        # 3. Render user prompt template
        user_prompt = config.get("prompt", "")
        if user_prompt:
            user_prompt = ctx.render_template(user_prompt, input_data)

        # 4. Build analysis prompt
        input_summary = json.dumps(input_data, ensure_ascii=False, default=str, indent=2)

        system_prompt = f"""당신은 API 호출 판단 전문가입니다.

아래에 사용 가능한 API 목록과 현재 입력 데이터가 주어집니다.

## 사용 가능한 API 목록

{catalog_text}

## 판단 기준
1. 입력 데이터의 내용을 분석하여, 위 API 중 호출해야 할 적절한 API가 있는지 판단합니다.
2. API를 호출하려면 다음 두 조건이 **모두** 충족되어야 합니다:
   a) 질의에 대한 적절한 조치를 해줄 수 있는 **목적이 명확하게** 판단되어야 합니다
   b) 해당 API를 호출하기 위한 **필수 파라미터 데이터가 모두** 입력 데이터에 준비되어 있어야 합니다
3. 조건이 충족되지 않으면 호출하지 않습니다.
4. 적절한 API가 **하나도 없다면 반드시 호출하지 않음**으로 판단하세요. 무리하게 호출하지 마세요.

## 응답 형식
반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요.

호출하는 경우:
{{"shouldCall": true, "reason": "판단 근거", "apiId": "API의 ID", "parameters": {{"param1": "value1"}}}}

호출하지 않는 경우 (적절한 API가 없거나 데이터가 부족한 경우):
{{"shouldCall": false, "reason": "호출하지 않는 구체적 이유", "apiId": null, "parameters": null}}"""

        user_message = f"""## 입력 데이터
{input_summary}"""
        if user_prompt:
            user_message = f"""## 추가 지시사항
{user_prompt}

{user_message}"""

        # 5. Call LLM for decision (시스템 기본 LLM 사용)
        llm_result = await chat(
            prompt=user_message,
            system_prompt=system_prompt,
            temperature=0.2,
            max_tokens=1000,
        )
        llm_response = llm_result.content

        # 6. Parse LLM response
        try:
            cleaned = llm_response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            decision = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            return {
                "api_route": {
                    "called": False,
                    "reason": f"AI 응답 파싱 실패: {llm_response[:200]}",
                    "apiId": None,
                    "apiName": None,
                    "request": None,
                    "response": None,
                },
            }

        should_call = decision.get("shouldCall", False)
        reason = decision.get("reason", "")
        api_id = decision.get("apiId")
        parameters = decision.get("parameters") or {}

        if not should_call or not api_id:
            return {
                "api_route": {
                    "called": False,
                    "reason": reason,
                    "apiId": None,
                    "apiName": None,
                    "request": None,
                    "response": None,
                },
            }

        # 7. Find the matched API definition
        matched_def = None
        for api_def in api_defs:
            if api_def.id == api_id:
                matched_def = api_def
                break

        if not matched_def:
            return {
                "api_route": {
                    "called": False,
                    "reason": f"AI가 선택한 API({api_id})를 찾을 수 없습니다",
                    "apiId": api_id,
                    "apiName": None,
                    "request": None,
                    "response": None,
                },
            }

        # 8. Execute API call
        url = render_url_or_header(matched_def.url_template, parameters, ctx.render_template)

        rendered_headers = {}
        if isinstance(matched_def.headers, dict):
            rendered_headers = {
                k: render_url_or_header(str(v), parameters, ctx.render_template)
                for k, v in matched_def.headers.items()
            }

        # Auth handling
        auth_type = matched_def.auth_type
        auth_config = matched_def.auth_config or {}
        if auth_type == "bearer":
            token = auth_config.get("token", "")
            rendered_token = render_url_or_header(token, parameters, ctx.render_template)
            if rendered_token:
                rendered_headers["Authorization"] = f"Bearer {rendered_token}"
        elif auth_type == "api_key":
            key_name = auth_config.get("headerName", "X-API-Key")
            key_value = auth_config.get("apiKey", "")
            rendered_headers[key_name] = render_url_or_header(key_value, parameters, ctx.render_template)

        # Remove empty headers
        rendered_headers = {
            k: v for k, v in rendered_headers.items()
            if v and str(v).strip() and str(v).strip() != "Bearer"
        }

        body = None
        if matched_def.body_template and matched_def.method.upper() in ["POST", "PUT", "PATCH"]:
            body = ctx.render_template(matched_def.body_template, parameters)

        # Execute HTTP request
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method=matched_def.method.upper(),
                url=url,
                headers=rendered_headers,
                content=body,
            )

            try:
                response_data = response.json()
            except Exception:
                response_data = response.text

            return {
                "api_route": {
                    "called": True,
                    "reason": reason,
                    "apiId": matched_def.id,
                    "apiName": matched_def.name,
                    "request": {
                        "method": matched_def.method.upper(),
                        "url": url,
                        "parameters": parameters,
                        "body": body,
                    },
                    "response": {
                        "status": response.status_code,
                        "data": response_data,
                    },
                },
            }
