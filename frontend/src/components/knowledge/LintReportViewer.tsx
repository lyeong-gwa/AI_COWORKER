/**
 * LintReportViewer — Karpathy v2 lint 보고서 렌더러
 *
 * 두 가지 표시 모드:
 *   1. 구조화된 JSON 응답 (백엔드 실제 응답) — 섹션별 collapsible
 *   2. report_markdown 문자열 — 마크다운 원본 렌더
 *
 * summary (errors/warnings/info 배지) 한눈에 표시.
 */
import { useState } from 'react';
import type { LintReport } from '../../types';

interface LintReportViewerProps {
  report: LintReport;
}

// ─── 섹션별 항목 렌더 ────────────────────────────────────────────────────────

interface SectionBlockProps {
  title: string;
  items: unknown[];
  severity: 'error' | 'warning' | 'info';
}

function itemToString(item: unknown): string {
  if (typeof item === 'string') return item;
  if (item && typeof item === 'object') {
    return JSON.stringify(item, null, 2);
  }
  return String(item);
}

function SectionBlock({ title, items, severity }: SectionBlockProps) {
  const [open, setOpen] = useState(true);

  const severityClasses = {
    error: 'text-red-400 border-red-900/40',
    warning: 'text-amber-400 border-amber-900/40',
    info: 'text-sky-400 border-sky-900/40',
  };

  return (
    <div className="rounded-lg border border-slate-800 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 bg-slate-900/60 hover:bg-slate-900/80 text-left transition-colors"
      >
        <span className="text-slate-500 text-xs w-3">{open ? '▾' : '▸'}</span>
        <span className="text-xs font-medium text-slate-200 flex-1">{title}</span>
        <span
          className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
            items.length > 0 ? severityClasses[severity] : 'text-slate-600 border-slate-800'
          }`}
        >
          {items.length}
        </span>
      </button>
      {open && (
        <div className="px-4 py-3 bg-slate-950/40">
          {items.length === 0 ? (
            <p className="text-[11px] text-slate-600 font-mono">(이슈 없음)</p>
          ) : (
            <ul className="space-y-2">
              {items.map((item, i) => (
                <li key={i}>
                  <pre className="text-xs text-slate-300 whitespace-pre-wrap font-mono leading-relaxed">
                    {itemToString(item)}
                  </pre>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// ─── 마크다운 섹션 파싱 (fallback) ──────────────────────────────────────────

interface MarkdownSection {
  heading: string;
  content: string;
}

function parseSections(markdown: string): MarkdownSection[] {
  const lines = markdown.split('\n');
  const sections: MarkdownSection[] = [];
  let current: MarkdownSection | null = null;

  for (const line of lines) {
    if (line.startsWith('## ')) {
      if (current) sections.push(current);
      current = { heading: line.slice(3).trim(), content: '' };
    } else if (current) {
      current.content += line + '\n';
    }
  }
  if (current) sections.push(current);
  return sections;
}

function MarkdownSectionBlock({ section }: { section: MarkdownSection }) {
  const [open, setOpen] = useState(true);
  const isEmpty = !section.content.trim();

  return (
    <div className="rounded-lg border border-slate-800 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 bg-slate-900/60 hover:bg-slate-900/80 text-left transition-colors"
      >
        <span className="text-slate-500 text-xs w-3">{open ? '▾' : '▸'}</span>
        <span className="text-xs font-medium text-slate-200 flex-1">{section.heading}</span>
        {isEmpty && <span className="text-[10px] text-slate-600 font-mono">clear</span>}
      </button>
      {open && (
        <div className="px-4 py-3 bg-slate-950/40">
          {isEmpty ? (
            <p className="text-[11px] text-slate-600 font-mono">(이슈 없음)</p>
          ) : (
            <pre className="text-xs text-slate-300 whitespace-pre-wrap leading-relaxed font-mono">
              {section.content.trim()}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

// ─── 메인 컴포넌트 ────────────────────────────────────────────────────────────

export function LintReportViewer({ report }: LintReportViewerProps) {
  const s = report.summary;
  const errorCount = s.errors ?? s.error_count ?? 0;
  const warningCount = s.warnings ?? s.warning_count ?? 0;
  const infoCount = s.info ?? s.info_count ?? 0;

  // 구조화된 섹션이 있으면 섹션별 렌더
  const hasStructuredData =
    report.duplicates !== undefined ||
    report.contradictions !== undefined ||
    report.orphans !== undefined ||
    report.broken_links !== undefined ||
    report.schema_violations !== undefined;

  return (
    <div className="space-y-4">
      {/* 요약 배지 */}
      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-xs text-slate-400 font-mono">Lint 결과:</span>
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${
            errorCount > 0
              ? 'bg-red-500/15 text-red-300 border-red-500/30'
              : 'bg-slate-800/60 text-slate-500 border-slate-700/40'
          }`}
        >
          Errors {errorCount}
        </span>
        <span
          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${
            warningCount > 0
              ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
              : 'bg-slate-800/60 text-slate-500 border-slate-700/40'
          }`}
        >
          Warnings {warningCount}
        </span>
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border bg-sky-500/10 text-sky-400 border-sky-500/20">
          Info {infoCount}
        </span>
        {s.llm_calls !== undefined && s.llm_calls > 0 && (
          <span className="text-[10px] text-slate-600 font-mono">
            LLM {s.llm_calls}회 · ${s.estimated_cost_usd?.toFixed(3) ?? '0.000'}
          </span>
        )}
        {report.report_path && (
          <span className="text-[10px] text-slate-600 font-mono ml-auto truncate">
            {report.report_path}
          </span>
        )}
      </div>

      {/* 구조화된 섹션 렌더 */}
      {hasStructuredData ? (
        <div className="space-y-2">
          <SectionBlock
            title="1. Duplicates (의미적 중복 후보)"
            items={report.duplicates ?? []}
            severity="warning"
          />
          <SectionBlock
            title="2. Contradictions (모순)"
            items={report.contradictions ?? []}
            severity="error"
          />
          <SectionBlock
            title="3. Orphans (고아 페이지)"
            items={report.orphans ?? []}
            severity="warning"
          />
          <SectionBlock
            title="4. Outdated (구식 의심)"
            items={report.outdated ?? []}
            severity="info"
          />
          <SectionBlock
            title="5. Broken Links (깨진 링크)"
            items={report.broken_links ?? []}
            severity="error"
          />
          <SectionBlock
            title="6. Schema Violations"
            items={report.schema_violations ?? []}
            severity="error"
          />
        </div>
      ) : report.report_markdown ? (
        // 마크다운 원본 fallback
        <div className="space-y-2">
          {parseSections(report.report_markdown)
            .filter((s) => s.heading.toLowerCase() !== 'summary')
            .map((section, i) => (
              <MarkdownSectionBlock key={i} section={section} />
            ))}
        </div>
      ) : (
        <div className="text-xs text-slate-500 font-mono px-2 py-4 text-center">
          보고서 내용 없음 (빈 데이터)
        </div>
      )}
    </div>
  );
}
