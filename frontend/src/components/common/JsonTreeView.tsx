/**
 * JsonTreeView — 재사용 가능한 JSON 트리 뷰어 (dark theme).
 *
 * EdgeInspectorPanel 의 TreeNode/TreeView 로직을 추출한 컴포넌트.
 * NodeInspectorDrawer 와 EdgeInspectorPanel 양쪽에서 import 하여 사용.
 *
 * 시각/동작은 추출 이전과 동치.
 */
import { useState } from 'react';

interface TreeNodeProps {
  label: string;
  value: unknown;
  depth: number;
  maxDepth: number;
}

function TreeNode({ label, value, depth, maxDepth }: TreeNodeProps) {
  // depth 가 maxDepth 미만이면 펼친 상태로 시작
  const [open, setOpen] = useState(depth < maxDepth);
  const isExpandable = value !== null && typeof value === 'object';
  const indent = depth * 12;

  if (!isExpandable) {
    const display =
      value === null || value === undefined
        ? <span className="text-gray-500 italic">null</span>
        : typeof value === 'string'
        ? <span className="text-green-400">"{value.length > 80 ? value.slice(0, 77) + '...' : value}"</span>
        : typeof value === 'number'
        ? <span className="text-yellow-400">{String(value)}</span>
        : typeof value === 'boolean'
        ? <span className="text-blue-400">{String(value)}</span>
        : <span className="text-gray-300">{String(value)}</span>;

    return (
      <div className="flex gap-1 py-0.5 text-[11px] font-mono" style={{ paddingLeft: indent + 4 }}>
        <span className="text-gray-500 shrink-0">{label}:</span>
        {display}
      </div>
    );
  }

  const isArray = Array.isArray(value);
  const entries = isArray
    ? (value as unknown[]).map((v, i) => [String(i), v] as [string, unknown])
    : Object.entries(value as Record<string, unknown>);

  const summary = isArray
    ? `[${entries.length}]`
    : `{${entries.length}}`;

  return (
    <div style={{ paddingLeft: indent }}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 py-0.5 text-[11px] font-mono hover:bg-gray-800/40 rounded px-1 w-full text-left"
      >
        <span className="text-gray-600 w-3 shrink-0 text-center">{open ? '▾' : '▸'}</span>
        <span className="text-gray-400 shrink-0">{label}:</span>
        <span className="text-gray-500 ml-1">{summary}</span>
      </button>
      {open && (
        <div className="border-l border-gray-700/50 ml-1.5">
          {entries.map(([k, v]) => (
            <TreeNode key={k} label={k} value={v} depth={depth + 1} maxDepth={maxDepth} />
          ))}
        </div>
      )}
    </div>
  );
}

export interface JsonTreeViewProps {
  /** 표시할 데이터 (object/array/primitive 모두 가능) */
  data: unknown;
  /**
   * 기본 펼침 동작 — true 이면 root 의 직접 자식까지 펼친다.
   * false 면 root 만 표시 (자식 닫힘).
   * 기본값: true (이전 EdgeInspectorPanel TreeView 동작과 동일 — depth 0 펼침)
   */
  defaultExpanded?: boolean;
  /**
   * 최대 펼침 깊이 — depth < maxDepth 이면 자동 펼침.
   * 기본값: 1 (root 의 직접 자식까지)
   */
  maxDepth?: number;
}

export function JsonTreeView({ data, defaultExpanded = true, maxDepth = 1 }: JsonTreeViewProps) {
  if (data === null || data === undefined) {
    return <p className="text-xs text-gray-500 italic">데이터 없음</p>;
  }
  if (typeof data !== 'object') {
    return <p className="text-xs text-gray-300 font-mono">{String(data)}</p>;
  }

  const entries = Array.isArray(data)
    ? (data as unknown[]).map((v, i) => [String(i), v] as [string, unknown])
    : Object.entries(data as Record<string, unknown>);

  if (entries.length === 0) {
    return <p className="text-xs text-gray-500 italic">{Array.isArray(data) ? '빈 배열' : '빈 객체'}</p>;
  }

  // defaultExpanded=false 이면 root 자식들도 닫혀서 시작 (depth 0 < 0 = false)
  const effectiveMaxDepth = defaultExpanded ? maxDepth : 0;

  return (
    <div className="space-y-0.5">
      {entries.map(([k, v]) => (
        <TreeNode key={k} label={k} value={v} depth={0} maxDepth={effectiveMaxDepth} />
      ))}
    </div>
  );
}

export default JsonTreeView;
