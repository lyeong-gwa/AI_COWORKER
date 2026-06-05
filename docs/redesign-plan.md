# AI 업무도우미 개편 설계서 (v2 — CLI 주도 범용 플랫폼)

> **작성일**: 2026-04-22
> **상태**: Phase 1~5 완료, Phase 1-4 InstanceDB 파일시스템 재설계 완료
> **목적**: 세션 단절 시 흐름 유지 + CLI 컨텍스트 문서
> **Phase 4 완료**: 2026-04-22
> **Phase 5 완료**: 2026-04-22
> **Phase 6 — 인스턴스DB 1급 자원화 완료**: 2026-04-26

---

## 후속 변경 이력

### 2026-06-05 — 워크플로우 설계도(blueprint) 추출·이식 + 스냅샷 동결
워크플로우를 자체 포함 설계도로 추출·이식하는 기능. 핵심은 저장 시 스펙을 "동결(freeze-once)" 하여 원본 재료 변경과 무관하게 과거 스펙으로 실행하고, 필요하면 재동기화로만 최신 반영.
- **스냅샷 동결 (freeze-once)**: 워크플로우 저장 시 참조한 API명세(url/headers/bodyTemplate/responseSchema)와 커스텀 AI노드 스펙(system_prompt/parameters)을 노드 config에 `apiSpecSnapshot`/`aiNodeSnapshot` 필드로 저장. 런타임은 스냅샷 우선 실행(없으면 원본 live 참조 폴백).
- **NEW 엔드포인트: `GET /api/v1/blueprint/workflows/{id}`** — 설계도 추출. 응답은 자체 포함 JSON 문자열로 복사·붙여넣기 가능. 스냅샷·노드·연결·위치정보 포함, 재료(환경값 — 인증 토큰·defaultParams 값·헤더)는 `redactedFields` 매니페스트로 mask.
- **NEW 엔드포인트: `POST /api/v1/blueprint/import`** — `{blueprint, dryRun?}` 가져오기. 결정론적 재생으로 노드/연결에 새 id(`wn-`/`wc-`) 부여, 인스턴스DB는 이름 매칭 재사용 또는 신규 생성, **재료 레지스트리 미오염**(API명세/AI노드를 별도 등록하지 않고 워크플로우에만 임베드). 구조 검증 게이트 통과. dryRun이면 `{plan, reconciliation}` 반환(미저장), 정상 실행이면 `{workflowId, reconciliation}` + 새로운 인스턴스DB id 목록.
- **NEW 엔드포인트: `POST /api/v1/blueprint/workflows/{id}/fill-materials`** — 보정 단계: 추출 후 mask된 환경값을 입력. `{values:[{nodeRef, path, value}]}`. 예: nodeRef="node-3", path="config.apiDefinition.headers.Authorization", value="Bearer xxx".
- **NEW 엔드포인트: `POST /api/v1/blueprint/workflows/{id}/knowledge-remap`** — 보정 단계: knowledge 노드가 참조하던 카테고리를 대상 인스턴스의 카테고리로 재매핑. `{remaps:[{nodeRef, from, to}]}`. 지식은 live 의존이므로 인스턴스간 참조 이름 조정 필요.
- **NEW 엔드포인트: `POST /api/v1/workflows/{id}/resync-snapshots`** — 재동기화: 원본 API명세/커스텀 AI노드가 변경되었을 때 스냅샷만 새로 동결. `{nodeIds?, dryRun?}`. 전체 또는 특정 노드만 선택 동결.
- **백필 스크립트: `backend/scripts/backfill_snapshots.py`** — 기존 워크플로우에 스냅샷 추가 (한 줄 실행).
- **프론트엔드**: 워크플로우 상세 페이지에 "설계도 내보내기" 버튼(blueprint 추출), "재동기화" 버튼. 워크플로우 목록에 "설계도 가져오기" 버튼(`/workflows/import`). 가져오기 후 보정 단계 폼(fill-materials/knowledge-remap).
- **인스턴스DB**: 메타(name/viewerHints/tags/description)만 스냅샷, 레코드는 미복사(live).
- **지식**: 스냅샷 없음(live 의존). 타 인스턴스에 이식 시 `knowledge-remap` 엔드포인트로 카테고리 대응.
- **459 백엔드 테스트 통과 + 프론트 빌드 0 에러**.

### 2026-06-05 — 워크플로우 생성 채팅 이력 보존 + 편집 모드 복원
워크플로우 생성·편집 시 LLM 게이트웨이와의 대화를 보존하고 편집 모드에서 재생하는 기능. 핵심은 새 저장소 추가 없이 기존 생성 추적 JSONL을 재활용.
- **`Workflow.generationTraceIds: string[]`** — 이 워크플로우 생성·편집에 관여한 생성 추적(trace) id 배열. `POST /workflows` 설정, `PATCH /workflows/{id}` append/union(dedup).
- **생성 추적 저장소 확장** — 기존 JSONL trace는 `userMessage`, `assistantMessage` 필드를 추가로 저장하여 Q&A 쌍 재구성 가능.
- **NEW 엔드포인트: `GET /workflows/{id}/generation-traces`** — 순서대로(최신) 대화 항목 조회. 응답: `[{traceId, createdAt, mode, userMessage, assistantMessage, attempts, result, errorCount, warningCount}, ...]`
- **편집 모드 복원** — `/workflows/:id/edit` 진입 시 이전 대화 로드 → UI에 "── 이전 대화 ──" / "── 이어서 편집 ──" 구분선 및 muted "이전" 버블 표시 후 새 입력 폼.

