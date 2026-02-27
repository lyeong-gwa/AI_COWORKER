import { useState } from 'react';
import type { AINode } from '../../types';

interface NodeDetailPanelProps {
  aiNode: AINode;
  instanceName: string;
  inputMapping: Record<string, string>;
  onUpdateName: (name: string) => void;
  onDelete: () => void;
  onClose: () => void;
}

type Tab = 'overview' | 'prompt' | 'io';

export function NodeDetailPanel({
  aiNode,
  instanceName,
  inputMapping,
  onUpdateName,
  onDelete,
  onClose,
}: NodeDetailPanelProps) {
  const [activeTab, setActiveTab] = useState<Tab>('overview');

  const tabs: { key: Tab; label: string; icon: string }[] = [
    { key: 'overview', label: '개요', icon: '📋' },
    { key: 'prompt', label: '프롬프트', icon: '💬' },
    { key: 'io', label: '입출력', icon: '🔄' },
  ];

  const inputFields = Object.entries(aiNode.inputSchema?.properties ?? {});
  const outputFields = Object.entries(aiNode.outputSchema?.properties ?? {});

  return (
    <div className="w-96 bg-gray-800 border-l border-gray-700 flex flex-col animate-slide-in-right">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-slate-700 flex items-center justify-center text-xl">
              🏭
            </div>
            <div>
              <div className="text-xs text-blue-300/70 uppercase tracking-wider">공장 상세</div>
              <div className="text-white font-semibold">{instanceName}</div>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl p-1">
            ✕
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1">
          {tabs.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-3 py-1.5 text-xs rounded-lg transition-colors flex items-center gap-1 ${
                activeTab === tab.key
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-700 text-gray-400 hover:text-gray-200'
              }`}
            >
              <span>{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        {activeTab === 'overview' && (
          <div className="space-y-4">
            {/* Instance name */}
            <div>
              <label className="block text-xs text-gray-400 mb-1">인스턴스 이름</label>
              <input
                type="text"
                value={instanceName}
                onChange={(e) => onUpdateName(e.target.value)}
                className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>

            {/* Reference node info */}
            <div className="bg-gray-900 rounded-lg p-3 space-y-2">
              <div className="text-xs text-gray-400 mb-2">참조 AI 노드</div>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-lg">{aiNode.icon}</span>
                <div>
                  <div className="text-white text-sm font-medium">{aiNode.name}</div>
                  <div className="text-gray-500 text-xs">{aiNode.description}</div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <span className="text-gray-500">모델</span>
                  <div className="text-gray-300">{aiNode.llmConfig?.model ?? '-'}</div>
                </div>
                <div>
                  <span className="text-gray-500">Temperature</span>
                  <div className="text-gray-300">{aiNode.llmConfig?.temperature ?? '-'}</div>
                </div>
                <div>
                  <span className="text-gray-500">Max Tokens</span>
                  <div className="text-gray-300">{aiNode.llmConfig?.maxTokens ?? '-'}</div>
                </div>
              </div>
            </div>

            {/* Tags */}
            {aiNode.tags.length > 0 && (
              <div>
                <div className="text-xs text-gray-400 mb-1">태그</div>
                <div className="flex flex-wrap gap-1">
                  {aiNode.tags.map(tag => (
                    <span key={tag} className="px-2 py-0.5 text-[10px] rounded bg-gray-700 text-gray-400">
                      #{tag}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'prompt' && (
          <div className="space-y-4">
            <div>
              <div className="text-xs text-gray-400 mb-1.5">시스템 프롬프트</div>
              <pre className="bg-gray-900 rounded-lg p-3 text-xs text-gray-300 whitespace-pre-wrap max-h-40 overflow-auto">
                {aiNode.systemPrompt || '(없음)'}
              </pre>
            </div>
            <div>
              <div className="text-xs text-gray-400 mb-1.5">사용자 프롬프트 템플릿</div>
              <pre className="bg-gray-900 rounded-lg p-3 text-xs text-gray-300 whitespace-pre-wrap max-h-60 overflow-auto font-mono">
                {aiNode.userPromptTemplate || '(없음)'}
              </pre>
            </div>
            <p className="text-[10px] text-gray-500 italic">
              프롬프트 수정은 노드 관리 페이지에서 할 수 있습니다.
            </p>
          </div>
        )}

        {activeTab === 'io' && (
          <div className="space-y-4">
            {/* Input Schema + Mapping */}
            <div>
              <div className="text-xs font-medium text-green-400 mb-2">입력 스키마 + 매핑</div>
              <div className="space-y-2">
                {inputFields.map(([key, prop]) => (
                  <div key={key} className="bg-gray-900 rounded-lg p-2.5">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-gray-300 text-xs font-medium">{key}</span>
                      <span className="text-gray-600 text-[10px]">{prop.type}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <div className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-400 font-mono truncate select-all">
                        {inputMapping[key] || `(자동 매핑 대기)`}
                      </div>
                      <button
                        onClick={() => {
                          const value = inputMapping[key];
                          if (value) navigator.clipboard.writeText(value);
                        }}
                        className="px-1.5 py-1 text-gray-500 hover:text-gray-300 transition-colors text-xs flex-shrink-0"
                        title="복사"
                      >
                        📋
                      </button>
                    </div>
                  </div>
                ))}
                {inputFields.length === 0 && (
                  <p className="text-gray-500 text-xs">입력 스키마 없음</p>
                )}
              </div>
            </div>

            {/* Output Schema */}
            <div>
              <div className="text-xs font-medium text-blue-400 mb-2">출력 스키마</div>
              <div className="bg-gray-900 rounded-lg p-3 space-y-1.5">
                {outputFields.map(([key, prop]) => (
                  <div key={key} className="flex items-center justify-between text-xs">
                    <span className="text-gray-300">{key}</span>
                    <span className="text-gray-600">{prop.type}</span>
                  </div>
                ))}
                {outputFields.length === 0 && (
                  <p className="text-gray-500 text-xs">출력 스키마 없음</p>
                )}
              </div>
            </div>
          </div>
        )}

      </div>

      {/* Footer actions */}
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
