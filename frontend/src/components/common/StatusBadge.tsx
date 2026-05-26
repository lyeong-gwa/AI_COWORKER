/**
 * StatusBadge — 인스턴스 / 노드 / 워크플로우 상태를 일관된 토큰으로 표시.
 *
 * Phase 3b 재구성의 일부. 모든 대시보드/뷰어 페이지에서 공통 사용.
 */
import type { ReactNode } from 'react';

export type InstanceStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'skipped'
  | 'not_executed'
  | string;

export type WorkflowStatus = 'draft' | 'active' | 'paused' | 'archived' | string;

interface BadgeTheme {
  label: string;
  bg: string;
  text: string;
  border: string;
  dot: string;
  pulse?: boolean;
}

const INSTANCE_THEME: Record<string, BadgeTheme> = {
  pending: {
    label: '대기',
    bg: 'bg-slate-800/60',
    text: 'text-slate-300',
    border: 'border-slate-600/60',
    dot: 'bg-slate-400',
  },
  queued: {
    label: '예약',
    bg: 'bg-amber-900/30',
    text: 'text-amber-200',
    border: 'border-amber-700/60',
    dot: 'bg-amber-400',
  },
  running: {
    label: '진행 중',
    bg: 'bg-sky-900/30',
    text: 'text-sky-200',
    border: 'border-sky-600/60',
    dot: 'bg-sky-400',
    pulse: true,
  },
  completed: {
    label: '성공',
    bg: 'bg-emerald-900/30',
    text: 'text-emerald-200',
    border: 'border-emerald-700/60',
    dot: 'bg-emerald-400',
  },
  failed: {
    label: '실패',
    bg: 'bg-rose-900/40',
    text: 'text-rose-200',
    border: 'border-rose-700/60',
    dot: 'bg-rose-400',
  },
  cancelled: {
    label: '취소',
    bg: 'bg-zinc-800/60',
    text: 'text-zinc-300',
    border: 'border-zinc-600/60',
    dot: 'bg-zinc-400',
  },
  skipped: {
    label: '건너뜀',
    bg: 'bg-slate-800/60',
    text: 'text-slate-400',
    border: 'border-slate-700/60',
    dot: 'bg-slate-500',
  },
  not_executed: {
    label: '통과 안됨',
    bg: 'bg-slate-900/40',
    text: 'text-slate-500',
    border: 'border-slate-700/40',
    dot: 'bg-slate-600',
  },
};

const WORKFLOW_THEME: Record<string, BadgeTheme> = {
  active: {
    label: '활성',
    bg: 'bg-emerald-900/30',
    text: 'text-emerald-200',
    border: 'border-emerald-700/60',
    dot: 'bg-emerald-400',
  },
  draft: {
    label: '초안',
    bg: 'bg-slate-800/60',
    text: 'text-slate-300',
    border: 'border-slate-600/60',
    dot: 'bg-slate-400',
  },
  paused: {
    label: '일시중지',
    bg: 'bg-amber-900/30',
    text: 'text-amber-200',
    border: 'border-amber-700/60',
    dot: 'bg-amber-400',
  },
  archived: {
    label: '보관됨',
    bg: 'bg-zinc-800/60',
    text: 'text-zinc-400',
    border: 'border-zinc-700/60',
    dot: 'bg-zinc-500',
  },
};

function normalize(status: string): string {
  return (status || '').toLowerCase().trim();
}

function resolve(status: string, themes: Record<string, BadgeTheme>): BadgeTheme {
  return (
    themes[normalize(status)] ?? {
      label: status || '알 수 없음',
      bg: 'bg-slate-800/60',
      text: 'text-slate-300',
      border: 'border-slate-600/60',
      dot: 'bg-slate-400',
    }
  );
}

interface StatusBadgeProps {
  status: InstanceStatus | WorkflowStatus;
  variant?: 'instance' | 'workflow';
  size?: 'xs' | 'sm' | 'md';
  children?: ReactNode;
}

export function StatusBadge({
  status,
  variant = 'instance',
  size = 'sm',
  children,
}: StatusBadgeProps) {
  const theme = resolve(String(status), variant === 'workflow' ? WORKFLOW_THEME : INSTANCE_THEME);

  const sizeClasses = {
    xs: 'text-[10px] px-1.5 py-0.5 gap-1',
    sm: 'text-xs px-2 py-0.5 gap-1.5',
    md: 'text-sm px-2.5 py-1 gap-2',
  }[size];

  const dotSize = size === 'xs' ? 'w-1.5 h-1.5' : 'w-2 h-2';

  return (
    <span
      className={`inline-flex items-center rounded-full border font-mono tracking-wide ${sizeClasses} ${theme.bg} ${theme.text} ${theme.border}`}
    >
      <span
        className={`${dotSize} rounded-full ${theme.dot} ${theme.pulse ? 'animate-pulse shadow-[0_0_8px_currentColor]' : ''}`}
      />
      <span className="uppercase">{children ?? theme.label}</span>
    </span>
  );
}
