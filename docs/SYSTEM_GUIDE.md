# AI 업무도우미 시스템 가이드

> AI(Claude 등)가 이 시스템을 처음 만나서도 자율적으로 활용할 수 있도록 쓴 실전 레퍼런스. 데이터 주입법은 [`EXAMPLE_DATA_INJECTION_GUIDE.md`](./EXAMPLE_DATA_INJECTION_GUIDE.md)에, 운영 지침은 [`CLAUDE.md`](../CLAUDE.md)에 별도로 있으니 이 문서는 **동작 원리·노드 명세·API 참조·확장 방법**에 집중한다.

---

## 목차
1. [시스템 개요](#1-시스템-개요)
2. [핵심 개념](#2-핵심-개념)
3. [아키텍처](#3-아키텍처)
4. [노드 타입 전수 명세](#4-노드-타입-전수-명세)
5. [워크플로우 실행 라이프사이클](#5-워크플로우-실행-라이프사이클)
6. [API 참조](#6-api-참조)
7. [프론트엔드 활용](#7-프론트엔드-활용)
8. [고급 기능](#8-고급-기능)
9. [확장 방법](#9-확장-방법)
10. [트러블슈팅](#10-트러블슈팅)
11. [관련 문서](#11-관련-문서)

---

## 1. 시스템 개요

**AI 업무도우미**는 ITO(IT 운영) 업무 자동화를 위한 n8n 스타일 로우코드 워크플로우 플랫폼이다. 프론트엔드 공장맵(Factory)에서 노드를 드래그·연결하면, 백엔드가 DAG(유향 비순환 그래프)로 실행한다.

### 주요 유스케이스
| 시나리오 | 구성 |
|---|---|
| 문의글 분류·자동응답 | `api-start` → `unpacker` → `knowledge` → `ai-custom`(요약/분류) → `sorter` → `api-call`(티켓 생성) |
| GitHub 마일스톤 산출물 자동 생성 | `form-start` → `milestone-collector` → `dev-deliverable-gen` → `review-deliverable-gen` → `markdown-viewer` |
| 주기적 시스템 점검 | `schedule-trigger`(cron) → `api-call`(점검 API) → `condition` → `webhook-notify`(Slack) |
| RAG 기반 지식 답변 | `form-start` → `knowledge`(벡터검색) → `ai-custom`(답변 생성) → `result` |

### 동작 모드
| 모드 | 설명 | 진입점 |
|---|---|---|
| **싱글톤 공장맵(Factory)** | 하나의 거대한 그래프를 항상 유지. 복수 트리거(`api-start`, `form-start`, 스케줄)를 한 맵에서 혼용 가능 | `/factory` API, `/factory` 페이지 |
| **개별 워크플로우(Workflow)** | 목적별로 개별 파이프라인 여러 개를 만들어 관리 | `/workflows` API, `/workflow` 페이지 |

두 모드는 내부적으로 같은 `Workflow` 테이블을 쓴다. 팩토리 맵은 ID 고정(`"factory-main"`)이며, 엔진·노드 핸들러도 공유한다.

---

## 2. 핵심 개념

### 2.1 세 계층의 "노드"
이 시스템에서 "노드"라는 단어는 세 가지를 가리킨다. **절대 혼동 금지.**

| 계층 | 이름 | 역할 | 코드 위치 |
|---|---|---|---|
| ① 핸들러(코드) | **Node Handler** | 타입별 실행 로직. `ai-custom`, `api-call`, `sorter` 등 각 타입마다 하나 | `backend/app/nodes/{triggers,ai,logic,action,transform,output}/*.py` |
| ② 템플릿(객체) | **AI Node** (`AINode` 테이블) | 재사용 프롬프트+스키마+LLM 설정. `ai-custom` 핸들러가 이 템플릿을 참조 | `backend/app/models/node.py`, 테이블 `ai_nodes` |
| ③ 인스턴스(객체) | **Workflow Node** (`WorkflowNode` 테이블) | 특정 워크플로우 내 노드 인스턴스. 캔버스 위치·config 보유 | `backend/app/models/workflow.py`, 테이블 `workflow_nodes` |

**핸들러는 코드이므로 "주입" 대상 아님.** AI Node와 Workflow Node는 데이터이므로 API로 CRUD 가능.

### 2.2 ApiDefinition (재사용 API 스펙)
HTTP 호출 스펙(URL/메서드/헤더/파라미터/인증)을 카탈로그로 관리. `api-call`·`api-start`·`ai-api-router` 노드가 `config.apiDefinitionId`로 참조한다.

### 2.3 Knowledge (RAG 컨텍스트)
`backend/data/knowledge/{id}.md` 파일에 YAML frontmatter + 본문으로 저장. `/knowledge/sync` 호출 시 로컬 ONNX 임베딩(`jhgan_ko-sroberta-multitask`)으로 벡터화하여 ChromaDB(`backend/data/chroma/`)에 저장. `knowledge` 노드가 코사인 유사도 검색으로 조회.

### 2.4 벨트 데이터 모델 (핵심)
워크플로우 엔진은 노드 간 데이터를 **"벨트(belt)"** 로 전달한다. 컨베이어 벨트 위에 데이터가 누적되면서 흐르는 모델.

- **각 노드가 받는 입력**: 업스트림 모든 노드의 `_passthrough` + `own_output`을 **플래트닝 병합**
- **각 노드가 벨트에 남기는 출력**: `{**자신의 output_dict, "_passthrough": {업스트림에서 받은 전체 belt}}`
- **효과**: 하류 노드는 **전체 상류 맥락**에 자유롭게 접근 가능. 같은 키가 충돌하면 `own_output`이 `_passthrough`를 덮어쓴다 (가까운 업스트림 우선).

```python
# backend/app/services/workflow_engine.py:380 _collect_belt_input
merged = {}
for source_id in incoming_edges[node_id]:
    source_data = belt_data[source_id]
    passthrough = source_data.get("_passthrough", {})
    own_output = {k: v for k, v in source_data.items() if k != "_passthrough"}
    merged.update(passthrough)  # passthrough 먼저
    merged.update(own_output)   # own output이 덮어쓰기
```

### 2.5 input_mapping (명시적 선택)
병합된 벨트에서 **필요한 필드만 골라 이름을 바꿔** 노드 핸들러에 전달하고 싶을 때 사용. `$.` 접두사가 경로 지정.

```json
{
  "inputMapping": {
    "text": "$.data.description",
    "category": "$.data.category"
  }
}
```
이러면 핸들러는 `{"text": "...", "category": "..."}` 만 받는다. `inputMapping`이 비면 **벨트 전체**가 그대로 넘어간다.

### 2.6 render_template (템플릿 치환)
`{{변수}}` / `{{중첩.경로}}` 플레이스홀더를 입력 데이터로 치환. dict/list는 `json.dumps(ensure_ascii=False)`로 직렬화된다.

```python
# backend/app/services/tool_executor.py:28
render_template("안녕 {{user.name}}, {{data}}건", {"user":{"name":"김"}, "data":[1,2,3]})
# -> '안녕 김, [1, 2, 3]건'
```

### 2.7 특수 벨트 키 (constants.py::BeltKey)
| 키 | 용도 |
|---|---|
| `_passthrough` | 상류 컨텍스트 전체 (엔진이 자동 관리) |
| `__sorterHandle` | sorter 노드가 매칭한 규칙 handle ID (라우팅용) |
| `__unpackItems` | unpacker가 분해한 배열 (엔진이 downstream chain 반복용으로 소비) |
| `_knowledgeError` | knowledge 노드 검색 실패 에러 메시지 |
| `_output` | 핸들러 출력이 dict가 아닐 때 감싸는 키 |

---

## 3. 아키텍처

### 3.1 디렉토리 구조
```
AI 업무도우미/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 엔트리 (lifespan, 좀비 정리, 스케줄러)
│   │   ├── core/
│   │   │   ├── config.py           # Settings (포트 8002, DB URL, LLM 키 등)
│   │   │   ├── constants.py        # NodeDefType enum, BeltKey, TRIGGER_TYPES
│   │   │   ├── database.py         # SQLAlchemy async engine + 마이그레이션
│   │   │   └── scheduler.py        # APScheduler 데몬 (cron)
│   │   ├── models/                 # SQLAlchemy 모델
│   │   │   ├── workflow.py         # Workflow, WorkflowNode, Connection, Execution, WarehouseEntry, NodeQueueItem
│   │   │   ├── node.py             # AINode (재사용 AI 템플릿)
│   │   │   ├── api_definition.py   # ApiDefinition
│   │   │   ├── ticket.py           # Ticket (칸반)
│   │   │   ├── audit_log.py        # AuditLog
│   │   │   └── tool.py             # 레거시 도구 정의
│   │   ├── schemas/                # Pydantic 요청/응답 스키마
│   │   ├── api/
│   │   │   ├── __init__.py         # 라우터 등록 (중요!)
│   │   │   └── routes/
│   │   │       ├── workflows.py, factory.py, nodes.py, api_definitions.py
│   │   │       ├── knowledge.py, tickets.py, ops.py, warehouse.py
│   │   │       ├── chat.py, export_import.py
│   │   ├── nodes/                  # 노드 핸들러 (타입별 1개)
│   │   │   ├── base.py             # NodeHandler ABC, ExecutionContext
│   │   │   ├── registry.py         # NodeHandlerRegistry
│   │   │   ├── common.py           # compute_dedup_key
│   │   │   ├── triggers/           # manual, form-start, api-start, schedule-trigger
│   │   │   ├── ai/                 # ai-custom, ai-api-router
│   │   │   ├── logic/              # condition, sorter, unpacker, mapper, loop, merge, switch
│   │   │   ├── action/             # api-call, http-request, knowledge, send-email,
│   │   │   │                       # webhook-notify, excel-export, warehouse-query, deliverable-generator
│   │   │   ├── transform/          # code, set-variable, json-parse
│   │   │   └── output/             # warehouse(result/markdown-viewer), output-webhook, output-log
│   │   ├── services/
│   │   │   ├── workflow_engine.py  # WorkflowEngine (DAG 순회, 벨트 관리)
│   │   │   ├── node_executor.py    # AINode 실행 (LLM 호출 래퍼)
│   │   │   ├── tool_executor.py    # render_template + _execute_api_call 등
│   │   │   ├── llm_client.py, llm/ # OpenAI/Anthropic/Azure/External 라우팅
│   │   │   ├── embedding/          # ONNX 임베딩 + ChromaDB 벡터 DB
│   │   │   ├── knowledge_file_service.py  # MD 파일 CRUD + frontmatter
│   │   │   └── audit.py            # 감사 로그
│   │   └── sandbox/
│   │       └── executor.py         # RestrictedPython 기반 코드 샌드박스
│   └── data/                       # SQLite(app.db), Chroma, knowledge/, exports/
├── frontend/
│   └── src/
│       ├── pages/                  # FactoryPage, WorkflowPage, KnowledgeBasePage, OpsDashboardPage,
│       │                           # NodeManagementPage, ApiDefinitionPage, DashboardPage
│       ├── nodes/                  # 노드 레지스트리 (registrations.ts가 모든 노드 등록)
│       ├── components/
│       │   └── workflow/           # 캔버스, 노드 카드, 설정 패널
│       └── services/               # API 클라이언트
└── docs/
    ├── SYSTEM_GUIDE.md             # (이 문서)
    └── EXAMPLE_DATA_INJECTION_GUIDE.md
```

### 3.2 스택
| 계층 | 기술 |
|---|---|
| Backend | FastAPI + SQLAlchemy(async, aiosqlite) + httpx + APScheduler |
| RAG | ChromaDB + ONNX Runtime (`jhgan_ko-sroberta-multitask` 로컬) |
| LLM | OpenAI / Anthropic / Azure OpenAI / Custom API / External LLM (Dify 호환) |
| Sandbox | RestrictedPython |
| Frontend | React + TypeScript + Vite + React Flow(@xyflow/react) + Tailwind |
| DB | SQLite(`backend/data/app.db`) + ChromaDB(`backend/data/chroma/`) + MD 파일(`backend/data/knowledge/`) |

### 3.3 포트
| 서비스 | 포트 | 주의 |
|---|---|---|
| Backend API | **8002** (고정) | CORS: `http://localhost:5173` 허용. 5174도 쓰면 `core/config.py` 수정 필요 |
| Frontend | **5174** (고정) | `--strictPort` 강제 |
| 목업 API 서버 | 8001 | 인접 프로젝트 — 외부 API 호출 경유지 |
| 정적분석 백엔드 | 8000 | 인접 프로젝트 |

포트 변경 금지. 점유 중이면 kill 후 재기동. (`CLAUDE.md` 참조)

### 3.4 기동
```bash
# Backend (포트 점유 kill 후 기동)
cd backend
PORT=8002
PID=$(netstat -ano | grep ":$PORT " | grep LISTENING | awk '{print $5}' | head -1)
[ -n "$PID" ] && taskkill //F //PID $PID
uvicorn app.main:app --reload --port 8002

# Frontend
cd frontend && npm run dev -- --port 5174 --strictPort
```

### 3.5 초기 상태
서버 첫 기동 시:
1. `backend/data/` 자동 생성, `data/knowledge/` 생성
2. SQLite 테이블 자동 생성(`init_db`), 마이그레이션 실행
3. 좀비 큐/실행 정리 (`node_queue_items`의 PROCESSING/PENDING 삭제, `workflow_executions`의 RUNNING을 FAILED로)
4. APScheduler 기동 + `schedule-trigger`를 가진 ACTIVE 워크플로우를 cron job으로 로드

모든 데이터 테이블은 빈 상태로 시작 — AI Node, API Definition, Workflow, Knowledge는 모두 명시적으로 주입 필요. (→ `EXAMPLE_DATA_INJECTION_GUIDE.md`)

---

## 4. 노드 타입 전수 명세

노드 타입의 **정식 값**은 `backend/app/core/constants.py::NodeDefType`에 정의. 핸들러는 `@NodeHandlerRegistry.register` 데코레이터로 자동 등록. 워크플로우 노드 정의 시 `definitionType`과 `nodeId`(둘 다 동일한 핸들러 타입 문자열)에 이 값을 쓴다.

### 4.1 Trigger (시작) 노드

| nodeId | 핸들러 파일 | 주요 config | 출력 |
|---|---|---|---|
| `manual` | `nodes/triggers/manual.py` | — (패스스루) | input_data 그대로 |
| `form-start` | `nodes/triggers/form_start.py` | `mode`, 폼 필드 메타 | 폼 입력 데이터 그대로 |
| `api-start` | `nodes/triggers/api_start.py` | `apiDefinitionId`, `defaultParams` | `{status, data}` (외부 API 호출 결과) |
| `schedule-trigger` | `nodes/triggers/schedule_trigger.py` | `cronExpr`(예: `"0 9 * * *"`), `timezone`, `payload` | `{triggeredAt, ...payload}` |
| `webhook`, `schedule`, `form` | 레거시 별칭 (핸들러는 manual과 동일) | | |

**핵심**: `api-start`는 트리거이면서 **외부 API 호출을 수행**한다. `ApiDefinition`의 `parameters` 중 `in: "query"`인 것은 URL에 자동 추가(소스 우선순위: 트리거 입력 > `defaultParams` > 파라미터 `default`). `urlTemplate`의 `{{var}}` 치환도 같은 params로 수행.

### 4.2 Action (동작) 노드

| nodeId | 핸들러 | config 주요 키 | 출력 |
|---|---|---|---|
| `api-call` | `action/api_call.py` | `apiDefinitionId`, `defaultParams` | `{status, data}` |
| `http-request` | `action/http_request.py` | `method`, `url`, `headers`, `body` (인라인 정의, ApiDefinition 불요) | `{status, data}` |
| `knowledge` | `action/knowledge.py` | `searchField`, `categories`(배열), `tags`(배열), `maxResults`(4~7) | `{knowledge: [{id,content,score,title,category,tags}], search_categories?}` |
| `send-email` | `action/send_email.py` | (미구현) | `{sent: false}` |
| `webhook-notify` | `action/webhook_notify.py` | `webhookUrl`, `platform`(`slack`/`teams`/`discord`/`generic`), `messageTemplate`, `titleTemplate`, `mentionUsers` | `{delivered, status, platform}` |
| `excel-export` | `action/excel_export.py` | `sheetName`, `columns: [{header, key}]`, `outputPath?` | `{file_path, row_count, url, ...}` |
| `warehouse-query` | `action/warehouse_query.py` | `sourceNodeId`, `dedupKey`(템플릿), `mode`(`exists`/`latest`/`list`), `limit` | `{exists, existsFlag, entry|entries}` |
| `deliverable-generator` | `action/deliverable_generator.py` | (입력: `github_url`, `milestone_number`, `github_token`) | `{markdown, dev_deliverable, review_deliverable, pr_count, ...}` |
| `milestone-collector` | 同 (Step 1) | 입력은 deliverable-generator와 동일 | `{owner, repo, milestone, prs, pr_count, milestone_title, milestone_number}` |
| `dev-deliverable-gen` | 同 (Step 2) | milestone-collector 출력을 입력으로 | 입력 + `{dev_deliverable, total_additions, total_deletions, total_files}` |
| `review-deliverable-gen` | 同 (Step 3) | dev-deliverable-gen 출력을 입력으로 | 입력 + `{review_deliverable, review_count, markdown(결합)}` |

### 4.3 AI 노드

| nodeId | 핸들러 | 설명 |
|---|---|---|
| `ai-custom` | `ai/ai_custom.py` | **가장 많이 쓰는 AI 노드.** `aiNodeId`가 있으면 해당 `AINode` 템플릿(프롬프트+스키마+LLM설정) 실행. 없으면 `config.prompt`+`config.systemPrompt`를 직접 사용 |
| `ai-chat`, `ai-classify`, `ai-extract`, `ai-summarize` | 同 (별칭) | `ai-custom`과 동일 핸들러, 표시명만 다름 |
| `ai-api-router` | `ai/ai_api_router.py` | 활성화된 모든 `ApiDefinition` 카탈로그를 LLM에 제시하고, 입력을 분석해 **적절한 API를 자동 선택·호출**. `config.apiIds`로 후보 제한 가능 |

**ai-custom 큐 FIFO**: 같은 노드 인스턴스에 대해 동시 실행이 들어오면 `node_queue_items`에 PENDING으로 enqueue되어 오래된 것부터 PROCESSING으로 승격. 완료/실패 시 큐에서 제거. 토큰 폭주 방지용.

**AINode 자동 타입 변환**: `input_schema`의 `properties[key].type`이 `"string"`인데 실제 값이 dict/list이면 `json.dumps(ensure_ascii=False)` 적용. `None`은 스키마 타입별 기본값(`""`, `[]`, `{}`)으로 대체.

### 4.4 Logic 노드

| nodeId | 핸들러 | config 주요 키 | 출력 특이점 |
|---|---|---|---|
| `condition` | `logic/condition.py` | `conditions: [{field, operator, value, branchId}]` — operators: `equals`/`notEquals`/`contains`/`greaterThan`/`lessThan` | `{matched, branch}` (현재 분기 라우팅 미구현 TODO) |
| `sorter` | `logic/sorter.py` | `rules: [{id, field, operator, value}]`, `dedup: {enabled, warehouseNodeId, matchField}` | `{__sorterHandle}` — 엔진이 매칭된 handle ID로 outgoing edge 필터링 |
| `unpacker` | `logic/unpacker.py` | `arrayField`(dot-path 지원) | `{items, count, __unpackItems}` — 엔진이 각 아이템마다 downstream chain을 반복 실행 |
| `mapper` | `logic/mapper.py` | `warehouseNodeId`, `matchKey`(dot-path), `outputField` | 입력 + `{[outputField]: matchedEntries, matchedCount}` |
| `loop` | `logic/loop.py` | (미구현) | — |
| `merge`, `switch` | (미구현, 디렉토리만) | — | — |

**sorter 라우팅 규칙** (`workflow_engine.py:189`): sorter의 outgoing_connection마다 `source_handle`이 있음. sorter 출력의 `__sorterHandle` 값과 `source_handle`이 일치하는 엣지만 downstream으로 전달. 매치 없으면 `"default"` handle로 fallback. `__skip__` 핸들로 출력하면 모든 다운스트림 차단(중복필터 스킵).

**unpacker 반복 실행** (`workflow_engine.py:198`): 배열을 분해하고, 엔진이 `_execute_downstream_chain`으로 전체 다운스트림 체인을 각 아이템마다 재실행. 반복 후 결과는 `outputData`를 리스트로 묶어 누적.

### 4.5 Transform 노드

| nodeId | 핸들러 | config 주요 키 | 출력 |
|---|---|---|---|
| `code` | `transform/code.py` | `code`(Python 문자열) | `result` 변수 값. RestrictedPython 샌드박스 실행 |
| `set-variable` | `transform/set_variable.py` | `variables: [{name, value}]` (value는 템플릿) | `{[name]: rendered, ...}` |
| `json-parse` | `transform/json_parse.py` | `source`(dot-path) | 문자열이면 `json.loads` 적용한 값, 아니면 원본 |

### 4.6 Output 노드

| nodeId | 핸들러 | config 주요 키 | 출력 |
|---|---|---|---|
| `result` | `output/warehouse.py` | `dedupKeyTemplate`(선택) | 입력 그대로 + `WarehouseEntry`에 축적 |
| `markdown-viewer` | 同 (별칭) | 同 | 마크다운 프리뷰 UI용 (엔진은 동일 취급) |
| `output-webhook` | `output/output_webhook.py` | `url` | 입력을 JSON으로 POST, `{status, sent}` |
| `output-log` | `output/output_log.py` | — | 로그 기록 |

**창고(WarehouseEntry)** 는 `result`/`markdown-viewer`/`sorter` 노드가 자동으로 기록한다 (`node_instance_id`로 구분). 다른 노드(`mapper`, `warehouse-query`)가 이 창고를 쿼리. `dedup_key`는 SHA1의 앞 32자.

---

## 5. 워크플로우 실행 라이프사이클

### 5.1 실행 시작
1. `POST /api/v1/workflows/{id}/execute` 또는 `POST /api/v1/factory/execute` → `WorkflowExecution` 레코드 PENDING으로 생성
2. FastAPI `BackgroundTasks`가 `execute_workflow(execution_id)` (= `WorkflowEngine.run`) 비동기 호출
3. 응답은 실행 ID가 포함된 Execution 객체 즉시 반환 (비동기)

### 5.2 엔진 단계 (`WorkflowEngine.run` - `services/workflow_engine.py:54`)
```
1. _load_execution       # Execution + Workflow + nodes + connections 로드
2. _build_dag            # incoming_edges, outgoing_edges, outgoing_connections 인덱싱
3. _find_start_nodes     # TRIGGER_TYPES ∩ (incoming edge 없는 노드). input_data._triggerNodeId로 특정 트리거 강제 가능
4. status = RUNNING, started_at 세팅
5. 각 start 노드에 initial belt_data = execution.input_data 세팅
6. _execute_dag (BFS)
   while queue or in_progress:
     ready = [n for n in queue if all(dep in completed for dep in incoming_edges[n])]
     for node_id in ready:
        _execute_node
        # → _collect_belt_input (업스트림 벨트 병합)
        # → _resolve_input_mapping ($. 경로 해석, 없으면 belt 전체)
        # → NodeHandlerRegistry.get(definition_type).execute(node, input_data, ctx)
        # → output을 belt_data[node_id] = {**output, _passthrough: belt_input}로 저장
        # → node_results[node_id] = {status, inputData, outputData, start/end time, logs}
        db.commit()  # SSE 구독자에게 실시간 업데이트
        # 라우팅:
        #   sorter → __sorterHandle에 매칭되는 outgoing만 queue에 enqueue
        #   unpacker → _execute_downstream_chain을 아이템마다 반복
        #   나머지 → 모든 outgoing을 queue에 enqueue
7. status = COMPLETED, output_data = _collect_outputs() (result/markdown-viewer/sorter/leaf)
8. (에러 시) status = FAILED, error_node_id/error_message 기록
```

### 5.3 실시간 모니터링
- **SSE 스트림**: `GET /api/v1/workflows/executions/{execution_id}/stream` 또는 `/api/v1/factory/executions/{execution_id}/stream`
  - 0.5초 폴링, `data: {status, nodeResults}` → 완료 시 `{status, output, error}` 최종 전송 후 종료
- **상세 조회**: `GET /api/v1/workflows/executions/{execution_id}` (non-stream)
- **취소**: `POST /api/v1/factory/executions/{execution_id}/cancel` → status를 CANCELLED로 (단, 진행 중인 핸들러 중단은 협조적)

### 5.4 트리거 종류별 진입 경로
| 트리거 | 실행 진입 |
|---|---|
| `manual`, `form-start` | 사용자가 UI에서 실행 버튼 / `/execute` API 호출 |
| `api-start` | `/execute` API 호출 시 트리거 노드가 `apiDefinitionId`로 외부 API를 자체 호출하여 데이터 획득 |
| `schedule-trigger` | `core/scheduler.py::_run_workflow_job`이 cron 도달 시 `WorkflowExecution` 생성 후 `execute_workflow` 호출 |
| `webhook` | 현재 전용 진입 라우트 없음 (레거시 별칭만 존재) |

### 5.5 에러·타임아웃
| 설정 | 기본값 | 위치 |
|---|---|---|
| 전체 실행 타임아웃 | 300초 | `settings.WORKFLOW_MAX_EXECUTION_TIME` |
| 노드당 타임아웃 | 60초 | `settings.WORKFLOW_NODE_TIMEOUT` |
| 최대 노드 수 | 100 | `settings.WORKFLOW_MAX_NODES` |
| HTTP 클라이언트 기본 timeout | 30초 | `httpx.AsyncClient(timeout=30)` 하드코딩 |
| AI 큐 대기 | 300초 | `ai_custom.py:max_wait` |

---

## 6. API 참조

Base URL: `http://localhost:8002/api/v1`. 모든 응답은 camelCase. 인증 없음.

### 6.1 AI Node — `/nodes`
| Method | Path | 용도 |
|---|---|---|
| GET | `/nodes` | 목록 (query: `category`, `is_active`, `q`, `skip`, `limit`) |
| GET | `/nodes/{id}` | 단건 |
| POST | `/nodes` | 생성 → body는 camelCase (`systemPrompt`, `userPromptTemplate`, `inputSchema`, `outputSchema`, `outputEnforcement`, `llmConfig`, `isActive` 등) |
| PATCH | `/nodes/{id}` | 부분 수정 |
| DELETE | `/nodes/{id}` | 삭제 |
| POST | `/nodes/{id}/test` | 단건 테스트 실행 (LLM 호출) |

### 6.2 API Definition — `/api-definitions`
| Method | Path | 용도 |
|---|---|---|
| GET | `/api-definitions` | 목록 |
| GET | `/api-definitions/{id}` | 단건 |
| POST | `/api-definitions` | 생성 (body: `name`, `method`, `urlTemplate`, `headers`, `bodyTemplate`, `authType`, `authConfig`, `parameters`, `responseSchema`) |
| PATCH | `/api-definitions/{id}` | 수정 |
| DELETE | `/api-definitions/{id}` | 삭제 |
| POST | `/api-definitions/{id}/execute` | DB에 저장된 스펙으로 실행 |
| POST | `/api-definitions/test-api` | 즉석 테스트 (저장 없이) |
| POST | `/api-definitions/capture` | HAR/curl 같은 원시 입력으로 스펙 추출 |

**중요**: `urlTemplate`의 실제 호출 URL 저장 위치는 `api_definitions.url_template` (DB 필드). 프론트 노드의 `config.url`은 UI 캐시일 뿐. (`../memory/MEMORY.md` 참조)

### 6.3 Workflow — `/workflows`
| Method | Path | 용도 |
|---|---|---|
| GET | `/workflows` | 목록 (query: `status`) |
| GET | `/workflows/{id}` | 상세 (nodes + connections 포함) |
| POST | `/workflows` | 생성 (body는 §6.2 §6 [EXAMPLE_DATA_INJECTION_GUIDE.md](./EXAMPLE_DATA_INJECTION_GUIDE.md) 참조) |
| PATCH | `/workflows/{id}` | 수정 (노드/연결 전체 교체) |
| DELETE | `/workflows/{id}` | 삭제 |
| POST | `/workflows/{id}/execute` | 실행 (body: `{inputData: {...}}`) |
| GET | `/workflows/{id}/executions` | 해당 WF의 실행 이력 |
| GET | `/workflows/executions/{execution_id}` | 실행 상세 |
| GET | `/workflows/executions/{execution_id}/stream` | SSE 실시간 스트림 |
| POST | `/workflows/executions/{execution_id}/cancel` | 취소 |

### 6.4 Factory Map (싱글톤) — `/factory`
워크플로우 ID `"factory-main"`의 특수 취급 버전. API 스키마는 WF와 거의 동일하지만 ID 고정.

| Method | Path | 용도 |
|---|---|---|
| GET | `/factory` | 맵 조회 (없으면 자동 생성) |
| PATCH | `/factory` | 맵 저장 (노드, 연결, 뷰포트) |
| DELETE | `/factory/nodes/{node_id}` | 노드 단건 삭제 |
| POST | `/factory/execute` | 전체 실행 |
| GET | `/factory/executions` | 팩토리 실행 이력 |
| GET | `/factory/executions/{id}` | 실행 상세 |
| GET | `/factory/executions/{id}/stream` | SSE |
| POST | `/factory/executions/{id}/cancel` | 취소 |
| GET | `/factory/warehouse/{node_id}` | 창고 조회 (특정 node_instance의 WarehouseEntry 목록) |
| DELETE | `/factory/warehouse/{node_id}` | 창고 비우기 |
| DELETE | `/factory/warehouse/{node_id}/entries` | 선택 삭제 |
| GET | `/factory/queue/{node_id}` | 해당 노드 입력 큐 조회 |
| DELETE | `/factory/queue/{node_id}` | 큐 비우기 |
| GET | `/factory/queue/{node_id}/count` | 큐 개수 |

### 6.5 Knowledge — `/knowledge`
| Method | Path | 용도 |
|---|---|---|
| GET | `/knowledge` | 문서 목록 (파일 스캔 + ChromaDB 해시 비교로 sync 상태 산출) |
| GET | `/knowledge/meta` | 전체 카테고리/태그 집계 |
| GET | `/knowledge/{doc_id}` | 단건 |
| POST | `/knowledge` | 생성 (body: `title`, `content`, `category`, `tags`, `source`, `api?`) |
| PUT | `/knowledge/{doc_id}` | 전체 교체 |
| DELETE | `/knowledge/{doc_id}` | 삭제 (파일 + ChromaDB) |
| POST | `/knowledge/sync` | **중요**: query `id=xxx` 있으면 단건 즉시 동기화, 없으면 전체 백그라운드 동기화 |
| GET | `/knowledge/sync/status` | 백그라운드 동기화 진행률 |
| POST | `/knowledge/search` | 벡터 유사도 검색 (body: `{query, topK, category}`) |

### 6.6 Warehouse (전역) — `/warehouse`
| Method | Path | 용도 |
|---|---|---|
| GET | `/warehouse/search?dedupKey=...&nodeId=...` | dedupKey 원문으로 검색 (서버에서 SHA1 해시 후 매칭) |

### 6.7 Tickets (칸반) — `/tickets`
| Method | Path | 용도 |
|---|---|---|
| GET | `/tickets/stats` | 카테고리/상태/우선순위별 count, SLA 초과 |
| GET | `/tickets` | 목록 |
| POST | `/tickets` | 생성 |
| GET/PATCH/DELETE | `/tickets/{id}` | CRUD |

### 6.8 Ops (운영 대시보드) — `/ops`
| Method | Path | 용도 |
|---|---|---|
| GET | `/ops/dashboard` | 최근 7일 WF/실행/티켓 통합 집계 |
| GET | `/ops/audit` | 감사 로그 조회 |
| GET | `/ops/scheduler/jobs` | 등록된 cron job 목록 |
| POST | `/ops/scheduler/reload` | 스케줄러 job 재로드 |
| POST | `/ops/scheduler/trigger/{workflow_id}` | cron 무시하고 즉시 트리거 |

### 6.9 Chat — `/chat`
| Method | Path | 용도 |
|---|---|---|
| POST | `/chat/message` | AI 채팅 메시지 전송 |
| GET | `/chat/sessions` | 세션 목록 |
| GET | `/chat/session/{id}` | 세션 이력 |
| POST | `/chat/session` | 새 세션 |
| DELETE | `/chat/session/{id}` | 세션 삭제 |

### 6.10 Export/Import
§6.7 [EXAMPLE_DATA_INJECTION_GUIDE.md](./EXAMPLE_DATA_INJECTION_GUIDE.md) 참조.

### 6.11 Mock 외부 API (워크플로우 테스트용)
- `GET /rest-comm/support/view-list` — 사내 문의글 조회 목업 데이터 (backend/app/main.py:22에 하드코딩)

이 목업은 8002(AI 업무도우미)에 **같이** 떠 있음. 별도 목업API서버(8001)와 구분 필요.

---

## 7. 프론트엔드 활용

### 7.1 주요 페이지
| 경로 | 파일 | 역할 |
|---|---|---|
| `/` | `DashboardPage.tsx` | 홈 대시보드 |
| `/factory` | `FactoryPage.tsx` | 싱글톤 공장맵 (n8n 스타일 캔버스) |
| `/workflow/:id?` | `WorkflowPage.tsx` | 개별 워크플로우 에디터 |
| `/knowledge` | `KnowledgeBasePage.tsx` | 지식 문서 CRUD + 벡터 검색 |
| `/nodes` | `NodeManagementPage.tsx` | AI Node 템플릿 관리 |
| `/api-definitions` | `ApiDefinitionPage.tsx` | API 정의 카탈로그 |
| `/ops` | `OpsDashboardPage.tsx` | 운영 대시보드(WF/실행/감사) |

### 7.2 노드 레지스트리 패턴
`frontend/src/nodes/registrations.ts`가 모든 노드를 `nodeRegistry.register({...})`로 등록. 항목:
- `defType` (백엔드 NodeDefType와 일치)
- `category` (`starter`/`ai`/`logic`/`action`/`output`)
- `reactFlowType` (ReactFlow 노드 타입명)
- `component` (노드 카드 컴포넌트)
- `palette` (팔레트 UI 메타 — 없으면 팔레트 미노출)
- `configPanel` (선택 시 오른쪽 설정 패널)
- `createNodeData` (드롭 시 초기 데이터 팩토리)
- `staticOutputFields` (스키마 없는 시스템 노드용 고정 필드)
- `panelBehavior` (`{ onClick: 'config'|'detail'|'queue'|'warehouse'|'none' }`)
- `minimapColor`

### 7.3 인터랙션 관례
| 동작 | 결과 |
|---|---|
| 팔레트 → 캔버스 드래그 | 새 노드 생성 (`createNodeData` 실행) |
| 노드 클릭 | `panelBehavior.onClick`에 따라 우측 패널: `config`(설정) / `queue`(큐 조회) / `warehouse`(창고 조회) |
| 노드 더블클릭 | `panelBehavior.onDoubleClick`: `detail`(실행 결과 모달) / `markdown-modal` |
| 엣지 연결 | `connections`에 추가. sorter에서 나가는 엣지는 `source_handle` 지정 (규칙 ID) |
| 실행 버튼 (트리거 노드) | `/execute` API 호출 → SSE 구독 → 노드 카드에 실시간 status/logs |

### 7.4 AI 노드 드래그 특별 케이스
`registrations.ts:101` 주석대로, AI 노드는 팔레트에서 별도 처리 (`aiNodes` 목록에서 드래그). 드롭 시 `extra.aiNode.id`가 `WorkflowNode.ai_node_id`에 저장되어 `ai-custom` 핸들러가 참조.

---

## 8. 고급 기능

### 8.1 템플릿 문법
- `{{field}}` — 루트 키 치환
- `{{nested.path.value}}` — dict의 중첩 경로
- 값이 dict/list → JSON 직렬화
- 값이 None → 빈 문자열
- 중간 경로가 비-dict → 빈 문자열

템플릿은 `url_template`, `bodyTemplate`, `webhookUrl`, `messageTemplate`, `outputPath`, AI 노드의 `userPromptTemplate`/`systemPrompt`, ai-custom의 `prompt`/`systemPrompt`, set-variable의 `value`, warehouse_query/sorter의 `dedupKey` 등에서 사용.

### 8.2 dedup_key (중복 필터)
`sorter`의 `dedup.enabled=true` + `warehouseNodeId` + `matchField` 조합:
- 업스트림에서 온 값(`matchField`)이 지정 창고에 이미 있으면 `__skip__` handle로 라우팅 → 하류 실행 차단

`warehouse-query`의 `dedupKey`(템플릿):
- 템플릿 렌더링 후 `hashlib.sha1(rendered).hexdigest()[:32]` 해시
- `WarehouseEntry.dedup_key` 컬럼과 매칭하여 `exists`/`latest`/`list` 모드로 조회

전역 창고 검색 `/api/v1/warehouse/search?dedupKey=원문값` — 서버가 동일 해시 변환 후 매칭.

### 8.3 스케줄 트리거
1. 워크플로우에 `schedule-trigger` 노드 포함 + `config: {cronExpr: "0 9 * * *", timezone: "Asia/Seoul", payload: {...}}` 설정
2. 워크플로우 status를 `ACTIVE`로
3. 서버 기동 시 또는 `POST /ops/scheduler/reload` 호출 시 APScheduler가 cron job 등록 (`core/scheduler.py`)
4. 도달 시점에 `_run_workflow_job` → `WorkflowExecution` 생성 → `execute_workflow` 호출
5. `GET /ops/scheduler/jobs`로 등록된 잡 확인, `POST /ops/scheduler/trigger/{workflow_id}`로 강제 트리거

### 8.4 RestrictedPython 샌드박스
`code` 노드는 `backend/app/sandbox/executor.py`의 `execute_code`로 실행. 제한:

**허용 내장** (`ALLOWED_BUILTINS`, `executor.py:52`): `bool/int/float/str/list/tuple/dict/set`, `abs/round/min/max/sum/pow`, `len/range/enumerate/zip/map/filter/sorted/reversed`, `isinstance/type/id/hash`, `hasattr/getattr/setattr`, `print`(로그수집), 주요 Exception 등.

**허용 모듈** (`ALLOWED_MODULES`): `json`, `math`, `re`, `datetime`, `collections`, `itertools`, `functools`, `operator`, `random`, `string`, `base64`, `hashlib`, `uuid`, `decimal`, `statistics` — 각 모듈별로 화이트리스트된 심볼만 접근 가능.

**금지 패턴** (`_validate_code`): `__builtins__`, `__class__`, `__subclasses__`, `os.system`, `subprocess`, `eval(`, `exec(`, `compile(`, `open(`, `__import__("os")` 등.

**실행 환경**: 입력은 `input` 변수로 주입, 결과는 `result` 변수에 넣으면 반환됨. 기본 10초 타임아웃, 1MB 출력 제한.

```python
# code 노드 예시 config.code
numbers = input.get('values', [])
result = {'sum': sum(numbers), 'avg': sum(numbers)/len(numbers) if numbers else 0}
```

### 8.5 지식 검색 세부
- 임베딩: 로컬 `jhgan_ko-sroberta-multitask` ONNX (완전 오프라인)
- 유사도: ChromaDB HNSW, `metadata={"hnsw:space": "cosine"}`
- `knowledge` 노드는 `max_results`를 `[4, 7]`로 클램핑 (너무 많거나 적으면 강제 보정)
- 카테고리 필터: 단일 `{category: X}` 또는 다중 `{category: {$in: [...]}}`
- 태그 필터: 벡터 DB 외에서 후처리 (교차 필터링)
- 쿼리 없음 + 카테고리만 있으면 카테고리명 자체로 검색 (전체 카테고리 문서 조회 근사)

### 8.6 LLM 프로바이더 라우팅
`settings.DEFAULT_LLM_PROVIDER` 또는 `ai-custom`의 `config.provider`로 지정:
- `openai` — `OPENAI_API_KEY`
- `anthropic` — `ANTHROPIC_API_KEY`
- `azure` — Azure OpenAI Service (`AZURE_OPENAI_ENDPOINT/API_KEY/DEPLOYMENT`)
- `custom_api` — 사내 API (`CUSTOM_API_URL/KEY/MODEL`)
- `external` — Dify/Agent Builder 호환 우회 시스템 (`EXTERNAL_LLM_API_KEY/URL`, `EXTERNAL_LLM=true`)

`app/services/llm/` 하위에 프로바이더별 핸들러. `call_llm` (레거시) / `chat` (신규) / `get_llm_handler` 모두 내부적으로 `app.services.llm` 모듈로 위임.

### 8.7 감사 로그 (audit_log)
`services/audit.py::log()`가 best-effort로 `audit_logs` 테이블에 기록. 실패해도 메인 트랜잭션에 영향 없음. 기록 항목: `actor`, `action`(예: `"workflow.execute"`), `target_type`, `target_id`, `details`(JSON). `GET /ops/audit`로 조회.

---

## 9. 확장 방법

### 9.1 새 노드 핸들러 추가
```python
# backend/app/nodes/action/my_new.py
from typing import Any, Dict
from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext

@NodeHandlerRegistry.register
class MyNewHandler(NodeHandler):
    node_type = "my-new"       # NodeDefType에도 추가할 것
    category = "action"        # trigger/ai/logic/transform/action/output
    display_name = "나의 새 노드"
    description = "뭔가 해준다"

    async def execute(self, node, input_data: Dict[str, Any], ctx: ExecutionContext) -> Any:
        config = node.config or {}
        # ctx.db, ctx.execution_id, ctx.node_id, ctx.render_template, ctx.get_nested_value 사용 가능
        rendered = ctx.render_template(config.get("messageTemplate", ""), input_data)
        return {"message": rendered}
```

**필수 작업**:
1. 파일 생성 (위치: `nodes/{category}/*.py`)
2. `NodeDefType`에 enum 값 추가 (`backend/app/core/constants.py:11`)
3. 해당 카테고리 `__init__.py`에 import 추가 (자동 등록 트리거)
4. 프론트엔드 `nodes/registrations.ts`에 등록 (팔레트·설정 패널 원하면)

### 9.2 새 API 라우트 추가
```python
# backend/app/api/routes/my_module.py
from fastapi import APIRouter, Depends
from ...core.database import get_db
router = APIRouter()

@router.get("")
async def list_something(db = Depends(get_db)):
    ...
```

**필수**: `backend/app/api/__init__.py`에 `include_router` 추가.

```python
from .routes import my_module
api_router.include_router(my_module.router, prefix="/my-module", tags=["MyModule"])
```

### 9.3 새 SQLAlchemy 모델
```python
# backend/app/models/my_model.py
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from ..core.database import Base

class MyModel(Base):
    __tablename__ = "my_models"
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

**필수**: `backend/app/models/__init__.py`에 export 추가. 다음 기동 시 `init_db()`가 `create_all`로 자동 생성.

### 9.4 새 AINode 타입 (코드 수정 없이)
프롬프트·스키마·LLM 설정만 다르면 `POST /api/v1/nodes`로 AINode를 추가하고, 워크플로우에서 `ai-custom` 노드에 `aiNodeId`로 연결하면 끝. 핸들러 코드 수정 불필요.

---

## 10. 트러블슈팅

### 10.1 API 호출 노드에 쿼리 파라미터가 붙지 않는다
- `ApiDefinition.parameters`에 `{name: "foo", in: "query"}`가 선언돼 있어야 자동 URL 추가됨 (`nodes/action/api_call.py:82`)
- 값 출처 우선순위: 업스트림 벨트 > `config.defaultParams` > 파라미터의 `default`
- 노드 UI의 `config.url`은 UI 캐시일 뿐 실제 호출 URL은 DB의 `api_definitions.url_template` (이 불일치 주의)

### 10.2 한글 JSON POST 시 글자 깨짐
- Windows 쉘에서 curl 인라인 JSON 인코딩 문제. **UTF-8 파일로 저장 후 `--data-binary @file.json`** 사용
- 또는 Python `urllib.request.Request(data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json; charset=utf-8"})` 사용

### 10.3 포트 8002 충돌
- `netstat -ano | grep ":8002 " | grep LISTENING` → PID 확인 → `taskkill //F //PID <pid>`
- `CLAUDE.md`의 **kill-then-start** 규칙 엄수. 대체 포트 금지.

### 10.4 RAG 검색 결과에 최신 지식이 안 나옴
- `POST /api/v1/knowledge/sync` (전체 백그라운드) 또는 `POST /api/v1/knowledge/sync?id=xxx` (단건 즉시)
- 진행률 확인: `GET /api/v1/knowledge/sync/status`
- `knowledge` 노드 `searchField`가 비어 있으면 입력의 모든 문자열 값을 concat해 검색함 — 명시적으로 `searchField: "description"` 등 지정 권장

### 10.5 워크플로우 실행은 되는데 출력이 비어있음
- `_collect_outputs`는 `output-*`/`result`/`markdown-viewer`/`sorter` 타입만 수집
- 이도 저도 없으면 **leaf 노드**의 output이 fallback — 그래프 말단에 `result` 노드 하나 두는 게 안전

### 10.6 ai-custom 노드가 시간 초과로 실패
- 큐 대기 5분 기본. 같은 노드 인스턴스에 너무 많이 쌓이면 FIFO로 순차 처리되어 뒤쪽이 밀림
- 노드 큐 비우기: `DELETE /api/v1/factory/queue/{node_id}`

### 10.7 sorter 연결이 실제로 라우팅 안 됨
- sorter의 outgoing `connection.source_handle` 값이 `rule-{rule.id}` 포맷과 정확히 일치해야 함
- sorter 출력 `__sorterHandle`이 `"default"`이면 `source_handle`이 `"default"` 또는 `null`인 엣지만 통과
- 매칭 실패 시 모두 차단되지 않고 `default`로 폴백

### 10.8 unpacker 다운스트림이 한 번만 실행됨
- `arrayField`가 실제 배열인지 확인. dict면 `ValueError`. 빈 배열이면 다운스트림 스킵
- 배열 경로는 dot-path 지원: `"data.items"`도 OK

### 10.9 schedule-trigger가 안 뜬다
- 워크플로우 status가 ACTIVE여야 함 (DRAFT/PAUSED/ARCHIVED 불가)
- `cronExpr` 형식 검증 (APScheduler CronTrigger 문법 — 5필드 또는 6필드)
- `POST /api/v1/ops/scheduler/reload`로 강제 재로드
- `GET /api/v1/ops/scheduler/jobs`로 실제 등록 확인

### 10.10 좀비 실행/큐가 남아있음
- 서버 재기동 시 `main.py::_cleanup_zombie_state`가 `node_queue_items`의 PROCESSING/PENDING 삭제, `workflow_executions`의 RUNNING을 FAILED로 변환
- 그래도 이상하면 `backend/data/app.db`를 `sqlite3`로 열어 직접 확인

### 10.11 code 노드가 `SandboxViolationError`
- `open/eval/exec/__import__("os")` 등 금지 패턴 점검
- 필요한 모듈이 `ALLOWED_MODULES` 화이트리스트에 없으면 추가하거나 다른 노드(`http-request`, `json-parse`, `set-variable`)로 대체

### 10.12 `EXTERNAL_LLM=true`인데 호출 실패
- `EXTERNAL_LLM_API_URL`은 `/v1/chat-messages` 경로까지 포함해야 함 (Dify/Agent Builder 호환)
- Bearer 토큰 포함 확인

---

## 11. 관련 문서

| 문서 | 역할 |
|---|---|
| [`EXAMPLE_DATA_INJECTION_GUIDE.md`](./EXAMPLE_DATA_INJECTION_GUIDE.md) | AINode / ApiDefinition / Knowledge / Workflow 주입 상세 가이드. curl/Python 예제 포함 |
| [`../CLAUDE.md`](../CLAUDE.md) | 이 하위 프로젝트의 AI 운영 지침 (포트·위임·kill-then-start) |
| [`../../ORCHESTRATION.md`](../../ORCHESTRATION.md) | 4개 서브프로젝트 전역 오케스트레이션 |
| [`../../AGENTS.md`](../../AGENTS.md) | 전역 AI 에이전트 구성 |
| [`../../목업API서버/`](../../목업API서버/) | 사내 Jira/Confluence/메신저/메일 API 모사 (`http://localhost:8001`) |

**핵심 코드 진입점** (빠른 탐색용):
- 실행 엔진: `backend/app/services/workflow_engine.py:34` (`WorkflowEngine`)
- 노드 레지스트리: `backend/app/nodes/registry.py:6` (`NodeHandlerRegistry`)
- 상수 정의: `backend/app/core/constants.py:11` (`NodeDefType`, `BeltKey`)
- 설정: `backend/app/core/config.py:15` (`Settings`)
- API 라우터 등록: `backend/app/api/__init__.py:8`
- 샌드박스: `backend/app/sandbox/executor.py:193` (`SandboxedExecutor`)
- 프론트 노드 레지스트리: `frontend/src/nodes/registrations.ts:1`
