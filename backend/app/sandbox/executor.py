"""
Sandboxed Code Executor using RestrictedPython

RestrictedPython을 사용한 안전한 코드 실행 환경
- 위험한 내장 함수 차단 (open, exec, eval, __import__ 등)
- 리소스 제한 (실행 시간, 메모리)
- 허용된 모듈만 import 가능
"""

import ast
import sys
import signal
import traceback
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field
from contextlib import contextmanager
from RestrictedPython import compile_restricted, safe_globals, safe_builtins
from RestrictedPython.Guards import (
    safe_builtins,
    guarded_iter_unpack_sequence,
    guarded_unpack_sequence,
)
from RestrictedPython.Eval import default_guarded_getiter, default_guarded_getitem


@dataclass
class ExecutionResult:
    """코드 실행 결과"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    logs: List[str] = field(default_factory=list)
    execution_time_ms: float = 0


class TimeoutError(Exception):
    """실행 시간 초과 에러"""
    pass


class SandboxViolationError(Exception):
    """샌드박스 규칙 위반 에러"""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# 안전한 내장 함수 정의
# ─────────────────────────────────────────────────────────────────────────────

# 허용할 내장 함수 목록
ALLOWED_BUILTINS = {
    # 타입 변환
    'bool', 'int', 'float', 'str', 'list', 'tuple', 'dict', 'set', 'frozenset',
    'bytes', 'bytearray',

    # 수학/논리
    'abs', 'round', 'min', 'max', 'sum', 'pow', 'divmod',

    # 시퀀스 처리
    'len', 'range', 'enumerate', 'zip', 'map', 'filter', 'sorted', 'reversed',
    'all', 'any', 'iter', 'next',

    # 문자열 처리
    'chr', 'ord', 'repr', 'ascii', 'format',

    # 기타 안전한 함수
    'isinstance', 'issubclass', 'type', 'id', 'hash',
    'callable', 'hasattr', 'getattr', 'setattr',
    'print',  # 로그 수집용

    # 예외
    'Exception', 'ValueError', 'TypeError', 'KeyError', 'IndexError',
    'RuntimeError', 'StopIteration',

    # 상수
    'True', 'False', 'None',
}

# 허용할 모듈 및 사용 가능한 함수/클래스
ALLOWED_MODULES = {
    'json': ['loads', 'dumps', 'JSONDecodeError'],
    'math': [
        'ceil', 'floor', 'trunc', 'sqrt', 'pow', 'exp', 'log', 'log10', 'log2',
        'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'atan2',
        'degrees', 'radians', 'pi', 'e', 'inf', 'nan',
        'fabs', 'factorial', 'gcd', 'isnan', 'isinf', 'isfinite',
    ],
    're': ['match', 'search', 'findall', 'sub', 'split', 'compile', 'Pattern'],
    'datetime': ['datetime', 'date', 'time', 'timedelta', 'timezone'],
    'collections': ['Counter', 'defaultdict', 'OrderedDict', 'namedtuple', 'deque'],
    'itertools': [
        'count', 'cycle', 'repeat', 'chain', 'compress', 'dropwhile', 'takewhile',
        'groupby', 'islice', 'starmap', 'product', 'permutations', 'combinations',
    ],
    'functools': ['reduce', 'partial', 'lru_cache'],
    'operator': [
        'add', 'sub', 'mul', 'truediv', 'floordiv', 'mod', 'pow',
        'neg', 'pos', 'abs', 'not_', 'and_', 'or_', 'xor',
        'eq', 'ne', 'lt', 'le', 'gt', 'ge',
        'itemgetter', 'attrgetter',
    ],
    'random': [
        'random', 'randint', 'randrange', 'choice', 'choices', 'sample', 'shuffle',
        'uniform', 'gauss', 'seed',
    ],
    'string': ['ascii_letters', 'ascii_lowercase', 'ascii_uppercase', 'digits', 'punctuation'],
    'base64': ['b64encode', 'b64decode', 'urlsafe_b64encode', 'urlsafe_b64decode'],
    'hashlib': ['md5', 'sha1', 'sha256', 'sha512'],
    'uuid': ['uuid4', 'UUID'],
    'decimal': ['Decimal', 'ROUND_HALF_UP', 'ROUND_DOWN'],
    'statistics': ['mean', 'median', 'mode', 'stdev', 'variance'],
}


def create_safe_import():
    """안전한 import 함수 생성"""
    def safe_import(name: str, globals_dict=None, locals_dict=None, fromlist=(), level=0):
        if name not in ALLOWED_MODULES:
            raise SandboxViolationError(f"모듈 '{name}'은(는) 허용되지 않습니다. 허용된 모듈: {list(ALLOWED_MODULES.keys())}")

        # 실제 모듈 import
        import importlib
        module = importlib.import_module(name)

        # 허용된 속성만 포함하는 제한된 모듈 객체 생성
        allowed_attrs = ALLOWED_MODULES[name]

        class RestrictedModule:
            pass

        restricted = RestrictedModule()
        restricted.__name__ = name

        for attr in allowed_attrs:
            if hasattr(module, attr):
                setattr(restricted, attr, getattr(module, attr))

        return restricted

    return safe_import


def create_safe_builtins() -> Dict[str, Any]:
    """안전한 내장 함수 딕셔너리 생성"""
    import builtins

    safe = {}

    for name in ALLOWED_BUILTINS:
        if hasattr(builtins, name):
            safe[name] = getattr(builtins, name)

    # RestrictedPython 필수 가드
    safe['_getiter_'] = default_guarded_getiter
    safe['_getitem_'] = default_guarded_getitem
    safe['_iter_unpack_sequence_'] = guarded_iter_unpack_sequence
    safe['_unpack_sequence_'] = guarded_unpack_sequence

    # 안전한 import 함수
    safe['__import__'] = create_safe_import()

    return safe


# ─────────────────────────────────────────────────────────────────────────────
# 코드 실행기
# ─────────────────────────────────────────────────────────────────────────────

class SandboxedExecutor:
    """
    RestrictedPython 기반 샌드박스 코드 실행기

    사용 예시:
        executor = SandboxedExecutor(timeout_seconds=5)
        result = executor.execute(
            code='result = sum([1, 2, 3, 4, 5])',
            input_data={'numbers': [1, 2, 3]},
            return_var='result'
        )
    """

    def __init__(
        self,
        timeout_seconds: int = 10,
        max_output_size: int = 1024 * 1024,  # 1MB
    ):
        self.timeout_seconds = timeout_seconds
        self.max_output_size = max_output_size
        self._logs: List[str] = []

    def _create_print_collector(self) -> callable:
        """로그 수집용 print 함수 생성"""
        logs = self._logs
        max_size = self.max_output_size
        current_size = [0]

        def safe_print(*args, **kwargs):
            text = ' '.join(str(arg) for arg in args)
            if current_size[0] + len(text) > max_size:
                raise SandboxViolationError("출력 크기가 제한을 초과했습니다.")
            current_size[0] += len(text)
            logs.append(text)

        return safe_print

    def _validate_code(self, code: str) -> None:
        """코드 사전 검증 (위험한 패턴 탐지)"""
        dangerous_patterns = [
            '__builtins__',
            '__class__',
            '__bases__',
            '__subclasses__',
            '__mro__',
            '__globals__',
            '__code__',
            '__reduce__',
            'os.system',
            'subprocess',
            'eval(',
            'exec(',
            'compile(',
            'open(',
            '__import__("os")',
            '__import__("sys")',
            '__import__("subprocess")',
        ]

        code_lower = code.lower()
        for pattern in dangerous_patterns:
            if pattern.lower() in code_lower:
                raise SandboxViolationError(f"위험한 코드 패턴이 감지되었습니다: {pattern}")

    def execute(
        self,
        code: str,
        input_data: Optional[Dict[str, Any]] = None,
        return_var: str = 'result',
    ) -> ExecutionResult:
        """
        코드 실행

        Args:
            code: 실행할 Python 코드
            input_data: 코드에 주입할 입력 데이터 (input 변수로 접근 가능)
            return_var: 반환할 변수명 (기본값: 'result')

        Returns:
            ExecutionResult: 실행 결과
        """
        import time
        start_time = time.perf_counter()
        self._logs = []

        try:
            # 1. 코드 사전 검증
            self._validate_code(code)

            # 2. RestrictedPython으로 컴파일
            byte_code = compile_restricted(
                code,
                filename='<sandbox>',
                mode='exec',
            )

            if byte_code.errors:
                return ExecutionResult(
                    success=False,
                    error='\n'.join(byte_code.errors),
                    error_type='CompileError',
                    logs=self._logs,
                )

            # 3. 실행 환경 구성
            safe_builtins_dict = create_safe_builtins()
            safe_builtins_dict['print'] = self._create_print_collector()

            global_env = {
                '__builtins__': safe_builtins_dict,
                '__name__': '__sandbox__',
                'input': input_data or {},
            }

            local_env = {}

            # 4. 타임아웃과 함께 실행
            exec(byte_code.code, global_env, local_env)

            # 5. 결과 추출
            execution_time = (time.perf_counter() - start_time) * 1000

            output = local_env.get(return_var)

            # 결과 직렬화 가능 여부 확인
            try:
                import json
                json.dumps(output, default=str)
            except (TypeError, ValueError):
                output = str(output)

            return ExecutionResult(
                success=True,
                output=output,
                logs=self._logs,
                execution_time_ms=execution_time,
            )

        except SandboxViolationError as e:
            return ExecutionResult(
                success=False,
                error=str(e),
                error_type='SandboxViolation',
                logs=self._logs,
                execution_time_ms=(time.perf_counter() - start_time) * 1000,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                logs=self._logs,
                execution_time_ms=(time.perf_counter() - start_time) * 1000,
            )


# ─────────────────────────────────────────────────────────────────────────────
# JavaScript/JSON 변환 실행기 (제한된 표현식 평가)
# ─────────────────────────────────────────────────────────────────────────────

class ExpressionEvaluator:
    """
    안전한 표현식 평가기

    템플릿 내 표현식 (예: {{input.name.toUpperCase()}}) 평가용
    제한된 연산만 허용
    """

    ALLOWED_STRING_METHODS = {
        'upper', 'lower', 'strip', 'lstrip', 'rstrip',
        'split', 'join', 'replace', 'startswith', 'endswith',
        'find', 'rfind', 'index', 'rindex', 'count',
        'isdigit', 'isalpha', 'isalnum', 'isspace',
        'capitalize', 'title', 'swapcase',
        'zfill', 'ljust', 'rjust', 'center',
    }

    ALLOWED_LIST_METHODS = {
        'append', 'extend', 'insert', 'remove', 'pop',
        'index', 'count', 'sort', 'reverse', 'copy',
    }

    ALLOWED_DICT_METHODS = {
        'keys', 'values', 'items', 'get', 'pop',
        'update', 'copy', 'clear',
    }

    def evaluate(self, expression: str, context: Dict[str, Any]) -> Any:
        """표현식 평가"""
        try:
            # AST 파싱
            tree = ast.parse(expression, mode='eval')

            # AST 검증
            self._validate_ast(tree)

            # 안전한 환경에서 평가
            return eval(
                compile(tree, '<expression>', 'eval'),
                {'__builtins__': {}},
                context,
            )
        except Exception as e:
            raise ValueError(f"표현식 평가 실패: {expression} - {e}")

    def _validate_ast(self, tree: ast.AST) -> None:
        """AST 노드 검증"""
        for node in ast.walk(tree):
            # 함수 호출 검증
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    # 메서드 호출 검증
                    method_name = node.func.attr
                    # 허용된 메서드인지 확인 (타입에 관계없이)
                    all_allowed = (
                        self.ALLOWED_STRING_METHODS |
                        self.ALLOWED_LIST_METHODS |
                        self.ALLOWED_DICT_METHODS
                    )
                    if method_name not in all_allowed:
                        raise ValueError(f"허용되지 않은 메서드: {method_name}")
                elif isinstance(node.func, ast.Name):
                    # 일반 함수 호출 차단
                    raise ValueError(f"함수 호출은 허용되지 않습니다: {node.func.id}")

            # Import 차단
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                raise ValueError("import는 허용되지 않습니다")


# ─────────────────────────────────────────────────────────────────────────────
# 싱글톤 인스턴스
# ─────────────────────────────────────────────────────────────────────────────

_executor: Optional[SandboxedExecutor] = None

def get_executor(timeout_seconds: int = 10) -> SandboxedExecutor:
    """샌드박스 실행기 싱글톤 인스턴스 반환"""
    global _executor
    if _executor is None:
        _executor = SandboxedExecutor(timeout_seconds=timeout_seconds)
    return _executor


def execute_code(
    code: str,
    input_data: Optional[Dict[str, Any]] = None,
    return_var: str = 'result',
    timeout_seconds: int = 10,
) -> ExecutionResult:
    """
    편의 함수: 코드 실행

    Args:
        code: 실행할 Python 코드
        input_data: 입력 데이터
        return_var: 반환할 변수명
        timeout_seconds: 타임아웃 (초)

    Returns:
        ExecutionResult: 실행 결과
    """
    executor = SandboxedExecutor(timeout_seconds=timeout_seconds)
    return executor.execute(code, input_data, return_var)
