import { useState, useEffect, useCallback } from 'react';
import { mockToolDefinitions } from '../data/mockData';
import { toolApi } from '../services/api';
import { useToast } from '../components/common/Toast';
import { useChatAssistant } from '../hooks/useChatAssistant';
import { useChatContext } from '../contexts/ChatContext';
import type {
  ToolDefinition,
  ToolType,
  ToolConfig,
  ApiCallConfig,
  FileReadConfig,
  FileWriteConfig,
  CodeExecuteConfig,
  DatabaseQueryConfig,
} from '../types';

// ============================================
// 상수 & 헬퍼
// ============================================

const TOOL_TYPE_META: Record<ToolType, { label: string; icon: string; color: string; bgClass: string }> = {
  api_call:       { label: 'API 호출기',  icon: '🌐', color: 'text-blue-400',   bgClass: 'bg-blue-900/30 border-blue-700' },
  file_read:      { label: '파일 읽기',   icon: '📄', color: 'text-yellow-400', bgClass: 'bg-yellow-900/30 border-yellow-700' },
  file_write:     { label: '파일 쓰기',   icon: '📝', color: 'text-pink-400',   bgClass: 'bg-pink-900/30 border-pink-700' },
  code_execute:   { label: '코드 실행',   icon: '💻', color: 'text-purple-400', bgClass: 'bg-purple-900/30 border-purple-700' },
  database_query: { label: 'DB 쿼리',    icon: '🗄️', color: 'text-teal-400',   bgClass: 'bg-teal-900/30 border-teal-700' },
};

const ALL_TYPES: ToolType[] = ['api_call', 'file_read', 'file_write', 'code_execute', 'database_query'];

const COLOR_OPTIONS = [
  'bg-blue-600', 'bg-green-600', 'bg-purple-600', 'bg-pink-600',
  'bg-yellow-600', 'bg-red-600', 'bg-indigo-600', 'bg-orange-600',
  'bg-teal-600', 'bg-cyan-600', 'bg-emerald-600', 'bg-gray-600',
];

const ICON_OPTIONS = ['🌐', '📄', '📝', '💻', '🗄️', '🎫', '💬', '📣', '🌤️', '📊', '⚙️', '🔧', '👤', '📈', '🐍', '🔄', '⚡', '🎯'];

/** 도구 타입에 맞는 빈 기본 config 생성 */
function createDefaultConfig(type: ToolType): ToolConfig {
  switch (type) {
    case 'api_call':
      return { method: 'GET', urlTemplate: '', headers: {}, bodyTemplate: '', responseMapping: '' };
    case 'file_read':
      return { pathTemplate: '', encoding: 'utf-8', parser: 'text' };
    case 'file_write':
      return { pathTemplate: '', contentTemplate: '' };
    case 'code_execute':
      return { language: 'javascript', code: '// input 변수로 데이터 접근\nreturn input;' };
    case 'database_query':
      return { connectionId: '', queryTemplate: '' };
  }
}

// ============================================
// Tool Card (그리드 카드)
// ============================================

function ToolCard({
  tool,
  onEdit,
  onDelete,
}: {
  tool: ToolDefinition;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const meta = TOOL_TYPE_META[tool.type];

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden hover:border-gray-500 transition-all duration-200 flex flex-col">
      {/* 상단 색상 바 + 타입 배지 */}
      <div className={`h-1.5 ${tool.color}`} />

      <div className="p-4 flex-1 flex flex-col">
        {/* 아이콘 + 타입 배지 행 */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2.5">
            <span className={`text-2xl p-1.5 rounded-lg ${tool.color} bg-opacity-20`}>{tool.icon}</span>
            <span className={`text-xs font-semibold px-2 py-0.5 rounded border ${meta.bgClass} ${meta.color}`}>
              {meta.icon} {meta.label}
            </span>
          </div>
        </div>

        {/* 이름 + 설명 */}
        <h3 className="font-bold text-white text-base leading-snug">{tool.name}</h3>
        <p className="text-gray-400 text-sm mt-0.5 leading-relaxed flex-1">{tool.description}</p>

        {/* 태그 행 */}
        {tool.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-3">
            {tool.tags.map(tag => (
              <span key={tag} className="px-2 py-0.5 text-xs rounded bg-gray-700 text-gray-400">
                #{tag}
              </span>
            ))}
          </div>
        )}

        {/* 타입별 핵심 정보 미니 프리뷰 */}
        <div className="mt-3 bg-gray-900 rounded p-2.5">
          <ToolPreview tool={tool} />
        </div>

        {/* 액션 버튼 */}
        <div className="flex gap-2 mt-4 pt-3 border-t border-gray-700">
          <button
            onClick={onEdit}
            className="flex-1 px-3 py-1.5 bg-gray-700 text-gray-200 rounded hover:bg-gray-600 text-sm transition-colors"
          >
            ✏️ 편집
          </button>
          <button
            onClick={onDelete}
            className="px-3 py-1.5 bg-gray-700 text-red-400 rounded hover:bg-red-900 text-sm transition-colors"
          >
            🗑️
          </button>
        </div>
      </div>
    </div>
  );
}

