import { memo, useContext, createContext, useState, useEffect } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { AINode } from '../../types';
import { factoryApi } from '../../services/api';
import { NodeOutputPill } from './NodeOutputPill';
import { ExecutionStatusBadge } from './ExecutionStatusBadge';
import { nodeRegistry } from '../../nodes/registry';

// Context to pass AI nodes data
export const AINodesContext = createContext<AINode[]>([]);

// Context for connection drag validation visual feedback
export interface ConnectionDragState {
  invalidTargetIds: Set<string>;
}

export const ConnectionDragContext = createContext<ConnectionDragState | null>(null);

export interface FactoryNodeData extends Record<string, unknown> {
  nodeId: string;
  instanceName: string;
  definitionType?: string;
  aiNodeId?: string;
  inputMapping?: Record<string, string>;
}

function FactoryNodeInner({ data, selected, id }: { data: FactoryNodeData; selected: boolean; id: string }) {
  const aiNodes = useContext(AINodesContext);
  const connectionDrag = useContext(ConnectionDragContext);
  const aiNode = aiNodes.find(n => n.id === (data.aiNodeId || data.nodeId));

  const execStatus = data._executionStatus as string | undefined;
  const execOutput = data._executionOutput;
  const execError = data._executionError as string | undefined;
  const execBorder = execStatus === 'running'
    ? 'border-blue-500 shadow-[0_0_12px_rgba(59,130,246,0.5)]'
    : execStatus === 'completed'
      ? 'border-green-500 shadow-[0_0_12px_rgba(34,197,94,0.3)]'
      : execStatus === 'failed'
        ? 'border-red-500 shadow-[0_0_12px_rgba(239,68,68,0.3)]'
        : execStatus === 'not_executed'
          ? 'border-slate-700/40 opacity-50 grayscale'
          : '';

  const [queueCount, setQueueCount] = useState({ pending: 0, processing: 0, total: 0 });

  useEffect(() => {
    let mounted = true;
    const fetchCount = async () => {
      try {
        const result = await factoryApi.getQueueCount(id);
        if (mounted) setQueueCount({ pending: result.pending, processing: result.processing, total: result.total });
      } catch {
        // 큐가 아직 없을 수 있음
      }
    };
    fetchCount();
    const interval = setInterval(fetchCount, 5000);
    return () => { mounted = false; clearInterval(interval); };
  }, [id]);

  // Check if this node is an invalid drop target during connection drag
  const isInvalidTarget = connectionDrag?.invalidTargetIds.has(id) ?? false;

  if (!aiNode) {
    // Check if this is a registered system node (non-AI)
    const regDef = nodeRegistry.get(data.definitionType || data.nodeId);
    if (regDef?.palette) {
      const pal = regDef.palette;
      const outputFields = regDef.staticOutputFields || [];
      return (
        <div
          className={`bg-gradient-to-b ${isInvalidTarget ? 'from-red-800/80 to-red-900/80 border-red-500' : execBorder ? `${pal.bg || 'from-slate-700 to-slate-800'} ${execBorder}` : `${pal.bg || 'from-slate-700 to-slate-800'} ${pal.border || 'border-slate-500'}`} border-2 rounded-xl shadow-2xl min-w-[220px] max-w-[280px] transition-all ${
            selected ? 'ring-2 ring-blue-400 ring-offset-2 ring-offset-gray-900 scale-105' : ''
          }${isInvalidTarget && !execStatus ? ' animate-pulse' : ''}`}
        >
          <Handle type="target" position={Position.Left} id="input" style={{ background: '#334155', border: '3px solid #94a3b8', width: 16, height: 16, top: '50%' }} title="입력" />
          <div className="px-4 py-3 border-b border-white/10 rounded-t-xl">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-lg bg-black/30 flex items-center justify-center text-xl">
                {pal.icon || '⚙️'}
              </div>
              <div className="flex-1 min-w-0">
                <div className={`text-xs ${pal.textColor || 'text-slate-300'} font-medium uppercase tracking-wider`}>{pal.label || data.nodeId}</div>
                <div className="text-white font-semibold text-sm truncate">{data.instanceName}</div>
              </div>
              <ExecutionStatusBadge status={execStatus} />
            </div>
          </div>
          <div className="px-4 py-3 space-y-2">
            {outputFields.length > 0 && (
              <div>
                <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">출력</div>
                <div className="text-xs text-slate-300">
                  {outputFields.slice(0, 3).map((f: any) => f.name || f).join(', ')}
                  {outputFields.length > 3 && ` +${outputFields.length - 3}`}
                </div>
              </div>
            )}
            <div className={`text-[10px] ${pal.descColor || 'text-slate-500'}`}>
              {pal.description || '시스템 노드'}
            </div>
          </div>
          <NodeOutputPill status={execStatus} output={execOutput} error={execError} />
          <Handle type="source" position={Position.Right} id="output" style={{ background: '#334155', border: '3px solid #94a3b8', width: 16, height: 16, top: '50%' }} title="출력" />
        </div>
      );
    }

    // Truly unknown node - show error
    return (
      <div className="bg-red-900/80 border-2 border-red-500 rounded-xl p-4 min-w-[200px]">
        <Handle type="target" position={Position.Left} id="input" style={{ background: '#ef4444', border: '2px solid #f87171', width: 14, height: 14, top: '50%' }} />
        <span className="text-red-300 text-sm">알 수 없는 노드: {data.nodeId}</span>
        <Handle type="source" position={Position.Right} id="output" style={{ background: '#ef4444', border: '2px solid #f87171', width: 14, height: 14, top: '50%' }} />
      </div>
    );
  }

  const inputFields = Object.keys(aiNode.inputSchema?.properties ?? {});
  const outputFields = Object.keys(aiNode.outputSchema?.properties ?? {});
  const hasAllInputs = inputFields.length === 0 || Object.keys(data.inputMapping || {}).length >= inputFields.length;

  return (
    <div
      className={`bg-gradient-to-b ${isInvalidTarget ? 'from-red-800/80 to-red-900/80 border-red-500' : execBorder ? `from-slate-700 to-slate-800 ${execBorder}` : 'from-slate-700 to-slate-800 border-slate-500'} border-2 rounded-xl shadow-2xl min-w-[220px] max-w-[280px] transition-all ${
        selected ? 'ring-2 ring-blue-400 ring-offset-2 ring-offset-gray-900 scale-105' : ''
      }${isInvalidTarget && !execStatus ? ' animate-pulse' : ''}`}
    >
      {/* Input Handle */}
      <Handle
        type="target"
        position={Position.Left}
        id="input"
        style={{
          background: '#334155',
          border: '3px solid #94a3b8',
          width: 16,
          height: 16,
          top: '50%',
        }}
        title="입력"
      />

      {/* Header */}
      <div className="px-4 py-3 border-b border-white/10 bg-slate-600/30 rounded-t-xl">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-black/30 flex items-center justify-center text-xl">
            🏭
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs text-blue-300/80 font-medium uppercase tracking-wider">공장</div>
            <div className="text-white font-semibold text-sm truncate">{data.instanceName}</div>
          </div>
          <ExecutionStatusBadge status={execStatus} />
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3 space-y-2.5">
        {/* Model badge */}
        <div className="flex items-center gap-1.5">
          <span className="px-2 py-0.5 text-[10px] rounded-full bg-blue-900/60 text-blue-300 border border-blue-700/50">
            {aiNode.llmConfig?.model ?? 'default'}
          </span>
        </div>

        {/* Input fields */}
        <div>
          <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">입력</div>
          <div className="space-y-1">
            {inputFields.slice(0, 3).map(field => {
              const isMapped = !!(data.inputMapping && data.inputMapping[field]);
              return (
                <div key={field} className="flex items-center gap-1.5 text-xs">
                  <div className={`w-1.5 h-1.5 rounded-full ${isMapped ? 'bg-green-400' : 'bg-red-400'}`} />
                  <span className="text-slate-300 truncate">{field}</span>
                </div>
              );
            })}
            {inputFields.length > 3 && (
              <div className="text-[10px] text-slate-500">+{inputFields.length - 3}개 더</div>
            )}
          </div>
        </div>

        {/* Output fields */}
        <div>
          <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-1">출력</div>
          <div className="text-xs text-slate-300">
            {outputFields.slice(0, 2).join(', ')}
            {outputFields.length > 2 && ` +${outputFields.length - 2}`}
          </div>
        </div>

        {/* Queue info + Status badge */}
        <div className="pt-1 space-y-1.5">
          {queueCount.total > 0 && (
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1">
                <span className="text-amber-400 text-[10px] font-bold">{queueCount.pending}</span>
                <span className="text-slate-500 text-[10px]">대기</span>
              </div>
              {queueCount.processing > 0 && (
                <div className="flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                  <span className="text-blue-300 text-[10px] font-bold">{queueCount.processing}</span>
                  <span className="text-slate-500 text-[10px]">처리중</span>
                </div>
              )}
              <span className="text-slate-600 text-[10px]">/ {queueCount.total}건</span>
            </div>
          )}
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] rounded-full ${
            queueCount.processing > 0
              ? 'bg-blue-900/40 text-blue-300 border border-blue-700/50'
              : hasAllInputs
                ? 'bg-green-900/40 text-green-300 border border-green-700/50'
                : 'bg-yellow-900/40 text-yellow-300 border border-yellow-700/50'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${
              queueCount.processing > 0
                ? 'bg-blue-400 animate-pulse'
                : hasAllInputs ? 'bg-green-400' : 'bg-yellow-400 animate-pulse'
            }`} />
            {queueCount.processing > 0 ? '가동중' : hasAllInputs ? '가동 가능' : '대기 중'}
          </span>
        </div>
      </div>

      {/* Execution output pill */}
      <NodeOutputPill status={execStatus} output={execOutput} error={execError} />

      {/* Decorative smoke */}
      <div className="absolute -top-2 right-2 text-slate-400/15 text-3xl pointer-events-none">🏭</div>

      {/* Output Handle */}
      <Handle
        type="source"
        position={Position.Right}
        id="output"
        style={{
          background: '#334155',
          border: '3px solid #94a3b8',
          width: 16,
          height: 16,
          top: '50%',
        }}
        title="출력"
      />
    </div>
  );
}

export const FactoryNode = memo(FactoryNodeInner);
