import { useState, useEffect, useCallback } from 'react';
import { apiDefinitionApi } from '../../services/api';
import type { ApiDefinition, ApiParam, ResponseField } from '../../types';

interface ApiCallConfigPanelProps {
  nodeId: string;
  nodeName: string;
  config: {
    apiDefinitionId?: string;
    docId?: string;
    docTitle?: string;
    method?: string;
    url?: string;
    inputFields?: string[];
    outputFields?: string[];
  };
  inputMapping: Record<string, string>;
  onUpdateName: (name: string) => void;
  onUpdateConfig: (config: ApiCallConfigPanelProps['config']) => void;
  onDelete: () => void;
  onClose: () => void;
}

/** Extract {{variable}} placeholders from a template string */
function extractPlaceholders(template: string): string[] {
  const matches = template.match(/\{\{([^}]+)\}\}/g) || [];
  return [...new Set(matches.map(m => m.replace(/^\{\{|\}\}$/g, '').trim()))];
}

/** Badge for parameter `in` location */
function InBadge({ location }: { location: ApiParam['in'] }) {
  const styles: Record<ApiParam['in'], string> = {
    path:   'bg-purple-700/50 text-purple-200',
    query:  'bg-blue-700/50 text-blue-200',
    header: 'bg-amber-700/50 text-amber-200',
    body:   'bg-green-700/50 text-green-200',
  };
  return (
    <span className={`px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase ${styles[location] ?? 'bg-gray-700/50 text-gray-300'}`}>
      {location}
    </span>
  );
}

/** Badge for a data type */
function TypeBadge({ type }: { type: string }) {
  const styles: Record<string, string> = {
    string:  'bg-emerald-800/50 text-emerald-300',
    number:  'bg-orange-800/50 text-orange-300',
    integer: 'bg-orange-800/50 text-orange-300',
    boolean: 'bg-pink-800/50 text-pink-300',
    object:  'bg-sky-800/50 text-sky-300',
    array:   'bg-violet-800/50 text-violet-300',
  };
  return (
    <span className={`px-1.5 py-0.5 rounded text-[9px] font-mono ${styles[type] ?? 'bg-gray-700/50 text-gray-300'}`}>
      {type}
    </span>
  );
}

