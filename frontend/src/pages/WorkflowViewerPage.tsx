/**
 * Workflow Viewer Page (`/workflows/:id`)
 *
 * Phase 3b 재구성 — 기존 FactoryPage 를 대체.
 * - 상단: 뒤로가기 · 이름 · 실행 버튼
 * - 본체: WorkflowViewerCanvas (dagre 자동 레이아웃, 편집 불가)
 * - 하단: 최근 인스턴스 목록 (최대 10건)
 *
 * 실행 버튼 UX:
 * - form-start 노드: 동적 입력 폼 모달
 * - api-start 노드: JSON payload 입력 (선택 사항, 바로 실행 가능)
 * - 그 외 트리거 없음: 빈 inputData로 즉시 실행
 *
 * 실행 성공(202) 시 /workflows/:id/instances/:iid 로 자동 이동.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ReactFlowProvider } from '@xyflow/react';
import type { Node } from '@xyflow/react';
import { workflowApi, nodeApi, type WorkflowExecution, type NodeCatalogEntry } from '../services/api';
import type { Workflow, WorkflowNodeInstance, AINode } from '../types';
import { WorkflowViewerCanvas } from '../components/workflow/WorkflowViewerCanvas';
import type { InspectedEdge } from '../components/workflow/WorkflowViewerCanvas';
import { NodeInspectorDrawer } from '../components/workflow/NodeInspectorDrawer';
import { AINodesContext } from '../components/workflow/FactoryNode';
import { StatusBadge } from '../components/common/StatusBadge';
import { EmptyState } from '../components/common/EmptyState';
import { useToast } from '../components/common/Toast';

// ─── Helpers ─────────────────────────────────────────────────

const TRIGGER_DEF_TYPES = new Set(['form-start', 'api-start']);

interface FormField {
  name: string;
  label: string;
  type: string;
  required: boolean;
  enum?: string[];
}

function extractFormFields(workflow: Workflow, triggerNode: WorkflowNodeInstance): FormField[] {
  // 1) config.fields 가 정의되어 있으면 우선
  const configFields = (triggerNode.config as any)?.fields;
  if (Array.isArray(configFields) && configFields.length > 0) {
    return configFields.map((f: any) => ({
      name: f.name,
      label: f.label || f.name,
      type: f.type || 'string',
      required: !!f.required,
    }));
  }

  // 2) BFS로 다운스트림 AI 노드의 inputSchema에서 자동 도출 (form-start 노드 config.fields 미정의 시 폴백)
  const edgesFromNode = new Map<string, string[]>();
  for (const conn of workflow.connections) {
    const list = edgesFromNode.get(conn.sourceNodeId) ?? [];
    list.push(conn.targetNodeId);
    edgesFromNode.set(conn.sourceNodeId, list);
  }
  const visited = new Set<string>([triggerNode.id]);
  const queue: string[] = [triggerNode.id];
  const fields: FormField[] = [];
  const seen = new Set<string>();

  while (queue.length > 0) {
    const curId = queue.shift()!;
    for (const nextId of edgesFromNode.get(curId) ?? []) {
      if (visited.has(nextId)) continue;
      visited.add(nextId);
      const nextNode = workflow.nodes.find((n) => n.id === nextId);
      if (!nextNode) continue;
      // 다운스트림 AI 노드의 inputMapping 키에서 필드명 도출
      const mapping = (nextNode.inputMapping || {}) as Record<string, string>;
      for (const [key, tpl] of Object.entries(mapping)) {
        if (seen.has(key)) continue;
        // {{prev.X}} 혹은 일반 리터럴 — 템플릿이 있으면 사용자 입력이 아님
        if (typeof tpl === 'string' && tpl.includes('{{')) continue;
        seen.add(key);
        fields.push({
          name: key,
          label: key,
          type: 'string',
          required: true,
        });
      }
      queue.push(nextId);
    }
  }
  return fields;
}

function formatRelative(iso?: string | null): string {
  if (!iso) return '-';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return '방금 전';
  if (mins < 60) return `${mins}분 전`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}시간 전`;
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

// ─── Run Modal ───────────────────────────────────────────────

interface RunModalProps {
  workflow: Workflow;
  triggerNode: WorkflowNodeInstance | null;
  onClose: () => void;
  onSubmit: (inputData: Record<string, unknown>) => void;
  submitting: boolean;
}

function RunModal({ workflow, triggerNode, onClose, onSubmit, submitting }: RunModalProps) {
  const isApiStart = triggerNode?.definitionType === 'api-start';
  const formFields = useMemo(
    () => (triggerNode && triggerNode.definitionType === 'form-start' ? extractFormFields(workflow, triggerNode) : []),
    [workflow, triggerNode],
  );

  const [values, setValues] = useState<Record<string, string>>({});
  const [jsonPayload, setJsonPayload] = useState('{}');
  const [jsonError, setJsonError] = useState<string | null>(null);

  const handleSubmit = () => {
    if (!triggerNode) {
      onSubmit({});
      return;
    }
    if (isApiStart) {
      try {
        const parsed = jsonPayload.trim() ? JSON.parse(jsonPayload) : {};
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          setJsonError('JSON 객체 형태여야 합니다 (예: {"key": "value"})');
          return;
        }
        setJsonError(null);
        onSubmit(parsed);
      } catch (e) {
        setJsonError(`JSON 파싱 실패: ${e instanceof Error ? e.message : String(e)}`);
      }
      return;
    }
    // form-start: required 검증
    const missing = formFields.filter((f) => f.required && !(values[f.name] || '').trim());
    if (missing.length > 0) {
      setJsonError(`필수 입력 누락: ${missing.map((f) => f.label).join(', ')}`);
      return;
    }
    setJsonError(null);
    const inputData: Record<string, unknown> = {};
    for (const f of formFields) {
      inputData[f.name] = values[f.name] ?? '';
    }
    onSubmit(inputData);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget && !submitting) onClose();
      }}
    >
      <div className="w-full max-w-lg rounded-xl bg-slate-900 border border-slate-700 shadow-2xl">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800">
          <div className="text-[10px] font-mono tracking-[0.25em] uppercase text-sky-400 mb-1">
            실행 입력
          </div>
          <h2 className="text-lg font-semibold text-slate-50">{workflow.name}</h2>
          {triggerNode && (
            <p className="text-xs text-slate-500 mt-0.5 font-mono">
              트리거: {triggerNode.definitionType} · {triggerNode.name}
            </p>
          )}
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-4 max-h-[60vh] overflow-auto">
          {!triggerNode && (
            <p className="text-sm text-slate-400">
              트리거 노드가 없어 빈 입력으로 즉시 실행됩니다.
            </p>
          )}

          {isApiStart && (
            <div>
              <label className="block text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-2">
                Payload (선택)
              </label>
              <textarea
                value={jsonPayload}
                onChange={(e) => setJsonPayload(e.target.value)}
                rows={8}
                className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-xs font-mono text-slate-200 focus:outline-none focus:border-sky-600"
                placeholder='{ "key": "value" }'
              />
              <p className="text-[11px] text-slate-500 mt-1.5">
                api-start 트리거의 payload JSON 을 입력합니다. 비워두면 빈 객체로 실행됩니다.
              </p>
            </div>
          )}

          {!isApiStart && triggerNode && (
            <>
              {formFields.length === 0 ? (
                <div className="rounded-lg border border-slate-700/60 bg-slate-800/40 px-4 py-3">
                  <p className="text-xs text-slate-400">
                    입력 필드가 정의되어 있지 않습니다. 빈 입력으로 실행됩니다.
                  </p>
                  <p className="text-[11px] text-slate-500 mt-1 font-mono">
                    config.fields 를 CLI 로 정의하면 이 화면에 폼이 나타납니다.
                  </p>
                </div>
              ) : (
                formFields.map((field) => (
                  <div key={field.name}>
                    <label className="block text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-1.5">
                      {field.label}
                      {field.required && <span className="text-rose-400 ml-1">*</span>}
                    </label>
                    <input
                      type={/token|password|secret|key/i.test(field.name) ? 'password' : 'text'}
                      value={values[field.name] || ''}
                      onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))}
                      className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-sm text-slate-200 focus:outline-none focus:border-sky-600"
                      placeholder={`${field.label} 입력...`}
                      autoFocus={formFields[0]?.name === field.name}
                    />
                  </div>
                ))
              )}
            </>
          )}

          {jsonError && (
            <div className="rounded-lg border border-rose-700/60 bg-rose-950/40 px-3 py-2 text-xs text-rose-300">
              {jsonError}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-800 flex items-center justify-between gap-3">
          <button
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200 transition-colors disabled:opacity-40"
          >
            취소
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="px-5 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:bg-sky-900 disabled:text-sky-400/50 text-white text-sm font-medium transition-colors inline-flex items-center gap-2"
          >
            {submitting ? (
              <>
                <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                실행 중...
              </>
            ) : (
              <>
                <span className="font-mono">▶</span>
                실행
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Instance List Section ───────────────────────────────────

function InstanceList({
  workflowId,
  instances,
  loading,
  onDelete,
}: {
  workflowId: string;
  instances: WorkflowExecution[];
  loading: boolean;
  onDelete: (executionId: string) => void;
}) {
  return (
    <div className="space-y-2">
      {loading ? (
        <>
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="h-14 rounded-lg bg-slate-900/40 border border-slate-800 animate-pulse"
            />
          ))}
        </>
      ) : instances.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-800 py-8 text-center text-sm text-slate-500">
          실행기록이 없습니다. 상단 실행 버튼으로 시작하세요.
        </div>
      ) : (
        instances.map((ex) => {
          const duration =
            ex.completedAt && ex.startedAt
              ? ((new Date(ex.completedAt).getTime() - new Date(ex.startedAt).getTime()) / 1000).toFixed(1)
              : null;
          return (
            <div
              key={ex.id}
              className="group flex items-center gap-4 px-4 py-3 rounded-lg border border-slate-800 bg-slate-900/30 hover:bg-slate-900/70 hover:border-slate-700 transition-all"
            >
              <Link
                to={`/workflows/${workflowId}/instances/${ex.id}`}
                className="flex items-center gap-4 flex-1 min-w-0"
              >
                <StatusBadge status={ex.status} size="xs" />
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] font-mono text-slate-300 truncate">{ex.id}</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">
                    {formatRelative(ex.createdAt)}
                    {duration !== null && (
                      <span className="ml-2 text-slate-600">· {duration}초</span>
                    )}
                    {ex.errorMessage && (
                      <span className="ml-2 text-rose-400 truncate">· {ex.errorMessage}</span>
                    )}
                  </div>
                </div>
                <span className="text-slate-600 group-hover:text-sky-400 transition-colors">
                  상세 →
                </span>
              </Link>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(ex.id);
                }}
                title="이 실행 기록 삭제"
                className="flex-shrink-0 p-1.5 rounded text-slate-600 hover:text-rose-400 hover:bg-rose-950/30 transition-colors opacity-0 group-hover:opacity-100"
              >
                🗑
              </button>
            </div>
          );
        })
      )}
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────

export default function WorkflowViewerPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();

  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [instances, setInstances] = useState<WorkflowExecution[]>([]);
  const [loadingWf, setLoadingWf] = useState(true);
  const [loadingIns, setLoadingIns] = useState(true);
  const [runModalOpen, setRunModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [aiNodes, setAiNodes] = useState<AINode[]>([]);
  const [catalog, setCatalog] = useState<NodeCatalogEntry[] | null>(null);
  const [selectedNode, setSelectedNode] = useState<Node<any> | null>(null);
  // [P-7] 엣지 선택 상태 — Page 가 mutual exclusion 책임
  const [selectedEdge, setSelectedEdge] = useState<InspectedEdge | null>(null);
  const hasAutoOpenedRef = useRef(false);

  // Load AI nodes for FactoryNode context
  useEffect(() => {
    nodeApi.list().then(setAiNodes).catch(() => setAiNodes([]));
  }, []);

  // Prefetch node catalog (1회) — drawer 정보 탭에서 사용
  useEffect(() => {
    let cancelled = false;
    nodeApi
      .getCatalog()
      .then((data) => {
        if (cancelled) return;
        setCatalog(data);
      })
      .catch(() => {
        if (cancelled) return;
        setCatalog([]); // 실패해도 null 유지하지 않고 빈 배열로 — drawer 가 catalogEntry==null 분기 처리
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // [P-7] 같은 노드 재클릭 시 토글 닫기, 다른 노드면 교체. 노드 선택 시 엣지 닫음.
  const handleNodeClick = useCallback((rfNode: Node<any>) => {
    setSelectedNode((prev) => (prev?.id === rfNode.id ? null : rfNode));
    setSelectedEdge(null);
  }, []);

  // [P-7] 엣지 선택 시 노드 드로어 닫음
  const handleEdgeSelect = useCallback((edge: InspectedEdge | null) => {
    setSelectedEdge(edge);
    if (edge) setSelectedNode(null);
  }, []);

  // Load workflow
  useEffect(() => {
    let cancelled = false;
    if (!id) return;
    async function load() {
      setLoadingWf(true);
      try {
        const wf = await workflowApi.get(id!);
        if (!cancelled) setWorkflow(wf);
      } catch (e) {
        toast.error(`업무자동화 조회 실패: ${e instanceof Error ? e.message : String(e)}`);
        if (!cancelled) setWorkflow(null);
      } finally {
        if (!cancelled) setLoadingWf(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [id, toast]);

  // Load instances
  const loadInstances = useCallback(async () => {
    if (!id) return;
    setLoadingIns(true);
    try {
      const data = await workflowApi.listInstances(id, 10);
      setInstances(data);
    } catch {
      setInstances([]);
    } finally {
      setLoadingIns(false);
    }
  }, [id]);

  // Delete single execution from list
  const handleDeleteInstance = useCallback(async (executionId: string) => {
    const confirmed = window.confirm(
      `실행기록 ${executionId}을 영구 삭제하시겠습니까?`
    );
    if (!confirmed) return;
    try {
      await workflowApi.deleteExecution(executionId);
      toast.success('실행기록이 삭제되었습니다.');
      await loadInstances();
    } catch (e) {
      toast.error(`삭제 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [loadInstances, toast]);

  useEffect(() => {
    loadInstances();
  }, [loadInstances]);

  // Auto-open run modal if ?run=1 (from dashboard 실행 버튼)
  useEffect(() => {
    if (!loadingWf && workflow && !hasAutoOpenedRef.current && searchParams.get('run') === '1') {
      hasAutoOpenedRef.current = true;
      setRunModalOpen(true);
      // URL 정리
      const sp = new URLSearchParams(searchParams);
      sp.delete('run');
      setSearchParams(sp, { replace: true });
    }
  }, [loadingWf, workflow, searchParams, setSearchParams]);

  // Identify trigger node (form-start / api-start)
  const triggerNode = useMemo<WorkflowNodeInstance | null>(() => {
    if (!workflow) return null;
    return (
      workflow.nodes.find((n) => TRIGGER_DEF_TYPES.has((n.definitionType || '').toLowerCase())) ?? null
    );
  }, [workflow]);

  const handleRun = async (inputData: Record<string, unknown>) => {
    if (!id) return;
    setSubmitting(true);
    try {
      // 우선 Phase 2b /run 엔드포인트(202) 시도 — 실패하면 레거시 /execute 폴백
      let instanceId: string | undefined;
      try {
        const runResp = await workflowApi.run(id, inputData);
        instanceId = runResp.instanceId;
      } catch (err) {
        // 404 or 405 — fallback to legacy execute endpoint
        try {
          const legacy = await workflowApi.execute(id, inputData);
          instanceId = legacy.id;
        } catch {
          throw err;
        }
      }

      if (!instanceId) throw new Error('인스턴스 ID를 받지 못했습니다');

      toast.success('실행 시작 — 상세 페이지로 이동합니다');
      setRunModalOpen(false);
      navigate(`/workflows/${id}/instances/${instanceId}`);
    } catch (e) {
      toast.error(`실행 실패: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSubmitting(false);
    }
  };

  // Render states
  if (loadingWf) {
    return (
      <div className="h-full flex items-center justify-center bg-slate-950">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-slate-700 border-t-sky-500 rounded-full animate-spin" />
          <span className="text-xs text-slate-500 font-mono">업무자동화 로드 중...</span>
        </div>
      </div>
    );
  }

  if (!workflow) {
    return (
      <div className="h-full bg-slate-950 p-6">
        <EmptyState
          icon={'⚠'}
          title="업무자동화를 찾을 수 없습니다"
          description="요청하신 ID에 해당하는 업무자동화가 존재하지 않거나 삭제되었을 수 있습니다."
          action={
            <Link
              to="/workflows"
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-sm text-slate-200"
            >
              목록으로 돌아가기
            </Link>
          }
        />
      </div>
    );
  }

  const canRun = workflow.nodes.length > 0;

  return (
    <div className="h-full flex flex-col bg-slate-950">
      {/* Header */}
      <header className="flex-shrink-0 border-b border-slate-800 bg-slate-950/80 backdrop-blur">
        <div className="w-full px-6 py-4 flex items-center gap-4">
          <Link
            to="/workflows"
            className="flex-shrink-0 p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 transition-colors"
            title="목록으로"
          >
            <span className="text-lg">←</span>
          </Link>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <div className="text-[10px] font-mono tracking-[0.2em] uppercase text-slate-500">
                업무자동화 상세
              </div>
              <StatusBadge status={workflow.nodes.length > 0 ? 'active' : 'draft'} variant="workflow" size="xs" />
            </div>
            <h1 className="text-xl font-semibold text-slate-50 truncate">{workflow.name}</h1>
            {workflow.description && (
              <p className="text-xs text-slate-500 mt-0.5 truncate">{workflow.description}</p>
            )}
          </div>
          <div className="flex-shrink-0 flex items-center gap-2">
            <span className="text-[11px] font-mono text-slate-500 hidden md:inline">
              {workflow.id}
            </span>
            <button
              onClick={() => setRunModalOpen(true)}
              disabled={!canRun}
              className="px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:bg-slate-800 disabled:text-slate-600 text-white text-sm font-semibold transition-all shadow-lg shadow-sky-900/40 inline-flex items-center gap-2"
            >
              <span className="font-mono">▶</span>
              실행하기
            </button>
          </div>
        </div>
      </header>

      {/* Canvas */}
      <div className="flex-shrink-0 relative" style={{ height: '55vh', minHeight: 320 }}>
        {workflow.nodes.length === 0 ? (
          <EmptyState
            icon={'∅'}
            title="노드가 없습니다"
            description="CLI로 노드를 추가하세요."
          />
        ) : (
          <AINodesContext.Provider value={aiNodes}>
            <ReactFlowProvider>
              <div className="absolute inset-0 flex">
                <WorkflowViewerCanvas
                  workflow={workflow}
                  onNodeClick={handleNodeClick}
                  onPaneClick={() => { setSelectedNode(null); setSelectedEdge(null); }}
                  selectedEdge={selectedEdge}
                  onEdgeSelect={handleEdgeSelect}
                />
              </div>
              <NodeInspectorDrawer
                node={selectedNode}
                workflow={workflow}
                catalog={catalog}
                onClose={() => setSelectedNode(null)}
              />
            </ReactFlowProvider>
          </AINodesContext.Provider>
        )}
      </div>

      {/* Instance list */}
      <section className="flex-1 min-h-0 overflow-auto border-t border-slate-800 bg-slate-950">
        <div className="w-full px-6 py-6">
          <div className="flex items-baseline justify-between mb-3">
            <h2 className="text-sm font-mono tracking-[0.2em] uppercase text-slate-400">
              최근 실행기록
            </h2>
            <button
              onClick={loadInstances}
              className="text-xs font-mono text-slate-500 hover:text-sky-400 transition-colors"
            >
              새로고침 ↻
            </button>
          </div>
          <InstanceList workflowId={workflow.id} instances={instances} loading={loadingIns} onDelete={handleDeleteInstance} />
        </div>
      </section>

      {/* Run modal */}
      {runModalOpen && (
        <RunModal
          workflow={workflow}
          triggerNode={triggerNode}
          submitting={submitting}
          onClose={() => setRunModalOpen(false)}
          onSubmit={handleRun}
        />
      )}
    </div>
  );
}
