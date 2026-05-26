/**
 * Dashboard Page — 실행현황 요약 + 워크플로우 카드 그리드
 *
 * Phase 3b 재구성 산출물. Phase 4c에서 집계 API 교체.
 * - 상단: 4종 요약 카드 (오늘 실행 / 진행 중 / 실패 / 성공)
 * - 하단: 워크플로우 카드 그리드 (뷰어 + 실행 진입점)
 *
 * 쓰기는 허용하지 않는다. 편집·생성은 모두 CLI로 이관되었다.
 * Phase 4c: GET /api/v1/dashboard/summary 단일 호출로 N+1 제거.
 */
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { dashboardApi, type DashboardWorkflowSummary } from '../services/api';
import { StatusBadge } from '../components/common/StatusBadge';
import { EmptyState } from '../components/common/EmptyState';
import { useToast } from '../components/common/Toast';

// ─── Local types ─────────────────────────────────────────────

interface SummaryStats {
  today: number;
  inProgress: number;
  failed: number;
  succeeded: number;
}

type WorkflowCardData = DashboardWorkflowSummary;

// ─── Helpers ─────────────────────────────────────────────────

const RECENT_DAYS = 7; // 요약 카드 description 표시용

function formatRelative(iso?: string | null): string {
  if (!iso) return '실행 이력 없음';
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return '방금 전';
  if (mins < 60) return `${mins}분 전`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}시간 전`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}일 전`;
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

// ─── Summary Card ────────────────────────────────────────────

interface SummaryCardProps {
  label: string;
  value: number;
  tone: 'sky' | 'amber' | 'rose' | 'emerald';
  description?: string;
  onClick?: () => void;
}

const TONE_MAP: Record<SummaryCardProps['tone'], { bar: string; glow: string; num: string; hover: string }> = {
  sky: {
    bar: 'bg-sky-500',
    glow: 'shadow-[0_0_24px_rgba(56,189,248,0.15)]',
    num: 'text-sky-100',
    hover: 'hover:border-sky-500/60',
  },
  amber: {
    bar: 'bg-amber-500',
    glow: 'shadow-[0_0_24px_rgba(245,158,11,0.15)]',
    num: 'text-amber-100',
    hover: 'hover:border-amber-500/60',
  },
  rose: {
    bar: 'bg-rose-500',
    glow: 'shadow-[0_0_24px_rgba(244,63,94,0.18)]',
    num: 'text-rose-100',
    hover: 'hover:border-rose-500/60',
  },
  emerald: {
    bar: 'bg-emerald-500',
    glow: 'shadow-[0_0_24px_rgba(16,185,129,0.15)]',
    num: 'text-emerald-100',
    hover: 'hover:border-emerald-500/60',
  },
};

function SummaryCard({ label, value, tone, description, onClick }: SummaryCardProps) {
  const t = TONE_MAP[tone];
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={`group relative text-left rounded-xl bg-slate-900/60 border border-slate-800 px-5 py-4 transition-all duration-200 ${t.hover} ${onClick ? 'cursor-pointer hover:bg-slate-900/90 ' + t.glow : 'cursor-default'}`}
    >
      {/* Accent bar */}
      <div className={`absolute top-0 left-0 h-[3px] w-10 rounded-br ${t.bar}`} />

      <div className="flex items-baseline justify-between mb-1">
        <span className="text-[10px] font-mono tracking-[0.2em] uppercase text-slate-500">
          {label}
        </span>
        <span className="text-[10px] text-slate-600 font-mono">
          {description}
        </span>
      </div>

      <div className={`font-light tabular-nums text-4xl ${t.num} leading-none mt-2`}>
        {value.toLocaleString()}
      </div>
    </button>
  );
}

// ─── Workflow Card ───────────────────────────────────────────

interface WorkflowCardProps {
  workflow: WorkflowCardData;
  onRun: () => void;
}

