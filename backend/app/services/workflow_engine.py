"""
Workflow Execution Engine

DAG 기반 워크플로우 실행:
1. 트리거 노드에서 시작
2. DAG 순서대로 노드 실행
3. 조건 분기 처리
4. 병렬 실행 지원 (merge 노드까지 대기)
5. 에러 핸들링
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..core.database import async_session_maker
from ..models.workflow import (
    Workflow, WorkflowNode, WorkflowConnection, WorkflowExecution,
    ExecutionStatus,
)
from ..models.node import AINode
from .node_executor import execute_node
from .tool_executor import render_template


class WorkflowEngine:
    """워크플로우 실행 엔진"""

    def __init__(self, execution_id: str):
        self.execution_id = execution_id
        self.execution: Optional[WorkflowExecution] = None
        self.workflow: Optional[Workflow] = None
        self.nodes_by_id: Dict[str, WorkflowNode] = {}
        self.connections: List[WorkflowConnection] = []

        # DAG 구조
        self.incoming_edges: Dict[str, List[str]] = defaultdict(list)  # node_id -> [source_node_ids]
        self.outgoing_edges: Dict[str, List[str]] = defaultdict(list)  # node_id -> [target_node_ids]

        # 실행 상태
        self.node_results: Dict[str, Dict[str, Any]] = {}
        self.completed_nodes: Set[str] = set()
        self.data_context: Dict[str, Any] = {}  # 노드 간 데이터 전달

    async def run(self) -> None:
        """워크플로우 실행"""
        async with async_session_maker() as db:
            try:
                # 1. 실행 정보 로드
                await self._load_execution(db)

                # 2. DAG 구성
                self._build_dag()

                # 3. 시작 노드 찾기 (트리거 노드)
                start_nodes = self._find_start_nodes()
                if not start_nodes:
                    raise ValueError("시작 노드(트리거)를 찾을 수 없습니다")

                # 4. 실행 시작
                self.execution.status = ExecutionStatus.RUNNING
                self.execution.started_at = datetime.utcnow()
                await db.commit()

                # 5. 초기 데이터 컨텍스트 설정
                self.data_context = {"trigger": self.execution.input_data}

                # 6. DAG 순회 실행
                await self._execute_dag(start_nodes, db)

                # 7. 완료 처리
                self.execution.status = ExecutionStatus.COMPLETED
                self.execution.completed_at = datetime.utcnow()
                self.execution.node_results = self.node_results

                # 출력 노드 결과 수집
                output_data = self._collect_outputs()
                self.execution.output_data = output_data

                await db.commit()

            except Exception as e:
                # 에러 처리
                self.execution.status = ExecutionStatus.FAILED
                self.execution.error_message = str(e)
                self.execution.completed_at = datetime.utcnow()
                self.execution.node_results = self.node_results
                await db.commit()
                raise

    async def _load_execution(self, db: AsyncSession) -> None:
        """실행 정보 로드"""
        result = await db.execute(
            select(WorkflowExecution).where(WorkflowExecution.id == self.execution_id)
        )
        self.execution = result.scalar_one_or_none()

        if not self.execution:
            raise ValueError(f"실행을 찾을 수 없습니다: {self.execution_id}")

        # 워크플로우 로드
        result = await db.execute(
            select(Workflow)
            .options(selectinload(Workflow.nodes), selectinload(Workflow.connections))
            .where(Workflow.id == self.execution.workflow_id)
        )
        self.workflow = result.scalar_one()

        # 노드/연결선 인덱싱
        for node in self.workflow.nodes:
            self.nodes_by_id[node.id] = node
        self.connections = list(self.workflow.connections)

    def _build_dag(self) -> None:
        """DAG 구조 구성"""
        for conn in self.connections:
            self.incoming_edges[conn.target_node_id].append(conn.source_node_id)
            self.outgoing_edges[conn.source_node_id].append(conn.target_node_id)

    def _find_start_nodes(self) -> List[str]:
        """시작 노드 찾기 (incoming edge가 없는 노드)"""
        start_nodes = []
        for node_id, node in self.nodes_by_id.items():
            if not self.incoming_edges[node_id]:
                # 트리거 노드인지 확인
                if node.definition_type in ['manual', 'schedule', 'webhook']:
                    start_nodes.append(node_id)
        return start_nodes

    async def _execute_dag(self, start_nodes: List[str], db: AsyncSession) -> None:
        """DAG 순회 실행"""
        # BFS 방식으로 실행
        queue = list(start_nodes)
        in_progress: Set[str] = set()

        while queue or in_progress:
            # 실행 가능한 노드 찾기 (모든 의존성이 완료된 노드)
            ready_nodes = []
            remaining_queue = []

            for node_id in queue:
                dependencies = self.incoming_edges[node_id]
                if all(dep in self.completed_nodes for dep in dependencies):
                    ready_nodes.append(node_id)
                else:
                    remaining_queue.append(node_id)

            queue = remaining_queue

            if not ready_nodes and not in_progress:
                if queue:
                    raise ValueError("순환 의존성이 감지되었습니다")
                break

            # 준비된 노드들 실행
            for node_id in ready_nodes:
                await self._execute_node(node_id, db)
                self.completed_nodes.add(node_id)

                # 다음 노드들을 큐에 추가
                for next_node_id in self.outgoing_edges[node_id]:
                    if next_node_id not in queue and next_node_id not in self.completed_nodes:
                        queue.append(next_node_id)

    async def _execute_node(self, node_id: str, db: AsyncSession) -> None:
        """단일 노드 실행"""
        node = self.nodes_by_id[node_id]
        start_time = datetime.utcnow()

        node_result = {
            "nodeId": node_id,
            "definitionType": node.definition_type,
            "status": "running",
            "startTime": start_time.isoformat(),
            "logs": [],
        }
        self.node_results[node_id] = node_result

        try:
            # 입력 데이터 수집 (이전 노드들의 출력)
            input_data = self._collect_node_input(node_id)
            node_result["inputData"] = input_data

            # 노드 타입별 실행
            output = await self._execute_by_type(node, input_data, db)

            # 결과 저장
            node_result["status"] = "completed"
            node_result["outputData"] = output
            node_result["endTime"] = datetime.utcnow().isoformat()

            # 데이터 컨텍스트에 출력 저장
            self.data_context[node_id] = output

            # 조건 노드 분기 처리
            if node.definition_type == 'condition' and node.branches:
                self._handle_condition_branches(node, output)

        except Exception as e:
            node_result["status"] = "failed"
            node_result["error"] = str(e)
            node_result["endTime"] = datetime.utcnow().isoformat()
            self.execution.error_node_id = node_id
            raise

    def _collect_node_input(self, node_id: str) -> Dict[str, Any]:
        """노드 입력 데이터 수집"""
        input_data = {}

        # 이전 노드들의 출력 수집
        for source_id in self.incoming_edges[node_id]:
            if source_id in self.data_context:
                input_data[source_id] = self.data_context[source_id]

        # 트리거 데이터 포함
        if "trigger" in self.data_context:
            input_data["trigger"] = self.data_context["trigger"]

        return input_data

    async def _execute_by_type(
        self,
        node: WorkflowNode,
        input_data: Dict[str, Any],
        db: AsyncSession,
    ) -> Any:
        """노드 타입별 실행 로직"""
        def_type = node.definition_type
        config = node.config

        # 트리거 노드
        if def_type in ['manual', 'schedule', 'webhook']:
            return input_data.get("trigger", {})

        # 로직 노드
        elif def_type == 'condition':
            return self._evaluate_condition(config, input_data)

        elif def_type == 'switch':
            return self._evaluate_switch(config, input_data)

        elif def_type == 'loop':
            return await self._execute_loop(node, config, input_data, db)

        elif def_type == 'merge':
            return self._merge_inputs(input_data)

        # 변환 노드
        elif def_type == 'set-variable':
            return self._set_variables(config, input_data)

        elif def_type == 'code':
            return await self._execute_code_node(config, input_data)

        elif def_type == 'json-parse':
            return self._parse_json(config, input_data)

        # 액션 노드
        elif def_type == 'http-request':
            return await self._execute_http_request(config, input_data)

        elif def_type == 'send-email':
            return await self._send_email(config, input_data)

        # AI 노드
        elif def_type in ['ai-chat', 'ai-classify', 'ai-extract', 'ai-summarize', 'ai-custom']:
            return await self._execute_ai_node(node, config, input_data, db)

        # 출력 노드
        elif def_type == 'output-log':
            return self._output_log(config, input_data)

        elif def_type == 'output-webhook':
            return await self._output_webhook(config, input_data)

        else:
            raise ValueError(f"알 수 없는 노드 타입: {def_type}")

    def _evaluate_condition(self, config: Dict, input_data: Dict) -> Dict:
        """조건 평가"""
        # 간단한 조건 평가 구현
        # TODO: 복잡한 조건 표현식 지원
        conditions = config.get('conditions', [])
        result = {"matched": False, "branch": "default"}

        for cond in conditions:
            field = cond.get('field', '')
            operator = cond.get('operator', 'equals')
            value = cond.get('value', '')

            # 필드 값 가져오기
            actual_value = self._get_nested_value(input_data, field)

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

    def _evaluate_switch(self, config: Dict, input_data: Dict) -> Dict:
        """스위치 평가"""
        switch_field = config.get('switchField', '')
        cases = config.get('cases', [])

        value = self._get_nested_value(input_data, switch_field)

        for case in cases:
            if case.get('value') == value:
                return {"matched": True, "case": case.get('value')}

        return {"matched": False, "case": "default"}

    def _set_variables(self, config: Dict, input_data: Dict) -> Dict:
        """변수 설정"""
        variables = config.get('variables', [])
        result = {}

        for var in variables:
            name = var.get('name', '')
            value = var.get('value', '')

            # 템플릿 렌더링
            rendered = render_template(value, input_data)
            result[name] = rendered

        return result

    def _merge_inputs(self, input_data: Dict) -> Dict:
        """입력 병합"""
        merged = {}
        for key, value in input_data.items():
            if key != "trigger":
                if isinstance(value, dict):
                    merged.update(value)
                else:
                    merged[key] = value
        return merged

    async def _execute_ai_node(
        self,
        node: WorkflowNode,
        config: Dict,
        input_data: Dict,
        db: AsyncSession,
    ) -> Dict:
        """AI 노드 실행"""
        # 커스텀 AI 노드인 경우 연결된 AINode 사용
        if node.ai_node_id:
            result = await db.execute(
                select(AINode).where(AINode.id == node.ai_node_id)
            )
            ai_node = result.scalar_one_or_none()

            if ai_node:
                exec_result = await execute_node(
                    node=ai_node,
                    input_data=input_data,
                    db=db,
                )
                return exec_result.output if exec_result.success else {"error": exec_result.error}

        # 기본 AI 노드 설정 사용
        from .llm_client import call_llm

        prompt = config.get('prompt', '')
        rendered_prompt = render_template(prompt, input_data)

        response, _ = await call_llm(
            prompt=rendered_prompt,
            provider=config.get('provider', 'openai'),
            model=config.get('model', 'gpt-4o-mini'),
            temperature=config.get('temperature', 0.7),
            max_tokens=config.get('maxTokens', 2000),
        )

        return {"response": response}

    async def _execute_http_request(self, config: Dict, input_data: Dict) -> Dict:
        """HTTP 요청 실행"""
        import httpx

        method = config.get('method', 'GET')
        url = render_template(config.get('url', ''), input_data)
        headers = {
            k: render_template(v, input_data)
            for k, v in config.get('headers', {}).items()
        }
        body = render_template(config.get('body', ''), input_data) if config.get('body') else None

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                content=body,
            )

            try:
                return {"status": response.status_code, "data": response.json()}
            except:
                return {"status": response.status_code, "data": response.text}

    def _output_log(self, config: Dict, input_data: Dict) -> Dict:
        """로그 출력"""
        message = render_template(config.get('message', ''), input_data)
        return {"logged": True, "message": message}

    def _collect_outputs(self) -> Dict[str, Any]:
        """출력 노드 결과 수집"""
        outputs = {}
        for node_id, result in self.node_results.items():
            node = self.nodes_by_id.get(node_id)
            if node and node.definition_type.startswith('output-'):
                outputs[node_id] = result.get("outputData")
        return outputs

    def _get_nested_value(self, data: Dict, path: str) -> Any:
        """중첩 경로로 값 가져오기"""
        keys = path.split('.')
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value

    def _handle_condition_branches(self, node: WorkflowNode, output: Dict) -> None:
        """조건 분기 처리 (특정 분기만 활성화)"""
        # TODO: 분기별 연결선 필터링 구현
        pass

    async def _execute_loop(self, node: WorkflowNode, config: Dict, input_data: Dict, db: AsyncSession) -> List:
        """루프 노드 실행"""
        # TODO: 루프 구현
        return []

    async def _execute_code_node(self, config: Dict, input_data: Dict) -> Any:
        """코드 노드 실행"""
        from ..sandbox import execute_code

        code = config.get('code', '')
        result = execute_code(code, input_data, 'result')

        if result.success:
            return result.output
        else:
            raise RuntimeError(f"코드 실행 실패: {result.error}")

    def _parse_json(self, config: Dict, input_data: Dict) -> Dict:
        """JSON 파싱"""
        import json
        source = config.get('source', '')
        value = self._get_nested_value(input_data, source)

        if isinstance(value, str):
            return json.loads(value)
        return value

    async def _send_email(self, config: Dict, input_data: Dict) -> Dict:
        """이메일 발송"""
        # TODO: 이메일 발송 구현
        return {"sent": False, "message": "이메일 발송 기능이 구현되지 않았습니다"}

    async def _output_webhook(self, config: Dict, input_data: Dict) -> Dict:
        """웹훅 출력"""
        import httpx

        url = render_template(config.get('url', ''), input_data)
        payload = input_data

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload)
            return {"status": response.status_code, "sent": True}


async def execute_workflow(execution_id: str) -> None:
    """워크플로우 실행 (진입점)"""
    engine = WorkflowEngine(execution_id)
    await engine.run()
