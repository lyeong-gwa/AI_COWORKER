import { memo, useContext } from 'react';
import { Handle, Position } from '@xyflow/react';
import { ConnectionDragContext } from './FactoryNode';
import { NodeOutputPill } from './NodeOutputPill';
import { ExecutionStatusBadge } from './ExecutionStatusBadge';

export interface MapperNodeData extends Record<string, unknown> {
  nodeId: string;
  instanceName: string;
  definitionType?: string;
  inputMapping?: Record<string, string>;
  config?: {
    warehouseNodeId?: string;
    warehouseNodeName?: string;
    matchKey?: string;
    outputField?: string;
  };
}

function MapperNodeInner({ data, selected, id }: { data: MapperNodeData; selected: boolean; id: string }) {
  const connectionDrag = useContext(ConnectionDragContext);
  const isInvalidTarget = connectionDrag?.invalidTargetIds.has(id) ?? false;

  const config = data.config || {};
  const matchKey = config.matchKey || '';
  const warehouseNodeName = config.warehouseNodeName || '';
  const outputField = config.outputField || 'matchedItems';

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
      className={`bg-gradient-to-b ${isInvalidTarget ? 'from-red-800/80 to-red-900/80 border-red-500' : execBorder ? `from-indigo-700 to-indigo-900 ${execBorder}` : 'from-indigo-700 to-indigo-900 border-indigo-400'} border-2 rounded-xl shadow-2xl min-w-[200px] max-w-[260px] transition-all ${
        selected ? 'ring-2 ring-indigo-300 ring-offset-2 ring-offset-gray-900 scale-105' : ''
      }${isInvalidTarget && !execStatus ? ' animate-pulse' : ''}`}
    >
      {/* Input Handle */}
      <Handle
        type="target"
        position={Position.Left}
        id="input"
        style={{
          background: '#3730a3',
          border: '3px solid #818cf8',
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
            🔗
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs text-indigo-300/80 font-medium uppercase tracking-wider">매퍼</div>
            <div className="text-white font-semibold text-sm truncate">{data.instanceName}</div>
          </div>
          <ExecutionStatusBadge status={execStatus} />
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3 space-y-2">
        {matchKey ? (
          <>
            {warehouseNodeName && (
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] text-indigo-300/60">창고:</span>
                <span className="px-2 py-0.5 text-[10px] rounded-full bg-indigo-900/60 text-indigo-200 border border-indigo-700/50 truncate max-w-[150px]">
                  {warehouseNodeName}
                </span>
              </div>
            )}
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-indigo-300/60">매칭 키:</span>
              <span className="px-2 py-0.5 text-[10px] rounded-full bg-indigo-900/60 text-indigo-200 border border-indigo-700/50 font-mono">
                {matchKey}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full bg-indigo-400" />
              <span className="text-indigo-300/60 text-[10px]">
                → {outputField} 으로 병합
              </span>
            </div>
          </>
        ) : (
          <div className="text-indigo-300/50 text-xs text-center py-1">
            클릭하여 매퍼 설정
          </div>
        )}
      </div>

      {/* Execution output pill */}
      <NodeOutputPill status={execStatus} output={execOutput} error={execError} />

      {/* Decorative */}
      <div className="absolute -top-1 -right-1 text-indigo-400/15 text-2xl pointer-events-none">🔗</div>

      {/* Output Handle */}
      <Handle
        type="source"
        position={Position.Right}
        id="output"
        style={{
          background: '#3730a3',
          border: '3px solid #818cf8',
          width: 16,
          height: 16,
          top: '50%',
        }}
        title="출력 (병합된 데이터)"
      />
    </div>
  );
}

export const MapperNode = memo(MapperNodeInner);