export function ApiCallConfigPanel({
  nodeId,
  nodeName,
  config,
  inputMapping,
  onUpdateName,
  onUpdateConfig,
  onDelete,
  onClose,
}: ApiCallConfigPanelProps) {
  const [apiDefs, setApiDefs] = useState<ApiDefinition[]>([]);
  const [loading, setLoading] = useState(true);

  // Fetch API definitions on mount
  useEffect(() => {
    let mounted = true;
    apiDefinitionApi.list().then(defs => {
      if (mounted) {
        setApiDefs(defs);
        setLoading(false);
      }
    }).catch(() => {
      if (mounted) setLoading(false);
    });
    return () => { mounted = false; };
  }, []);

  // Handle API definition selection
  const handleApiDefSelect = useCallback((apiDefId: string) => {
    const def = apiDefs.find(d => d.id === apiDefId);
    if (!def) return;

    const method = def.method || 'GET';
    const url = def.urlTemplate || '';

    // Extract input fields from parameters
    const inputFields = def.parameters
      .filter(p => p.in === 'path' || p.in === 'query' || p.in === 'body')
      .map(p => p.name);

    // Also check for {{variable}} in url template, headers, body
    const allTemplates = [url, ...Object.values(def.headers || {}).map(String), def.bodyTemplate || ''].join(' ');
    const placeholders = extractPlaceholders(allTemplates);
    const allInputFields = [...new Set([...inputFields, ...placeholders])];

    const outputFields = ['status', 'data'];

    onUpdateConfig({
      apiDefinitionId: def.id,
      docId: def.id,  // backwards compat
      docTitle: def.name,
      method,
      url,
      inputFields: allInputFields,
      outputFields,
    });
  }, [apiDefs, onUpdateConfig]);

  // Suppress unused nodeId warning - kept for consistency with other panels
  void nodeId;

  // Resolve the currently selected ApiDefinition object
  const selectedDef = apiDefs.find(d => d.id === (config.apiDefinitionId || config.docId));

  return (
    <div className="w-96 h-full bg-gray-800 border-l border-gray-700 flex flex-col overflow-hidden animate-slide-in-right">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-cyan-900 flex items-center justify-center text-xl">
              🌐
            </div>
            <div>
              <div className="text-xs text-cyan-300/70 uppercase tracking-wider">API 호출기 설정</div>
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
        {/* API Doc selector */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5">API 정의 선택</label>
          {loading ? (
            <div className="text-gray-500 text-xs">로딩 중...</div>
          ) : (
            <select
              value={config.apiDefinitionId || config.docId || ''}
              onChange={(e) => handleApiDefSelect(e.target.value)}
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-cyan-500"
            >
              <option value="">API 정의를 선택하세요...</option>
              {apiDefs.map(def => (
                <option key={def.id} value={def.id}>
                  [{def.method}] {def.name}
                </option>
              ))}
            </select>
          )}
          {apiDefs.length === 0 && !loading && (
            <p className="text-gray-500 text-[10px] mt-1">
              API 정의가 없습니다. API 정의 페이지에서 추가하세요.
            </p>
          )}
        </div>

        {/* Selected doc preview */}
        {(config.docId || config.apiDefinitionId) && (
          <>
            {/* Method + URL */}
            {(() => {
              const dispMethod = config.method || selectedDef?.method || 'GET';
              const dispTitle = config.docTitle || selectedDef?.name || '';
              const dispUrl = config.url || selectedDef?.urlTemplate || '';
              return (
                <div className="bg-gray-900 rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`px-2 py-0.5 text-[10px] rounded-full font-bold ${
                      dispMethod === 'GET'    ? 'bg-green-600/60 text-green-200' :
                      dispMethod === 'POST'   ? 'bg-blue-600/60 text-blue-200' :
                      dispMethod === 'PUT'    ? 'bg-amber-600/60 text-amber-200' :
                      dispMethod === 'DELETE' ? 'bg-red-600/60 text-red-200' :
                      'bg-gray-600/60 text-gray-200'
                    }`}>
                      {dispMethod}
                    </span>
                    <span className="text-gray-300 text-xs font-medium">{dispTitle}</span>
                  </div>
                  {dispUrl && <div className="text-[10px] text-gray-500 font-mono break-all">{dispUrl}</div>}
                </div>
              );
            })()}

            {/* API Description */}
            {selectedDef?.description && (
              <div>
                <div className="text-xs font-medium text-gray-400 mb-1.5">API 설명</div>
                <p className="text-gray-300 text-xs leading-relaxed bg-gray-900 rounded-lg px-3 py-2">
                  {selectedDef.description}
                </p>
              </div>
            )}

            {/* Parameters (rich view) */}
            <div>
              <div className="text-xs font-medium text-green-400 mb-2">파라미터</div>
              {selectedDef && selectedDef.parameters.length > 0 ? (
                <div className="space-y-2">
                  {selectedDef.parameters.map((param: ApiParam) => (
                    <div key={param.name} className="bg-gray-900 rounded-lg px-3 py-2">
                      {/* Top row: name, badges, required marker, mapping status */}
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-gray-200 text-xs font-mono">{param.name}</span>
                        {param.required && (
                          <span className="text-red-400 text-xs font-bold leading-none" title="필수">*</span>
                        )}
                        <InBadge location={param.in} />
                        <TypeBadge type={param.type} />
                        <span className="ml-auto text-[10px]">
                          {inputMapping[param.name] ? (
                            <span className="text-green-400/70">{inputMapping[param.name]}</span>
                          ) : (
                            <span className="text-yellow-400/70">미연결</span>
                          )}
                        </span>
                      </div>
                      {/* Description row */}
                      {param.description && (
                        <div className="text-[10px] text-gray-500 mt-1 leading-snug">
                          {param.description}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (config.inputFields || []).length > 0 ? (
                /* Fallback: show placeholder-extracted fields as chips */
                <div className="space-y-1.5">
                  {config.inputFields!.map(field => (
                    <div key={field} className="bg-gray-900 rounded-lg px-3 py-2 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className="w-1.5 h-1.5 rounded-full bg-green-400" />
                        <span className="text-gray-300 text-xs font-mono">{field}</span>
                      </div>
                      <div className="text-[10px] text-gray-600">
                        {inputMapping[field] ? (
                          <span className="text-green-400/70">{inputMapping[field]}</span>
                        ) : (
                          <span className="text-yellow-400/70">미연결</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-gray-500 text-xs">파라미터 없음 (고정 URL)</p>
              )}
              <p className="text-[10px] text-gray-600 mt-1">
                URL, 헤더, 바디의 {'{{변수}}'} 패턴에서 자동 추출됩니다.
              </p>
            </div>

            {/* Node Output Format */}
            <div>
              <div className="text-xs font-medium text-blue-400 mb-2">노드 출력</div>
              <div className="bg-gray-900 rounded-lg overflow-hidden">
                {/* status field */}
                <div className="px-3 py-2 border-b border-gray-800">
                  <div className="flex items-center gap-2">
                    <span className="text-gray-200 text-xs font-mono">status</span>
                    <TypeBadge type="number" />
                    <span className="ml-auto text-[10px] text-gray-500">HTTP 상태 코드</span>
                  </div>
                </div>
                {/* data field — expandable to show API response structure */}
                <div className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <span className="text-gray-200 text-xs font-mono">data</span>
                    <TypeBadge type="object" />
                    <span className="ml-auto text-[10px] text-gray-500">API 응답 본문</span>
                  </div>
                  <p className="text-[10px] text-gray-600 mt-1">
                    다음 노드에서 <span className="text-blue-400 font-mono">$.data</span>로 응답 본문 전체를,{' '}
                    <span className="text-blue-400 font-mono">$.status</span>로 HTTP 코드를 참조합니다.
                  </p>
                </div>
              </div>
            </div>

            {/* API Response Body Structure (inside data) */}
            {selectedDef && selectedDef.responseSchema?.fields?.length > 0 && (
              <div>
                <div className="text-xs font-medium text-cyan-400 mb-2 flex items-center gap-1.5">
                  <span className="text-gray-500 font-mono text-[10px]">$.data</span>
                  <span>응답 본문 구조</span>
                </div>
                <div className="bg-gray-900 rounded-lg divide-y divide-gray-800 border border-gray-700/50">
                  {selectedDef.responseSchema.fields.map((field: ResponseField) => (
                    <div key={field.field} className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <span className="text-gray-200 text-xs font-mono flex-1">{field.field}</span>
                        <TypeBadge type={field.type} />
                      </div>
                      {field.description && (
                        <div className="text-[10px] text-gray-500 mt-0.5 leading-snug">
                          {field.description}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
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
