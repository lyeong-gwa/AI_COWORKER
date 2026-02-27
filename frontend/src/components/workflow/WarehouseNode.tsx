import { memo, useState, useEffect, useContext } from 'react';
import { Handle, Position } from '@xyflow/react';
import { factoryApi } from '../../services/api';
import { ConnectionDragContext } from './FactoryNode';

export interface WarehouseNodeData extends Record<string, unknown> {
  nodeId: string;
  instanceName: string;
  definitionType?: string;
  inputMapping?: Record<string, string>;
  aiNodeId?: string;
}

function WarehouseNodeInner({ data, selected, id }: { data: WarehouseNodeData; selected: boolean; id: string }) {
  const connectionDrag = useContext(ConnectionDragContext);
  const [itemCount, setItemCount] = useState<number>(0);

  // Check if this warehouse is an invalid drop target during connection drag
  const isInvalidTarget = connectionDrag?.invalidTargetIds.has(id) ?? false;

  // Fetch warehouse count on mount and periodically
  useEffect(() => {
    let mounted = true;

    const fetchCount = async () => {
      try {
        const result = await factoryApi.getWarehouse(id, 1);
        if (mounted) setItemCount(result.total);
      } catch {
        // Ignore errors - warehouse may not have data yet
      }
    };

    fetchCount();
    const interval = setInterval(fetchCount, 10000); // refresh every 10s

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [id]);

  return (
    <div
      className={`bg-gradient-to-b ${isInvalidTarget ? 'from-red-800/80 to-red-900/80 border-red-500' : 'from-emerald-700 to-emerald-900 border-emerald-400'} border-2 rounded-xl shadow-2xl min-w-[200px] transition-all ${
        selected ? 'ring-2 ring-emerald-300 ring-offset-2 ring-offset-gray-900 scale-105' : ''
      }${isInvalidTarget ? ' animate-pulse' : ''}`}
    >
      {/* Input Handle (left side only - warehouses receive) */}
      <Handle
        type="target"
        position={Position.Left}
        id="input"
        style={{
          background: '#065f46',
          border: '3px solid #34d399',
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
            📦
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs text-emerald-300/80 font-medium uppercase tracking-wider">창고</div>
            <div className="text-white font-semibold text-sm truncate">{data.instanceName}</div>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3">
        {/* Item count */}
        <div className="flex items-center gap-2 mb-2">
          <div className="text-2xl font-bold text-emerald-200">{itemCount}</div>
          <div className="text-emerald-300/70 text-xs">개 데이터 보관중</div>
        </div>

        {/* Status indicator */}
        <div className="flex items-center gap-1.5">
          <div className={`w-2 h-2 rounded-full ${itemCount > 0 ? 'bg-emerald-400' : 'bg-gray-500'}`} />
          <span className="text-emerald-300/60 text-[10px]">
            {itemCount > 0 ? '클릭하여 데이터 확인' : '아직 데이터 없음'}
          </span>
        </div>
      </div>

      {/* Decorative */}
      <div className="absolute -top-1 -right-1 text-emerald-400/15 text-2xl pointer-events-none">📦</div>
    </div>
  );
}

export const WarehouseNode = memo(WarehouseNodeInner);
