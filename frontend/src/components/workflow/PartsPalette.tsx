import { useState } from 'react';
import type { DragEvent } from 'react';
import type { AINode } from '../../types';

const START_DEFS = [
  { definitionType: 'form-start', icon: '\u{1F4CB}', label: '폼 입력 시작',   desc: '폼으로 원료 생성',       bg: 'from-amber-700 to-amber-900', border: 'border-amber-500', textColor: 'text-amber-100', descColor: 'text-amber-300/60' },
  { definitionType: 'api-start',  icon: '\u{1F680}', label: 'API 호출 시작',  desc: 'API 호출로 원료 생성',    bg: 'from-teal-700 to-teal-900',   border: 'border-teal-500',  textColor: 'text-teal-100',  descColor: 'text-teal-300/60' },
];

const WAREHOUSE_DEF = {
  definitionType: 'result',
  icon: '\u{1F4E6}',
  label: '창고',
  desc: '가공 결과물 축적',
  bg: 'from-emerald-700 to-emerald-900',
  border: 'border-emerald-500',
};

const SORTER_DEF = {
  definitionType: 'sorter',
  icon: '\u{1F500}',
  label: '분류기',
  desc: '조건별 분기 + 데이터 보관',
  bg: 'from-violet-700 to-violet-900',
  border: 'border-violet-500',
};

const API_CALL_DEF = {
  definitionType: 'api-call',
  icon: '\u{1F310}',
  label: 'API 호출기',
  desc: '문서 기반 API 직접 호출',
  bg: 'from-cyan-700 to-cyan-900',
  border: 'border-cyan-500',
};

const UNPACKER_DEF = {
  definitionType: 'unpacker',
  icon: '\u{1F4E4}',
  label: '언패커',
  desc: '배열을 개별 객체로 분배',
  bg: 'from-rose-700 to-rose-900',
  border: 'border-rose-500',
};

const KNOWLEDGE_DEF = {
  definitionType: 'knowledge',
  icon: '\u{1F4DA}',
  label: '지식 검색',
  desc: '지식 베이스에서 관련 문서 검색',
  bg: 'from-indigo-700 to-indigo-900',
  border: 'border-indigo-500',
};

interface PartsPaletteProps {
  aiNodes: AINode[];
}

