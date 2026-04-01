import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { NodeOutputPill } from './NodeOutputPill';
import { ExecutionStatusBadge } from './ExecutionStatusBadge';

export interface FormStartNodeData extends Record<string, unknown> {
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
    defaultValues?: Record<string, any>;
  };
}

function FormStartNodeInner({ data, selected }: { data: FormStartNodeData; selected: boolean }) {
  const config = data.config || {};
  const mode = config.mode || 'manual';

  const execStatus = data._executionStatus as string | undefined;
  const execOutput = data._executionOutput;
  const execError = data._executionError as string | undefined;
  const execBorder = execStatus === 'running'
    ? 'border-blue-500 shadow-[0_0_12px_rgba(59,130,246,0.5)]'
    : execStatus === 'completed'
      ? 'border-green-500 shadow-[0_0_12px_rgba(34,197,94,0.3)]'
      : execStatus === 'failed'
        ? 'border-red-500 shadow-[0_0_12px_rgba(239,68,68,0.3)]'
        : 'border-amber-400';

  return (
    <div
      className={`bg-gradient-to-b from-amber-600 to-amber-800 border-2 ${execBorder} rounded-xl shadow-2xl min-w-[200px] transition-all ${
        selected ? 'ring-2 ring-amber-300 ring-offset-2 ring-offset-gray-900 scale-105' : ''
      }`}
    >
      {/* Header */}
      <div className="px-4 py-3 border-b border-white/10">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-black/30 flex items-center justify-center text-xl">
            {'\u{1F4CB}'}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <div className="text-xs text-amber-200/80 font-medium uppercase tracking-wider">
                {'\u{1F4CB}'} 폼 입력 시작
              </div>
              <span className={`px-1.5 py-0.5 text-[9px] rounded-full font-medium ${
                mode === 'schedule'
                  ? 'bg-amber-900/60 text-amber-200 border border-amber-500/50'
                  : 'bg-amber-900/40 text-amber-300 border border-amber-400/40'
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
      <div className="px-4 py-3">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-2 h-2 rounded-full bg-amber-300 animate-pulse" />
          <span className="text-amber-100/80 text-xs">폼 입력 시작점</span>
        </div>
        <div className="text-amber-200/50 text-[10px]">
          다음 노드의 입력 양식을 폼으로 제공합니다
        </div>
      </div>

      {/* Execution output pill */}
      <NodeOutputPill status={execStatus} output={execOutput} error={execError} />

      {/* Decorative */}
      <div className="absolute -top-1 -right-1 text-amber-400/20 text-2xl pointer-events-none">{'\u{1F4CB}'}</div>

      {/* Output Handle (right side only - start node produces) */}
      <Handle
        type="source"
        position={Position.Right}
        id="output"
        style={{
          background: '#d97706',
          border: '3px solid #fbbf24',
          width: 16,
          height: 16,
          top: '50%',
        }}
        title="출력"
      />
    </div>
  );
}

export const FormStartNode = memo(FormStartNodeInner);
