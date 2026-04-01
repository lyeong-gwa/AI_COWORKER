import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { NodeOutputPill } from './NodeOutputPill';
import { ExecutionStatusBadge } from './ExecutionStatusBadge';

export interface ApiStartNodeData extends Record<string, unknown> {
  nodeId: string;
  instanceName: string;
  definitionType?: string;
  inputMapping?: Record<string, string>;
  aiNodeId?: string;
  config?: {
    mode?: 'manual' | 'schedule';
    scheduleConfig?: {
      type?: string;
      hour?: number;
      minute?: number;
      dayOfWeek?: number;
      dayOfMonth?: number;
    };
    docId?: string;
    docTitle?: string;
    method?: string;
    url?: string;
    inputFields?: string[];
    defaultParams?: Record<string, any>;
  };
}

function ApiStartNodeInner({ data, selected }: { data: ApiStartNodeData; selected: boolean }) {
  const config = data.config || {};
  const mode = config.mode || 'manual';
  const hasDoc = !!config.docId;
  const method = config.method || 'GET';

  // Method badge colors
  const methodColors: Record<string, string> = {
    GET: 'bg-green-600/60 text-green-200',
    POST: 'bg-blue-600/60 text-blue-200',
    PUT: 'bg-amber-600/60 text-amber-200',
    PATCH: 'bg-orange-600/60 text-orange-200',
    DELETE: 'bg-red-600/60 text-red-200',
  };

  const execStatus = data._executionStatus as string | undefined;
  const execOutput = data._executionOutput;
  const execError = data._executionError as string | undefined;
  const execBorder = execStatus === 'running'
    ? 'border-blue-500 shadow-[0_0_12px_rgba(59,130,246,0.5)]'
    : execStatus === 'completed'
      ? 'border-green-500 shadow-[0_0_12px_rgba(34,197,94,0.3)]'
      : execStatus === 'failed'
        ? 'border-red-500 shadow-[0_0_12px_rgba(239,68,68,0.3)]'
        : 'border-teal-400';

  return (
    <div
      className={`bg-gradient-to-b from-teal-600 to-teal-800 border-2 ${execBorder} rounded-xl shadow-2xl min-w-[220px] max-w-[280px] transition-all ${
        selected ? 'ring-2 ring-teal-300 ring-offset-2 ring-offset-gray-900 scale-105' : ''
      }`}
    >
      {/* Header */}
      <div className="px-4 py-3 border-b border-white/10">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-black/30 flex items-center justify-center text-xl">
            {'\u{1F680}'}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <div className="text-xs text-teal-200/80 font-medium uppercase tracking-wider">API 시작</div>
              <span className={`px-1.5 py-0.5 text-[9px] rounded-full font-medium ${
                mode === 'schedule'
                  ? 'bg-teal-900/60 text-teal-200 border border-teal-500/50'
                  : 'bg-teal-900/40 text-teal-300 border border-teal-400/40'
              }`}>
                {mode === 'schedule' ? '스케줄' : '수동실행'}
              </span>
            </div>
            <div className="text-white font-semibold text-sm truncate">{data.instanceName}</div>
          </div>
          <ExecutionStatusBadge status={execStatus} />
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3 space-y-2">
        {hasDoc ? (
          <>
            {/* Method + Doc title */}
            <div className="flex items-center gap-2">
              <span className={`px-2 py-0.5 text-[10px] rounded-full font-bold ${methodColors[method] || 'bg-gray-600/60 text-gray-200'}`}>
                {method}
              </span>
              <span className="text-teal-200 text-xs truncate">{config.docTitle || config.docId}</span>
            </div>

            {/* URL preview */}
            {config.url && (
              <div className="text-[10px] text-teal-300/50 font-mono truncate">
                {config.url}
              </div>
            )}
          </>
        ) : (
          <div className="text-teal-300/50 text-xs text-center py-2">
            클릭하여 API 문서 선택
          </div>
        )}
      </div>

      {/* Execution output pill */}
      <NodeOutputPill status={execStatus} output={execOutput} error={execError} />

      {/* Decorative */}
      <div className="absolute -top-1 -right-1 text-teal-400/15 text-2xl pointer-events-none">{'\u{1F680}'}</div>

      {/* Output Handle (right side only - start node produces) */}
      <Handle
        type="source"
        position={Position.Right}
        id="output"
        style={{
          background: '#0d9488',
          border: '3px solid #5eead4',
          width: 16,
          height: 16,
          top: '50%',
        }}
        title="출력"
      />
    </div>
  );
}

export const ApiStartNode = memo(ApiStartNodeInner);
