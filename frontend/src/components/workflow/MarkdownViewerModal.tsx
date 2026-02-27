import { useState, useEffect, useCallback, useRef } from 'react';
import { factoryApi } from '../../services/api';
import type { WarehouseEntry } from '../../types';

// ─── Types ────────────────────────────────────────────────────────────────────

interface MarkdownViewerModalProps {
  isOpen: boolean;
  onClose: () => void;
  resultNodeId: string;
  resultNodeName: string;
  onReExecute: () => void;
}

type ActiveTab = 'rendered' | 'raw';

// ─── Helpers ──────────────────────────────────────────────────────────────────



// ─── Markdown Extraction ──────────────────────────────────────────────────────

function extractMarkdown(outputData: unknown): string | null {
  if (!outputData) return null;
  if (typeof outputData === 'string') return outputData;
  if (typeof outputData === 'object') {
    const data = outputData as Record<string, unknown>;
    // 1순위: 'markdown' 키를 직접 확인
    if (typeof data.markdown === 'string') return data.markdown;
    // 2순위: '_output' 키 확인 (비-dict 출력인 경우)
    if (typeof data._output === 'string') return data._output;
    // 3순위: 가장 긴 문자열 값을 마크다운으로 추정 (짧은 필드 무시)
    let longest: string | null = null;
    for (const [k, value] of Object.entries(data)) {
      if (k === '_passthrough' || k === 'trigger') continue;
      if (typeof value === 'string' && value.length > (longest?.length ?? 0)) {
        longest = value;
      }
    }
    if (longest && longest.length > 50) return longest;
  }
  return null;
}

// ─── Inline Markdown Parser ───────────────────────────────────────────────────

/**
 * Parse inline markdown: **bold**, *italic*, ~~strike~~, `code`, [link](url)
 */
function parseInline(text: string): JSX.Element[] {
  const parts: JSX.Element[] = [];
  // Combined regex for inline elements
  const regex = /(\*\*(.+?)\*\*|\*([^*]+?)\*|~~(.+?)~~|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let keyIdx = 0;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(<span key={keyIdx++}>{text.slice(lastIndex, match.index)}</span>);
    }

    if (match[2] !== undefined) {
      // **bold**
      parts.push(
        <strong key={keyIdx++} className="font-semibold text-slate-100">
          {parseInline(match[2])}
        </strong>
      );
    } else if (match[3] !== undefined) {
      // *italic*
      parts.push(
        <em key={keyIdx++} className="italic text-slate-300">
          {match[3]}
        </em>
      );
    } else if (match[4] !== undefined) {
      // ~~strikethrough~~
      parts.push(
        <del key={keyIdx++} className="line-through text-slate-500">
          {match[4]}
        </del>
      );
    } else if (match[5] !== undefined) {
      // `inline code`
      parts.push(
        <code
          key={keyIdx++}
          className="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-[0.8em] font-mono text-amber-300"
        >
          {match[5]}
        </code>
      );
    } else if (match[6] !== undefined && match[7] !== undefined) {
      // [text](url)
      parts.push(
        <a
          key={keyIdx++}
          href={match[7]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-400 hover:text-blue-300 underline underline-offset-2 transition-colors"
        >
          {match[6]}
        </a>
      );
    }

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(<span key={keyIdx++}>{text.slice(lastIndex)}</span>);
  }

  return parts;
}

// ─── Block-Level Token Types ──────────────────────────────────────────────────

type Token =
  | { type: 'heading'; level: 1 | 2 | 3 | 4; text: string }
  | { type: 'hr' }
  | { type: 'blank' }
  | { type: 'blockquote'; lines: string[] }
  | { type: 'codeblock'; lang: string; lines: string[] }
  | { type: 'table'; header: string[]; rows: string[][] }
  | { type: 'image'; alt: string; url: string }
  | { type: 'ul'; items: string[][]; indent: number }
  | { type: 'ol'; items: string[][] }
  | { type: 'paragraph'; text: string };

// ─── Tokenizer ────────────────────────────────────────────────────────────────

