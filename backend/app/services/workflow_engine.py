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
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from ..core.database import async_session_maker
from ..core.constants import (
    NodeDefType, TRIGGER_TYPE_VALUES, AI_NODE_TYPE_VALUES,
    BeltKey, FIELD_MAPPING_PREFIX, KNOWLEDGE_MIN_RESULTS, KNOWLEDGE_MAX_RESULTS,
)
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
                        for idx, item in enumerate(unpack_items):
                            # 각 아이템을 _passthrough와 함께 벨트에 저장
                            item_data = item if isinstance(item, dict) else {"value": item}
                            self.belt_data[node_id] = {**item_data, BeltKey.PASSTHROUGH: dict(upstream_belt)}

                            # 전체 다운스트림 체인을 이 아이템에 대해 실행
                            await self._execute_downstream_chain(
                                self.outgoing_edges[node_id], db
                            )

                            # 중간 결과 커밋
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
            nid = chain_queue.pop(0)
            if nid in chain_visited:
                continue

            # 이 체인 내 의존성 확인 (체인 밖의 의존성은 이미 완료된 것으로 간주)
            deps = self.incoming_edges[nid]
            deps_ok = all(d in self.completed_nodes or d in chain_visited for d in deps)
            if not deps_ok:
                chain_queue.append(nid)
                continue

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
                        chain_queue.append(conn.target_node_id)
            else:
                for next_id in self.outgoing_edges[nid]:
                    chain_queue.append(next_id)

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
        """노드 타입별 실행 로직"""
        def_type = node.definition_type
        config = node.config

        # 트리거 노드 (레거시: form-start, api-start 제외 — 아래에서 별도 처리)
        if def_type in (NodeDefType.MANUAL, NodeDefType.SCHEDULE, NodeDefType.WEBHOOK, NodeDefType.FORM):
            return input_data

        # 폼 시작 노드 — 수동 실행 시 폼 데이터, 스케줄 실행 시 기본값 사용
        elif def_type == NodeDefType.FORM_START:
            return input_data

        # API 시작 노드 — 외부 API 호출 후 응답을 출력으로 전달
        elif def_type == NodeDefType.API_START:
            return await self._execute_api_start(node, input_data, db)

        # 지식 검색 노드 — 입력 데이터로 지식 베이스를 검색하여 결과 병합
        elif def_type == NodeDefType.KNOWLEDGE:
            return await self._execute_knowledge_node(node, input_data, db)

        # 로직 노드
        elif def_type == NodeDefType.CONDITION:
            return self._evaluate_condition(config, input_data)

        elif def_type == NodeDefType.SWITCH:
            return self._evaluate_switch(config, input_data)

        elif def_type == NodeDefType.LOOP:
            return await self._execute_loop(node, config, input_data, db)

        elif def_type == NodeDefType.MERGE:
            return self._merge_inputs(input_data)

        # 변환 노드
        elif def_type == NodeDefType.SET_VARIABLE:
            return self._set_variables(config, input_data)

        elif def_type == NodeDefType.CODE:
            return await self._execute_code_node(config, input_data)

        elif def_type == NodeDefType.JSON_PARSE:
            return self._parse_json(config, input_data)

        # 액션 노드
        elif def_type == NodeDefType.HTTP_REQUEST:
            return await self._execute_http_request(config, input_data)

        elif def_type == NodeDefType.SEND_EMAIL:
            return await self._send_email(config, input_data)

        # AI 노드 (큐에 추가 후 처리)
        elif def_type in AI_NODE_TYPE_VALUES:
            return await self._execute_ai_node_with_queue(node, config, input_data, db)

        # 출력 노드
        elif def_type == NodeDefType.OUTPUT_LOG:
            return self._output_log(config, input_data)

        elif def_type == NodeDefType.OUTPUT_WEBHOOK:
            return await self._output_webhook(config, input_data)

        # 분류기 노드 (조건 분기 + 창고 보관)
        elif def_type == NodeDefType.SORTER:
            return await self._execute_sorter(node, config, input_data, db)

        # API 문서 직접 호출 노드 (LLM 없이)
        elif def_type == NodeDefType.API_CALL:
            return await self._execute_api_doc_node(node, config, input_data)

        # 언패커 노드 (배열 → 개별 객체 분배)
        elif def_type == NodeDefType.UNPACKER:
            return self._execute_unpacker(node, config, input_data)

        # 결과 노드 (pass-through + 창고에 축적)
        elif def_type in (NodeDefType.RESULT, NodeDefType.MARKDOWN_VIEWER):
            output = input_data
            # 창고에 축적
            try:
                from ..models.workflow import WarehouseEntry
                entry = WarehouseEntry(
                    id=f"wh-{uuid.uuid4().hex[:8]}",
                    node_instance_id=node.id,
                    execution_id=self.execution_id,
                    data=output if isinstance(output, dict) else {"value": output},
                )
                db.add(entry)
            except Exception:
                pass  # 창고 저장 실패해도 실행은 계속
            return output

        else:
            raise ValueError(f"알 수 없는 노드 타입: {def_type}")

    async def _execute_api_doc_node(
        self,
        node: WorkflowNode,
        config: Dict,
        input_data: Dict,
    ) -> Dict:
        """API 문서 기반 직접 호출 노드 (LLM 없이 API 실행)

        config.apiDefinitionId: API 정의 DB 레코드 ID (우선)
        config.docId: 지식 베이스 MD 파일 ID (레거시 호환)
        """
        import httpx
        from sqlalchemy import select

        api_def_id = config.get("apiDefinitionId")
        doc_id = config.get("docId")

        method = "GET"
        url_template = ""
        headers_raw = {}
        body_template = None
        auth_type = "none"
        auth_config = {}

        # 1. ApiDefinition DB에서 로드 (우선)
        if api_def_id:
            from ..models.api_definition import ApiDefinition
            async with async_session_maker() as api_db:
                result = await api_db.execute(
                    select(ApiDefinition).where(ApiDefinition.id == api_def_id)
                )
                api_def = result.scalar_one_or_none()
            if api_def:
                method = api_def.method
                url_template = api_def.url_template
                headers_raw = api_def.headers or {}
                body_template = api_def.body_template
                auth_type = api_def.auth_type
                auth_config = api_def.auth_config or {}
            else:
                raise ValueError(f"API 정의를 찾을 수 없습니다: {api_def_id}")

        # 2. 레거시: 지식 문서에서 로드
        elif doc_id:
            from .knowledge_file_service import read_md_file
            doc = read_md_file(doc_id)
            if not doc:
                raise ValueError(f"API 문서를 찾을 수 없습니다: {doc_id}")
            api_meta = doc.extra_metadata.get("api", {})
            if not api_meta:
                raise ValueError(f"API 메타데이터가 없습니다: {doc_id}")
            method = api_meta.get("method", "GET")
            url_template = api_meta.get("url", "")
            headers_raw = api_meta.get("headers", {})
            body_template = api_meta.get("bodyTemplate")
        else:
            raise ValueError("API 문서가 선택되지 않았습니다")

        # Render templates with input_data
        url = render_template(url_template, input_data)

        rendered_headers = {}
        if isinstance(headers_raw, dict):
            rendered_headers = {
                k: render_template(str(v), input_data)
                for k, v in headers_raw.items()
            }

        # 인증 처리 (ApiDefinition에서 로드한 경우)
        if auth_type == "bearer":
            token = auth_config.get("token", "")
            rendered_token = render_template(token, input_data)
            if rendered_token:
                rendered_headers["Authorization"] = f"Bearer {rendered_token}"
        elif auth_type == "api_key":
            key_name = auth_config.get("headerName", "X-API-Key")
            key_value = auth_config.get("apiKey", "")
            rendered_headers[key_name] = render_template(key_value, input_data)

        # 빈 값 헤더 제거 (Bearer 뒤 토큰 없는 경우 등)
        rendered_headers = {
            k: v for k, v in rendered_headers.items()
            if v and str(v).strip() and str(v).strip() != "Bearer"
        }

        body = None
        if body_template and method.upper() in ['POST', 'PUT', 'PATCH']:
            body = render_template(body_template, input_data)

        # Execute HTTP request
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                headers=rendered_headers,
                content=body,
            )

            try:
                response_data = response.json()
            except Exception:
                response_data = response.text

            return {
                "status": response.status_code,
                "data": response_data,
            }

    async def _execute_api_start(
        self,
        node: WorkflowNode,
        input_data: Dict[str, Any],
        db: AsyncSession,
    ) -> Dict:
        """API 시작 노드 — API 정의 또는 지식 문서를 읽어 호출하고 응답을 반환

        config.apiDefinitionId: API 정의 DB 레코드 ID (우선)
        config.docId: 지식 베이스 MD 파일 ID (레거시 호환)
        config.defaultParams: 스케줄 실행 시 사용할 기본 파라미터
        input_data.trigger: 수동 실행 시 전달되는 파라미터 (기본값 오버라이드)
        """
        import httpx
        from sqlalchemy import select

        config = node.config or {}
        api_def_id = config.get('apiDefinitionId')
        doc_id = config.get('docId')
        default_params = config.get('defaultParams', {})

        # 수동 트리거 입력과 기본 파라미터 병합 (벨트 데이터가 우선)
        params = {**default_params, **input_data}

        method = 'GET'
        url_template = ''
        headers_raw = {}
        body_template = None
        auth_type = 'none'
        auth_config = {}

        # 1. ApiDefinition DB에서 로드 (우선)
        if api_def_id:
            from ..models.api_definition import ApiDefinition
            result = await db.execute(
                select(ApiDefinition).where(ApiDefinition.id == api_def_id)
            )
            api_def = result.scalar_one_or_none()
            if api_def:
                method = api_def.method
                url_template = api_def.url_template
                headers_raw = api_def.headers or {}
                body_template = api_def.body_template
                auth_type = api_def.auth_type
                auth_config = api_def.auth_config or {}
            else:
                return {"error": f"API 정의를 찾을 수 없습니다: {api_def_id}", "status": 0, "data": None}

        # 2. 레거시: 지식 문서에서 로드
        elif doc_id:
            from .knowledge_file_service import read_md_file
            doc = read_md_file(doc_id)
            if not doc:
                return {"error": f"API 문서를 찾을 수 없습니다: {doc_id}", "status": 0, "data": None}
            api_meta = doc.extra_metadata.get('api', {})
            if not api_meta:
                return {"error": "API 메타데이터가 없습니다", "status": 0, "data": None}
            method = api_meta.get('method', 'GET')
            url_template = api_meta.get('url', '')
            headers_raw = api_meta.get('headers', {})
            body_template = api_meta.get('bodyTemplate')
        else:
            return {"error": "API 문서가 선택되지 않았습니다", "status": 0, "data": None}

        # 파라미터로 템플릿 렌더링
        url = render_template(url_template, params)

        rendered_headers = {}
        if isinstance(headers_raw, dict):
            rendered_headers = {
                k: render_template(str(v), params)
                for k, v in headers_raw.items()
            }

        # 인증 처리 (ApiDefinition에서 로드한 경우)
        if auth_type == 'bearer':
            token = auth_config.get('token', '')
            rendered_token = render_template(token, params)
            if rendered_token:
                rendered_headers['Authorization'] = f"Bearer {rendered_token}"
        elif auth_type == 'api_key':
            key_name = auth_config.get('headerName', 'X-API-Key')
            key_value = auth_config.get('apiKey', '')
            rendered_headers[key_name] = render_template(key_value, params)

        # 빈 값 헤더 제거 (Bearer 뒤 토큰 없는 경우 등)
        rendered_headers = {
            k: v for k, v in rendered_headers.items()
            if v and str(v).strip() and str(v).strip() != "Bearer"
        }

        body = None
        if body_template and method.upper() in ['POST', 'PUT', 'PATCH']:
            body = render_template(body_template, params)

        # HTTP 요청 실행
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                headers=rendered_headers,
                content=body,
            )

            try:
                response_data = response.json()
            except Exception:
                response_data = response.text

            return {
                "status": response.status_code,
                "data": response_data,
            }

    async def _execute_knowledge_node(
        self,
        node: WorkflowNode,
        input_data: Dict[str, Any],
        db: AsyncSession,
    ) -> Dict:
        """지식 검색 노드 — 지식 베이스에서 유사 문서를 검색하여 입력 데이터에 병합"""
        config = node.config or {}
        search_field = config.get('searchField', '')
        category = config.get('category', '')
        tags = config.get('tags', [])
        max_results = min(KNOWLEDGE_MAX_RESULTS, max(KNOWLEDGE_MIN_RESULTS, config.get('maxResults', 5)))

        flat_input = input_data

        # 입력 데이터에서 검색 쿼리 추출
        query = ''
        if search_field:
            val = self._get_nested_value(flat_input, search_field)
            if val is not None:
                query = str(val)

        if not query:
            # Fallback: 플래트닝된 데이터의 모든 문자열 값을 결합
            str_values = [str(v) for v in flat_input.values() if isinstance(v, str)]
            query = ' '.join(str_values)

        if not query:
            # 카테고리가 설정된 경우, 카테고리명으로 검색 (전체 카테고리 문서 조회)
            if category:
                query = category
            else:
                return {'knowledge': [], BeltKey.KNOWLEDGE_ERROR: '검색 쿼리를 추출할 수 없습니다'}

        # 벡터 DB로 유사도 검색
        from .embedding.vector_db import get_vector_db

        try:
            vector_db = get_vector_db()

            # ChromaDB 필터 구성
            where_filter = None
            if category:
                where_filter = {'category': category}

            # 검색 실행
            results = vector_db.search(
                query=query,
                top_k=max_results,
                where=where_filter,
            )

            knowledge_items = []
            for sr in results:
                item = {
                    'id': sr.id,
                    'content': sr.content,
                    'score': sr.score,
                    'title': sr.metadata.get('title', sr.id),
                    'category': sr.metadata.get('category', ''),
                    'tags': sr.metadata.get('tags', ''),
                }

                # 태그 필터 (벡터 DB 필터가 지원하지 않는 태그 교차 필터링)
                if tags:
                    item_tags = item.get('tags', '')
                    if isinstance(item_tags, str):
                        item_tags = [t.strip() for t in item_tags.split(',') if t.strip()]
                    if not any(t in item_tags for t in tags):
                        continue

                knowledge_items.append(item)

            # 지식 검색 결과 + 카테고리 반환 (입력 데이터는 _passthrough로 프레임워크가 처리)
            result = {'knowledge': knowledge_items}
            if category:
                result['category'] = category
            return result

        except Exception as e:
            # 검색 실패 시 빈 결과 + 에러 정보 (입력 데이터는 _passthrough로 처리)
            return {'knowledge': [], BeltKey.KNOWLEDGE_ERROR: str(e)}

    def _execute_unpacker(
        self,
        node: WorkflowNode,
        config: Dict,
        input_data: Dict,
    ) -> Dict:
        """언패커 노드: 배열 필드를 개별 객체로 분해

        config.arrayField: 입력 데이터에서 배열을 가져올 필드 경로 (e.g. "data")
        결과: {"items": [...], "count": N, "__unpackItems": [...]}
        __unpackItems는 _execute_dag에서 특수 처리됨
        """
        array_field = config.get("arrayField", "")

        if not array_field:
            raise ValueError("언패커: arrayField가 설정되지 않았습니다")

        # Resolve array from input data
        value = self._get_nested_value(input_data, array_field)

        if not isinstance(value, list):
            raise ValueError(f"언패커: '{array_field}' 필드가 배열이 아닙니다 (타입: {type(value).__name__})")

        return {
            "items": value,
            "count": len(value),
            BeltKey.UNPACK_ITEMS: value,
        }

    async def _execute_sorter(
        self,
        node: WorkflowNode,
        config: Dict,
        input_data: Dict,
        db: AsyncSession,
    ) -> Dict:
        """분류기 노드 실행: 조건 분기 + 창고 보관"""
        import re

        original = input_data

        # 창고에 축적
        try:
            from ..models.workflow import WarehouseEntry
            entry = WarehouseEntry(
                id=f"wh-{uuid.uuid4().hex[:8]}",
                node_instance_id=node.id,
                execution_id=self.execution_id,
                data=original if isinstance(original, dict) else {"value": original},
            )
            db.add(entry)
        except Exception:
            pass

        # 규칙 순차 평가
        rules = config.get("rules", [])
        matched_handle = "default"

        for rule in rules:
            field = rule.get("field", "")
            operator = rule.get("operator", "equals")
            value = rule.get("value", "")
            actual = self._get_nested_value(original, field) if field else None

            if self._evaluate_sorter_rule(actual, operator, value):
                matched_handle = f"rule-{rule.get('id', '')}"
                break

        return {BeltKey.SORTER_HANDLE: matched_handle}

    def _evaluate_sorter_rule(self, actual: Any, operator: str, value: str) -> bool:
        """분류기 규칙 평가"""
        import re

        if operator == "exists":
            return actual is not None
        if operator == "notExists":
            return actual is None

        if actual is None:
            return False

        actual_str = str(actual)

        if operator == "equals":
            return actual_str == value or actual == value
        elif operator == "notEquals":
            return actual_str != value and actual != value
        elif operator == "contains":
            return value in actual_str
        elif operator == "startsWith":
            return actual_str.startswith(value)
        elif operator == "endsWith":
            return actual_str.endswith(value)
        elif operator == "greaterThan":
            try:
                return float(actual) > float(value)
            except (ValueError, TypeError):
                return False
        elif operator == "lessThan":
            try:
                return float(actual) < float(value)
            except (ValueError, TypeError):
                return False
        elif operator == "regex":
            try:
                return bool(re.search(value, actual_str))
            except re.error:
                return False

        return False

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

    async def _execute_ai_node_with_queue(
        self,
        node: WorkflowNode,
        config: Dict,
        input_data: Dict,
        db: AsyncSession,
    ) -> Dict:
        """AI 노드 실행 (큐 기반 FIFO)"""
        from ..models.workflow import NodeQueueItem, QueueItemStatus

        queue_item_id = f"qi-{uuid.uuid4().hex[:8]}"

        # 1. 큐에 아이템 추가 (pending) — separate session
        async with async_session_maker() as queue_db:
            queue_item = NodeQueueItem(
                id=queue_item_id,
                node_instance_id=node.id,
                execution_id=self.execution_id,
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
            output = await self._execute_ai_node(node, config, input_data, db)

            # 6. 완료 → 큐에서 삭제 (큐는 순차 처리용, 이력 보관 아님)
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
            # 실패 → 큐에서 삭제 (다음 아이템 블로킹 방지)
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
                # input_schema에서 string 타입인데 dict/list가 전달된 경우 자동 JSON 직렬화
                coerced_input = dict(input_data)
                schema_props = (ai_node.input_schema or {}).get("properties", {})
                for key, val in coerced_input.items():
                    if isinstance(val, (dict, list)):
                        expected_type = schema_props.get(key, {}).get("type")
                        if expected_type == "string":
                            coerced_input[key] = json.dumps(val, ensure_ascii=False, default=str)

                exec_result = await execute_node(
                    node=ai_node,
                    input_data=coerced_input,
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
