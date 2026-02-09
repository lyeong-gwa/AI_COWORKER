"""
Node Executor Service

AI 노드 실행 로직:
1. 도구 실행
2. 지식 베이스 검색
3. 프롬프트 렌더링
4. LLM 호출
5. 출력 검증
"""

import time
import json
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import jsonschema

from ..models.node import AINode
from ..models.tool import ToolDefinition
from ..models.knowledge import KnowledgeDocument
from ..schemas.node import NodeTestResponse
from ..core.config import settings
from .tool_executor import execute_tool, ToolExecutionResult
from .llm_client import call_llm


async def execute_node(
    node: AINode,
    input_data: Dict[str, Any],
    db: AsyncSession,
    mock_tool_results: Optional[Dict[str, Any]] = None,
    mock_knowledge: Optional[str] = None,
) -> NodeTestResponse:
    """
    AI 노드 실행

    Args:
        node: AI 노드 모델
        input_data: 입력 데이터
        db: DB 세션
        mock_tool_results: 테스트용 도구 결과 목업
        mock_knowledge: 테스트용 지식 목업

    Returns:
        NodeTestResponse: 실행 결과
    """
    start_time = time.perf_counter()
    logs: List[Dict[str, Any]] = []

    def log(level: str, message: str, data: Any = None):
        logs.append({
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message,
            "data": data,
        })

    try:
        # 1. 입력 검증
        log("info", "입력 데이터 검증 시작")
        try:
            jsonschema.validate(input_data, node.input_schema)
            log("info", "입력 검증 통과")
        except jsonschema.ValidationError as e:
            log("error", f"입력 검증 실패: {e.message}")
            raise ValueError(f"입력 검증 실패: {e.message}")

        # 2. 도구 실행
        tool_results: Dict[str, Any] = {}

        if mock_tool_results is not None:
            # 테스트 모드: 목업 데이터 사용
            tool_results = mock_tool_results
            log("info", "테스트 모드: 도구 결과 목업 사용")
        elif node.linked_tool_ids:
            log("info", f"도구 실행 시작 ({len(node.linked_tool_ids)}개)")

            for tool_id in node.linked_tool_ids:
                # 도구 조회
                result = await db.execute(
                    select(ToolDefinition).where(ToolDefinition.id == tool_id)
                )
                tool = result.scalar_one_or_none()

                if not tool:
                    log("warning", f"도구를 찾을 수 없음: {tool_id}")
                    continue

                log("info", f"도구 실행: {tool.name}")

                # 도구 실행
                tool_result: ToolExecutionResult = await execute_tool(tool, input_data)

                if tool_result.success:
                    tool_results[tool_id] = tool_result.output
                    log("info", f"도구 성공: {tool.name}", {"output_preview": str(tool_result.output)[:100]})
                else:
                    log("error", f"도구 실패: {tool.name}", {"error": tool_result.error})
                    tool_results[tool_id] = {"error": tool_result.error}

        # 3. 지식 베이스 검색
        knowledge_context = ""

        if mock_knowledge is not None:
            # 테스트 모드
            knowledge_context = mock_knowledge
            log("info", "테스트 모드: 지식 목업 사용")
        elif node.linked_knowledge_ids:
            log("info", f"지식 검색 시작 ({len(node.linked_knowledge_ids)}개)")

            knowledge_docs = []
            for doc_id in node.linked_knowledge_ids:
                result = await db.execute(
                    select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
                )
                doc = result.scalar_one_or_none()
                if doc:
                    knowledge_docs.append(f"# {doc.title}\n{doc.content}")

            knowledge_context = "\n\n---\n\n".join(knowledge_docs)
            log("info", f"지식 컨텍스트 생성 완료 ({len(knowledge_context)} chars)")

        # 4. 프롬프트 렌더링
        log("info", "프롬프트 렌더링 시작")

        rendered_prompt = render_prompt(
            template=node.prompt_template,
            input_data=input_data,
            tool_results=tool_results,
            knowledge=knowledge_context,
        )

        # 출력 스키마 주입 (설정된 경우)
        if node.output_enforcement.get('enabled') and node.output_enforcement.get('includeSchemaInPrompt'):
            schema_instruction = _build_schema_instruction(
                node.output_schema,
                node.output_enforcement.get('exampleOutput'),
            )
            rendered_prompt = f"{rendered_prompt}\n\n{schema_instruction}"
            log("info", "출력 스키마 프롬프트에 주입됨")

        log("info", f"렌더링된 프롬프트 ({len(rendered_prompt)} chars)")

        # 5. LLM 호출
        log("info", "LLM 호출 시작")

        model_config = node.model_config or {}
        llm_response, token_usage = await call_llm(
            prompt=rendered_prompt,
            provider=model_config.get('provider', settings.DEFAULT_LLM_PROVIDER),
            model=model_config.get('model', settings.DEFAULT_MODEL),
            temperature=model_config.get('temperature', 0.7),
            max_tokens=model_config.get('maxTokens', 2000),
        )

        log("info", "LLM 응답 수신", {"tokens": token_usage})

        # 6. 출력 파싱 및 검증
        output = None
        validation_passed = None
        validation_errors = []

        try:
            # JSON 파싱 시도
            output = json.loads(llm_response)
            log("info", "JSON 파싱 성공")

            # 출력 검증 (설정된 경우)
            if node.output_enforcement.get('validationEnabled'):
                try:
                    jsonschema.validate(output, node.output_schema)
                    validation_passed = True
                    log("info", "출력 검증 통과")
                except jsonschema.ValidationError as e:
                    validation_passed = False
                    validation_errors.append(str(e.message))
                    log("warning", f"출력 검증 실패: {e.message}")

                    # 재시도 (설정된 경우)
                    if node.output_enforcement.get('retryOnFailure'):
                        max_retries = node.output_enforcement.get('maxRetries', 3)
                        log("info", f"재시도 시작 (최대 {max_retries}회)")

                        for retry in range(max_retries):
                            retry_prompt = f"{rendered_prompt}\n\n[이전 응답이 스키마와 맞지 않습니다. 오류: {e.message}. 다시 시도해주세요.]"

                            llm_response, _ = await call_llm(
                                prompt=retry_prompt,
                                provider=model_config.get('provider', settings.DEFAULT_LLM_PROVIDER),
                                model=model_config.get('model', settings.DEFAULT_MODEL),
                                temperature=model_config.get('temperature', 0.7),
                                max_tokens=model_config.get('maxTokens', 2000),
                            )

                            try:
                                output = json.loads(llm_response)
                                jsonschema.validate(output, node.output_schema)
                                validation_passed = True
                                validation_errors = []
                                log("info", f"재시도 {retry + 1}회 성공")
                                break
                            except (json.JSONDecodeError, jsonschema.ValidationError) as retry_error:
                                validation_errors.append(f"재시도 {retry + 1}: {str(retry_error)}")
                                log("warning", f"재시도 {retry + 1}회 실패")

        except json.JSONDecodeError:
            # JSON이 아닌 텍스트 응답
            output = llm_response
            log("info", "텍스트 응답 (JSON 아님)")

        execution_time_ms = (time.perf_counter() - start_time) * 1000

        return NodeTestResponse(
            success=True,
            output=output,
            logs=logs,
            rendered_prompt=rendered_prompt,
            tool_results=tool_results if tool_results else None,
            llm_response=llm_response,
            validation_passed=validation_passed,
            validation_errors=validation_errors if validation_errors else None,
            execution_time_ms=execution_time_ms,
            token_usage=token_usage,
        )

    except Exception as e:
        execution_time_ms = (time.perf_counter() - start_time) * 1000
        log("error", f"노드 실행 실패: {str(e)}")

        return NodeTestResponse(
            success=False,
            error=str(e),
            error_type=type(e).__name__,
            logs=logs,
            execution_time_ms=execution_time_ms,
        )


