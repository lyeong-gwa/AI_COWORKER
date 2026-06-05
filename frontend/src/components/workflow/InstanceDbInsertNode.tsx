import { memo, useState, useEffect, useContext } from 'react';
import { Handle, Position } from '@xyflow/react';
import { instanceDbApi } from '../../services/api';
import { ConnectionDragContext } from './FactoryNode';
import { NodeOutputPill } from './NodeOutputPill';
import { ExecutionStatusBadge } from './ExecutionStatusBadge';
import { InstanceExecutionContext } from '../../contexts/InstanceExecutionContext';

export interface InstanceDbInsertNodeData extends Record<string, unknown> {
  nodeId: string;
  instanceName: string;
  definitionType?: string;
  inputMapping?: Record<string, string>;
  config?: Record<string, unknown>;
}

function InstanceDbInsertNodeInner({
  data,
  selected,
  id,
}: {
  data: InstanceDbInsertNodeData;
  selected: boolean;
  id: string;
}) {
  const connectionDrag = useContext(ConnectionDragContext);
  const executionCtx = useContext(InstanceExecutionContext);

  // "적재 N건" count from the instance DB records API.
  // When executionId is available (InstanceDetailPage context), filter to that execution.
  // Otherwise, show the total record count for this workflow's DB.
  const [insertCount, setInsertCount] = useState<number | null>(null);

  const instanceDbId = (data.config as Record<string, unknown> | undefined)
    ?.instanceDbId as string | undefined;

  const isInvalidTarget = connectionDrag?.invalidTargetIds.has(id) ?? false;

  const execStatus = data._executionStatus as string | undefined;
  const execOutput = data._executionOutput;
  const execError = data._executionError as string | undefined;
  const execBorder =
    execStatus === 'running'
      ? 'border-blue-500 shadow-[0_0_12px_rgba(59,130,246,0.5)]'
      : execStatus === 'completed'
        ? 'border-green-500 shadow-[0_0_12px_rgba(34,197,94,0.3)]'
        : execStatus === 'failed'
          ? 'border-red-500 shadow-[0_0_12px_rgba(239,68,68,0.3)]'
          : '';

  useEffect(() => {
    if (!instanceDbId) return;

    let mounted = true;
    const fetchCount = async () => {
      try {
        const params: Parameters<typeof instanceDbApi.listRecords>[1] = { limit: 1 };
        // When inside InstanceDetailPage, narrow to this specific execution
        if (executionCtx?.executionId) {
          params.sourceExecutionId = executionCtx.executionId;
        }
        const result = await instanceDbApi.listRecords(instanceDbId, params);
        if (mounted) setInsertCount(result.total);
      } catch {
        /* ignore — DB may be empty or not yet created */
      }
    };

    fetchCount();
    const interval = setInterval(fetchCount, 10000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [instanceDbId, executionCtx?.executionId]);

  return (
    <div
      className={`bg-gradient-to-b ${
        isInvalidTarget
          ? 'from-red-800/80 to-red-900/80 border-red-500'
          : execBorder
            ? `from-teal-700 to-teal-900 ${execBorder}`
            : 'from-teal-700 to-teal-900 border-teal-400'
      } border-2 rounded-xl shadow-2xl min-w-[200px] transition-all ${
        selected ? 'ring-2 ring-teal-300 ring-offset-2 ring-offset-gray-900 scale-105' : ''
      }${isInvalidTarget && !execStatus ? ' animate-pulse' : ''}`}
    >
      {/* Input Handle */}
      <Handle
        type="target"
        position={Position.Left}
        id="input"
        style={{ background: '#0f766e', border: '3px solid #2dd4bf', width: 16, height: 16, top: '50%' }}
        title="입력"
      />
      <Handle
        type="source"
        position={Position.Right}
        id="output"
        style={{ background: '#0f766e', border: '3px solid #2dd4bf', width: 16, height: 16, top: '50%' }}
        title="출력 (패스스루)"
      />

      {/* Header */}
      <div className="px-4 py-3 border-b border-white/10">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-black/30 flex items-center justify-center text-xl">📥</div>
          <div className="flex-1 min-w-0">
            <div className="text-xs text-teal-300/80 font-medium uppercase tracking-wider">인스턴스DB 적재</div>
            <div className="text-white font-semibold text-sm truncate">{data.instanceName}</div>
          </div>
          <ExecutionStatusBadge status={execStatus} />
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3">
        {instanceDbId ? (
          <>
            <div className="flex items-center gap-2 mb-2">
              <div className="text-2xl font-bold text-teal-200">
                {insertCount === null ? '…' : insertCount}
              </div>
              <div className="text-teal-300/70 text-xs">건 적재됨</div>
            </div>
            <div className="flex items-center gap-1.5">
              <div
                className={`w-2 h-2 rounded-full ${
                  insertCount !== null && insertCount > 0 ? 'bg-teal-400' : 'bg-gray-500'
                }`}
              />
              <span className="text-teal-300/60 text-[10px]">
                {insertCount !== null && insertCount > 0 ? '클릭하여 적재 내역 확인' : '아직 데이터 없음'}
              </span>
            </div>
          </>
        ) : (
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-yellow-500" />
            <span className="text-yellow-300/70 text-[10px]">DB 미설정</span>
          </div>
        )}
      </div>

      {/* Execution output pill */}
      <NodeOutputPill status={execStatus} output={execOutput} error={execError} />

      {/* Decorative */}
      <div className="absolute -top-1 -right-1 text-teal-400/15 text-2xl pointer-events-none">📥</div>
    </div>
  );
}

export const InstanceDbInsertNode = memo(InstanceDbInsertNodeInner);
