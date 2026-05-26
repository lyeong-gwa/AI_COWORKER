"""AI 노드 핸들러 — ai-custom, ai-chat, ai-classify, ai-extract, ai-summarize"""
import asyncio
import json
import uuid
from typing import Any, Dict

from sqlalchemy import select, func

from ...core.database import async_session_maker
from ...models.workflow import NodeQueueItem, QueueItemStatus
from ...models.node import AINode
from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext


@NodeHandlerRegistry.register
class AiCustomHandler(NodeHandler):
    node_type = "ai-custom"
    category = "ai"
    display_name = "AI 커스텀"
    description = "큐 기반 FIFO로 AI 노드를 실행합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        return await self._execute_with_queue(node, input_data, ctx)

    async def _execute_with_queue(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Dict:
        """AI 노드 실행 (큐 기반 FIFO)"""
        config = node.config

        queue_item_id = f"qi-{uuid.uuid4().hex[:8]}"

        # 1. 큐에 아이템 추가 (pending) — separate session
        async with async_session_maker() as queue_db:
            queue_item = NodeQueueItem(
                id=queue_item_id,
                node_instance_id=node.id,
                execution_id=ctx.execution_id,
                data=input_data,
                status=QueueItemStatus.PENDING,
            )
            queue_db.add(queue_item)
            await queue_db.commit()

        # 2. 이 노드의 processing 중인 아이템이 있으면 대기
        max_wait = 300  # 5분 최대 대기
        waited = 0
        while waited < max_wait:
            async with async_session_maker() as queue_db:
                result = await queue_db.execute(
                    select(func.count()).where(
                        NodeQueueItem.node_instance_id == node.id,
                        NodeQueueItem.status == QueueItemStatus.PROCESSING,
                    )
                )
                processing_count = result.scalar() or 0

            if processing_count == 0:
                break

            await asyncio.sleep(1)
            waited += 1

        # 3. 내 차례 확인 (FIFO: 가장 오래된 pending이 나인지)
        async with async_session_maker() as queue_db:
            result = await queue_db.execute(
                select(NodeQueueItem)
                .where(
                    NodeQueueItem.node_instance_id == node.id,
                    NodeQueueItem.status == QueueItemStatus.PENDING,
                )
                .order_by(NodeQueueItem.created_at.asc())
                .limit(1)
            )
            next_item = result.scalar_one_or_none()

        if next_item and next_item.id != queue_item_id:
            # 내 앞에 다른 아이템이 있음 — 대기
            waited2 = 0
            while waited2 < max_wait:
                async with async_session_maker() as queue_db:
                    # 내 아이템 상태 확인
                    result = await queue_db.execute(
                        select(NodeQueueItem).where(NodeQueueItem.id == queue_item_id)
                    )
                    refreshed = result.scalar_one_or_none()
                    if not refreshed or refreshed.status != QueueItemStatus.PENDING:
                        break

                    # 내 앞의 pending/processing이 없으면 내 차례
                    result2 = await queue_db.execute(
                        select(func.count()).where(
                            NodeQueueItem.node_instance_id == node.id,
                            NodeQueueItem.status.in_([QueueItemStatus.PENDING, QueueItemStatus.PROCESSING]),
                            NodeQueueItem.created_at < refreshed.created_at,
                        )
                    )
                    ahead = result2.scalar() or 0

                if ahead == 0:
                    break

                await asyncio.sleep(1)
                waited2 += 1

        # 4. processing 상태로 전환
        async with async_session_maker() as queue_db:
            result = await queue_db.execute(
                select(NodeQueueItem).where(NodeQueueItem.id == queue_item_id)
            )
            qi = result.scalar_one()
            qi.status = QueueItemStatus.PROCESSING
            await queue_db.commit()

        # 5. 실제 AI 노드 실행 (original db session)
        try:
            output = await self._execute_ai_node(node, config, input_data, ctx)

            # 6. 완료 -> 큐에서 삭제 (큐는 순차 처리용, 이력 보관 아님)
            async with async_session_maker() as queue_db:
                result = await queue_db.execute(
                    select(NodeQueueItem).where(NodeQueueItem.id == queue_item_id)
                )
                qi = result.scalar_one_or_none()
                if qi:
                    await queue_db.delete(qi)
                    await queue_db.commit()

            return output

        except Exception as e:
            # 실패 -> 큐에서 삭제 (다음 아이템 블로킹 방지)
            async with async_session_maker() as queue_db:
                result = await queue_db.execute(
                    select(NodeQueueItem).where(NodeQueueItem.id == queue_item_id)
                )
                qi = result.scalar_one_or_none()
                if qi:
                    await queue_db.delete(qi)
                    await queue_db.commit()
            raise

    async def _execute_ai_node(
        self,
        node: Any,
        config: Dict,
        input_data: Dict,
        ctx: ExecutionContext,
    ) -> Dict:
        """AI 노드 실행"""
        # 커스텀 AI 노드인 경우 연결된 AINode 사용
        if node.ai_node_id:
            result = await ctx.db.execute(
                select(AINode).where(AINode.id == node.ai_node_id)
            )
            ai_node = result.scalar_one_or_none()

            if ai_node:
                # input_schema 기반 자동 타입 변환
                coerced_input = dict(input_data)
                schema_props = (ai_node.input_schema or {}).get("properties", {})
                for key in list(coerced_input.keys()):
                    val = coerced_input[key]
                    expected_type = schema_props.get(key, {}).get("type")
                    # dict/list → JSON 문자열 변환 (스키마가 string을 기대하는 경우)
                    if isinstance(val, (dict, list)) and expected_type == "string":
                        coerced_input[key] = json.dumps(val, ensure_ascii=False, default=str)
                    # None → 스키마 타입에 맞는 기본값 변환
                    elif val is None and expected_type:
                        if expected_type == "string":
                            coerced_input[key] = ""
                        elif expected_type == "array":
                            coerced_input[key] = []
                        elif expected_type == "object":
                            coerced_input[key] = {}

                from ...services.node_executor import execute_node
                exec_result = await execute_node(
                    node=ai_node,
                    input_data=coerced_input,
                    db=ctx.db,
                )
                return exec_result.output if exec_result.success else {"error": exec_result.error}

        # 기본 AI 노드 설정 사용
        from ...services.llm_client import call_llm

        prompt = config.get('prompt', '')
        rendered_prompt = ctx.render_template(prompt, input_data)

        # systemPrompt가 있으면 system role로 분리 전달 (템플릿 변수 치환 포함)
        system_prompt_raw = config.get('systemPrompt') or config.get('system_prompt')
        rendered_system_prompt = None
        if system_prompt_raw:
            rendered_system_prompt = ctx.render_template(system_prompt_raw, input_data)

        response, _ = await call_llm(
            prompt=rendered_prompt,
            provider=config.get('provider', 'openai'),
            model=config.get('model', 'gpt-4o-mini'),
            temperature=config.get('temperature', 0.7),
            max_tokens=config.get('maxTokens', 2000),
            system_prompt=rendered_system_prompt,
        )

        return {"response": response}


# 동일 핸들러를 다른 AI 타입으로 등록
for _type in ["ai-chat", "ai-classify", "ai-extract", "ai-summarize"]:
    _display = _type.replace("ai-", "AI ").title()
    _cls = type(
        f"{_type.replace('-', '_').title().replace('_', '')}Handler",
        (AiCustomHandler,),
        {"node_type": _type, "display_name": _display},
    )
    NodeHandlerRegistry.register(_cls)
