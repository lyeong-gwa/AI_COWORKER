import React, { useState, useEffect, useCallback } from 'react';
import type { WarehouseEntry } from '../../types';

// ─── Types ────────────────────────────────────────────────────────────────────

interface WarehouseDataModalProps {
  entry: WarehouseEntry | null;
  onClose: () => void;
}

type ActiveTab = 'structure' | 'markdown';

// ─── Inline Markdown Parser ───────────────────────────────────────────────────

function parseInline(text: string): React.JSX.Element[] {
  const parts: React.JSX.Element[] = [];
  const regex = /(\*\*(.+?)\*\*|\*([^*]+?)\*|~~(.+?)~~|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let keyIdx = 0;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(<span key={keyIdx++}>{text.slice(lastIndex, match.index)}</span>);
    }
    if (match[2] !== undefined) {
      parts.push(
        <strong key={keyIdx++} className="font-semibold text-slate-100">
          {parseInline(match[2])}
        </strong>
      );
    } else if (match[3] !== undefined) {
      parts.push(
        <em key={keyIdx++} className="italic text-slate-300">
          {match[3]}
        </em>
      );
    } else if (match[4] !== undefined) {
      parts.push(
        <del key={keyIdx++} className="line-through text-slate-500">
          {match[4]}
        </del>
      );
    } else if (match[5] !== undefined) {
      parts.push(
        <code
          key={keyIdx++}
          className="px-1.5 py-0.5 rounded bg-gray-900 border border-gray-700 text-[0.8em] font-mono text-amber-300"
        >
          {match[5]}
        </code>
      );
    } else if (match[6] !== undefined && match[7] !== undefined) {
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

// ─── Token Types ──────────────────────────────────────────────────────────────

type Token =
  | { type: 'heading'; level: 1 | 2 | 3 | 4 | 5 | 6; text: string }
  | { type: 'hr' }
  | { type: 'blank' }
  | { type: 'blockquote'; lines: string[] }
  | { type: 'codeblock'; lang: string; lines: string[] }
  | { type: 'table'; header: string[]; rows: string[][] }
  | { type: 'ul'; items: string[][] }
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

    if (trimmed === '') {
      tokens.push({ type: 'blank' });
      i++;
      continue;
    }

    if (trimmed.startsWith('```')) {
      const lang = trimmed.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < rawLines.length && !rawLines[i].trim().startsWith('```')) {
        codeLines.push(rawLines[i]);
        i++;
      }
      if (i < rawLines.length) i++;
      tokens.push({ type: 'codeblock', lang, lines: codeLines });
      continue;
    }

    if (/^[-*_]{3,}$/.test(trimmed)) {
      tokens.push({ type: 'hr' });
      i++;
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      const level = Math.min(headingMatch[1].length, 6) as 1 | 2 | 3 | 4 | 5 | 6;
      tokens.push({ type: 'heading', level, text: headingMatch[2] });
      i++;
      continue;
    }

    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      const tableLines: string[] = [rawLines[i]];
      i++;
      while (i < rawLines.length && rawLines[i].trim().startsWith('|') && rawLines[i].trim().endsWith('|')) {
        tableLines.push(rawLines[i]);
        i++;
      }
      const parseRow = (row: string) =>
        row.trim().slice(1, -1).split('|').map((cell) => cell.trim());
      if (tableLines.length >= 2) {
        const header = parseRow(tableLines[0]);
        const dataStart = tableLines[1].includes('---') ? 2 : 1;
        const rows = tableLines.slice(dataStart).map(parseRow);
        tokens.push({ type: 'table', header, rows });
      }
      continue;
    }

    if (trimmed.startsWith('>')) {
      const bqLines: string[] = [];
      while (i < rawLines.length && rawLines[i].trim().startsWith('>')) {
        bqLines.push(rawLines[i].replace(/^\s*>\s?/, ''));
        i++;
      }
      tokens.push({ type: 'blockquote', lines: bqLines });
      continue;
    }

    if (/^(\s*)[-*+]\s/.test(line)) {
      const listItems: string[][] = [];
      let currentItem: string[] = [];
      while (i < rawLines.length) {
        const listLine = rawLines[i];
        const listTrimmed = listLine.trim();
        if (listTrimmed === '') { i++; break; }
        const itemMatch = listLine.match(/^(\s*)[-*+]\s(.*)$/);
        if (itemMatch) {
          if (currentItem.length > 0) listItems.push(currentItem);
          currentItem = [itemMatch[2]];
        } else if (listTrimmed && currentItem.length > 0) {
          currentItem.push(listTrimmed);
        } else {
          break;
        }
        i++;
      }
      if (currentItem.length > 0) listItems.push(currentItem);
      if (listItems.length > 0) tokens.push({ type: 'ul', items: listItems });
      continue;
    }

    if (/^\d+\.\s/.test(trimmed)) {
      const listItems: string[][] = [];
      while (i < rawLines.length && /^\d+\.\s/.test(rawLines[i].trim())) {
        listItems.push([rawLines[i].trim().replace(/^\d+\.\s/, '')]);
        i++;
      }
      if (listItems.length > 0) tokens.push({ type: 'ol', items: listItems });
      continue;
    }

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

