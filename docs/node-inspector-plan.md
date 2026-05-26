# NodeInspectorDrawer 설계안 (v2.1)

> 워크플로우 뷰어에서 노드 클릭 시 우측 슬라이드 드로어로 (1) 노드 카탈로그 스펙 + 현재 워크플로우 config (2) 그 노드가 보유한 데이터 — 두 가지를 탭으로 동시에 제공한다. **본 문서는 설계안이며 구현 문서가 아니다. 구현은 별도 Phase 분할에서 수행.**
>
> **v2.1 — critic 2차 의결 APPROVE-WITH-CONDITIONS 7건(C-1 ~ C-6, D-2) 반영, 작성일 2026-04-26.** 주요 변경: P-1 frontend `WorkflowExecution.nodeResults` 타입 정정(배열→Record), P-2 `knowledgeApi.list` 객체 인자 시그니처, P-3 catalog config 키 표기 라벨 정정 + §부록A 매트릭스, P-4 Phase 1c 산출물 명확화, P-5 InstanceDBRecord 인덱스, P-6 §14 R-1 fetch 공유 명시, P-7 EdgeInspectorPanel close 책임자 명시. v2 까지의 변경 이력은 §16 참조.

---

## 0. 한눈에 요약

- 신규 컴포넌트 1개: `frontend/src/components/workflow/NodeInspectorDrawer.tsx`
- 보조 신규 컴포넌트 3개: `JsonTreeView`, `NodeInspectorEmpty`, `NodeInspectorTabBar`
- 수정 대상 컴포넌트 4개: `WorkflowViewerCanvas.tsx`, `WorkflowViewerPage.tsx`, `InstanceDetailPage.tsx`, `NodeOutputPill.tsx`
- 수정 대상 클라이언트: `frontend/src/services/api.ts` (`factoryApi.getWarehouse` 시그니처 확장 — B-1, **v2.1 추가 P-2: `knowledgeApi.list` 객체 인자 시그니처**)
- **수정 대상 타입(v2.1 신규 P-1)**: `frontend/src/types/index.ts` 의 `WorkflowExecution.nodeResults` 를 `Record<string, NodeExecutionResult>` 로 정정
- 수정 대상 카드 (선택): "클릭하여 …" 라벨 5곳 — Phase 4 candidate (D-1, L-2)
- 백엔드 수정 1건 + 모델 1건: `backend/app/api/routes/instance_dbs.py` (records 라우터에 `sourceWorkflowId` / `sourceExecutionId` AND 필터 추가 — R-9), **v2.1 추가 P-5: `backend/app/models/instance_db.py` 의 `source_workflow_id` / `source_execution_id` 에 `index=True`**
- 탭 구조: `정보` / `데이터` / (인스턴스 한정) `실행 결과`
- 13종 노드 모두 동작 매트릭스 명세 (§5). v2 변경: form-start ✅ / mapper ✅ / knowledge ✅ 데이터 탭 활성화
- 데이터 페이징·본문 추출 정책 명세 (§7) — v2: backend `_entry_body()` 와 우선순위 일치
- Phase 분할 1a / 1b / 1c / 2 / 3 / 4 (§13). **v2.1 P-4: Phase 1c 산출물 = 정보 탭 §6 카운트 배지(mapper/knowledge) + form-start 정보 탭. 데이터 탭 7종 활성화는 모두 Phase 2.**
- a11y: 비-modal 드로어 (§9) — `aria-modal="false"`, focus trap **제거**, ESC 글로벌 캡처 유지
- **카탈로그 표기 매트릭스 (v2.1 P-3 신설 §부록 A)** — 13종 42개 config 키 중 snake_case 는 `ai_node_id` 1개뿐. 나머지는 camel/lowercase. §4 §5 헤더 라벨도 그에 맞춰 정정.
- **선택 mutual exclusion (v2.1 P-7)** — EdgeInspectorPanel ↔ NodeInspectorDrawer 의 동시 오픈 방지 책임자는 **Page state**.
- **카운트 fetch 공유 (v2.1 P-6)** — mapper/result/markdown-viewer 의 정보 탭 카운트는 데이터 탭 응답의 `total` 을 재사용.

---

## 1. 설계 목표 및 비목표

### 1.1 목표
1. 노드 클릭 시 단일 우측 드로어로 "이 노드가 무엇을 하는지" + "지금 갖고 있는 데이터"를 동시에 본다.
2. 13종 노드(form-start, api-start, ai-custom, ai-api-router, sorter, unpacker, mapper, api-call, knowledge, instance-db-insert, instance-db-lookup, result, markdown-viewer)에서 정보 탭은 **항상** 동작한다.
3. 데이터 탭은 보유 데이터가 있는/미리보기가 의미 있는 노드에서만 활성화된다(§5.6 v2 매트릭스). 그 외는 탭 자체 disable.
4. WorkflowViewerPage(설계 단계)와 InstanceDetailPage(실행 단계) 두 곳에서 모두 동작한다.
5. 카탈로그(13종 풀 스펙)는 페이지 단위 1회 fetch + 메모리 캐시.

### 1.2 비목표
- 노드 편집/생성/삭제 — 본 드로어는 **읽기 전용**. (편집은 CLI만 — 루트 정책)
- 워크플로우 그래프 자체의 시각 변경(엣지/레이아웃 등). 기존 EdgeInspectorPanel과 공존.
- `workflow_engine.py` 변경 — 정책상 금지.
- 신규 백엔드 엔드포인트 추가 — 단, **기존 엔드포인트의 query 파라미터 추가는 허용** (R-9). 본 설계의 백엔드 변경은 query 파라미터 2개 추가 1건뿐.

### 1.3 정책 준수
- 루트 `ORCHESTRATION.md` + `AI 업무도우미/CLAUDE.md` §9 운영 규칙 6 (테스트 회귀), 7 (프론트엔드 빌드)을 충족하도록 §12 검증 체크리스트 정의.
- §9-1 직접 소스 수정 금지 → 본 설계는 executor/designer에 위임 가능한 단위로 분할 (§13).

---

## 2. 아키텍처 개요

```
WorkflowViewerCanvas (props.onNodeClick 이미 존재 — wiring 은 페이지에서 신규)
  ▼ onNodeClick(reactFlowNode) / onPaneClick()
[Page 컨테이너]
  └ state: selectedNodeContext, drawerOpen, activeTab, catalog
  ▼ <NodeInspectorDrawer />
       ├── <NodeInspectorTabBar />  (정보 / 데이터 / 실행 결과?)
       ├── <NodeInspectorInfoTab />     ← catalog + workflow.nodes[i].config
       ├── <NodeInspectorDataTab />     ← 노드별 분기 (§5 매트릭스)
       └── <NodeInspectorRunTab />      ← (InstanceDetailPage 한정) instance.nodeResults[id]
```

- 드로어는 **컨트롤드 컴포넌트**: 부모(Page)가 `selectedNode | null` 와 `onClose` 만 제공.
- 드로어 자체에서는 카탈로그(필요 시)와 데이터 탭 fetch를 책임. `useEffect`로 `selectedNode.id` 변경 시 데이터 reset.
- 카탈로그 프리페치: 페이지 mount 시 1회 (`useNodeCatalog()` 훅, `useState + useEffect`로 충분, react-query 미도입). 캐시는 React state로 충분 — 페이지 unmount 시 폐기.

---

## 3. 컴포넌트 명세

### 3.1 `NodeInspectorDrawer.tsx` (신규)

**Props (확정)**

```ts
export interface InspectedNodeContext {
  /** ReactFlow Node.id == WorkflowNodeInstance.id (DB workflow_nodes.id) */
  nodeInstanceId: string;
  /** 백엔드 카탈로그 키 (form-start, ai-custom, ...) */
  defType: string;
  /** 사용자가 부여한 인스턴스 이름 */
  instanceName: string;
  /** ai-custom 일 때만 의미 */
  aiNodeId?: string;
  /** 워크플로우 정의에서 가져온 config snapshot — camelCase (인스턴스 표기) */
  config?: Record<string, unknown>;
  /** 워크플로우 정의에서 가져온 inputMapping snapshot */
  inputMapping?: Record<string, string>;
}

export interface NodeInspectorDrawerProps {
  /** null 이면 닫힘 */
  node: InspectedNodeContext | null;
  /** InstanceDetailPage 에서만 전달. WorkflowViewerPage 에서는 undefined */
  nodeResult?: {
    status?: string;
    inputData?: unknown;
    outputData?: unknown;
    error?: string;
    startTime?: string;
    endTime?: string;
    definitionType?: string;
  };
  /** 카탈로그 스펙. 페이지에서 한 번 fetch 후 prop 으로 전달. */
  catalog: NodeCatalogEntry[] | null;
  /**
   * 드로어가 위치한 페이지 컨텍스트. instance-db 데이터 탭 필터링에 사용 (R-9).
   * - `viewer`: WorkflowViewerPage → sourceWorkflowId 로 필터
   * - `instance`: InstanceDetailPage → sourceExecutionId 로 필터
   */
  pageContext: 'viewer' | 'instance';
  /** viewer 컨텍스트에서 전달 */
  workflowId?: string;
  /** instance 컨텍스트에서 전달 */
  instanceId?: string;
  /** 닫기 콜백 */
  onClose: () => void;
}
```

> **결정 D-2**: 카탈로그를 page-scope 에서 fetch 하여 prop 으로 주입한다. 드로어 내부 fetch는 하지 않는다 — 매번 노드 클릭 시 재요청 방지 + 테스트 용이성.

**내부 상태**

```ts
const [activeTab, setActiveTab] = useState<'info' | 'data' | 'run'>('info');
```

**Race condition 가드 (M-9)**

`useEffect` 안의 모든 fetch (catalog 추가정보 / 데이터 탭 records / mapper 의 warehouseNodeId 미리보기 등)는 **AbortController** 우선 사용, 미지원 환경 fallback 으로 `cancelled` boolean 을 cleanup 에서 set:

```ts
useEffect(() => {
  const controller = new AbortController();
  let cancelled = false;
  (async () => {
    try {
      const data = await someApi.fetch({ signal: controller.signal });
      if (cancelled) return;
      setData(data);
    } catch (e) {
      if (cancelled || (e as DOMException)?.name === 'AbortError') return;
      setError(e);
    }
  })();
  return () => {
    cancelled = true;
    controller.abort();
  };
}, [node?.nodeInstanceId, activeTab, page]);
```

