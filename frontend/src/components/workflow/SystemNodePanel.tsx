import { useState } from 'react';
import { nodeRegistry } from '../../nodes/registry';

interface SystemNodePanelProps {
  nodeId: string;
  nodeName: string;
  config: Record<string, any>;
  inputMapping?: Record<string, string>;
  upstreamFields?: { name: string; type: string }[];
  allNodes?: any[];
  onUpdateName: (name: string) => void;
  onUpdateConfig: (config: Record<string, any>) => void;
  onDelete: () => void;
  onClose: () => void;
  [key: string]: any;
}

export function SystemNodePanel({
  nodeId,
  nodeName,
  inputMapping = {},
  upstreamFields = [],
  allNodes = [],
  onUpdateName,
  onDelete,
  onClose,
}: SystemNodePanelProps) {
  const [localName, setLocalName] = useState(nodeName);

  // Find the definitionType from allNodes
  const canvasNode = allNodes.find((n: any) => n.id === nodeId);
  const defType: string = canvasNode?.data?.definitionType || canvasNode?.data?.nodeId || '';
  const regDef = nodeRegistry.get(defType);

  const palette = regDef?.palette;
  const staticOutputFields = regDef?.staticOutputFields || [];
  const icon = palette?.icon || '\u2699\uFE0F';
  const label = palette?.label || defType;
  const description = palette?.description || '';

  const inputMappingEntries = Object.entries(inputMapping);

  return (
    <div className="w-96 bg-gray-800 border-l border-gray-700 flex flex-col animate-slide-in-right">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <div className="w-10 h-10 rounded-lg bg-gray-700 flex items-center justify-center text-xl flex-shrink-0">
              {icon}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs text-gray-400 uppercase tracking-wider truncate">{label}</div>
              <input
                type="text"
                value={localName}
                onChange={(e) => setLocalName(e.target.value)}
                onBlur={() => onUpdateName(localName)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    onUpdateName(localName);
                    (e.target as HTMLInputElement).blur();
                  }
                }}
                className="bg-transparent text-white font-semibold text-sm border-none outline-none w-full"
                placeholder="이름 입력..."
              />
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white p-1 flex-shrink-0 ml-2"
            aria-label="닫기"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {/* Description */}
        {description && (
          <div className="bg-gray-900/60 border border-gray-700 rounded-lg p-3">
            <p className="text-xs text-gray-400 leading-relaxed">{description}</p>
          </div>
        )}

        {/* Input mapping section */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5 font-medium uppercase tracking-wider">
            입력 매핑
          </label>
          {inputMappingEntries.length > 0 ? (
            <div className="bg-gray-900 border border-gray-700 rounded-lg divide-y divide-gray-700/60">
              {inputMappingEntries.map(([field, path]) => (
                <div key={field} className="flex items-center gap-2 px-3 py-2">
                  <span className="text-xs font-mono text-blue-300 flex-shrink-0">{field}</span>
                  <svg className="w-3 h-3 text-gray-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                  <span className="text-xs font-mono text-gray-300 truncate" title={path}>{path}</span>
                </div>
              ))}
            </div>
          ) : upstreamFields.length > 0 ? (
            <div className="bg-gray-900 border border-gray-700 rounded-lg p-3">
              <p className="text-xs text-gray-500">
                상위 노드에서 <span className="text-gray-300 font-mono">{upstreamFields.map(f => f.name).join(', ')}</span> 필드를 받습니다.
              </p>
            </div>
          ) : (
            <div className="bg-gray-900 border border-gray-700 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500">연결된 상위 노드가 없습니다</p>
              <p className="text-[10px] text-gray-600 mt-0.5">컨베이어벨트로 이전 노드를 연결하세요</p>
            </div>
          )}
        </div>

        {/* Upstream fields (available inputs) */}
        {upstreamFields.length > 0 && (
          <div>
            <label className="block text-xs text-gray-400 mb-1.5 font-medium uppercase tracking-wider">
              사용 가능한 입력 필드
            </label>
            <div className="bg-gray-900 border border-gray-700 rounded-lg p-2 flex flex-wrap gap-1.5">
              {upstreamFields.map((field) => (
                <span
                  key={field.name}
                  className="inline-flex items-center gap-1 px-2 py-1 bg-gray-800 border border-gray-600 rounded text-[11px]"
                >
                  <span className="font-mono text-gray-200">{field.name}</span>
                  <span className="text-gray-500">{field.type}</span>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Output fields section */}
        {staticOutputFields.length > 0 && (
          <div>
            <label className="block text-xs text-gray-400 mb-1.5 font-medium uppercase tracking-wider">
              출력 필드
            </label>
            <div className="bg-gray-900 border border-gray-700 rounded-lg divide-y divide-gray-700/60">
              {staticOutputFields.map((field) => (
                <div key={field.name} className="flex items-center justify-between px-3 py-2">
                  <span className="text-xs font-mono text-emerald-300">{field.name}</span>
                  <span className={`px-1.5 py-0.5 text-[9px] rounded border ${
                    field.type === 'string'
                      ? 'bg-blue-600/20 text-blue-300 border-blue-500/30'
                      : field.type === 'number'
                        ? 'bg-purple-600/20 text-purple-300 border-purple-500/30'
                        : field.type === 'array'
                          ? 'bg-amber-600/20 text-amber-300 border-amber-500/30'
                          : field.type === 'object'
                            ? 'bg-teal-600/20 text-teal-300 border-teal-500/30'
                            : 'bg-gray-600/20 text-gray-300 border-gray-500/30'
                  }`}>
                    {field.type}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Info box */}
        <div className="bg-gray-900/40 border border-gray-700/60 rounded-lg p-3">
          <div className="flex items-start gap-2">
            <svg className="w-4 h-4 text-gray-500 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-[10px] text-gray-500 leading-relaxed">
              이 노드는 시스템 노드로 별도 설정이 필요하지 않습니다. 상위 노드를 연결하면 자동으로 처리됩니다.
            </p>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-gray-700 flex gap-2">
        <button
          onClick={onDelete}
          className="px-3 py-2 bg-red-600/20 text-red-400 rounded-lg hover:bg-red-600/30 text-sm flex-1 transition-colors"
        >
          삭제
        </button>
      </div>
    </div>
  );
}
