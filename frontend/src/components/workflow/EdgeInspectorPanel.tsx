import { useState, useCallback } from 'react';
import { OutputRenderer } from './OutputRenderer';
import { JsonTreeView } from '../common/JsonTreeView';

// ─── Panel ────────────────────────────────────────────────────────────────────

export interface InspectedEdge {
  edgeId: string;
  sourceNodeId: string;
  targetNodeId: string;
  sourceOutput: unknown;
}

interface EdgeInspectorPanelProps {
  edge: InspectedEdge | null;
  onClose: () => void;
}

export function EdgeInspectorPanel({ edge, onClose }: EdgeInspectorPanelProps) {
  const [treeOpen, setTreeOpen] = useState(false);

  const handleClose = useCallback(() => {
    setTreeOpen(false);
    onClose();
  }, [onClose]);

  if (!edge) return null;

  return (
    <div className="absolute top-0 right-0 h-full w-[400px] bg-gray-900 border-l border-gray-700 shadow-2xl flex flex-col z-40">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700 shrink-0 bg-gray-800/80">
        <div>
          <h3 className="text-sm font-semibold text-white">엣지 데이터 검사</h3>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className="text-[11px] text-blue-400 font-mono truncate max-w-[120px]">{edge.sourceNodeId}</span>
            <svg width="14" height="10" viewBox="0 0 14 10" fill="none" className="text-gray-600 shrink-0">
              <path d="M0 5h12M8 1l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span className="text-[11px] text-gray-400 font-mono truncate max-w-[120px]">{edge.targetNodeId}</span>
          </div>
        </div>
        <button
          onClick={handleClose}
          className="text-gray-500 hover:text-gray-300 transition-colors text-lg leading-none ml-2 shrink-0"
          title="닫기"
        >
          &times;
        </button>
      </div>

      {/* Rendered output */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        <div>
          <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2">소스 출력 데이터</div>
          <OutputRenderer data={edge.sourceOutput} />
        </div>

        {/* Tree view collapsible */}
        {edge.sourceOutput !== null && edge.sourceOutput !== undefined && (
          <div className="border border-gray-700 rounded-lg overflow-hidden">
            <button
              onClick={() => setTreeOpen((v) => !v)}
              className="w-full flex items-center justify-between px-3 py-2 bg-gray-800/50 hover:bg-gray-800 transition-colors text-left"
            >
              <span className="text-xs text-gray-400 font-medium">트리뷰</span>
              <span className="text-[10px] text-gray-600">{treeOpen ? '▴' : '▾'}</span>
            </button>
            {treeOpen && (
              <div className="px-3 py-2.5 bg-gray-900/60 overflow-auto max-h-64">
                <JsonTreeView data={edge.sourceOutput} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default EdgeInspectorPanel;
