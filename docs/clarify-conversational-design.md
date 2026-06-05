# 대화형 워크플로우 생성/편집 — 하이브리드 되묻기(폼 질문) 설계서

> 작성일: 2026-06-06 · 상태: **설계 확정(미구현)** · 대상: AI 업무도우미 웹 채팅 생성/편집(`POST /api/v1/workflows/generate`)
> 후속: 구현은 별도 지시 시 착수(아래 Phasing 순). 이 문서는 executor 인계용 SSoT.

## 0. 배경 / 문제
현재 채팅 생성 파이프라인은 **매 턴 무조건 draft를 생성**한다(Plan→Assemble→Validate→Repair, `workflow_generator.py:1117-1374`). 요청이 모호하거나 의사결정이 필요한 지점에서도 AI가 임의로 골라버린다.
- 실제 사례: "소스코드검증 신규 문의글 조회"인데 생성기가 `mock-support-view-list`가 아니라 `github-milestone-issues`(GitHub)를 선택 → **재료 선택 모호성(D1)**.

목표: **하이브리드 되묻기** — 명확하면 바로 생성, 모호/결정 지점이면 **폼(선택지) 질문**으로 사용자에게 물어보고 답을 받은 뒤 진행. AI가 재확인·조언도 가능. 토큰 절약 중시.

## 확정된 설계 결정 (이번 의사결정)
1. **질문 적극성 = 보수적**: 꼭 필요할 때만 질문(애매할 땐 기존처럼 생성으로 편향). 임계값(FLOOR/MARGIN)은 설정으로 조정.
2. **롤아웃 = 기능 플래그**: `WORKFLOW_CLARIFY_ENABLED` env로 on/off. 기본 off로 배포 후 점진 활성. off면 100% 기존 동작.
3. **응답 타이핑**: `/generate`는 기존처럼 dict 반환(무 타입). 두 형태(`draft`/`question`)를 라우트 설명에 문서화. (Pydantic 판별 union은 도입 안 함 — 직렬화 리스크 회피)
4. **advisor↔질문 연계**: phase 1 제외(후순위). advisor는 기존대로 post-draft 비차단 제안 유지.
5. **미충족 재료(D4)**: 폼에서 **재료 신규 생성 불가**(재료 생성=CLI 전용 정책, CLAUDE.md §5.1). "건너뛰기/취소 + CLI 등록 안내"만 제공.
6. **답변 턴 description**: 서버가 `clarifyState.originalDescription` 재사용. 클라이언트는 description 비워 보내도 됨.

## 1. 응답 모델 (핵심 변경) — discriminated union (`kind`)
하위호환 규칙: **draft 결과는 기존 키 전부 유지 + `kind:"draft"` 추가.** 기존 테스트/프론트(`result["draft"]`)·CLI 무영향(`/generate`는 웹 전용, CLI 미사용 — grep 확인).

```jsonc
// (A) DRAFT — 기존 동작 + 태그
{ "kind":"draft", "draft":{...}, "validation":{...}, "assistantMessage":"...",
  "attempts":0, "stages":[...], "traceId":"gen-...", "clarifyState":{...}? }

// (B) QUESTION — 신규. 이 턴엔 draft 미생성/미변경
{ "kind":"question", "questions":[ /* §3 */ ], "assistantMessage":"확인이 필요합니다...",
  "draft":null, "baseDraftEcho":{...}|null, "clarifyState":{...}, "traceId":"gen-..." }
```
- 질문 턴은 `draft:null` 명시(TS union narrowing). `attempts/validation/stages`는 생략 → 클라이언트는 `kind` 먼저 분기.
- 대화 상태는 서버 무상태, **`clarifyState`를 클라이언트가 echo**(기존 `history`/`baseDraft` 패턴과 동일).

### `clarifyState`
```jsonc
{ "originalDescription":"소스코드검증 신규 문의글을 조회...",
  "materialsHash":"sha1:...",            // 재료 변동 staleness 감지
  "askCount":1,                          // 가드 캡
  "resolvedBindings":{ "trigger.apiDefinitionId":"api-7f3c", "intent.skipProcessed":true },
  "askedQuestionIds":["q-trigger-api"] } // 중복질문 방지
```

