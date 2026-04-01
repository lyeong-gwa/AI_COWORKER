import { memo, useState, useEffect, useContext } from 'react';
import { Handle, Position } from '@xyflow/react';
import { factoryApi } from '../../services/api';
import { ConnectionDragContext } from './FactoryNode';
import { NodeOutputPill } from './NodeOutputPill';
import { ExecutionStatusBadge } from './ExecutionStatusBadge';

interface SorterRule {
  id: string;
  field: string;
  operator: string;
  value: string;
  label: string;
}

export interface DedupConfig {
  enabled: boolean;
  warehouseNodeId: string;
  matchField: string;
}

export interface SorterNodeData extends Record<string, unknown> {
  nodeId: string;
  instanceName: string;
  definitionType?: string;
  config?: {
    rules?: SorterRule[];
    dedup?: DedupConfig;
  };
  inputMapping?: Record<string, string>;
}

function SorterNodeInner({ data, selected, id }: { data: SorterNodeData; selected: boolean; id: string }) {
  const connectionDrag = useContext(ConnectionDragContext);
  const [itemCount, setItemCount] = useState<number>(0);

  const rules: SorterRule[] = data.config?.rules || [];
  const dedup = data.config?.dedup;
  const dedupEnabled = dedup?.enabled && dedup?.warehouseNodeId && dedup?.matchField;

  // Check if this sorter is an invalid drop target during connection drag
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
  // Total handles: one per rule + one default + (optional) skip
  const totalHandles = rules.length + 1 + (dedupEnabled ? 1 : 0);

  // Calculate evenly spaced top % for each handle index (0-based)
  const handleTopPercent = (index: number): string => {
    return `${((index + 1) / (totalHandles + 1)) * 100}%`;
  };

  // Fetch warehouse item count on mount and periodically
  useEffect(() => {
    let mounted = true;

    const fetchCount = async () => {
      try {
        const result = await factoryApi.getWarehouse(id, 1);
        if (mounted) setItemCount(result.total);
      } catch {
        // Ignore errors - may not have data yet
      }
    };

    fetchCount();
    const interval = setInterval(fetchCount, 10000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [id]);

  return (
    <div
      className={`bg-gradient-to-b ${isInvalidTarget ? 'from-red-800/80 to-red-900/80 border-red-500' : execBorder ? `from-violet-700 to-violet-900 ${execBorder}` : 'from-violet-700 to-violet-900 border-violet-400'} border-2 rounded-xl shadow-2xl min-w-[220px] transition-all relative ${
        selected ? 'ring-2 ring-violet-300 ring-offset-2 ring-offset-gray-900 scale-105' : ''
      }${isInvalidTarget && !execStatus ? ' animate-pulse' : ''}`}
    >
      {/* Input Handle (left side) */}
      <Handle
        type="target"
        position={Position.Left}
        id="input"
        style={{
          background: '#4c1d95',
          border: '3px solid #a78bfa',
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
            🔀
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs text-violet-300/80 font-medium uppercase tracking-wider">분류기</div>
            <div className="text-white font-semibold text-sm truncate">{data.instanceName}</div>
          </div>
          <ExecutionStatusBadge status={execStatus} />
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3 space-y-2">
        {/* Rule count */}
        <div className="flex items-center gap-2">
          <div className="text-xl font-bold text-violet-200">{rules.length}</div>
          <div className="text-violet-300/70 text-xs">개 분류 규칙</div>
        </div>

        {/* Rule list preview */}
        {rules.length > 0 && (
          <div className="space-y-1">
            {rules.slice(0, 3).map((rule) => (
              <div key={rule.id} className="flex items-center gap-1.5 text-[10px]">
                <div className="w-1.5 h-1.5 rounded-full bg-violet-400 flex-shrink-0" />
                <span className="text-violet-200/80 truncate">{rule.label || `${rule.field} ${rule.operator} ${rule.value}`}</span>
              </div>
            ))}
            {rules.length > 3 && (
              <div className="text-[10px] text-violet-400/60">+{rules.length - 3}개 더</div>
            )}
          </div>
        )}

        {rules.length === 0 && !dedupEnabled && (
          <div className="text-violet-300/50 text-[10px]">규칙을 설정하세요</div>
        )}

        {/* Dedup filter indicator */}
        {dedupEnabled && (
          <div className="flex items-center gap-1.5 text-[10px] bg-amber-900/30 rounded px-2 py-1">
            <span className="text-amber-400">🔍</span>
            <span className="text-amber-200/80 truncate">
              중복 필터: <span className="font-mono">{dedup!.matchField}</span>
            </span>
          </div>
        )}

        {/* Item count */}
        <div className="flex items-center gap-1.5 pt-1 border-t border-white/10">
          <div className={`w-2 h-2 rounded-full ${itemCount > 0 ? 'bg-violet-400' : 'bg-gray-500'}`} />
          <span className="text-violet-300/60 text-[10px]">
            {itemCount > 0 ? `${itemCount}건 처리 이력` : '처리 대기 중'}
          </span>
        </div>
      </div>

      {/* Execution output pill */}
      <NodeOutputPill status={execStatus} output={execOutput} error={execError} />

      {/* Decorative */}
      <div className="absolute -top-1 -right-1 text-violet-400/15 text-2xl pointer-events-none">🔀</div>

      {/* Dynamic rule output handles (right side) */}
      {rules.map((rule, index) => (
        <div key={rule.id}>
          {/* Rule label next to handle */}
          <div
            style={{
              position: 'absolute',
              right: 22,
              top: handleTopPercent(index),
              transform: 'translateY(-50%)',
              pointerEvents: 'none',
            }}
            className="text-[9px] text-violet-200/70 font-medium max-w-[80px] truncate text-right leading-none"
          >
            {rule.label || rule.field}
          </div>
          <Handle
            type="source"
            position={Position.Right}
            id={`rule-${rule.id}`}
            style={{
              background: '#5b21b6',
              border: '3px solid #a78bfa',
              width: 14,
              height: 14,
              top: handleTopPercent(index),
            }}
            title={rule.label || `${rule.field} ${rule.operator} ${rule.value}`}
          />
        </div>
      ))}

      {/* Default (기타) handle */}
      <div
        style={{
          position: 'absolute',
          right: 22,
          top: handleTopPercent(rules.length),
          transform: 'translateY(-50%)',
          pointerEvents: 'none',
        }}
        className="text-[9px] text-gray-400/80 font-medium text-right leading-none"
      >
        기타
      </div>
      <Handle
        type="source"
        position={Position.Right}
        id="default"
        style={{
          background: '#374151',
          border: '3px solid #9ca3af',
          width: 14,
          height: 14,
          top: handleTopPercent(rules.length),
        }}
        title="기타 (기본 출력)"
      />

      {/* Skip (중복) handle — only visible when dedup enabled */}
      {dedupEnabled && (
        <>
          <div
            style={{
              position: 'absolute',
              right: 22,
              top: handleTopPercent(rules.length + 1),
              transform: 'translateY(-50%)',
              pointerEvents: 'none',
            }}
            className="text-[9px] text-amber-400/80 font-medium text-right leading-none"
          >
            중복
          </div>
          <Handle
            type="source"
            position={Position.Right}
            id="__skip__"
            style={{
              background: '#92400e',
              border: '3px solid #f59e0b',
              width: 14,
              height: 14,
              top: handleTopPercent(rules.length + 1),
            }}
            title="중복 필터됨 (스킵)"
          />
        </>
      )}
    </div>
  );
}

export const SorterNode = memo(SorterNodeInner);
