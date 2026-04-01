import { memo, useContext } from 'react';
import { Handle, Position } from '@xyflow/react';
import { ConnectionDragContext } from './FactoryNode';
import { NodeOutputPill } from './NodeOutputPill';
import { ExecutionStatusBadge } from './ExecutionStatusBadge';

export interface UnpackerNodeData extends Record<string, unknown> {
  nodeId: string;
  instanceName: string;
  definitionType?: string;
  inputMapping?: Record<string, string>;
  config?: {
    arrayField?: string;
  };
}

function UnpackerNodeInner({ data, selected, id }: { data: UnpackerNodeData; selected: boolean; id: string }) {
  const connectionDrag = useContext(ConnectionDragContext);
  const isInvalidTarget = connectionDrag?.invalidTargetIds.has(id) ?? false;

  const config = data.config || {};
  const arrayField = config.arrayField || '';

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
      className={`bg-gradient-to-b ${isInvalidTarget ? 'from-red-800/80 to-red-900/80 border-red-500' : execBorder ? `from-rose-700 to-rose-900 ${execBorder}` : 'from-rose-700 to-rose-900 border-rose-400'} border-2 rounded-xl shadow-2xl min-w-[200px] max-w-[260px] transition-all ${
        selected ? 'ring-2 ring-rose-300 ring-offset-2 ring-offset-gray-900 scale-105' : ''
      }${isInvalidTarget && !execStatus ? ' animate-pulse' : ''}`}
    >
      {/* Input Handle */}
      <Handle
        type="target"
        position={Position.Left}
        id="input"
        style={{
          background: '#9f1239',
          border: '3px solid #fb7185',
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
            📤
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs text-rose-300/80 font-medium uppercase tracking-wider">언패커</div>
            <div className="text-white font-semibold text-sm truncate">{data.instanceName}</div>
          </div>
          <ExecutionStatusBadge status={execStatus} />
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3 space-y-2">
        {arrayField ? (
          <>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 text-[10px] rounded-full bg-rose-900/60 text-rose-200 border border-rose-700/50 font-mono">
                {arrayField}
              </span>
              <span className="text-rose-300/60 text-[10px]">배열 필드</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full bg-rose-400" />
              <span className="text-rose-300/60 text-[10px]">
                배열 → 개별 객체로 분배
              </span>
            </div>
          </>
        ) : (
          <div className="text-rose-300/50 text-xs text-center py-1">
            클릭하여 배열 필드 설정
          </div>
        )}
      </div>

      {/* Execution output pill */}
      <NodeOutputPill status={execStatus} output={execOutput} error={execError} />

      {/* Decorative */}
      <div className="absolute -top-1 -right-1 text-rose-400/15 text-2xl pointer-events-none">📤</div>

      {/* Output Handle */}
      <Handle
        type="source"
        position={Position.Right}
        id="output"
        style={{
          background: '#9f1239',
          border: '3px solid #fb7185',
          width: 16,
          height: 16,
          top: '50%',
        }}
        title="출력 (개별 객체)"
      />
    </div>
  );
}

export const UnpackerNode = memo(UnpackerNodeInner);