function WorkflowCard({ workflow, onRun }: WorkflowCardProps) {
  return (
    <div className="group relative flex flex-col rounded-xl bg-gradient-to-b from-slate-900/80 to-slate-900/40 border border-slate-800 hover:border-slate-700 transition-all duration-200 overflow-hidden">
      {/* Hover accent */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-500/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

      {/* Body */}
      <Link
        to={`/workflows/${workflow.id}`}
        className="flex-1 p-5 flex flex-col gap-3 min-w-0"
      >
        {/* Status & ID */}
        <div className="flex items-center justify-between gap-2">
          <StatusBadge status={workflow.status} variant="workflow" size="xs" />
          <span className="text-[10px] font-mono text-slate-600 truncate">
            {workflow.id}
          </span>
        </div>

        {/* Title */}
        <div className="min-w-0">
          <h3 className="text-slate-100 font-semibold text-[15px] leading-snug truncate">
            {workflow.name}
          </h3>
          <p className="text-slate-400 text-xs mt-1 line-clamp-2 min-h-[2em]">
            {workflow.description || '설명 없음'}
          </p>
        </div>

        {/* Meta row */}
        <div className="flex items-center gap-3 text-[11px] text-slate-500 font-mono mt-auto pt-2 border-t border-slate-800/60">
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-1 h-1 rounded-full bg-slate-500" />
            노드 {workflow.nodeCount}
          </span>
          <span className="text-slate-600">·</span>
          <span>{formatRelative(workflow.latestInstance?.createdAt ?? workflow.updatedAt)}</span>
        </div>
      </Link>

      {/* Run button */}
      <button
        onClick={onRun}
        disabled={workflow.status !== 'active'}
        className="block w-full px-5 py-3 bg-slate-950/80 border-t border-slate-800 text-left text-sm font-medium transition-colors disabled:text-slate-600 disabled:cursor-not-allowed enabled:text-sky-300 enabled:hover:bg-sky-950/40 enabled:hover:text-sky-200"
      >
        <span className="font-mono text-xs tracking-wider">▶ 실행하기</span>
      </button>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────

export default function DashboardPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [workflows, setWorkflows] = useState<WorkflowCardData[]>([]);
  const [stats, setStats] = useState<SummaryStats>({
    today: 0,
    inProgress: 0,
    failed: 0,
    succeeded: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        // Phase 4c: 단일 집계 엔드포인트 — N+1 listInstances 호출 제거.
        const summary = await dashboardApi.getSummary();

        if (cancelled) return;

        setStats({
          today: summary.counts.todayRuns,
          inProgress: summary.counts.inProgress,
          failed: summary.counts.failed,
          succeeded: summary.counts.completed,
        });
        setWorkflows(summary.workflows);
      } catch (e) {
        toast.error(`대시보드 로드 실패: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [toast]);

  const sortedWorkflows = useMemo(() => {
    // 활성 먼저, 그다음 최근 실행(latestInstance.createdAt) 순
    return [...workflows].sort((a, b) => {
      if (a.status !== b.status) {
        if (a.status === 'active') return -1;
        if (b.status === 'active') return 1;
      }
      const at = new Date(a.latestInstance?.createdAt ?? a.updatedAt).getTime();
      const bt = new Date(b.latestInstance?.createdAt ?? b.updatedAt).getTime();
      return bt - at;
    });
  }, [workflows]);

  return (
    <div className="h-full overflow-auto bg-slate-950">
      <div className="w-full px-6 py-8">
        {/* Header */}
        <header className="mb-8 flex items-baseline justify-between gap-4">
          <div>
            <div className="text-[11px] font-mono tracking-[0.25em] uppercase text-slate-500 mb-2">
              업무자동화 · 관제실
            </div>
            <h1 className="text-3xl font-light text-slate-50 tracking-tight">
              실행 현황 <span className="text-slate-600">/</span>
              <span className="text-slate-300 ml-2 font-normal">Overview</span>
            </h1>
          </div>
          <Link
            to="/workflows"
            className="text-xs font-mono text-sky-400 hover:text-sky-300 tracking-wider uppercase transition-colors"
          >
            전체 목록 →
          </Link>
        </header>

        {/* Summary cards */}
        <section className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-10">
          <SummaryCard
            label="오늘 실행"
            value={stats.today}
            tone="sky"
            description="TODAY"
            onClick={() => navigate('/workflows')}
          />
          <SummaryCard
            label="진행 중"
            value={stats.inProgress}
            tone="amber"
            description="ACTIVE"
          />
          <SummaryCard
            label="최근 실패"
            value={stats.failed}
            tone="rose"
            description={`${RECENT_DAYS}D`}
          />
          <SummaryCard
            label="최근 성공"
            value={stats.succeeded}
            tone="emerald"
            description={`${RECENT_DAYS}D`}
          />
        </section>

        {/* Workflow grid */}
        <section>
          <div className="flex items-baseline justify-between mb-4">
            <h2 className="text-sm font-mono tracking-[0.2em] uppercase text-slate-400">
              업무자동화 목록
            </h2>
            <span className="text-xs font-mono text-slate-600">
              {loading ? '로딩...' : `${workflows.length}개`}
            </span>
          </div>

          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <div
                  key={i}
                  className="h-48 rounded-xl bg-slate-900/40 border border-slate-800 animate-pulse"
                />
              ))}
            </div>
          ) : sortedWorkflows.length === 0 ? (
            <EmptyState
              icon={'∅'}
              title="아직 등록된 업무자동화가 없습니다"
              description={
                <>
                  업무자동화의 생성·수정·삭제는 CLI(Claude Code 등)를 통해서만 가능합니다.
                  <br />
                  프로젝트 <code className="px-1 text-sky-300">CLAUDE.md</code>를 참고하세요.
                </>
              }
              hint={<span>curl -X POST http://localhost:8002/api/v1/workflows</span>}
            />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {sortedWorkflows.map((wf) => (
                <WorkflowCard
                  key={wf.id}
                  workflow={wf}
                  onRun={() => navigate(`/workflows/${wf.id}?run=1`)}
                />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