function tokenize(markdown: string): Token[] {
  const rawLines = markdown.split('\n');
  const tokens: Token[] = [];
  let i = 0;

  while (i < rawLines.length) {
    const line = rawLines[i];
    const trimmed = line.trim();

    // Blank line
    if (trimmed === '') {
      tokens.push({ type: 'blank' });
      i++;
      continue;
    }

    // Code block: ```lang
    if (trimmed.startsWith('```')) {
      const lang = trimmed.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < rawLines.length && !rawLines[i].trim().startsWith('```')) {
        codeLines.push(rawLines[i]);
        i++;
      }
      if (i < rawLines.length) i++; // skip closing ```
      tokens.push({ type: 'codeblock', lang, lines: codeLines });
      continue;
    }

    // Horizontal rule: ---, ***, ___
    if (/^[-*_]{3,}$/.test(trimmed)) {
      tokens.push({ type: 'hr' });
      i++;
      continue;
    }

    // Heading: # to ####
    const headingMatch = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (headingMatch) {
      const level = Math.min(headingMatch[1].length, 4) as 1 | 2 | 3 | 4;
      tokens.push({ type: 'heading', level, text: headingMatch[2] });
      i++;
      continue;
    }

    // Image: ![alt](url)
    const imageMatch = trimmed.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
    if (imageMatch) {
      tokens.push({ type: 'image', alt: imageMatch[1], url: imageMatch[2] });
      i++;
      continue;
    }

    // Table: starts with |
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      const tableLines: string[] = [rawLines[i]];
      i++;
      while (i < rawLines.length && rawLines[i].trim().startsWith('|') && rawLines[i].trim().endsWith('|')) {
        tableLines.push(rawLines[i]);
        i++;
      }

      const parseRow = (row: string) =>
        row
          .trim()
          .slice(1, -1)
          .split('|')
          .map((cell) => cell.trim());

      if (tableLines.length >= 2) {
        const header = parseRow(tableLines[0]);
        // Skip separator row (contains ---)
        const dataStart = tableLines[1].includes('---') ? 2 : 1;
        const rows = tableLines.slice(dataStart).map(parseRow);
        tokens.push({ type: 'table', header, rows });
      }
      continue;
    }

    // Blockquote: lines starting with >
    if (trimmed.startsWith('>')) {
      const bqLines: string[] = [];
      while (i < rawLines.length && rawLines[i].trim().startsWith('>')) {
        bqLines.push(rawLines[i].replace(/^\s*>\s?/, ''));
        i++;
      }
      tokens.push({ type: 'blockquote', lines: bqLines });
      continue;
    }

    // Unordered list: -, *, +
    if (/^(\s*)[-*+]\s/.test(line)) {
      const indent = (line.match(/^(\s*)/) || ['', ''])[1].length;
      const listItems: string[][] = [];
      let currentItem: string[] = [];

      while (i < rawLines.length) {
        const listLine = rawLines[i];
        const listTrimmed = listLine.trim();
        if (listTrimmed === '') {
          i++;
          break;
        }
        const itemMatch = listLine.match(/^(\s*)[-*+]\s(.*)$/);
        if (itemMatch) {
          if (currentItem.length > 0) listItems.push(currentItem);
          currentItem = [itemMatch[2]];
        } else if (listTrimmed && currentItem.length > 0) {
          // continuation line
          currentItem.push(listTrimmed);
        } else {
          break;
        }
        i++;
      }
      if (currentItem.length > 0) listItems.push(currentItem);
      if (listItems.length > 0) tokens.push({ type: 'ul', items: listItems, indent });
      continue;
    }

    // Ordered list: 1. 2. etc.
    if (/^\d+\.\s/.test(trimmed)) {
      const listItems: string[][] = [];
      while (i < rawLines.length && /^\d+\.\s/.test(rawLines[i].trim())) {
        const itemText = rawLines[i].trim().replace(/^\d+\.\s/, '');
        listItems.push([itemText]);
        i++;
      }
      if (listItems.length > 0) tokens.push({ type: 'ol', items: listItems });
      continue;
    }

    // Paragraph (merge consecutive non-special lines)
    const paraLines: string[] = [];
    while (
      i < rawLines.length &&
      rawLines[i].trim() !== '' &&
      !rawLines[i].trim().startsWith('#') &&
      !rawLines[i].trim().startsWith('```') &&
      !rawLines[i].trim().startsWith('>') &&
      !/^[-*_]{3,}$/.test(rawLines[i].trim()) &&
      !rawLines[i].trim().startsWith('|') &&
      !/^(\s*)[-*+]\s/.test(rawLines[i]) &&
      !/^\d+\.\s/.test(rawLines[i].trim())
    ) {
      paraLines.push(rawLines[i].trim());
      i++;
    }
    if (paraLines.length > 0) {
      tokens.push({ type: 'paragraph', text: paraLines.join(' ') });
    }
  }

  return tokens;
}