노드가 빠르게 교체될 때 stale fetch 가 새 노드 state 를 덮어쓰는 사고를 방지.

**닫기 동작 (전부 같은 onClose 호출)**

| 트리거 | 동작 |
|--------|------|
| 헤더 X 버튼 | onClose |
| ESC 키 | useEffect + window keydown listener (드로어 mount 시 부착, M-4 비-modal) |
| 드로어 바깥(캔버스) 클릭 | ReactFlow `onPaneClick` → onClose. 다른 노드 클릭은 자동 전환 처리(아래) |
| 같은 노드 재클릭 | 토글 닫기 (M-3) |
| 다른 노드 클릭 | 자동 교체 (드로어는 열린 상태 유지, 내부 state는 새 node로 reset) |

> **결정 M-3 (D-3 갱신)**: 같은 노드 재클릭 = **닫기(토글)**, 다른 노드 = **자동 교체**, 빈 캔버스 = **닫기**. EdgeInspectorPanel 의 다른 엣지=교체 동작과 일관성 위해 같은 엣지 재클릭=닫기 도 추후 별도 micro-PR 로 정합. 본 설계는 노드만.

**탭 활성화 규칙**

- `정보` 탭은 항상 활성.
- `데이터` 탭은 §5 v2 매트릭스의 "데이터 탭 ✅" 노드에서만 활성. 그 외는 disabled + 툴팁 "이 노드는 미리보기할 데이터가 없습니다".
- `실행 결과` 탭은 `nodeResult` prop 이 정의되어 있을 때만 표시. 즉 InstanceDetailPage 한정.
- 드로어 첫 오픈 시 디폴트 탭은 `정보`. 단, InstanceDetailPage 에서 nodeResult 의 status === 'failed' 이면 `실행 결과` 탭을 디폴트로 (사용자 의도 추정).

**시각/레이아웃 (M-8, F-10)**

- 드로어 컨테이너 클래스: `absolute top-0 right-0 h-full min-w-[400px] max-w-[480px] bg-gray-900 border-l border-gray-700 shadow-2xl flex flex-col z-40`
- 내부 콘텐츠 영역: `overflow-y-auto overflow-x-auto`
- 페이지 캔버스 컨테이너는 `relative` 유지. WorkflowViewerPage(`55vh`) / InstanceDetailPage(`360px`) 모두 컨테이너 안에서 `h-full` 로 수용. 작은 컨테이너는 드로어 내부 스크롤로 해소.
- z-index: EdgeInspectorPanel(z-40)과 동일. 동시에 둘 다 열리는 상황은 발생 불가하지만, 안전을 위해 노드 드로어가 열릴 때 EdgeInspector 는 닫는다 (Page 가 둘을 동시에 관리).
- 모바일(<1024px) 대응은 §14 R-4 — 본 설계는 1024px+ 가정.

### 3.2 `NodeInspectorTabBar.tsx` (신규, 드로어 내부 전용)

- 3개 버튼(또는 2개) 가로 배치, 활성 탭 underline. 키보드 ←/→ 로 탭 이동.
- focus-visible ring 명시 (a11y).

### 3.3 `JsonTreeView.tsx` (신규, `components/common/`)

- EdgeInspectorPanel 안의 `TreeNode` / `TreeView` 패턴을 별도 파일로 추출.
- props: `{ data: unknown; defaultDepth?: number }`
- EdgeInspectorPanel 도 본 컴포넌트를 import 하도록 리팩토링 (중복 제거). **이 리팩토링은 Phase 1a 에서 수행하며, 회귀 위험을 줄이기 위해 시각적·동작 동치성을 보장한다(EdgeInspectorPanel 회귀 테스트 포함).**

### 3.4 `NodeInspectorEmpty.tsx` (신규, 드로어 내부 전용)

- 데이터 탭 빈/로딩/오류 상태 4종 (`empty`, `loading`, `error`, `unsupported`) 1개 컴포넌트로 처리.
- **M-5**: error 상태에 fetch 별 재시도 가능. props:

```ts
interface NodeInspectorEmptyProps {
  state: 'loading' | 'empty' | 'error' | 'unsupported';
  message?: string;
  onRetryCatalog?: () => void;   // 카탈로그 fetch 실패 재시도
  onRetryExtra?: () => void;     // 정보 탭 §6 추가정보 fetch 재시도
  onRetryData?: () => void;      // 데이터 탭 records fetch 재시도
}
```

각 fetch 가 독립적이므로 재시도도 분리. 어느 콜백이 전달되었느냐에 따라 다른 라벨의 버튼을 노출.

### 3.5 `WorkflowViewerCanvas.tsx` (수정) — wiring 명시 (B-3)

- onNodeClick prop **정의 자체는 이미 존재**하지만, 페이지에서 wiring 이 안 되어 있다. **본 설계가 신규 wiring 책임**.
- 또한 `onPaneClick?: () => void` 신규 prop 추가 → ReactFlow `onPaneClick={...}` 연결.
- 두 prop 다 페이지에서 신규 wiring 필수 (§3.6, §3.7).

### 3.6 `WorkflowViewerPage.tsx` (수정) — onNodeClick / onPaneClick 신규 wiring (B-3)

- 추가 state:
  ```ts
  const [selectedNode, setSelectedNode] = useState<InspectedNodeContext | null>(null);
  const [catalog, setCatalog] = useState<NodeCatalogEntry[] | null>(null);
  ```
- `useEffect`로 mount 시 `nodeApi.getCatalog()` 호출 → setCatalog. AbortController 적용.
- `WorkflowViewerCanvas` 에 `onNodeClick={handleNodeClick}` **(현재 미전달, 본 설계가 신규 wiring)** 전달.
  ```ts
  const handleNodeClick = (rfNode) => {
    const inst = workflow.nodes.find(n => n.id === rfNode.id);
    if (!inst) return;
    if (selectedNode?.nodeInstanceId === inst.id) { setSelectedNode(null); return; }
    setSelectedNode({
      nodeInstanceId: inst.id,
      defType: LEGACY_DEF_TYPE_MAP[inst.definitionType ?? ''] ?? inst.definitionType ?? '',
      instanceName: inst.name,
      aiNodeId: inst.aiNodeId,
      config: inst.config,        // camelCase (인스턴스 표기)
      inputMapping: inst.inputMapping,
    });
  };
  ```
- `onPaneClick={() => setSelectedNode(null)}` 전달 (신규 wiring).
- 캔버스 영역(`<div className="flex-shrink-0 relative" style={{ height: '55vh' }}>`)에 `<NodeInspectorDrawer node={selectedNode} catalog={catalog} pageContext="viewer" workflowId={workflow.id} onClose={...} />` 를 sibling으로 추가.
- **mutual exclusion 책임자 명시 (P-7)**: Page state 가 `selectedEdge` 와 `selectedNode` 둘 다 보유한다. 노드 클릭 시 핸들러 안에서 `setSelectedEdge(null)` 호출 → EdgeInspectorPanel 자동 닫음. 엣지 클릭 시 `setSelectedNode(null)` 호출 → NodeInspectorDrawer 자동 닫음. 즉 동시에 둘이 열리지 않도록 닫는 쪽은 항상 **Page** 가 책임지며, 자식 컴포넌트(드로어/EdgeInspectorPanel)는 자기 자신의 onClose 만 호출한다.

### 3.7 `InstanceDetailPage.tsx` (수정) — onNodeClick / onPaneClick 신규 wiring (B-3, M-1)

- 추가 state는 동일 (`selectedNode`, `catalog`).
- **M-1**: nodeResult 는 `instance.nodeResults[selectedNode.nodeInstanceId]` 를 직접 사용. 백엔드 응답에 `inputData/outputData/startTime/endTime/status/error/definitionType` 모두 포함되어 있어 NodeProgress 타입 확장은 불필요.
  ```ts
  const nodeResult = selectedNode ? instance.nodeResults?.[selectedNode.nodeInstanceId] : undefined;
  ```
  > **타입 전제 (P-1, C-1 정정)**: 위 indexer 접근(`?.[key]`)이 컴파일되려면 `WorkflowExecution.nodeResults` 가 `Record<string, NodeExecutionResult>` 이어야 한다. v2 의 `frontend/src/types/index.ts:225-251` 는 `NodeExecutionResult[]` (배열) 로 잘못 타입핑되어 있음. backend `app/models/workflow.py:192` 은 `Mapped[Dict[str, Any]]` 이고 응답 변환 `app/api/routes/warehouse.py:98` 도 dict 그대로 반환한다. v2.1 은 §11 수정 대상에 `frontend/src/types/index.ts` 를 추가하여 타입을 `Record<string, NodeExecutionResult>` 로 정정한다. 이 변경은 InstanceDetailPage(`InstanceDetailPage.tsx:309-311` 의 `Object.entries(ex.nodeResults)`) 같은 기존 사용처와 자연스럽게 정합된다 — 회귀 점검은 §13 Phase 1c 에 명시.
- Canvas 영역(`<section>` 안의 `<div style={{ height: 360 }}>`)에 드로어 sibling 으로 추가. `pageContext="instance"`, `instanceId={instance.id}` 전달.
- WorkflowViewerCanvas 에 `onNodeClick` / `onPaneClick` **신규 wiring** (B-3).
- **mutual exclusion 책임자 (P-7)**: §3.6 과 동일. Page state 가 `selectedEdge` / `selectedNode` 두 selection 을 직접 mutually exclusive 로 관리하며, 노드 클릭 핸들러 안에서 `setSelectedEdge(null)`, 엣지 클릭 핸들러 안에서 `setSelectedNode(null)` 을 호출한다.

### 3.8 `NodeOutputPill.tsx` (수정) — stopPropagation + 의도된 mental model (H-5)

- onClick 핸들러에 `e.stopPropagation()` 추가하여 카드 클릭(드로어 토글)과 pill 토글의 충돌을 차단.
  - 기존: `onClick={() => setExpanded(v => !v)}`
  - 변경: `onClick={(e) => { e.stopPropagation(); setExpanded(v => !v); }}`
- **의도된 동작 (사용자 mental model 변경 — H-5 명시)**: pill 영역을 클릭하면 **드로어가 열리지 않는다**. pill 영역은 "이 자리의 출력 미리보기 토글" 전용으로 분리됨. 카드 본체(pill 외 영역)를 클릭하면 드로어가 열린다.
- pill onClick 자체는 유지 (toggle 기능 보존).

