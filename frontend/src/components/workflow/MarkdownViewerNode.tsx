import { memo, useState, useEffect, useContext } from 'react';
import { Handle, Position } from '@xyflow/react';
import { factoryApi } from '../../services/api';
import { ConnectionDragContext } from './FactoryNode';
import { NodeOutputPill } from './NodeOutputPill';
import { ExecutionStatusBadge } from './ExecutionStatusBadge';

export interface MarkdownViewerNodeData extends Record<string, unknown> {
  nodeId: string;
  instanceName: string;
  definitionType?: string;
  inputMapping?: Record<string, string>;
  config?: Record<string, unknown>;
}

function MarkdownViewerNodeInner({ data, selected, id }: { data: MarkdownViewerNodeData; selected: boolean; id: string }) {
  const connectionDrag = useContext(ConnectionDragContext);
  const [itemCount, setItemCount] = useState<number>(0);
  const isInvalidTarget = connectionDrag?.invalidTargetIds.has(id) ?? false;

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

  useEffect(() => {
    let mounted = true;
    const fetchCount = async () => {
      try {
        const result = await factoryApi.getWarehouse(id, 1);
        if (mounted) setItemCount(result.total);
      } catch { /* ignore */ }
    };
    fetchCount();
    const interval = setInterval(fetchCount, 10000);
    return () => { mounted = false; clearInterval(interval); };
  }, [id]);

  return (
    <div className={`bg-gradient-to-b ${isInvalidTarget ? 'from-red-800/80 to-red-900/80 border-red-500' : execBorder ? `from-indigo-700 to-indigo-900 ${execBorder}` : 'from-indigo-700 to-indigo-900 border-indigo-400'} border-2 rounded-xl shadow-2xl min-w-[200px] transition-all ${selected ? 'ring-2 ring-indigo-300 ring-offset-2 ring-offset-gray-900 scale-105' : ''}${isInvalidTarget && !execStatus ? ' animate-pulse' : ''}`}>
      {/* Input Handle */}
      <Handle type="target" position={Position.Left} id="input" style={{ background: '#312e81', border: '3px solid #818cf8', width: 16, height: 16, top: '50%' }} title="입력" />

      {/* Header */}
      <div className="px-4 py-3 border-b border-white/10">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-black/30 flex items-center justify-center text-xl">📄</div>
          <div className="flex-1 min-w-0">
            <div className="text-xs text-indigo-300/80 font-medium uppercase tracking-wider">마크다운 뷰어</div>
            <div className="text-white font-semibold text-sm truncate">{data.instanceName}</div>
          </div>
          <ExecutionStatusBadge status={execStatus} />
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3">
        <div className="flex items-center gap-2 mb-2">
          <div className="text-2xl font-bold text-indigo-200">{itemCount}</div>
          <div className="text-indigo-300/70 text-xs">개 결과 보관중</div>
        </div>
        <div className="flex items-center gap-1.5">
          <div className={`w-2 h-2 rounded-full ${itemCount > 0 ? 'bg-indigo-400' : 'bg-gray-500'}`} />
          <span className="text-indigo-300/60 text-[10px]">
            {itemCount > 0 ? '클릭하여 마크다운 보기' : '아직 데이터 없음'}
          </span>
        </div>
      </div>

      {/* Execution output pill */}
      <NodeOutputPill status={execStatus} output={execOutput} error={execError} />

      {/* Decorative */}
      <div className="absolute -top-1 -right-1 text-indigo-400/15 text-2xl pointer-events-none">📄</div>
    </div>
  );
}

export const MarkdownViewerNode = memo(MarkdownViewerNodeInner);