### 2026-06-02 — 웹 채팅 워크플로우 생성 + 결정론적 검증 게이트
워크플로우 생성 주체를 **CLI 전용 → CLI + 웹 채팅** 으로 확장. 핵심 동기: CLI 모델별 생성 품질 편차, 그리고 단절 노드·데이터 비호환 워크플로우가 검증 없이 저장되던 문제.
- **결정론적 검증** `app/services/workflow_validator.py` — `validate_workflow_structure`. ERROR 9종(단절/도달불가/끊긴엣지/트리거없음/미지deftype/필수config누락/참조ID없음/sorter핸들/순환)은 생성·수정 시 422로 차단. WARNING 4종은 보고. 카탈로그가 SSoT. 모든 `POST/PATCH/PUT /workflows`에 게이트 적용 + 미저장 `POST /workflows/validate`.
- **단계적 생성** `app/services/workflow_generator.py` — `POST /workflows/generate`. 앱 백엔드가 `get_llm_handler()`(폐쇄망 custom_api 1급)로 Plan→Assemble→Validate→Repair(≤3) 루프 수행. **노드 배치는 AI 판단, 구조 정합성은 검증 프로세스가 강제.** 노드/연결 id는 서버가 항상 전역 고유로 재부여(LLM 예시 id 복사로 인한 PK 충돌 방지).
- **웹 UI** `/workflows/new/chat` (`ChatWorkflowGeneratorPage`) — 채팅 입력 + draft 미리보기 + 검증 리포트 + 확정 저장. 백엔드 테스트 344 통과, 프론트 빌드 0 에러, end-to-end 검증 완료.

### 2026-05-12 — InstanceDB 파일시스템 재설계
SQLite 테이블 `instance_dbs`, `instance_db_records` 를 폴더+JSON 으로 전환. JSON Schema·dedup_key 폐기. Phase 1-4 백엔드 테스트 120/120 통과. 상세는 `instance-db-fs-redesign.md`.

---

## 0. 이 문서의 독자

1. 본 프로젝트의 개편 작업을 이어받는 **LLM CLI (Claude Code 등)**
2. 검토 및 의결을 내린 **사용자(ITO 담당)**
3. Phase 작업을 위임받는 **서브에이전트 (executor/designer/architect)**

세션이 끊어지거나 새 CLI에게 인계될 때, **이 문서만 읽어도** 프로젝트 방향과 잔여 작업을 파악할 수 있도록 작성.

---

## 1. 개편의 핵심 원칙 (한 문장씩)

1. **AI 업무도우미는 범용 업무자동화 플랫폼이다.** 특정 도메인(GitHub/마일스톤/코드정적분석 등)에 종속되지 않는다.
2. **CLI가 관리자다.** 워크플로우·노드·지식·API 명세 등 모든 재료 생성/수정은 CLI(Claude Code 등)가 REST API를 호출해 수행한다.
3. **웹 UI는 실행/조회 전용 대시보드다.** 편집·생성 UI는 전부 제거한다.
4. **드래그앤드롭은 완전 폐기한다.** ReactFlow 캔버스는 자동 레이아웃(dagre) 기반 **읽기 전용 뷰어**로 재활용한다.
5. **position/viewport 데이터는 존재하지 않는다.** DB/타입/코드에서 전부 제거한다.
6. **자동 지식화는 금지한다.** 실행 결과는 창고(warehouse) 인스턴스로만 저장되며, 지식베이스 이관은 사용자 검토 후 CLI 명시 요청으로만 이루어진다.
7. **제로 스타트.** 기존 워크플로우·지식문서·API 명세·인스턴스를 전부 비우고 시작한다.
8. **대화형 점진 고도화.** 사용자는 MD 명세 파일을 미리 쓰지 않고, CLI와 대화하며 필요한 재료를 조립해 나간다.
9. **플로팅 챗 UI는 제거한다.** 향후 필요 시 복원 가능하도록 코드는 보존하되 UI에서는 완전히 숨긴다.
10. **CLAUDE.md는 CLI의 시스템 프롬프트 역할이다.** 퀄리티 이슈이므로 운영하면서 보완한다.

---

## 2. 아키텍처 다이어그램

```
사용자 로컬 (바이브코딩 환경)
┌──────────────────────────────────────────────┐
│ LLM CLI (Claude Code / 기타 AI CLI)           │
│  컨텍스트: AGENTS.md, CLAUDE.md               │
│  역할: 사용자 업무 파악 → 필요한 재료 식별     │
│       → REST API 호출 → 재료 등록·조립        │
│       → 인스턴스 검토 → 지식 프로모션          │
└──────────────────────────────────────────────┘
                        │ HTTP (REST)
                        ▼
┌──────────────────────────────────────────────┐
│ AI 업무도우미 Backend (FastAPI, 포트 8002)     │
│                                                │
│  [API 레이어]                                  │
│   - POST /workflows, /nodes, /knowledge,       │
│          /api-definitions                      │
│   - POST /workflows/{id}/run (background)      │
│   - GET  /nodes/catalog                        │
│   - GET  /warehouse/instances/{id}             │
│   - POST /knowledge/from-instance              │
│                                                │
│  [실행 엔진] workflow_engine.py (변경 없음)     │
│  [저장소] SQLAlchemy + ChromaDB                │
└──────────────────────────────────────────────┘
                        ▲
                        │ HTTP
┌───────────────────────┼──────────────────────┐
│ 웹 UI (Vite, 포트 5174) — 실행/조회 전용       │
│   - /          대시보드 (실행현황 + WF카드)    │
│   - /workflows 워크플로우 리스트               │
│   - /workflows/:id  뷰어 + 실행 버튼           │
│   - /workflows/:id/instances/:iid  실행 상세   │
│   - /knowledge  지식문서 뷰어 (읽기전용)       │
│   - /api-definitions  API명세 뷰어 (읽기전용)  │
│   - /nodes      노드 카탈로그 뷰어 (읽기전용)   │
│   ※ 플로팅 챗 제거                             │
└──────────────────────────────────────────────┘
```

