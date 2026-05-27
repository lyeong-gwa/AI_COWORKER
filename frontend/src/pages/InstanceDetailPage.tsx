/**
 * Instance Detail Page (`/workflows/:id/instances/:iid`)
 *
 * Phase 3b 신설 — SSE로 인스턴스 진행 상황을 라이브로 스트리밍.
 *
 * 이벤트 타입 (backend: warehouse.stream_instance):
 *   - stream_open        : 구독 확인
 *   - status             : 실행 전체 status 변화 (queued → running → completed/failed)
 *   - node_start         : 노드 시작 (pending/running)
 *   - node_complete      : 노드 완료 (output 포함)
 *   - node_error         : 노드 실패
 *   - execution_complete : 실행 종료 (최종 output/error 포함) → 스트림 종료
 *
 * 폴백: SSE 실패 시 3초 간격 폴링. navigator.onLine === false 이면 안내.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ReactFlowProvider } from '@xyflow/react';
import type { Node } from '@xyflow/react';
import {
  warehouseApi,
  workflowApi,
  nodeApi,
  factoryApi,
  type WorkflowExecution,
  type WarehouseInstanceEntry,
  type NodeCatalogEntry,
} from '../services/api';
import type { Workflow, AINode } from '../types';
import { WorkflowViewerCanvas } from '../components/workflow/WorkflowViewerCanvas';
import type { InspectedEdge } from '../components/workflow/WorkflowViewerCanvas';
import { NodeInspectorDrawer } from '../components/workflow/NodeInspectorDrawer';
import { AINodesContext } from '../components/workflow/FactoryNode';
import { StatusBadge } from '../components/common/StatusBadge';
import { useToast } from '../components/common/Toast';
import { StyledMarkdown } from '../components/common/StyledMarkdown';
import { InstanceExecutionContext } from '../contexts/InstanceExecutionContext';

// ─── Types ───────────────────────────────────────────────────

interface NodeProgress {
  status: string;
  output?: unknown;
  error?: string;
}

interface TimelineEvent {
  id: string;
  at: number; // epoch ms
  kind: 'open' | 'status' | 'node_start' | 'node_complete' | 'node_error' | 'complete' | 'error';
  nodeId?: string;
  status?: string;
  message?: string;
}

// ─── Helpers ─────────────────────────────────────────────────

function formatClock(ms: number): string {
  const d = new Date(ms);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
}

function formatElapsed(startIso?: string | null, endIso?: string | null): string {
  if (!startIso) return '00:00';
  const start = new Date(startIso).getTime();
  const end = endIso ? new Date(endIso).getTime() : Date.now();
  const ms = Math.max(0, end - start);
  const totalSec = Math.floor(ms / 1000);
  const hrs = Math.floor(totalSec / 3600);
  const mins = Math.floor((totalSec % 3600) / 60);
  const secs = totalSec % 60;
  if (hrs > 0) return `${hrs}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function makeEventId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function getEntryTitle(e: WarehouseInstanceEntry): string {
  const d = e.data;
  if (typeof d.prTitle === 'string' && d.prTitle) return d.prTitle;
  if (typeof d.title === 'string' && d.title) return d.title;
  if (d.prNumber != null) return `PR #${d.prNumber}`;
  return e.id;
}

// ─── Node Row ────────────────────────────────────────────────

interface NodeRowProps {
  nodeId: string;
  nodeName: string;
  defType: string;
  progress?: NodeProgress;
}

function NodeRow({ nodeId, nodeName, defType, progress }: NodeRowProps) {
  const [expanded, setExpanded] = useState(false);
  const [jsonOpen, setJsonOpen] = useState(false);
  const status = progress?.status || 'pending';

  const outputPreview = useMemo(() => {
    if (progress?.output == null) return null;
    try {
      const json = JSON.stringify(progress.output);
      if (json.length > 200) return json.slice(0, 200) + '…';
      return json;
    } catch {
      return String(progress.output);
    }
  }, [progress?.output]);

  const borderTone = {
    pending: 'border-slate-800',
    running: 'border-sky-600/60 shadow-[0_0_12px_rgba(56,189,248,0.15)]',
    completed: 'border-emerald-700/50',
    failed: 'border-rose-700/60',
    cancelled: 'border-zinc-700/60',
    skipped: 'border-slate-800',
    not_executed: 'border-slate-800/50',
  }[status] || 'border-slate-800';

  const isNotExecuted = status === 'not_executed';

  return (
    <>
      <div className={`rounded-lg border bg-slate-900/40 transition-all ${borderTone}${isNotExecuted ? ' opacity-60' : ''}`}>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="w-full px-4 py-3 flex items-center gap-3 text-left"
        >
          <StatusBadge status={status} size="xs" />
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-2 min-w-0">
              <span className="text-sm font-semibold text-slate-100 truncate">{nodeName}</span>
              <span className="text-[10px] font-mono text-slate-500 truncate hidden md:inline">
                {defType}
              </span>
            </div>
            <div className="text-[11px] font-mono text-slate-600 truncate">{nodeId}</div>
          </div>
          {progress?.error && (
            <span className="flex-shrink-0 text-[11px] text-rose-400 font-mono truncate max-w-[200px]">
              {progress.error}
            </span>
          )}
          <span className={`text-slate-600 transition-transform ${expanded ? 'rotate-90' : ''}`}>
            ›
          </span>
        </button>

        {expanded && (
          <div className="px-4 pb-3 space-y-2 border-t border-slate-800/60 pt-3">
            {isNotExecuted ? (
              <div className="rounded-md border border-slate-700/40 bg-slate-950/40 px-3 py-2.5 flex items-start gap-2">
                <span className="text-slate-600 text-base mt-0.5 flex-shrink-0">⊘</span>
                <p className="text-xs text-slate-500 leading-relaxed">
                  이 노드는 실행되지 않았습니다. 업스트림 분기에서 차단(예: sorter not_exists 미매칭)되어 다운스트림 처리가 생략되었습니다.
                </p>
              </div>
            ) : (
              <>
                {progress?.error && (
                  <div className="rounded-md border border-rose-700/40 bg-rose-950/30 px-3 py-2 text-xs text-rose-300 font-mono whitespace-pre-wrap">
                    {progress.error}
                  </div>
                )}
                {outputPreview ? (
                  <div className="rounded-md bg-slate-950/60 border border-slate-800 px-3 py-2">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">
                        Output
                      </span>
                      <button
                        onClick={() => setJsonOpen(true)}
                        className="text-[10px] font-mono text-sky-400 hover:text-sky-300 uppercase tracking-wider"
                      >
                        JSON 열기 →
                      </button>
                    </div>
                    <pre className="text-[11px] text-slate-300 font-mono whitespace-pre-wrap break-all">
                      {outputPreview}
                    </pre>
                  </div>
                ) : (
                  <div className="text-xs text-slate-500 italic">
                    {status === 'pending'
                      ? '대기 중 — 아직 실행되지 않았습니다.'
                      : status === 'running'
                        ? '실행 중 — 결과 대기 중...'
                        : '출력 없음'}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {jsonOpen && progress?.output != null && (
        <JsonModal
          title={`${nodeName} · Output`}
          payload={progress.output}
          onClose={() => setJsonOpen(false)}
        />
      )}
    </>
  );
}

// ─── JSON Modal ──────────────────────────────────────────────

function JsonModal({
  title,
  payload,
  onClose,
}: {
  title: string;
  payload: unknown;
  onClose: () => void;
}) {
  const pretty = useMemo(() => {
    try {
      return JSON.stringify(payload, null, 2);
    } catch {
      return String(payload);
    }
  }, [payload]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-3xl max-h-[80vh] flex flex-col rounded-xl bg-slate-900 border border-slate-700 shadow-2xl">
        <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
          <div className="flex items-center gap-2">
            <button
              onClick={() => navigator.clipboard?.writeText(pretty)}
              className="text-[11px] font-mono text-slate-400 hover:text-sky-300 uppercase tracking-wider"
            >
              복사
            </button>
            <button onClick={onClose} className="text-slate-400 hover:text-slate-100 text-xl px-2">
              ✕
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-auto p-4">
          <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap break-all">
            {pretty}
          </pre>
        </div>
      </div>
    </div>
  );
}

// ─── Timeline Strip ──────────────────────────────────────────

function TimelineStrip({ events }: { events: TimelineEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="text-xs text-slate-600 italic px-1">아직 수신된 이벤트가 없습니다.</div>
    );
  }
  return (
    <div className="space-y-1 max-h-48 overflow-auto pr-2">
      {events.map((ev) => {
        const tone =
          ev.kind === 'node_complete' || ev.kind === 'complete'
            ? 'text-emerald-300'
            : ev.kind === 'node_error' || ev.kind === 'error'
              ? 'text-rose-300'
              : ev.kind === 'node_start' || ev.kind === 'status'
                ? 'text-sky-300'
                : 'text-slate-400';
        return (
          <div key={ev.id} className="flex items-baseline gap-3 text-[11px] font-mono">
            <span className="text-slate-600 tabular-nums">{formatClock(ev.at)}</span>
            <span className={`uppercase tracking-wider ${tone}`}>{ev.kind}</span>
            {ev.nodeId && <span className="text-slate-500 truncate">{ev.nodeId}</span>}
            {ev.status && <span className="text-slate-400">· {ev.status}</span>}
            {ev.message && <span className="text-slate-500 truncate">· {ev.message}</span>}
          </div>
        );
      })}
    </div>
  );
}

// ─── Warehouse Entries Panel ─────────────────────────────────

/**
 * Per-defType visual style tokens.
 * icon      — emoji shown in group header
 * accent    — Tailwind class for the 4px left bar color (border-{color})
 * headerBg  — header background tint
 * itemBg    — item row background tint (subtle)
 * itemBorder — item left border color when NOT selected (border-l-{color})
 * labelColor — group name text color
 */
