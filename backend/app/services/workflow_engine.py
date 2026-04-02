"""
Workflow Execution Engine

DAG 기반 워크플로우 실행:
1. 트리거 노드에서 시작
2. DAG 순서대로 노드 실행
3. 조건 분기 처리
4. 병렬 실행 지원 (merge 노드까지 대기)
5. 에러 핸들링
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..core.database import async_session_maker
from ..core.constants import (
    NodeDefType, TRIGGER_TYPE_VALUES,
    BeltKey, FIELD_MAPPING_PREFIX,
)
from ..models.workflow import (
    Workflow, WorkflowNode, WorkflowConnection, WorkflowExecution,
    ExecutionStatus,
)
from .tool_executor import render_template
from ..nodes import NodeHandlerRegistry
from ..nodes.base import ExecutionContext


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
        self.outgoing_connections: Dict[str, List[WorkflowConnection]] = defaultdict(list)

        # 실행 상태
        self.node_results: Dict[str, Dict[str, Any]] = {}
        self.completed_nodes: Set[str] = set()
        self.belt_data: Dict[str, Dict[str, Any]] = {}  # 벨트 누적 데이터 (node_id → 해당 노드까지의 누적 데이터)

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

                # 5. 초기 벨트 데이터 설정
                trigger_data = self.execution.input_data or {}
                for start_id in start_nodes:
                    self.belt_data[start_id] = dict(trigger_data)

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
            self.outgoing_connections[conn.source_node_id].append(conn)

    def _find_start_nodes(self) -> List[str]:
        """시작 노드 찾기 (incoming edge가 없는 노드)"""
        # 특정 트리거 노드가 지정된 경우 해당 노드만 실행
        trigger_node_id = self.execution.input_data.get('_triggerNodeId')
        if trigger_node_id and trigger_node_id in self.nodes_by_id:
            # _triggerNodeId를 입력 데이터에서 제거
            if '_triggerNodeId' in self.execution.input_data:
                self.execution.input_data = {
                    k: v for k, v in self.execution.input_data.items()
                    if k != '_triggerNodeId'
                }
            return [trigger_node_id]

        _START_TYPES = TRIGGER_TYPE_VALUES
        start_nodes = []
        for node_id, node in self.nodes_by_id.items():
            if not self.incoming_edges[node_id]:
                if node.definition_type in _START_TYPES:
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

                # 각 노드 실행 후 중간 결과 커밋 (SSE 실시간 업데이트 지원)
                self.execution.node_results = dict(self.node_results)
                await db.commit()

                # 다음 노드들을 큐에 추가 (핸들 기반 라우팅)
                node = self.nodes_by_id[node_id]
                if node.definition_type == NodeDefType.SORTER:
                    # 분류기: matched handle에 맞는 연결만 통과
                    result = self.belt_data.get(node_id, {})
                    matched_handle = result.get(BeltKey.SORTER_HANDLE, "default") if isinstance(result, dict) else "default"
                    for conn in self.outgoing_connections[node_id]:
                        target = conn.target_node_id
                        edge_handle = conn.source_handle or "default"
                        if edge_handle == matched_handle and target not in queue and target not in self.completed_nodes:
                            queue.append(target)
                elif node.definition_type == NodeDefType.UNPACKER:
                    # 언패커: 각 아이템마다 전체 다운스트림 체인을 개별 실행
                    result = self.belt_data.get(node_id, {})
                    unpack_items = result.get(BeltKey.UNPACK_ITEMS, []) if isinstance(result, dict) else []

                    if unpack_items:
                        # 원본 벨트 (언패커 이전까지 누적된 데이터)
                        upstream_belt = self._collect_belt_input(node_id)

                        # 원본 배열을 passthrough에서 제거 (개별 아이템만 전달되어야 함)
                        unpacker_config = node.config or {}
                        array_field_name = unpacker_config.get("arrayField", "")
                        clean_upstream = dict(upstream_belt)
                        if array_field_name:
                            # 점 구분 경로 지원: "data.data" → 최상위 키 "data" 제거
                            top_key = array_field_name.split(".")[0]
                            if top_key in clean_upstream:
                                del clean_upstream[top_key]

                        # 누적 결과 저장용
                        accumulated_results: Dict[str, list] = {}

                        for idx, item in enumerate(unpack_items):
                            # 각 아이템을 _passthrough와 함께 벨트에 저장
                            item_data = item if isinstance(item, dict) else {"value": item}
                            # 아이템 인덱스 정보 주입 (하류 노드에서 몇 번째 아이템인지 식별 가능)
                            item_data['_item_index'] = idx
                            item_data['_item_total'] = len(unpack_items)
                            self.belt_data[node_id] = {**item_data, BeltKey.PASSTHROUGH: clean_upstream}

                            # 전체 다운스트림 체인을 이 아이템에 대해 실행
                            await self._execute_downstream_chain(
                                self.outgoing_edges[node_id], db
                            )

                            # 이번 반복의 다운스트림 결과 누적
                            for nid, nr in self.node_results.items():
                                if nid != node_id:  # 언패커 자신은 제외
                                    if nid not in accumulated_results:
                                        accumulated_results[nid] = []
                                    accumulated_results[nid].append(dict(nr))

                            # 중간 결과 커밋
                            self.execution.node_results = dict(self.node_results)
                            await db.commit()

                        # 누적된 결과를 node_results에 반영 (outputData를 리스트로 변환)
                        for nid, result_list in accumulated_results.items():
                            if len(result_list) > 1:
                                combined_output = [
                                    r.get("outputData") for r in result_list
                                    if r.get("outputData") is not None
                                ]
                                merged = result_list[-1].copy()
                                merged["outputData"] = combined_output
                                merged["itemCount"] = len(result_list)
                                self.node_results[nid] = merged

                        # 누적 결과 최종 커밋
                        self.execution.node_results = dict(self.node_results)
                        await db.commit()

                        # 마지막 아이템 이후 원래 결과 복원
                        self.belt_data[node_id] = result
                    # 빈 배열이면 다운스트림 스킵
                else:
                    for next_node_id in self.outgoing_edges[node_id]:
                        if next_node_id not in queue and next_node_id not in self.completed_nodes:
                            queue.append(next_node_id)

    async def _execute_downstream_chain(
        self, start_node_ids: List[str], db: AsyncSession
    ) -> None:
        """언패커에서 호출: 시작 노드부터 전체 다운스트림 체인을 실행 (분류기 핸들 라우팅 포함)"""
        chain_queue = list(start_node_ids)
        chain_visited: Set[str] = set()

        while chain_queue:
            progress_made = False
            next_round = []

            while chain_queue:
                nid = chain_queue.pop(0)
                if nid in chain_visited:
                    continue

                # 이 체인 내 의존성 확인 (체인 밖의 의존성은 이미 완료된 것으로 간주)
                deps = self.incoming_edges[nid]
                deps_ok = all(d in self.completed_nodes or d in chain_visited for d in deps)
                if not deps_ok:
                    next_round.append(nid)
                    continue

                progress_made = True
                chain_visited.add(nid)
                self.completed_nodes.discard(nid)
                await self._execute_node(nid, db)
                self.completed_nodes.add(nid)

                # 중간 결과 커밋
                self.execution.node_results = dict(self.node_results)
                await db.commit()

                # 다음 노드 라우팅
                chain_node = self.nodes_by_id[nid]
                if chain_node.definition_type == NodeDefType.SORTER:
                    # 분류기: matched handle에 맞는 연결만 통과
                    chain_result = self.belt_data.get(nid, {})
                    matched_handle = chain_result.get(BeltKey.SORTER_HANDLE, "default") if isinstance(chain_result, dict) else "default"
                    for conn in self.outgoing_connections[nid]:
                        edge_handle = conn.source_handle or "default"
                        if edge_handle == matched_handle:
                            next_round.append(conn.target_node_id)
                else:
                    for next_id in self.outgoing_edges[nid]:
                        next_round.append(next_id)

            chain_queue = next_round
            if not progress_made and chain_queue:
                import logging
                logging.getLogger(__name__).warning(
                    f"downstream chain deadlock: {chain_queue} 노드의 의존성을 충족할 수 없습니다"
                )
                break

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
            # 입력 데이터 수집 (이전 노드들의 벨트 데이터 병합)
            belt_input = self._collect_belt_input(node_id)
            input_data = self._resolve_input_mapping(node_id, belt_input)
            node_result["inputData"] = input_data

            # 노드 타입별 실행
            output = await self._execute_by_type(node, input_data, db)

            # 지식 검색 결과가 입력에 있으면 referencedKnowledge 자동 주입 (LLM 의존 X)
            if isinstance(output, dict) and 'referencedKnowledge' in output:
                knowledge_items = input_data.get('knowledge', [])
                if knowledge_items and isinstance(knowledge_items, list):
                    titles = [
                        k.get('title', k.get('id', ''))
                        for k in knowledge_items
                        if isinstance(k, dict)
                    ]
                    if titles:
                        output['referencedKnowledge'] = titles

            # 결과 저장
            node_result["status"] = "completed"
            node_result["outputData"] = output
            node_result["endTime"] = datetime.utcnow().isoformat()

            # 벨트에 저장: 자신의 출력 + 입력 데이터를 _passthrough로 보존
            if isinstance(output, dict):
                self.belt_data[node_id] = {**output, BeltKey.PASSTHROUGH: dict(belt_input)}
            else:
                self.belt_data[node_id] = {BeltKey.OUTPUT: output, BeltKey.PASSTHROUGH: dict(belt_input)}

            # 조건 노드 분기 처리
            if node.definition_type == NodeDefType.CONDITION and node.branches:
                self._handle_condition_branches(node, output)

        except Exception as e:
            node_result["status"] = "failed"
            node_result["error"] = str(e)
            node_result["endTime"] = datetime.utcnow().isoformat()
            self.execution.error_node_id = node_id
            raise

    def _collect_belt_input(self, node_id: str) -> Dict[str, Any]:
        """연결된 업스트림 노드들의 벨트 데이터를 플래트닝하여 병합 (_passthrough + own output)"""
        merged = {}
        for source_id in self.incoming_edges[node_id]:
            if source_id in self.belt_data:
                source_data = self.belt_data[source_id]
                passthrough = source_data.get(BeltKey.PASSTHROUGH, {})
                own_output = {k: v for k, v in source_data.items() if k != BeltKey.PASSTHROUGH}
                merged.update(passthrough)  # passthrough 먼저
                merged.update(own_output)   # own output이 겹치면 덮어쓰기
        # 시작 노드: incoming edge가 없으면 초기화된 belt_data 사용 (트리거 데이터)
        if not self.incoming_edges[node_id] and node_id in self.belt_data:
            source_data = self.belt_data[node_id]
            passthrough = source_data.get(BeltKey.PASSTHROUGH, {})
            own_output = {k: v for k, v in source_data.items() if k != BeltKey.PASSTHROUGH}
            merged.update(passthrough)
            merged.update(own_output)
        return merged

    def _resolve_input_mapping(self, node_id: str, belt_input: Dict[str, Any]) -> Dict[str, Any]:
        """input_mapping의 $.field 표현식을 벨트 데이터에서 해석"""
        node = self.nodes_by_id[node_id]
        mapping = node.input_mapping

        if not mapping:
            return belt_input

        resolved = {}
        for target_key, source_expr in mapping.items():
            if isinstance(source_expr, str) and source_expr.startswith(FIELD_MAPPING_PREFIX):
                path = source_expr[len(FIELD_MAPPING_PREFIX):]  # "$." 제거
                # 벨트 데이터에서 직접 중첩 경로 해석
                value = belt_input
                for key in path.split("."):
                    if isinstance(value, dict):
                        value = value.get(key)
                    else:
                        value = None
                        break
                resolved[target_key] = value
            else:
                resolved[target_key] = source_expr

        return resolved

    async def _execute_by_type(
        self,
        node: WorkflowNode,
        input_data: Dict[str, Any],
        db: AsyncSession,
    ) -> Any:
        """노드 타입별 실행 — 핸들러 레지스트리에 위임"""
        ctx = ExecutionContext(
            db=db,
            execution_id=self.execution_id,
            node_id=node.id,
            get_nested_value=self._get_nested_value,
            render_template=render_template,
        )
        handler = NodeHandlerRegistry.get(node.definition_type)
        return await handler.execute(node, input_data, ctx)

    def _collect_outputs(self) -> Dict[str, Any]:
        """출력 노드 결과 수집"""
        outputs = {}
        for node_id, result in self.node_results.items():
            node = self.nodes_by_id.get(node_id)
            if node and (node.definition_type.startswith('output-') or node.definition_type in (NodeDefType.RESULT, NodeDefType.MARKDOWN_VIEWER) or node.definition_type == NodeDefType.SORTER):
                outputs[node_id] = result.get("outputData")

        # fallback: result/output 노드가 없으면 마지막 leaf 노드의 출력 사용
        if not outputs:
            leaf_nodes = [nid for nid in self.completed_nodes
                          if not self.outgoing_edges.get(nid)]
            for leaf_id in leaf_nodes:
                if leaf_id in self.node_results:
                    outputs[leaf_id] = self.node_results[leaf_id].get("outputData")

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


async def execute_workflow(execution_id: str) -> None:
    """워크플로우 실행 (진입점)"""
    engine = WorkflowEngine(execution_id)
    await engine.run()
