import { useState } from 'react';

interface MarkdownViewerConfigPanelProps {
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

export function MarkdownViewerConfigPanel({
  nodeName,
  config,
  upstreamFields = [],
  onUpdateName,
  onUpdateConfig,
  onDelete,
  onClose,
}: MarkdownViewerConfigPanelProps) {
  const [localName, setLocalName] = useState(nodeName);
  const [displayKey, setDisplayKey] = useState<string>(config.displayKey || '');

  const handleDisplayKeyBlur = () => {
    onUpdateConfig({ ...config, displayKey: displayKey.trim() || undefined });
  };

  const handleDisplayKeyKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      onUpdateConfig({ ...config, displayKey: displayKey.trim() || undefined });
      (e.target as HTMLInputElement).blur();
    }
  };

  const stringFields = upstreamFields.filter((f) => f.type === 'string' || f.type === 'object');

  return (
    <div className="w-96 bg-gray-800 border-l border-gray-700 flex flex-col animate-slide-in-right">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <div className="w-10 h-10 rounded-lg bg-gray-700 flex items-center justify-center text-xl flex-shrink-0">
              📄
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs text-gray-400 uppercase tracking-wider truncate">마크다운 뷰어</div>
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
        <div className="bg-gray-900/60 border border-gray-700 rounded-lg p-3">
          <p className="text-xs text-gray-400 leading-relaxed">
            상위 노드의 출력 데이터를 마크다운으로 렌더링합니다. 표시할 키를 지정하면 해당 키의 값을 우선 표시합니다.
          </p>
        </div>

        {/* displayKey config */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5 font-medium uppercase tracking-wider">
            표시할 키 (선택)
          </label>
          <input
            type="text"
            value={displayKey}
            onChange={(e) => setDisplayKey(e.target.value)}
            onBlur={handleDisplayKeyBlur}
            onKeyDown={handleDisplayKeyKeyDown}
            placeholder="예: answer, response, content"
            className="w-full bg-gray-900 border border-gray-600 rounded-lg text-sm text-white px-3 py-2 focus:outline-none focus:border-indigo-500 transition-colors placeholder-gray-600"
          />
          <p className="text-[10px] text-gray-500 mt-1 leading-relaxed">
            비워두면 자동 감지: markdown → _output → 가장 긴 문자열
          </p>
        </div>

        {/* Upstream fields (available inputs) */}
        {stringFields.length > 0 && (
          <div>
            <label className="block text-xs text-gray-400 mb-1.5 font-medium uppercase tracking-wider">
              사용 가능한 필드
            </label>
            <div className="bg-gray-900 border border-gray-700 rounded-lg p-2 flex flex-wrap gap-1.5">
              {stringFields.map((field) => (
                <button
                  key={field.name}
                  type="button"
                  onClick={() => {
                    setDisplayKey(field.name);
                    onUpdateConfig({ ...config, displayKey: field.name });
                  }}
                  className="inline-flex items-center gap-1 px-2 py-1 bg-gray-800 border border-gray-600 hover:border-indigo-500 hover:bg-indigo-900/20 rounded text-[11px] transition-colors cursor-pointer"
                  title="클릭하여 선택"
                >
                  <span className="font-mono text-gray-200">{field.name}</span>
                  <span className="text-gray-500">{field.type}</span>
                </button>
              ))}
            </div>
            <p className="text-[10px] text-gray-600 mt-1">필드를 클릭하면 자동 입력됩니다</p>
          </div>
        )}

        {/* All upstream fields */}
        {upstreamFields.length > 0 && (
          <div>
            <label className="block text-xs text-gray-400 mb-1.5 font-medium uppercase tracking-wider">
              모든 입력 필드
            </label>
            <div className="bg-gray-900 border border-gray-700 rounded-lg p-2 flex flex-wrap gap-1.5">
              {upstreamFields.map((field) => (
                <button
                  key={field.name}
                  type="button"
                  onClick={() => {
                    setDisplayKey(field.name);
                    onUpdateConfig({ ...config, displayKey: field.name });
                  }}
                  className="inline-flex items-center gap-1 px-2 py-1 bg-gray-800 border border-gray-600 hover:border-indigo-500 hover:bg-indigo-900/20 rounded text-[11px] transition-colors cursor-pointer"
                >
                  <span className="font-mono text-gray-200">{field.name}</span>
                  <span className="text-gray-500">{field.type}</span>
                </button>
              ))}
            </div>
          </div>
        )}
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
