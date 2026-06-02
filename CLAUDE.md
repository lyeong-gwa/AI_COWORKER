# AI 업무도우미 (범용 업무자동화 플랫폼)

> **반드시 루트 `../ORCHESTRATION.md`, `../AGENTS.md` 먼저 읽어라.**

---

## 1. 이 시스템은 무엇인가

AI 업무도우미는 **ITO 담당자의 업무를 CLI 주도로 자동화하는 범용 백엔드 플랫폼**이다. 특정 도메인(GitHub 마일스톤, 코드정적분석, 티켓 분류 등)에 종속되지 않는다. CLI가 사용자와 대화하며 필요한 재료(지식문서, API 명세, 커스텀 AI 노드)를 등록하고, 범용 노드 11종을 조립하여 워크플로우를 구성한다.

웹 UI는 실행 트리거와 결과 조회 전용 대시보드다. 편집·생성 기능은 웹 UI에 없다. 모든 조립과 수정은 CLI가 REST API를 직접 호출하여 수행한다.

시스템은 항상 **제로 스타트**에서 출발한다. 사용자는 미리 명세 파일을 작성하지 않는다. CLI와 대화하며 필요한 재료를 점진적으로 등록하고 고도화한다.

---

## 2. 당신(CLI)의 역할

- **사용자 업무 요구사항 이해**: 사용자가 자동화하려는 업무를 구체적으로 파악하고, 어떤 재료(지식/API/AI 노드)가 필요한지 식별한다.
- **재료 등록**: 파악된 재료를 REST API로 순서에 맞게 등록한다. 워크플로우 조립 전에 재료부터 준비한다.
- **워크플로우 조립**: `GET /api/v1/nodes/catalog`로 노드 스펙을 확인하고, 범용 노드 11종만 사용하여 워크플로우를 설계·등록한다. 도메인 특화 노드 신설은 금지.
- **실행 및 결과 관찰**: `POST /api/v1/workflows/{id}/run`으로 실행을 시작하고 `instanceId`를 받아 SSE 스트림 또는 인스턴스 조회로 진행 상황을 관찰한다.
- **지식 프로모션**: 실행 결과가 유용하다고 판단될 때, **사용자 검토를 받은 후** CLI 명시 요청으로만 `POST /api/v1/knowledge/from-instance`를 호출한다. 자동 지식화 금지.
- **실패·오류 진단**: 실행 실패 시 인스턴스 상세와 노드 결과를 조회하여 원인을 파악하고 워크플로우 수정 또는 재조립을 제안한다.
- **웹 UI 유도**: 사용자가 웹 UI에서 편집을 요청하면 "편집은 CLI로만 가능하다"고 안내하고 CLI에서 처리한다.

---

## 3. 시스템 구성요소

| 구성요소 | 설명 |
|---------|------|
| **워크플로우** | 노드와 연결의 집합. CLI가 REST API로 생성·수정. 웹은 조회·실행만 가능. |
| **노드** | 워크플로우의 실행 단위. 범용 13종 중 선택하거나 커스텀 AI 노드(`ai-custom`)를 등록한다. |
| **지식문서** | ChromaDB에 임베딩되는 마크다운 파일. `knowledge` 노드가 RAG 검색에 사용. |
| **API 명세** | 외부 API의 URL/파라미터/응답 스키마를 등록한 레코드. `api-call`, `api-start`, `ai-api-router` 노드가 참조. |
| **인스턴스DB** | 동질 record 컬렉션. JSON Schema 강제. CLI가 등록·관리, 노드가 적재. |
| **인스턴스** | 워크플로우 실행 1회의 기록. 노드별 상태·결과·창고 항목을 포함. |
| **창고(Warehouse)** | `result`, `markdown-viewer` 노드가 인스턴스 실행 결과를 적재하는 저장소. 지식 프로모션의 원본. |

**데이터 흐름**