> **주의 D-4**: `nodrag` 클래스는 드래그 차단이지 클릭 버블링 차단이 아니다. ReactFlow `onNodeClick` 은 카드 어디를 눌러도 호출된다. stopPropagation 이 필수.

---

## 4. 정보 탭 구성 (모든 노드 공통)

세로 스크롤 영역 안에 다음 섹션을 순서대로 배치한다.

### 섹션 1 — Header
- 좌: `nodeRegistry.get(defType).icon` (이모지) + `instanceName`
- 우: `× 닫기`
- 헤더 아래 라인:
  - `defType` 배지 (예: `ai-custom`)
  - `category` 배지 (`ai`, `logic` 등) — 색상 매핑은 `nodeRegistry.getMinimapColor(defType)` 재사용
  - `nodeInstanceId` (font-mono 작게)

### 섹션 2 — Purpose
- catalog.purpose 그대로 출력 (1~2 문장).
- 카탈로그 fetch 실패/누락 시 "카탈로그를 불러올 수 없습니다 (코드: …)" 표시 + `onRetryCatalog` (M-5).

### 섹션 3 — 현재 워크플로우 Config (인스턴스 표기, H-3)

- 헤더에 "현재 워크플로우 Config (인스턴스 표기)" 명시. 인스턴스 표기는 프론트엔드에서 일관되게 camelCase 로 직렬화되어 들어온다(예: `aiNodeId`, `apiDefinitionId`).
- `workflow.nodes[i].config` 의 키-값을 표로 표시 — **인스턴스 표기 그대로(camelCase, 예: `aiNodeId`)**.
- 값이 객체/배열이면 JsonTreeView 으로 fallback (depth 1 까지 펼친 채).
- 키 옆에 `catalog.config[].required` 가 true 인데 값이 비어있으면 노란색 ⚠ 경고 배지.
- config 가 `undefined` 또는 빈 객체면 "config 없음" 표시.
- catalog 의 config 정의에 명시되지 않은 키가 들어있으면 "(undocumented)" 보조 라벨.

### 섹션 4 — Inputs / Outputs (카탈로그 표기 — 노드별 상이, H-3, P-3)

- 헤더에 "노드 카탈로그 Inputs/Outputs (스펙, 카탈로그가 정의한 표기 그대로)" 명시.
- 두 개의 mini-table.
- 각 행: name(catalog 가 정의한 표기 그대로) / type / required / description. 카탈로그 inputs/outputs 는 placeholder 가 다수(`<임의>`, `<arrayField로_지정한_경로>` 등) 이고 일부 실제 키(`status`, `data`, `count`, `items`, `record`, `records`, `found`, `recordId`, `inserted`, `skipped`, `reason`, `knowledge`, `search_categories`, `matchedItems`, `matchedCount`, `__sorterHandle`, `api_route`)는 snake/camel 이 혼재한다.
- 카탈로그가 producesArray=true 인 노드(unpacker, knowledge)는 출력 위에 "이 노드는 배열을 언팩합니다" 안내.

### 섹션 5 — Catalog Config 스펙 (카탈로그가 정의한 표기 그대로 — 필드별 상이, H-3, P-3)

- 헤더에 "노드 카탈로그 Config 스펙 (카탈로그가 정의한 표기 그대로 — 필드별 상이)" 명시. §3 과 별개 표.
- catalog.config 의 키 그대로 표시. **표기는 노드/필드별로 snake / camel 이 혼재** 한다 — v2 까지의 "snake_case 통일" 라벨은 부정확. 정확한 매트릭스는 §부록 A.
  - 예: ai-custom 의 `ai_node_id` 는 snake, 같은 노드의 `systemPrompt`/`maxTokens`/`provider` 는 camel.
  - 예: mapper 의 `warehouseNodeId`/`matchKey`/`outputField` 는 모두 camel.
- §3 (인스턴스 표기 — 일괄 camelCase) 과 §5 (카탈로그 표기 — 필드별 상이) 는 **별개 표** 임을 두 헤더에 명시. 사용자가 "왜 같은 의미인데 표기가 다르냐" 고 묻지 않도록 두 헤더 모두 "표기 차이는 일부러 보존된 것" 임을 작은 보조 라벨로 안내한다.

### 섹션 5b — InputMapping (있는 경우)
- `workflow.nodes[i].inputMapping` 이 비어있지 않으면 표시.
- 표 형식: `현재 입력 필드 ← {{prev.출력필드}}`.

### 섹션 6 — 노드별 추가 정보 (§5 매트릭스 참조)
- 노드 종류에 따라 extra fetch + 렌더 컴포넌트 분기. fetch 실패 시 `onRetryExtra` (M-5).

### 섹션 7 — useCases / connectsWellWith
- `useCases`: bullet list. 비어있으면 섹션 숨김.
- `connectsWellWith`: 칩(badge) 가로 wrap. 비어있으면 섹션 숨김.

### 섹션 8 — 진단 정보 (Debug, 접힘 기본)
- requiresUpstream, producesArray 같은 메타.
- aiNodeId (있을 때).
- 접근성: aria-expanded.

---

## 5. 13종 노드 동작 매트릭스 (가장 중요) — v2

표기:
- **추가정보 API**: 정보 탭 §6 에서 호출하는 API. 없음(―)이면 섹션 자체 비표시.
- **데이터 탭**: ✅ 있음 / ❌ 없음(disabled).
- **데이터 API**: 데이터 탭에서 호출하는 API.
- **렌더**: 데이터 탭의 렌더링 정책.

### 5.1 starter 카테고리

| defType | 추가정보 API | 추가정보 렌더 | 데이터 탭 | 데이터 API | 렌더 |
|---------|-------------|--------------|----------|-----------|------|
| `form-start` | ― | (config.formFields 표는 §3 Config 가 이미 표시) | ✅ | ― (config 만 사용) | **Form Preview (F-4)**: config.fields 를 read-only 폼처럼 렌더. input/select/textarea 비활성화 상태로 placeholder/label 표시, defaultValues 적용. |
| `api-start` | `apiDefinitionApi.get(config.apiDefinitionId)` (있을 때만) | API 명세 미니 카드: method 배지 + urlTemplate(monospace) + parameters 표(name/type/required) + responseSchema 트리뷰. 또한 `mode` (`manual`/`schedule`) 와 `defaultParams` 표시. | ❌ | ― | ― |

> **갭 D-5**: api-start 의 `apiDefinitionId` 가 비어있으면 추가정보 섹션은 "API 명세 미연결" empty state. 클릭 시 CLI 안내 문구.
> **F-4 (form-start 데이터 탭)**: 실제 폼처럼 보이지만 비활성화. 사용자가 어떤 필드를 채우게 될지 미리 본다. submit 동작 없음.

### 5.2 ai 카테고리

| defType | 추가정보 API | 추가정보 렌더 | 데이터 탭 | 데이터 API | 렌더 |
|---------|-------------|--------------|----------|-----------|------|
| `ai-custom` | `nodeApi.get(aiNodeId)` (필요) | AI 노드 메타 카드: name, description, icon/color, **systemPrompt(접힘 기본, StyledMarkdown)**, **userPromptTemplate(접힘, code block)**, llmConfig (model/temperature/maxTokens 표), inputSchema/outputSchema 트리뷰. configOverrides 가 있으면 "오버라이드 적용" 배지 + 오버라이드 값 표시. | ❌ | ― | ― |
| `ai-api-router` | `apiDefinitionApi.list()` 호출 후 `config.apiIds` 로 필터. 빈 배열이면 전체 활성 API. | API 후보 목록(최대 20개): 각 항목은 method/urlTemplate. 요청 가능한 API 가 많으면 "외 N개" + 더보기. | ❌ | ― | ― |

> **결정 D-6**: ai-custom 의 systemPrompt/userPromptTemplate 은 보안/사이즈 이유로 디폴트 접힘. 클릭하여 펼침.
> **결정 D-7**: ai-api-router 는 list() 를 호출하는데 fetch 비용이 작지 않다. config.apiIds 가 명시되어 있으면 단건씩 `apiDefinitionApi.get(id)` 를 병렬로 호출 (Promise.all) — 일반적으로 5개 이하. 데이터 탭은 정보 탭에 흡수 → ❌.

### 5.3 logic 카테고리

| defType | 추가정보 API | 추가정보 렌더 | 데이터 탭 | 데이터 API | 렌더 |
|---------|-------------|--------------|----------|-----------|------|
| `sorter` | `instanceDbApi.get(rule.dataSource.instanceDbId)` (rule 별 필요 시) | rules 표를 시각적으로 강조: 각 룰의 field/operator/value/handle. dataSource 가 instance-db 면 해당 인스턴스DB 미니 카드. default handle 별도 표시. | ❌ | ― | ― |
| `unpacker` | ― | "언팩 대상 필드: `arrayField`" 강조 표시. config 의 arrayField 가 비면 ⚠ 경고. | ❌ | ― | ― |
| `mapper` | (정보 탭 단독 진입 시) `factoryApi.getWarehouse(config.warehouseNodeId, { limit: 1 })` → total 만 사용. **데이터 탭이 이미 열려 있다면 fetch 재사용 (P-6)**: 데이터 탭의 `{ limit: 20, skip: 0 }` 응답에 포함된 `total` 을 정보 탭 §6 카운트 배지에도 그대로 표시한다. 즉 같은 nodeId 로 limit=1 + limit=20 두 번 호출되는 일은 데이터 탭 첫 진입 이후로는 발생하지 않는다. | "매칭 키: `matchKey`" 강조 표시. matchKey 가 비면 ⚠ 경고. **mapper 가 참조하는 창고 (config.warehouseNodeId 가 가리키는 임의의 창고 노드 인스턴스 id, H-1)** 의 적재 카운트 배지 표시. config.warehouseNodeId 가 비어있으면 "참조 창고 미설정" empty. | ✅ | `factoryApi.getWarehouse(config.warehouseNodeId, { limit: 20, skip })` | result 와 동일한 records 표. **상단 안내 배너**: "이 미리보기는 mapper 가 매칭에 사용하는 창고(`warehouseNodeId`)의 records 입니다." |
| `knowledge` | ― | catalog config 표 외에 별도 API 호출 없음. searchField/categories/tags/maxResults 강조. | ✅ | `knowledgeApi.list({ category, limit: 20, offset })` (categories 첫 항목 우선; tags 는 클라이언트 필터) — **P-2**: `knowledgeApi.list` 시그니처를 `(params?: { category?: string; limit?: number; offset?: number })` 객체 인자로 확장 (`api.ts:108-111`). backend(`knowledge.py:82-87`) 가 category/skip/limit 모두 지원하므로 그대로 통과. | **Knowledge documents 목록**: 이 노드의 categories/tags 필터에 매칭되는 지식문서. 컬럼: title / category / tags / updatedAt. 본문 미리보기는 첫 200자만. limit/offset 페이징. |

