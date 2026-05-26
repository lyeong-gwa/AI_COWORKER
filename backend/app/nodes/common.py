"""노드 공통 유틸리티.

여러 노드 핸들러가 공유하는 템플릿/경로 처리 헬퍼들. instance-db-insert /
instance-db-lookup 양쪽이 동일한 dedup_key 해시 방식·동일한 type-preserving
객체 렌더 방식을 써야 record 적재·조회가 정확히 일치하므로 한 곳에 모은다.
"""
import hashlib
import re
from typing import Any, Callable, Dict, Optional


# ── 정규식 ─────────────────────────────────────────────────────────────────

_SINGLE_BRACE_VAR = re.compile(r'\{([A-Za-z_][A-Za-z0-9_]*)\}')

# 템플릿 문자열 전체가 단일 ``{{var}}`` 참조일 때만 매칭 — 타입 보존용.
_PURE_REFERENCE_RE = re.compile(r"^\s*\{\{\s*([^{}]+?)\s*\}\}\s*$")


# ── URL/헤더 템플릿 ────────────────────────────────────────────────────────


def render_url_or_header(template: str, params: Dict[str, Any], double_brace_renderer) -> str:
    """URL·헤더 템플릿 렌더: `{{var}}` 먼저 처리 후 OpenAPI식 `{var}` 치환.

    - 단일 중괄호는 식별자 패턴만 치환하며, 키가 없으면 리터럴을 유지한다.
    - JSON 바디에는 사용하지 말 것 (바디는 `{{var}}` 전용 유지).
    """
    if template is None:
        return ""
    rendered = double_brace_renderer(template, params)

    def _sub(match):
        key = match.group(1)
        if params and key in params:
            value = params[key]
            if value is not None:
                return str(value)
        return match.group(0)

    return _SINGLE_BRACE_VAR.sub(_sub, rendered)


# ── dedup 키 ───────────────────────────────────────────────────────────────


def compute_dedup_key(template: Optional[str], input_data: Dict[str, Any], render_template) -> Optional[str]:
    """dedup 키 템플릿을 렌더링 후 SHA1 앞 32자로 해시.

    - template이 비어있으면 None 반환.
    - 렌더 결과가 공백이면 None 반환.

    instance-db-insert 가 적재 시 이 함수로 키를 만들면 instance-db-lookup
    by_key 모드도 동일 함수로 검색해야 매칭된다.
    """
    if not template:
        return None
    try:
        rendered = render_template(template, input_data)
    except Exception:
        return None
    if not rendered or not str(rendered).strip():
        return None
    digest = hashlib.sha1(str(rendered).encode("utf-8")).hexdigest()
    return digest[:32]


# ── nested 경로 ────────────────────────────────────────────────────────────


def resolve_path(data: Dict[str, Any], path: str) -> Any:
    """dot-path 로 nested 값 조회. 없으면 None."""
    if not path:
        return None
    keys = [k.strip() for k in path.split(".")]
    value: Any = data
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            return None
    return value


# ── object/list/string 재귀 렌더 (타입 보존) ─────────────────────────────


def render_object(template: Any, data: Dict[str, Any], render_template: Callable[[str, Dict[str, Any]], str]) -> Any:
    """object/list/string 안의 모든 string 리프에 render_template 적용.

    - dict: 키는 그대로, 값은 재귀적으로 렌더
    - list: 각 요소를 재귀적으로 렌더
    - str: 단일 `{{var}}` 참조면 원본 타입 보존(int/bool/list/dict 등),
           그 외에는 일반 문자열 치환
    - 그 외 (int/float/bool/None): 그대로 반환

    타입 보존 동기: JSON Schema 가 ``type:integer`` 등을 요구할 때
    ``{{boardId}}`` 같은 단일 변수 참조는 원래 int 값으로 적재되어야 한다.
    혼합 문자열(``"id-{{boardId}}"``)은 전체가 string 으로 렌더된다.
    """
    if isinstance(template, dict):
        return {k: render_object(v, data, render_template) for k, v in template.items()}
    if isinstance(template, list):
        return [render_object(v, data, render_template) for v in template]
    if isinstance(template, str):
        m = _PURE_REFERENCE_RE.match(template)
        if m:
            # 단일 변수 참조 — 원본 타입 그대로 반환 (None 포함)
            return resolve_path(data, m.group(1))
        return render_template(template, data)
    return template


# ── warehouseEntryId 추출 ─────────────────────────────────────────────────


def resolve_warehouse_entry_id(input_data: Dict[str, Any]) -> Optional[str]:
    """입력 dict 에서 warehouseEntryId 또는 entryId 를 찾아 반환."""
    if not isinstance(input_data, dict):
        return None
    for key in ("warehouseEntryId", "entryId"):
        val = input_data.get(key)
        if isinstance(val, str) and val:
            return val
    return None


__all__ = [
    "render_url_or_header",
    "compute_dedup_key",
    "resolve_path",
    "render_object",
    "resolve_warehouse_entry_id",
]
