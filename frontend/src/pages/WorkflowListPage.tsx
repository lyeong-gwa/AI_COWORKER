/**
 * Workflow List Page (`/workflows`)
 *
 * 전체 워크플로우 목록. 필터(상태, 검색)와 정렬 제공.
 * 각 행 클릭 시 WorkflowViewerPage (/workflows/:id) 로 이동.
 *
 * Phase 3b 신설. 편집 기능 없음 (읽기전용 + 실행 진입점).
 * Phase B: 카드 우상단 🗑 버튼 → WorkflowDeleteConfirmModal.
 */
import { useEffect, useMemo, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { workflowApi, type WorkflowSummary } from '../services/api';
import { StatusBadge } from '../components/common/StatusBadge';
import { EmptyState } from '../components/common/EmptyState';
import { CliHint } from '../components/common/CliHint';
import { useToast } from '../components/common/Toast';
import { WorkflowDeleteConfirmModal } from '../components/workflow/WorkflowDeleteConfirmModal';
import { cronToLabel } from '../components/workflow/WorkflowScheduleCard';

type SortKey = 'updatedDesc' | 'updatedAsc' | 'nameAsc';

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'updatedDesc', label: '최근 수정순' },
  { value: 'updatedAsc', label: '오래된 수정순' },
  { value: 'nameAsc', label: '이름 오름차순' },
];

const STATUS_FILTERS: Array<{ value: 'all' | WorkflowSummary['status']; label: string }> = [
  { value: 'all', label: '전체' },
  { value: 'active', label: '활성' },
  { value: 'draft', label: '초안' },
  { value: 'paused', label: '일시중지' },
  { value: 'archived', label: '보관됨' },
];

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  } catch {
    return iso;
  }
}