```
사용자 대화
    │
    ▼
LLM CLI (CLAUDE.md 기준)
    │ REST API (포트 8002)
    ├─ POST /api-definitions    재료 등록
    ├─ POST /knowledge
    ├─ POST /nodes
    ├─ POST /workflows
    │
    ▼
Backend (FastAPI + SQLAlchemy + ChromaDB)
    │
    ├─ POST /workflows/{id}/run → instanceId (202)
    │
    ▼
BackgroundTask (workflow_engine.py)
    │ SSE 스트림
    ▼
GET /warehouse/instances/{id}/stream
    │
    ▼
웹 UI (포트 5174) — 실행·조회 전용 대시보드
```

---

## 4. 기본 제공 노드 (범용 13종 요약 표)

| defType | 카테고리 | 한 줄 용도 |
|---------|---------|-----------|
| `form-start` | starter | 웹 실행 버튼 클릭 시 입력 폼 렌더 → 워크플로우 트리거 |
| `api-start` | starter | 등록된 API 명세를 호출한 결과로 워크플로우 트리거 |
| `ai-custom` | ai | 커스텀 AI 노드(ai_nodes) 또는 config 내 프롬프트로 LLM 직접 호출 |
| `ai-api-router` | ai | AI가 입력을 분석하여 적절한 API 명세를 선택·호출 |
| `sorter` | logic | config.rules 조건 평가 → 매칭 handle로 분기, default handle 포함 |
| `unpacker` | logic | 배열 필드를 개별 아이템으로 언팩 → 다운스트림 반복 실행 |
| `mapper` | logic | 창고(warehouse) 데이터에서 동일 키 항목 조회 → 현재 입력에 병합 |
| `api-call` | action | 등록된 API 명세를 AI 판단 없이 직접 호출 |
| `knowledge` | action | ChromaDB 벡터 DB에서 RAG 유사도 검색 → 컨텍스트 확보 |
| `instance-db-insert` | action | 인스턴스DB 적재 (자유 JSON 저장) |
| `instance-db-lookup` | action | 인스턴스DB 조회 (필터 매칭 다건) |
| `result` | output | 실행 결과를 창고(WarehouseEntry)에 저장 |
| `markdown-viewer` | output | 입력 필드를 마크다운으로 UI 렌더 + 창고 저장 겸용 |

**상세 스키마(inputs/outputs/config/useCases/connectsWellWith):**
```
GET http://localhost:8002/api/v1/nodes/catalog
```

범용 13종 외 도메인 특화 노드 신설 금지. 필요 기능은 `ai-custom` + `api-call` 조합으로 구현.

---

## 5. REST API 개요

**진실의 원천**: `http://localhost:8002/docs` (FastAPI 자동 생성 OpenAPI UI)
**에러 포맷**: 모든 오류는 `{"error": {"code": "...", "message": "...", "details": {...}}}` 구조로 반환.

### 5.1 재료 관리 (CLI 주도, 일부 삭제는 웹 허용)

> **편집 정책 (2026-05-27 갱신):**
> - **생성·수정** — 노드/API명세/워크플로우/인스턴스DB 메타는 **CLI 전용**
> - **지식문서** (`/knowledge`) — 웹 UI 에서 등록·편집·삭제 모두 허용 (순수 데이터, 점진적 큐레이션 필요)
> - **워크플로우 삭제** — **웹 UI 허용** (cascade: 실행이력·창고·노드결과 자동 정리)
> - **인스턴스DB records 삭제** — **웹 UI 허용** (단건·다건). 인스턴스DB 메타(스키마·이름) 자체 삭제는 CLI 전용 유지
> - 사유: 운영자가 SSH/파일시스템 우회 없이 사고 처리·재시도가 가능해야 함