> **변경 D-8 (H-1 정정)**: mapper 의 "참조 창고" 는 **catalog mapper.config.warehouseNodeId (catalog.py:539-547) 가 가리키는 임의의 창고 노드 인스턴스 id**. 종전 표현 "업스트림 result 노드" 는 부정확. mapper 데이터 탭 활성화 (H-1) — `factoryApi.getWarehouse(warehouseNodeId, ...)` 사용.
> **H-2 (knowledge 데이터 탭 활성화)**: ChromaDB 직접 조회는 불가하지만 `knowledgeApi.list({category})` 로 카테고리 매칭 문서 목록은 표시 가능. 노드의 categories[0] 을 query 로 보내고, tags 매칭은 클라이언트 측 필터. 본문 200자 preview.

### 5.4 action 카테고리

| defType | 추가정보 API | 추가정보 렌더 | 데이터 탭 | 데이터 API | 렌더 |
|---------|-------------|--------------|----------|-----------|------|
| `api-call` | `apiDefinitionApi.get(config.apiDefinitionId)` (필요) | api-start 와 동일한 API 명세 카드 (method/urlTemplate/parameters/responseSchema/headers/bodyTemplate). 필수 미설정 시 ⚠. | ❌ | ― | ― |
| `instance-db-insert` | `instanceDbApi.get(config.instanceDbId)` | InstanceDB 메타 카드: name/description/schema(트리뷰)/tags. config 의 sourceMode + dedupKeyTemplate 강조. | ✅ | `instanceDbApi.listRecords(config.instanceDbId, { limit:20, offset, sourceWorkflowId?, sourceExecutionId? })` (R-9) | records 표. **R-9 컨텍스트 필터링**: viewer 컨텍스트 → `sourceWorkflowId=<workflowId>` (이 워크플로우가 적재한 records 만), instance 컨텍스트 → `sourceExecutionId=<instanceId>` (이번 실행에서 적재한 records 만). 카운트는 "전체 / 필터 결과" 둘 다 표시. 노란 배너는 제거 (필터링 정확). |
| `instance-db-lookup` | `instanceDbApi.get(config.instanceDbId)` | 동일 | ✅ | 동일 | 동일 + "lookup 노드는 적재하지 않습니다" 안내. R-9 필터 동일 적용 (lookup 노드 자체는 적재 안 하므로 sourceWorkflowId/sourceExecutionId 일치하는 records 가 0건일 수 있음 — 그 경우 안내 문구). |

> **결정 D-9 갱신 (R-9)**: 종전 "전체 records 만 보여주는 노란 배너" 는 폐기. backend 가 `sourceWorkflowId` / `sourceExecutionId` AND 필터 query 파라미터를 추가하여 컨텍스트별 정확한 records 만 표시. 카운트는 "전체 N / 필터 후 M" 으로 두 값 모두 보여 사용자 가시성 확보.

### 5.5 output 카테고리 (D-11, B-2, H-4)

| defType | 추가정보 API | 추가정보 렌더 | 데이터 탭 | 데이터 API | 렌더 |
|---------|-------------|--------------|----------|-----------|------|
| `result` | (정보 탭 단독 진입 시) `factoryApi.getWarehouse(nodeInstanceId, { limit: 1 })` → total 만 사용. **데이터 탭이 이미 열려 있다면 fetch 재사용 (P-6)**: 데이터 탭의 `{ limit: 20, skip: 0 }` 응답 `total` 을 그대로 표시. | "창고 적재 N개" 카운트 배지. | ✅ | `factoryApi.getWarehouse(nodeInstanceId, { limit:20, skip })` (B-1 시그니처) | 표 형식: createdAt / dedupKey / data summary. 행 클릭 시 펼침 → §7.2 의 본문 추출 정책으로 본문 표시. body 가 string 이면 `<pre>` 코드 블록, body 가 dict/list 면 ```json ... ``` code block + JsonTreeView 토글. |
| `markdown-viewer` | (정보 탭 단독 진입 시) `factoryApi.getWarehouse(nodeInstanceId, { limit: 1 })` → total. **데이터 탭이 이미 열려 있다면 fetch 재사용 (P-6)**. | 동일 + "렌더 필드: config.field" | ✅ | 동일 | 행을 펼치면 **StyledMarkdown** 으로 마크다운 렌더. body 가 dict/list 면 ```json ... ``` code block 으로 감싼 후 StyledMarkdown 에 전달 (markdown 으로 렌더되게). 페이징은 동일. |

> **결정 D-11 갱신 (H-4)**: result 와 markdown-viewer 는 **동일 backend 테이블 (warehouse_entries) + 동일 본문 추출 함수 (§7.2)** 를 공유한다. **차이는 렌더만**: result 는 `<pre>` 코드 블록, markdown-viewer 는 StyledMarkdown. 본문 추출 우선순위는 §7.2 한 곳에 단일 정의.

### 5.6 매트릭스 검증 (13/13) — v2

| # | defType | 정보 탭 | 데이터 탭 | v1→v2 변경 |
|---|---------|---------|-----------|-----------|
| 1 | form-start | ✅ | ✅ | **❌→✅ (F-4 form preview)** |
| 2 | api-start | ✅ | ❌ | — |
| 3 | ai-custom | ✅ | ❌ | — |
| 4 | ai-api-router | ✅ | ❌ | — (정보 탭 흡수 유지) |
| 5 | sorter | ✅ | ❌ | — |
| 6 | unpacker | ✅ | ❌ | — |
| 7 | mapper | ✅ | ✅ | **❌→✅ (H-1 warehouseNodeId 미리보기)** |
| 8 | api-call | ✅ | ❌ | — |
| 9 | knowledge | ✅ | ✅ | **❌→✅ (H-2 knowledgeApi.list)** |
| 10 | instance-db-insert | ✅ | ✅ | 필터링 변경 (R-9) |
| 11 | instance-db-lookup | ✅ | ✅ | 필터링 변경 (R-9) |
| 12 | result | ✅ | ✅ | — |
| 13 | markdown-viewer | ✅ | ✅ | — |

총 13종 모두 정의됨, 누락 없음. 데이터 탭 활성 **7종** (v1 의 4종에서 mapper / knowledge / form-start 추가).

---

## 6. 실행 결과 탭 (InstanceDetailPage 한정)

- prop 으로 받은 `nodeResult` 만 렌더 (별도 fetch 없음). M-1: `instance.nodeResults[selectedNode.nodeInstanceId]` 직접 사용.
- 4 영역:
  1. 상태 배지(status) + 시간 (startTime → endTime 경과)
  2. 입력 데이터(`inputData`) — JsonTreeView
  3. 출력 데이터(`outputData`) — OutputRenderer + JsonTreeView 토글 (EdgeInspectorPanel 과 동일 패턴)
  4. 오류(`error`) — 빨간 카드, 있을 때만
- nodeResult 가 정의돼 있어도 status === 'idle' 또는 미실행이면 "아직 실행되지 않았습니다" empty state.

> **갭 D-12 갱신 (M-1)**: NodeProgress 타입 확장 불필요. backend 응답에 `inputData/outputData/startTime/endTime/status/error/definitionType` 모두 포함되어 있어 그대로 사용. 드로어는 prop 으로 받기만 함, 자체 fetch 안 함.

> **SSE 갱신 정책 (M-2)**: 드로어가 열려있는 동안 SSE 새 이벤트 도착 시 자동 갱신 안 함. 사용자가 데이터 탭 헤더의 **↻ 새로고침 버튼** 을 눌러야 갱신. 자동 갱신은 사용자가 보고 있는 행이 갑자기 바뀌는 혼동을 유발하므로.

---

## 7. 데이터 렌더링 정책 (재사용 라이브러리)

### 7.1 마크다운
- `components/common/StyledMarkdown.tsx` 그대로 사용. 코드 블록 syntax highlight 지원 여부는 현재 컴포넌트에 위임.

### 7.2 result/markdown-viewer 본문 추출 (B-2 정정)

백엔드 `warehouse.py _entry_body()` (warehouse.py:427-458) 의 우선순위와 **정확히 일치**:

```ts
function pickBody(data: Record<string, unknown>): unknown {
  if (data.data !== undefined) return data.data;       // 1순위
  if (data.markdown !== undefined) return data.markdown; // 2순위
  if (data.response !== undefined) return data.response; // 3순위
  if (data.output !== undefined) return data.output;   // 4순위
  return data; // fallback: 통째로 (JSON.stringify)
}
```

> **순서 정정 (B-2)**: v1 의 `markdown → data → response → output → fallback` 은 backend 와 불일치. backend 순서는 **`data → markdown → response → output → fallback`**. 본 v2 는 backend 와 정확히 일치하도록 정정.

**렌더 분기**:

| body 타입 | result 노드 | markdown-viewer 노드 |
|-----------|-------------|---------------------|
| `string` | `<pre>` 코드 블록 | StyledMarkdown |
| `dict` / `list` (object) | ```json``` code block 으로 감싼 후 `<pre>` | ```json``` code block 으로 감싼 후 StyledMarkdown (markdown 처럼 렌더) |
| `null`/`undefined` | "본문 없음" empty | 동일 |
| `number`/`bool` | 그대로 stringify | 동일 |

> **결정 D-11 (H-4 재명시)**: result 와 markdown-viewer 는 **동일 본문 추출 함수 + 다른 렌더**. dict/list 도 ```json``` code block 으로 감싸 markdown-viewer 가 markdown 처럼 렌더하도록 일치. 본문 추출 우선순위는 본 §7.2 가 **유일한 단일 정의**.

