/**
 * PageTypeBadge — Karpathy v2 page_type 5종 색상 배지
 *
 * Summary:    blue     — 원본 요약, 입문용
 * Entity:     emerald  — 단일 대상 사실 기술
 * Concept:    violet   — 추상 개념·정책·원칙 정의
 * Comparison: amber    — 2개 이상 비교
 * Synthesis:  rose     — 운영 중 새 통찰
 */
import type { PageType } from '../../types';

interface PageTypeBadgeProps {
  type: PageType;
  className?: string;
}

const TYPE_CONFIG: Record<
  PageType,
  { label: string; bg: string; text: string; border: string }
> = {
  Summary: {
    label: 'Summary',
    bg: 'bg-blue-500/15',
    text: 'text-blue-300',
    border: 'border-blue-500/30',
  },
  Entity: {
    label: 'Entity',
    bg: 'bg-emerald-500/15',
    text: 'text-emerald-300',
    border: 'border-emerald-500/30',
  },
  Concept: {
    label: 'Concept',
    bg: 'bg-violet-500/15',
    text: 'text-violet-300',
    border: 'border-violet-500/30',
  },
  Comparison: {
    label: 'Comparison',
    bg: 'bg-amber-500/15',
    text: 'text-amber-300',
    border: 'border-amber-500/30',
  },
  Synthesis: {
    label: 'Synthesis',
    bg: 'bg-rose-500/15',
    text: 'text-rose-300',
    border: 'border-rose-500/30',
  },
};

export function PageTypeBadge({ type, className = '' }: PageTypeBadgeProps) {
  const cfg = TYPE_CONFIG[type] ?? TYPE_CONFIG.Summary;
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${cfg.bg} ${cfg.text} ${cfg.border} ${className}`}
    >
      {cfg.label}
    </span>
  );
}
