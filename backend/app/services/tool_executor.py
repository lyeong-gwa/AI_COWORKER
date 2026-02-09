"""
Tool Executor Service

각 도구 타입별 실행 로직
"""

import time
import re
import httpx
from typing import Any, Dict, List
from dataclasses import dataclass, field

from ..models.tool import ToolDefinition, ToolType
from ..sandbox import execute_code, ExecutionResult as SandboxResult


@dataclass
class ToolExecutionResult:
    """도구 실행 결과"""
    success: bool
    output: Any = None
    error: str | None = None
    execution_time_ms: float = 0
    logs: List[str] = field(default_factory=list)


def render_template(template: str, data: Dict[str, Any]) -> str:
    """
    템플릿 변수 치환
    {{variable}} 형식을 data의 값으로 치환
    """
    def replacer(match):
        key = match.group(1).strip()
        keys = key.split('.')
        value = data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, '')
            else:
                return ''
        return str(value) if value is not None else ''

    return re.sub(r'\{\{([^}]+)\}\}', replacer, template)


async def execute_tool(tool: ToolDefinition, input_data: Dict[str, Any]) -> ToolExecutionResult:
    """
    도구 실행

    Args:
        tool: 도구 정의
        input_data: 입력 데이터

    Returns:
        ToolExecutionResult: 실행 결과
    """
    start_time = time.perf_counter()
    logs: List[str] = []

    try:
        if tool.type == ToolType.API_CALL:
            result = await _execute_api_call(tool.config, input_data, logs)
        elif tool.type == ToolType.FILE_READ:
            result = await _execute_file_read(tool.config, input_data, logs)
        elif tool.type == ToolType.FILE_WRITE:
            result = await _execute_file_write(tool.config, input_data, logs)
        elif tool.type == ToolType.CODE_EXECUTE:
            result = await _execute_code(tool.config, input_data, logs)
        elif tool.type == ToolType.DATABASE_QUERY:
            result = await _execute_db_query(tool.config, input_data, logs)
        else:
            raise ValueError(f"알 수 없는 도구 타입: {tool.type}")

        execution_time = (time.perf_counter() - start_time) * 1000
        return ToolExecutionResult(
            success=True,
            output=result,
            execution_time_ms=execution_time,
            logs=logs,
        )

    except Exception as e:
        execution_time = (time.perf_counter() - start_time) * 1000
        return ToolExecutionResult(
            success=False,
            error=str(e),
            execution_time_ms=execution_time,
            logs=logs,
        )


async def _execute_api_call(
    config: Dict[str, Any],
    input_data: Dict[str, Any],
    logs: List[str],
) -> Any:
    """API 호출 실행"""
    method = config.get('method', 'GET')
    url_template = config.get('urlTemplate', '')
    headers = config.get('headers', {})
    body_template = config.get('bodyTemplate')
    auth_type = config.get('authType', 'none')
    auth_config = config.get('authConfig', {})

    # URL 렌더링
    url = render_template(url_template, input_data)
    logs.append(f"[API] {method} {url}")

    # 헤더 렌더링
    rendered_headers = {
        k: render_template(v, input_data)
        for k, v in headers.items()
    }

    # 인증 처리
    if auth_type == 'bearer':
        token = auth_config.get('token', '')
        rendered_headers['Authorization'] = f"Bearer {render_template(token, input_data)}"
    elif auth_type == 'api_key':
        key_name = auth_config.get('headerName', 'X-API-Key')
        key_value = auth_config.get('apiKey', '')
        rendered_headers[key_name] = render_template(key_value, input_data)

    # 바디 렌더링
    body = None
    if body_template and method in ['POST', 'PUT', 'PATCH']:
        body = render_template(body_template, input_data)
        logs.append(f"[API] Body: {body[:100]}...")

    # HTTP 요청
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.request(
            method=method,
            url=url,
            headers=rendered_headers,
            content=body,
        )

        logs.append(f"[API] Response: {response.status_code}")

        # JSON 응답 시도
        try:
            return response.json()
        except:
            return response.text


async def _execute_file_read(
    config: Dict[str, Any],
    input_data: Dict[str, Any],
    logs: List[str],
) -> str:
    """파일 읽기 실행"""
    path_template = config.get('pathTemplate', '')
    encoding = config.get('encoding', 'utf-8')

    path = render_template(path_template, input_data)
    logs.append(f"[FILE_READ] {path}")

    # 보안: 경로 검증 (상위 디렉토리 접근 방지)
    if '..' in path or path.startswith('/'):
        raise ValueError("허용되지 않는 경로입니다")

    with open(path, 'r', encoding=encoding) as f:
        content = f.read()

    logs.append(f"[FILE_READ] Read {len(content)} bytes")
    return content


async def _execute_file_write(
    config: Dict[str, Any],
    input_data: Dict[str, Any],
    logs: List[str],
) -> Dict[str, Any]:
    """파일 쓰기 실행"""
    path_template = config.get('pathTemplate', '')
    mode = config.get('mode', 'overwrite')

    path = render_template(path_template, input_data)
    content = input_data.get('content', '')

    logs.append(f"[FILE_WRITE] {path} (mode={mode})")

    # 보안: 경로 검증
    if '..' in path or path.startswith('/'):
        raise ValueError("허용되지 않는 경로입니다")

    write_mode = 'w' if mode == 'overwrite' else 'a'
    with open(path, write_mode, encoding='utf-8') as f:
        f.write(content)

    logs.append(f"[FILE_WRITE] Wrote {len(content)} bytes")
    return {"path": path, "bytes_written": len(content)}


async def _execute_code(
    config: Dict[str, Any],
    input_data: Dict[str, Any],
    logs: List[str],
) -> Any:
    """코드 실행 (샌드박스)"""
    language = config.get('language', 'python')
    code = config.get('code', '')
    input_mapping = config.get('inputMapping', {})

    if language != 'python':
        raise ValueError(f"지원하지 않는 언어: {language}")

    logs.append("[CODE] Executing in sandbox...")

    # 입력 매핑 적용
    mapped_input = {}
    for target_key, source_path in input_mapping.items():
        keys = source_path.split('.')
        value = input_data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                value = None
                break
        mapped_input[target_key] = value

    # 샌드박스에서 실행
    result: SandboxResult = execute_code(
        code=code,
        input_data=mapped_input if mapped_input else input_data,
        return_var='result',
        timeout_seconds=10,
    )

    logs.extend(result.logs)

    if not result.success:
        raise RuntimeError(f"코드 실행 실패: {result.error}")

    logs.append(f"[CODE] Completed in {result.execution_time_ms:.2f}ms")
    return result.output


async def _execute_db_query(
    config: Dict[str, Any],
    input_data: Dict[str, Any],
    logs: List[str],
) -> Any:
    """DB 쿼리 실행"""
    connection_id = config.get('connectionId', '')
    query_template = config.get('queryTemplate', '')

    query = render_template(query_template, input_data)
    logs.append(f"[DB] Connection: {connection_id}")
    logs.append(f"[DB] Query: {query[:100]}...")

    # TODO: 실제 DB 연결 구현
    # 현재는 더미 결과 반환
    return {
        "rows": [],
        "rowCount": 0,
        "message": "DB 연결이 구현되지 않았습니다",
    }
