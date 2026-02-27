import { memo, useContext } from 'react';
import { Handle, Position } from '@xyflow/react';
import { ConnectionDragContext } from './FactoryNode';

export interface ApiCallNodeData extends Record<string, unknown> {
  nodeId: string;
  instanceName: string;
  definitionType?: string;
  inputMapping?: Record<string, string>;
  config?: {
    docId?: string;
    docTitle?: string;
    method?: string;
    url?: string;
    inputFields?: string[];
    outputFields?: string[];
  };
}

function ApiCallNodeInner({ data, selected, id }: { data: ApiCallNodeData; selected: boolean; id: string }) {
  const connectionDrag = useContext(ConnectionDragContext);
  const isInvalidTarget = connectionDrag?.invalidTargetIds.has(id) ?? false;

  const config = data.config || {};
  const hasDoc = !!config.docId;
  const method = config.method || 'GET';
  const inputFields = config.inputFields || [];
  const outputFields = config.outputFields || ['status', 'data'];

  // Method badge colors
  const methodColors: Record<string, string> = {
    GET: 'bg-green-600/60 text-green-200',
    POST: 'bg-blue-600/60 text-blue-200',
    PUT: 'bg-amber-600/60 text-amber-200',
    PATCH: 'bg-orange-600/60 text-orange-200',
    DELETE: 'bg-red-600/60 text-red-200',
  };

  return (
    <div
      className={`bg-gradient-to-b ${isInvalidTarget ? 'from-red-800/80 to-red-900/80 border-red-500' : 'from-cyan-700 to-cyan-900 border-cyan-400'} border-2 rounded-xl shadow-2xl min-w-[220px] max-w-[280px] transition-all ${
        selected ? 'ring-2 ring-cyan-300 ring-offset-2 ring-offset-gray-900 scale-105' : ''
      }${isInvalidTarget ? ' animate-pulse' : ''}`}
    >
      {/* Input Handle */}
      <Handle
        type="target"
        position={Position.Left}
        id="input"
        style={{
          background: '#0e7490',
          border: '3px solid #22d3ee',
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
            🌐
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs text-cyan-300/80 font-medium uppercase tracking-wider">API 호출기</div>
            <div className="text-white font-semibold text-sm truncate">{data.instanceName}</div>
          </div>
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
              <span className="text-cyan-200 text-xs truncate">{config.docTitle || config.docId}</span>
            </div>

            {/* URL preview */}
            {config.url && (
              <div className="text-[10px] text-cyan-300/50 font-mono truncate">
                {config.url}
              </div>
            )}

            {/* Input fields */}
            {inputFields.length > 0 && (
              <div>
                <div className="text-[10px] text-cyan-400/60 uppercase tracking-wider mb-1">입력 변수</div>
                <div className="flex flex-wrap gap-1">
                  {inputFields.slice(0, 4).map(f => (
                    <span key={f} className="px-1.5 py-0.5 text-[9px] rounded bg-cyan-900/60 text-cyan-300 border border-cyan-700/50">
                      {f}
                    </span>
                  ))}
                  {inputFields.length > 4 && (
                    <span className="text-[9px] text-cyan-400/50">+{inputFields.length - 4}</span>
                  )}
                </div>
              </div>
            )}

            {/* Output fields */}
            <div className="flex items-center gap-1.5 pt-1 border-t border-white/10">
              <div className="w-2 h-2 rounded-full bg-cyan-400" />
              <span className="text-cyan-300/60 text-[10px]">
                출력: {outputFields.join(', ')}
              </span>
            </div>
          </>
        ) : (
          <div className="text-cyan-300/50 text-xs text-center py-2">
            클릭하여 API 문서 선택
          </div>
        )}
      </div>

      {/* Decorative */}
      <div className="absolute -top-1 -right-1 text-cyan-400/15 text-2xl pointer-events-none">🌐</div>

      {/* Output Handle */}
      <Handle
        type="source"
        position={Position.Right}
        id="output"
        style={{
          background: '#0e7490',
          border: '3px solid #22d3ee',
          width: 16,
          height: 16,
          top: '50%',
        }}
        title="출력"
      />
    </div>
  );
}

export const ApiCallNode = memo(ApiCallNodeInner);