| 메서드 | 경로 | 용도 |
|--------|------|------|
| GET | `/api/v1/nodes/catalog` | 11종 노드 상세 스펙 조회 |
| POST | `/api/v1/nodes` | 커스텀 AI 노드 등록 |
| PUT | `/api/v1/nodes/{id}` | 커스텀 AI 노드 수정 |
| DELETE | `/api/v1/nodes/{id}` | 커스텀 AI 노드 삭제 |
| POST | `/api/v1/knowledge` | 지식문서 등록 (CLI **및** 웹) |
| PUT | `/api/v1/knowledge/{doc_id}` | 지식문서 수정 (CLI **및** 웹) |
| DELETE | `/api/v1/knowledge/{doc_id}` | 지식문서 삭제 (CLI **및** 웹) |
| POST | `/api/v1/api-definitions` | 외부 API 명세 등록 |
| PUT | `/api/v1/api-definitions/{id}` | API 명세 수정 |
| DELETE | `/api/v1/api-definitions/{id}` | API 명세 삭제 |
| POST | `/api/v1/workflows` | 워크플로우 생성 (nodes + connections, position 없음) |
| PUT/PATCH | `/api/v1/workflows/{id}` | 워크플로우 수정 |
| DELETE | `/api/v1/workflows/{id}` | 워크플로우 삭제 |

### 5.2 실행·조회 (웹·CLI 공통)

| 메서드 | 경로 | 용도 |
|--------|------|------|
| POST | `/api/v1/workflows/{id}/run` | 백그라운드 실행 시작 → `{instanceId, workflowId, status:"queued"}` 즉시 반환 (HTTP 202) |
| GET | `/api/v1/workflows` | 워크플로우 목록 |
| GET | `/api/v1/workflows/{id}` | 워크플로우 상세 (nodes + connections) |
| GET | `/api/v1/workflows/{id}/instances` | 인스턴스 목록 |
| GET | `/api/v1/warehouse/instances/{id}` | 인스턴스 상세 (창고 데이터 포함) |
| GET | `/api/v1/warehouse/instances/{id}/stream` | SSE: 노드별 실행 진행상황 실시간 스트림 |
| GET | `/api/v1/nodes` | 커스텀 AI 노드 목록 |
| GET | `/api/v1/knowledge` | 지식문서 목록·검색 |
| GET | `/api/v1/api-definitions` | API 명세 목록 |
| POST | `/api/v1/api-definitions/{id}/probe` | **API 실행 + 응답 스키마 자동 저장** → `mappablePaths` (input_mapping 경로 목록) + `arrayGuide` 반환 |
| POST | `/api/v1/workflows/{id}/validate-flow` | 실행 전 데이터 흐름 정적 검증 → null 리스크 `issues` 목록 반환 |
| GET | `/api/v1/dashboard/summary` | 대시보드 집계 — `{counts: {todayRuns, inProgress, failed, completed}, workflows: [{...latestInstance}]}` |

### 5.3 인스턴스DB CRUD (CLI 전용)

| 메서드 | 경로 | 용도 |
|--------|------|------|
| POST | `/api/v1/instance-dbs` | 인스턴스DB 메타 등록 (name, description, tags) |
| GET | `/api/v1/instance-dbs` | 인스턴스DB 목록 (검색 q 파라미터) |
| GET | `/api/v1/instance-dbs/{id}` | 인스턴스DB 상세 |
| PUT | `/api/v1/instance-dbs/{id}` | 인스턴스DB 수정 |
| DELETE | `/api/v1/instance-dbs/{id}` | 인스턴스DB 삭제 (records cascade) |
| GET | `/api/v1/instance-dbs/{id}/records` | records 리스트 (limit/offset/sourceWorkflowId/sourceExecutionId) |
| GET | `/api/v1/instance-dbs/{id}/records/{rid}` | 단일 record 조회 |

### 5.4 지식 프로모션 (CLI 전용)

| 메서드 | 경로 | 용도 |
|--------|------|------|
| POST | `/api/v1/knowledge/from-instance` | 인스턴스 → 지식문서 프로모션. 요청 바디: `{instanceId, title, category, tags}` |

---

## 6. 작업 원칙