/** 카드 내 타입별 핵심 속성 미니 프리뷰 */
function ToolPreview({ tool }: { tool: ToolDefinition }) {
  switch (tool.type) {
    case 'api_call': {
      const cfg = tool.config as ApiCallConfig;
      return (
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-blue-400 bg-blue-900/40 px-1.5 py-0.5 rounded">
              {cfg.method}
            </span>
            <span className="text-xs text-gray-400 font-mono truncate">{cfg.urlTemplate}</span>
          </div>
          {cfg.auth && (
            <span className="text-xs text-gray-500">🔐 인증: {cfg.auth.type}</span>
          )}
        </div>
      );
    }
    case 'file_read': {
      const cfg = tool.config as FileReadConfig;
      return (
        <div className="space-y-0.5">
          <span className="text-xs text-gray-400 font-mono truncate block">{cfg.pathTemplate}</span>
          <span className="text-xs text-gray-500">파서: {cfg.parser} · 인코딩: {cfg.encoding || 'utf-8'}</span>
        </div>
      );
    }
    case 'file_write': {
      const cfg = tool.config as FileWriteConfig;
      return (
        <span className="text-xs text-gray-400 font-mono truncate block">{cfg.pathTemplate}</span>
      );
    }
    case 'code_execute': {
      const cfg = tool.config as CodeExecuteConfig;
      return (
        <div className="space-y-0.5">
          <span className="text-xs text-gray-500">
            언어: <span className="text-purple-300 font-semibold">{cfg.language}</span>
          </span>
          <div className="text-xs text-gray-500 font-mono truncate">
            {cfg.code.split('\n')[0]}
          </div>
        </div>
      );
    }
    case 'database_query': {
      const cfg = tool.config as DatabaseQueryConfig;
      return (
        <div className="space-y-0.5">
          {cfg.connectionId && <span className="text-xs text-gray-500">연결: {cfg.connectionId}</span>}
          <span className="text-xs text-gray-400 font-mono truncate block">{cfg.queryTemplate}</span>
        </div>
      );
    }
  }
}

// ============================================
// 모달 내 타입별 설정 폼
// ============================================

