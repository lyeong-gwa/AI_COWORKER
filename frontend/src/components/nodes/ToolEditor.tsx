import { useState, useEffect } from 'react';
import type { ToolType, ToolDefinition } from '../../types';
import { toolApi } from '../../services/api';

// ============================================
// 노드에서 도구 참조 (읽기 전용)
// - 도구는 "도구 관리" 페이지에서만 생성/수정
// - 노드에서는 라이브러리의 도구를 참조만 함
// ============================================

const TOOL_TYPE_LABELS: Record<ToolType, { label: string; icon: string }> = {
  api_call:       { label: 'API 호출기',  icon: '🌐' },
  file_read:      { label: '파일 읽기',   icon: '📄' },
  file_write:     { label: '파일 쓰기',   icon: '📝' },
  code_execute:   { label: '코드 실행',   icon: '💻' },
  database_query: { label: 'DB 쿼리',    icon: '🗄️' },
};

// ─── 도구 참조 카드 (읽기 전용) ────────────────────────────────────────────────

function LinkedToolCard({
  tool,
  toolId,
  onUnlink,
}: {
  tool?: ToolDefinition;
  toolId: string;
  onUnlink: () => void;
}) {
  const [expanded, setExpanded] = useState(false);

  // 라이브러리에서 도구 정의 가져오기
  const def = tool;

  if (!def) {
    return (
      <div className="bg-gray-900 border border-red-600/50 rounded-lg p-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-red-400">
            <span>⚠️</span>
            <span className="text-sm">도구를 찾을 수 없음: {toolId}</span>
          </div>
          <button
            onClick={onUnlink}
            className="text-gray-500 hover:text-red-400 transition-colors text-sm"
            title="연결 해제"
          >
            ✕
          </button>
        </div>
      </div>
    );
  }

  const meta = TOOL_TYPE_LABELS[def.type];

  return (
    <div className="bg-gray-900 border border-gray-600 rounded-lg overflow-hidden">
      {/* 헤더 */}
      <div
        className="flex items-center justify-between px-3 py-2.5 bg-gray-800 border-b border-gray-700 cursor-pointer select-none"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2.5">
          <span className={`text-xl p-1 rounded ${def.color} bg-opacity-20`}>{def.icon}</span>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-200 font-medium">{def.name}</span>
              <span className="text-xs bg-gray-700 text-gray-400 px-1.5 py-0.5 rounded">
                {meta.icon} {meta.label}
              </span>
              <span className="text-xs bg-blue-900/50 text-blue-400 px-1.5 py-0.5 rounded">
                🔗 연결됨
              </span>
            </div>
            <p className="text-xs text-gray-500">{def.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-gray-600 text-xs">{expanded ? '▲' : '▼'}</span>
          <button
            onClick={(e) => { e.stopPropagation(); onUnlink(); }}
            className="text-gray-500 hover:text-red-400 transition-colors text-sm"
            title="연결 해제"
          >
            ✕
          </button>
        </div>
      </div>

      {/* 상세 정보 (읽기 전용) */}
      {expanded && (
        <div className="p-3 space-y-3 bg-gray-900/50">
          {/* 태그 */}
          {def.tags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {def.tags.map(tag => (
                <span key={tag} className="px-2 py-0.5 text-xs rounded bg-gray-700 text-gray-400">
                  #{tag}
                </span>
              ))}
            </div>
          )}

          {/* 타입별 설정 미리보기 (읽기 전용) */}
          <div className="bg-gray-800 rounded-lg p-3 border border-gray-700">
            <div className="text-xs text-gray-500 mb-2 flex items-center gap-1">
              <span>📋</span> 설정 정보 (읽기 전용)
            </div>
            {def.type === 'api_call' && (
              <div className="space-y-1.5 text-xs">
                <div className="flex gap-2">
                  <span className="text-gray-500 w-16">Method:</span>
                  <span className="text-green-400 font-mono">{(def.config as {method: string}).method}</span>
                </div>
                <div className="flex gap-2">
                  <span className="text-gray-500 w-16">URL:</span>
                  <span className="text-blue-400 font-mono truncate">{(def.config as {urlTemplate: string}).urlTemplate}</span>
                </div>
              </div>
            )}
            {def.type === 'file_read' && (
              <div className="space-y-1.5 text-xs">
                <div className="flex gap-2">
                  <span className="text-gray-500 w-16">경로:</span>
                  <span className="text-blue-400 font-mono">{(def.config as {pathTemplate: string}).pathTemplate}</span>
                </div>
                <div className="flex gap-2">
                  <span className="text-gray-500 w-16">인코딩:</span>
                  <span className="text-gray-300">{(def.config as {encoding?: string}).encoding || 'utf-8'}</span>
                </div>
              </div>
            )}
            {def.type === 'file_write' && (
              <div className="space-y-1.5 text-xs">
                <div className="flex gap-2">
                  <span className="text-gray-500 w-16">경로:</span>
                  <span className="text-blue-400 font-mono">{(def.config as {pathTemplate: string}).pathTemplate}</span>
                </div>
              </div>
            )}
            {def.type === 'code_execute' && (
              <div className="space-y-1.5 text-xs">
                <div className="flex gap-2">
                  <span className="text-gray-500 w-16">언어:</span>
                  <span className="text-yellow-400">{(def.config as {language: string}).language}</span>
                </div>
                <div className="mt-2">
                  <span className="text-gray-500">코드 미리보기:</span>
                  <pre className="mt-1 p-2 bg-gray-900 rounded text-gray-400 font-mono overflow-x-auto">
                    {(def.config as {code: string}).code.slice(0, 100)}
                    {(def.config as {code: string}).code.length > 100 && '...'}
                  </pre>
                </div>
              </div>
            )}
            {def.type === 'database_query' && (
              <div className="text-xs">
                <span className="text-gray-500">쿼리:</span>
                <pre className="mt-1 p-2 bg-gray-900 rounded text-gray-400 font-mono overflow-x-auto">
                  {(def.config as {queryTemplate: string}).queryTemplate.slice(0, 100)}
                  {(def.config as {queryTemplate: string}).queryTemplate.length > 100 && '...'}
                </pre>
              </div>
            )}
          </div>

          {/* 수정 안내 */}
          <p className="text-xs text-gray-600 italic">
            💡 도구 설정을 변경하려면 "도구 관리" 페이지에서 수정하세요.
          </p>
        </div>
      )}
    </div>
  );
}