---

## 3. 의결 완료 사항 (14건)

| # | 항목 | 결정 | 의결 근거 |
|---|------|------|-----------|
| 1 | 정체성 | 범용 업무자동화 플랫폼, 특정 도메인 종속 X | 사용자 명시 |
| 2 | 전환 전략 | 하이브리드 (생성=CLI, 조회=뷰어 모드 캔버스) | 공수 최적 |
| 3 | DB 마이그레이션 | 일괄 폐기 (제로 스타트) | 토이 단계, 도메인 흔적 제거 |
| 4 | 생성/편집 주체 | CLI (Claude Code든 타 LLM CLI든 agnostic) | 바이브코딩 환경 |
| 5 | 웹 UI 역할 | 실행 + 결과 조회 | UX 단순화 |
| 6 | CLAUDE.md 성격 | "LLM CLI가 체계적 업무자동화 활용" 서비스 역할 중심 | 사용자 명시 |
| 7 | 플로팅 챗 | UI에서 완전 제거 (코드 흔적은 보존) | 미래 복원 여지 |
| 8 | 웹 쓰기 범위 | 최소 쓰기 (실행 + 창고 인스턴스) | 권한 분리 명확 |
| 9 | 지식 프로모션 | CLI 명시 요청만 (사용자 검토 후) | 품질 보장 |
| 10 | 노드 카탈로그 전달 | 하이브리드: CLAUDE.md 요약표 + `GET /nodes/catalog` 상세 | 오프라인 + 최신성 |
| 11 | 페이지 구조 | 대시보드/WF리스트/WF뷰어/인스턴스/지식/API/노드 | 역할별 분리 |
| 12 | 대시보드 | 상단 실행현황 + 하단 WF 카드 (옵션 C) | 종합 조망 |
| 13 | 실행 UX | 폼 입력 → 백그라운드 실행 → 노드별 진행 표시 | 화면 이탈 내성 |
| 14 | 용어 | 업무 중심 용어 (운영 중 미세조정) | 도메인 친화 |
| + | 도메인 특화 노드 | 4종 완전 삭제 (milestone-collector, deliverable-generator, dev-deliverable-gen, review-deliverable-gen) | 범용성 확보 |
| + | MD 명세 파일 방식 | **폐기** (사용자가 미리 작성하지 않음, 대화형 고도화) | 사용자 재확인 |

---

## 4. 범용 노드 13종 (개편 후 유지)

| defType | 카테고리 | 목적 | 비고 |
|---------|---------|------|------|
| form-start | starter | 폼 입력 트리거 | 실행 시 입력 폼 렌더 |
| api-start | starter | 외부 API 호출 트리거 | 웹훅·스케줄 |
| ai-custom | ai | 커스텀 AI 프롬프트 실행 | CLI가 system_prompt 등록 |
| ai-api-router | ai | AI가 적절한 API 선택·호출 | api-definitions 참조 |
| sorter | logic | 조건별 분기 | 규칙 기반, instance-db lookup 지원 |
| unpacker | logic | 배열 언팩 (반복 처리) | 각 항목 → 다운스트림 |
| mapper | logic | 데이터 병합·매핑 | 키 기반 join |
| api-call | action | 외부 API 호출 | api-definitions 참조 |
| knowledge | action | 지식베이스 RAG 검색 | ChromaDB |
| instance-db-insert | action | 인스턴스DB 적재 | 자유 JSON 파일 저장 (2026-05-12 재설계) |
| instance-db-lookup | action | 인스턴스DB 조회 | filterTemplate 매칭 다건 (2026-05-12 재설계) |
| result | output | 창고 인스턴스 저장 | DB persist |
| markdown-viewer | output | 마크다운 렌더링 | UI 표시 |

**삭제 대상 4종 (도메인 특화):**
- `milestone-collector` (GitHub 마일스톤 전용)
- `deliverable-generator` (GitHub PR 산출물 전용)
- `dev-deliverable-gen` (개발산출물 전용)
- `review-deliverable-gen` (리뷰산출물 전용)

→ 향후 필요 시 `ai-custom` + `api-call` 조합으로 재현.

---

## 5. REST API 설계 (CLI 호출 포인트)

### 5.1 재료 관리 (CLI 전용)

| 메서드 | 경로 | 용도 |
|--------|------|------|
| GET | `/api/v1/nodes/catalog` | 노드 카탈로그 상세 스키마 (inputs/outputs/config) |
| POST | `/api/v1/nodes` | 커스텀 AI 노드 등록 (name, system_prompt, tags) |
| PUT | `/api/v1/nodes/{id}` | 커스텀 AI 노드 수정 |
| DELETE | `/api/v1/nodes/{id}` | 커스텀 AI 노드 삭제 |
| POST | `/api/v1/knowledge` | 지식문서 등록 (title, category, tags, content) |
| PUT | `/api/v1/knowledge/{id}` | 지식문서 수정 |
| DELETE | `/api/v1/knowledge/{id}` | 지식문서 삭제 |
| POST | `/api/v1/api-definitions` | 외부 API 명세 등록 |
| PUT | `/api/v1/api-definitions/{id}` | API 명세 수정 |
| DELETE | `/api/v1/api-definitions/{id}` | API 명세 삭제 |
| POST | `/api/v1/workflows` | 워크플로우 생성 (nodes + connections, position 없음) |
| PUT | `/api/v1/workflows/{id}` | 워크플로우 수정 |
| DELETE | `/api/v1/workflows/{id}` | 워크플로우 삭제 |