function ApiCallConfigForm({
  config,
  onChange,
}: {
  config: Extract<ToolConfig, { method: string }>;
  onChange: (c: ToolConfig) => void;
}) {
  const headers = config.headers ? Object.entries(config.headers) : [];

  const set = <K extends keyof typeof config>(key: K, val: (typeof config)[K]) =>
    onChange({ ...config, [key]: val });

  const updateHeader = (idx: number, key: string, val: string) => {
    const next = [...headers];
    next[idx] = [key, val];
    onChange({ ...config, headers: Object.fromEntries(next) });
  };

  return (
    <div className="space-y-4">
      {/* Method + URL */}
      <div className="flex gap-2">
        <select
          value={config.method}
          onChange={(e) => set('method', e.target.value as typeof config.method)}
          className="w-28 bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          {(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const).map(m => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
        <input
          type="text"
          value={config.urlTemplate}
          onChange={(e) => set('urlTemplate', e.target.value)}
          placeholder="https://api.example.com/{{input.path}}"
          className="flex-1 bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
        />
      </div>

      {/* Headers */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs text-gray-500">헤더</label>
          <button
            onClick={() => onChange({ ...config, headers: { ...config.headers, '': '' } })}
            className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
          >
            + 헤더 추가
          </button>
        </div>
        <div className="space-y-1.5">
          {headers.map((entry, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <input
                type="text"
                value={entry[0]}
                onChange={(e) => updateHeader(idx, e.target.value, entry[1])}
                placeholder="키"
                className="flex-1 bg-gray-900 border border-gray-600 rounded px-3 py-1.5 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
              />
              <span className="text-gray-600 text-xs">:</span>
              <input
                type="text"
                value={entry[1]}
                onChange={(e) => updateHeader(idx, entry[0], e.target.value)}
                placeholder="값"
                className="flex-1 bg-gray-900 border border-gray-600 rounded px-3 py-1.5 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
              />
              <button
                onClick={() => {
                  const next = headers.filter((_, i) => i !== idx);
                  onChange({ ...config, headers: Object.fromEntries(next) });
                }}
                className="text-gray-600 hover:text-red-400 transition-colors text-sm"
              >
                ✕
              </button>
            </div>
          ))}
          {headers.length === 0 && <p className="text-xs text-gray-600 italic">헤더 없음</p>}
        </div>
      </div>

      {/* Body */}
      <div>
        <label className="block text-xs text-gray-500 mb-1">
          요청 본문 (Body)
          <span className="text-gray-600 ml-1">– POST / PUT / PATCH 시 사용</span>
        </label>
        <textarea
          value={config.bodyTemplate || ''}
          onChange={(e) => set('bodyTemplate', e.target.value)}
          placeholder={'{"key": "{{input.value}}"}'}
          rows={3}
          className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono resize-none"
        />
      </div>

      {/* Response Mapping */}
      <div>
        <label className="block text-xs text-gray-500 mb-1">
          응답 매핑 <span className="text-gray-600">(예: data.items)</span>
        </label>
        <input
          type="text"
          value={config.responseMapping || ''}
          onChange={(e) => set('responseMapping', e.target.value)}
          placeholder="data.items"
          className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
        />
      </div>

      {/* Auth */}
      <div>
        <label className="block text-xs text-gray-500 mb-1">인증 (선택사항)</label>
        <div className="flex gap-2">
          <select
            value={config.auth?.type || ''}
            onChange={(e) => {
              if (e.target.value === '') {
                const { auth: _, ...rest } = config;
                onChange(rest as ToolConfig);
              } else {
                onChange({ ...config, auth: { type: e.target.value as 'bearer' | 'basic' | 'api_key', value: config.auth?.value || '' } });
              }
            }}
            className="w-36 bg-gray-900 border border-gray-600 rounded-lg px-3 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="">없음</option>
            <option value="bearer">Bearer Token</option>
            <option value="basic">Basic Auth</option>
            <option value="api_key">API Key</option>
          </select>
          {config.auth && (
            <input
              type="text"
              value={config.auth.value}
              onChange={(e) => onChange({ ...config, auth: { ...config.auth!, value: e.target.value } })}
              placeholder="{{env.TOKEN}}"
              className="flex-1 bg-gray-900 border border-gray-600 rounded-lg px-3 py-1.5 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
            />
          )}
        </div>
      </div>
    </div>
  );
}

function FileReadConfigForm({
  config,
  onChange,
}: {
  config: Extract<ToolConfig, { parser: string }>;
  onChange: (c: ToolConfig) => void;
}) {
  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs text-gray-500 mb-1">경로 템플릿</label>
        <input
          type="text"
          value={config.pathTemplate}
          onChange={(e) => onChange({ ...config, pathTemplate: e.target.value })}
          placeholder="/data/{{input.filename}}.csv"
          className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
        />
      </div>
      <div className="flex gap-4">
        <div>
          <label className="block text-xs text-gray-500 mb-1">파서</label>
          <select
            value={config.parser}
            onChange={(e) => onChange({ ...config, parser: e.target.value as 'text' | 'json' | 'csv' })}
            className="w-36 bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="text">Plain Text</option>
            <option value="json">JSON</option>
            <option value="csv">CSV</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">인코딩</label>
          <select
            value={config.encoding || 'utf-8'}
            onChange={(e) => onChange({ ...config, encoding: e.target.value })}
            className="w-36 bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="utf-8">UTF-8</option>
            <option value="utf-16">UTF-16</option>
            <option value="ascii">ASCII</option>
          </select>
        </div>
      </div>
    </div>
  );
}