1. **제로 스타트**: 빈 시스템에서 시작. 기존 DB/ChromaDB 초기화가 필요하면 `python scripts/wipe.py --confirm` 실행.
2. **재료 먼저, 워크플로우 나중**: API 명세·지식문서·커스텀 AI 노드를 먼저 등록한 후 워크플로우를 조립한다.
2a. **[필수] API probe 후 input_mapping 작성**: API 명세를 등록한 직후 반드시 `POST /api/v1/api-definitions/{id}/probe`를 호출하여 실제 응답 구조를 확인한다. 반환된 `mappablePaths`의 `path` 값만을 input_mapping에 사용한다. 추측으로 경로를 작성하는 것은 **절대 금지**. 배열 필드는 `arrayGuide`의 `unpackerConfig`와 `downstreamMapping`을 참고한다.
2b. **[필수] 워크플로우 작성 전 검증**: `POST /api/v1/workflows/{id}/validate-flow`로 사전 검증 후 `issues`가 있으면 input_mapping을 수정한다.
2c. **[필수] 실행 후 감사 보고서 확인**: 실행 완료 후 `GET /api/v1/warehouse/instances/{id}`의 `outputData._executionAudit`을 확인한다. `nodesWithNullInputs`가 있으면 해당 노드의 `nullWarnings`를 보고 input_mapping을 수정한다.
3. **자동 지식화 금지**: 인스턴스 → 지식문서 이관은 사용자 검토 후 CLI 명시 요청으로만 수행. 실행 엔진이 자동 호출해서는 안 된다.
4. **범용성 유지**: 도메인 특화 노드(`milestone-collector` 등) 신설 금지. 새 요구사항은 `ai-custom` + `api-call` 조합으로 충족한다. 인스턴스DB는 인프라 자원이므로 이 원칙과 무관.
5. **실행 엔진 건드리지 않기**: `backend/app/services/workflow_engine.py`는 position 무관하게 안정적으로 동작한다. 수정하지 않는다.
6. **외부 API는 목업API 경유**: 사내 API(Jira/Confluence/메신저 등) 직접 호출 금지. 반드시 `목업API서버`(포트 8001)를 거쳐야 한다.
7. **실행은 비동기 백그라운드**: `POST /workflows/{id}/run`은 HTTP 202를 즉시 반환하고 `instanceId`를 제공한다. 실행 완료를 동기적으로 기다리지 않는다.
8. **진행상황은 SSE 스트림**: `GET /warehouse/instances/{id}/stream`으로 `EventSource` 구독. SSE 연결 불가 시 `/warehouse/instances/{id}` 폴링으로 fallback.
9. **노드별 timeout 존재**: ai-custom=600s, api-call=60s, knowledge=30s, 기본=300s. timeout 초과 시 노드 상태가 `failed`로 기록된다.
10. **지식 웹 편집 허용** (2026-05-14): 지식 페이지(`/knowledge`)에서 카테고리/태그/제목/본문 인라인 편집·신규 등록·삭제 가능. 다른 재료(노드/API명세/워크플로우)는 CLI 전용 정책 유지. 지식은 ChromaDB 재임베딩이 PUT 시 자동 처리되므로 웹 편집 시 추가 조치 불필요.
11. **첫 세팅 시 ONNX 모델 사전 확인**: clone 직후 세팅을 AI 가 진행할 때, ONNX 임베딩 모델(`backend/models/onnx/`)은 git 에 포함되지 않으므로 **세팅 자동 진행 전 반드시 사용자에게 "ONNX 모델이 준비되어 있습니까?"를 먼저 확인**한다. 미준비 시 진행을 중단하고 모델 확보 방법(사외망 다운로드 후 복사 / 사내 모델 저장소)을 사용자와 합의한 뒤 진행한다. (글로벌 `feedback_ask_before_workaround` 정책과 동일 취지)

---

## 7. 포트·기동

| 서비스 | 포트 |
|--------|------|
| Backend (FastAPI) | **8002** |
| Frontend (Vite) | **5174** |

대체 포트 금지. 기동 전 점유 PID 확인 후 kill (루트 `../ORCHESTRATION.md` 정책).