### 5.2 실행·조회 (웹·CLI 공통)

| 메서드 | 경로 | 용도 |
|--------|------|------|
| POST | `/api/v1/workflows/{id}/run` | 백그라운드 실행 시작, instance_id 즉시 반환 |
| GET | `/api/v1/workflows/{id}/instances` | 인스턴스 목록 |
| GET | `/api/v1/warehouse/instances/{iid}` | 인스턴스 상세 (창고 데이터) |
| GET | `/api/v1/warehouse/instances/{iid}/stream` | SSE: 노드별 진행상황 실시간 스트림 |
| GET | `/api/v1/workflows` | 워크플로우 리스트 |
| GET | `/api/v1/workflows/{id}` | 워크플로우 상세 (nodes + connections) |
| GET | `/api/v1/nodes` | 커스텀 AI 노드 목록 |
| GET | `/api/v1/knowledge` | 지식문서 목록·검색 |
| GET | `/api/v1/api-definitions` | API 명세 목록 |
| GET | `/api/v1/dashboard/summary` | 대시보드 집계 — `{counts: {todayRuns, inProgress, failed, completed}, workflows: [{...latestInstance}]}` (Phase 4c 신설) |

### 5.5 인스턴스DB CRUD (CLI 전용)

| 메서드 | 경로 | 용도 |
|--------|------|------|
| POST | `/api/v1/instance-dbs` | 인스턴스DB 메타 등록 (name, description, tags) — 2026-05-12 schema 필드 제거 |
| GET | `/api/v1/instance-dbs` | 인스턴스DB 목록 (검색 q 파라미터) |
| GET | `/api/v1/instance-dbs/{id}` | 인스턴스DB 상세 |
| PUT | `/api/v1/instance-dbs/{id}` | 인스턴스DB 수정 |
| DELETE | `/api/v1/instance-dbs/{id}` | 인스턴스DB 삭제 (폴더 통째) — 2026-05-12 파일시스템 전환 |
| GET | `/api/v1/instance-dbs/{id}/records` | records 리스트 (limit/offset/sourceWorkflowId/sourceExecutionId) — 2026-05-12 dedupKey 제거 |
| GET | `/api/v1/instance-dbs/{id}/records/{rid}` | 단일 record 조회 |

### 5.3 지식 프로모션 (CLI 전용)

| 메서드 | 경로 | 용도 |
|--------|------|------|
| POST | `/api/v1/knowledge/from-instance` | 인스턴스를 지식문서로 프로모션 `{ instance_id, title, category, tags }` |

### 5.4 설계 원칙
- **RESTful + JSON**, camelCase 응답
- **OpenAPI 스펙은 `/docs` (FastAPI 자동 생성)** 에서 제공
- **에러 메시지는 CLI가 파싱 가능하도록** `{ error: {code, message, details} }` 구조
- **인증은 현재 단계 없음** (내부 네트워크 가정), 추후 도입 여지

---

## 6. 데이터 모델 (개편 후)

### 6.0 신규 테이블 (Phase 6)

| 테이블 | 필드 | 설명 |
|--------|------|------|
| `instance_dbs` | id(pk), name(unique), schema(JSON), tags(JSON), created_by, created_at, updated_at | 인스턴스DB 메타 |
| `instance_db_records` | id(pk), instance_db_id(fk), data(JSON), dedup_key, source_warehouse_id, source_workflow_id, source_execution_id, created_at | 인스턴스DB 레코드. UNIQUE(instance_db_id, dedup_key) where dedup_key IS NOT NULL |

### 6.1 제거할 필드

| 파일 | 필드 |
|------|------|
| `backend/app/schemas/workflow.py:16-19` | `class Position` |
| `backend/app/schemas/workflow.py:30` | `WorkflowNodeCreate.position` |
| `backend/app/schemas/workflow.py:43` | `WorkflowNodeResponse.position` |
| `backend/app/schemas/workflow.py:93-97` | `class ViewportConfig` |
| `backend/app/schemas/workflow.py:105` | `WorkflowBase.viewport` |
| `backend/app/schemas/workflow.py:122` | `WorkflowUpdate.viewport` |
| `backend/app/schemas/workflow.py:136` | `WorkflowResponse.viewport` |
| `backend/app/schemas/workflow.py:269` | `FactoryMapUpdate.viewport` |
| `backend/app/models/workflow.py:55-60` | `Workflow.viewport` 컬럼 |
| `backend/app/models/workflow.py:131-136` | `WorkflowNode.position` 컬럼 |
| `frontend/src/types/index.ts:102-105` | `Position` interface |
| `frontend/src/types/index.ts:114` | `WorkflowNodeInstance.position` |
| `frontend/src/types/index.ts:382` | `WorkflowNode.position` |
| `frontend/src/nodes/types.ts:63` | `createNodeData` 시그니처의 position |
| `frontend/src/nodes/registrations.ts` | 15곳(→11곳) createNodeData position 인자 |

### 6.2 추가할 필드

```python
# backend/app/models/workflow.py (WorkflowNode)
order_index: int  # 형제 노드 안정 순번 (UI 자동 레이아웃에서 tie-break용)
```

```python
# backend/app/models/workflow.py (Workflow)
created_by: str = 'cli'  # 'cli' | 'web' (미래 확장용)
```