export default function WorkflowListPage() {
  const { toast } = useToast();
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | WorkflowSummary['status']>('all');
  const [sortKey, setSortKey] = useState<SortKey>('updatedDesc');

  // 삭제 모달 상태
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await workflowApi.list();
      setWorkflows(data);
    } catch (e) {
      toast.error(`목록 조회 실패: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let items = workflows.filter((wf) => {
      if (statusFilter !== 'all' && wf.status !== statusFilter) return false;
      if (!q) return true;
      return (
        wf.name.toLowerCase().includes(q) ||
        (wf.description || '').toLowerCase().includes(q) ||
        wf.tags.some((t) => t.toLowerCase().includes(q))
      );
    });
    items = [...items].sort((a, b) => {
      if (sortKey === 'nameAsc') return a.name.localeCompare(b.name, 'ko');
      const at = new Date(a.updatedAt).getTime();
      const bt = new Date(b.updatedAt).getTime();
      return sortKey === 'updatedDesc' ? bt - at : at - bt;
    });
    return items;
  }, [workflows, query, statusFilter, sortKey]);

  return (
    <div className="h-full overflow-auto bg-slate-950">
      <div className="w-full px-6 py-8">
        {/* Header */}
        <header className="mb-6">
          <div className="text-[11px] font-mono tracking-[0.25em] uppercase text-slate-500 mb-2">
            업무자동화
          </div>
          <h1 className="text-3xl font-light text-slate-50 tracking-tight">
            업무자동화 목록
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            {workflows.length}개 등록됨 · 표시 중 {filtered.length}개
          </p>
        </header>

        <div className="mb-4">
          <CliHint tone="subtle">
            생성·수정은 CLI로 가능합니다.{' '}
            <strong className="text-slate-200">삭제·실행·조회는 웹 UI에서 수행할 수 있습니다.</strong>
          </CliHint>
        </div>

        {/* Controls */}
        <div className="mb-5 flex flex-wrap items-center gap-3">
          {/* Search */}
          <div className="flex-1 min-w-[240px] relative">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="이름·설명·태그 검색"
              className="w-full pl-10 pr-3 py-2 rounded-lg bg-slate-900/60 border border-slate-800 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-sky-600/60 focus:bg-slate-900"
            />
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 text-sm font-mono">
              /
            </span>
          </div>

          {/* Status filter */}
          <div className="flex gap-1 p-1 rounded-lg bg-slate-900/60 border border-slate-800">
            {STATUS_FILTERS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setStatusFilter(opt.value)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                  statusFilter === opt.value
                    ? 'bg-slate-800 text-slate-100'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {/* Sort */}
          <select
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
            className="px-3 py-2 rounded-lg bg-slate-900/60 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-sky-600/60"
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* List */}
        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="h-20 rounded-lg bg-slate-900/40 border border-slate-800 animate-pulse"
              />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={'∅'}
            title={workflows.length === 0 ? '등록된 업무자동화가 없습니다' : '조건에 맞는 업무자동화가 없습니다'}
            description={
              workflows.length === 0 ? (
                <>
                  CLI로 업무자동화를 생성하세요.
                  <br />
                  자세한 사용법은 <code className="px-1 text-sky-300">CLAUDE.md</code> 참고.
                </>
              ) : (
                <>필터 또는 검색어를 변경해 보세요.</>
              )
            }
            hint={workflows.length === 0 ? 'curl -X POST http://localhost:8002/api/v1/workflows' : undefined}
          />
        ) : (
          <div className="space-y-2">
            {filtered.map((wf) => (
              <div
                key={wf.id}
                className="group relative rounded-lg border border-slate-800 bg-slate-900/40 hover:bg-slate-900/80 hover:border-slate-700 transition-all"
              >
                <Link
                  to={`/workflows/${wf.id}`}
                  className="block"
                >
                  <div className="flex items-center gap-4 px-5 py-4 pr-14">
                    {/* Left status */}
                    <div className="flex-shrink-0">
                      <StatusBadge status={wf.status} variant="workflow" size="xs" />
                    </div>

                    {/* Middle: info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-baseline gap-3 min-w-0">
                        <h3 className="text-slate-100 font-semibold text-[15px] truncate">
                          {wf.name}
                        </h3>
                        <span className="text-[10px] font-mono text-slate-600 truncate hidden md:inline">
                          {wf.id}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 mt-0.5 truncate">
                        {wf.description || '설명 없음'}
                      </p>
                      <div className="flex flex-wrap items-center gap-1 mt-1.5">
                        {wf.tags.slice(0, 4).map((tag) => (
                          <span
                            key={tag}
                            className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800/60 text-slate-400 border border-slate-700/60"
                          >
                            #{tag}
                          </span>
                        ))}
                        {/* 스케줄 배지 */}
                        {wf.scheduleConfig && (
                          wf.scheduleConfig.enabled ? (
                            <span className="inline-flex items-center gap-1 rounded-full border border-cyan-600/50 bg-cyan-900/30 px-2 py-0.5 text-[10px] font-mono text-cyan-300">
                              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse flex-shrink-0" />
                              &#x23F0; ON &middot; {cronToLabel(wf.scheduleConfig.cronExpr)}
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 rounded-full border border-slate-700/60 bg-slate-800/40 px-2 py-0.5 text-[10px] font-mono text-slate-500">
                              &#x23F0; OFF
                            </span>
                          )
                        )}
                      </div>
                    </div>

                    {/* Right: meta */}
                    <div className="flex-shrink-0 flex items-center gap-4 text-right">
                      <div className="text-[11px] font-mono text-slate-500">
                        <div>노드 {wf.nodeCount}</div>
                        <div className="text-slate-600 mt-0.5">{formatDate(wf.updatedAt)}</div>
                      </div>
                      <span className="text-slate-600 group-hover:text-sky-400 transition-colors text-lg">
                        →
                      </span>
                    </div>
                  </div>
                </Link>

                {/* 삭제 버튼 — hover 시에만 노출 */}
                <button
                  type="button"
                  title={`"${wf.name}" 삭제`}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setDeleteTarget({ id: wf.id, name: wf.name });
                  }}
                  className="absolute top-1/2 right-4 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity w-8 h-8 rounded-lg flex items-center justify-center text-slate-500 hover:text-red-400 hover:bg-red-500/10 border border-transparent hover:border-red-500/30 transition-colors"
                  aria-label={`"${wf.name}" 삭제`}
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 3.5h12M4.5 3.5V2a.5.5 0 0 1 .5-.5h4a.5.5 0 0 1 .5.5v1.5M5.5 6v5M8.5 6v5M2.5 3.5l.5 9a.5.5 0 0 0 .5.5h7a.5.5 0 0 0 .5-.5l.5-9" />
  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 워크플로 삭제 확인 모달 */}
      {deleteTarget && (
        <WorkflowDeleteConfirmModal
          workflowId={deleteTarget.id}
          workflowName={deleteTarget.name}
          onClose={() => setDeleteTarget(null)}
          onDeleted={() => {
            setDeleteTarget(null);
            load();
          }}
        />
      )}
    </div>
  );
}