def render_prompt(
    template: str,
    input_data: Dict[str, Any],
    tool_results: Dict[str, Any],
    knowledge: str,
) -> str:
    """
    프롬프트 템플릿 렌더링

    변수 형식:
    - {{input.fieldName}} - 입력 데이터
    - {{toolResults.toolId}} - 도구 실행 결과
    - {{knowledge}} - 지식 베이스 컨텍스트
    """
    result = template

    # {{input.xxx}} 치환
    def replace_input(match):
        path = match.group(1)
        keys = path.split('.')
        value = input_data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key, '')
            else:
                return ''
        return str(value) if value is not None else ''

    result = re.sub(r'\{\{input\.([^}]+)\}\}', replace_input, result)

    # {{toolResults.xxx}} 치환
    def replace_tool(match):
        tool_id = match.group(1)
        value = tool_results.get(tool_id, '')
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value) if value is not None else ''

    result = re.sub(r'\{\{toolResults\.([^}]+)\}\}', replace_tool, result)

    # {{knowledge}} 치환
    result = result.replace('{{knowledge}}', knowledge)

    return result


def _build_schema_instruction(schema: Dict[str, Any], example: Optional[str]) -> str:
    """출력 스키마 지시문 생성"""
    instruction = """
## 출력 형식 요구사항

반드시 아래 JSON 스키마에 맞게 응답하세요:

```json
{schema}
```
""".format(schema=json.dumps(schema, ensure_ascii=False, indent=2))

    if example:
        instruction += f"""
### 예시 출력

```json
{example}
```
"""

    instruction += """
중요: 응답은 반드시 유효한 JSON 형식이어야 합니다. 추가 설명이나 마크다운 없이 JSON만 반환하세요.
"""

    return instruction
