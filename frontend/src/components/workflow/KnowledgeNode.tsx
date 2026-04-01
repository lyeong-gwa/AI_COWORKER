import { memo, useContext } from 'react';
import { Handle, Position } from '@xyflow/react';
import { ConnectionDragContext } from './FactoryNode';
import { NodeOutputPill } from './NodeOutputPill';
import { ExecutionStatusBadge } from './ExecutionStatusBadge';

export interface KnowledgeNodeData extends Record<string, unknown> {
  nodeId: string;
  instanceName: string;
  definitionType?: string;
  inputMapping?: Record<string, string>;
  aiNodeId?: string;
  config?: {
    searchField?: string;
    category?: string;
    tags?: string[];
    maxResults?: number;
    matchCount?: number;
  };
}

function KnowledgeNodeInner({ data, selected, id }: { data: KnowledgeNodeData; selected: boolean; id: string }) {
  const connectionDrag = useContext(ConnectionDragContext);
  const isInvalidTarget = connectionDrag?.invalidTargetIds.has(id) ?? false;

  const config = data.config || {};
  const hasSearchField = !!config.searchField;
  const maxResults = config.maxResults || 5;

  // Build filter summary
  const filterParts: string[] = [];
  if (config.category) filterParts.push(config.category);
  if (config.tags && config.tags.length > 0) filterParts.push(config.tags.join(', '));

  const execStatus = data._executionStatus as string | undefined;
  const execOutput = data._executionOutput;
  const execError = data._executionError as string | undefined;
  const execBorder = execStatus === 'running'
    ? 'border-blue-500 shadow-[0_0_12px_rgba(59,130,246,0.5)]'
    : execStatus === 'completed'
      ? 'border-green-500 shadow-[0_0_12px_rgba(34,197,94,0.3)]'
      : execStatus === 'failed'
        ? 'border-red-500 shadow-[0_0_12px_rgba(239,68,68,0.3)]'
        : '';

  return (
    <div
      className={`bg-gradient-to-b ${isInvalidTarget ? 'from-red-800/80 to-red-900/80 border-red-500' : execBorder ? `from-indigo-600 to-indigo-800 ${execBorder}` : 'from-indigo-600 to-indigo-800 border-indigo-400'} border-2 rounded-xl shadow-2xl min-w-[220px] max-w-[280px] transition-all ${
        selected ? 'ring-2 ring-indigo-300 ring-offset-2 ring-offset-gray-900 scale-105' : ''
      }${isInvalidTarget && !execStatus ? ' animate-pulse' : ''}`}
    >
      {/* Input Handle */}
      <Handle
        type="target"
        position={Position.Left}
        id="input"
        style={{
          background: '#4338ca',
          border: '3px solid #a5b4fc',
          width: 16,
          height: 16,
          top: '50%',
        }}
        title="입력"
      />

      {/* Header */}
      <div className="px-4 py-3 border-b border-white/10">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-black/30 flex items-center justify-center text-xl">
            {'\u{1F4DA}'}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs text-indigo-300/80 font-medium uppercase tracking-wider">지식 검색</div>
            <div className="text-white font-semibold text-sm truncate">{data.instanceName}</div>
          </div>
          <ExecutionStatusBadge status={execStatus} />
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3 space-y-2">
        {/* Search field */}
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${hasSearchField ? 'bg-indigo-400' : 'bg-gray-500 animate-pulse'}`} />
          <span className="text-indigo-200/80 text-xs">
            {hasSearchField ? (
              <>검색: <span className="font-mono text-indigo-300">{config.searchField}</span></>
            ) : (
              '검색 필드 미설정'
            )}
          </span>
        </div>

        {/* Filter summary */}
        {(filterParts.length > 0 || (config.matchCount != null && config.matchCount > 0)) && (
          <div className="flex flex-wrap gap-1">
            {filterParts.map((part, i) => (
              <span key={i} className="px-1.5 py-0.5 text-[9px] rounded bg-indigo-900/60 text-indigo-300 border border-indigo-700/50">
                {part}
              </span>
            ))}
            {config.matchCount != null && config.matchCount > 0 && (
              <span className="px-1.5 py-0.5 text-[9px] rounded bg-emerald-900/60 text-emerald-300 border border-emerald-700/50">
                {config.matchCount}건 매칭
              </span>
            )}
          </div>
        )}

        {/* Result count */}
        <div className="flex items-center gap-1.5 pt-1 border-t border-white/10">
          <div className="w-2 h-2 rounded-full bg-indigo-400" />
          <span className="text-indigo-300/60 text-[10px]">
            {config.matchCount != null && config.matchCount > 0
              ? `${config.matchCount}건 중 최대 ${maxResults}개`
              : `최대 ${maxResults}개 결과`}
          </span>
        </div>
      </div>

      {/* Execution output pill */}
      <NodeOutputPill status={execStatus} output={execOutput} error={execError} />

      {/* Decorative */}
      <div className="absolute -top-1 -right-1 text-indigo-400/15 text-2xl pointer-events-none">{'\u{1F4DA}'}</div>

      {/* Output Handle */}
      <Handle
        type="source"
        position={Position.Right}
        id="output"
        style={{
          background: '#4338ca',
          border: '3px solid #a5b4fc',
          width: 16,
          height: 16,
          top: '50%',
        }}
        title="출력"
      />
    </div>
  );
}

export const KnowledgeNode = memo(KnowledgeNodeInner);