### 6.3 기존 데이터 처리
- DB 재생성 스크립트 (`backend/app/cli.py reset-db` 또는 `scripts/wipe.py` 신설)
- ChromaDB 컬렉션 drop & recreate
- 파일 기반 지식문서 `backend/knowledge/*.md` 제거 (유틸리티 템플릿은 유지 검토)

---

## 7. 웹 UI 페이지 구조 (개편 후)

### 7.1 라우트

| 경로 | 페이지 | 쓰기 허용 |
|------|--------|-----------|
| `/` | 대시보드 (실행현황 상단 + WF 카드 하단) | ❌ |
| `/workflows` | 워크플로우 리스트 | ❌ |
| `/workflows/:id` | 워크플로우 뷰어 (자동레이아웃 DAG + 실행 버튼) | ⭕ 실행만 |
| `/workflows/:id/instances/:iid` | 인스턴스 상세 + SSE 진행 스트림 | ❌ |
| `/instance-dbs` | 인스턴스DB 뷰어 (읽기전용) | ❌ |
| `/knowledge` | 지식문서 뷰어 | ❌ |
| `/api-definitions` | API 명세 뷰어 | ❌ |
| `/nodes` | 노드 카탈로그 뷰어 | ❌ |

### 7.2 제거 대상
- `PartsPalette.tsx` (드래그 팔레트)
- `FactoryCanvas.tsx`의 드래그/연결 생성 로직 (뷰어 모드로 대체)
- 모든 ConfigPanel의 저장 버튼 (읽기전용 렌더는 유지 검토)
- `ChatAssistant.tsx` 플로팅 위젯 마운트 (코드는 보존)
- `ChatContext.tsx` Provider 주입 (비활성화)

### 7.3 신설
- `frontend/src/utils/autoLayout.ts` — dagre 기반 자동 레이아웃
- `frontend/src/pages/InstanceDetailPage.tsx` — SSE 스트림 구독 + 노드별 상태 렌더
- 대시보드 재작성 (실행현황 요약 카드 + 워크플로우 그리드)

### 7.4 용어 전환 (UI만, 코드 내부는 기술용어 유지)
- "Workflow" → "업무자동화"
- "Execute" → "실행"
- "Instance" → "실행기록"
- "Warehouse" → "결과창고"
- 기타: 운영 중 미세조정

---

## 8. 백그라운드 실행 설계

### 8.1 기술 선택
- **FastAPI BackgroundTasks** (현재 단계). Celery/RQ 미도입.
- 필요 시 `asyncio.create_task`로 독립 태스크 관리.
- 향후 분산 실행이 필요해지면 Celery로 전환 가능한 구조 유지.

### 8.2 상태 모델
```python
# workflow_engine.py 내부
class NodeExecutionState(Enum):
    pending = 'pending'
    running = 'running'
    completed = 'completed'
    failed = 'failed'
    skipped = 'skipped'
```

### 8.3 영속화
- `workflow_executions` 테이블 (인스턴스) — 이미 존재, 필드 검토
- `node_execution_results` 테이블 — 노드별 상태·결과 저장
- 실행 재시작 시 DB 상태에서 복원 가능

### 8.4 진행상황 푸시
- **SSE** (`ExecutionLogEvent` 이미 스키마 존재) — 이벤트 타입: `node_start`, `node_complete`, `node_error`, `execution_complete`
- 웹 UI는 `EventSource`로 구독. 연결 끊겨도 폴링 fallback 확보.

### 8.5 중단 감지
- 노드별 timeout (기본값 5분, 노드 타입별 override)
- heartbeat: 1분마다 `last_heartbeat_at` 갱신
- 기동 시 stale instance 탐지 → `failed` 처리

---

## 9. Phase 6 — ✅ 인스턴스DB 1급 자원화 (2~3일) ✅ 완료 (2026-04-26)

**목표**: 워크플로우가 자동 누적하는 동질 데이터셋(인스턴스DB)을 1급 자원으로 격상. sorter 노드의 lookup 규칙 확장 및 CLI 프롬프트 강화.

**작업 목록:**
- [x] 데이터 모델 확정 (instance_dbs, instance_db_records 테이블)
  - UNIQUE(instance_db_id, dedup_key) where dedup_key IS NOT NULL
  - source_warehouse_id, source_workflow_id, source_execution_id 추적 필드
- [x] `backend/app/models/instance_db.py` (Phase A: 모델만)
- [x] `backend/app/api/routes/instance_dbs.py` — 7개 엔드포인트 구현
  - POST (메타 등록, schema 강제)
  - GET / GET/{id} / PUT / DELETE (CRUD)
  - GET /{id}/records, GET /{id}/records/{rid} (조회)
- [x] 노드 핸들러 (Phase B: instance-db-insert, instance-db-lookup)
  - `backend/app/nodes/action/instance_db_insert.py` — record 적재, dedup 검사, skipOnDuplicate
  - `backend/app/nodes/action/instance_db_lookup.py` — by_key/filter 모드
- [x] sorter 노드 확장: `_evaluate_instance_db_rule` (dataSource='instance-db' 지원)
- [x] 카탈로그 업데이트: instance-db-insert, instance-db-lookup 메타 등록
- [x] 프론트엔드: `InstanceDBViewerPage.tsx` (읽기전용)
- [x] CLAUDE.md 섹션 3 갱신 — 인스턴스DB 설명 추가
- [x] 본 설계서 섹션 4·5·6·7 갱신

**검증 기준:** 모두 충족
- pytest 91개 통과 (기존 63 + Phase 6 신규 28)
- E2E 시나리오: InstanceDB `idb-0fb61e0a` ("answered_boards") 및 워크플로우 `wf-b90acd45` ("QnA 답변 워크플로우")
  - 1차 실행: board_id=A, B 적재 (2 records)
  - 2차 실행: board_id=A 중복 차단 (inserted=false, skipped=true, reason=duplicate)
  - 3차 실행: board_id=C, D 적재 (총 4 records)
  - records 조회 확인: 최종 4건

