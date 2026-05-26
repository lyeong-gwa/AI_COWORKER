/**
 * EmptyState — CLI 주도 플랫폼 문구 가이드에 맞춘 빈 상태 배너.
 * 편집 기능이 웹에서 모두 제거되므로, 빈 상태에서는 항상 CLI 안내로 유도한다.
 */
import type { ReactNode } from 'react';

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  hint?: ReactNode;
  action?: ReactNode;
}

export function EmptyState({ icon, title, description, hint, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-6">
      {icon && (
        <div className="mb-4 w-16 h-16 rounded-2xl bg-slate-800/60 border border-slate-700/60 flex items-center justify-center text-3xl text-slate-400">
          {icon}
        </div>
      )}
      <h3 className="text-slate-200 font-semibold text-base mb-1.5">{title}</h3>
      {description && (
        <p className="text-sm text-slate-400 max-w-md leading-relaxed">{description}</p>
      )}
      {hint && (
        <div className="mt-4 px-4 py-2 rounded-lg bg-sky-950/40 border border-sky-800/50 text-xs text-sky-200 font-mono">
          {hint}
        </div>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