### 7.3 InstanceDB records (R-9)
- 표 컬럼: id (truncated), createdAt, dedupKey, sourceWorkflowId(축약), sourceExecutionId(축약), data summary (`{N keys}`).
- 행 클릭 시 행 아래로 펼침: JsonTreeView(data, depth=1).
- dedupKey 검색 인풋(상단)으로 listRecords 의 dedupKey 파라미터 사용.
- **R-9 컨텍스트 필터**: viewer → sourceWorkflowId, instance → sourceExecutionId 자동 적용. 헤더에 "현재 컨텍스트로 필터링됨 — 전체 N / 필터 결과 M" 카운트 표시.

### 7.4 일반 JSON
- `JsonTreeView` (§3.3) 만 사용. 깊이 0 펼침 기본.

### 7.5 빈/로딩/오류 상태 (M-5)
- `NodeInspectorEmpty` 단일 컴포넌트:
  - `loading`: spinner + "불러오는 중..."
  - `empty`: "데이터 없음" + 노드별 힌트 (예: "워크플로우를 실행하면 데이터가 생성됩니다.")
  - `error`: 빨간 박스 + 메시지 + 재시도 버튼 (`onRetryCatalog` / `onRetryExtra` / `onRetryData` 중 해당 콜백 노출)
  - `unsupported`: "이 노드는 보유 데이터가 없습니다" — 비활성 탭 클릭 시(이론상 disabled로 도달 안 함, fallback)

---

## 8. 라우팅 / 페이징 / 성능

### 8.1 URL 동기화 (선택, 단계적)
- **Phase 1 에서는 URL 동기화 없음**. selectedNode 는 페이지 메모리 state.
- **Phase 4 옵션**: `?node={instanceId}&tab=info|data|run` 쿼리 파라미터로 deep-link.
  - 장점: 인스턴스 실행 결과 deep-link, 사용자에게 공유 가능.
  - 단점: 라우팅 코드 추가, history 노이즈.
  - 권고: InstanceDetailPage 만 Phase 4 에서 도입.

### 8.2 페이징 UI (B-1)
- 데이터 탭 하단 고정: `[< 이전]  page 1/N (total M)  [다음 >]`
- 기본 limit=20.
- result/markdown-viewer/mapper: `factoryApi.getWarehouse(nodeId, { limit, skip })` — **B-1**: api.ts 의 `factoryApi.getWarehouse` 시그니처를 v2 에서 `(nodeId: string, params?: { limit?: number; skip?: number })` 로 확장. 호출부(§5.5 result/markdown-viewer, §5.3 mapper)는 모두 객체 form 사용.
- instance-db: `instanceDbApi.listRecords(id, { limit, offset, sourceWorkflowId?, sourceExecutionId? })` — backend limit 1-500 검증, offset 지원 (R-9 query 파라미터 추가).
- knowledge: `knowledgeApi.list({ category, limit, offset })`.

### 8.3 캐시 / 중복 fetch
- 카탈로그: 페이지 mount 1회. unmount 시 폐기.
- 데이터 탭: 노드 변경 시 매번 fetch (단, 이전 페이지 기억은 안 함, 페이지 1로 reset).
- **WarehouseNode 카드의 자동 폴링과 드로어 fetch 는 별개로 둔다.** WarehouseNode 가 10초마다 호출하는 `factoryApi.getWarehouse(id, { limit:1 })` 은 count 만 사용하므로 충돌 없음. 드로어가 동시에 같은 endpoint 를 limit=20 으로 호출해도 backend 동시성 안전(read-only).
- 카탈로그 fetch 가 늦어지는 동안에도 드로어를 열 수 있어야 함 → catalog === null 이면 정보 탭 §2-7 영역에 "카탈로그 로딩 중..." 표시, 헤더/§3 (config) 는 즉시 표시.

### 8.4 성능 가드
- `JsonTreeView` 는 **각 깊이별로 직접 자식만 펼친다** (현재 EdgeInspectorPanel 구현 동일). depth 1 기본 펼침.
- 한 응답이 매우 큰 경우(>100 KB) 에는 트리뷰 root 에 "표시: 처음 200 키" 같은 truncation. (Phase 4 개선 사항으로 표시, Phase 1~3 은 현재 동작 그대로 둔다.)

---

## 9. 키보드 / 접근성 (M-4)

| 키 | 동작 |
|----|------|
| ESC | 드로어 닫기 (글로벌 캡처) |
| ←/→ | 활성 탭 좌/우 이동 (focus 가 탭바일 때) |
| Tab | **자유 이동** (focus trap **제거** — M-4). Tab 키로 캔버스/사이드바로 자유 이동 가능. |
| Enter/Space | 탭 버튼 활성, 행 펼침 |

- `role="dialog"`
- **`aria-modal="false"` (M-4)** — 비-modal 드로어. 캔버스/사이드바 인터랙션 허용.
- **focus trap 제거 (M-4)**. ESC 키만 글로벌로 캐치.
- `aria-label`: "노드 검사 패널 — {instanceName}"
- 탭바: `role="tablist"`, 각 탭 `role="tab"` `aria-selected`.
- 닫기 버튼: `aria-label="닫기"`.

---

## 10. "클릭하여 …" 라벨 처리 (D-1, L-2)

| 파일 | 라인 | 라벨 | 변경 권고 |
|------|------|------|----------|
| ApiStartNode.tsx | :106 | "클릭하여 ..." | Phase 1~3 **유지**. Phase 4 에서 마이크로카피 변경 (L-2). |
| ApiCallNode.tsx | :133 | 동상 | 동일 |
| UnpackerNode.tsx | :89 | 동상 | 동일 |
| MapperNode.tsx | :102 | 동상 | 동일 |
| WarehouseNode.tsx | :103 | "클릭하여 데이터 확인" | 동일 |
| MarkdownViewerNode.tsx | :72 | "클릭하여 …" | 동일 |

> **결정 D-1**: 라벨은 그대로 두되, 드로어 도입 후 시각 회귀 테스트(§12)에서 "클릭 → 드로어 열림" 동작이 모든 라벨 노드에서 검증되도록 명시한다.
> **L-2 (Phase 4 candidate)**: "클릭하여 데이터 확인" → "상세 정보 보기" 등 문구 변경. Phase 1c 와 분리.

---

## 11. 신규/수정 파일 목록 (v2.1)

| 분류 | 경로 | 작업 | 책임 에이전트 | 비고 |
|------|------|------|-------------|------|
| 신규 | `frontend/src/components/workflow/NodeInspectorDrawer.tsx` | 작성 | designer | Phase 1a skeleton, 1b/1c 본구현 |
| 신규 | `frontend/src/components/workflow/NodeInspectorTabBar.tsx` | 작성 | designer | Phase 1b |
| 신규 | `frontend/src/components/workflow/NodeInspectorEmpty.tsx` | 작성 | designer | Phase 1b. retry 콜백 props (M-5) |
| 신규 | `frontend/src/components/workflow/NodeInspectorInfoTab.tsx` | 작성 | designer | Phase 1b |
| 신규 | `frontend/src/components/workflow/NodeInspectorDataTab.tsx` | 작성 | designer | Phase 2. 7종 분기 (form-preview/mapper/knowledge/instance-db/result/markdown-viewer 등) |
| 신규 | `frontend/src/components/workflow/NodeInspectorRunTab.tsx` | 작성 | designer | Phase 3 |
| 신규 | `frontend/src/components/common/JsonTreeView.tsx` | 추출/작성 | designer | Phase 1a |
| 수정 | `frontend/src/components/workflow/EdgeInspectorPanel.tsx` | JsonTreeView import 로 교체 + 회귀 테스트 | designer | Phase 1a |
| 수정 | `frontend/src/components/workflow/WorkflowViewerCanvas.tsx` | onPaneClick prop 추가 | designer | Phase 1c |
| 수정 | `frontend/src/components/workflow/NodeOutputPill.tsx` | onClick stopPropagation 추가 (H-5 mental model) | designer | Phase 1c |
| 수정 | `frontend/src/pages/WorkflowViewerPage.tsx` | selectedNode state + 드로어 마운트 + onNodeClick/onPaneClick **신규 wiring (B-3)** + selection mutual exclusion (P-7: 노드 클릭 시 setSelectedEdge(null)) | designer | Phase 1c |
| 수정 | `frontend/src/pages/InstanceDetailPage.tsx` | 동일 + nodeResult 전달 + onNodeClick/onPaneClick **신규 wiring (B-3)** + selection mutual exclusion (P-7) | designer | Phase 1c |
| **수정 (P-1, 신규)** | **`frontend/src/types/index.ts`** | `WorkflowExecution.nodeResults` 의 타입을 `NodeExecutionResult[]` (배열, 잘못된 타입) → `Record<string, NodeExecutionResult>` 로 정정. backend `app/models/workflow.py:192` (Mapped[Dict[str, Any]]) 와 응답 변환 `app/api/routes/warehouse.py:98` 가 dict 임에 정합. **이 변경은 InstanceDetailPage 의 `Object.entries(ex.nodeResults)` 같은 기존 사용처가 컴파일되도록 유지하면서, §3.7 / §6 / D-12 의 `instance.nodeResults?.[selectedNode.nodeInstanceId]` indexer 접근이 컴파일되게 한다.** | designer | Phase 1a (드로어 wiring 전 선행) |
| **수정 (P-2, 신규)** | **`frontend/src/services/api.ts` (knowledgeApi.list)** | 현재 `list(category?: string)` 단일 인자 → `list(params?: { category?: string; limit?: number; offset?: number })` 객체 인자로 확장. backend `knowledge.py:82-87` 가 category/skip/limit 모두 지원하므로 그대로 통과. 기존 사용처(category 만 넘기던 곳)는 `list({ category })` 로 동시 수정. | designer | Phase 2 시작 시 (Phase 1a 와 함께 묶거나, Phase 2 의 첫 작업으로) |
| 수정 | **`frontend/src/services/api.ts` (factoryApi.getWarehouse, B-1)** | `factoryApi.getWarehouse` 시그니처를 `(nodeId: string, params?: { limit?: number; skip?: number })` 로 확장. 기존 호출부(WarehouseNode 자동 폴링 등)는 backward compatible 하게 유지하거나 동시 수정. | designer | Phase 1a |
| 수정 | **`backend/app/api/routes/instance_dbs.py` (R-9)** | `GET /api/v1/instance-dbs/{id}/records` 에 `sourceWorkflowId` / `sourceExecutionId` query 파라미터 (둘 다 optional, AND 필터) 추가. 응답은 동일 RecordListResponse. 페이징(limit/offset) 유지. | executor | Phase 2 (backend) |
| **수정 (P-5, 신규)** | **`backend/app/models/instance_db.py`** | `InstanceDBRecord.source_workflow_id` 와 `source_execution_id` 두 컬럼에 `index=True` 를 추가. R-9 필터가 자주 호출되고 records 누적될수록 풀 스캔 → 인덱스 필수. **마이그레이션 정책**: 본 프로젝트는 alembic **미사용**(`backend/app/core/database.py:59` 의 `Base.metadata.create_all` 사용, scripts/wipe.py 가 재생성을 담당)이므로, ① 신규/wipe 후 재생성 환경에서는 `index=True` 만으로 자동 적용된다. ② 기존 `instance_db_records` 테이블이 이미 존재하는 환경에서는 `CREATE INDEX IF NOT EXISTS` SQL 1회 실행이 필요하므로, Phase 2 backend 작업의 **첫 step** 으로 (a) 모델 컬럼에 `index=True` 추가, (b) 기존 데이터 보존이 필요한 환경을 위해 `scripts/` 에 1회용 인덱스 생성 보조 SQL 스니펫(`CREATE INDEX IF NOT EXISTS ix_instance_db_records_source_workflow_id ON instance_db_records (source_workflow_id);` / `..._source_execution_id`) 또는 wipe + 재생성 사용을 README 한 줄로 명시. | executor | Phase 2 (backend) — R-9 라우트 변경의 직전 step |
| 데이터 탭 분기 | mapper / knowledge / form-start | NodeInspectorDataTab 의 분기 로직 | designer | Phase 2 |

