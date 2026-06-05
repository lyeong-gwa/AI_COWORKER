/**
 * NodeInspectorDrawer — 노드 클릭 시 우측에 슬라이드되는 read-only 드로어.
 *
 * 설계 문서: `docs/node-inspector-plan.md` v2.1 §3.1
 *
 * Phase 1a: 빈 스켈레톤 + 레이아웃 + race-condition 가드 (AbortController)
 * Phase 1b: 정보 탭 §1-§5 + §7-§8
 * Phase 1c: 정보 탭 §6 (추가 정보 fetch + 렌더), 페이지 통합
 * Phase 2: 데이터 탭 7종 분기 (form-start/mapper/knowledge/result/markdown-viewer/instance-db-insert/instance-db-lookup)
 * Phase 3: 실행 결과 탭 (InstanceDetailPage 한정)
 */
import { useCallback, useEffect, useState } from 'react';
import type { Node } from '@xyflow/react';
import type { Workflow, WorkflowExecution } from '../../types';
import type { NodeCatalogEntry } from '../../services/api';
import { NodeInfoTab } from './NodeInfoTab';
import { NodeDataTab } from './NodeDataTab';

// ─── Types ────────────────────────────────────────────────────────────────

/** WorkflowExecution 의 nodeResults 항목 형태 (api.ts WorkflowExecution.nodeResults 의 value) */
export type NodeInspectorInstanceResult =
  | {
      status?: string;
      inputData?: unknown;
      outputData?: unknown;
      error?: string;
      startTime?: string;
      endTime?: string;
      definitionType?: string;
    }
  | undefined;

/** 페이지에서 전달하는 인스턴스 컨텍스트 (Phase 3 의 실행 결과 탭용) */
export interface NodeInspectorInstanceContext {
  /** 인스턴스 id */
  id: string;
  /** 노드별 실행 결과 — backend 응답 그대로 (Record) */
  nodeResults?: Record<string, unknown>;
}

export interface NodeInspectorDrawerProps {
  /** 선택된 ReactFlow 노드. null 이면 드로어 닫힘. */
  node: Node<any> | null;
  /** 현재 보고 있는 워크플로우 정의 */
  workflow: Workflow;
  /** 노드 카탈로그 (페이지 단위 prefetch). null 이면 로딩 중. */
  catalog: NodeCatalogEntry[] | null;
  /**
   * 드로어가 위치한 페이지 컨텍스트. instance-db 데이터 탭 필터링에 사용 (R-9).
   * - `viewer`: WorkflowViewerPage → sourceWorkflowId 로 필터
   * - `instance`: InstanceDetailPage → sourceExecutionId 로 필터
   * 기본값: 'viewer'
   */
  pageContext?: 'viewer' | 'instance';
  /** Phase 3 실행 결과 탭 활성화 — InstanceDetailPage 한정. 데이터 탭 instance-db 컨텍스트에도 사용. */
  instance?: NodeInspectorInstanceContext;
  /** 닫기 콜백 (ESC, X 버튼, pane click 모두 동일 콜백 사용) */
  onClose: () => void;
  /**
   * 인라인 노드 재료 편집 활성화 여부.
   * - true: WorkflowViewerPage — 드롭다운으로 참조 재료를 변경 가능
   * - false/undefined: InstanceDetailPage — read-only 유지
   */
  editable?: boolean;
  /**
   * 재료 변경 후 워크플로우를 새로고침하는 콜백.
   * editable=true 일 때 PATCH 성공 시 호출됨.
   */
  onWorkflowUpdated?: (updated: Workflow) => void;
}

type ActiveTab = 'info' | 'data' | 'run';

// 과거 DB 호환용 — `form` → `form-start` 정규화 (WorkflowViewerCanvas 와 동일 매핑)
const LEGACY_DEF_TYPE_MAP: Record<string, string> = {
  form: 'form-start',
};

/** §5 매트릭스: 데이터 탭 활성화 7종 */
const DATA_TAB_ENABLED_DEF_TYPES = new Set([
  'form-start',
  'mapper',
  'knowledge',
  'result',
  'markdown-viewer',
  'instance-db-insert',
  'instance-db-lookup',
]);

function resolveDefType(node: Node<any>, workflow: Workflow): string {
  const inst = workflow.nodes.find((n) => n.id === node.id);
  const raw = (inst?.definitionType ?? (node.data?.definitionType as string | undefined) ?? '') as string;
  return LEGACY_DEF_TYPE_MAP[raw] ?? raw;
}

// ─── Component ───────────────────────────────────────────────────────────