export function PartsPalette({ aiNodes }: PartsPaletteProps) {
  const [searchQuery, setSearchQuery] = useState('');

  const filteredNodes = searchQuery
    ? aiNodes.filter(
        (n) =>
          n.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          n.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
          n.tags.some((t) => t.toLowerCase().includes(searchQuery.toLowerCase()))
      )
    : aiNodes;

  const onStarterDragStart = (event: DragEvent, defType: string) => {
    event.dataTransfer.setData(
      'application/starternode',
      JSON.stringify({ type: defType, definitionType: defType })
    );
    event.dataTransfer.effectAllowed = 'move';
  };

  const onSystemDragStart = (event: DragEvent, defType: string, nodeType: string) => {
    event.dataTransfer.setData(
      'application/systemnode',
      JSON.stringify({ type: nodeType, definitionType: defType })
    );
    event.dataTransfer.effectAllowed = 'move';
  };

  const onFactoryDragStart = (event: DragEvent, aiNode: AINode) => {
    event.dataTransfer.setData('application/ainode', JSON.stringify(aiNode));
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div className="w-72 bg-gray-800 border-r border-gray-700 flex flex-col">
      {/* Header */}
      <div className="p-3 border-b border-gray-700">
        <h3 className="text-white font-semibold mb-1 flex items-center gap-2">
          <span className="text-lg">{'\u{1F529}'}</span>
          부품 팔레트
        </h3>
        <p className="text-gray-500 text-[10px] mb-2">드래그하여 맵에 배치</p>
        <input
          type="text"
          placeholder="공장 검색..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
        />
      </div>

      {/* Parts list */}
      <div className="flex-1 overflow-auto p-2 space-y-3">
        {/* Start points section */}
        <div>
          <div className="text-xs font-semibold text-amber-400/80 uppercase tracking-wider px-1 mb-1.5 flex items-center gap-1">
            <span>{'\u{1F3AF}'}</span> 시작지점 (원료 생성)
          </div>
          <div className="space-y-1.5">
            {START_DEFS.map((def) => (
              <div
                key={def.definitionType}
                draggable
                onDragStart={(e) => onStarterDragStart(e, def.definitionType)}
                className={`bg-gradient-to-r ${def.bg} border ${def.border} hover:brightness-125 rounded-lg p-2.5 cursor-grab active:cursor-grabbing transition-all`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-lg">{def.icon}</span>
                  <div>
                    <div className={`font-medium text-xs ${def.textColor}`}>{def.label}</div>
                    <div className={`${def.descColor} text-[10px]`}>{def.desc}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Factory (AI nodes) section */}
        <div>
          <div className="text-xs font-semibold text-blue-400/80 uppercase tracking-wider px-1 mb-1.5 flex items-center gap-1">
            <span>{'\u{1F3ED}'}</span> 공장 (AI 가공)
          </div>
          <div className="space-y-1.5">
            {filteredNodes.map((node) => (
              <div
                key={node.id}
                draggable
                onDragStart={(e) => onFactoryDragStart(e, node)}
                className="bg-gradient-to-r from-slate-700 to-slate-800 border border-slate-500 hover:border-slate-400 rounded-lg p-2.5 cursor-grab active:cursor-grabbing transition-colors"
              >
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-lg">{node.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-white font-medium text-xs truncate">{node.name}</div>
                    <div className="text-slate-400 text-[10px] truncate">{node.description}</div>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1">
                  <span className="px-1.5 py-0.5 text-[9px] rounded bg-blue-900/60 text-blue-300">
                    {node.llmConfig?.model ?? 'default'}
                  </span>
                </div>
              </div>
            ))}
            {filteredNodes.length === 0 && (
              <p className="text-gray-500 text-xs text-center py-4">
                {searchQuery ? '검색 결과 없음' : '노드 관리에서 AI 노드를 생성하세요'}
              </p>
            )}
          </div>
        </div>

        {/* Sorter section */}
        <div>
          <div className="text-xs font-semibold text-violet-400/80 uppercase tracking-wider px-1 mb-1.5 flex items-center gap-1">
            <span>{'\u{1F500}'}</span> 분류기 (조건 분기)
          </div>
          <div
            draggable
            onDragStart={(e) => onSystemDragStart(e, 'sorter', 'sorter')}
            className={`bg-gradient-to-r ${SORTER_DEF.bg} border ${SORTER_DEF.border} hover:brightness-125 rounded-lg p-2.5 cursor-grab active:cursor-grabbing transition-all`}
          >
            <div className="flex items-center gap-2">
              <span className="text-lg">{SORTER_DEF.icon}</span>
              <div>
                <div className="font-medium text-xs text-violet-100">{SORTER_DEF.label}</div>
                <div className="text-violet-300/60 text-[10px]">{SORTER_DEF.desc}</div>
              </div>
            </div>
          </div>
        </div>

        {/* API Call section */}
        <div>
          <div className="text-xs font-semibold text-cyan-400/80 uppercase tracking-wider px-1 mb-1.5 flex items-center gap-1">
            <span>{'\u{1F310}'}</span> API 호출기 (직접 호출)
          </div>
          <div
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData('application/apicallnode', JSON.stringify({ type: 'api-call' }));
              e.dataTransfer.effectAllowed = 'move';
            }}
            className={`bg-gradient-to-r ${API_CALL_DEF.bg} border ${API_CALL_DEF.border} hover:brightness-125 rounded-lg p-2.5 cursor-grab active:cursor-grabbing transition-all`}
          >
            <div className="flex items-center gap-2">
              <span className="text-lg">{API_CALL_DEF.icon}</span>
              <div>
                <div className="font-medium text-xs text-cyan-100">{API_CALL_DEF.label}</div>
                <div className="text-cyan-300/60 text-[10px]">{API_CALL_DEF.desc}</div>
              </div>
            </div>
          </div>
        </div>

        {/* Knowledge section */}
        <div>
          <div className="text-xs font-semibold text-indigo-400/80 uppercase tracking-wider px-1 mb-1.5 flex items-center gap-1">
            <span>{'\u{1F4DA}'}</span> 지식 검색
          </div>
          <div
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData('application/knowledgenode', JSON.stringify({ type: 'knowledge' }));
              e.dataTransfer.effectAllowed = 'move';
            }}
            className={`bg-gradient-to-r ${KNOWLEDGE_DEF.bg} border ${KNOWLEDGE_DEF.border} hover:brightness-125 rounded-lg p-2.5 cursor-grab active:cursor-grabbing transition-all`}
          >
            <div className="flex items-center gap-2">
              <span className="text-lg">{KNOWLEDGE_DEF.icon}</span>
              <div>
                <div className="font-medium text-xs text-indigo-100">{KNOWLEDGE_DEF.label}</div>
                <div className="text-indigo-300/60 text-[10px]">{KNOWLEDGE_DEF.desc}</div>
              </div>
            </div>
          </div>
        </div>

        {/* Warehouse section */}
        <div>
          <div className="text-xs font-semibold text-emerald-400/80 uppercase tracking-wider px-1 mb-1.5 flex items-center gap-1">
            <span>{'\u{1F4E6}'}</span> 창고 (결과 축적)
          </div>
          <div
            draggable
            onDragStart={(e) => onSystemDragStart(e, 'result', 'result')}
            className={`bg-gradient-to-r ${WAREHOUSE_DEF.bg} border ${WAREHOUSE_DEF.border} hover:brightness-125 rounded-lg p-2.5 cursor-grab active:cursor-grabbing transition-all`}
          >
            <div className="flex items-center gap-2">
              <span className="text-lg">{WAREHOUSE_DEF.icon}</span>
              <div>
                <div className="font-medium text-xs text-emerald-100">{WAREHOUSE_DEF.label}</div>
                <div className="text-emerald-300/60 text-[10px]">{WAREHOUSE_DEF.desc}</div>
              </div>
            </div>
          </div>
        </div>

        {/* Unpacker section */}
        <div>
          <div className="text-xs font-semibold text-rose-400/80 uppercase tracking-wider px-1 mb-1.5 flex items-center gap-1">
            <span>{'\u{1F4E4}'}</span> 언패커 (배열 분배)
          </div>
          <div
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData('application/unpackernode', JSON.stringify({ type: 'unpacker' }));
              e.dataTransfer.effectAllowed = 'move';
            }}
            className={`bg-gradient-to-r ${UNPACKER_DEF.bg} border ${UNPACKER_DEF.border} hover:brightness-125 rounded-lg p-2.5 cursor-grab active:cursor-grabbing transition-all`}
          >
            <div className="flex items-center gap-2">
              <span className="text-lg">{UNPACKER_DEF.icon}</span>
              <div>
                <div className="font-medium text-xs text-rose-100">{UNPACKER_DEF.label}</div>
                <div className="text-rose-300/60 text-[10px]">{UNPACKER_DEF.desc}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-gray-700 text-[10px] text-gray-500">
        노드를 드래그하여 공장 맵에 배치하세요
      </div>
    </div>
  );
}