**위임:** `executor`, `designer-low`, `writer`

---

## 10. Phase별 실행 계획 (선형 진행)

### Phase 1 — 🧹 대청소 (3~4일)

**목표**: 도메인 흔적·position 데이터·플로팅 챗 UI 전부 제거. 빈 상태로 초기화.

**작업 목록:**
- [ ] 도메인 특화 노드 4종 삭제
  - `backend/app/nodes/action/milestone_collector.py`, `deliverable_generator.py`, `dev_deliverable_gen.py`, `review_deliverable_gen.py` (파일 확인 후)
  - `frontend/src/components/workflow/` 내 해당 노드 컴포넌트
  - `frontend/src/nodes/registrations.ts`에서 4개 등록 제거
  - `backend/app/core/constants.py`의 `NodeDefType` enum에서 4개 제거
- [ ] position/viewport 필드 제거 (6.1의 체크리스트 전체)
- [ ] 하드코딩된 도메인 키워드 제거
  - `agent_service.py`의 "소스코드검증", "OG0704", "코드아이즈" 등
  - `INTENT_DETECTION_PROMPT`, `ASSISTANT_SYSTEM_PROMPT` 일반화
- [ ] DB 초기화 스크립트 작성
  - `scripts/wipe.py` — 모든 테이블 drop & recreate
  - ChromaDB 컬렉션 drop
  - `backend/knowledge/*.md` 제거 (검토 후)
- [ ] 플로팅 챗 UI 비활성화
  - `App.tsx`에서 `<ChatProvider>` 제거 또는 조건부
  - `ChatAssistant` 마운트 제거
  - 코드 자체는 보존

**검증 기준:**
- `grep -r "position\|viewport" backend/app/models backend/app/schemas` → 0
- `grep -r "milestone-collector\|dev-deliverable\|review-deliverable" backend frontend` → 0
- 프론트 빌드 통과
- 백엔드 기동 + `/api/v1/workflows` GET → `[]`

**위임:** `executor` (BE), `executor` (FE), `build-fixer` (마이그레이션)

---

### Phase 2 — 🔧 범용 인프라 정비 (4~5일)

**목표**: 노드 카탈로그 API, CLI용 REST API 정비, CLAUDE.md 완성.

**작업 목록:**
- [ ] `backend/app/nodes/catalog.py` 신설
  - 11종 범용 노드의 `NodeCatalogEntry` 정의
  - purpose, inputs[], outputs[], config[], useCases, connectsWellWith
- [ ] `GET /api/v1/nodes/catalog` 엔드포인트
- [ ] 기존 CRUD API 재정비 (position 제거 반영, 에러 포맷 통일)
- [ ] `POST /api/v1/workflows/{id}/run` — 백그라운드 실행 시작
- [ ] `POST /api/v1/knowledge/from-instance` — 지식 프로모션
- [ ] `GET /api/v1/warehouse/instances/{iid}/stream` — SSE
- [ ] 커스텀 AI 노드 등록 플로우 정비 (`POST /nodes`)
- [ ] `AI 업무도우미/CLAUDE.md` 완성 (설계 섹션 11 기반)
- [ ] OpenAPI docs 검증 (`/docs` 페이지)

**검증 기준:**
- OpenAPI 스펙에 모든 엔드포인트 노출
- CLI에서 `curl http://localhost:8002/api/v1/nodes/catalog` 성공
- 샘플 워크플로우 1개를 API만으로 생성·실행 가능

**위임:** `executor`, `architect` (스키마 리뷰), `writer` (CLAUDE.md)

---

### Phase 3 — 🖥 웹 UI 재구성 (5~7일)

**목표**: 편집 UI 전면 제거, 읽기전용 뷰어 + 대시보드 + 인스턴스 상세.

**작업 목록:**
- [ ] `FactoryCanvas.tsx` → `WorkflowViewerCanvas.tsx` 개편
  - `nodesDraggable={false}`, `nodesConnectable={false}`
  - 마운트 시 `autoLayout(nodes, edges)` 호출
- [ ] `utils/autoLayout.ts` 신설 (dagre)
- [ ] `PartsPalette.tsx` 삭제
- [ ] 대시보드 재작성 (`pages/DashboardPage.tsx`)
  - 상단: 실행현황 요약 카드 (오늘 실행/실패/성공)
  - 하단: 워크플로우 카드 그리드 (실행 버튼)
- [ ] 워크플로우 뷰어 페이지 (`pages/WorkflowViewerPage.tsx`)
  - 자동레이아웃 DAG + 실행 버튼
  - 실행 시 `FormStartConfigPanel` 재활용하여 입력 폼 렌더
  - 하단 인스턴스 목록
- [ ] 인스턴스 상세 페이지 신설 (`pages/InstanceDetailPage.tsx`)
  - SSE 구독 → 노드별 진행상황 라이브 업데이트
  - 완료 시 창고 결과 마크다운/JSON 표시
- [ ] 지식/API/노드 페이지 읽기전용 축소
- [ ] 업무용어로 UI 문구 전환 (하드코딩)
- [ ] 라우터 정리 (`App.tsx`)

**검증 기준:**
- 모든 편집 버튼 제거됨
- 자동 레이아웃으로 기존 샘플 WF가 합리적으로 렌더
- 실행 → 진행상황 라이브 표시 → 완료 결과 조회 E2E 동작

**위임:** `designer-high` (레이아웃), `executor` (상태·라우팅)

