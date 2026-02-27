interface UpstreamField {
  name: string;
  type: string;
}

interface UnpackerConfigPanelProps {
  nodeId: string;
  nodeName: string;
  config: {
    arrayField?: string;
  };
  upstreamFields: UpstreamField[];
  onUpdateName: (name: string) => void;
  onUpdateConfig: (config: UnpackerConfigPanelProps['config']) => void;
  onDelete: () => void;
  onClose: () => void;
}

export function UnpackerConfigPanel({
  nodeId,
  nodeName,
  config,
  upstreamFields,
  onUpdateName,
  onUpdateConfig,
  onDelete,
  onClose,
}: UnpackerConfigPanelProps) {
  const arrayField = config.arrayField || '';

  const handleSelectField = (fieldName: string) => {
    // Toggle: same field clicked again → deselect
    const newValue = arrayField === fieldName ? '' : fieldName;
    onUpdateConfig({ arrayField: newValue });
  };

  // Suppress unused var lint
  void nodeId;

  // Type badge colors
  const typeBadge = (type: string) => {
    if (type === 'array') return 'bg-rose-600/60 text-rose-200 border-rose-500/50';
    if (type === 'object') return 'bg-amber-600/40 text-amber-200 border-amber-500/50';
    return 'bg-gray-600/40 text-gray-300 border-gray-500/50';
  };

  // Is the type likely an array?
  const isArrayLike = (type: string) => type === 'array' || type === 'object';

  return (
    <div className="w-96 bg-gray-800 border-l border-gray-700 flex flex-col animate-slide-in-right">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-rose-900 flex items-center justify-center text-xl">
              📤
            </div>
            <div>
              <div className="text-xs text-rose-300/70 uppercase tracking-wider">언패커 설정</div>
              <input
                type="text"
                value={nodeName}
                onChange={(e) => onUpdateName(e.target.value)}
                className="bg-transparent text-white font-semibold text-sm border-none outline-none w-full"
                placeholder="이름 입력..."
              />
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl p-1">
            ✕
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {/* What is unpacker */}
        <div className="bg-gray-900 rounded-lg p-3">
          <div className="text-xs text-gray-400 mb-2">언패커란?</div>
          <p className="text-gray-300 text-xs leading-relaxed">
            이전 노드의 출력에서 <strong className="text-rose-300">배열(object[])</strong> 필드를 선택하면,
            배열의 각 원소를 <strong className="text-rose-300">개별 객체</strong>로 분리하여
            다음 노드에 하나씩 전달합니다.
          </p>
        </div>

        {/* Visual explanation */}
        <div className="bg-gray-900 rounded-lg p-3">
          <div className="text-[10px] text-gray-500 mb-2">동작 예시</div>
          <div className="space-y-1 text-[10px] font-mono">
            <div className="text-gray-400">입력: {'{'} data: [A, B, C] {'}'}</div>
            <div className="text-rose-400 flex items-center gap-1">
              <span>↓</span> 선택: "data"
            </div>
            <div className="text-green-400">출력 1: A</div>
            <div className="text-green-400">출력 2: B</div>
            <div className="text-green-400">출력 3: C</div>
          </div>
        </div>

        {/* Upstream field selection */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5">배열 필드 선택</label>
          {upstreamFields.length > 0 ? (
            <div className="space-y-1.5">
              {upstreamFields.map(field => {
                const isSelected = arrayField === field.name;
                const isRecommended = isArrayLike(field.type);
                return (
                  <button
                    key={field.name}
                    onClick={() => handleSelectField(field.name)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg border transition-all text-left ${
                      isSelected
                        ? 'bg-rose-900/50 border-rose-400 ring-1 ring-rose-400/50'
                        : isRecommended
                          ? 'bg-gray-900 border-gray-600 hover:border-rose-500/50 hover:bg-gray-900/80'
                          : 'bg-gray-900/50 border-gray-700 hover:border-gray-500 opacity-60 hover:opacity-80'
                    }`}
                  >
                    {/* Radio indicator */}
                    <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
                      isSelected ? 'border-rose-400 bg-rose-400' : 'border-gray-500'
                    }`}>
                      {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                    </div>

                    {/* Field info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-gray-200 font-mono">{field.name}</span>
                        <span className={`px-1.5 py-0.5 text-[9px] rounded border ${typeBadge(field.type)}`}>
                          {field.type}
                        </span>
                        {isRecommended && (
                          <span className="text-[9px] text-rose-400/70">추천</span>
                        )}
                      </div>
                    </div>

                    {/* Check icon */}
                    {isSelected && (
                      <span className="text-rose-300 text-sm">✓</span>
                    )}
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="bg-gray-900 rounded-lg p-4 text-center">
              <div className="text-gray-500 text-xs mb-1">상위 노드가 연결되지 않았습니다</div>
              <p className="text-gray-600 text-[10px]">
                컨베이어벨트로 이전 노드를 연결하면 출력 필드가 표시됩니다.
              </p>
            </div>
          )}
        </div>

        {/* Status */}
        <div className="flex items-center gap-2 bg-gray-900 rounded-lg p-3">
          <div className={`w-2.5 h-2.5 rounded-full ${arrayField ? 'bg-rose-400' : 'bg-gray-500 animate-pulse'}`} />
          <span className="text-xs text-gray-400">
            {arrayField ? (
              <>
                <span className="text-rose-300 font-mono">{arrayField}</span> 필드의 각 원소를 분배합니다
              </>
            ) : (
              '배열 필드를 선택해주세요'
            )}
          </span>
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