## 2. 언제 묻나 = 하이브리드 정책
순서: **결정론 트리거(LLM 없음) → 없으면 바로 생성 → 애매하면 LLM Clarify 1회**. 일반 경로 토큰비용은 오늘과 동일.

### 2.1 결정론 트리거 (신규 `app/services/clarify_detector.py`)
`_collect_materials()`(`workflow_generator.py:378-474`) 결과 + Stage A 스켈레톤(또는 편집모드 base_draft)로 탐지.

| 코드 | 트리거 | 탐지 |
|---|---|---|
| D1-ambiguous-api | API 필요한데 후보 apiDefinition ≥2개 근접 | 노드 purpose vs (name+url+params) 토큰 겹침 점수; top1-top2 < MARGIN & top1 > FLOOR → 질문. **GitHub vs 문의글 사례** |
| D2-ambiguous-idb | instanceDb 후보 ≥2 | name/description 점수 |
| D3-ambiguous-ainode | aiNode 후보 ≥2 또는 약한 1개 | usage/name 점수 |
| D4-missing-material | 필요한데 등록 재료 0 | 현재 "조용히 노드 생략" → 질문(건너뛰기/취소)로 승격 |
| D5-low-confidence | 단일 후보지만 점수 < FLOOR | 확인/다른것(기타) |
| D6-destructive-edit | (편집) 노드/트리거/룰 삭제 유발 | 의도 키워드 pre-confirm 또는 refine 후 post-guard, 1회만 |

점수: 한/영 토큰화(공백·구두점, 소문자), name+url+description 양쪽 점수. 상수(MARGIN/FLOOR/cap) 중앙화. **기본 보수적**(애매하면 질문 안 함).

### 2.2 LLM Clarify (신규 Stage A2, 선택 호출)
결정론 신호가 불확실하거나(짧은 description·빈약 스켈레톤) 후보 문구를 LLM이 잘 다듬어야 할 때만 호출.
출력 계약: `{ "action":"ask"|"proceed", "questions":[...], "rationale":"..." }`. 규칙: 결과가 실질적으로 바뀌는 경우만 ask, 재료 id 환각 금지(`workflow_generator.py:485-487` 동일 가드), 최대 N질문. `proceed`면 바로 Assemble.
토큰: ask면 Stage B + Repair(최대 3회, 각 max_tokens=3000)를 **건너뛰어 절약**.

### 2.3 가드
- `MAX_QUESTIONS_PER_TURN`(예 2), `MAX_ASK_TURNS`/thread(예 2, `clarifyState.askCount`). 캡 초과 → **최고점 후보로 자동 진행 + assistantMessage 안내**.
- 이미 답한 항목(`resolvedBindings`/`askedQuestionIds`) 재질문 금지. D6 confirm 1회.

## 3. 질문/답변 스키마
### 3.1 Question (서버→클라)
```jsonc
{ "id":"q-trigger-api", "type":"single|multi|text", "bindingKey":"trigger.apiDefinitionId",
  "title":"'문의글 조회'에 사용할 API를 선택하세요", "detail":"여러 후보가 일치합니다...",
  "options":[ {"value":"api-7f3c","label":"mock-support-view-list","description":"GET /support/inquiries — 문의글 목록"},
              {"value":"api-2a9d","label":"github-milestone-issues","description":"GET /repos/.../issues"} ],
  "multiSelect":false, "allowOther":true, "otherLabel":"다른 API 직접 지정" }
```
D4는 options가 제어 선택(`{value:"skip"}`/`{value:"abort"}`), `bindingKey:"node.<purpose>.action"`.

### 3.2 Answer (클라→서버) — 다음 `/generate` 요청의 `answers:[]`
```jsonc
{ "questionId":"q-trigger-api", "bindingKey":"trigger.apiDefinitionId",
  "selected":["api-7f3c"], "other":null }
```

### 3.3 바인딩 네임스페이스 → 결정론 주입
답변을 `resolvedBindings`로 변환 후 **assembler가 재결정 못 하게 강제 주입**:

