import { useState, useEffect, useRef } from 'react';
import { apiDefinitionApi } from '../../services/api';
import type { ApiDefinition } from '../../types';

interface UpstreamField {
  name: string;
  type: string;
}

interface AiApiRouterConfigPanelProps {
  nodeId: string;
  nodeName: string;
  config: {
    prompt?: string;
    apiIds?: string[];
  };
  inputMapping: Record<string, string>;
  upstreamFields?: UpstreamField[];
  onUpdateName: (name: string) => void;
  onUpdateConfig: (config: AiApiRouterConfigPanelProps['config']) => void;
  onDelete: () => void;
  onClose: () => void;
}

function TypeBadge({ type }: { type: string }) {
  const styles: Record<string, string> = {
    string:  'bg-emerald-800/50 text-emerald-300',
    number:  'bg-orange-800/50 text-orange-300',
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

const OUTPUT_FIELDS = [
  { name: 'api_route', type: 'object', desc: 'AI 라우팅 결과 (아래 구조)' },
  { name: '  .called', type: 'boolean', desc: 'API 호출 여부' },
  { name: '  .reason', type: 'string', desc: 'AI 판단 근거' },
  { name: '  .apiId', type: 'string', desc: '호출된 API ID' },
  { name: '  .apiName', type: 'string', desc: '호출된 API 이름' },
  { name: '  .request', type: 'object', desc: '요청 정보 (method, url, parameters, body)' },
  { name: '  .response', type: 'object', desc: '응답 정보 (status, data)' },
];


export function AiApiRouterConfigPanel({
  nodeId,
  nodeName,
  config,
  upstreamFields = [],
  onUpdateName,
  onUpdateConfig,
  onDelete,
  onClose,
}: AiApiRouterConfigPanelProps) {
  void nodeId;

  const [localConfig, setLocalConfig] = useState({
    prompt: config.prompt || '',
    apiIds: config.apiIds || [] as string[],
  });

  const [apiDefs, setApiDefs] = useState<ApiDefinition[]>([]);
  const [apiLoading, setApiLoading] = useState(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    let mounted = true;
    apiDefinitionApi.list().then(defs => {
      if (mounted) { setApiDefs(defs); setApiLoading(false); }
    }).catch(() => { if (mounted) setApiLoading(false); });
    return () => { mounted = false; };
  }, []);

  function update(patch: Partial<typeof localConfig>) {
    const next = { ...localConfig, ...patch };
    setLocalConfig(next);
    onUpdateConfig(next);
  }

  function toggleApi(apiId: string) {
    const current = localConfig.apiIds || [];
    const next = current.includes(apiId)
      ? current.filter(id => id !== apiId)
      : [...current, apiId];
    update({ apiIds: next });
  }

  function insertVariable(fieldName: string) {
    const ta = textareaRef.current;
    if (!ta) return;
    const tag = `{{${fieldName}}}`;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const before = localConfig.prompt.slice(0, start);
    const after = localConfig.prompt.slice(end);
    const newPrompt = before + tag + after;
    update({ prompt: newPrompt });
    // 커서를 삽입된 태그 뒤로 이동
    requestAnimationFrame(() => {
      ta.focus();
      const pos = start + tag.length;
      ta.setSelectionRange(pos, pos);
    });
  }

  return (
    <div className="w-96 h-full bg-gray-800 border-l border-gray-700 flex flex-col overflow-hidden animate-slide-in-right">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-purple-900 flex items-center justify-center text-xl">
              🤖
            </div>
            <div>
              <div className="text-xs text-purple-300/70 uppercase tracking-wider">AI API 라우터 설정</div>
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
        {/* API 선택 필터 */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5">
            사용할 API 선택
            {localConfig.apiIds.length > 0 && (
              <span className="ml-1.5 px-1.5 py-0.5 bg-purple-600/30 text-purple-300 rounded text-[10px]">
                {localConfig.apiIds.length}개 선택
              </span>
            )}
          </label>
          {apiLoading ? (
            <div className="animate-pulse bg-gray-700 rounded h-20 w-full" />
          ) : apiDefs.length === 0 ? (
            <div className="bg-gray-900 rounded-lg p-3 text-center">
              <p className="text-gray-500 text-xs">등록된 API 정의가 없습니다</p>
              <p className="text-gray-600 text-[10px] mt-1">API 정의 페이지에서 추가하세요</p>
            </div>
          ) : (
            <>
              {/* Selected API badges */}
              {localConfig.apiIds.length > 0 && (
                <div className="flex flex-wrap gap-1 mb-2">
                  {localConfig.apiIds.map(id => {
                    const def = apiDefs.find(d => d.id === id);
                    return (
                      <button
                        key={id}
                        onClick={() => toggleApi(id)}
                        className="inline-flex items-center gap-1 px-2 py-0.5 bg-purple-600/40 text-purple-200 border border-purple-500/50 rounded text-[11px] hover:bg-purple-600/60 transition-colors"
                      >
                        {def ? `[${def.method}] ${def.name}` : id}
                        <span className="text-purple-400">×</span>
                      </button>
                    );
                  })}
                </div>
              )}

              {/* API checkbox list */}
              <div className="max-h-48 overflow-y-auto bg-gray-900 border border-gray-600 rounded-lg p-2 space-y-0.5">
                {apiDefs.map(def => {
                  const isChecked = localConfig.apiIds.includes(def.id);
                  const methodColors: Record<string, string> = {
                    GET: 'bg-green-600/60 text-green-200',
                    POST: 'bg-blue-600/60 text-blue-200',
                    PUT: 'bg-amber-600/60 text-amber-200',
                    PATCH: 'bg-orange-600/60 text-orange-200',
                    DELETE: 'bg-red-600/60 text-red-200',
                  };
                  return (
                    <label
                      key={def.id}
                      className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer transition-colors text-xs ${
                        isChecked ? 'bg-purple-900/30 text-purple-200' : 'text-gray-300 hover:bg-gray-800'
                      }`}
                    >
                      <input type="checkbox" checked={isChecked} onChange={() => toggleApi(def.id)} className="sr-only" />
                      <div className={`w-3.5 h-3.5 rounded border flex-shrink-0 flex items-center justify-center transition-colors ${
                        isChecked ? 'bg-purple-500 border-purple-400' : 'border-gray-500 bg-transparent'
                      }`}>
                        {isChecked && (
                          <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                      </div>
                      <span className={`px-1.5 py-0.5 text-[9px] rounded-full font-bold ${methodColors[def.method] || 'bg-gray-600/60 text-gray-200'}`}>
                        {def.method}
                      </span>
                      <span className="truncate">{def.name}</span>
                    </label>
                  );
                })}
              </div>
              <p className="text-[10px] text-gray-500 mt-1.5">
                선택하지 않으면 모든 API를 대상으로 판단합니다
              </p>
            </>
          )}
        </div>

        {/* 프롬프트 + 변수 삽입 */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5">추가 지시사항 (프롬프트)</label>

          {/* 입력 변수 칩 */}
          {upstreamFields.length > 0 && (
            <div className="mb-2">
              <div className="text-[10px] text-gray-500 mb-1">클릭하여 변수 삽입:</div>
              <div className="flex flex-wrap gap-1">
                {upstreamFields.map(field => (
                  <button
                    key={field.name}
                    onClick={() => insertVariable(field.name)}
                    className="inline-flex items-center gap-1 px-2 py-0.5 bg-purple-900/40 text-purple-300 border border-purple-600/50 rounded text-[11px] hover:bg-purple-800/50 hover:border-purple-500 transition-colors cursor-pointer"
                    title={`{{${field.name}}} 삽입`}
                  >
                    <span className="text-purple-400/70 font-mono">{'{{'}</span>
                    <span className="font-mono">{field.name}</span>
                    <TypeBadge type={field.type} />
                    <span className="text-purple-400/70 font-mono">{'}}'}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <textarea
            ref={textareaRef}
            value={localConfig.prompt}
            onChange={(e) => update({ prompt: e.target.value })}
            rows={5}
            className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-purple-500 resize-none placeholder-gray-600 font-mono"
            placeholder={upstreamFields.length > 0
              ? `위 변수를 클릭하거나 직접 {{변수명}}을 입력하세요.\n예: {{${upstreamFields[0].name}}}의 내용을 분석하여 적절한 API를 호출하세요`
              : 'AI에게 추가 지시사항을 입력하세요... (선택사항)'}
          />
          <p className="text-[10px] text-gray-500 mt-1">
            {'{{변수명}}'} 형식으로 이전 노드의 데이터를 참조할 수 있습니다
          </p>
        </div>

        {/* 입력 데이터 미리보기 */}
        {upstreamFields.length > 0 && (
          <div>
            <div className="text-xs font-medium text-green-400 mb-2">입력 데이터 (이전 노드 출력)</div>
            <div className="bg-gray-900 rounded-lg border border-gray-700/50 p-2 space-y-0.5">
              {upstreamFields.map(field => (
                <div key={field.name} className="flex items-center gap-2 px-2 py-1">
                  <div className="w-1.5 h-1.5 rounded-full bg-green-400 flex-shrink-0" />
                  <span className="text-gray-200 text-xs font-mono flex-1">{field.name}</span>
                  <TypeBadge type={field.type} />
                </div>
              ))}
            </div>
            <p className="text-[10px] text-gray-500 mt-1">
              이 데이터가 AI에게 전달되어 API 호출 여부를 판단합니다
            </p>
          </div>
        )}

        {/* 출력 필드 */}
        <div>
          <div className="text-xs font-medium text-blue-400 mb-2">출력 필드</div>
          <div className="bg-gray-900 rounded-lg divide-y divide-gray-800 border border-gray-700/50">
            {OUTPUT_FIELDS.map((field) => (
              <div key={field.name} className="px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className="text-gray-200 text-xs font-mono flex-1">{field.name}</span>
                  <TypeBadge type={field.type} />
                  <span className="text-[10px] text-gray-500">{field.desc}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Info box */}
        <div className="bg-purple-900/20 border border-purple-700/30 rounded-lg px-3 py-2.5">
          <p className="text-[11px] text-purple-300/70 leading-relaxed">
            이 노드는 {localConfig.apiIds.length > 0 ? '선택된' : '등록된 모든'} API 정의를 참조하여, 입력 데이터에 적합한 API가 있으면 자동으로 호출합니다.
          </p>
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