// ─── Diff Line Highlighting ───────────────────────────────────────────────────

function renderDiffLine(line: string, idx: number): JSX.Element {
  if (line.startsWith('+') && !line.startsWith('+++')) {
    return (
      <div key={idx} className="bg-emerald-900/40 text-emerald-300 px-3 py-0.5 leading-relaxed">
        {line}
      </div>
    );
  }
  if (line.startsWith('-') && !line.startsWith('---')) {
    return (
      <div key={idx} className="bg-red-900/40 text-red-300 px-3 py-0.5 leading-relaxed">
        {line}
      </div>
    );
  }
  if (line.startsWith('@')) {
    return (
      <div key={idx} className="bg-blue-900/30 text-blue-300 px-3 py-0.5 leading-relaxed font-semibold">
        {line}
      </div>
    );
  }
  return (
    <div key={idx} className="text-slate-300 px-3 py-0.5 leading-relaxed">
      {line}
    </div>
  );
}

// ─── Blockquote Content Parser ────────────────────────────────────────────────

/**
 * Render blockquote content, detecting callout-style prefixes like
 * 🔵 **[Info]**, 🟢 **[OK]**, 🔴 **[Error]**, etc.
 */
function renderBlockquoteContent(lines: string[], keyBase: number): JSX.Element {
  const fullText = lines.join('\n');

  // Detect callout patterns: emoji + **[Label]**
  const calloutMatch = fullText.match(/^([\u{1F300}-\u{1FAFF}🔵🔴🟢🟡🟠⚪⚫🔶🔷])\s*\*\*\[([^\]]+)\]\*\*\s*([\s\S]*)$/u);

  if (calloutMatch) {
    const emoji = calloutMatch[1];
    const label = calloutMatch[2];
    const rest = calloutMatch[3].trim();

    // Color-code by label type
    const colorMap: Record<string, { border: string; bg: string; badge: string; text: string }> = {
      info:    { border: 'border-blue-500/60',    bg: 'bg-blue-950/40',   badge: 'bg-blue-900/60 text-blue-300 border-blue-700/50',   text: 'text-blue-100' },
      Info:    { border: 'border-blue-500/60',    bg: 'bg-blue-950/40',   badge: 'bg-blue-900/60 text-blue-300 border-blue-700/50',   text: 'text-blue-100' },
      ok:      { border: 'border-emerald-500/60', bg: 'bg-emerald-950/40',badge: 'bg-emerald-900/60 text-emerald-300 border-emerald-700/50', text: 'text-emerald-100' },
      OK:      { border: 'border-emerald-500/60', bg: 'bg-emerald-950/40',badge: 'bg-emerald-900/60 text-emerald-300 border-emerald-700/50', text: 'text-emerald-100' },
      warning: { border: 'border-amber-500/60',   bg: 'bg-amber-950/40',  badge: 'bg-amber-900/60 text-amber-300 border-amber-700/50',    text: 'text-amber-100' },
      Warning: { border: 'border-amber-500/60',   bg: 'bg-amber-950/40',  badge: 'bg-amber-900/60 text-amber-300 border-amber-700/50',    text: 'text-amber-100' },
      error:   { border: 'border-red-500/60',     bg: 'bg-red-950/40',    badge: 'bg-red-900/60 text-red-300 border-red-700/50',          text: 'text-red-100' },
      Error:   { border: 'border-red-500/60',     bg: 'bg-red-950/40',    badge: 'bg-red-900/60 text-red-300 border-red-700/50',          text: 'text-red-100' },
      tip:     { border: 'border-purple-500/60',  bg: 'bg-purple-950/40', badge: 'bg-purple-900/60 text-purple-300 border-purple-700/50', text: 'text-purple-100' },
      Tip:     { border: 'border-purple-500/60',  bg: 'bg-purple-950/40', badge: 'bg-purple-900/60 text-purple-300 border-purple-700/50', text: 'text-purple-100' },
    };

    const colors = colorMap[label] || colorMap['info'];

    return (
      <div
        key={keyBase}
        className={`rounded-lg border-l-4 ${colors.border} ${colors.bg} px-4 py-3 flex gap-3 items-start`}
      >
        <span className="text-lg leading-none pt-0.5 shrink-0">{emoji}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <span
              className={`text-xs font-semibold px-2 py-0.5 rounded border ${colors.badge}`}
            >
              {label}
            </span>
          </div>
          {rest && (
            <p className={`text-sm leading-relaxed ${colors.text}`}>
              {parseInline(rest)}
            </p>
          )}
        </div>
      </div>
    );
  }

  // Standard blockquote
  return (
    <div
      key={keyBase}
      className="border-l-4 border-indigo-500/50 bg-indigo-950/30 pl-4 pr-3 py-2.5 rounded-r-lg"
    >
      {lines.map((bqLine, li) => (
        <p key={li} className="text-sm text-slate-300 leading-relaxed italic">
          {parseInline(bqLine)}
        </p>
      ))}
    </div>
  );
}