```bash
# Backend 기동 (포트 점유 kill 포함)
PORT=8002
PID=$(netstat -ano | grep ":$PORT " | grep LISTENING | awk '{print $5}' | head -1)
[ -n "$PID" ] && taskkill //F //PID $PID
cd "AI 업무도우미/backend" && uvicorn app.main:app --reload --port 8002

# Frontend 기동
PORT=5174
PID=$(netstat -ano | grep ":$PORT " | grep LISTENING | awk '{print $5}' | head -1)
[ -n "$PID" ] && taskkill //F //PID $PID
cd "AI 업무도우미/frontend" && npm run dev -- --port 5174 --strictPort

# DB 초기화 (제로 스타트)
cd "AI 업무도우미/backend" && python scripts/wipe.py --confirm
```

---

## 8. 디렉토리 구조 (간략)

```
AI 업무도우미/
├── backend/
│   ├── app/
│   │   ├── api/routes/          # FastAPI 라우터 (workflows, knowledge, nodes, ...)
│   │   ├── nodes/
│   │   │   └── catalog.py       # 노드 카탈로그 SSoT — 범용 11종 정의
│   │   ├── services/
│   │   │   ├── workflow_engine.py  # 실행 엔진 (수정 금지)
│   │   │   └── execution_bus.py    # SSE 이벤트 버스 (in-memory pub/sub)
│   │   └── main.py              # 앱 엔트리포인트
│   ├── data/
│   │   ├── app.db               # SQLite DB
│   │   └── chroma/              # ChromaDB 벡터 저장소
│   └── scripts/
│       ├── wipe.py              # DB/벡터 초기화
│       └── e2e_zero_start.py    # 제로 스타트 E2E 검증 스크립트
├── frontend/
│   └── src/                     # React + TypeScript (실행/조회 전용)
└── docs/
    └── redesign-plan.md         # 상세 설계서 (의결 사항·Phase 계획 포함)
```

---

## 9. 서브에이전트 지침 (executor/designer/architect에게)

### 담당 에이전트

- `planner` (opus) — 워크플로우 구조 설계, Phase 계획 수립
- `executor` (sonnet) — 백엔드·프론트엔드 소스 구현
- `designer` (sonnet) — 웹 UI (읽기전용 뷰어, 실행 대시보드)
- `architect` (opus) — 완료 검증 (완료 선언 전 필수)

### 운영 규칙

1. **직접 소스 수정 금지** — executor/designer에 위임. 오케스트레이터가 직접 `.py`, `.ts`, `.tsx` 파일을 편집하지 않는다.
2. **UI 변경은 designer 담당** — 프론트엔드 컴포넌트·스타일 수정은 designer에게 위임.
3. **완료 선언 전 architect 검증 필수** — 모든 Phase 작업 완료 후 architect가 검증해야만 완료 선언 가능.
4. **position/viewport 부활 금지** — DB 모델, 스키마, 프론트엔드 타입에 position/viewport 필드를 재추가하지 않는다.
5. **workflow_engine.py 수정 금지** — 실행 엔진은 안정적이므로 건드리지 않는다.
6. **테스트 회귀 확인** — 소스 수정 후 `cd backend && python -m pytest -q` 로 63개 테스트 통과 확인 필수.
7. **프론트엔드 빌드 확인** — 프론트엔드 변경 후 `cd frontend && npm run build` 0 에러 확인 필수.

---

## 10. 인접 프로젝트 계약

| 계약 ID | 상대 | 내용 |
|---------|------|------|
| **C3** | `../목업API서버/` (포트 8001) | 사내 Jira/Confluence/메신저/메일 API 모사. 사외망 제약으로 직접 사내 API 호출 금지. 필요 엔드포인트가 없으면 `../.omc/proposals/`에 제안 작성 후 목업API 담당에 요청. |
| (참고) | `../코드정적분석/` (포트 8000) | 분석 결과를 워크플로우 input으로 활용 가능 (현재 미연동) |

**루트 `../ORCHESTRATION.md` 정책이 모든 서브프로젝트 지침보다 우선한다.**