interface NodeTypeStyle {
  icon: string;
  accent: string;      // e.g. 'border-amber-500'
  headerBg: string;   // e.g. 'bg-amber-950/40'
  itemBg: string;     // e.g. 'bg-amber-950/10'
  itemBorder: string; // e.g. 'border-l-amber-700/50'
  labelColor: string; // e.g. 'text-amber-200'
}

const NODE_TYPE_STYLE: Record<string, NodeTypeStyle> = {
  'form-start':         { icon: '📋', accent: 'border-amber-500',   headerBg: 'bg-amber-950/50',   itemBg: 'bg-amber-950/10',   itemBorder: 'border-l-amber-600/60',   labelColor: 'text-amber-200' },
  'api-start':          { icon: '🚀', accent: 'border-teal-500',    headerBg: 'bg-teal-950/50',    itemBg: 'bg-teal-950/10',    itemBorder: 'border-l-teal-600/60',    labelColor: 'text-teal-200'  },
  'ai-custom':          { icon: '🤖', accent: 'border-blue-500',    headerBg: 'bg-blue-950/50',    itemBg: 'bg-blue-950/10',    itemBorder: 'border-l-blue-600/60',    labelColor: 'text-blue-200'  },
  'ai-api-router':      { icon: '🤖', accent: 'border-purple-500',  headerBg: 'bg-purple-950/50',  itemBg: 'bg-purple-950/10',  itemBorder: 'border-l-purple-600/60',  labelColor: 'text-purple-200'},
  'sorter':             { icon: '🔀', accent: 'border-violet-500',  headerBg: 'bg-violet-950/50',  itemBg: 'bg-violet-950/10',  itemBorder: 'border-l-violet-600/60',  labelColor: 'text-violet-200'},
  'unpacker':           { icon: '📤', accent: 'border-rose-500',    headerBg: 'bg-rose-950/50',    itemBg: 'bg-rose-950/10',    itemBorder: 'border-l-rose-600/60',    labelColor: 'text-rose-200'  },
  'mapper':             { icon: '🔗', accent: 'border-indigo-500',  headerBg: 'bg-indigo-950/50',  itemBg: 'bg-indigo-950/10',  itemBorder: 'border-l-indigo-600/60',  labelColor: 'text-indigo-200'},
  'api-call':           { icon: '🌐', accent: 'border-cyan-500',    headerBg: 'bg-cyan-950/50',    itemBg: 'bg-cyan-950/10',    itemBorder: 'border-l-cyan-600/60',    labelColor: 'text-cyan-200'  },
  'knowledge':          { icon: '📚', accent: 'border-indigo-400',  headerBg: 'bg-indigo-950/50',  itemBg: 'bg-indigo-950/10',  itemBorder: 'border-l-indigo-500/60',  labelColor: 'text-indigo-200'},
  'instance-db-insert': { icon: '📥', accent: 'border-teal-400',    headerBg: 'bg-teal-950/50',    itemBg: 'bg-teal-950/10',    itemBorder: 'border-l-teal-500/60',    labelColor: 'text-teal-200'  },
  'instance-db-lookup': { icon: '🔍', accent: 'border-cyan-400',    headerBg: 'bg-cyan-950/50',    itemBg: 'bg-cyan-950/10',    itemBorder: 'border-l-cyan-500/60',    labelColor: 'text-cyan-200'  },
  'result':             { icon: '📦', accent: 'border-emerald-500', headerBg: 'bg-emerald-950/50', itemBg: 'bg-emerald-950/10', itemBorder: 'border-l-emerald-600/60', labelColor: 'text-emerald-200'},
  'markdown-viewer':    { icon: '📄', accent: 'border-slate-400',   headerBg: 'bg-slate-800/70',   itemBg: 'bg-slate-800/20',   itemBorder: 'border-l-slate-500/60',   labelColor: 'text-slate-200' },
};

