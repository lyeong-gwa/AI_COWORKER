import { useState, useEffect, useCallback } from 'react';
import { apiDefinitionApi } from '../services/api';
import type { ApiDefinition, CreateApiDefinitionData, UpdateApiDefinitionData } from '../types';
// import { useChatContext } from '../contexts/ChatContext';

const HTTP_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const;

const METHOD_COLORS: Record<string, string> = {
  GET: 'bg-green-600 text-green-100',
  POST: 'bg-blue-600 text-blue-100',
  PUT: 'bg-amber-600 text-amber-100',
  PATCH: 'bg-orange-600 text-orange-100',
  DELETE: 'bg-red-600 text-red-100',
};

// Mock data for offline mode
const mockApiDefs: ApiDefinition[] = [];

export default function ApiDefinitionPage() {
  const [apiDefs, setApiDefs] = useState<ApiDefinition[]>([]);
  const [isOnline, setIsOnline] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [showEditor, setShowEditor] = useState(false);
  const [showTestCapture, setShowTestCapture] = useState(false);
  const [editingDef, setEditingDef] = useState<ApiDefinition | null>(null);
  const [showCreateMenu, setShowCreateMenu] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null);

  // Load data
  const loadData = useCallback(async () => {
    try {
      const data = await apiDefinitionApi.list();
      setApiDefs(data);
      setIsOnline(true);
    } catch {
      setApiDefs(mockApiDefs);
      setIsOnline(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  // Extract unique categories
  const categories = [...new Set(apiDefs.map(d => d.category).filter(Boolean))];

  // Filter
  const filtered = apiDefs.filter(d => {
    const matchesSearch = !searchQuery ||
      d.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      d.urlTemplate.toLowerCase().includes(searchQuery.toLowerCase()) ||
      d.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = !selectedCategory || d.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  // CRUD handlers
  const handleCreate = async (data: CreateApiDefinitionData) => {
    try {
      const created = await apiDefinitionApi.create(data);
      setApiDefs(prev => [created, ...prev]);
      setShowEditor(false);
      setShowTestCapture(false);
    } catch (err) {
      console.error('API 정의 생성 실패:', err);
    }
  };

  const handleUpdate = async (id: string, data: UpdateApiDefinitionData) => {
    try {
      const updated = await apiDefinitionApi.update(id, data);
      setApiDefs(prev => prev.map(d => d.id === id ? updated : d));
      setShowEditor(false);
      setEditingDef(null);
    } catch (err) {
      console.error('API 정의 수정 실패:', err);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await apiDefinitionApi.delete(id);
      setApiDefs(prev => prev.filter(d => d.id !== id));
      setShowDeleteConfirm(null);
    } catch (err) {
      console.error('API 정의 삭제 실패:', err);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🌐</span>
            <div>
              <h1 className="text-xl font-bold text-white">API 정의</h1>
              <p className="text-xs text-gray-400">구조화된 API 규격 관리</p>
            </div>
            {!isOnline && (
              <span className="px-2 py-0.5 bg-yellow-600/30 text-yellow-300 text-[10px] rounded-full">오프라인</span>
            )}
          </div>
          <div className="relative">
            <button
              onClick={() => setShowCreateMenu(!showCreateMenu)}
              className="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-700 text-sm font-medium flex items-center gap-2"
            >
              + 새 API 정의
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {showCreateMenu && (
              <div className="absolute right-0 mt-1 w-52 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-20 overflow-hidden">
                <button
                  onClick={() => { setShowCreateMenu(false); setEditingDef(null); setShowEditor(true); }}
                  className="w-full px-4 py-2.5 text-left text-sm text-gray-200 hover:bg-gray-700 flex items-center gap-2"
                >
                  <span>📝</span> 직접 추가
                </button>
                <button
                  onClick={() => { setShowCreateMenu(false); setShowTestCapture(true); }}
                  className="w-full px-4 py-2.5 text-left text-sm text-gray-200 hover:bg-gray-700 flex items-center gap-2"
                >
                  <span>🧪</span> API 테스트로 추가
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Search + Filter */}
        <div className="flex gap-2">
          <input
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="검색 (이름, URL, 설명)..."
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
          />
          <select
            value={selectedCategory}
            onChange={e => setSelectedCategory(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200"
          >
            <option value="">전체 카테고리</option>
            {categories.map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Stats */}
      <div className="px-4 py-2 bg-gray-800/50 border-b border-gray-700/50 text-xs text-gray-400">
        총 {filtered.length}개 API 정의
        {selectedCategory && ` (${selectedCategory})`}
      </div>

      {/* Card Grid */}
      <div className="flex-1 overflow-auto p-4">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-gray-500">
            <span className="text-4xl mb-3 opacity-30">🌐</span>
            <p className="text-sm">API 정의가 없습니다</p>
            <p className="text-xs mt-1">새 API 정의를 추가하세요</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filtered.map(apiDef => (
              <ApiDefinitionCard
                key={apiDef.id}
                apiDef={apiDef}
                onClick={() => { setEditingDef(apiDef); setShowEditor(true); }}
                onDelete={() => setShowDeleteConfirm(apiDef.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Editor Modal */}
      {showEditor && (
        <ApiDefinitionEditorModal
          apiDef={editingDef}
          onSave={editingDef
            ? (data) => handleUpdate(editingDef.id, data)
            : handleCreate
          }
          onClose={() => { setShowEditor(false); setEditingDef(null); }}
        />
      )}

      {/* Test & Capture Modal */}
      {showTestCapture && (
        <ApiTestCaptureModal
          onSave={handleCreate}
          onClose={() => setShowTestCapture(false)}
        />
      )}

      {/* Delete Confirm */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-xl p-6 max-w-sm w-full mx-4">
            <h3 className="text-lg font-bold text-white mb-2">API 정의 삭제</h3>
            <p className="text-sm text-gray-300 mb-4">이 API 정의를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.</p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setShowDeleteConfirm(null)} className="px-4 py-2 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 text-sm">취소</button>
              <button onClick={() => handleDelete(showDeleteConfirm)} className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm">삭제</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// ── ApiDefinitionCard Component ──────────────────────────────────────────────

function ApiDefinitionCard({ apiDef, onClick, onDelete }: {
  apiDef: ApiDefinition;
  onClick: () => void;
  onDelete: () => void;
}) {
  const methodColor = METHOD_COLORS[apiDef.method] || 'bg-gray-600 text-gray-100';
  const paramCount = apiDef.parameters?.length || 0;

  return (
    <div
      onClick={onClick}
      className="bg-gray-800 border border-gray-700 rounded-xl p-4 cursor-pointer hover:border-cyan-500/50 hover:bg-gray-750 transition-all group"
    >
      {/* Top: icon + name + method badge */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="text-xl flex-shrink-0">{apiDef.icon || '🌐'}</span>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-white truncate">{apiDef.name}</h3>
            {apiDef.category && (
              <span className="text-[10px] text-gray-500">{apiDef.category}</span>
            )}
          </div>
        </div>
        <span className={`px-2 py-0.5 text-[10px] rounded font-bold flex-shrink-0 ${methodColor}`}>
          {apiDef.method}
        </span>
      </div>

      {/* URL template */}
      <div className="mb-3 bg-gray-900 rounded-lg px-3 py-2">
        <p className="text-xs text-gray-300 font-mono truncate">{apiDef.urlTemplate}</p>
      </div>

      {/* Description (truncated) */}
      {apiDef.description && (
        <p className="text-xs text-gray-400 mb-3 line-clamp-2">{apiDef.description}</p>
      )}

      {/* Bottom: params count + tags + delete */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 flex-wrap">
          {paramCount > 0 && (
            <span className="px-1.5 py-0.5 bg-gray-700 rounded text-[10px] text-gray-400">
              {paramCount}개 파라미터
            </span>
          )}
          {(apiDef.tags || []).slice(0, 2).map(tag => (
            <span key={tag} className="px-1.5 py-0.5 bg-gray-700 rounded text-[10px] text-cyan-400">
              {tag}
            </span>
          ))}
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="text-gray-500 hover:text-red-400 text-xs opacity-0 group-hover:opacity-100 transition-opacity"
        >
          삭제
        </button>
      </div>
    </div>
  );
}

// ── ApiDefinitionEditorModal Component ───────────────────────────────────────

function ApiDefinitionEditorModal({ apiDef, onSave, onClose }: {
  apiDef: ApiDefinition | null;
  onSave: (data: any) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState(apiDef?.name || '');
  const [description, setDescription] = useState(apiDef?.description || '');
  const [method, setMethod] = useState(apiDef?.method || 'GET');
  const [urlTemplate, setUrlTemplate] = useState(apiDef?.urlTemplate || '');
  const [category, setCategory] = useState(apiDef?.category || '');
  const [tags, setTags] = useState((apiDef?.tags || []).join(', '));
  const [icon, setIcon] = useState(apiDef?.icon || '🌐');
  const [authType, setAuthType] = useState(apiDef?.authType || 'none');
  const [headers, setHeaders] = useState<{key: string; value: string}[]>(
    Object.entries(apiDef?.headers || {}).map(([key, value]) => ({ key, value }))
  );
  const [bodyTemplate, setBodyTemplate] = useState(apiDef?.bodyTemplate || '');
  const [parameters, setParameters] = useState<any[]>(apiDef?.parameters || []);
  const [responseFields, setResponseFields] = useState<any[]>(apiDef?.responseSchema?.fields || []);
  const [activeTab, setActiveTab] = useState(0);

  const tabs = ['기본 정보', '요청 설정', '응답 정의'];

  const handleSave = () => {
    if (!name.trim() || !urlTemplate.trim()) return;
    const headersObj: Record<string, string> = {};
    headers.forEach(h => { if (h.key.trim()) headersObj[h.key.trim()] = h.value; });

    onSave({
      name: name.trim(),
      description,
      icon,
      color: apiDef?.color || 'text-cyan-400',
      category,
      tags: tags.split(',').map(t => t.trim()).filter(Boolean),
      method,
      urlTemplate,
      headers: headersObj,
      bodyTemplate: bodyTemplate || null,
      authType,
      authConfig: apiDef?.authConfig || {},
      parameters,
      responseSchema: { fields: responseFields, example: apiDef?.responseSchema?.example },
    });
  };

  const addHeader = () => setHeaders(prev => [...prev, { key: '', value: '' }]);
  const addParam = () => setParameters(prev => [...prev, { name: '', in: 'query', type: 'string', required: false, description: '', default: null }]);
  const addResponseField = () => setResponseFields(prev => [...prev, { field: '', type: 'string', description: '' }]);

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-2">
      <div className="bg-gray-800 rounded-xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-gray-700 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">{icon}</span>
            <h2 className="text-lg font-bold text-white">
              {apiDef ? 'API 정의 수정' : '새 API 정의'}
            </h2>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-2xl">&times;</button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-700">
          {tabs.map((tab, i) => (
            <button
              key={tab}
              onClick={() => setActiveTab(i)}
              className={`px-4 py-2.5 text-sm font-medium transition-colors ${
                activeTab === i
                  ? 'text-cyan-400 border-b-2 border-cyan-400'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {activeTab === 0 && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">이름 <span className="text-red-400">*</span></label>
                  <input value={name} onChange={e => setName(e.target.value)} className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-cyan-500" />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">카테고리</label>
                  <input value={category} onChange={e => setCategory(e.target.value)} placeholder="예: GitHub, 내부시스템" className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-cyan-500" />
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">설명</label>
                <textarea value={description} onChange={e => setDescription(e.target.value)} rows={3} className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 resize-y focus:outline-none focus:ring-1 focus:ring-cyan-500" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">아이콘</label>
                  <input value={icon} onChange={e => setIcon(e.target.value)} className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-cyan-500" />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">태그 (쉼표 구분)</label>
                  <input value={tags} onChange={e => setTags(e.target.value)} placeholder="GitHub, API" className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-cyan-500" />
                </div>
              </div>
            </div>
          )}

          {activeTab === 1 && (
            <div className="space-y-4">
              {/* Method + URL */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">요청 <span className="text-red-400">*</span></label>
                <div className="flex gap-2">
                  <select value={method} onChange={e => setMethod(e.target.value)} className={`px-3 py-2 rounded-lg text-sm font-bold ${METHOD_COLORS[method] || 'bg-gray-600'} border-none focus:outline-none cursor-pointer`}>
                    {HTTP_METHODS.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                  <input value={urlTemplate} onChange={e => setUrlTemplate(e.target.value)} placeholder="https://api.example.com/v1/{{resource}}" className="flex-1 bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 font-mono focus:outline-none focus:ring-1 focus:ring-cyan-500" />
                </div>
              </div>

              {/* Auth */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">인증</label>
                <select value={authType} onChange={e => setAuthType(e.target.value as 'none' | 'bearer' | 'basic' | 'api_key')} className="bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200">
                  <option value="none">없음</option>
                  <option value="bearer">Bearer Token</option>
                  <option value="basic">Basic Auth</option>
                  <option value="api_key">API Key</option>
                </select>
              </div>

              {/* Headers */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs text-gray-400">헤더</label>
                  <button onClick={addHeader} className="text-xs text-cyan-400 hover:text-cyan-300">+ 추가</button>
                </div>
                <div className="space-y-1.5">
                  {headers.map((h, i) => (
                    <div key={i} className="flex gap-2">
                      <input value={h.key} onChange={e => setHeaders(prev => prev.map((item, idx) => idx === i ? { ...item, key: e.target.value } : item))} placeholder="Header-Name" className="w-1/3 bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 font-mono focus:outline-none focus:ring-1 focus:ring-cyan-500" />
                      <input value={h.value} onChange={e => setHeaders(prev => prev.map((item, idx) => idx === i ? { ...item, value: e.target.value } : item))} placeholder="value or {{variable}}" className="flex-1 bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 font-mono focus:outline-none focus:ring-1 focus:ring-cyan-500" />
                      <button onClick={() => setHeaders(prev => prev.filter((_, idx) => idx !== i))} className="text-gray-500 hover:text-red-400 text-xs px-1">&times;</button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Body Template */}
              {['POST', 'PUT', 'PATCH'].includes(method) && (
                <div>
                  <label className="block text-xs text-gray-400 mb-1">바디 템플릿</label>
                  <textarea value={bodyTemplate} onChange={e => setBodyTemplate(e.target.value)} rows={5} placeholder={'{\n  "field": "{{variable}}"\n}'} className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-xs text-gray-200 font-mono resize-y focus:outline-none focus:ring-1 focus:ring-cyan-500" />
                </div>
              )}

              {/* Parameters Table */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs text-gray-400">파라미터</label>
                  <button onClick={addParam} className="text-xs text-cyan-400 hover:text-cyan-300">+ 추가</button>
                </div>
                {parameters.length > 0 && (
                  <div className="bg-gray-900 rounded-lg overflow-hidden">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-gray-700">
                          <th className="text-left px-2 py-1.5 text-gray-400 font-medium">이름</th>
                          <th className="text-left px-2 py-1.5 text-gray-400 font-medium w-20">위치</th>
                          <th className="text-left px-2 py-1.5 text-gray-400 font-medium w-20">타입</th>
                          <th className="text-center px-2 py-1.5 text-gray-400 font-medium w-10">필수</th>
                          <th className="text-left px-2 py-1.5 text-gray-400 font-medium">설명</th>
                          <th className="w-8"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {parameters.map((p, i) => (
                          <tr key={i} className="border-b border-gray-800">
                            <td className="px-2 py-1">
                              <input value={p.name} onChange={e => setParameters(prev => prev.map((item, idx) => idx === i ? { ...item, name: e.target.value } : item))} className="bg-transparent border-b border-gray-700 w-full text-cyan-300 font-mono focus:outline-none focus:border-cyan-500 py-0.5" />
                            </td>
                            <td className="px-2 py-1">
                              <select value={p.in} onChange={e => setParameters(prev => prev.map((item, idx) => idx === i ? { ...item, in: e.target.value } : item))} className="bg-gray-800 border border-gray-700 rounded px-1 py-0.5 text-gray-300 w-full">
                                <option value="path">path</option>
                                <option value="query">query</option>
                                <option value="header">header</option>
                                <option value="body">body</option>
                              </select>
                            </td>
                            <td className="px-2 py-1">
                              <select value={p.type} onChange={e => setParameters(prev => prev.map((item, idx) => idx === i ? { ...item, type: e.target.value } : item))} className="bg-gray-800 border border-gray-700 rounded px-1 py-0.5 text-gray-300 w-full">
                                <option value="string">string</option>
                                <option value="number">number</option>
                                <option value="boolean">boolean</option>
                              </select>
                            </td>
                            <td className="px-2 py-1 text-center">
                              <input type="checkbox" checked={p.required} onChange={e => setParameters(prev => prev.map((item, idx) => idx === i ? { ...item, required: e.target.checked } : item))} className="accent-cyan-500" />
                            </td>
                            <td className="px-2 py-1">
                              <input value={p.description} onChange={e => setParameters(prev => prev.map((item, idx) => idx === i ? { ...item, description: e.target.value } : item))} placeholder="설명..." className="bg-transparent border-b border-gray-700 w-full text-gray-300 focus:outline-none focus:border-cyan-500 py-0.5" />
                            </td>
                            <td className="px-1">
                              <button onClick={() => setParameters(prev => prev.filter((_, idx) => idx !== i))} className="text-gray-500 hover:text-red-400">&times;</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 2 && (
            <div className="space-y-4">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs text-gray-400">응답 필드</label>
                  <button onClick={addResponseField} className="text-xs text-cyan-400 hover:text-cyan-300">+ 추가</button>
                </div>
                {responseFields.length > 0 ? (
                  <div className="bg-gray-900 rounded-lg overflow-hidden">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-gray-700">
                          <th className="text-left px-3 py-2 text-gray-400 font-medium">필드</th>
                          <th className="text-left px-3 py-2 text-gray-400 font-medium w-24">타입</th>
                          <th className="text-left px-3 py-2 text-gray-400 font-medium">설명</th>
                          <th className="w-8"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {responseFields.map((f, i) => (
                          <tr key={i} className="border-b border-gray-800">
                            <td className="px-3 py-1.5">
                              <input value={f.field} onChange={e => setResponseFields(prev => prev.map((item, idx) => idx === i ? { ...item, field: e.target.value } : item))} className="bg-transparent border-b border-gray-700 w-full text-green-300 font-mono focus:outline-none focus:border-cyan-500 py-0.5" />
                            </td>
                            <td className="px-3 py-1.5">
                              <select value={f.type} onChange={e => setResponseFields(prev => prev.map((item, idx) => idx === i ? { ...item, type: e.target.value } : item))} className="bg-gray-800 border border-gray-700 rounded px-1 py-0.5 text-gray-300 w-full">
                                <option value="string">string</option>
                                <option value="number">number</option>
                                <option value="boolean">boolean</option>
                                <option value="object">object</option>
                                <option value="array">array</option>
                                <option value="null">null</option>
                              </select>
                            </td>
                            <td className="px-3 py-1.5">
                              <input value={f.description} onChange={e => setResponseFields(prev => prev.map((item, idx) => idx === i ? { ...item, description: e.target.value } : item))} placeholder="설명..." className="bg-transparent border-b border-gray-700 w-full text-gray-300 focus:outline-none focus:border-cyan-500 py-0.5" />
                            </td>
                            <td className="px-1">
                              <button onClick={() => setResponseFields(prev => prev.filter((_, idx) => idx !== i))} className="text-gray-500 hover:text-red-400">&times;</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="bg-gray-900 rounded-lg p-6 text-center text-gray-500 text-sm">
                    응답 필드가 없습니다. "API 테스트로 추가" 기능으로 자동 추출하거나 직접 추가하세요.
                  </div>
                )}
              </div>

              {/* Response Example (read-only if exists) */}
              {apiDef?.responseSchema?.example && (
                <div>
                  <label className="block text-xs text-gray-400 mb-1">응답 예시</label>
                  <pre className="bg-gray-900 border border-gray-700 rounded-lg p-3 text-xs text-gray-300 font-mono overflow-auto max-h-60 whitespace-pre-wrap">
                    {JSON.stringify(apiDef.responseSchema.example, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-700 flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 text-sm">취소</button>
          <button
            onClick={handleSave}
            disabled={!name.trim() || !urlTemplate.trim()}
            className="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-700 text-sm disabled:opacity-50"
          >
            {apiDef ? '수정' : '생성'}
          </button>
        </div>
      </div>
    </div>
  );
}


// ── ApiTestCaptureModal Component ────────────────────────────────────────────

function ApiTestCaptureModal({ onSave, onClose }: {
  onSave: (data: CreateApiDefinitionData) => void;
  onClose: () => void;
}) {
  const [step, setStep] = useState<1 | 2>(1);
  const [method, setMethod] = useState('GET');
  const [url, setUrl] = useState('');
  const [headers, setHeaders] = useState<{key: string; value: string}[]>([
    { key: 'Accept', value: 'application/json' },
  ]);
  const [bodyTemplate, setBodyTemplate] = useState('');
  const [variableValues, setVariableValues] = useState<Record<string, string>>({});
  const [testing, setTesting] = useState(false);
  const [testResponse, setTestResponse] = useState<any>(null);

  // Step 2 state
  const [defName, setDefName] = useState('');
  const [defDescription, setDefDescription] = useState('');
  const [defCategory, setDefCategory] = useState('');
  const [defTags, setDefTags] = useState('');
  const [parameters, setParameters] = useState<any[]>([]);
  const [responseFields, setResponseFields] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);

  // Extract {{variable}} placeholders
  const detectedVars = (() => {
    const allTexts = [url, ...headers.map(h => `${h.key}: ${h.value}`), bodyTemplate];
    const vars = new Set<string>();
    for (const text of allTexts) {
      const matches = text.match(/\{\{([^}]+)\}\}/g) || [];
      for (const m of matches) vars.add(m.replace(/^\{\{|\}\}$/g, '').trim());
    }
    return [...vars];
  })();

  const handleTest = async () => {
    if (!url.trim()) return;
    setTesting(true);
    setTestResponse(null);

    const headersObj: Record<string, string> = {};
    headers.forEach(h => { if (h.key.trim()) headersObj[h.key.trim()] = h.value; });

    try {
      const result = await apiDefinitionApi.testApi({
        method, url, headers: headersObj,
        bodyTemplate: bodyTemplate || undefined,
        inputData: variableValues,
      });
      setTestResponse(result.success ? { success: true, data: result.output, time: result.executionTimeMs } : { success: false, error: result.error, time: result.executionTimeMs });
    } catch (err) {
      setTestResponse({ success: false, error: err instanceof Error ? err.message : '요청 실패' });
    } finally {
      setTesting(false);
    }
  };

  const handleProceedToStep2 = async () => {
    if (!testResponse?.success) return;

    // Auto-generate title from URL
    try {
      const urlObj = new URL(url.replace(/\{\{[^}]+\}\}/g, 'x'));
      const pathParts = urlObj.pathname.split('/').filter(Boolean);
      setDefName(pathParts.slice(-2).join(' ') + ' API');
    } catch { setDefName('새 API'); }

    // Auto-generate parameters from variables
    setParameters(detectedVars.map(name => ({
      name, in: 'path' as const, type: 'string', required: true, description: '', default: null,
    })));

    // Auto-capture response schema
    if (testResponse.data) {
      try {
        const captured = await apiDefinitionApi.capture(testResponse.data, url);
        setResponseFields(captured.responseSchema?.fields || []);
      } catch {
        // Manual fallback
        setResponseFields([]);
      }
    }

    setStep(2);
  };

  const handleSave = () => {
    if (!defName.trim()) return;
    setSaving(true);

    const headersObj: Record<string, string> = {};
    headers.forEach(h => { if (h.key.trim()) headersObj[h.key.trim()] = h.value; });

    onSave({
      name: defName.trim(),
      description: defDescription,
      category: defCategory,
      tags: defTags.split(',').map(t => t.trim()).filter(Boolean),
      method,
      urlTemplate: url,
      headers: headersObj,
      bodyTemplate: bodyTemplate || undefined,
      authType: 'none',
      parameters,
      responseSchema: {
        fields: responseFields,
        example: testResponse?.data,
      },
    });
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-2">
      <div className="bg-gray-800 rounded-xl w-full max-w-5xl max-h-[92vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-gray-700 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🧪</span>
            <div>
              <h2 className="text-lg font-bold text-white">API 테스트로 추가</h2>
              <div className="flex items-center gap-2 mt-1">
                <div className={`px-2 py-0.5 text-xs rounded-full ${step === 1 ? 'bg-cyan-600 text-white' : 'bg-gray-700 text-gray-400'}`}>1. API 테스트</div>
                <span className="text-gray-600">→</span>
                <div className={`px-2 py-0.5 text-xs rounded-full ${step === 2 ? 'bg-cyan-600 text-white' : 'bg-gray-700 text-gray-400'}`}>2. 정의 저장</div>
              </div>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-2xl">&times;</button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto">
          {step === 1 && (
            <div className="flex h-full">
              {/* Left: Request */}
              <div className="flex-1 p-4 space-y-4 overflow-auto border-r border-gray-700">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">요청</label>
                  <div className="flex gap-2">
                    <select value={method} onChange={e => setMethod(e.target.value)} className={`px-3 py-2 rounded-lg text-sm font-bold ${METHOD_COLORS[method] || 'bg-gray-600'} border-none focus:outline-none cursor-pointer`}>
                      {HTTP_METHODS.map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                    <input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://api.example.com/v1/{{resource}}" className="flex-1 bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 font-mono placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-cyan-500" />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-xs text-gray-400">헤더</label>
                    <button onClick={() => setHeaders(prev => [...prev, { key: '', value: '' }])} className="text-xs text-cyan-400 hover:text-cyan-300">+ 추가</button>
                  </div>
                  <div className="space-y-1.5">
                    {headers.map((h, i) => (
                      <div key={i} className="flex gap-2">
                        <input value={h.key} onChange={e => setHeaders(prev => prev.map((item, idx) => idx === i ? { ...item, key: e.target.value } : item))} placeholder="Header-Name" className="w-1/3 bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 font-mono focus:outline-none focus:ring-1 focus:ring-cyan-500" />
                        <input value={h.value} onChange={e => setHeaders(prev => prev.map((item, idx) => idx === i ? { ...item, value: e.target.value } : item))} placeholder="value or {{variable}}" className="flex-1 bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 font-mono focus:outline-none focus:ring-1 focus:ring-cyan-500" />
                        <button onClick={() => setHeaders(prev => prev.filter((_, idx) => idx !== i))} className="text-gray-500 hover:text-red-400 text-xs px-1">&times;</button>
                      </div>
                    ))}
                  </div>
                </div>

                {['POST', 'PUT', 'PATCH'].includes(method) && (
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">바디 템플릿</label>
                    <textarea value={bodyTemplate} onChange={e => setBodyTemplate(e.target.value)} rows={5} placeholder={'{\n  "field": "{{variable}}"\n}'} className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-xs text-gray-200 font-mono resize-y focus:outline-none focus:ring-1 focus:ring-cyan-500" />
                  </div>
                )}

                {detectedVars.length > 0 && (
                  <div>
                    <label className="block text-xs text-gray-400 mb-1.5">변수 값 (테스트용)</label>
                    <div className="space-y-1.5">
                      {detectedVars.map(varName => (
                        <div key={varName} className="flex items-center gap-2">
                          <span className="text-xs text-cyan-300 font-mono w-28 truncate flex-shrink-0">{`{{${varName}}}`}</span>
                          <input value={variableValues[varName] || ''} onChange={e => setVariableValues(prev => ({ ...prev, [varName]: e.target.value }))} placeholder={`${varName} 값 입력`} className="flex-1 bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-cyan-500" />
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <button onClick={handleTest} disabled={testing || !url.trim()} className="w-full py-2.5 bg-cyan-600 text-white rounded-lg hover:bg-cyan-700 transition-colors text-sm font-medium disabled:opacity-50 flex items-center justify-center gap-2">
                  {testing ? (<><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />호출 중...</>) : ('🚀 API 호출')}
                </button>
              </div>

              {/* Right: Response */}
              <div className="w-[45%] p-4 overflow-auto">
                <label className="block text-xs text-gray-400 mb-2">응답</label>
                {testResponse ? (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-1 text-xs rounded font-bold ${testResponse.success ? 'bg-green-600/40 text-green-300' : 'bg-red-600/40 text-red-300'}`}>
                        {testResponse.success ? 'SUCCESS' : 'FAILED'}
                      </span>
                      {testResponse.time && <span className="text-gray-500 text-[10px]">{Math.round(testResponse.time)}ms</span>}
                    </div>
                    {testResponse.error && <div className="bg-red-900/30 border border-red-700/50 rounded-lg p-3 text-red-300 text-xs">{testResponse.error}</div>}
                    {testResponse.data && (
                      <pre className="bg-gray-900 border border-gray-700 rounded-lg p-3 text-xs text-gray-300 font-mono overflow-auto max-h-[50vh] whitespace-pre-wrap">
                        {typeof testResponse.data === 'string' ? testResponse.data : JSON.stringify(testResponse.data, null, 2)}
                      </pre>
                    )}
                  </div>
                ) : (
                  <div className="bg-gray-900 rounded-lg p-8 text-center">
                    <div className="text-3xl mb-2 opacity-30">📡</div>
                    <p className="text-gray-500 text-sm">API를 호출하면 응답이 여기에 표시됩니다</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="p-4 space-y-4 overflow-auto">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">이름 <span className="text-red-400">*</span></label>
                  <input value={defName} onChange={e => setDefName(e.target.value)} className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-cyan-500" />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">카테고리</label>
                  <input value={defCategory} onChange={e => setDefCategory(e.target.value)} placeholder="예: GitHub" className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-cyan-500" />
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">태그 (쉼표 구분)</label>
                <input value={defTags} onChange={e => setDefTags(e.target.value)} className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-cyan-500" />
              </div>

              <div className="bg-gray-900 rounded-lg p-3">
                <div className="text-xs text-gray-500 mb-1">API 요약</div>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 text-[10px] rounded font-bold ${METHOD_COLORS[method] || 'bg-gray-600'}`}>{method}</span>
                  <span className="text-gray-300 text-xs font-mono truncate">{url}</span>
                </div>
              </div>

              <div>
                <label className="block text-xs text-gray-400 mb-1">설명</label>
                <textarea value={defDescription} onChange={e => setDefDescription(e.target.value)} rows={3} placeholder="이 API가 무엇을 하는지..." className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 resize-y focus:outline-none focus:ring-1 focus:ring-cyan-500" />
              </div>

              {/* Parameters */}
              {parameters.length > 0 && (
                <div>
                  <label className="block text-xs text-gray-400 mb-1.5">파라미터 (자동 감지)</label>
                  <div className="bg-gray-900 rounded-lg overflow-hidden">
                    <table className="w-full text-xs">
                      <thead><tr className="border-b border-gray-700">
                        <th className="text-left px-3 py-2 text-gray-400">이름</th>
                        <th className="text-left px-3 py-2 text-gray-400 w-20">타입</th>
                        <th className="text-center px-3 py-2 text-gray-400 w-12">필수</th>
                        <th className="text-left px-3 py-2 text-gray-400">설명</th>
                      </tr></thead>
                      <tbody>
                        {parameters.map((p, i) => (
                          <tr key={p.name} className="border-b border-gray-800">
                            <td className="px-3 py-1.5 text-cyan-300 font-mono">{p.name}</td>
                            <td className="px-3 py-1.5">
                              <select value={p.type} onChange={e => setParameters(prev => prev.map((item, idx) => idx === i ? { ...item, type: e.target.value } : item))} className="bg-gray-800 border border-gray-700 rounded px-1 py-0.5 text-gray-300 w-full">
                                <option value="string">string</option>
                                <option value="number">number</option>
                                <option value="boolean">boolean</option>
                              </select>
                            </td>
                            <td className="px-3 py-1.5 text-center">
                              <input type="checkbox" checked={p.required} onChange={e => setParameters(prev => prev.map((item, idx) => idx === i ? { ...item, required: e.target.checked } : item))} className="accent-cyan-500" />
                            </td>
                            <td className="px-3 py-1.5">
                              <input value={p.description} onChange={e => setParameters(prev => prev.map((item, idx) => idx === i ? { ...item, description: e.target.value } : item))} placeholder="설명..." className="bg-transparent border-b border-gray-700 w-full text-gray-300 focus:outline-none focus:border-cyan-500 py-0.5" />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Response Fields */}
              {responseFields.length > 0 && (
                <div>
                  <label className="block text-xs text-gray-400 mb-1.5">응답 필드 (자동 감지)</label>
                  <div className="bg-gray-900 rounded-lg overflow-hidden max-h-60 overflow-y-auto">
                    <table className="w-full text-xs">
                      <thead className="sticky top-0 bg-gray-900"><tr className="border-b border-gray-700">
                        <th className="text-left px-3 py-2 text-gray-400">필드</th>
                        <th className="text-left px-3 py-2 text-gray-400 w-20">타입</th>
                        <th className="text-left px-3 py-2 text-gray-400">설명</th>
                      </tr></thead>
                      <tbody>
                        {responseFields.map((f, i) => (
                          <tr key={`${f.field}-${i}`} className="border-b border-gray-800">
                            <td className="px-3 py-1.5 text-green-300 font-mono">{f.field}</td>
                            <td className="px-3 py-1.5 text-gray-400">{f.type}</td>
                            <td className="px-3 py-1.5">
                              <input value={f.description} onChange={e => setResponseFields(prev => prev.map((item, idx) => idx === i ? { ...item, description: e.target.value } : item))} placeholder="설명..." className="bg-transparent border-b border-gray-700 w-full text-gray-300 focus:outline-none focus:border-cyan-500 py-0.5" />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-700 flex items-center justify-between">
          <div>
            {step === 2 && (
              <button onClick={() => setStep(1)} className="px-4 py-2 text-gray-400 hover:text-white text-sm">← API 테스트로 돌아가기</button>
            )}
          </div>
          <div className="flex gap-3">
            <button onClick={onClose} className="px-4 py-2 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 text-sm">취소</button>
            {step === 1 ? (
              <button onClick={handleProceedToStep2} disabled={!testResponse?.success} className="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-700 text-sm disabled:opacity-50">다음: 정의 저장 →</button>
            ) : (
              <button onClick={handleSave} disabled={saving || !defName.trim()} className="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-700 text-sm disabled:opacity-50 flex items-center gap-2">
                {saving ? (<><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />저장 중...</>) : 'API 정의 저장'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