function FileWriteConfigForm({
  config,
  onChange,
}: {
  config: Extract<ToolConfig, { contentTemplate: string }>;
  onChange: (c: ToolConfig) => void;
}) {
  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs text-gray-500 mb-1">경로 템플릿</label>
        <input
          type="text"
          value={config.pathTemplate}
          onChange={(e) => onChange({ ...config, pathTemplate: e.target.value })}
          placeholder="/output/{{input.filename}}.json"
          className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
        />
      </div>
      <div>
        <label className="block text-xs text-gray-500 mb-1">내용 템플릿</label>
        <textarea
          value={config.contentTemplate}
          onChange={(e) => onChange({ ...config, contentTemplate: e.target.value })}
          placeholder={'{"result": "{{input.data}}"}'}
          rows={4}
          className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono resize-none"
        />
      </div>
    </div>
  );
}

function CodeExecuteConfigForm({
  config,
  onChange,
}: {
  config: Extract<ToolConfig, { code: string }>;
  onChange: (c: ToolConfig) => void;
}) {
  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs text-gray-500 mb-1">언어</label>
        <select
          value={config.language}
          onChange={(e) => onChange({ ...config, language: e.target.value as 'javascript' | 'python' })}
          className="w-40 bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          <option value="javascript">JavaScript</option>
          <option value="python">Python</option>
        </select>
      </div>
      <div>
        <label className="block text-xs text-gray-500 mb-1">코드</label>
        <textarea
          value={config.code}
          onChange={(e) => onChange({ ...config, code: e.target.value })}
          placeholder={`// input 변수로 데이터 접근\nreturn { ...input, processed: true };`}
          rows={8}
          className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono resize-none"
        />
      </div>
    </div>
  );
}

function DatabaseQueryConfigForm({
  config,
  onChange,
}: {
  config: Extract<ToolConfig, { queryTemplate: string }>;
  onChange: (c: ToolConfig) => void;
}) {
  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs text-gray-500 mb-1">연결 ID (선택사항)</label>
        <input
          type="text"
          value={config.connectionId || ''}
          onChange={(e) => onChange({ ...config, connectionId: e.target.value })}
          placeholder="pg-main"
          className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
        />
      </div>
      <div>
        <label className="block text-xs text-gray-500 mb-1">쿼리 템플릿</label>
        <textarea
          value={config.queryTemplate}
          onChange={(e) => onChange({ ...config, queryTemplate: e.target.value })}
          placeholder={"SELECT * FROM users WHERE id = '{{input.userId}}'"}
          rows={5}
          className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono resize-none"
        />
      </div>
    </div>
  );
}

/** 타입에 맞는 폼 컴포넌트를 라우팅 */
function ConfigForm({ type, config, onChange }: { type: ToolType; config: ToolConfig; onChange: (c: ToolConfig) => void }) {
  switch (type) {
    case 'api_call':
      return <ApiCallConfigForm config={config as any} onChange={onChange} />;
    case 'file_read':
      return <FileReadConfigForm config={config as any} onChange={onChange} />;
    case 'file_write':
      return <FileWriteConfigForm config={config as any} onChange={onChange} />;
    case 'code_execute':
      return <CodeExecuteConfigForm config={config as any} onChange={onChange} />;
    case 'database_query':
      return <DatabaseQueryConfigForm config={config as any} onChange={onChange} />;
  }
}

// ============================================
// Tool Editor Modal
// ============================================