const DEFAULT_NODE_STYLE: NodeTypeStyle = {
  icon: '⚙️',
  accent: 'border-slate-500',
  headerBg: 'bg-slate-800/60',
  itemBg: 'bg-slate-800/10',
  itemBorder: 'border-l-slate-600/60',
  labelColor: 'text-slate-200',
};

function getNodeTypeStyle(defType?: string): NodeTypeStyle {
  if (!defType) return DEFAULT_NODE_STYLE;
  return NODE_TYPE_STYLE[defType] ?? DEFAULT_NODE_STYLE;
}

interface WarehouseEntriesPanelProps {
  entries: WarehouseInstanceEntry[];
  workflow: Workflow;
  instanceId: string;
  selectedEntryId: string | null;
  onSelectEntry: (id: string) => void;
  onEntriesChange: (entries: WarehouseInstanceEntry[]) => void;
}

function WarehouseEntriesPanel({
  entries,
  workflow,
  instanceId,
  selectedEntryId,
  onSelectEntry,
  onEntriesChange,
}: WarehouseEntriesPanelProps) {
  const { toast } = useToast();
  const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002/api/v1';

  // Per-group collapse state — Set of collapsed nodeInstanceIds (default: all expanded)
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  const toggleGroup = useCallback((nodeInstanceId: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(nodeInstanceId)) {
        next.delete(nodeInstanceId);
      } else {
        next.add(nodeInstanceId);
      }
      return next;
    });
  }, []);

  // Build nodeId → node name lookup from workflow
  const nodeNameMap = useMemo<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    for (const n of workflow.nodes) {
      map[n.id] = n.name;
    }
    return map;
  }, [workflow.nodes]);

  // Build nodeId → definitionType lookup
  const nodeDefTypeMap = useMemo<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    for (const n of workflow.nodes) {
      if (n.definitionType) map[n.id] = n.definitionType;
    }
    return map;
  }, [workflow.nodes]);

  // Group entries by nodeInstanceId — include defType for styling
  const groups = useMemo<Array<{
    nodeInstanceId: string;
    nodeName: string;
    defType: string | undefined;
    items: WarehouseInstanceEntry[];
    sorterHandleGroups?: Array<{
      handle: string;
      label: string;
      items: WarehouseInstanceEntry[];
      color: string;
    }>;
  }>>(() => {
    const groupMap = new Map<string, WarehouseInstanceEntry[]>();
    for (const e of entries) {
      const g = groupMap.get(e.nodeInstanceId) ?? [];
      g.push(e);
      groupMap.set(e.nodeInstanceId, g);
    }
    return Array.from(groupMap.entries()).map(([nodeInstanceId, items]) => {
      const defType = nodeDefTypeMap[nodeInstanceId];
      const result: any = {
        nodeInstanceId,
        nodeName: nodeNameMap[nodeInstanceId] ?? nodeInstanceId,
        defType,
        items,
      };

      // If this is a sorter node, subdivide by __sorterHandle
      if (defType === 'sorter') {
        const handleGroups = new Map<string, WarehouseInstanceEntry[]>();
        for (const item of items) {
          const handle = (item.data as Record<string, unknown>)?.__sorterHandle as string | undefined || 'legacy';
          const group = handleGroups.get(handle) ?? [];
          group.push(item);
          handleGroups.set(handle, group);
        }

        // Sort handles: put 'default' last, others alphabetically
        const sortedHandles = Array.from(handleGroups.entries()).sort(([a], [b]) => {
          if (a === 'default') return 1;
          if (b === 'default') return -1;
          return a.localeCompare(b);
        });

        result.sorterHandleGroups = sortedHandles.map(([handle, groupItems]) => {
          const isDefault = handle === 'default';
          return {
            handle,
            label: isDefault ? '차단' : '통과',
            items: groupItems,
            color: isDefault ? 'slate' : 'cyan',
          };
        });
      }

      return result;
    });
  }, [entries, nodeNameMap, nodeDefTypeMap]);

  const refreshEntries = useCallback(async () => {
    try {
      const updated = await warehouseApi.listInstanceEntries(instanceId);
      onEntriesChange(updated);
    } catch {
      // ignore
    }
  }, [instanceId, onEntriesChange]);

  const handleDeleteEntry = useCallback(async (nodeInstanceId: string, entryId: string) => {
    try {
      await factoryApi.deleteEntries(nodeInstanceId, [entryId]);
      await refreshEntries();
      toast.success('항목이 삭제되었습니다.');
    } catch (err) {
      toast.error(`삭제 실패: ${err instanceof Error ? err.message : String(err)}`);
    }
  }, [refreshEntries, toast]);

  const handleClearGroup = useCallback(async (nodeInstanceId: string, entryIds: string[]) => {
    const confirmed = window.confirm(`이 노드의 결과 ${entryIds.length}건을 모두 삭제하시겠습니까?`);
    if (!confirmed) return;
    try {
      await factoryApi.deleteEntries(nodeInstanceId, entryIds);
      await refreshEntries();
      toast.success(`${entryIds.length}건 삭제 완료.`);
    } catch (err) {
      toast.error(`삭제 실패: ${err instanceof Error ? err.message : String(err)}`);
    }
  }, [refreshEntries, toast]);

  const selectedEntry = useMemo(
    () => entries.find((e) => e.id === selectedEntryId) ?? null,
    [entries, selectedEntryId],
  );

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-4">
      {/* Left: grouped list */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/30 overflow-hidden flex flex-col">
        <div className="px-4 py-2.5 border-b border-slate-800/60 flex items-center justify-between">
          <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">
            결과 목록
          </span>
          <span className="text-[10px] font-mono text-slate-600">{entries.length}건</span>
        </div>
        <div className="flex-1 overflow-auto">
          {groups.map((group, idx) => {
            const style = getNodeTypeStyle(group.defType);
            const isCollapsed = collapsedGroups.has(group.nodeInstanceId);
            return (
              <div
                key={group.nodeInstanceId}
                className={`${idx > 0 ? 'mt-1' : ''} mb-1 mx-1 rounded-lg overflow-hidden border border-slate-800/60`}
              >
                {/* Group header row — toggle button + clear button as siblings (avoid nested <button>) */}
                <div
                  className={`w-full flex items-center gap-0 border-l-4 ${style.accent} ${style.headerBg}`}
                >
                  <button
                    type="button"
                    onClick={() => toggleGroup(group.nodeInstanceId)}
                    aria-expanded={!isCollapsed}
                    className="flex-1 min-w-0 flex items-center gap-0 text-left hover:brightness-110 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-slate-400"
                  >
                    {/* Icon + label area */}
                    <div className="flex items-center gap-2 flex-1 min-w-0 px-3 py-2.5">
                      <span className="text-base leading-none flex-shrink-0" aria-hidden="true">
                        {style.icon}
                      </span>
                      <div className="flex-1 min-w-0">
                        <span className={`text-xs font-semibold truncate block ${style.labelColor}`}>
                          {group.nodeName}
                        </span>
                        <span className="text-[10px] font-mono text-slate-500 truncate block">
                          {group.defType ?? ''} · {group.items.length}건
                        </span>
                      </div>
                    </div>
                    {/* Chevron */}
                    <span
                      className={`flex-shrink-0 mr-2 text-slate-400 transition-transform duration-200 ${isCollapsed ? '' : 'rotate-90'}`}
                      aria-hidden="true"
                    >
                      ›
                    </span>
                  </button>
                  {/* Clear button — sibling of toggle, no nested-button hydration error */}
                  <button
                    type="button"
                    onClick={() => handleClearGroup(group.nodeInstanceId, group.items.map((i) => i.id))}
                    className="flex-shrink-0 mr-2 px-2 py-1 rounded border border-slate-700/60 bg-rose-950/20 text-[10px] font-mono text-rose-400/80 hover:text-rose-300 hover:border-rose-700/60 hover:bg-rose-950/40 transition-colors"
                    title="이 노드의 모든 결과 삭제"
                    aria-label={`${group.nodeName} 결과 전체 삭제`}
                  >
                    🗑
                  </button>
                </div>

                {/* Entry rows — hidden when collapsed */}
                {!isCollapsed && (
                  <div className={`${style.itemBg} border-t border-slate-800/40`}>
                    {/* Sorter handle grouping (if applicable) */}
                    {group.sorterHandleGroups ? (
                      <>
                        {group.sorterHandleGroups.map((handleGroup) => {
                          const isDefaultHandle = handleGroup.handle === 'default';
                          const headerBgClass = isDefaultHandle ? 'bg-slate-800/30' : 'bg-cyan-900/20';
                          const labelColorClass = isDefaultHandle ? 'text-slate-400' : 'text-cyan-300';

                          return (
                            <div key={handleGroup.handle}>
                              {/* Sub-header for handle group — always show */}
                              <div className={`px-3 py-2 text-[10px] font-mono uppercase tracking-wider ${headerBgClass} border-t border-slate-700/40`}>
                                <span className={labelColorClass}>
                                  {handleGroup.handle}
                                </span>
                                <span className={`ml-2 font-semibold ${labelColorClass}`}>
                                  {handleGroup.items.length}건
                                </span>
                                <span className={`ml-2 text-[9px] ${isDefaultHandle ? 'text-slate-500' : 'text-cyan-400/60'}`}>
                                  ({handleGroup.label})
                                </span>
                              </div>

                              {/* Entries in this handle group */}
                              {handleGroup.items.map((e) => {
                                const isSelected = selectedEntryId === e.id;
                                const time = e.createdAt
                                  ? new Date(e.createdAt).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                                  : '-';
                                return (
                                  <div
                                    key={e.id}
                                    role="button"
                                    tabIndex={0}
                                    onClick={() => onSelectEntry(e.id)}
                                    onKeyDown={(ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); onSelectEntry(e.id); } }}
                                    className={`flex items-center gap-2 pl-8 pr-3 py-2 cursor-pointer transition-colors border-l-2 ${
                                      isSelected
                                        ? 'bg-cyan-900/40 border-l-cyan-500'
                                        : `${style.itemBorder} hover:bg-slate-800/50`
                                    }`}
                                  >
                                    <div className="flex-1 min-w-0">
                                      <div className={`text-xs truncate ${isSelected ? 'text-cyan-100 font-medium' : 'text-slate-300'}`}>
                                        {getEntryTitle(e)}
                                      </div>
                                      <div className="text-[10px] font-mono text-slate-500">{time}</div>
                                    </div>
                                    <button
                                      type="button"
                                      onClick={(ev) => {
                                        ev.stopPropagation();
                                        handleDeleteEntry(e.nodeInstanceId, e.id);
                                      }}
                                      className="flex-shrink-0 p-1 rounded text-slate-600 hover:text-rose-400 hover:bg-rose-950/30 transition-colors"
                                      title="이 항목 삭제"
                                      aria-label="항목 삭제"
                                    >
                                      🗑
                                    </button>
                                  </div>
                                );
                              })}
                            </div>
                          );
                        })}
                      </>
                    ) : (
                      /* Regular (non-sorter) entry display */
                      <>
                        {group.items.map((e) => {
                          const isSelected = selectedEntryId === e.id;
                          const time = e.createdAt
                            ? new Date(e.createdAt).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                            : '-';
                          return (
                            <div
                              key={e.id}
                              role="button"
                              tabIndex={0}
                              onClick={() => onSelectEntry(e.id)}
                              onKeyDown={(ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); onSelectEntry(e.id); } }}
                              className={`flex items-center gap-2 pl-8 pr-3 py-2 cursor-pointer transition-colors border-l-2 ${
                                isSelected
                                  ? 'bg-cyan-900/40 border-l-cyan-500'
                                  : `${style.itemBorder} hover:bg-slate-800/50`
                              }`}
                            >
                              <div className="flex-1 min-w-0">
                                <div className={`text-xs truncate ${isSelected ? 'text-cyan-100 font-medium' : 'text-slate-300'}`}>
                                  {getEntryTitle(e)}
                                </div>
                                <div className="text-[10px] font-mono text-slate-500">{time}</div>
                              </div>
                              <button
                                type="button"
                                onClick={(ev) => {
                                  ev.stopPropagation();
                                  handleDeleteEntry(e.nodeInstanceId, e.id);
                                }}
                                className="flex-shrink-0 p-1 rounded text-slate-600 hover:text-rose-400 hover:bg-rose-950/30 transition-colors"
                                title="이 항목 삭제"
                                aria-label="항목 삭제"
                              >
                                🗑
                              </button>
                            </div>
                          );
                        })}
                      </>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Right: detail panel */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/30 overflow-hidden flex flex-col min-h-[300px]">
        {selectedEntry == null ? (
          <div className="flex-1 flex items-center justify-center">
            <span className="text-sm text-slate-600 font-mono">좌측에서 결과를 선택하세요</span>
          </div>
        ) : (
          <>
            {/* Metadata bar */}
            <div className="flex items-start flex-wrap gap-x-4 gap-y-1 px-4 py-3 border-b border-slate-800/60 bg-slate-950/40">
              <div className="min-w-0 flex flex-wrap items-center gap-3 flex-1">
                <span className="text-[10px] font-mono text-slate-500 truncate">
                  <span className="text-slate-600">ID</span> {selectedEntry.id}
                </span>
                <span className="text-[10px] font-mono text-slate-500 truncate">
                  <span className="text-slate-600">노드</span>{' '}
                  {nodeNameMap[selectedEntry.nodeInstanceId] ?? selectedEntry.nodeInstanceId}
                </span>
                {selectedEntry.createdAt && (
                  <span className="text-[10px] font-mono text-slate-500">
                    <span className="text-slate-600">생성</span>{' '}
                    {new Date(selectedEntry.createdAt).toLocaleString('ko-KR')}
                  </span>
                )}
              </div>
              <a
                href={`${API_BASE}/warehouse/entries/${selectedEntry.id}/report.md?save=true&download=true`}
                download
                className="flex-shrink-0 inline-flex items-center gap-1 px-2.5 py-1.5 rounded border border-slate-700 bg-slate-900/60 text-[11px] font-mono text-slate-300 hover:text-slate-100 hover:border-slate-500 hover:bg-slate-800/60 transition-colors"
              >
                📥 다운로드
              </a>
            </div>
            {/* Content body */}
            <div className="flex-1 max-h-[600px] overflow-auto p-4">
              <WarehouseEntryBody entry={selectedEntry} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ─── Warehouse Entry Body ────────────────────────────────────

function WarehouseEntryBody({ entry }: { entry: WarehouseInstanceEntry }) {
  if (typeof entry.data.markdown === 'string') {
    return (
      <StyledMarkdown variant="comment" className="text-sm text-slate-200">
        {entry.data.markdown}
      </StyledMarkdown>
    );
  }
  if (typeof entry.data.data === 'string') {
    return (
      <pre className="whitespace-pre-wrap text-sm text-slate-200 leading-relaxed font-sans">
        {entry.data.data}
      </pre>
    );
  }
  if (typeof entry.data.response === 'string') {
    return (
      <pre className="whitespace-pre-wrap text-sm text-slate-200 leading-relaxed font-sans">
        {entry.data.response}
      </pre>
    );
  }
  // JSON fallback with simple key/value colorization
  const pretty = (() => {
    try { return JSON.stringify(entry.data, null, 2); } catch { return String(entry.data); }
  })();
  return (
    <pre className="text-xs font-mono whitespace-pre-wrap break-words leading-relaxed text-slate-300">
      {pretty}
    </pre>
  );
}

// ─── Page ────────────────────────────────────────────────────

export default function InstanceDetailPage() {
  const { id: workflowId, iid: instanceId } = useParams<{ id: string; iid: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [instance, setInstance] = useState<(WorkflowExecution & { instanceId: string }) | null>(null);
  const [nodeProgress, setNodeProgress] = useState<Record<string, NodeProgress>>({});
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [entries, setEntries] = useState<WarehouseInstanceEntry[]>([]);
  const [connection, setConnection] = useState<'connecting' | 'sse' | 'polling' | 'done' | 'offline'>(
    'connecting',
  );
  const [loading, setLoading] = useState(true);
  const [elapsed, setElapsed] = useState('00:00');
  const [aiNodes, setAiNodes] = useState<AINode[]>([]);
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<NodeCatalogEntry[] | null>(null);
  const [selectedNode, setSelectedNode] = useState<Node<any> | null>(null);
  // [P-7] 엣지 선택 상태 — Page 가 mutual exclusion 책임
  const [selectedEdge, setSelectedEdge] = useState<InspectedEdge | null>(null);

  // 보고서 미리보기 모달
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const sseRef = useRef<EventSource | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tickerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const pushEvent = useCallback((ev: Omit<TimelineEvent, 'id' | 'at'> & { at?: number }) => {
    setEvents((prev) => [
      ...prev,
      { ...ev, id: makeEventId(), at: ev.at ?? Date.now() },
    ]);
  }, []);

  // Apply execution snapshot (from polling or initial GET) to nodeProgress state
  const applyExecution = useCallback(
    (ex: WorkflowExecution) => {
      setInstance((prev) => ({ ...(prev ?? ({} as any)), ...ex, instanceId: ex.id }) as any);
      if (ex.nodeResults && typeof ex.nodeResults === 'object') {
        const updated: Record<string, NodeProgress> = {};
        for (const [nid, r] of Object.entries(ex.nodeResults)) {
          if (r && typeof r === 'object') {
            const rb = r as Record<string, unknown>;
            updated[nid] = {
              status: String(rb.status || 'pending'),
              output: rb.outputData ?? rb.output,
              error: typeof rb.error === 'string' ? rb.error : undefined,
            };
          }
        }
        setNodeProgress(updated);
      }
    },
    [],
  );

  // Initial load: workflow + instance snapshot
  useEffect(() => {
    let cancelled = false;
    if (!workflowId || !instanceId) return;

    async function load() {
      setLoading(true);
      try {
        const [wf, ex, entryList] = await Promise.all([
          workflowApi.get(workflowId!),
          warehouseApi.getInstance(instanceId!),
          warehouseApi.listInstanceEntries(instanceId!).catch(() => [] as WarehouseInstanceEntry[]),
        ]);
        if (cancelled) return;
        setWorkflow(wf);
        applyExecution(ex);
        setEntries(entryList);
      } catch (e) {
        toast.error(`실행기록 조회 실패: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [workflowId, instanceId, applyExecution, toast]);

  // Auto-select first entry when entries change (initial load or after deletion)
  useEffect(() => {
    if (entries.length > 0) {
      setSelectedEntryId((prev) => {
        // Keep current selection if it still exists
        if (prev && entries.some((e) => e.id === prev)) return prev;
        return entries[0].id;
      });
    } else {
      setSelectedEntryId(null);
    }
  }, [entries]);

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
        setCatalog([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // [P-7] 노드 클릭 핸들러 — 토글 동작. 노드 선택 시 엣지 닫음.
  const handleNodeClick = useCallback((rfNode: Node<any>) => {
    setSelectedNode((prev) => (prev?.id === rfNode.id ? null : rfNode));
    setSelectedEdge(null);
  }, []);

  // [P-7] 엣지 선택 시 노드 드로어 닫음
  const handleEdgeSelect = useCallback((edge: InspectedEdge | null) => {
    setSelectedEdge(edge);
    if (edge) setSelectedNode(null);
  }, []);

  // Ticker: elapsed time updater
  useEffect(() => {
    if (!instance) return;
    tickerRef.current = setInterval(() => {
      setElapsed(formatElapsed(instance.startedAt ?? instance.createdAt, instance.completedAt));
    }, 1000);
    return () => {
      if (tickerRef.current) clearInterval(tickerRef.current);
    };
  }, [instance]);

  // Poll fallback — reused if SSE fails
  const startPolling = useCallback(() => {
    if (!instanceId) return;
    setConnection('polling');
    const poll = async () => {
      try {
        const ex = await warehouseApi.getInstance(instanceId);
        applyExecution(ex);
        if (ex.status === 'completed' || ex.status === 'failed' || ex.status === 'cancelled') {
          setConnection('done');
          return;
        }
      } catch {
        if (!navigator.onLine) {
          setConnection('offline');
        }
      }
      pollRef.current = setTimeout(poll, 3000);
    };
    poll();
  }, [instanceId, applyExecution]);

  // SSE subscription
  useEffect(() => {
    if (!instanceId || !instance) return;
    // 이미 종료된 실행이면 구독 불필요
    if (['completed', 'failed', 'cancelled'].includes(instance.status)) {
      setConnection('done');
      return;
    }

    if (!navigator.onLine) {
      setConnection('offline');
      return;
    }

    let closed = false;
    const es = warehouseApi.streamInstance(instanceId);
    sseRef.current = es;
    setConnection('connecting');

    const addListener = (type: string, handler: (ev: MessageEvent) => void) => {
      es.addEventListener(type, handler as EventListener);
    };

    const parse = (ev: MessageEvent) => {
      try {
        return JSON.parse(ev.data);
      } catch {
        return null;
      }
    };

    addListener('stream_open', (ev) => {
      const data = parse(ev);
      setConnection('sse');
      pushEvent({ kind: 'open', message: data?.message });
    });

    addListener('status', (ev) => {
      const data = parse(ev);
      if (!data) return;
      pushEvent({ kind: 'status', status: data.status });
      setInstance((prev) => (prev ? { ...prev, status: data.status } : prev));
    });

    addListener('node_start', (ev) => {
      const data = parse(ev);
      if (!data?.nodeId) return;
      pushEvent({ kind: 'node_start', nodeId: data.nodeId, status: data.status });
      setNodeProgress((prev) => ({
        ...prev,
        [data.nodeId]: { ...(prev[data.nodeId] || {}), status: data.status || 'running' },
      }));
    });

    addListener('node_complete', (ev) => {
      const data = parse(ev);
      if (!data?.nodeId) return;
      pushEvent({ kind: 'node_complete', nodeId: data.nodeId, status: data.status });
      setNodeProgress((prev) => ({
        ...prev,
        [data.nodeId]: {
          status: data.status || 'completed',
          output: data.output,
          error: prev[data.nodeId]?.error,
        },
      }));
    });

    addListener('node_error', (ev) => {
      const data = parse(ev);
      if (!data?.nodeId) return;
      pushEvent({
        kind: 'node_error',
        nodeId: data.nodeId,
        status: data.status,
        message: data.error,
      });
      setNodeProgress((prev) => ({
        ...prev,
        [data.nodeId]: {
          status: data.status || 'failed',
          error: data.error,
          output: prev[data.nodeId]?.output,
        },
      }));
    });

    addListener('execution_complete', (ev) => {
      const data = parse(ev);
      pushEvent({ kind: 'complete', status: data?.status, message: data?.error });
      setInstance((prev) =>
        prev
          ? {
              ...prev,
              status: data?.status ?? prev.status,
              outputData: data?.output ?? prev.outputData,
              errorMessage: data?.error ?? prev.errorMessage,
              errorNodeId: data?.errorNodeId ?? prev.errorNodeId,
              completedAt: prev.completedAt ?? new Date().toISOString(),
            }
          : prev,
      );
      setConnection('done');
      // 최종 상태에서 창고 적재 목록 재조회
      warehouseApi
        .listInstanceEntries(instanceId)
        .then(setEntries)
        .catch(() => {});
      if (!closed) {
        closed = true;
        es.close();
        sseRef.current = null;
      }
    });

    es.onerror = () => {
      pushEvent({ kind: 'error', message: 'SSE 연결 실패 — 폴링으로 전환' });
      if (!closed) {
        closed = true;
        es.close();
        sseRef.current = null;
        startPolling();
      }
    };

    return () => {
      closed = true;
      if (sseRef.current) {
        sseRef.current.close();
        sseRef.current = null;
      }
      if (pollRef.current) {
        clearTimeout(pollRef.current);
        pollRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [instanceId, instance?.id]);

  // Online/offline listener
  useEffect(() => {
    const onOnline = () => {
      if (connection === 'offline') setConnection('polling');
      if (!sseRef.current && instanceId) startPolling();
    };
    const onOffline = () => setConnection('offline');
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, [connection, instanceId, startPolling]);

  // Final markdown output (first markdown-viewer node or outputData as markdown)
  const markdownOutput = useMemo<string | null>(() => {
    if (!workflow) return null;
    const mdNode = workflow.nodes.find(
      (n) => (n.definitionType || '').toLowerCase() === 'markdown-viewer',
    );
    if (mdNode) {
      const progress = nodeProgress[mdNode.id];
      const out = progress?.output;
      if (out && typeof out === 'object') {
        const obj = out as Record<string, unknown>;
        for (const k of ['markdown', 'content', 'text', 'body']) {
          if (typeof obj[k] === 'string') return obj[k] as string;
        }
      }
      if (typeof out === 'string') return out;
    }
    // Fallback: instance outputData
    if (instance?.outputData && typeof instance.outputData === 'object') {
      const obj = instance.outputData as Record<string, unknown>;
      for (const k of ['markdown', 'content', 'text', 'body']) {
        if (typeof obj[k] === 'string') return obj[k] as string;
      }
    }
    return null;
  }, [workflow, nodeProgress, instance]);

  // ─── Report preview handler ──────────────────────────────────
  const handleOpenPreview = useCallback(async () => {
    const base = import.meta.env.VITE_API_BASE_URL || '/api/v1';
    const url = `${base}/warehouse/instances/${instanceId}/report.md`;
    setPreviewOpen(true);
    setPreviewContent(null);
    setPreviewError(null);
    setPreviewLoading(true);
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const text = await res.text();
      setPreviewContent(text);
    } catch (e) {
      setPreviewError(`보고서를 불러올 수 없습니다: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setPreviewLoading(false);
    }
  }, [instanceId]);

  // ESC 키로 미리보기 모달 닫기
  useEffect(() => {
    if (!previewOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPreviewOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [previewOpen]);

  // ─── Delete execution handler ────────────────────────────────
  const handleDeleteExecution = useCallback(async () => {
    if (!instanceId || !workflowId) return;
    const entryCount = entries.length;
    const confirmed = window.confirm(
      `실행기록 ${instanceId}와 관련 결과 ${entryCount}건이 영구 삭제됩니다. 계속하시겠습니까?`
    );
    if (!confirmed) return;
    try {
      await workflowApi.deleteExecution(instanceId);
      toast.success('실행기록이 삭제되었습니다.');
      navigate(`/workflows/${workflowId}`);
    } catch (e) {
      toast.error(`삭제 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [instanceId, workflowId, entries.length, navigate, toast]);

  // ─── Render ──

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-slate-950">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-slate-700 border-t-sky-500 rounded-full animate-spin" />
          <span className="text-xs text-slate-500 font-mono">실행기록 로드 중...</span>
        </div>
      </div>
    );
  }

  if (!instance || !workflow) {
    return (
      <div className="h-full flex items-center justify-center bg-slate-950">
        <div className="text-center">
          <p className="text-sm text-slate-400">실행기록을 찾을 수 없습니다.</p>
          <Link
            to={`/workflows/${workflowId ?? ''}`}
            className="inline-block mt-3 text-xs font-mono text-sky-400 hover:text-sky-300"
          >
            ← 업무자동화로 돌아가기
          </Link>
        </div>
      </div>
    );
  }

  const orderedNodes = [...workflow.nodes].sort(
    (a, b) => (a.orderIndex ?? 0) - (b.orderIndex ?? 0),
  );

  // Compute not_executed nodes: nodes defined in workflow but absent from nodeProgress
  // when the execution is in a terminal state (completed/failed/cancelled).
  const isTerminal = ['completed', 'failed', 'cancelled'].includes(instance.status);
  const notExecutedNodeIds = isTerminal
    ? orderedNodes
        .filter((n) => !(n.id in nodeProgress))
        .map((n) => n.id)
    : [];

  // Augmented progress: inject not_executed entries for the canvas and NodeRow list
  const augmentedNodeProgress: Record<string, NodeProgress> = {
    ...nodeProgress,
    ...Object.fromEntries(notExecutedNodeIds.map((id) => [id, { status: 'not_executed' }])),
  };

  // Stats for header count
  const executedCount = Object.keys(nodeProgress).length;
  const completedCount = Object.values(nodeProgress).filter((p) => p.status === 'completed').length;
  const notExecutedCount = notExecutedNodeIds.length;

  const connectionLabel = {
    connecting: '연결 중',
    sse: 'LIVE (SSE)',
    polling: 'POLLING',
    done: 'COMPLETED',
    offline: 'OFFLINE',
  }[connection];

  const connectionTone = {
    connecting: 'text-amber-300 border-amber-700/60 bg-amber-950/30',
    sse: 'text-emerald-300 border-emerald-700/60 bg-emerald-950/30',
    polling: 'text-sky-300 border-sky-700/60 bg-sky-950/30',
    done: 'text-slate-400 border-slate-700/60 bg-slate-900/60',
    offline: 'text-rose-300 border-rose-700/60 bg-rose-950/30',
  }[connection];

  return (
    <div className="h-full flex flex-col bg-slate-950">
      {/* Header */}
      <header className="flex-shrink-0 border-b border-slate-800 bg-slate-950/80 backdrop-blur">
        <div className="w-full px-6 py-4 flex items-center gap-4">
          <Link
            to={`/workflows/${workflowId}`}
            className="flex-shrink-0 p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 transition-colors"
          >
            <span className="text-lg">←</span>
          </Link>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <div className="text-[10px] font-mono tracking-[0.2em] uppercase text-slate-500">
                실행기록
              </div>
              <StatusBadge status={instance.status} />
              <span
                className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10px] font-mono uppercase tracking-wider ${connectionTone}`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    connection === 'sse' ? 'bg-emerald-400 animate-pulse' : 'bg-current opacity-60'
                  }`}
                />
                {connectionLabel}
              </span>
            </div>
            <h1 className="text-lg font-mono text-slate-100 truncate">{instance.id}</h1>
            <p className="text-[11px] text-slate-500 mt-0.5">
              {workflow.name} ·{' '}
              {instance.startedAt
                ? new Date(instance.startedAt).toLocaleString('ko-KR')
                : '시작 전'}
            </p>
          </div>
          <div className="flex-shrink-0 flex items-center gap-4">
            {instance.status === 'completed' && (
              <>
                <button
                  onClick={handleOpenPreview}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-900/60 text-xs font-mono text-slate-300 hover:text-slate-100 hover:border-slate-500 hover:bg-slate-800/60 transition-colors"
                >
                  👁 미리보기
                </button>
                <a
                  href={`${import.meta.env.VITE_API_BASE_URL || '/api/v1'}/warehouse/instances/${instanceId}/report.md?save=true&download=true`}
                  download={`report-exec-${instanceId?.slice(0, 8)}.md`}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-900/60 text-xs font-mono text-slate-300 hover:text-slate-100 hover:border-slate-500 hover:bg-slate-800/60 transition-colors"
                >
                  📄 MD 보고서 다운로드
                </a>
              </>
            )}
            <button
              onClick={handleDeleteExecution}
              title="이 실행 기록 삭제"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-900/60 text-xs font-mono text-rose-400/80 hover:text-rose-300 hover:border-rose-700/60 hover:bg-rose-950/30 transition-colors"
            >
              🗑 삭제
            </button>
            <div className="text-right">
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500">
                경과
              </div>
              <div className="text-2xl font-light tabular-nums text-slate-100 font-mono">
                {elapsed}
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Content: two columns on desktop */}
      <InstanceExecutionContext.Provider value={{ executionId: instance.id }}>
      <div className="flex-1 overflow-auto">
        <div className="w-full px-6 py-6 space-y-6">
          {/* Canvas */}
          <section>
            <div className="flex items-baseline justify-between mb-2">
              <h2 className="text-xs font-mono tracking-[0.2em] uppercase text-slate-400">
                노드별 진행상태
              </h2>
              <span className="text-[10px] font-mono text-slate-600">
                {notExecutedCount > 0 ? (
                  <>
                    <span className="text-emerald-600">{completedCount}</span>
                    <span> / {executedCount} 실행</span>
                    <span className="mx-1.5 text-slate-700">·</span>
                    <span className="text-slate-600">{notExecutedCount} 통과 안됨</span>
                  </>
                ) : (
                  <>{completedCount} / {orderedNodes.length} 완료</>
                )}
              </span>
            </div>
            <div className="relative rounded-xl border border-slate-800 overflow-hidden" style={{ height: 360 }}>
              <AINodesContext.Provider value={aiNodes}>
                <ReactFlowProvider>
                  <div className="absolute inset-0 flex">
                    <WorkflowViewerCanvas
                      workflow={workflow}
                      nodeProgress={augmentedNodeProgress}
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
                    pageContext="instance"
                    instance={
                      instance
                        ? {
                            id: instance.id,
                            nodeResults: instance.nodeResults as Record<string, unknown> | undefined,
                          }
                        : undefined
                    }
                    onClose={() => setSelectedNode(null)}
                  />
                </ReactFlowProvider>
              </AINodesContext.Provider>
            </div>
          </section>

          {/* Two-column grid: Nodes list + Timeline */}
          <section className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6">
            {/* Node list */}
            <div>
              <div className="flex items-baseline justify-between mb-2">
                <h2 className="text-xs font-mono tracking-[0.2em] uppercase text-slate-400">
                  노드별 결과
                </h2>
                <span className="text-[10px] font-mono text-slate-600">
                  {notExecutedCount > 0 ? (
                    <>
                      <span>{executedCount}개 실행</span>
                      <span className="mx-1 text-slate-700">·</span>
                      <span className="text-slate-600">{notExecutedCount}개 통과 안됨</span>
                    </>
                  ) : (
                    <>{orderedNodes.length}개</>
                  )}
                </span>
              </div>
              <div className="space-y-2">
                {orderedNodes.map((n) => (
                  <NodeRow
                    key={n.id}
                    nodeId={n.id}
                    nodeName={n.name}
                    defType={n.definitionType || ''}
                    progress={augmentedNodeProgress[n.id]}
                  />
                ))}
              </div>
            </div>

            {/* Timeline */}
            <div>
              <div className="flex items-baseline justify-between mb-2">
                <h2 className="text-xs font-mono tracking-[0.2em] uppercase text-slate-400">
                  이벤트 타임라인
                </h2>
                <span className="text-[10px] font-mono text-slate-600">{events.length}</span>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-3">
                <TimelineStrip events={events} />
              </div>

              {/* Error summary */}
              {instance.errorMessage && (
                <div className="mt-4 rounded-lg border border-rose-700/60 bg-rose-950/30 p-3">
                  <div className="text-[10px] font-mono uppercase tracking-wider text-rose-400 mb-1">
                    실패 사유
                  </div>
                  <div className="text-xs text-rose-200 font-mono whitespace-pre-wrap break-all">
                    {instance.errorMessage}
                  </div>
                  {instance.errorNodeId && (
                    <div className="mt-1 text-[11px] font-mono text-rose-400/70">
                      실패 노드: {instance.errorNodeId}
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>

          {/* Markdown output if available */}
          {markdownOutput && (
            <section>
              <h2 className="text-xs font-mono tracking-[0.2em] uppercase text-slate-400 mb-2">
                최종 마크다운 출력
              </h2>
              <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-5 text-sm text-slate-200">
                <pre className="whitespace-pre-wrap break-words font-sans leading-relaxed">
                  {markdownOutput}
                </pre>
              </div>
            </section>
          )}

          {/* Warehouse entries — 1실행 1결과 레이아웃 */}
          {entries.length > 0 && (
            <section>
              <div className="flex items-baseline justify-between mb-3">
                <h2 className="text-xs font-mono tracking-[0.2em] uppercase text-slate-400">
                  결과창고 적재 ({entries.length})
                </h2>
              </div>
              <WarehouseEntriesPanel
                entries={entries}
                workflow={workflow}
                instanceId={instanceId!}
                selectedEntryId={selectedEntryId}
                onSelectEntry={setSelectedEntryId}
                onEntriesChange={(updated) => {
                  setEntries(updated);
                }}
              />
            </section>
          )}
        </div>
      </div>
      </InstanceExecutionContext.Provider>

      {/* 보고서 미리보기 모달 */}
      {previewOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
          onClick={() => setPreviewOpen(false)}
        >
          <div
            className="relative flex flex-col w-full max-w-4xl max-h-[85vh] mx-4 rounded-xl border border-slate-700 bg-slate-900 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* 모달 헤더 */}
            <div className="flex-shrink-0 flex items-center justify-between px-5 py-3.5 border-b border-slate-800">
              <h2 className="text-sm font-mono text-slate-200 truncate">
                보고서 미리보기 — <span className="text-sky-400">exec-{instanceId?.slice(0, 8)}</span>
              </h2>
              <button
                onClick={() => setPreviewOpen(false)}
                className="ml-4 flex-shrink-0 p-1.5 rounded-md text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
                aria-label="닫기"
              >
                ✕
              </button>
            </div>

            {/* 모달 본문 */}
            <div className="flex-1 overflow-auto px-6 py-5">
              {previewLoading && (
                <div className="flex items-center justify-center h-40 gap-3 text-slate-400">
                  <div className="w-5 h-5 border-2 border-slate-600 border-t-sky-500 rounded-full animate-spin" />
                  <span className="text-sm font-mono">보고서 불러오는 중...</span>
                </div>
              )}
              {previewError && !previewLoading && (
                <div className="flex items-center gap-2 text-rose-400 text-sm font-mono py-4">
                  <span>⚠</span>
                  <span>{previewError}</span>
                </div>
              )}
              {previewContent && !previewLoading && (
                <StyledMarkdown className="text-slate-200">
                  {previewContent}
                </StyledMarkdown>
              )}
            </div>

            {/* 모달 푸터 */}
            <div className="flex-shrink-0 flex items-center justify-end gap-3 px-5 py-3 border-t border-slate-800">
              <a
                href={`${import.meta.env.VITE_API_BASE_URL || '/api/v1'}/warehouse/instances/${instanceId}/report.md?save=true&download=true`}
                download={`report-exec-${instanceId?.slice(0, 8)}.md`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-900/60 text-xs font-mono text-slate-300 hover:text-slate-100 hover:border-slate-500 hover:bg-slate-800/60 transition-colors"
              >
                📄 다운로드
              </a>
              <button
                onClick={() => setPreviewOpen(false)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-900/60 text-xs font-mono text-slate-400 hover:text-slate-100 hover:border-slate-500 hover:bg-slate-800/60 transition-colors"
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