---

## 12. 검증 체크리스트 (architect 가 사용)

### 12.1 빌드/타입
- [ ] `cd "AI 업무도우미/frontend" && npm run build` — 0 에러 (CLAUDE.md §9-7 강제).
- [ ] tsc strict 모드: 모든 신규 파일 any 사용 0 (단, ReactFlow Node<any> 만 허용).

### 12.2 백엔드 회귀
- [ ] `cd "AI 업무도우미/backend" && python -m pytest -q` — 63개 테스트 통과 (CLAUDE.md §9-6).
- [ ] R-9 backend 변경에 대한 신규 테스트 추가 (sourceWorkflowId 필터 / sourceExecutionId 필터 / 둘 다 적용 AND).

### 12.3 기능 회귀 (수동/Playwright)
13종 노드 각각에 대해:
- [ ] 워크플로우 뷰어에서 노드 클릭 → 드로어 열림.
- [ ] 같은 노드 재클릭 → 드로어 닫힘.
- [ ] 다른 노드 클릭 → 드로어 노드 교체.
- [ ] ESC → 드로어 닫힘.
- [ ] 캔버스 빈 영역 클릭 → 드로어 닫힘.
- [ ] 정보 탭: header/purpose/config(camelCase)/inputs(snake_case)/catalog config(snake_case)/inputMapping/§6 추가정보/useCases/connectsWellWith 모두 표시.
- [ ] 데이터 탭(매트릭스 §5.6 활성 7종): 페이지네이션 동작, 빈/로딩/오류 상태 정상.
- [ ] InstanceDetailPage 에서만 실행 결과 탭 표시. 워크플로우 뷰어는 미표시.
- [ ] R-9: WorkflowViewerPage 컨텍스트 instance-db 필터 = sourceWorkflowId. InstanceDetailPage 컨텍스트 = sourceExecutionId.

### 12.4 충돌 회귀
- [ ] WarehouseNode/MarkdownViewerNode 카드의 NodeOutputPill 클릭 시 드로어가 열리지 않는다 (H-5 mental model).
- [ ] EdgeInspectorPanel 과 NodeInspectorDrawer 가 동시에 열리지 않는다. **close 책임자 (P-7): Page state 가 두 selection 을 mutually exclusive 하게 관리. 노드 클릭 핸들러 안에서 `setSelectedEdge(null)`, 엣지 클릭 핸들러 안에서 `setSelectedNode(null)` 을 호출하는지 코드 리뷰 시 확인.**
- [ ] WarehouseNode 의 10초 자동 폴링 카운트가 드로어 오픈 동안에도 정상.
- [ ] B-1: `factoryApi.getWarehouse` 시그니처 변경 후 WarehouseNode 자동 폴링이 정상 동작.
- [ ] **P-2: `knowledgeApi.list` 시그니처 변경 후 기존 사용처(KnowledgeListPage 등) 회귀 0건.**
- [ ] **P-1: `WorkflowExecution.nodeResults` 타입 정정 후 InstanceDetailPage 의 `Object.entries(ex.nodeResults)` 가 동일 동작 + 새 indexer `instance.nodeResults?.[id]` 도 정상.**
- [ ] **P-6 fetch 공유: mapper/result/markdown-viewer 데이터 탭 진입 후 정보 탭으로 돌아가도 limit=1 추가 호출 0건 (DevTools Network 탭 확인).**

### 12.5 시각 회귀 (Playwright) — 22장 (M-6)

`_참고자료/screenshots/node-inspector-*.png` 22장 캡처 (MEMORY: 스크린샷 위치 정책 준수).

**시나리오 명세**:

| # | 파일명 | 시나리오 |
|---|--------|---------|
| 1 | `node-inspector-form-start-info.png` | form-start 정보 탭 |
| 2 | `node-inspector-api-start-info.png` | api-start 정보 탭 |
| 3 | `node-inspector-ai-custom-info.png` | ai-custom 정보 탭 (systemPrompt 접힘 상태) |
| 4 | `node-inspector-ai-api-router-info.png` | ai-api-router 정보 탭 |
| 5 | `node-inspector-sorter-info.png` | sorter 정보 탭 |
| 6 | `node-inspector-unpacker-info.png` | unpacker 정보 탭 |
| 7 | `node-inspector-mapper-info.png` | mapper 정보 탭 |
| 8 | `node-inspector-api-call-info.png` | api-call 정보 탭 |
| 9 | `node-inspector-knowledge-info.png` | knowledge 정보 탭 |
| 10 | `node-inspector-instance-db-insert-info.png` | instance-db-insert 정보 탭 |
| 11 | `node-inspector-instance-db-lookup-info.png` | instance-db-lookup 정보 탭 |
| 12 | `node-inspector-result-info.png` | result 정보 탭 |
| 13 | `node-inspector-markdown-viewer-info.png` | markdown-viewer 정보 탭 |
| 14 | `node-inspector-result-data.png` | result 데이터 탭 |
| 15 | `node-inspector-markdown-viewer-data.png` | markdown-viewer 데이터 탭 |
| 16 | `node-inspector-instance-db-insert-data.png` | instance-db-insert 데이터 탭 (R-9 필터링 적용) |
| 17 | `node-inspector-mapper-data.png` | mapper 데이터 탭 |
| 18 | `node-inspector-knowledge-data.png` | knowledge 데이터 탭 |
| 19 | `node-inspector-ai-custom-systemprompt-expanded.png` | ai-custom systemPrompt 펼친 상태 |
| 20 | `node-inspector-result-row-expanded.png` | result 데이터 탭 행 펼친 상태 |
| 21 | `node-inspector-data-error-state.png` | 데이터 탭 fetch 실패 + 재시도 버튼 |
| 22 | `node-inspector-small-container.png` | InstanceDetailPage 360px 컨테이너에서 드로어 내부 스크롤 (F-10) |