// ─── Full Markdown Renderer ───────────────────────────────────────────────────

function renderMarkdown(markdown: string): JSX.Element {
  const tokens = tokenize(markdown);
  const elements: JSX.Element[] = [];
  let prevType: string | null = null;

  tokens.forEach((token, idx) => {
    if (token.type === 'blank') {
      prevType = 'blank';
      return;
    }

    const needsExtraGap = prevType !== null && prevType !== 'blank' && idx > 0;

    switch (token.type) {
      case 'heading': {
        const sizeCls =
          token.level === 1
            ? 'text-2xl font-bold text-slate-100 border-b border-slate-700/60 pb-2 mt-2'
            : token.level === 2
            ? 'text-xl font-bold text-slate-200 border-b border-slate-700/40 pb-1.5'
            : token.level === 3
            ? 'text-base font-bold text-slate-200'
            : 'text-sm font-semibold text-slate-300';
        const Tag = `h${token.level}` as keyof JSX.IntrinsicElements;
        elements.push(
          <Tag
            key={idx}
            className={`${sizeCls} ${needsExtraGap ? 'mt-5' : 'mt-1'} leading-tight`}
          >
            {parseInline(token.text)}
          </Tag>
        );
        break;
      }

      case 'hr':
        elements.push(
          <hr key={idx} className="border-slate-700/60 my-1" />
        );
        break;

      case 'codeblock': {
        const isDiff = ['diff', 'patch'].includes(token.lang) ||
          token.lines.some((l) => (l.startsWith('+') || l.startsWith('-')) && !l.startsWith('+++') && !l.startsWith('---'));
        elements.push(
          <div
            key={idx}
            className="rounded-xl overflow-hidden border border-slate-700/70 shadow-lg"
          >
            {/* Code block header */}
            <div className="flex items-center justify-between px-4 py-2 bg-slate-900/80 border-b border-slate-700/70">
              <div className="flex items-center gap-2">
                <div className="flex gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
                  <div className="w-2.5 h-2.5 rounded-full bg-amber-500/60" />
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/60" />
                </div>
                {token.lang && (
                  <span className="text-xs font-mono text-slate-500 ml-1">{token.lang}</span>
                )}
              </div>
              {isDiff && (
                <span className="text-[10px] text-slate-600 font-medium uppercase tracking-wider">diff</span>
              )}
            </div>
            {/* Code content */}
            <div className="text-[13px] font-mono overflow-x-auto bg-slate-950/50">
              {isDiff
                ? token.lines.map((l, li) => renderDiffLine(l, li))
                : (
                  <pre className="px-4 py-3 text-slate-300 leading-relaxed whitespace-pre-wrap break-all">
                    {token.lines.join('\n')}
                  </pre>
                )}
            </div>
          </div>
        );
        break;
      }

      case 'blockquote':
        elements.push(renderBlockquoteContent(token.lines, idx));
        break;

      case 'table': {
        elements.push(
          <div key={idx} className="overflow-x-auto rounded-xl border border-slate-700/60">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-slate-800/80">
                  {token.header.map((cell, ci) => (
                    <th
                      key={ci}
                      className="px-4 py-2.5 text-left text-xs font-semibold text-slate-300 uppercase tracking-wide border-b border-slate-700/60"
                    >
                      {parseInline(cell)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {token.rows.map((row, ri) => (
                  <tr
                    key={ri}
                    className={ri % 2 === 0 ? 'bg-slate-900/20' : 'bg-slate-800/20'}
                  >
                    {row.map((cell, ci) => (
                      <td
                        key={ci}
                        className="px-4 py-2 text-slate-300 border-b border-slate-700/30 last:border-b-0 leading-relaxed"
                      >
                        {parseInline(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
        break;
      }

      case 'image':
        elements.push(
          <div
            key={idx}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/60 border border-slate-700/50 text-slate-500 text-sm"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <path d="m21 15-5-5L5 21" />
            </svg>
            <span className="italic">{token.alt || '이미지'}</span>
          </div>
        );
        break;

      case 'ul':
        elements.push(
          <ul key={idx} className="space-y-1">
            {token.items.map((item, ii) => (
              <li key={ii} className="flex items-start gap-2.5 text-sm text-slate-300 leading-relaxed">
                <span className="mt-2 w-1.5 h-1.5 rounded-full bg-slate-500 shrink-0" />
                <span>{parseInline(item.join(' '))}</span>
              </li>
            ))}
          </ul>
        );
        break;

      case 'ol':
        elements.push(
          <ol key={idx} className="space-y-1">
            {token.items.map((item, ii) => (
              <li key={ii} className="flex items-start gap-2.5 text-sm text-slate-300 leading-relaxed">
                <span className="shrink-0 w-5 h-5 rounded-full bg-slate-700/70 border border-slate-600/50 flex items-center justify-center text-[10px] font-semibold text-slate-400 mt-0.5">
                  {ii + 1}
                </span>
                <span className="flex-1">{parseInline(item.join(' '))}</span>
              </li>
            ))}
          </ol>
        );
        break;

      case 'paragraph':
        elements.push(
          <p key={idx} className="text-sm text-slate-300 leading-relaxed">
            {parseInline(token.text)}
          </p>
        );
        break;
    }

    prevType = token.type;
  });

  if (elements.length === 0) {
    return (
      <p className="text-sm text-slate-500 italic text-center py-8">
        내용 없음
      </p>
    );
  }

  return <div className="space-y-3">{elements}</div>;
}

// ─── Component ────────────────────────────────────────────────────────────────

function MarkdownViewerModal({
  isOpen,
  onClose,
  resultNodeId,
  resultNodeName,
  onReExecute,
}: MarkdownViewerModalProps) {
  const [activeTab, setActiveTab] = useState<ActiveTab>('rendered');
  const [entries, setEntries] = useState<WarehouseEntry[]>([]);
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const contentRef = useRef<HTMLDivElement>(null);

  // Load warehouse entries on open
  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    setError(null);
    setCopied(false);

    factoryApi
      .getWarehouse(resultNodeId, 50)
      .then((result) => {
        // Sort by newest first
        const sorted = [...result.items].sort(
          (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
        );
        setEntries(sorted);
        // Auto-select the first (newest) entry
        if (sorted.length > 0) {
          setSelectedEntryId(sorted[0].id);
        }
      })
      .catch((err: Error) => {
        setError(err.message || '창고 데이터를 불러오지 못했습니다.');
      })
      .finally(() => setLoading(false));
  }, [isOpen, resultNodeId]);

  // Escape key handler
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Backdrop click
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose]
  );

  // Get selected warehouse entry
  const selectedEntry = entries.find((e) => e.id === selectedEntryId) ?? null;
  const rawOutput = selectedEntry?.data ?? null;
  const markdownText = rawOutput != null ? extractMarkdown(rawOutput) : null;
  const hasError = rawOutput != null && markdownText === null;

  // Copy markdown to clipboard
  const handleCopy = useCallback(() => {
    const text = markdownText ?? '';
    navigator.clipboard
      .writeText(text)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => {/* ignore */});
  }, [markdownText]);

  // Download as .md file
  const handleDownload = useCallback(() => {
    if (!markdownText) return;
    const blob = new Blob([markdownText], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${resultNodeName.replace(/\s+/g, '-')}-output.md`;
    a.click();
    URL.revokeObjectURL(url);
  }, [markdownText, resultNodeName]);

  if (!isOpen) return null;

  // ─── Loading state ─────────────────────────────────────────────────────────

  const renderLoading = () => (
    <div className="flex flex-col items-center justify-center py-24 gap-4">
      <div className="relative w-10 h-10">
        <div className="absolute inset-0 rounded-full border-2 border-slate-700" />
        <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-indigo-500 animate-spin" />
      </div>
      <p className="text-slate-500 text-sm">불러오는 중...</p>
    </div>
  );

  // ─── Error state ───────────────────────────────────────────────────────────

  const renderError = () => (
    <div className="flex flex-col items-center justify-center py-20 gap-3">
      <div className="w-12 h-12 rounded-xl bg-red-900/30 border border-red-700/50 flex items-center justify-center text-red-400 text-2xl">
        ✕
      </div>
      <p className="text-red-400 text-sm">{error}</p>
    </div>
  );

  // ─── No data state ─────────────────────────────────────────────────────────

  const renderNoData = () => (
    <div className="flex flex-col items-center justify-center py-24 gap-4">
      <div className="w-16 h-16 rounded-2xl bg-slate-800/60 border border-slate-700/50 flex items-center justify-center">
        <svg className="w-8 h-8 text-slate-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M9 12h6M9 16h6M9 8h3M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" />
        </svg>
      </div>
      <div className="text-center">
        <p className="text-slate-400 text-sm font-medium">아직 실행 결과가 없습니다</p>
        <p className="text-slate-600 text-xs mt-1">워크플로우를 실행하면 마크다운이 여기에 렌더링됩니다</p>
      </div>
      <button
        onClick={onReExecute}
        className="mt-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors"
      >
        지금 실행
      </button>
    </div>
  );

  // ─── Rendered markdown tab ─────────────────────────────────────────────────

  const renderMarkdownTab = () => {
    if (loading) return renderLoading();
    if (error) return renderError();
    if (hasError) {
      return (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <div className="w-12 h-12 rounded-xl bg-amber-900/30 border border-amber-700/50 flex items-center justify-center text-amber-400 text-2xl">
            ⚠
          </div>
          <p className="text-amber-400 text-sm font-medium">마크다운 텍스트를 찾을 수 없습니다</p>
          <p className="text-slate-600 text-xs">원본 데이터 탭에서 내용을 확인하세요</p>
        </div>
      );
    }
    if (!markdownText) return renderNoData();

    return (
      <div
        ref={contentRef}
        className="px-8 py-6"
      >
        {renderMarkdown(markdownText)}
      </div>
    );
  };

  // ─── Raw JSON tab ──────────────────────────────────────────────────────────

  const renderRawTab = () => {
    if (loading) return renderLoading();
    if (error) return renderError();
    if (!rawOutput) return renderNoData();

    return (
      <div className="px-6 py-5">
        <pre className="text-xs font-mono text-slate-300 whitespace-pre-wrap break-all leading-relaxed bg-slate-950/40 rounded-xl border border-slate-700/50 p-5 overflow-auto">
          {JSON.stringify(rawOutput, null, 2)}
        </pre>
      </div>
    );
  };

  // ─── Main render ───────────────────────────────────────────────────────────

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={handleBackdropClick}
    >
      <div
        className="bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl w-full max-w-4xl mx-4 flex flex-col max-h-[90vh]"
        style={{ boxShadow: '0 25px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(148,163,184,0.08)' }}
      >
        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700/60 shrink-0">
          <div className="flex items-center gap-3">
            {/* Document icon */}
            <div className="w-9 h-9 rounded-xl bg-indigo-900/40 border border-indigo-700/40 flex items-center justify-center shrink-0">
              <svg className="w-4.5 h-4.5 text-indigo-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M9 12h6M9 16h6M9 8h3M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z" />
              </svg>
            </div>
            <div>
              <h2 className="text-sm font-semibold text-slate-100 leading-tight">마크다운 뷰어</h2>
              <p className="text-xs text-slate-500 leading-tight mt-0.5 truncate max-w-xs">{resultNodeName}</p>
            </div>
          </div>

          {/* Action buttons + close */}
          <div className="flex items-center gap-2">
            {markdownText && (
              <>
                <button
                  onClick={handleCopy}
                  title="마크다운 복사"
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700/60 text-slate-400 hover:text-slate-200 text-xs font-medium transition-all"
                >
                  {copied ? (
                    <>
                      <svg className="w-3.5 h-3.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M20 6L9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                      <span className="text-emerald-400">복사됨</span>
                    </>
                  ) : (
                    <>
                      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <rect x="9" y="9" width="13" height="13" rx="2" />
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                      </svg>
                      복사
                    </>
                  )}
                </button>
                <button
                  onClick={handleDownload}
                  title=".md 파일 다운로드"
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700/60 text-slate-400 hover:text-slate-200 text-xs font-medium transition-all"
                >
                  <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M12 15V3m0 12-4-4m4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M2 17l.621 2.485A2 2 0 0 0 4.561 21h14.878a2 2 0 0 0 1.94-1.515L22 17" strokeLinecap="round" />
                  </svg>
                  다운로드
                </button>
              </>
            )}

            <div className="w-px h-5 bg-slate-700/60 mx-1" />

            <button
              onClick={onClose}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-all"
              title="닫기"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6 6 18M6 6l12 12" strokeLinecap="round" />
              </svg>
            </button>
          </div>
        </div>

        {/* ── Entry selector bar ──────────────────────────────────────────── */}
        {entries.length > 0 && (
          <div className="flex items-center gap-3 px-6 py-2.5 bg-slate-800/50 border-b border-slate-700/40 shrink-0">
            <span className="text-xs text-slate-500 shrink-0">보고서</span>
            <select
              value={selectedEntryId ?? ''}
              onChange={(e) => setSelectedEntryId(e.target.value)}
              className="flex-1 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-300 px-3 py-1.5 focus:outline-none focus:border-indigo-500 transition-colors"
            >
              {entries.map((entry, idx) => {
                const md = extractMarkdown(entry.data);
                const date = new Date(entry.createdAt).toLocaleString('ko-KR', {
                  month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                });
                const label = md
                  ? `#${entries.length - idx} — ${date}`
                  : `#${entries.length - idx} — ${date} (데이터 없음)`;
                return (
                  <option key={entry.id} value={entry.id}>
                    {label}
                  </option>
                );
              })}
            </select>
            <span className="text-xs text-slate-600 shrink-0">
              {entries.length}개 보관중
            </span>
          </div>
        )}

        {/* ── Tabs ───────────────────────────────────────────────────────── */}
        <div className="flex border-b border-slate-700/60 shrink-0 px-2">
          <button
            onClick={() => setActiveTab('rendered')}
            className={`relative flex items-center gap-2 px-4 py-3 text-xs font-medium transition-colors ${
              activeTab === 'rendered'
                ? 'text-indigo-400'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M4 6h16M4 10h16M4 14h10M4 18h8" strokeLinecap="round" />
            </svg>
            마크다운 보기
            {activeTab === 'rendered' && (
              <span className="absolute bottom-0 left-2 right-2 h-0.5 bg-indigo-500 rounded-full" />
            )}
          </button>
          <button
            onClick={() => setActiveTab('raw')}
            className={`relative flex items-center gap-2 px-4 py-3 text-xs font-medium transition-colors ${
              activeTab === 'raw'
                ? 'text-indigo-400'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="m16 18 6-6-6-6M8 6l-6 6 6 6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            원본 데이터
            {activeTab === 'raw' && (
              <span className="absolute bottom-0 left-2 right-2 h-0.5 bg-indigo-500 rounded-full" />
            )}
          </button>
        </div>

        {/* ── Content area ───────────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {activeTab === 'rendered' ? renderMarkdownTab() : renderRawTab()}
        </div>

        {/* ── Footer ─────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-end gap-2 px-6 py-3.5 border-t border-slate-700/60 bg-slate-900/60 rounded-b-2xl shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700/60 text-slate-300 text-sm font-medium transition-all"
          >
            닫기
          </button>
          <button
            onClick={onReExecute}
            className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-all shadow-lg shadow-indigo-900/30"
          >
            재실행
          </button>
        </div>
      </div>
    </div>
  );
}

export { MarkdownViewerModal };
export default MarkdownViewerModal;
