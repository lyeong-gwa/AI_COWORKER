"""조건 노드 핸들러"""
from typing import Any, Dict

from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class ConditionHandler(NodeHandler):
    node_type = "condition"
    category = "logic"
    display_name = "조건"
    description = "조건에 따라 분기합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config
        # 간단한 조건 평가 구현
        # TODO: 복잡한 조건 표현식 지원
        conditions = config.get('conditions', [])
        result = {"matched": False, "branch": "default"}

        for cond in conditions:
            field = cond.get('field', '')
            operator = cond.get('operator', 'equals')
            value = cond.get('value', '')

            # 필드 값 가져오기
            actual_value = ctx.get_nested_value(input_data, field)

            # 연산자별 비교
            matched = False
            if operator == 'equals':
                matched = actual_value == value
            elif operator == 'notEquals':
                matched = actual_value != value
            elif operator == 'contains':
                matched = value in str(actual_value)
            elif operator == 'greaterThan':
                matched = float(actual_value) > float(value)
            elif operator == 'lessThan':
                matched = float(actual_value) < float(value)

            if matched:
                result = {"matched": True, "branch": cond.get('branchId', 'true')}
                break

        return result