(주: form-start 데이터 탭은 form preview 동작이므로 #14-18 중 별도 케이스로 추가하지 않고, 정보 탭에서 검증되는 config.fields 표와 함께 기능 회귀 §12.3 으로 커버. 필요 시 23번째로 추가 가능.)

### 12.6 a11y (M-4)
- [ ] 키보드만으로 드로어 오픈 / 탭 전환 / 닫기 가능.
- [ ] **focus trap 없음 검증** — Tab 키로 드로어 → 캔버스 → 사이드바 자유 이동.
- [ ] `aria-modal="false"` 검증.
- [ ] ESC 키 글로벌 캡처 검증 (드로어 외부에 focus 가 있어도 ESC 로 닫힘).
- [ ] 스크린리더 announce 검증 (NVDA / VoiceOver 둘 중 하나).

---

## 13. Phase 분할 (v2.1 — H-6 분할 + P-4 산출물 명확화 반영)

권고: **6 phase 로 분할 (1a/1b/1c/2/3/4)**. 단일 PR/세션이 너무 커지면 회귀 위험 + 리뷰 부담. 각 sub-phase 가 architect 검증 가능한 단위.

| Phase | 목표 | 주요 산출물 | 성공 기준 |
|-------|------|------------|----------|
| **1a** | 스켈레톤 + JsonTreeView 추출 + 타입 정정 | `NodeInspectorDrawer.tsx` (빈 컴포넌트), `JsonTreeView.tsx`, EdgeInspectorPanel 의 TreeNode 를 JsonTreeView 로 교체 + EdgeInspectorPanel 회귀 테스트, `factoryApi.getWarehouse` 시그니처 확장(B-1), **`frontend/src/types/index.ts` 의 `WorkflowExecution.nodeResults` 타입 정정 (P-1: 배열 → Record)**. 회귀 점검: `InstanceDetailPage.tsx:309-311` 의 `Object.entries(ex.nodeResults)` 가 새 타입에서도 컴파일·동작하는지(Record 에서도 정상). 그 외 사용처 grep 으로 식별. | EdgeInspectorPanel 시각·동작 동치 보존. 빈 드로어 mount 가능. 기존 회귀 0. **P-1 타입 정정 후 frontend `npm run build` 0 에러 + InstanceDetailPage 회귀 검증 통과.** |
| **1b** | 정보 탭 §1-§5 + §7-§8 + 13종 매트릭스 (정보 탭 한정) | `NodeInspectorTabBar`, `NodeInspectorInfoTab`, `NodeInspectorEmpty`, header / 현재 config(인스턴스 표기, 일괄 camelCase) / Inputs/Outputs(카탈로그 표기, 노드별 상이) / catalog config(카탈로그 표기, 필드별 상이 — §부록A 매트릭스 참조) / UseCases / ConnectsWellWith, 13종 카탈로그 호환성 검증. **form-start 정보 탭 (P-4)**: 단순 카탈로그 표시(특별 fetch 없음, config.fields/defaultValues 표만). **§부록A catalog config 키 표기 매트릭스의 정확성 1차 검증** (catalog.py 와의 1:1 대조). | 13종 노드 정보 탭 §1-§5,§7-§8 표시. 빌드 + pytest 통과. |
| **1c** | 정보 탭 §6 추가 정보 + 페이지 통합 + Phase 1c 한정 카운트 배지 (P-4) | apiDefinition/instanceDb/aiNode/knowledge/api-router fetch + 렌더, WorkflowViewerPage / InstanceDetailPage 의 onNodeClick/onPaneClick **신규 wiring** (B-3) + selection mutual exclusion (P-7), ESC 핸들러, NodeOutputPill stopPropagation (H-5). **Phase 1c 한정 — P-4 산출물 명확화**: <br>① **mapper 정보 탭 §6 카운트 배지** (`config.warehouseNodeId` 가 가리키는 창고 노드의 적재 카운트 1회 호출). 이 시점에 **데이터 탭은 disabled 상태이므로 fetch 공유(P-6)는 적용 불가**, 정보 탭 단독 진입 호출만 수행. <br>② **knowledge 정보 탭 §6 의 카테고리 카운트 표시** (정보 탭 단독 호출, 데이터 탭은 Phase 2). <br>③ **form-start 정보 탭 표시** (단순 카탈로그 표시 — 데이터 탭의 read-only form preview 는 Phase 2). <br>**※ mapper / knowledge / form-start 의 데이터 탭(records preview / documents 목록 / form preview) 자체 활성화는 Phase 2 의 일.** Phase 1c 산출물에 데이터 탭 활성화는 포함되지 않는다. <br>④ **P-1 회귀 점검 재검증**: §3.7 InstanceDetailPage 의 `instance.nodeResults?.[selectedNode.nodeInstanceId]` indexer 가 정상 컴파일·동작. NodeProgress 흐름과의 정합도 확인. | 13종 노드 클릭 → 정보 탭 완전 표시. ESC/pane click/같은 노드 토글/다른 노드 교체 모두 동작. EdgeInspectorPanel ↔ NodeInspectorDrawer 동시 오픈 0건 (§12.4, P-7). |
| **2** | 데이터 탭 (7종) + R-9 backend + InstanceDB 인덱스 (P-5) + knowledgeApi 시그니처 (P-2) | `NodeInspectorDataTab` + 페이지네이션 + 7종 분기 (form-preview F-4, mapper H-1, knowledge H-2, instance-db-insert/lookup R-9, result, markdown-viewer), StyledMarkdown 통합, 데이터 빈/로딩/오류 상태 (M-5 retry props). <br>**backend 작업 순서 (P-5 첫 step → R-9)**: <br>① **`backend/app/models/instance_db.py` 의 `source_workflow_id`/`source_execution_id` 에 `index=True` 추가** + (alembic 미사용 환경의) 1회용 `CREATE INDEX IF NOT EXISTS` SQL 스니펫 또는 wipe+재생성 안내. <br>② **`backend/app/api/routes/instance_dbs.py` 의 `GET /api/v1/instance-dbs/{id}/records` 에 `sourceWorkflowId`/`sourceExecutionId` query 파라미터 (AND 필터) 추가**. <br>③ pytest 신규 테스트: 단일 필터 / AND 필터 / 인덱스 사용 검증(EXPLAIN 또는 실행시간 회귀). <br>**frontend 작업 순서**: <br>① **`knowledgeApi.list` 시그니처 확장 (P-2)**: 객체 인자 + 기존 사용처 동시 수정. <br>② NodeInspectorDataTab + 7종 분기 본체. <br>③ **fetch 공유 (P-6, R-1)**: mapper / result / markdown-viewer 가 데이터 탭 진입 시 받는 응답의 `total` 을 정보 탭 §6 카운트 배지에도 동일 사용 (limit=1 별도 호출 절감). | 7종 데이터 탭 모두 동작. count 매칭(P-6 fetch 공유 후에도 동일 N). 페이지 이동 동작. R-9 컨텍스트 필터 정확. backend 신규 테스트 통과. P-5 인덱스 적용 확인 (sqlite EXPLAIN QUERY PLAN 에서 SCAN 이 SEARCH 로 변경). |
| **3** | 실행 결과 탭 + a11y + 시각 회귀 22장 | `NodeInspectorRunTab`, InstanceDetailPage 한정 표시, status==='failed' 자동 선택, role/aria-* 마무리 (M-4 비-modal), Playwright 시각 회귀 22장 | architect 검증 통과 + 시각 회귀 22장 0 diff. |
| **4** | 후속 개선 (선택) | URL 동기화 (`?node=&tab=`), 큰 JSON truncation, 마이크로 카피 라벨 다듬기 (L-2), NodeCatalogPage 드로어 통합 (F-9) | 사용자 피드백 기반 우선순위 결정. |

---

## 14. 위험 / 오픈 이슈 (v2)

| ID | 위험 | 영향 | 완화 |
|----|------|-----|------|
| R-1 | factoryApi.getWarehouse 가 limit=1 카운트(정보 탭 §6) 와 limit=20 본문(데이터 탭) 으로 두 번 호출될 수 있음 (mapper/result/markdown-viewer 의 같은 nodeId, P-6 정정) | 미미 (read-only) | **결정 (P-6, C-4)**: 같은 nodeId 의 limit=1 카운트 호출은 데이터 탭 첫 fetch 의 응답에 포함된 `total` 을 정보 탭 §6 카운트 배지에 재사용하여 절감한다. 즉 ① 정보 탭만 본 사용자 → limit=1 한 번. ② 사용자가 데이터 탭을 진입하는 순간 데이터 탭의 limit=20 응답이 도착하면 그 `total` 로 정보 탭 카운트도 갱신. ③ 데이터 탭에서 다시 정보 탭으로 돌아가도 새 limit=1 호출은 일어나지 않음. 별도 react-query 캐시 도입은 하지 않고 드로어 내부 useState 로 관리한다. WarehouseNode 카드의 10초 자동 폴링(`limit:1`) 은 별개 — 드로어와 무관하게 그대로 동작. |
| R-2 | ai-api-router 의 apiIds 가 100개일 때 `Promise.all(get)` 100회 | 응답 지연 | 10개 초과 시 `apiDefinitionApi.list()` 한 번 + 클라이언트 필터로 폴백. |
| R-3 | WorkflowViewer 에서 nodeResult 가 없는데 사용자가 실행 결과 탭을 기대 | 혼동 | 탭을 아예 렌더 안 함. 정보 탭에만 "실행은 인스턴스 페이지에서 확인" 작은 안내. |
| R-4 | 드로어 width 400px 가 좁은 화면에서 캔버스를 가린다 | UX 저하 | 화면 < 1024px 에서는 drawer를 100% width 모달처럼 전환 (Phase 4). M-8: min-w-[400px] max-w-[480px] 가변. |
| R-5 | StyledMarkdown 이 매우 긴 markdown 렌더 시 느림 | 성능 | 데이터 탭 행 펼침 시점에만 렌더. 닫으면 unmount. |
| R-6 | NodeOutputPill stopPropagation 추가 시 다른 곳의 클릭 이벤트(예: 카드 자체 selection)에 영향 | 회귀 | ReactFlow `onNodeClick` 은 카드 자체에 부착되어 있고, pill click 만 막는 것이므로 영향 범위는 pill 자체에 한정. H-5 의도된 mental model 변경으로 명시. 회귀 테스트 §12.4. |
| R-7 | catalog fetch 실패 시 정보 탭 절반 비어보임 | UX 저하 | header/§3 config 만 즉시 표시 + 안내 + `onRetryCatalog` 재시도 버튼 (M-5). |
| R-8 | LEGACY_DEF_TYPE_MAP 에서 매핑 실패한 defType (드물게) | 카탈로그 미스매치 | "알 수 없는 노드 타입" empty 정보 탭. defType 그대로 표시. |
| **R-9 (해결됨)** | InstanceDB 데이터 탭이 instanceDB 전체 records 를 보여주는 것이 사용자 의도와 다를 수 있음 | (해결됨) | **제품 결정**: backend 에 `sourceWorkflowId`/`sourceExecutionId` query 파라미터 추가 (AND 필터). viewer 컨텍스트는 sourceWorkflowId, instance 컨텍스트는 sourceExecutionId 자동 적용. 카운트는 "전체/필터" 둘 다 표시. 노란 배너 제거. |
| R-10 | ai-custom 의 systemPrompt 에 시크릿이 포함될 가능성 | 보안 | 디폴트 접힘 (D-6). 펼쳐도 화면 표시만. 복사 버튼은 Phase 4 추가 검토. |
| R-11 | mapper 노드의 "어느 창고" 표현 오해 | UX | H-1 정정: catalog mapper.config.warehouseNodeId 가 가리키는 임의의 창고 노드 인스턴스 id. 데이터 탭 활성화로 records 미리보기 직접 제공. |
| R-12 | ESC 글로벌 핸들러가 다른 모달(RunModal 등) 과 충돌 | 키 가로채기 | RunModal 은 별도 모달 컴포넌트. 드로어는 `useEffect` 안에서 `document.activeElement` 가 드로어 내부 또는 캔버스일 때만 처리. 일반적으로 모달이 위 z-index 이면 ESC 는 모달이 먼저 처리되어야 함 — Phase 1c 에서 stopPropagation 으로 가드. |
| R-13 (신규) | M-9 race condition: 빠른 노드 교체 시 stale fetch 가 새 노드 state 를 덮어쓰기 | 잘못된 데이터 표시 | useEffect cleanup 에서 AbortController.abort() + cancelled flag 이중 가드 (§3.1). |
| R-14 (신규) | F-10 작은 컨테이너(360px) 에서 드로어 콘텐츠 잘림 | UX | 컨테이너 `relative`, 드로어 `h-full overflow-y-auto` 로 내부 스크롤. 시각 회귀 §12.5 #22 로 검증. |
| R-15 (신규) | H-3 catalog snake_case ↔ 인스턴스 camelCase 혼동 | 사용자 오해 | §3 / §4 / §5 표 헤더에 표기 컨벤션 명시. |

---

## 15. critic 우선 검토 요청 항목 (v2)

다음 항목은 v2 변경 또는 새 결정의 핵심이므로 critic 가 우선 검토.

1. **R-9 backend 사양 (instance_dbs.py query 파라미터)** — `sourceWorkflowId` 와 `sourceExecutionId` 의 AND 필터 동작이 backend `InstanceDBRecord` 컬럼 (instance_db.py) 와 정확히 일치하는지. 페이징(limit/offset) 과의 상호작용. 기존 RecordListResponse 호환성.
2. **§7.2 본문 추출 우선순위 정정 (B-2)** — backend `_entry_body()` (warehouse.py:427-458) 와 정확히 일치하는지(`data → markdown → response → output → fallback`). dict/list 일 때 ```json``` code block 으로 감싸 markdown-viewer 가 markdown 으로 렌더되게 일치.
3. **§5.3 mapper / §5.4 knowledge / §5.1 form-start 데이터 탭 활성화** — H-1 mapper (warehouseNodeId 미리보기), H-2 knowledge (knowledgeApi.list 카테고리 매칭 + 200자 preview), F-4 form-start (read-only form preview) 의 구현 가능성과 사용자 가치.
4. **§3.6/§3.7 onNodeClick / onPaneClick 신규 wiring (B-3)** — 페이지에 wiring 이 미존재함을 명시. WorkflowViewerCanvas 의 prop 정의는 있으나 사용처가 없는 현재 상태.
5. **§13 Phase 1a/1b/1c 분할 (H-6)** — 각 sub-phase 가 architect 검증 가능한 독립 단위인지. Phase 2 의 backend 변경(R-9)과 Phase 1c 의 wiring 의 의존성 방향.

(추가 일반 항목: §5.6 13/13 매트릭스 v2 완전성, §3.8 H-5 mental model 변경의 사용자 영향, §9 M-4 비-modal a11y 정합성, §12.5 22장 시각 회귀 시나리오 적절성)

---

## 16. 변경 이력

| 일자 | 버전 | 작성자 | 비고 |
|------|------|-------|------|
| 2026-04-26 | 0.1 | planner (Prometheus) | 초안 — critic 검토 대상 |
| 2026-04-26 | **v2** | planner (Prometheus) | **critic APPROVE-WITH-CONDITIONS 12건 (B-1, B-2, B-3, H-1~H-6, M-1~M-9, L-2, F-4) + 제품 결정 2건 (R-9 backend 변경, F-4 form preview) 반영.** 주요 변경: §5.6 매트릭스 4종 → 7종 데이터 탭 활성 (form-start/mapper/knowledge 추가), §7.2 본문 추출 순서 정정 (data → markdown → response → output), §11 api.ts + instance_dbs.py 추가, §13 Phase 1a/1b/1c 분할, §9 비-modal + focus trap 제거, §12.5 13+4 → 22장 시각 회귀, §3.1 race condition 가드(AbortController), §3.5/3.6/3.7 onNodeClick/onPaneClick 신규 wiring 명시, §4 §3/§4/§5 헤더에 camelCase/snake_case 표기 컨벤션 명시, §3.8 NodeOutputPill 의도된 mental model 명시. |
| 2026-04-26 | **v2.1** | planner (Prometheus) | **critic 2차 의결 APPROVE-WITH-CONDITIONS 7건 반영 (필수 4 + 권장 3, 모두 채택).** 변경 위치 요약: <br>**P-1 (C-1)** §3.7 + §11 — `frontend/src/types/index.ts:225-251` 의 `WorkflowExecution.nodeResults` 타입을 `NodeExecutionResult[]` (배열, 잘못됨) → `Record<string, NodeExecutionResult>` 로 정정. backend `app/models/workflow.py:192` (Mapped[Dict]) 와 응답 `app/api/routes/warehouse.py:98` 가 dict 임에 정합. §3.7 / §6 / D-12 의 indexer 접근 컴파일 가능. 회귀 점검은 §13 Phase 1a + 1c. <br>**P-2 (C-2)** §5.3 + §11 — `knowledgeApi.list` 시그니처 `(category?)` → `(params?: { category?, limit?, offset? })` 객체 인자 확장. backend `knowledge.py:82-87` 그대로 통과. Phase 2 시작 시. <br>**P-3 (C-3)** §4 §3/§4/§5 헤더 라벨 정정 + **§부록 A 신설** — "카탈로그 표기 = snake_case" 라벨은 부정확. 실제로 ai-custom 의 `ai_node_id` 만 snake, 나머지(`warehouseNodeId`, `matchKey`, `outputField`, `systemPrompt`, `maxTokens`, `provider`, ...)는 camel. 헤더를 "카탈로그가 정의한 표기 그대로 (필드별 상이)" 로 변경. §부록 A 에 13종 노드의 catalog config 키 표기 매트릭스 첨부. <br>**P-4 (D-2)** §13 Phase 1c 산출물 명확화 — Phase 1c = ① mapper 정보 탭 §6 카운트 배지 (창고 노드 카운트 1회 호출) ② knowledge 정보 탭 카테고리 카운트 ③ form-start 정보 탭(단순 카탈로그). **데이터 탭 활성화(records preview / documents 목록 / form preview) 는 모두 Phase 2.** <br>**P-5 (C-6)** §11 — `backend/app/models/instance_db.py` 의 `source_workflow_id`/`source_execution_id` 에 `index=True` 추가 + alembic 미사용 환경(create_all 기반)을 위한 1회용 SQL 스니펫 안내. Phase 2 backend 의 첫 step. <br>**P-6 (C-4)** §14 R-1 정정 — mapper/result/markdown-viewer 의 정보 탭 카운트 + 데이터 탭 본문 fetch 가 같은 nodeId 로 두 번 호출되는 사실 인정. **데이터 탭 응답의 `total` 을 정보 탭 카운트로 재사용** (드로어 useState 캐시) 으로 절감. WarehouseNode 카드 폴링은 별개 유지. <br>**P-7 (C-5)** §3.6 / §3.7 / §12.4 — EdgeInspectorPanel ↔ NodeInspectorDrawer mutual exclusion 의 **close 책임자가 Page state 임을 명시**. 노드 클릭 핸들러 안에서 `setSelectedEdge(null)`, 엣지 클릭 핸들러 안에서 `setSelectedNode(null)`. |

---

## 부록 A — Catalog Config 키 표기 매트릭스 (P-3, v2.1 신설)

> backend `app/nodes/catalog.py` 의 `CATALOG: List[NodeCatalogEntry]` 를 1:1 으로 대조한 표. 각 노드의 `config[].name` 을 그대로 옮겨, 표기(snake_case / camelCase / 단일 lowercase) 를 명시한다. `dedup` 같은 단일 단어는 표기 구분이 무의미하므로 "lowercase" 로 표시. 정보 탭 §5 (Catalog Config 스펙) 는 본 매트릭스에 의거하여 **카탈로그가 정의한 표기 그대로** 렌더한다 (camelCase 강제 변환 금지).
>
> 이 매트릭스는 critic C-3 검토 후 catalog.py 갱신 시 함께 갱신해야 하는 **종속 문서**다. catalog.py 의 키가 추가/변경되면 본 매트릭스도 동시 수정.

| # | defType | 카테고리 | catalog.config[].name 목록 (catalog.py 출현 순) | 표기 |
|---|---------|---------|-----------------------------------------------|------|
| 1 | `form-start` | starter | `mode`, `scheduleConfig`, `fields`, `defaultValues` | 단일 lowercase + camelCase (snake 0건) |
| 2 | `api-start` | starter | `apiDefinitionId`, `mode`, `scheduleConfig`, `defaultParams` | 단일 lowercase + camelCase (snake 0건) |
| 3 | `ai-custom` | ai | `ai_node_id`, `prompt`, `systemPrompt`, `model`, `provider`, `temperature`, `maxTokens` | **혼재** — `ai_node_id` 만 snake, 나머지 camel/lowercase |
| 4 | `ai-api-router` | ai | `prompt`, `apiIds` | 단일 lowercase + camelCase (snake 0건) |
| 5 | `sorter` | logic | `rules`, `dedup` | 단일 lowercase (※ `dedup` 객체 내부 키 `enabled`/`warehouseNodeId`/`matchField` 는 camelCase) |
| 6 | `unpacker` | logic | `arrayField` | camelCase |
| 7 | `mapper` | logic | `warehouseNodeId`, `matchKey`, `outputField` | camelCase (3/3) |
| 8 | `api-call` | action | `apiDefinitionId`, `defaultParams` | camelCase (2/2) |
| 9 | `knowledge` | action | `searchField`, `categories`, `tags`, `maxResults` | 단일 lowercase + camelCase (snake 0건) |
| 10 | `instance-db-insert` | action | `instanceDbId`, `sourceMode`, `dataTemplate`, `dedupKeyTemplate`, `skipOnDuplicate` | camelCase (5/5) |
| 11 | `instance-db-lookup` | action | `instanceDbId`, `mode`, `keyTemplate`, `filterTemplate`, `limit` | 단일 lowercase + camelCase (snake 0건) |
| 12 | `result` | output | `dedupKeyTemplate` | camelCase |
| 13 | `markdown-viewer` | output | `displayKey`, `dedupKeyTemplate` | camelCase (2/2) |

**관찰 (P-3 정정 근거)**:
- 13종 42개 config 키 중 **snake_case 는 단 1개** (`ai_node_id`).
- 나머지 41개는 모두 camelCase 또는 단일 단어 lowercase (`mode`, `prompt`, `model`, `provider`, `temperature`, `rules`, `dedup`, `categories`, `tags`, `limit` 등).
- 따라서 v2 헤더 "카탈로그 표기 — snake_case" 는 사실과 정반대. v2.1 은 헤더를 "카탈로그가 정의한 표기 그대로 (필드별 상이)" 로 일괄 정정한다 (§4 §5 헤더).
- 인스턴스(`workflow.nodes[i].config`) 표기는 프론트엔드에서 일괄 camelCase 로 들어오므로, ai-custom 의 경우 catalog 표기 `ai_node_id` ↔ 인스턴스 표기 `aiNodeId` 의 매핑을 사용자가 동시에 보게 된다 (§3 인스턴스 camelCase / §5 카탈로그 snake — 이 노드 한정). 이 차이는 일부러 보존되며, 두 헤더가 모두 그 사실을 명시한다.
