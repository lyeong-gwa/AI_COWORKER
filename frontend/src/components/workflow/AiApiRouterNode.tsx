import { memo, useContext } from 'react';
import { Handle, Position } from '@xyflow/react';
import { ConnectionDragContext } from './FactoryNode';
import { NodeOutputPill } from './NodeOutputPill';
import { ExecutionStatusBadge } from './ExecutionStatusBadge';

export interface AiApiRouterNodeData extends Record<string, unknown> {
  nodeId: string;
  instanceName: string;
  definitionType?: string;
  inputMapping?: Record<string, string>;
  config?: {
    prompt?: string;
    apiIds?: string[];
  };
}

function AiApiRouterNodeInner({ data, selected, id }: { data: AiApiRouterNodeData; selected: boolean; id: string }) {
  const connectionDrag = useContext(ConnectionDragContext);
  const isInvalidTarget = connectionDrag?.invalidTargetIds.has(id) ?? false;

  const config = data.config || {};
  const apiCount = config.apiIds?.length || 0;

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
      className={`bg-gradient-to-b ${isInvalidTarget ? 'from-red-800/80 to-red-900/80 border-red-500' : execBorder ? `from-purple-700 to-purple-900 ${execBorder}` : 'from-purple-700 to-purple-900 border-purple-400'} border-2 rounded-xl shadow-2xl min-w-[220px] max-w-[280px] transition-all ${
        selected ? 'ring-2 ring-purple-300 ring-offset-2 ring-offset-gray-900 scale-105' : ''
      }${isInvalidTarget && !execStatus ? ' animate-pulse' : ''}`}
    >
      {/* Input Handle */}
      <Handle
        type="target"
        position={Position.Left}
        id="input"
        style={{
          background: '#6d28d9',
          border: '3px solid #7c3aed',
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
            🤖
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs text-purple-300/80 font-medium uppercase tracking-wider">AI API 라우터</div>
            <div className="text-white font-semibold text-sm truncate">{data.instanceName}</div>
          </div>
          <ExecutionStatusBadge status={execStatus} />
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3 space-y-2">
        {/* API scope */}
        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 text-[10px] rounded-full font-bold bg-purple-600/60 text-purple-200">
            {apiCount > 0 ? `${apiCount}개 API 대상` : '전체 API 대상'}
          </span>
        </div>

        {/* Summary */}
        <div className="text-[10px] text-purple-300/60 leading-relaxed">
          AI가 입력을 분석하여 적절한 API를 자동 호출합니다
        </div>

        {/* Prompt preview */}
        {config.prompt && (
          <div className="text-[10px] text-purple-200/50 font-mono truncate border-t border-white/10 pt-1">
            {config.prompt.slice(0, 60)}{config.prompt.length > 60 ? '…' : ''}
          </div>
        )}

        {/* Output fields */}
        <div className="flex items-center gap-1.5 pt-1 border-t border-white/10">
          <div className="w-2 h-2 rounded-full bg-purple-400" />
          <span className="text-purple-300/60 text-[10px]">
            출력: 원본 입력 + api_route (판단/요청/응답)
          </span>
        </div>
      </div>

      {/* Execution output pill */}
      <NodeOutputPill status={execStatus} output={execOutput} error={execError} />

      {/* Decorative */}
      <div className="absolute -top-1 -right-1 text-purple-400/15 text-2xl pointer-events-none">🤖</div>

      {/* Output Handle */}
      <Handle
        type="source"
        position={Position.Right}
        id="output"
        style={{
          background: '#6d28d9',
          border: '3px solid #7c3aed',
          width: 16,
          height: 16,
          top: '50%',
        }}
        title="출력"
      />
    </div>
  );
}

export const AiApiRouterNode = memo(AiApiRouterNodeInner);