| bindingKey | 결과 | 주입 |
|---|---|---|
| `trigger.apiDefinitionId` | 구체 apiDefinitionId | Stage B 프롬프트에 강제 지시 + **assemble 후 post-overwrite** |
| `node.<key>.apiDefinitionId/instanceDbId/aiNodeId` | 구체 id(또는 `inline`) | 동일(노드 purpose/name 키) |
| `intent.skipProcessed` | bool | sorter-dedup 결정 |
| `node.<key>.action=skip|abort` | 제어 | skip=노드 제거, abort=무 draft 메시지 |

**핵심**: 프롬프트 지시와 별개로 `apply_bindings(draft, resolvedBindings)`가 assemble/repair 후 바운드 필드를 **덮어쓴다** → LLM이 사용자 선택을 못 뒤집음(`_ensure_ids`/`_normalize_sorter_wiring`와 동일 "서버가 진실" 철학).

## 4. 백엔드 변경 (파일 단위)
### 4.1 신규 `app/services/clarify_detector.py`
- `detect_clarifications(description, skeleton, materials, base_draft, clarify_state) -> {action, questions, autoBindings}` (D1~D6 + 가드, autoBindings=무질문 단일해결 자동적용)
- 점수 helper/상수, `apply_bindings(draft, resolved_bindings)`, `compute_materials_hash(materials)`

### 4.2 `app/services/workflow_generator.py`
- `generate_workflow(...)`에 `answers=None, clarify_state=None` 추가(기본 None → 기존 시그니처/pytest 보존, `test_workflow_generator.py:143`).
- 흐름(create): 재료수집 → materialsHash/staleness → answers를 resolvedBindings로 폴드(값이 실제 재료 id인지 검증, 환각이면 재질문) → Stage A → `detect_clarifications` → `ask`면 **Stage B 전에 question 턴 반환**(트레이스 question으로 마감); 아니면 autoBindings+answered 적용 후 Stage B(강제지시) → `apply_bindings`(`:1272-1275` 및 각 Repair `:1303-1306` 뒤) → Validate/Repair → `kind:"draft"` 반환 + clarifyState echo.
- **기능 플래그**: `WORKFLOW_CLARIFY_ENABLED` off면 detect/clarify 전체 skip(=오늘 동작).
- 편집모드: Stage R + D6(base_draft 기반), clarify는 의도 pre-confirm 가능.

### 4.3 `app/api/routes/workflows.py` + `app/schemas/workflow.py`
- `WorkflowGenerateRequest`(`:279-293`)에 `answers:Optional[List[dict]]=None`, `clarifyState:Optional[dict]=None` 추가(Optional → 하위호환).
- 엔드포인트(`:346-369`)는 `answers/clarify_state` 전달. 응답은 dict 유지(무 response_model), 200 동일.

### 4.4 generation_trace
- 트레이스에 `turnKind:"question"|"draft"`, `questions:[...]`(질문턴) 추가. 질문턴 `finalDraft=null`. `assistantMessage`=질문문구.
- `trace_to_conversation_item`(`generation_trace.py:194-219`) 출력에 `turnKind` 노출 → 편집모드 복원 UI가 질문턴을 "(질문) ..."로 렌더. `read_traces` 요약의 `finalDraft`/`nodeCount` 접근 가드.

### 4.5 검증 게이트/advisor
- 검증 게이트(§6.12) 불변(질문턴은 draft 미생성 → 게이트 미호출, 저장 경로는 그대로). advisor 연계는 phase 1 제외.

## 5. 프론트 변경 (파일 단위)
### 5.1 `src/services/api.ts`
- `WorkflowQuestionOption/WorkflowQuestion/QuestionResult/DraftResult/GenerateResponse(union)/WorkflowAnswer` 타입 추가. `workflowApi.generate`에 `answers?/clarifyState?` 추가, 반환 `GenerateResponse`.

### 5.2 `src/pages/ChatWorkflowGeneratorPage.tsx`
- `LocalMessage`(`:29-35`)에 `role:'question'`, `questions?`, `answered?` 추가.
- 신규 `QuestionForm({questions,onSubmit})`: 라디오(single)/체크박스(multi)/텍스트 + `allowOther` "기타" + "확인". SuggestionPanel(`:183-243`) 스타일 재사용.
- `handleSend`(`:438-510`): `result.kind` 분기. `question`이면 question 메시지+assistant 버블 push, `pendingClarifyState` 저장, currentDraft 미변경(편집모드 baseDraftEcho 유지). `draft`면 기존 경로 + clarifyState 저장.
- `handleAnswerSubmit(answers)`: `generate({description:'', mode, baseDraft, history, answers, clarifyState})` 재호출(서버가 originalDescription 사용), 질문 메시지 `answered:true`.
- 렌더 루프(`:700-708`)에 `role==='question'` → `<QuestionForm/>`(answered면 읽기전용 요약). 편집모드 복원 시 과거 질문턴은 평문("(이전 질문) ...")으로.