function ToolEditorModal({
  tool,
  onSave,
  onClose,
}: {
  tool: ToolDefinition | null;   // null = 새 생성
  onSave: (tool: ToolDefinition) => Promise<void>;
  onClose: () => void;
}) {
  const isNew = tool === null;

  // ── 1단계: 타입 선택 (새 생성 시에만) ──────────────────────────────────
  const [selectedType, setSelectedType] = useState<ToolType | null>(tool?.type || null);

  // ── 기본 필드 ──────────────────────────────────────────────────────────
  const [name, setName]               = useState(tool?.name || '');
  const [description, setDescription] = useState(tool?.description || '');
  const [icon, setIcon]               = useState(tool?.icon || '🔧');
  const [color, setColor]             = useState(tool?.color || 'bg-blue-600');
  const [tags, setTags]               = useState(tool?.tags.join(', ') || '');
  const [config, setConfig]           = useState<ToolConfig | null>(tool?.config || null);
  const [saving, setSaving]           = useState(false);

  // 타입 선택 시 기본 config 초기화
  const handleTypeSelect = (type: ToolType) => {
    setSelectedType(type);
    setIcon(TOOL_TYPE_META[type].icon);
    setConfig(createDefaultConfig(type));
  };

  // ── Save ──────────────────────────────────────────────────────────────
  const handleSave = async () => {
    if (!selectedType || !config) return;
    const saved: ToolDefinition = {
      id: tool?.id || `tool-def-${Date.now()}`,
      name,
      description,
      type: selectedType,
      icon,
      color,
      tags: tags.split(',').map(t => t.trim()).filter(Boolean),
      config,
      createdAt: tool?.createdAt || new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    setSaving(true);
    try {
      await onSave(saved);
    } finally {
      setSaving(false);
    }
  };

  const canSave = selectedType && name.trim().length > 0 && config;

  // ── 타입 아직 선택되지 않음 → 타입 피커 화면 ──────────────────────────
  if (!selectedType || !config) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-2 sm:p-4">
        <div className="bg-gray-800 rounded-xl w-full max-w-[95vw] sm:max-w-2xl max-h-[90vh] overflow-y-auto">
          {/* Header */}
          <div className="p-5 border-b border-gray-700 flex items-center justify-between">
            <h2 className="text-lg font-bold text-white">새 도구 만들기 – 타입 선택</h2>
            <button onClick={onClose} className="text-gray-400 hover:text-white text-2xl leading-none">×</button>
          </div>

          {/* 타입 그리드 */}
          <div className="p-6">
            <p className="text-gray-400 text-sm mb-4">만들고 싶은 도구 타입을 선택하세요</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {ALL_TYPES.map(type => {
                const m = TOOL_TYPE_META[type];
                return (
                  <button
                    key={type}
                    onClick={() => handleTypeSelect(type)}
                    className="bg-gray-900 border border-gray-600 rounded-lg p-4 text-left hover:border-blue-500 hover:bg-gray-700 transition-colors"
                  >
                    <div className="flex items-center gap-3 mb-1.5">
                      <span className="text-2xl">{m.icon}</span>
                      <span className="text-white font-semibold">{m.label}</span>
                    </div>
                    <p className="text-gray-500 text-xs pl-9">
                      {type === 'api_call'       && 'REST API 호출 → 결과를 노드에서 사용'}
                      {type === 'file_read'      && '파일 → 노드에서 사용 가능한 데이터로 변환'}
                      {type === 'file_write'     && '데이터 → 파일로 저장'}
                      {type === 'code_execute'   && 'JS / Python 코드 실행'}
                      {type === 'database_query' && '데이터베이스 쿼리 실행'}
                    </p>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── 타입 선택된 후 → 기본 폼 화면 ──────────────────────────────────────
  const meta = TOOL_TYPE_META[selectedType];

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-2 sm:p-4">
      <div className="bg-gray-800 rounded-xl w-full max-w-[95vw] sm:max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-5 border-b border-gray-700 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-xl">{meta.icon}</span>
            <div>
              <h2 className="text-lg font-bold text-white">
                {isNew ? `새 ${meta.label} 만들기` : `도구 편집: ${tool!.name}`}
              </h2>
              <span className={`text-xs ${meta.color}`}>{meta.label}</span>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-2xl leading-none">×</button>
        </div>

        {/* Body – 스크롤 가능 */}
        <div className="flex-1 overflow-auto p-6 space-y-5">
          {/* ── 기본 정보 행 ──────────────────────────────────────────── */}
          <div>
            <div className="flex justify-between items-center mb-1.5">
              <label className="block text-sm text-gray-400">도구 이름 *</label>
              <span className={`text-xs ${name.length > 90 ? 'text-red-400' : name.length > 75 ? 'text-yellow-400' : 'text-gray-500'}`}>
                {name.length}/100
              </span>
            </div>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={100}
              placeholder="예: 서비스데스크 문의글 조회"
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-4 py-2.5 text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <div className="flex justify-between items-center mb-1.5">
              <label className="block text-sm text-gray-400">설명</label>
              <span className={`text-xs ${description.length > 450 ? 'text-red-400' : description.length > 375 ? 'text-yellow-400' : 'text-gray-500'}`}>
                {description.length}/500
              </span>
            </div>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={500}
              placeholder="이 도구가 하는 일을 간결하게 설명하세요"
              rows={2}
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-4 py-2.5 text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            />
          </div>

          {/* ── 아이콘 + 색상 ────────────────────────────────────────── */}
          <div className="grid grid-cols-2 gap-6">
            <div>
              <label className="block text-sm text-gray-400 mb-1.5">아이콘</label>
              <div className="flex flex-wrap gap-1.5">
                {ICON_OPTIONS.map(i => (
                  <button
                    key={i}
                    onClick={() => setIcon(i)}
                    className={`w-9 h-9 text-lg rounded-lg flex items-center justify-center transition-all ${
                      icon === i ? 'bg-blue-600 ring-2 ring-blue-400' : 'bg-gray-700 hover:bg-gray-600'
                    }`}
                  >
                    {i}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1.5">색상</label>
              <div className="flex flex-wrap gap-1.5">
                {COLOR_OPTIONS.map(c => (
                  <button
                    key={c}
                    onClick={() => setColor(c)}
                    className={`w-9 h-9 rounded-lg ${c} transition-all ${
                      color === c ? 'ring-2 ring-white ring-offset-2 ring-offset-gray-800' : ''
                    }`}
                  />
                ))}
              </div>
            </div>
          </div>

          {/* ── 태그 ──────────────────────────────────────────────────── */}
          <div>
            <label className="block text-sm text-gray-400 mb-1.5">태그 (쉼표로 구분)</label>
            <input
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="예: api, service-desk, notification"
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-4 py-2.5 text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* ── 타입별 설정 폼 ────────────────────────────────────────── */}
          <div>
            <div className="flex items-center gap-2 mb-3">
              <span className="text-lg">{meta.icon}</span>
              <label className="text-sm font-semibold text-gray-300">{meta.label} 설정</label>
            </div>
            <div className="bg-gray-900 rounded-lg border border-gray-700 p-4">
              <ConfigForm type={selectedType} config={config} onChange={setConfig} />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-700 flex items-center justify-between">
          <span className="text-xs text-gray-600">
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border ${meta.bgClass} ${meta.color}`}>
              {meta.icon} {meta.label}
            </span>
          </span>
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="px-5 py-2 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 transition-colors"
            >
              취소
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !canSave}
              className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {saving ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  {isNew ? '생성 중...' : '저장 중...'}
                </>
              ) : (isNew ? '생성' : '저장')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================
// Main Page
// ============================================

export function ToolManagementPage() {
  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [isOnline, setIsOnline] = useState(true);
  const { toast } = useToast();
  const { setToolContext, clearContext } = useChatAssistant();
  const { onDataChange } = useChatContext();
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedType, setSelectedType] = useState<ToolType | null>(null);
  const [selectedTag, setSelectedTag]   = useState<string | null>(null);
  const [editingTool, setEditingTool]   = useState<ToolDefinition | null | 'new'>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    document.title = '도구 관리 | AI 업무도우미';
  }, []);

  // Load data - try API first, fallback to mock
  const loadTools = useCallback(async () => {
    setLoading(true);
    try {
      const data = await toolApi.list();
      setTools(data);
      setIsOnline(true);
    } catch {
      setTools(mockToolDefinitions);
      setIsOnline(false);
      toast.info('오프라인 모드로 실행 중입니다');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadTools();
  }, [loadTools]);

  useEffect(() => {
    return onDataChange((target) => {
      if (target.includes('tool')) loadTools();
    });
  }, [onDataChange, loadTools]);

  // ── Keyboard shortcuts ────────────────────────────────────────
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger if user is typing in an input/textarea
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable) {
        // Only handle Escape in input fields
        if (e.key === 'Escape') {
          target.blur();
        }
        return;
      }

      // Escape: close any open modal
      if (e.key === 'Escape') {
        if (editingTool) {
          setEditingTool(null);
        } else if (confirmDelete) {
          setConfirmDelete(null);
        }
      }

      // Ctrl+N or Cmd+N: open create modal
      if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        if (!editingTool) {
          setEditingTool('new');
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [editingTool, confirmDelete]);

  // ── Set chat context when tool is being edited ──────────────────

  useEffect(() => {
    if (editingTool && editingTool !== 'new') {
      setToolContext(editingTool);
    } else {
      clearContext();
    }
  }, [editingTool, setToolContext, clearContext]);

  // 모든 태그 수집 (중복 제거, 정렬)
  const allTags = Array.from(new Set(tools.flatMap(t => t.tags))).sort();

  // 필터링
  const filteredTools = tools.filter(tool => {
    const matchesSearch = !searchQuery ||
      tool.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      tool.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      tool.tags.some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase()));
    const matchesType = !selectedType || tool.type === selectedType;
    const matchesTag  = !selectedTag  || tool.tags.includes(selectedTag);
    return matchesSearch && matchesType && matchesTag;
  });

  // ── CRUD ────────────────────────────────────────────────────────────────
  const handleSave = async (tool: ToolDefinition) => {
    try {
      if (isOnline) {
        const exists = tools.find(t => t.id === tool.id);
        if (exists) {
          const updated = await toolApi.update(tool.id, {
            name: tool.name,
            description: tool.description,
            icon: tool.icon,
            color: tool.color,
            config: tool.config,
            tags: tool.tags,
          });
          setTools(prev => prev.map(t => t.id === updated.id ? updated : t));
        } else {
          const created = await toolApi.create({
            name: tool.name,
            description: tool.description,
            type: tool.type,
            icon: tool.icon,
            color: tool.color,
            config: tool.config,
            tags: tool.tags,
          });
          setTools(prev => [...prev, created]);
        }
        toast.success(exists ? '도구가 수정되었습니다' : '도구가 생성되었습니다');
      } else {
        // Offline mode - local state only
        setTools(prev => {
          const exists = prev.find(t => t.id === tool.id);
          return exists
            ? prev.map(t => t.id === tool.id ? tool : t)
            : [...prev, tool];
        });
        toast.info('오프라인 모드: 로컬에만 저장되었습니다');
      }
    } catch (err) {
      const detail = err instanceof Error ? err.message : '';
      toast.error(`저장에 실패했습니다${detail ? `: ${detail}` : ''}`);
    }
    setEditingTool(null);
  };

  const handleDelete = (id: string) => {
    setConfirmDelete(id);
  };

  const confirmDeleteAction = async () => {
    if (!confirmDelete) return;
    setDeleting(true);
    try {
      if (isOnline) {
        await toolApi.delete(confirmDelete);
        toast.success('도구가 삭제되었습니다');
      }
      setTools(prev => prev.filter(t => t.id !== confirmDelete));
    } catch (err) {
      const detail = err instanceof Error ? err.message : '';
      toast.error(`삭제에 실패했습니다${detail ? `: ${detail}` : ''}`);
    } finally {
      setDeleting(false);
      setConfirmDelete(null);
    }
  };

  // ── 타입별 개수 통계 ────────────────────────────────────────────────────
  const typeCounts = ALL_TYPES.reduce<Record<string, number>>((acc, t) => {
    acc[t] = tools.filter(tool => tool.type === t).length;
    return acc;
  }, {});

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-gray-400 text-sm">도구 목록 불러오는 중...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <header className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-white">도구 관리</h1>
            <p className="text-gray-400 text-sm">
              재사용 가능한 도구를 중앙 라이브러리에서 생성하고 관리합니다
            </p>
          </div>
          <button
            onClick={() => setEditingTool('new')}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
          >
            <span>+</span>
            <span>새 도구</span>
          </button>
        </div>

        {/* ── 검색 + 타입 필터 ────────────────────────────────────────── */}
        <div className="flex flex-wrap items-center gap-3">
          {/* 검색 인풋 */}
          <div className="relative flex-1" style={{ minWidth: 200, maxWidth: 360 }}>
            <input
              type="text"
              placeholder="도구 검색..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 pl-10 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">🔍</span>
          </div>

          {/* 타입 필터 Pills */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-gray-500 text-sm">타입:</span>
            <button
              onClick={() => setSelectedType(null)}
              className={`px-3 py-1 rounded-full text-sm transition-colors ${
                !selectedType ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              전체
            </button>
            {ALL_TYPES.map(type => {
              const m = TOOL_TYPE_META[type];
              return (
                <button
                  key={type}
                  onClick={() => setSelectedType(selectedType === type ? null : type)}
                  className={`px-3 py-1 rounded-full text-sm transition-colors flex items-center gap-1 ${
                    selectedType === type ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  {m.icon} {m.label}
                  <span className="text-xs opacity-60">({typeCounts[type]})</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* ── 태그 필터 ───────────────────────────────────────────────── */}
        {allTags.length > 0 && (
          <div className="flex items-center gap-2 mt-3 flex-wrap">
            <span className="text-gray-500 text-sm">태그:</span>
            <button
              onClick={() => setSelectedTag(null)}
              className={`px-2.5 py-0.5 rounded-full text-xs transition-colors ${
                !selectedTag ? 'bg-gray-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
              }`}
            >
              전체
            </button>
            {allTags.map(tag => (
              <button
                key={tag}
                onClick={() => setSelectedTag(selectedTag === tag ? null : tag)}
                className={`px-2.5 py-0.5 rounded-full text-xs transition-colors ${
                  selectedTag === tag ? 'bg-gray-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                }`}
              >
                #{tag}
              </button>
            ))}
          </div>
        )}
      </header>

      {/* ── Stats Bar ──────────────────────────────────────────────────── */}
      <div className="px-4 py-2.5 border-b border-gray-700 bg-gray-800/50 flex items-center gap-6 text-sm flex-wrap">
        <span className="text-gray-400">
          전체 도구: <span className="text-white font-medium">{tools.length}</span>
        </span>
        {ALL_TYPES.map(type => {
          const m = TOOL_TYPE_META[type];
          return (
            <span key={type} className="text-gray-400 flex items-center gap-1">
              {m.icon} {m.label}:
              <span className={`font-medium ${m.color}`}>{typeCounts[type]}</span>
            </span>
          );
        })}
        <span className="text-gray-500 ml-auto text-xs">
          표시: {filteredTools.length}개
        </span>
      </div>

      {/* ── Tool Grid ──────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-auto p-4">
        {filteredTools.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-16 h-16 rounded-full bg-gray-800 flex items-center justify-center mb-4">
              <span className="text-3xl">🔧</span>
            </div>
            <h3 className="text-lg font-medium text-gray-300 mb-2">
              {tools.length === 0 ? '등록된 도구가 없습니다' : '조건에 맞는 도구가 없습니다'}
            </h3>
            <p className="text-gray-500 text-sm mb-4 max-w-md">
              {tools.length === 0
                ? 'AI 노드에서 사용할 도구를 정의하세요. API 호출, 데이터베이스 쿼리, 코드 실행 등을 자동화할 수 있습니다'
                : '검색 조건을 수정하거나 새 도구를 생성하세요'}
            </p>
            {tools.length === 0 ? (
              <button
                onClick={() => setEditingTool('new')}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                + 새 도구 정의
              </button>
            ) : (
              <div className="flex gap-2">
                <button
                  onClick={() => { setSearchQuery(''); setSelectedType(null); setSelectedTag(null); }}
                  className="px-4 py-2 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600 text-sm transition-colors"
                >
                  필터 초기화
                </button>
                <button
                  onClick={() => setEditingTool('new')}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm transition-colors"
                >
                  새 도구 만들기
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filteredTools.map(tool => (
              <ToolCard
                key={tool.id}
                tool={tool}
                onEdit={() => setEditingTool(tool)}
                onDelete={() => handleDelete(tool.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Editor Modal ───────────────────────────────────────────────── */}
      {editingTool && (
        <ToolEditorModal
          tool={editingTool === 'new' ? null : editingTool}
          onSave={handleSave}
          onClose={() => setEditingTool(null)}
        />
      )}

      {/* ── Confirm Delete Dialog ──────────────────────────────────────── */}
      {confirmDelete && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60] p-2 sm:p-4">
          <div className="bg-gray-800 rounded-xl p-6 max-w-sm w-full">
            <h3 className="text-lg font-bold text-white mb-2">삭제 확인</h3>
            <p className="text-gray-400 text-sm mb-6">
              정말 삭제하시겠습니까? 다른 노드에서 참조 중이면 연결이 끊어질 수 있습니다.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setConfirmDelete(null)}
                disabled={deleting}
                className="px-4 py-2 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                취소
              </button>
              <button
                onClick={confirmDeleteAction}
                disabled={deleting}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {deleting ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    삭제 중...
                  </>
                ) : '삭제'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
