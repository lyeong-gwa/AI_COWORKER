import { useState, useMemo } from 'react';

interface UpstreamField {
  name: string;
  type: string;
}

interface MapperConfigPanelProps {
  nodeId: string;
  nodeName: string;
  config: {
    warehouseNodeId?: string;
    warehouseNodeName?: string;
    matchKey?: string;
    outputField?: string;
  };
  upstreamFields: UpstreamField[];
  allNodes?: { id: string; data: Record<string, unknown> }[];
  onUpdateName: (name: string) => void;
  onUpdateConfig: (config: MapperConfigPanelProps['config']) => void;
  onDelete: () => void;
  onClose: () => void;
}

export function MapperConfigPanel({
  nodeId,
  nodeName,
  config,
  upstreamFields,
  allNodes = [],
  onUpdateName,
  onUpdateConfig,
  onDelete,
  onClose,
}: MapperConfigPanelProps) {
  const warehouseNodeId = config.warehouseNodeId || '';
  const matchKey = config.matchKey || '';
  const outputField = config.outputField || 'matchedItems';

  const [matchKeyInput, setMatchKeyInput] = useState(matchKey);

  // Suppress unused var lint
  void nodeId;

  // 캔버스의 창고(result) 노드 목록 수집
  const warehouseNodes = useMemo(() => {
    return allNodes.filter(n => {
      const defType = n.data.definitionType as string | undefined;
      return defType === 'result' || defType === 'markdown-viewer';
    }).map(n => ({
      id: n.id,
      name: (n.data.instanceName as string) || n.id,
    }));
  }, [allNodes]);

  const handleSelectWarehouse = (id: string) => {
    const node = warehouseNodes.find(n => n.id === id);
    onUpdateConfig({
      ...config,
      warehouseNodeId: id,
      warehouseNodeName: node?.name || id,
    });
  };

  const handleSelectMatchKey = (fieldName: string) => {
    const newKey = matchKey === fieldName ? '' : fieldName;
    setMatchKeyInput(newKey);
    onUpdateConfig({ ...config, matchKey: newKey });
  };

  const handleMatchKeyDirect = () => {
    const trimmed = matchKeyInput.trim();
    if (trimmed) {
      onUpdateConfig({ ...config, matchKey: trimmed });
    }
  };

  const handleOutputFieldChange = (value: string) => {
    onUpdateConfig({ ...config, outputField: value || 'matchedItems' });
  };

  return (
    <div className="w-96 bg-gray-800 border-l border-gray-700 flex flex-col animate-slide-in-right">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-indigo-900 flex items-center justify-center text-xl">
              🔗
            </div>
            <div>
              <div className="text-xs text-indigo-300/70 uppercase tracking-wider">매퍼 설정</div>
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
        {/* 설명 */}
        <div className="bg-gray-900 rounded-lg p-3">
          <div className="text-xs text-gray-400 mb-2">매퍼란?</div>
          <p className="text-gray-300 text-xs leading-relaxed">
            <strong className="text-indigo-300">창고</strong>에 쌓인 데이터 중,
            입력 데이터와 <strong className="text-indigo-300">동일한 키 값</strong>을 가진
            항목들을 찾아 입력에 병합합니다.
          </p>
        </div>

        {/* 동작 예시 */}
        <div className="bg-gray-900 rounded-lg p-3">
          <div className="text-[10px] text-gray-500 mb-2">동작 예시</div>
          <div className="space-y-1 text-[10px] font-mono">
            <div className="text-gray-400">입력: {'{'} title: "문의", category: "서버" {'}'}</div>
            <div className="text-indigo-400">+ 창고: [{'{'} category:"서버", ... {'}'}, {'{'} category:"DB", ... {'}'}]</div>
            <div className="text-gray-500">↓ 매칭 키: "category"</div>
            <div className="text-green-400">출력: {'{'} title, category, matchedItems: [서버 항목들] {'}'}</div>
          </div>
        </div>

        {/* Step 1: 창고 노드 선택 */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5">
            <span className="text-indigo-400 font-semibold mr-1">1</span>
            창고 노드 선택
          </label>
          {warehouseNodes.length > 0 ? (
            <div className="space-y-1.5">
              {warehouseNodes.map(node => {
                const isSelected = warehouseNodeId === node.id;
                return (
                  <button
                    key={node.id}
                    onClick={() => handleSelectWarehouse(node.id)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg border transition-all text-left ${
                      isSelected
                        ? 'bg-indigo-900/50 border-indigo-400 ring-1 ring-indigo-400/50'
                        : 'bg-gray-900 border-gray-600 hover:border-indigo-500/50'
                    }`}
                  >
                    <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
                      isSelected ? 'border-indigo-400 bg-indigo-400' : 'border-gray-500'
                    }`}>
                      {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-lg">📦</span>
                      <span className="text-sm text-gray-200">{node.name}</span>
                    </div>
                    {isSelected && <span className="text-indigo-300 text-sm ml-auto">✓</span>}
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="bg-gray-900 rounded-lg p-4 text-center">
              <div className="text-gray-500 text-xs mb-1">캔버스에 창고 노드가 없습니다</div>
              <p className="text-gray-600 text-[10px]">
                먼저 창고 노드를 추가해주세요.
              </p>
            </div>
          )}
        </div>

        {/* Step 2: 매칭 키 선택 */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5">
            <span className="text-indigo-400 font-semibold mr-1">2</span>
            매칭 키 (입력과 창고 데이터의 공통 필드)
          </label>
          {upstreamFields.length > 0 && (
            <div className="space-y-1.5 mb-2">
              {upstreamFields.map(field => {
                const isSelected = matchKey === field.name;
                return (
                  <button
                    key={field.name}
                    onClick={() => handleSelectMatchKey(field.name)}
                    className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg border transition-all text-left ${
                      isSelected
                        ? 'bg-indigo-900/50 border-indigo-400 ring-1 ring-indigo-400/50'
                        : 'bg-gray-900/50 border-gray-700 hover:border-gray-500'
                    }`}
                  >
                    <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
                      isSelected ? 'border-indigo-400 bg-indigo-400' : 'border-gray-500'
                    }`}>
                      {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-gray-200 font-mono">{field.name}</span>
                      <span className="px-1.5 py-0.5 text-[9px] rounded border bg-gray-600/40 text-gray-300 border-gray-500/50">
                        {field.type}
                      </span>
                    </div>
                    {isSelected && <span className="text-indigo-300 text-sm ml-auto">✓</span>}
                  </button>
                );
              })}
            </div>
          )}
          {/* 직접 입력 */}
          <div className="bg-gray-900 rounded-lg p-2.5">
            <div className="text-[10px] text-gray-500 mb-1.5">직접 입력 (중첩 경로 지원: data.category)</div>
            <div className="flex gap-2">
              <input
                type="text"
                value={matchKeyInput}
                onChange={(e) => setMatchKeyInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleMatchKeyDirect()}
                placeholder="예: category"
                className="flex-1 bg-gray-800 border border-gray-600 rounded px-2.5 py-1.5 text-xs text-gray-200 font-mono placeholder-gray-600 outline-none focus:border-indigo-500"
              />
              <button
                onClick={handleMatchKeyDirect}
                disabled={!matchKeyInput.trim()}
                className="px-3 py-1.5 bg-indigo-600/30 text-indigo-300 rounded text-xs hover:bg-indigo-600/50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                적용
              </button>
            </div>
          </div>
        </div>

        {/* Step 3: 출력 필드명 */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5">
            <span className="text-indigo-400 font-semibold mr-1">3</span>
            출력 필드명 (매칭 결과가 담길 키)
          </label>
          <input
            type="text"
            value={outputField}
            onChange={(e) => handleOutputFieldChange(e.target.value)}
            placeholder="matchedItems"
            className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 font-mono placeholder-gray-600 outline-none focus:border-indigo-500"
          />
        </div>

        {/* Status */}
        <div className="flex items-center gap-2 bg-gray-900 rounded-lg p-3">
          <div className={`w-2.5 h-2.5 rounded-full ${warehouseNodeId && matchKey ? 'bg-indigo-400' : 'bg-gray-500 animate-pulse'}`} />
          <span className="text-xs text-gray-400">
            {warehouseNodeId && matchKey ? (
              <>
                <span className="text-indigo-300 font-mono">{matchKey}</span> 기준으로 매칭 →{' '}
                <span className="text-indigo-300 font-mono">{outputField}</span>
              </>
            ) : (
              '창고 노드와 매칭 키를 설정해주세요'
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
