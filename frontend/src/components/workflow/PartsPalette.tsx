import { useState } from 'react';
import type { DragEvent } from 'react';
import type { AINode } from '../../types';
import { nodeRegistry } from '../../nodes';

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

  // 시스템 노드 (팔레트에 표시되는 모든 비-AI 노드)
  const starterNodes = nodeRegistry.getPaletteNodes('starter');
  const logicNodes = nodeRegistry.getPaletteNodes('logic');
  const actionNodes = nodeRegistry.getPaletteNodes('action');
  const outputNodes = nodeRegistry.getPaletteNodes('output');
  const systemNodes = [...logicNodes, ...actionNodes, ...outputNodes];

  const onStarterDragStart = (event: DragEvent, defType: string) => {
    const def = nodeRegistry.get(defType);
    if (!def?.palette?.dragType) return;
    event.dataTransfer.setData(
      def.palette.dragType,
      JSON.stringify({ type: defType, definitionType: defType })
    );
    event.dataTransfer.effectAllowed = 'move';
  };

  const onSystemDragStart = (event: DragEvent, defType: string) => {
    const def = nodeRegistry.get(defType);
    if (!def?.palette?.dragType) return;
    event.dataTransfer.setData(
      def.palette.dragType,
      JSON.stringify({ type: defType, definitionType: defType })
    );
    event.dataTransfer.effectAllowed = 'move';
  };

  const onAINodeDragStart = (event: DragEvent, aiNode: AINode) => {
    event.dataTransfer.setData('application/ainode', JSON.stringify(aiNode));
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div className="w-56 bg-gray-900/50 border-r border-gray-700/50 flex flex-col overflow-hidden">
      {/* 검색 */}
      <div className="p-2 border-b border-gray-700/50">
        <input
          type="text"
          placeholder="부품 검색..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full px-2 py-1.5 text-xs bg-gray-800 border border-gray-600 rounded text-gray-200 placeholder-gray-500"
        />
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-3">
        {/* 시작 노드 */}
        <div>
          <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5">시작</div>
          <div className="space-y-1">
            {starterNodes.map((def) => (
              <div
                key={def.defType}
                draggable
                onDragStart={(e) => onStarterDragStart(e, def.defType)}
                className={`p-2 rounded border ${def.palette!.border} bg-gradient-to-r ${def.palette!.bg} cursor-grab active:cursor-grabbing hover:brightness-110 transition-all`}
              >
                <div className="flex items-center gap-1.5">
                  <span className="text-sm">{def.palette!.icon}</span>
                  <span className={`text-xs font-medium ${def.palette!.textColor || 'text-gray-100'}`}>{def.palette!.label}</span>
                </div>
                <div className={`text-[10px] mt-0.5 ${def.palette!.descColor || 'text-gray-400/60'}`}>{def.palette!.description}</div>
              </div>
            ))}
          </div>
        </div>

        {/* 시스템 노드 */}
        <div>
          <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5">시스템</div>
          <div className="space-y-1">
            {systemNodes.map((def) => (
              <div
                key={def.defType}
                draggable
                onDragStart={(e) => onSystemDragStart(e, def.defType)}
                className={`p-2 rounded border ${def.palette!.border} bg-gradient-to-r ${def.palette!.bg} cursor-grab active:cursor-grabbing hover:brightness-110 transition-all`}
              >
                <div className="flex items-center gap-1.5">
                  <span className="text-sm">{def.palette!.icon}</span>
                  <span className="text-xs font-medium text-gray-100">{def.palette!.label}</span>
                </div>
                <div className="text-[10px] mt-0.5 text-gray-400/60">{def.palette!.description}</div>
              </div>
            ))}
          </div>
        </div>

        {/* AI 노드 */}
        <div>
          <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5">
            AI 노드 ({filteredNodes.length})
          </div>
          <div className="space-y-1">
            {filteredNodes.map((aiNode) => (
              <div
                key={aiNode.id}
                draggable
                onDragStart={(e) => onAINodeDragStart(e, aiNode)}
                className="p-2 rounded border border-gray-600 bg-gradient-to-r from-gray-700 to-gray-800 cursor-grab active:cursor-grabbing hover:brightness-110 transition-all"
              >
                <div className="flex items-center gap-1.5">
                  <span className="text-sm">{'\u{1F3ED}'}</span>
                  <span className="text-xs font-medium text-gray-100 truncate">{aiNode.name}</span>
                </div>
                <div className="text-[10px] mt-0.5 text-gray-400/60 truncate">{aiNode.description}</div>
                {aiNode.tags.length > 0 && (
                  <div className="flex gap-1 mt-1 flex-wrap">
                    {aiNode.tags.slice(0, 2).map((tag) => (
                      <span key={tag} className="text-[9px] px-1 py-0.5 bg-gray-600/50 rounded text-gray-400">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