---

### Phase 4 — ⚙ 백그라운드 실행 + 진행상황 (3~4일) ✅ 완료 (2026-04-22)

**목표**: 실행이 화면 이탈에 견디고, 진행상황이 라이브로 푸시되도록 구현.

**작업 목록:**
- [x] `workflow_engine.py` 실행 로직 비동기화 검증
- [x] FastAPI BackgroundTasks 통합
- [x] 노드 상태 DB 영속화 (`node_execution_results`)
- [x] SSE 스트림 구현 (`ExecutionEventBus` in-memory pub/sub + SSE push)
- [x] 중단 감지 — 노드별 timeout (ai-custom=600s, api-call=60s, knowledge=30s, 기본 300s)
- [x] 기동 시 stale instance 복원·실패 처리 (RUNNING/PENDING → FAILED)
- [x] 프론트 `EventSource` 연동 + 30초 heartbeat / 15초 idle ping
- [x] **Phase 4c**: `GET /api/v1/dashboard/summary` 신설 (N+1 제거)
  - `backend/app/api/routes/dashboard.py` 신설
  - `DashboardPage.tsx` N+1 Promise.all → `dashboardApi.getSummary()` 1회 호출로 교체
  - `frontend/src/services/api.ts`에 `dashboardApi` 추가
  - `backend/tests/test_dashboard_summary.py` 4개 테스트 신설
- [x] **Phase 4c**: 레거시 주석 정리 (WorkflowViewerCanvas, WorkflowViewerPage)
- [x] **Phase 4c**: `redesign-plan.md` 갱신

**실제 구현 요약 (Phase 4a~4c):**

| 구성요소 | 내용 |
|---------|------|
| `ExecutionEventBus` | in-memory pub/sub, workflow_engine.py에 emit 5곳 |
| `node_results` | WorkflowExecution.node_results JSON 컬럼에 영속화 |
| SSE 스트림 | `/warehouse/instances/{id}/stream` — 초기 스냅샷 + 이벤트 push |
| Timeout | 노드 타입별 설정 (ai-custom 600s, api-call 60s, knowledge 30s) |
| Heartbeat | 30초 ping, 15초 idle ping |
| Stale 복원 | 서버 기동 시 RUNNING/PENDING → FAILED 자동 처리 |
| Dashboard API | `GET /api/v1/dashboard/summary` — counts + workflows + latestInstance |
| 테스트 | 63개 통과 (4a/4b 59개 + 4c 4개 신규) |
| E2E | Playwright 5/5 통과 |
| 프론트 빌드 | 0 에러 |

**검증 기준:** 모두 충족
- 실행 중 브라우저 닫고 재접속 → 상태 복원 (SSE 재구독 + DB 스냅샷)
- 노드 timeout 발생 시 `failed` 처리 및 원인 기록
- Dashboard N+1 → 단일 API 호출로 교체 완료

**위임:** `executor-high` (백엔드 비동기), `executor` (프론트 SSE + Phase 4c)

---

### Phase 5 — ✅ E2E 검증 + 문서 (2~3일) ✅ 완료 (2026-04-22)

**목표**: 전체 흐름 회귀 테스트, 문서 최종 갱신.

**작업 목록:**
- [x] CLI → API → 실행 → 조회 풀 시나리오 테스트
- [x] Playwright E2E 5개 통과 (실행/뷰어/인스턴스 조회 포함)
- [x] pytest 기반 API 테스트 — 백엔드 63개 통과
- [x] `AI 업무도우미/CLAUDE.md` 최종 갱신 (Phase 4 변경 반영 — SSE, timeout, dashboard summary)
- [x] 루트 `ORCHESTRATION.md`, `AGENTS.md` 갱신 (인접 프로젝트에 개편 사실 고지)
- [x] `AI 업무도우미/docs/redesign-plan.md` (본 문서) 완료 상태로 갱신
- [ ] architect 최종 검증 (Phase 5b 완료 후 수행 예정)

**검증 기준:**
- 백엔드 테스트 63개 green ✅
- Playwright E2E 5/5 통과 ✅
- 문서 간 상호 참조 일관성 확인 ✅
- architect 검증 통과 (예정)

**위임:** `qa-tester-high`, `writer`, `architect`

---

## 11. CLAUDE.md 최종 스켈레톤 (Phase 2에서 구현)

```markdown
# AI 업무도우미 (범용 업무자동화 플랫폼)

## 1. 이 시스템은 무엇인가
LLM CLI가 사용자 업무를 파악하여 체계적 자동화 환경을 조립·운영하는 백엔드 서비스. 당신(CLI)이 이 시스템의 "관리자"다.

## 2. 당신(CLI)의 역할
- 사용자 업무 이해 → 필요한 재료(지식/API/커스텀노드) 식별
- REST API로 재료 등록
- 범용 노드들을 조립해 워크플로우 생성
- 인스턴스 결과 검토 후 지식베이스 프로모션

## 3. 시스템 구성요소
- 워크플로우: 노드들을 연결한 자동화 파이프라인
- 노드: 11종 범용 + 커스텀 AI 노드
- 지식문서: RAG 검색 대상, 검토 후 CLI만 등록
- API 명세: 외부 API 호출 템플릿
- 인스턴스: 워크플로우 1회 실행 결과
- 창고: 인스턴스 원시 데이터 저장소

## 4. 기본 제공 노드 (요약 표)
[11종 표 — 본 설계서 섹션 4 참조]
상세: GET http://localhost:8002/api/v1/nodes/catalog

## 5. REST API 개요
[본 설계서 섹션 5 요약]
상세 OpenAPI: GET http://localhost:8002/docs

## 6. 작업 원칙
1. 제로 스타트 — 빈 시스템에서 대화로 점진 고도화
2. 재료 먼저, 워크플로우 나중
3. 자동 지식화 금지 — 인스턴스→지식 이관은 CLI 명시 요청만
4. 범용성 유지 — 도메인 특화 노드 신설 금지, `ai-custom` + `api-call` 조합 우선

## 7. 포트·기동
- Backend: 8002 (FastAPI)
- Frontend: 5174 (Vite)
- 포트 점유 시 kill 후 기동 (루트 ORCHESTRATION.md 정책 준수)
```

