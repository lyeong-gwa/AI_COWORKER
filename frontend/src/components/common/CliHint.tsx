/**
 * CliHint — "이 리소스는 CLI로만 편집 가능합니다" 배너.
 *
 * 지식/API명세/노드 뷰어 페이지 상단에 배치하여 사용자 기대치를 조율한다.
 */
import type { ReactNode } from 'react';

interface CliHintProps {
  title?: string;
  children: ReactNode;
  tone?: 'info' | 'subtle';
}

export function CliHint({ title = 'CLI로 관리', children, tone = 'info' }: CliHintProps) {
  const styles =
    tone === 'info'
      ? 'bg-sky-950/40 border-sky-800/60 text-sky-100'
      : 'bg-slate-900/60 border-slate-700/60 text-slate-300';

  return (
    <div
      className={`flex items-start gap-3 rounded-lg border px-4 py-3 ${styles}`}
      role="status"
    >
      <div className="flex-shrink-0 mt-0.5 w-6 h-6 rounded-md bg-sky-500/20 border border-sky-500/40 flex items-center justify-center text-sky-300 text-xs font-bold">
        {'>_'}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-300/90">
          {title}
        </div>
        <div className="mt-1 text-[13px] leading-relaxed text-slate-200/90">{children}</div>
      </div>
    </div>
  );
}
