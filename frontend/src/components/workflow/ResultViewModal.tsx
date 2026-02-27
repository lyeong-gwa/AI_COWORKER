import { useState, useEffect, useCallback } from 'react';
import { factoryApi } from '../../services/api';
import type { WorkflowExecution } from '../../services/api';

// ─── Types ───────────────────────────────────────────────────────────────────

interface ResultViewModalProps {
  isOpen: boolean;
  onClose: () => void;
  resultNodeId: string;
  resultNodeName: string;
  onReExecute: () => void;
}

type ActiveTab = 'latest' | 'history';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatDuration(startedAt?: string, completedAt?: string): string {
  if (!startedAt) return '-';
  const start = new Date(startedAt).getTime();
  const end = completedAt ? new Date(completedAt).getTime() : Date.now();
  const diffMs = end - start;
  if (diffMs < 1000) return `${diffMs}ms`;
  if (diffMs < 60000) return `${(diffMs / 1000).toFixed(1)}s`;
  return `${Math.floor(diffMs / 60000)}m ${Math.floor((diffMs % 60000) / 1000)}s`;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString('ko-KR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function getStatusBadge(status: WorkflowExecution['status']): {
  icon: string;
  label: string;
  className: string;
} {
  switch (status) {
    case 'completed':
      return { icon: '✅', label: '완료', className: 'bg-green-900/40 text-green-400 border border-green-700/50' };
    case 'failed':
      return { icon: '❌', label: '실패', className: 'bg-red-900/40 text-red-400 border border-red-700/50' };
    case 'running':
      return { icon: '⏳', label: '실행 중', className: 'bg-blue-900/40 text-blue-400 border border-blue-700/50' };
    case 'pending':
      return { icon: '⏳', label: '대기 중', className: 'bg-gray-700/60 text-gray-400 border border-gray-600/50' };
    case 'cancelled':
      return { icon: '🚫', label: '취소됨', className: 'bg-gray-700/60 text-gray-400 border border-gray-600/50' };
    default:
      return { icon: '?', label: status, className: 'bg-gray-700/60 text-gray-400 border border-gray-600/50' };
  }
}

// ─── Output Rendering Helpers ─────────────────────────────────────────────────

/**
 * Format a key name into a readable label.
 * Keys starting with "wfn-" get the prefix stripped and the rest capitalized.
 * Other keys get their first letter capitalized.
 */
function formatKeyLabel(key: string): string {
  if (key.startsWith('wfn-')) {
    const rest = key.slice(4);
    return rest.charAt(0).toUpperCase() + rest.slice(1);
  }
  return key.charAt(0).toUpperCase() + key.slice(1);
}

/**
 * Parse a single line of text and apply inline markdown-like formatting.
 * Supports **bold** syntax.
 */
function parseInlineMarkdown(line: string): JSX.Element[] {
  const parts: JSX.Element[] = [];
  // Match **bold** and `inline code`
  const regex = /(\*\*(.+?)\*\*|`([^`]+)`)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(line)) !== null) {
    if (match.index > lastIndex) {
      parts.push(<span key={lastIndex}>{line.slice(lastIndex, match.index)}</span>);
    }
    if (match[2]) {
      // **bold**
      parts.push(<strong key={match.index} className="font-semibold text-gray-100">{match[2]}</strong>);
    } else if (match[3]) {
      // `inline code`
      parts.push(
        <code key={match.index} className="px-1 py-0.5 bg-gray-900 border border-gray-700 rounded text-xs font-mono text-red-300">
          {match[3]}
        </code>
      );
    }
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < line.length) {
    parts.push(<span key={lastIndex}>{line.slice(lastIndex)}</span>);
  }

  return parts;
}

/**
 * Render a string value as formatted text.
 * Handles paragraphs, bullet points, and numbered lists.
 * Supports **bold** inline markdown.
 */
function renderTextContent(text: string): JSX.Element {
  const lines = text.split('\n');
  const elements: JSX.Element[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // Skip empty lines between blocks (they act as paragraph separators)
    if (trimmed === '') {
      i++;
      continue;
    }

    // Code block: ```
    if (trimmed.startsWith('```')) {
      const lang = trimmed.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++; // skip closing ```
      elements.push(
        <div key={`code-${i}`} className="rounded-lg overflow-hidden border border-gray-700">
          {lang && (
            <div className="px-3 py-1 bg-gray-900 text-[10px] text-gray-500 border-b border-gray-700 font-mono">
              {lang}
            </div>
          )}
          <pre className="px-3 py-2 bg-gray-900/60 text-xs text-gray-200 font-mono whitespace-pre-wrap overflow-x-auto">
            {codeLines.join('\n')}
          </pre>
        </div>
      );
      continue;
    }

    // Horizontal rule: ---, ***, ___
    if (/^[-*_]{3,}$/.test(trimmed)) {
      elements.push(<hr key={`hr-${i}`} className="border-gray-700 my-2" />);
      i++;
      continue;
    }

    // Heading: #, ##, ###
    const headingMatch = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const text = headingMatch[2];
      const className = level === 1
        ? 'text-sm font-bold text-blue-400 mt-3 mb-1'
        : level === 2
        ? 'text-xs font-bold text-blue-300 mt-2 mb-1'
        : 'text-xs font-semibold text-purple-300 mt-1.5 mb-0.5';
      const Tag = `h${level + 2}` as keyof JSX.IntrinsicElements;
      elements.push(
        <Tag key={`h-${i}`} className={className}>
          {parseInlineMarkdown(text)}
        </Tag>
      );
      i++;
      continue;
    }

    // Numbered list item: "1. ...", "2. ...", etc.
    if (/^\d+\.\s/.test(trimmed)) {
      const listItems: JSX.Element[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i].trim())) {
        const itemText = lines[i].trim().replace(/^\d+\.\s/, '');
        listItems.push(
          <li key={i} className="ml-4">
            {parseInlineMarkdown(itemText)}
          </li>
        );
        i++;
      }
      elements.push(
        <ol key={`ol-${i}`} className="list-decimal list-inside space-y-0.5 text-xs text-gray-200">
          {listItems}
        </ol>
      );
      continue;
    }

    // Bullet point: "- ..." or "* ..."
    if (/^[-*]\s/.test(trimmed)) {
      const listItems: JSX.Element[] = [];
      while (i < lines.length && /^[-*]\s/.test(lines[i].trim())) {
        const itemText = lines[i].trim().replace(/^[-*]\s/, '');
        listItems.push(
          <li key={i} className="ml-4">
            {parseInlineMarkdown(itemText)}
          </li>
        );
        i++;
      }
      elements.push(
        <ul key={`ul-${i}`} className="list-disc list-inside space-y-0.5 text-xs text-gray-200">
          {listItems}
        </ul>
      );
      continue;
    }

    // Regular paragraph line
    elements.push(
      <p key={i} className="text-xs text-gray-200 leading-relaxed">
        {parseInlineMarkdown(trimmed)}
      </p>
    );
    i++;
  }

  if (elements.length === 0) {
    return <p className="text-xs text-gray-500 italic">빈 결과</p>;
  }

  return <div className="space-y-1.5">{elements}</div>;
}