// ─── 라이브러리에서 도구 선택 패널 ───────────────────────────────────────────────

function LibraryPickerPanel({
  onPick,
  linkedToolIds,
  allTools,
}: {
  onPick: (def: ToolDefinition) => void;
  linkedToolIds: string[];
  allTools: ToolDefinition[];
}) {
  const [filter, setFilter] = useState<ToolType | null>(null);
  const [search, setSearch] = useState('');

  const visible = allTools.filter(d => {
    // 이미 연결된 도구는 제외
    if (linkedToolIds.includes(d.id)) return false;
    if (filter && d.type !== filter) return false;
    if (search) {
      const q = search.toLowerCase();
      return d.name.toLowerCase().includes(q) ||
             d.description.toLowerCase().includes(q) ||
             d.tags.some(t => t.includes(q));
    }
    return true;
  });

  return (
    <div className="space-y-3">
      {/* 검색 + 타입 필터 */}
      <div className="flex gap-2 items-center flex-wrap">
        <div className="relative flex-1" style={{ minWidth: 140 }}>
          <input
            type="text"
            placeholder="도구 검색..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 pl-8 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500 text-xs">🔍</span>
        </div>
        <button
          onClick={() => setFilter(null)}
          className={`px-2 py-0.5 rounded text-xs transition-colors ${!filter ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}`}
        >
          전체
        </button>
        {(['api_call', 'file_read', 'file_write', 'code_execute', 'database_query'] as ToolType[]).map(t => (
          <button
            key={t}
            onClick={() => setFilter(filter === t ? null : t)}
            className={`px-2 py-0.5 rounded text-xs transition-colors ${filter === t ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}`}
          >
            {TOOL_TYPE_LABELS[t].icon} {TOOL_TYPE_LABELS[t].label}
          </button>
        ))}
      </div>

      {/* 도구 목록 */}
      {visible.length === 0 ? (
        <div className="text-center py-6">
          <p className="text-gray-500 text-sm mb-2">
            {linkedToolIds.length === allTools.length
              ? '모든 도구가 이미 연결되어 있습니다'
              : '조건에 맞는 도구가 없습니다'}
          </p>
          <p className="text-xs text-gray-600">
            새 도구는 "도구 관리" 페이지에서 생성하세요
          </p>
        </div>
      ) : (
        <div className="space-y-1.5 max-h-60 overflow-y-auto pr-1">
          {visible.map(def => {
            const meta = TOOL_TYPE_LABELS[def.type];
            return (
              <button
                key={def.id}
                onClick={() => onPick(def)}
                className="w-full text-left bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 hover:border-blue-500 hover:bg-gray-700 transition-colors group"
              >
                <div className="flex items-center gap-2.5">
                  <span className={`text-lg p-1 rounded ${def.color} bg-opacity-20`}>{def.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-gray-200 font-medium truncate">{def.name}</span>
                      <span className="text-xs bg-gray-700 text-gray-400 px-1.5 py-0.5 rounded shrink-0">
                        {meta.icon} {meta.label}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 truncate">{def.description}</p>
                  </div>
                  <span className="text-blue-400 opacity-0 group-hover:opacity-100 transition-opacity text-xs">
                    + 연결
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Public: ToolEditor (읽기 전용 도구 참조) ──────────────────────────────────

export function ToolEditor({
  linkedToolIds,
  onChange,
}: {
  linkedToolIds: string[];  // 연결된 도구 ID 목록
  onChange: (toolIds: string[]) => void;
}) {
  const [showPicker, setShowPicker] = useState(false);
  const [allTools, setAllTools] = useState<ToolDefinition[]>([]);
  const [loadingTools, setLoadingTools] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await toolApi.list();
        setAllTools(data);
      } catch {
        const { mockToolDefinitions } = await import('../../data/mockData');
        setAllTools(mockToolDefinitions);
      } finally {
        setLoadingTools(false);
      }
    };
    load();
  }, []);

  const getToolById = (id: string) => allTools.find(t => t.id === id);

  const linkTool = (def: ToolDefinition) => {
    onChange([...linkedToolIds, def.id]);
    setShowPicker(false);
  };

  const unlinkTool = (toolId: string) => {
    onChange(linkedToolIds.filter(id => id !== toolId));
  };

  if (loadingTools) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="text-gray-400 text-sm">도구 목록을 불러오는 중...</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 안내 배너 */}
      <div className="bg-gray-700 rounded-lg p-3 border-l-4 border-blue-500">
        <p className="text-gray-300 text-sm">
          <strong>도구 라이브러리</strong>에서 필요한 도구를 연결하세요.
          <br />
          <span className="text-gray-400 text-xs">
            도구 생성/수정은 "도구 관리" 메뉴에서 할 수 있습니다.
            노드에서는 도구의 규격을 그대로 사용합니다.
          </span>
        </p>
      </div>

      {/* 연결된 도구 목록 */}
      {linkedToolIds.length === 0 ? (
        <div className="text-center py-8 bg-gray-800/50 rounded-lg border border-dashed border-gray-700">
          <span className="text-3xl mb-2 block">🔧</span>
          <p className="text-gray-500 text-sm">연결된 도구가 없습니다</p>
          <p className="text-gray-600 text-xs mt-1">아래 버튼을 눌러 도구를 추가하세요</p>
        </div>
      ) : (
        <div className="space-y-2">
          {linkedToolIds.map(toolId => (
            <LinkedToolCard
              key={toolId}
              tool={getToolById(toolId)}
              toolId={toolId}
              onUnlink={() => unlinkTool(toolId)}
            />
          ))}
        </div>
      )}

      {/* 도구 추가 영역 */}
      {showPicker ? (
        <div className="border border-gray-600 rounded-lg overflow-hidden bg-gray-800">
          <div className="flex items-center justify-between px-3 py-2 border-b border-gray-700 bg-gray-700/50">
            <span className="text-sm text-gray-300 font-medium flex items-center gap-2">
              📚 라이브러리에서 도구 선택
            </span>
            <button
              onClick={() => setShowPicker(false)}
              className="text-gray-500 hover:text-gray-300 transition-colors"
            >
              ✕
            </button>
          </div>
          <div className="p-3">
            <LibraryPickerPanel
              onPick={linkTool}
              linkedToolIds={linkedToolIds}
              allTools={allTools}
            />
          </div>
        </div>
      ) : (
        <button
          onClick={() => setShowPicker(true)}
          className="w-full py-3 border-2 border-dashed border-gray-600 rounded-lg text-gray-400 hover:border-blue-500 hover:text-blue-400 transition-colors text-sm flex items-center justify-center gap-2"
        >
          <span>📚</span>
          <span>도구 라이브러리에서 추가</span>
        </button>
      )}

      {/* 통계 */}
      {linkedToolIds.length > 0 && (
        <div className="text-xs text-gray-600 text-right">
          연결된 도구: {linkedToolIds.length}개
        </div>
      )}
    </div>
  );
}