// ─── Markdown Renderer ────────────────────────────────────────────────────────

function MarkdownRenderer({ markdown }: { markdown: string }) {
  const tokens = tokenize(markdown);

  const headingClasses: Record<number, string> = {
    1: 'text-2xl font-bold text-white mt-6 mb-3 pb-2 border-b border-gray-700',
    2: 'text-xl font-bold text-white mt-5 mb-2',
    3: 'text-lg font-semibold text-gray-100 mt-4 mb-2',
    4: 'text-base font-semibold text-gray-200 mt-3 mb-1',
    5: 'text-sm font-semibold text-gray-300 mt-2 mb-1',
    6: 'text-sm font-medium text-gray-400 mt-2 mb-1',
  };

  return (
    <div className="text-sm text-gray-300 leading-relaxed">
      {tokens.map((token, idx) => {
        switch (token.type) {
          case 'blank':
            return <div key={idx} className="h-2" />;

          case 'heading':
            return (
              <div key={idx} className={headingClasses[token.level]}>
                {parseInline(token.text)}
              </div>
            );

          case 'hr':
            return <hr key={idx} className="border-gray-700 my-4" />;

          case 'paragraph':
            return (
              <p key={idx} className="mb-3 text-gray-300 leading-relaxed">
                {parseInline(token.text)}
              </p>
            );

          case 'codeblock':
            return (
              <div key={idx} className="mb-4 rounded-lg overflow-hidden border border-gray-700">
                {token.lang && (
                  <div className="px-3 py-1 bg-gray-900 text-xs font-mono text-emerald-400 border-b border-gray-700">
                    {token.lang}
                  </div>
                )}
                <pre className="bg-gray-950 p-3 overflow-auto text-xs font-mono text-gray-300 leading-relaxed">
                  {token.lines.join('\n')}
                </pre>
              </div>
            );

          case 'blockquote':
            return (
              <blockquote
                key={idx}
                className="my-3 pl-4 border-l-4 border-emerald-500/50 bg-gray-900/50 py-2 pr-3 rounded-r-lg"
              >
                <span className="text-gray-400 italic text-sm">{token.lines.join(' ')}</span>
              </blockquote>
            );

          case 'ul':
            return (
              <ul key={idx} className="mb-3 space-y-1 pl-4">
                {token.items.map((item, iIdx) => (
                  <li key={iIdx} className="flex gap-2 text-gray-300">
                    <span className="text-emerald-400 mt-0.5 shrink-0">•</span>
                    <span>{parseInline(item.join(' '))}</span>
                  </li>
                ))}
              </ul>
            );

          case 'ol':
            return (
              <ol key={idx} className="mb-3 space-y-1 pl-4">
                {token.items.map((item, iIdx) => (
                  <li key={iIdx} className="flex gap-2 text-gray-300">
                    <span className="text-emerald-400 shrink-0 font-mono text-xs mt-0.5">{iIdx + 1}.</span>
                    <span>{parseInline(item.join(' '))}</span>
                  </li>
                ))}
              </ol>
            );

          case 'table':
            return (
              <div key={idx} className="mb-4 overflow-auto rounded-lg border border-gray-700">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-gray-900">
                      {token.header.map((h, hIdx) => (
                        <th
                          key={hIdx}
                          className="px-3 py-2 text-left font-semibold text-gray-200 border-b border-gray-700"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {token.rows.map((row, rIdx) => (
                      <tr
                        key={rIdx}
                        className={rIdx % 2 === 0 ? 'bg-gray-800/50' : 'bg-gray-900/50'}
                      >
                        {row.map((cell, cIdx) => (
                          <td
                            key={cIdx}
                            className="px-3 py-2 text-gray-300 border-b border-gray-700/50"
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

          default:
            return null;
        }
      })}
    </div>
  );
}

// ─── Markdown Extractor ───────────────────────────────────────────────────────

function extractMarkdownContent(data: Record<string, unknown>): string | null {
  if (typeof data.markdown === 'string') return data.markdown;
  if (typeof data.content === 'string' && data.content.length > 100) return data.content;
  if (typeof data._output === 'string' && data._output.length > 100) return data._output;

  // single-string-value shortcut
  const entries = Object.entries(data);
  if (entries.length === 1 && typeof entries[0][1] === 'string') {
    const val = entries[0][1] as string;
    if (val.length > 100) return val;
  }

  // longest string heuristic
  let longest: string | null = null;
  for (const [k, v] of Object.entries(data)) {
    if (k === '_passthrough' || k === 'trigger') continue;
    if (typeof v === 'string' && v.length > (longest?.length ?? 0)) {
      longest = v;
    }
  }
  if (longest && longest.length > 100) return longest;
  return null;
}

// ─── JSON Tree View ───────────────────────────────────────────────────────────

interface TreeNodeProps {
  keyName: string | null;
  value: unknown;
  depth: number;
  defaultExpanded?: boolean;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };
  return (
    <button
      onClick={handleCopy}
      className="opacity-0 group-hover:opacity-100 ml-1.5 px-1.5 py-0.5 rounded text-[10px] bg-gray-700 text-gray-400 hover:bg-gray-600 hover:text-gray-200 transition-all shrink-0"
    >
      {copied ? '✓' : '복사'}
    </button>
  );
}

function TreeNode({ keyName, value, depth, defaultExpanded = false }: TreeNodeProps) {
  const [expanded, setExpanded] = useState(defaultExpanded || depth < 2);
  const indent = depth * 16;

  const keyLabel = keyName !== null ? (
    <span className="text-blue-400 font-mono text-xs shrink-0">{keyName}:</span>
  ) : null;

  if (value === null || value === undefined) {
    return (
      <div className="flex items-center gap-1.5 py-0.5 group" style={{ paddingLeft: indent }}>
        {keyLabel}
        <span className="text-gray-500 text-xs italic">null</span>
      </div>
    );
  }

  if (typeof value === 'boolean') {
    return (
      <div className="flex items-center gap-1.5 py-0.5 group" style={{ paddingLeft: indent }}>
        {keyLabel}
        <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${value ? 'bg-purple-900/50 text-purple-300' : 'bg-gray-700/60 text-gray-400'}`}>
          {String(value)}
        </span>
        <CopyButton text={String(value)} />
      </div>
    );
  }

  if (typeof value === 'number') {
    return (
      <div className="flex items-center gap-1.5 py-0.5 group" style={{ paddingLeft: indent }}>
        {keyLabel}
        <span className="text-amber-300 text-xs font-mono px-1 py-0.5 bg-amber-900/20 rounded">
          {String(value)}
        </span>
        <CopyButton text={String(value)} />
      </div>
    );
  }

  if (typeof value === 'string') {
    const isLong = value.length > 120;
    const [showFull, setShowFull] = useState(false);
    const displayValue = isLong && !showFull ? value.slice(0, 120) + '...' : value;
    return (
      <div className="flex items-start gap-1.5 py-0.5 group" style={{ paddingLeft: indent }}>
        {keyLabel}
        <span className="text-emerald-300 text-xs font-mono break-all">
          "{displayValue}"
          {isLong && (
            <button
              onClick={() => setShowFull(!showFull)}
              className="ml-1 text-[10px] text-emerald-500 hover:text-emerald-300 underline"
            >
              {showFull ? '접기' : `+${value.length - 120}자 더 보기`}
            </button>
          )}
        </span>
        <CopyButton text={value} />
      </div>
    );
  }

  if (Array.isArray(value)) {
    return (
      <div style={{ paddingLeft: indent }}>
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1.5 py-0.5 hover:bg-gray-800/50 rounded px-1 -ml-1 w-full text-left group"
        >
          <span className="text-gray-500 text-xs">{expanded ? '▼' : '▶'}</span>
          {keyLabel}
          <span className="text-xs text-gray-400">
            Array
            <span className="ml-1 px-1.5 py-0.5 bg-gray-700 text-gray-400 rounded text-[10px]">
              {value.length}개
            </span>
          </span>
        </button>
        {expanded && (
          <div className="border-l border-gray-700/60 ml-1.5">
            {value.map((item, idx) => (
              <TreeNode key={idx} keyName={String(idx)} value={item} depth={depth + 1} />
            ))}
          </div>
        )}
      </div>
    );
  }

  if (typeof value === 'object') {
    const keys = Object.keys(value as Record<string, unknown>);
    return (
      <div style={{ paddingLeft: indent }}>
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1.5 py-0.5 hover:bg-gray-800/50 rounded px-1 -ml-1 w-full text-left group"
        >
          <span className="text-gray-500 text-xs">{expanded ? '▼' : '▶'}</span>
          {keyLabel}
          <span className="text-xs text-gray-400">
            Object
            <span className="ml-1 px-1.5 py-0.5 bg-gray-700 text-gray-400 rounded text-[10px]">
              {keys.length}개 키
            </span>
          </span>
        </button>
        {expanded && (
          <div className="border-l border-gray-700/60 ml-1.5">
            {keys.map((k) => (
              <TreeNode
                key={k}
                keyName={k}
                value={(value as Record<string, unknown>)[k]}
                depth={depth + 1}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1.5 py-0.5 group" style={{ paddingLeft: indent }}>
      {keyLabel}
      <span className="text-gray-300 text-xs font-mono">{String(value)}</span>
    </div>
  );
}

function StructureView({ data }: { data: Record<string, unknown> }) {
  const keys = Object.keys(data);
  return (
    <div className="p-4 space-y-0.5">
      {keys.length === 0 ? (
        <p className="text-gray-500 text-sm italic text-center py-8">빈 객체입니다</p>
      ) : (
        keys.map((k) => (
          <TreeNode key={k} keyName={k} value={data[k]} depth={0} defaultExpanded={true} />
        ))
      )}
    </div>
  );
}

// ─── Main Modal ───────────────────────────────────────────────────────────────

export function WarehouseDataModal({ entry, onClose }: WarehouseDataModalProps) {
  const [activeTab, setActiveTab] = useState<ActiveTab>('structure');
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (entry) {
      setVisible(false);
      requestAnimationFrame(() => {
        requestAnimationFrame(() => setVisible(true));
      });
      setActiveTab('structure');
    }
  }, [entry]);

  const handleClose = useCallback(() => {
    setVisible(false);
    setTimeout(onClose, 150);
  }, [onClose]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose();
    };
    if (entry) {
      window.addEventListener('keydown', handleKeyDown);
      return () => window.removeEventListener('keydown', handleKeyDown);
    }
  }, [entry, handleClose]);

  if (!entry) return null;

  const markdownContent = extractMarkdownContent(entry.data);
  const shortId = entry.id.length > 20 ? entry.id.slice(0, 20) + '...' : entry.id;
  const dateStr = new Date(entry.createdAt).toLocaleString('ko-KR');

  const handleCopyPlain = () => {
    navigator.clipboard.writeText(JSON.stringify(entry.data, null, 2));
  };

  const handleDownloadJson = () => {
    const blob = new Blob([JSON.stringify(entry.data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `warehouse-${entry.id.slice(0, 12)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center p-4 transition-all duration-150 ${
        visible ? 'bg-black/60 backdrop-blur-sm' : 'bg-black/0'
      }`}
      onClick={handleClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`w-full max-w-4xl max-h-[85vh] bg-gray-800 border border-gray-700 rounded-xl shadow-2xl flex flex-col transition-all duration-150 ${
          visible ? 'opacity-100 scale-100' : 'opacity-0 scale-95'
        }`}
      >
        {/* Header */}
        <div className="px-5 py-4 border-b border-gray-700 flex items-start justify-between gap-4 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-lg bg-emerald-900 flex items-center justify-center text-lg shrink-0">
              📦
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs text-emerald-400/70 uppercase tracking-wider">창고 데이터</span>
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="font-mono text-sm text-gray-200 truncate">{shortId}</span>
                {entry.executionId && (
                  <span className="text-[10px] text-gray-500 bg-gray-700/50 px-1.5 py-0.5 rounded truncate max-w-[160px]">
                    실행: {entry.executionId.slice(0, 16)}
                  </span>
                )}
              </div>
              <div className="text-[11px] text-gray-500 mt-0.5">{dateStr}</div>
            </div>
          </div>
          <button
            onClick={handleClose}
            className="text-gray-500 hover:text-white text-xl p-1 shrink-0 transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Tab bar */}
        <div className="px-5 border-b border-gray-700 flex gap-1 shrink-0">
          <button
            onClick={() => setActiveTab('structure')}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
              activeTab === 'structure'
                ? 'border-emerald-500 text-emerald-400'
                : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
          >
            구조 보기
          </button>
          <button
            onClick={() => setActiveTab('markdown')}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px flex items-center gap-1.5 ${
              activeTab === 'markdown'
                ? 'border-emerald-500 text-emerald-400'
                : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
          >
            MD 프리뷰
            {markdownContent && (
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
            )}
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto min-h-0">
          {activeTab === 'structure' && (
            <StructureView data={entry.data} />
          )}
          {activeTab === 'markdown' && (
            <div className="p-5">
              {markdownContent ? (
                <MarkdownRenderer markdown={markdownContent} />
              ) : (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <div className="text-3xl mb-3">📄</div>
                  <p className="text-gray-400 text-sm">마크다운 콘텐츠를 찾을 수 없습니다</p>
                  <p className="text-gray-600 text-xs mt-1">
                    "markdown", "content" 키 또는 긴 문자열 값이 없습니다
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-gray-700 flex items-center justify-between gap-3 shrink-0">
          <div className="text-xs text-gray-600">
            {Object.keys(entry.data).length}개 키
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyPlain}
              className="px-3 py-1.5 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600 text-xs transition-colors flex items-center gap-1.5"
            >
              📋 복사
            </button>
            <button
              onClick={handleDownloadJson}
              className="px-3 py-1.5 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600 text-xs transition-colors flex items-center gap-1.5"
            >
              JSON 다운로드
            </button>
            <button
              onClick={handleClose}
              className="px-3 py-1.5 bg-emerald-800/50 text-emerald-300 border border-emerald-700/50 rounded-lg hover:bg-emerald-800 text-xs transition-colors"
            >
              닫기
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