/**
 * Render an array value as a list.
 */
function renderArrayContent(arr: unknown[]): JSX.Element {
  if (arr.length === 0) {
    return <p className="text-xs text-gray-500 italic">빈 배열</p>;
  }

  return (
    <ul className="list-disc list-inside space-y-1 text-xs text-gray-200">
      {arr.map((item, idx) => (
        <li key={idx} className="ml-2">
          {typeof item === 'string' ? item : JSON.stringify(item)}
        </li>
      ))}
    </ul>
  );
}

/**
 * Render a single value (used inside object rendering).
 */
function renderValue(value: unknown): JSX.Element {
  if (value === null || value === undefined) {
    return <p className="text-xs text-gray-500 italic">null</p>;
  }
  if (typeof value === 'string') {
    return renderTextContent(value);
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return <p className="text-xs text-gray-200 font-mono">{String(value)}</p>;
  }
  if (Array.isArray(value)) {
    return renderArrayContent(value);
  }
  if (typeof value === 'object') {
    // Unwrap single-string objects (e.g., {"markdown": "..."})
    const entries = Object.entries(value as Record<string, unknown>).filter(
      ([, v]) => v !== null && v !== undefined
    );
    if (entries.length === 1 && typeof entries[0][1] === 'string') {
      return renderTextContent(entries[0][1] as string);
    }
    return (
      <pre className="text-xs text-gray-200 font-mono whitespace-pre-wrap break-all bg-gray-900/40 rounded p-2">
        {JSON.stringify(value, null, 2)}
      </pre>
    );
  }
  return (
    <pre className="text-xs text-gray-200 font-mono whitespace-pre-wrap break-all">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

/**
 * Main output renderer. Handles all cases:
 * - null/undefined → "데이터 없음"
 * - string → formatted text
 * - object with single string value → unwrap and render text directly
 * - object with multiple entries → labeled sections
 * - array → list
 * - fallback → raw JSON pre block
 */
function renderOutputData(data: unknown): JSX.Element {
  if (data === null || data === undefined) {
    return <p className="text-xs text-gray-500 italic">데이터 없음</p>;
  }

  if (typeof data === 'string') {
    return renderTextContent(data);
  }

  if (typeof data === 'object' && !Array.isArray(data)) {
    const entries = Object.entries(data as Record<string, unknown>).filter(
      ([k, v]) => v !== null && v !== undefined && k !== 'trigger'
    );

    if (entries.length === 0) {
      return <p className="text-xs text-gray-500 italic">빈 결과</p>;
    }

    // Single string value → unwrap and render directly (common case: {"wfn-diagnosis": "..."})
    if (entries.length === 1 && typeof entries[0][1] === 'string') {
      return renderTextContent(entries[0][1] as string);
    }

    // Single nested object with single string value → unwrap twice
    // (e.g., {"cr-reviewer": {"markdown": "..."}})
    if (entries.length === 1 && typeof entries[0][1] === 'object' && !Array.isArray(entries[0][1])) {
      const inner = Object.entries(entries[0][1] as Record<string, unknown>).filter(
        ([, v]) => v !== null && v !== undefined
      );
      if (inner.length === 1 && typeof inner[0][1] === 'string') {
        return renderTextContent(inner[0][1] as string);
      }
    }

    // Multiple entries → labeled sections
    return (
      <div className="space-y-3">
        {entries.map(([key, value]) => (
          <div key={key}>
            <div className="text-xs font-medium text-gray-400 mb-1">{formatKeyLabel(key)}</div>
            {renderValue(value)}
          </div>
        ))}
      </div>
    );
  }

  if (Array.isArray(data)) {
    return renderArrayContent(data);
  }

  // Fallback
  return (
    <pre className="text-xs text-gray-200 font-mono whitespace-pre-wrap break-all">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

/**
 * Extract plain text from output data for clipboard copy.
 * When the data is an object with a single string value, unwrap it.
 * Otherwise fall back to JSON.
 */
function getPlainText(data: unknown): string {
  if (data === null || data === undefined) return '';

  if (typeof data === 'string') return data;

  if (typeof data === 'object' && !Array.isArray(data)) {
    const entries = Object.entries(data as Record<string, unknown>).filter(
      ([k, v]) => v !== null && v !== undefined && k !== 'trigger'
    );
    if (entries.length === 1 && typeof entries[0][1] === 'string') {
      return entries[0][1] as string;
    }
    // Unwrap nested single-string objects
    if (entries.length === 1 && typeof entries[0][1] === 'object' && !Array.isArray(entries[0][1])) {
      const inner = Object.entries(entries[0][1] as Record<string, unknown>).filter(
        ([, v]) => v !== null && v !== undefined
      );
      if (inner.length === 1 && typeof inner[0][1] === 'string') {
        return inner[0][1] as string;
      }
    }
  }

  return JSON.stringify(data, null, 2);
}

// ─── Component ───────────────────────────────────────────────────────────────

function ResultViewModal({
  isOpen,
  onClose,
  resultNodeId,
  resultNodeName,
  onReExecute,
}: ResultViewModalProps) {
  const [activeTab, setActiveTab] = useState<ActiveTab>('latest');
  const [executions, setExecutions] = useState<WorkflowExecution[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedHistoryId, setExpandedHistoryId] = useState<string | null>(null);
  const [inputCollapsed, setInputCollapsed] = useState(true);
  const [copied, setCopied] = useState(false);

  // Load executions on open
  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    setError(null);
    setExpandedHistoryId(null);
    setCopied(false);

    factoryApi
      .listExecutions()
      .then((data) => {
        // Sort newest first
        const sorted = [...data].sort(
          (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
        );
        setExecutions(sorted);
      })
      .catch((err: Error) => {
        setError(err.message || '실행 이력을 불러오지 못했습니다.');
      })
      .finally(() => setLoading(false));
  }, [isOpen]);

  // Escape key handler
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Backdrop click handler
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose]
  );

  // Copy to clipboard - extracts plain text when possible
  const handleCopy = useCallback((data: unknown) => {
    navigator.clipboard
      .writeText(getPlainText(data))
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => {/* ignore */});
  }, []);

  // Download JSON file
  const handleDownload = useCallback((data: unknown, filename: string) => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  // Toggle history item
  const handleToggleHistory = useCallback((id: string) => {
    setExpandedHistoryId((prev) => (prev === id ? null : id));
  }, []);

  if (!isOpen) return null;

  // Find most recent completed execution
  const latestCompleted = executions.find((e) => e.status === 'completed') ?? null;

  // Extract result node output from an execution
  function getNodeOutput(execution: WorkflowExecution): unknown {
    const results = execution.nodeResults as Record<string, { outputData?: unknown }>;
    return results[resultNodeId]?.outputData ?? null;
  }

  // ─── Tab: Latest Result ─────────────────────────────────────────────────

  const renderLatestTab = () => {
    if (loading) {
      return (
        <div className="flex items-center justify-center py-16 text-gray-500 text-sm">
          <svg className="animate-spin h-5 w-5 mr-2" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          불러오는 중...
        </div>
      );
    }

    if (error) {
      return (
        <div className="py-10 text-center text-red-400 text-sm">
          <p>{error}</p>
        </div>
      );
    }

    if (!latestCompleted) {
      return (
        <div className="py-16 text-center text-gray-500 text-sm">
          <p className="text-3xl mb-3">📭</p>
          <p>아직 실행 결과가 없습니다.</p>
          <p className="text-xs mt-1 text-gray-600">워크플로우를 실행한 후 결과를 확인할 수 있습니다.</p>
        </div>
      );
    }

    const badge = getStatusBadge(latestCompleted.status);
    const nodeOutput = getNodeOutput(latestCompleted);

    return (
      <div className="space-y-4">
        {/* Execution info box */}
        <div className="bg-gray-900/60 border border-gray-700 rounded-lg p-4 flex flex-wrap gap-4 text-sm">
          <div className="flex items-center gap-2">
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${badge.className}`}>
              {badge.icon} {badge.label}
            </span>
          </div>
          <div className="flex items-center gap-1.5 text-gray-400">
            <span className="text-gray-500">소요 시간</span>
            <span className="text-gray-200 font-mono text-xs">
              {formatDuration(latestCompleted.startedAt, latestCompleted.completedAt)}
            </span>
          </div>
          <div className="flex items-center gap-1.5 text-gray-400">
            <span className="text-gray-500">실행 일시</span>
            <span className="text-gray-200 text-xs">
              {formatDate(latestCompleted.createdAt)}
            </span>
          </div>
        </div>

        {/* Input Data - collapsible */}
        <div className="border border-gray-700 rounded-lg overflow-hidden">
          <button
            onClick={() => setInputCollapsed((p) => !p)}
            className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-900/40 hover:bg-gray-900/70 transition-colors text-left"
          >
            <span className="text-sm font-medium text-gray-300">입력 데이터</span>
            <span className="text-gray-500 text-xs">{inputCollapsed ? '펼치기 ▾' : '접기 ▴'}</span>
          </button>
          {!inputCollapsed && (
            <div className="px-4 py-3 bg-gray-900/20">
              <pre className="text-xs text-gray-300 font-mono whitespace-pre-wrap break-all overflow-auto max-h-48">
                {JSON.stringify(latestCompleted.inputData, null, 2)}
              </pre>
            </div>
          )}
        </div>

        {/* Result Data */}
        <div className="border border-gray-700 rounded-lg overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2.5 bg-gray-900/40">
            <span className="text-sm font-medium text-gray-300">결과 데이터</span>
            <span className="text-xs text-gray-500 truncate ml-2">{resultNodeName}</span>
          </div>
          <div className="px-4 py-3 bg-gray-900/20 overflow-auto max-h-[50vh]">
            {nodeOutput !== null ? (
              renderOutputData(nodeOutput)
            ) : (
              <p className="text-xs text-gray-500 italic">
                해당 노드의 출력 데이터가 없습니다.
              </p>
            )}
          </div>
        </div>

        {/* Action buttons */}
        {nodeOutput !== null && (
          <div className="flex items-center gap-2 pt-1">
            <button
              onClick={() => handleCopy(nodeOutput)}
              className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs font-medium rounded-lg transition-colors"
            >
              {copied ? '복사됨 ✓' : '결과 복사'}
            </button>
            <button
              onClick={() =>
                handleDownload(
                  nodeOutput,
                  `result-${resultNodeId}-${latestCompleted.id.slice(0, 8)}.json`
                )
              }
              className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs font-medium rounded-lg transition-colors"
            >
              JSON 다운로드
            </button>
          </div>
        )}
      </div>
    );
  };

  // ─── Tab: Execution History ─────────────────────────────────────────────

  const renderHistoryTab = () => {
    if (loading) {
      return (
        <div className="flex items-center justify-center py-16 text-gray-500 text-sm">
          <svg className="animate-spin h-5 w-5 mr-2" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          불러오는 중...
        </div>
      );
    }

    if (error) {
      return (
        <div className="py-10 text-center text-red-400 text-sm">
          <p>{error}</p>
        </div>
      );
    }

    if (executions.length === 0) {
      return (
        <div className="py-16 text-center text-gray-500 text-sm">
          <p className="text-3xl mb-3">📋</p>
          <p>실행 이력이 없습니다.</p>
        </div>
      );
    }

    return (
      <div className="space-y-2">
        {executions.map((execution, idx) => {
          const badge = getStatusBadge(execution.status);
          const isExpanded = expandedHistoryId === execution.id;
          const nodeOutput = getNodeOutput(execution);

          return (
            <div
              key={execution.id}
              className="border border-gray-700 rounded-lg overflow-hidden"
            >
              {/* Row header */}
              <button
                onClick={() => handleToggleHistory(execution.id)}
                className="w-full flex items-center gap-3 px-4 py-3 bg-gray-900/30 hover:bg-gray-900/60 transition-colors text-left"
              >
                <span className="text-gray-600 text-xs font-mono w-5 shrink-0">
                  #{executions.length - idx}
                </span>
                <span className={`px-2 py-0.5 rounded text-xs font-medium shrink-0 ${badge.className}`}>
                  {badge.icon} {badge.label}
                </span>
                <span className="text-gray-400 text-xs flex-1 truncate">
                  {formatDate(execution.createdAt)}
                </span>
                <span className="text-gray-500 text-xs font-mono shrink-0">
                  {formatDuration(execution.startedAt, execution.completedAt)}
                </span>
                <span className="text-gray-600 text-xs shrink-0">
                  {isExpanded ? '▴' : '▾'}
                </span>
              </button>

              {/* Expanded content */}
              {isExpanded && (
                <div className="px-4 py-3 bg-gray-900/20 border-t border-gray-700/60">
                  {nodeOutput !== null ? (
                    <>
                      <p className="text-xs text-gray-500 mb-1.5 font-medium">
                        {resultNodeName} 출력
                      </p>
                      <div className="overflow-auto max-h-48">
                        {renderOutputData(nodeOutput)}
                      </div>
                    </>
                  ) : execution.status === 'failed' && execution.errorMessage ? (
                    <div className="text-xs text-red-400">
                      <p className="font-medium mb-1">오류 메시지</p>
                      <p className="font-mono">{execution.errorMessage}</p>
                    </div>
                  ) : (
                    <p className="text-xs text-gray-500 italic">
                      해당 노드의 출력 데이터가 없습니다.
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  // ─── Main render ────────────────────────────────────────────────────────

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={handleBackdropClick}
    >
      <div className="bg-gray-800 border border-gray-700 rounded-xl shadow-2xl w-full max-w-2xl mx-4 flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700 shrink-0">
          <div>
            <h2 className="text-lg font-semibold text-white">실행 결과</h2>
            <p className="text-xs text-gray-500 mt-0.5 truncate max-w-xs">{resultNodeName}</p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-300 transition-colors text-xl leading-none"
            title="닫기"
          >
            &times;
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-700 shrink-0">
          <button
            onClick={() => setActiveTab('latest')}
            className={`flex-1 px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === 'latest'
                ? 'text-blue-400 border-b-2 border-blue-400 bg-gray-800'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            최신 결과
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={`flex-1 px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === 'history'
                ? 'text-blue-400 border-b-2 border-blue-400 bg-gray-800'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            실행 이력
            {executions.length > 0 && (
              <span className="ml-1.5 text-xs text-gray-500">({executions.length})</span>
            )}
          </button>
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {activeTab === 'latest' ? renderLatestTab() : renderHistoryTab()}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-gray-700 shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 text-sm font-medium rounded-lg transition-colors"
          >
            닫기
          </button>
          <button
            onClick={onReExecute}
            className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            재실행
          </button>
        </div>
      </div>
    </div>
  );
}

export { ResultViewModal };
export default ResultViewModal;