export function NodeInspectorDrawer({
  node,
  workflow,
  catalog,
  pageContext = 'viewer',
  instance,
  onClose,
  editable = false,
  onWorkflowUpdated,
}: NodeInspectorDrawerProps) {
  const [activeTab, setActiveTab] = useState<ActiveTab>('info');

  // [P-6] warehouse total 캐시 — 데이터 탭 fetch 결과를 정보 탭이 재사용한다.
  // React state 로 관리하여 cache 갱신 시 자동 re-render (prop 참조 변경 → useEffect 재실행).
  const [warehouseTotalCache, setWarehouseTotalCache] = useState<ReadonlyMap<string, number>>(new Map());

  const handleWarehouseTotalFetched = useCallback((wNodeId: string, total: number) => {
    setWarehouseTotalCache((prev) => {
      // 이미 같은 값이면 갱신 생략 (불필요한 리렌더 방지)
      if (prev.get(wNodeId) === total) return prev;
      const next = new Map(prev);
      next.set(wNodeId, total);
      return next;
    });
  }, []);

  // 노드가 바뀔 때마다 탭을 'info' 로 reset
  useEffect(() => {
    if (!node) return;
    setActiveTab('info');
  }, [node?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // ESC 키 글로벌 캡처 (M-4 비-modal 드로어, focus trap 없음)
  useEffect(() => {
    if (!node) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [node, onClose]);

  if (!node) return null;

  const defType = resolveDefType(node, workflow);
  const catalogEntry = catalog?.find((c) => c.defType === defType) ?? null;
  const instanceName =
    (workflow.nodes.find((n) => n.id === node.id)?.name) ??
    (node.data?.instanceName as string | undefined) ??
    node.id;

  const dataTabEnabled = DATA_TAB_ENABLED_DEF_TYPES.has(defType);
  const showRunTab = !!instance;

  // NodeDataTab 에 전달할 instance — WorkflowExecution 형태로 변환
  const instanceForDataTab = instance
    ? ({
        id: instance.id,
        workflowId: workflow.id,
        status: 'success' as const,
        nodeResults: (instance.nodeResults ?? {}) as Record<string, import('../../types').NodeExecutionResult>,
        startedAt: '',
        triggerInput: undefined,
      } satisfies WorkflowExecution)
    : undefined;

  return (
    <div
      role="dialog"
      aria-modal="false"
      aria-label={`노드 검사 패널 — ${instanceName}`}
      className="absolute top-0 right-0 h-full min-w-[400px] max-w-[480px] bg-gray-900 border-l border-gray-700 shadow-2xl flex flex-col z-40"
    >
      {/* Header — 닫기 버튼만, 본문 헤더는 NodeInfoTab §1 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700 shrink-0 bg-gray-800/80">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-white truncate">노드 검사</h3>
          <p className="text-[10px] font-mono text-gray-500 truncate">{node.id}</p>
        </div>
        <button
          onClick={onClose}
          className="text-gray-500 hover:text-gray-300 transition-colors text-lg leading-none ml-2 shrink-0"
          title="닫기 (ESC)"
          aria-label="닫기"
        >
          &times;
        </button>
      </div>

      {/* Tab bar */}
      <div role="tablist" className="flex border-b border-gray-800 shrink-0 bg-gray-900/60">
        <TabButton
          active={activeTab === 'info'}
          onClick={() => setActiveTab('info')}
          label="정보"
        />
        <TabButton
          active={activeTab === 'data'}
          onClick={() => setActiveTab('data')}
          label="데이터"
          disabled={!dataTabEnabled}
          title={dataTabEnabled ? undefined : '이 노드는 미리보기할 데이터가 없습니다'}
        />
        {showRunTab && (
          <TabButton
            active={activeTab === 'run'}
            onClick={() => setActiveTab('run')}
            label="실행 결과"
            disabled
            title="Phase 3 에서 활성화"
          />
        )}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto overflow-x-auto">
        {activeTab === 'info' && (
          <NodeInfoTab
            node={node}
            workflow={workflow}
            catalog={catalogEntry}
            warehouseTotalCache={warehouseTotalCache}
            editable={editable}
            onWorkflowUpdated={onWorkflowUpdated}
          />
        )}
        {activeTab === 'data' && dataTabEnabled && (
          <NodeDataTab
            node={node}
            workflow={workflow}
            instance={instanceForDataTab}
            pageContext={pageContext === 'instance' ? 'instance' : 'workflow'}
            onWarehouseTotalFetched={handleWarehouseTotalFetched}
          />
        )}
        {activeTab === 'data' && !dataTabEnabled && (
          <div className="px-4 py-6 text-xs text-gray-500 italic">
            이 노드는 미리보기할 데이터가 없습니다.
          </div>
        )}
        {activeTab === 'run' && (
          <div className="px-4 py-6 text-xs text-gray-500 italic">
            실행 결과 탭은 Phase 3 에서 구현됩니다.
          </div>
        )}
      </div>
    </div>
  );
}

// ─── TabButton ───────────────────────────────────────────────────────────

interface TabButtonProps {
  active: boolean;
  onClick: () => void;
  label: string;
  disabled?: boolean;
  title?: string;
}

function TabButton({ active, onClick, label, disabled, title }: TabButtonProps) {
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      title={title}
      className={[
        'px-4 py-2 text-xs font-medium transition-colors border-b-2 -mb-px',
        active
          ? 'text-sky-300 border-sky-400'
          : 'text-gray-400 border-transparent hover:text-gray-200',
        disabled ? 'opacity-40 cursor-not-allowed hover:text-gray-400' : 'cursor-pointer',
      ].join(' ')}
    >
      {label}
    </button>
  );
}

export default NodeInspectorDrawer;