## 6. 의사결정 지점 분류
| # | 상황 | 결정론/LLM | 폼 |
|---|---|---|---|
|1| 애매 API 선택(≥2) — **GitHub vs 문의글** | 결정론 D1 (문구는 LLM 가능) | single+기타 |
|2| 애매 instanceDB | 결정론 D2 | single |
|3| 애매 AI노드 vs inline | 결정론 D3 | single(‘inline 프롬프트’ 포함) |
|4| 미충족 재료 → 건너뛰기/취소 | 결정론 D4 | single(생성 불가=CLI 전용, 안내) |
|5| 저신뢰 단일매치 | 결정론 D5 | single(확인/기타) |
|6| 애매 트리거 타입(form vs api-start) | LLM | single |
|7| 다중 배선 후보 | LLM | single |
|8| 파괴적 편집 confirm | 결정론 D6 | single(진행/취소) |
|9| 저장 전 최종 확인 | **범위 외**(저장은 명시 버튼, 과잉질문) | — |
|10| skip-processed 의도 불명 | LLM/키워드 | yes/no |

## 7. 토큰 효율
- 일반 경로 불변(detector는 이미 수집된 재료+Stage A만). Stage A는 오늘도 호출됨 → 추가 LLM 비용 0.
- 질문 턴은 **Stage B + Repair(≤3, 각 3000토큰) 전에 반환** → 잘못된 draft 생성/수정 왕복 회피로 **절약**.
- LLM Clarify는 불확실할 때만 1회. 답변 후엔 `apply_bindings`로 결정론 확정 → 추가 Repair 불필요.

## 8. Phasing / 리스크
**빌드 순서**
1. P1 — 스키마/배선(무동작): draft에 `kind` 추가, request에 `answers/clarifyState` Optional, TS union, 플래그(기본 off). 기존 테스트/빌드 그린 확인.
2. P2 — 결정론 detector(D1~3) + question 턴 반환 + `apply_bindings`(+테스트).
3. P3 — 프론트 QuestionForm + 답변 왕복.
4. P4 — D4~6 + 트레이스 question턴 + 편집모드 복원 렌더.
5. P5 — LLM Clarify(#6,#7,#10).

**리스크/엣지**: 과잉질문(보수적 기본+캡+자동진행), 답변 staleness(materialsHash 불일치 시 바인딩 무효화/재검출, 사라진 재료 id 거부), 편집모드+질문(프리뷰 보존·D6 1회), 다중질문(캡, 한 번에 제출, 부분답=최적후보+안내), 한국어 토큰화(영문 API명+한글 설명 양쪽 점수), 하위호환(웹 전용·draft 추가형·플래그 off 시 무영향), 미답 질문턴 방치(새 자유입력=일반 refine로 처리, pending 폐기), LLM이 강제 바인딩 무시(assemble/repair 후 overwrite로 방어).

## 부록 — 주요 파일 앵커
- `backend/app/services/workflow_generator.py` (generate_workflow `:1117`, _collect_materials `:378`, Stage A `:658`/B `:844`/R `:959`/D `:1056`, _ensure_ids `:295`, _normalize_sorter_wiring `:74`)
- `backend/app/api/routes/workflows.py` (`generate_workflow_endpoint :346`), `backend/app/schemas/workflow.py` (`WorkflowGenerateRequest :279`)
- `backend/app/services/generation_trace.py` (`trace_to_conversation_item :194`)
- `frontend/src/pages/ChatWorkflowGeneratorPage.tsx`, `frontend/src/services/api.ts` (`GenerateResult :576`, `workflowApi.generate :803`)
- 신규: `backend/app/services/clarify_detector.py`
- 보존 계약: `backend/tests/test_workflow_generator.py:143-219` (draft 결과 키)
