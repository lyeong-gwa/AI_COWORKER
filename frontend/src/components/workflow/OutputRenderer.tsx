/* eslint-disable react-refresh/only-export-components */
import React from 'react';

// ─── Key label formatter ──────────────────────────────────────────────────────

export function formatKeyLabel(key: string): string {
  if (key.startsWith('wfn-')) {
    const rest = key.slice(4);
    return rest.charAt(0).toUpperCase() + rest.slice(1);
  }
  return key.charAt(0).toUpperCase() + key.slice(1);
}

// ─── Inline markdown parser ───────────────────────────────────────────────────

function parseInlineMarkdown(line: string): React.JSX.Element[] {
  const parts: React.JSX.Element[] = [];
  const regex = /(\*\*(.+?)\*\*|`([^`]+)`)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(line)) !== null) {
    if (match.index > lastIndex) {
      parts.push(<span key={lastIndex}>{line.slice(lastIndex, match.index)}</span>);
    }
    if (match[2]) {
      parts.push(<strong key={match.index} className="font-semibold text-gray-100">{match[2]}</strong>);
    } else if (match[3]) {
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

// ─── Text content renderer ────────────────────────────────────────────────────

export function renderTextContent(text: string): React.JSX.Element {
  const lines = text.split('\n');
  const elements: React.JSX.Element[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed === '') {
      i++;
      continue;
    }

    if (trimmed.startsWith('```')) {
      const lang = trimmed.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++;
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

    if (/^[-*_]{3,}$/.test(trimmed)) {
      elements.push(<hr key={`hr-${i}`} className="border-gray-700 my-2" />);
      i++;
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const headingText = headingMatch[2];
      const className = level === 1
        ? 'text-sm font-bold text-blue-400 mt-3 mb-1'
        : level === 2
        ? 'text-xs font-bold text-blue-300 mt-2 mb-1'
        : 'text-xs font-semibold text-purple-300 mt-1.5 mb-0.5';
      const Tag = `h${level + 2}` as keyof React.JSX.IntrinsicElements;
      elements.push(
        <Tag key={`h-${i}`} className={className}>
          {parseInlineMarkdown(headingText)}
        </Tag>
      );
      i++;
      continue;
    }

    if (/^\d+\.\s/.test(trimmed)) {
      const listItems: React.JSX.Element[] = [];
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

    if (/^[-*]\s/.test(trimmed)) {
      const listItems: React.JSX.Element[] = [];
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

// ─── Array content renderer ───────────────────────────────────────────────────

export function renderArrayContent(arr: unknown[]): React.JSX.Element {
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

// ─── Single value renderer ────────────────────────────────────────────────────

export function renderValue(value: unknown): React.JSX.Element {
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

// ─── Main output renderer ─────────────────────────────────────────────────────

export function renderOutputData(data: unknown): React.JSX.Element {
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

    if (entries.length === 1 && typeof entries[0][1] === 'string') {
      return renderTextContent(entries[0][1] as string);
    }

    if (entries.length === 1 && typeof entries[0][1] === 'object' && !Array.isArray(entries[0][1])) {
      const inner = Object.entries(entries[0][1] as Record<string, unknown>).filter(
        ([, v]) => v !== null && v !== undefined
      );
      if (inner.length === 1 && typeof inner[0][1] === 'string') {
        return renderTextContent(inner[0][1] as string);
      }
    }

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

  return (
    <pre className="text-xs text-gray-200 font-mono whitespace-pre-wrap break-all">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

// ─── Plain text extractor ─────────────────────────────────────────────────────

export function getPlainText(data: unknown): string {
  if (data === null || data === undefined) return '';

  if (typeof data === 'string') return data;

  if (typeof data === 'object' && !Array.isArray(data)) {
    const entries = Object.entries(data as Record<string, unknown>).filter(
      ([k, v]) => v !== null && v !== undefined && k !== 'trigger'
    );
    if (entries.length === 1 && typeof entries[0][1] === 'string') {
      return entries[0][1] as string;
    }
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

// ─── Component wrapper ────────────────────────────────────────────────────────

interface OutputRendererProps {
  data: unknown;
  className?: string;
}

export function OutputRenderer({ data, className }: OutputRendererProps) {
  return (
    <div className={className}>
      {renderOutputData(data)}
    </div>
  );
}

export default OutputRenderer;
