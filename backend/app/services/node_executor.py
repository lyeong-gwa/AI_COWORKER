"""
Node Executor Service

AI 노드 실행 로직:
1. 입력 검증
2. 프롬프트 렌더링
3. LLM 호출
4. 출력 검증
"""

import time
import json
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
import jsonschema

from ..models.node import AINode
from ..schemas.node import NodeTestResponse
from ..core.config import settings
from .llm_client import call_llm


async def execute_node(
    node: AINode,
    input_data: Dict[str, Any],
    db: AsyncSession,
) -> NodeTestResponse:
    """
    AI 노드 실행

    Args:
        node: AI 노드 모델
        input_data: 입력 데이터
        db: DB 세션

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
        # 스키마 정규화 (DB에서 문자열로 저장된 경우 처리)
        input_schema = _normalize_schema(node.input_schema)
        output_schema = _normalize_schema(node.output_schema)

        # 1. 입력 검증
        log("info", "입력 데이터 검증 시작")
        try:
            jsonschema.validate(input_data, input_schema)
            log("info", "입력 검증 통과")
        except jsonschema.ValidationError as e:
            log("error", f"입력 검증 실패: {e.message}")
            raise ValueError(f"입력 검증 실패: {e.message}")

        # 2. 프롬프트 렌더링
        log("info", "프롬프트 렌더링 시작")

        rendered_prompt = render_prompt(
            template=node.user_prompt_template,
            input_data=input_data,
        )

        # 출력 스키마 주입 (설정된 경우)
        if node.output_enforcement.get('enabled') and node.output_enforcement.get('includeSchemaInPrompt'):
            schema_instruction = _build_schema_instruction(
                output_schema,
                node.output_enforcement.get('exampleOutput'),
            )
            rendered_prompt = f"{rendered_prompt}\n\n{schema_instruction}"
            log("info", "출력 스키마 프롬프트에 주입됨")

        log("info", f"렌더링된 프롬프트 ({len(rendered_prompt)} chars)")

        # 3. LLM 호출
        log("info", "LLM 호출 시작")

        model_config = node.llm_config or {}
        llm_response, token_usage = await call_llm(
            prompt=rendered_prompt,
            provider=model_config.get('provider', settings.DEFAULT_LLM_PROVIDER),
            model=model_config.get('model', settings.DEFAULT_MODEL),
            temperature=model_config.get('temperature', 0.7),
            max_tokens=model_config.get('maxTokens', 2000),
        )

        log("info", "LLM 응답 수신", {"tokens": token_usage})

        # 4. 출력 파싱 및 검증
        output = None
        validation_passed = None
        validation_errors = []

        try:
            # JSON 파싱 시도 (마크다운 코드블록 제거)
            cleaned = llm_response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned = "\n".join(lines)
            output = json.loads(cleaned)
            log("info", "JSON 파싱 성공")

            # 출력 검증 (설정된 경우)
            if node.output_enforcement.get('validationEnabled'):
                try:
                    jsonschema.validate(output, output_schema)
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
            renderedPrompt=rendered_prompt,
            llmResponse=llm_response,
            validationPassed=validation_passed,
            validationErrors=validation_errors if validation_errors else None,
            executionTimeMs=execution_time_ms,
            tokenUsage=token_usage,
        )

    except Exception as e:
        execution_time_ms = (time.perf_counter() - start_time) * 1000
        log("error", f"노드 실행 실패: {str(e)}")

        return NodeTestResponse(
            success=False,
            error=str(e),
            errorType=type(e).__name__,
            logs=logs,
            executionTimeMs=execution_time_ms,
        )


def _normalize_schema(schema: Any) -> Dict[str, Any]:
    """스키마를 dict로 정규화 (DB에서 문자열로 저장된 경우 처리)"""
    if isinstance(schema, str):
        try:
            return json.loads(schema)
        except (json.JSONDecodeError, TypeError):
            return {"type": "object", "properties": {}}
    if isinstance(schema, dict):
        return schema
    return {"type": "object", "properties": {}}


def render_prompt(
    template: str,
    input_data: Dict[str, Any],
) -> str:
    """
    프롬프트 템플릿 렌더링

    변수 형식:
    - {{input.fieldName}} - 입력 데이터
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
