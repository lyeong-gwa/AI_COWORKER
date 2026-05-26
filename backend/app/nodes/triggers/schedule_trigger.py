"""스케줄 트리거 노드 — cron 기반 스케줄로 워크플로우를 시작하는 진입점.

이번 반복에서는 노드 정의(메타)만 등록합니다. 실제 cron 파싱/스케줄 디스패치는
별도 스케줄러 데몬(반복 5 예정)이 본 워크플로우를 호출하는 구조로 분리됩니다.
즉, 이 노드의 execute()는 단순 패스스루로 `triggeredAt`과 `payload`를 방출합니다.
"""
from datetime import datetime, timezone
from typing import Any, Dict

from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class ScheduleTriggerHandler(NodeHandler):
    node_type = "schedule-trigger"
    category = "trigger"
    display_name = "스케줄"
    description = "cron 표현식 기반 스케줄로 워크플로우를 시작합니다 (스케줄러 데몬 연동 예정)"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        config = node.config or {}
        # 설정 메타(참고용): cronExpr, timezone
        _cron_expr = config.get("cronExpr", "")
        _tz = config.get("timezone", "Asia/Seoul")
        payload = config.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}

        triggered_at = datetime.now(timezone.utc).isoformat()

        # input_data가 들어오면 payload 위에 덮어쓴다 (외부 호출자가 명시 전달한 값 우선)
        merged: Dict[str, Any] = {"triggeredAt": triggered_at, **payload}
        if isinstance(input_data, dict):
            merged.update(input_data)
        return merged