---

## 12. 위험 관리

| 위험 | 심각도 | 완화 |
|------|--------|------|
| 기존 코드 삭제로 빌드 깨짐 | 중 | Phase 1 완료 전 feature branch 유지, 각 삭제마다 빌드 확인 |
| position 제거 시 ReactFlow 렌더 깨짐 | 중 | autoLayout 먼저 구현 → 뷰어 모드 전환 |
| SSE 연결 불안정 (방화벽·프록시) | 낮 | polling fallback 기본 내장 |
| 백그라운드 실행 중 서버 재시작 | 중 | stale instance 감지 + 실패 처리 |
| CLI가 catalog를 잘못 해석 | 중 | OpenAPI + 카탈로그 JSON 스키마 검증 |
| 토큰 비용 급증 (CLI 반복 호출) | 낮 | CLI는 사용자 로컬, 이 프로젝트 부담 X |

---

## 13. 재확인 사항 (Phase 착수 전 체크)

- [x] 사용자 의결 14건 완료
- [x] 도메인 특화 노드 4종 삭제 합의
- [x] MD 명세 파일 방식 폐기 합의
- [x] 제로 스타트 (DB 전부 비움) 합의
- [x] 본 설계서 작성
- [ ] Phase 1 착수 승인 대기

---

## 14. 다음 실행 명령 (참고)

Phase 1 착수 시 예시:
```bash
# 백엔드 기동 확인
cd backend && uvicorn app.main:app --reload --port 8002

# Phase 1 작업을 executor 에이전트에게 위임
# Task(subagent_type="oh-my-claudecode:executor",
#      model="sonnet",
#      prompt="Phase 1 대청소 착수: 본 설계서 섹션 9.Phase 1 체크리스트를 순서대로 실행...")
```

---

## 15. 참고 경로 (절대경로)

- 본 설계서: `C:\Users\wjdgm\OneDrive\바탕 화면\클로드코드_오케스트레이션\AI 업무도우미\docs\redesign-plan.md`
- 루트 지시서: `C:\Users\wjdgm\OneDrive\바탕 화면\클로드코드_오케스트레이션\ORCHESTRATION.md`
- 프로젝트 지시서: `C:\Users\wjdgm\OneDrive\바탕 화면\클로드코드_오케스트레이션\AI 업무도우미\CLAUDE.md`
- 포트 정책: 루트 ORCHESTRATION.md "포트 할당" 섹션

### 주요 소스 파일 (Phase 1~5 완료 기준, 실존 확인)

**Backend**
- `backend/app/nodes/catalog.py` — 범용 11종 노드 카탈로그 SSoT
- `backend/app/services/execution_bus.py` — SSE 이벤트 버스 (in-memory pub/sub)
- `backend/app/services/workflow_engine.py` — 실행 엔진 (수정 금지)
- `backend/app/api/routes/dashboard.py` — `/dashboard/summary` 엔드포인트
- `backend/app/api/routes/warehouse.py` — 인스턴스 상세 + SSE 스트림
- `backend/app/api/routes/workflows.py` — 워크플로우 CRUD + 실행
- `backend/app/api/routes/nodes.py` — 커스텀 AI 노드 CRUD + 카탈로그
- `backend/app/api/routes/knowledge.py` — 지식문서 CRUD + 프로모션
- `backend/scripts/wipe.py` — DB/ChromaDB 초기화
- `backend/scripts/e2e_zero_start.py` — 제로 스타트 E2E 검증 스크립트

**Frontend**
- `frontend/src/utils/autoLayout.ts` — dagre 기반 자동 레이아웃
- `frontend/src/components/workflow/WorkflowViewerCanvas.tsx` — 읽기전용 ReactFlow 캔버스
- `frontend/src/pages/DashboardPage.tsx` — 실행현황 대시보드
- `frontend/src/pages/WorkflowViewerPage.tsx` — 워크플로우 뷰어 + 실행 버튼
- `frontend/src/pages/WorkflowListPage.tsx` — 워크플로우 목록
- `frontend/src/pages/InstanceDetailPage.tsx` — 실행 상세 + SSE 구독
- `frontend/src/pages/KnowledgeViewerPage.tsx` — 지식문서 읽기전용 뷰어
- `frontend/src/pages/ApiDefinitionViewerPage.tsx` — API 명세 읽기전용 뷰어
- `frontend/src/pages/NodeCatalogPage.tsx` — 노드 카탈로그 읽기전용 뷰어

**삭제된 파일 (Phase 1/3에서 제거)**
- `FactoryCanvas.tsx` → `WorkflowViewerCanvas.tsx`로 대체
- `PartsPalette.tsx` — 드래그 팔레트 삭제
- 도메인 특화 노드 4종 (`milestone_collector.py` 등) — 삭제

---

**문서 버전**: v2.0 (CLI 주도 범용 플랫폼)
**이전 버전**: 초기 Planner/Architect/Critic 3인 분석 (내장 LLM 빌더 전제 → 폐기)
**다음 업데이트**: Phase 1 완료 시
