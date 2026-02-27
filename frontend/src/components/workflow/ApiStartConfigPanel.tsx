import { useState, useEffect, useCallback } from 'react';
import { apiDefinitionApi } from '../../services/api';
import type { ApiDefinition, ApiParam, ResponseField } from '../../types';

interface ScheduleConfig {
  type?: string;
  hour?: number;
  minute?: number;
  dayOfWeek?: number;
  dayOfMonth?: number;
}

interface ApiStartConfig {
  mode?: 'manual' | 'schedule';
  scheduleConfig?: ScheduleConfig;
  apiDefinitionId?: string;
  docId?: string;
  docTitle?: string;
  method?: string;
  url?: string;
  inputFields?: string[];
  defaultParams?: Record<string, any>;
}

interface ApiStartConfigPanelProps {
  nodeId: string;
  nodeName: string;
  config: ApiStartConfig;
  onUpdateName: (name: string) => void;
  onUpdateConfig: (config: ApiStartConfig) => void;
  onExecute: () => void;
  executing?: boolean;
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

const SCHEDULE_TYPES = [
  { value: 'hourly', label: '매시간' },
  { value: 'daily', label: '매일' },
  { value: 'weekly', label: '매주' },
  { value: 'monthly', label: '매월' },
];

const DAY_OF_WEEK_OPTIONS = [
  { value: 0, label: '월요일' },
  { value: 1, label: '화요일' },
  { value: 2, label: '수요일' },
  { value: 3, label: '목요일' },
  { value: 4, label: '금요일' },
  { value: 5, label: '토요일' },
  { value: 6, label: '일요일' },
];

export function ApiStartConfigPanel({
  nodeId,
  nodeName,
  config,
  onUpdateName,
  onUpdateConfig,
  onExecute,
  executing,
  onDelete,
  onClose,
}: ApiStartConfigPanelProps) {
  const [apiDefs, setApiDefs] = useState<ApiDefinition[]>([]);
  const [loading, setLoading] = useState(true);

  const mode = config.mode || 'manual';
  const scheduleConfig = config.scheduleConfig || {};
  const [scheduleType, setScheduleType] = useState(scheduleConfig.type || 'daily');
  const [hour, setHour] = useState(scheduleConfig.hour ?? 9);
  const [minute, setMinute] = useState(scheduleConfig.minute ?? 0);
  const [dayOfWeek, setDayOfWeek] = useState(scheduleConfig.dayOfWeek ?? 0);
  const [dayOfMonth, setDayOfMonth] = useState(scheduleConfig.dayOfMonth ?? 1);

  // Suppress unused var lint
  void nodeId;

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

  const handleModeChange = (newMode: 'manual' | 'schedule') => {
    onUpdateConfig({ ...config, mode: newMode });
  };

  const handleScheduleUpdate = (patch: Partial<ScheduleConfig>) => {
    const newSchedule = {
      type: scheduleType,
      hour,
      minute,
      dayOfWeek,
      dayOfMonth,
      ...patch,
    };
    if (patch.type !== undefined) setScheduleType(patch.type);
    if (patch.hour !== undefined) setHour(patch.hour);
    if (patch.minute !== undefined) setMinute(patch.minute);
    if (patch.dayOfWeek !== undefined) setDayOfWeek(patch.dayOfWeek);
    if (patch.dayOfMonth !== undefined) setDayOfMonth(patch.dayOfMonth);
    onUpdateConfig({ ...config, mode: 'schedule', scheduleConfig: newSchedule });
  };

  // Handle API definition selection
  const handleApiDefSelect = useCallback((apiDefId: string) => {
    const def = apiDefs.find(d => d.id === apiDefId);
    if (!def) return;

    const method = def.method || 'GET';
    const url = def.urlTemplate || '';

    // Extract input fields from parameters
    const paramFields = def.parameters
      .filter(p => p.in === 'path' || p.in === 'query' || p.in === 'body')
      .map(p => p.name);

    // Also check for {{variable}} in url template, headers, body
    const allTemplates = [url, ...Object.values(def.headers || {}).map(String), def.bodyTemplate || ''].join(' ');
    const placeholders = extractPlaceholders(allTemplates);
    const inputFields = [...new Set([...paramFields, ...placeholders])];

    onUpdateConfig({
      ...config,
      apiDefinitionId: def.id,
      docId: def.id,
      docTitle: def.name,
      method,
      url,
      inputFields,
    });
  }, [apiDefs, config, onUpdateConfig]);

  const handleDefaultParamChange = (field: string, value: string) => {
    const newDefaults = { ...(config.defaultParams || {}), [field]: value };
    onUpdateConfig({ ...config, defaultParams: newDefaults });
  };

  // Method badge colors
  const methodColors: Record<string, string> = {
    GET: 'bg-green-600/60 text-green-200',
    POST: 'bg-blue-600/60 text-blue-200',
    PUT: 'bg-amber-600/60 text-amber-200',
    PATCH: 'bg-orange-600/60 text-orange-200',
    DELETE: 'bg-red-600/60 text-red-200',
  };

  // Resolve the currently selected ApiDefinition object
  const selectedDef = apiDefs.find(d => d.id === (config.apiDefinitionId || config.docId));

  return (
    <div className="w-96 h-full bg-gray-800 border-l border-gray-700 flex flex-col overflow-hidden animate-slide-in-right">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-teal-900 flex items-center justify-center text-xl">
              {'\u{1F680}'}
            </div>
            <div>
              <div className="text-xs text-teal-300/70 uppercase tracking-wider">API 시작 설정</div>
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
        {/* Mode toggle */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5">실행 모드</label>
          <div className="flex gap-2">
            <button
              onClick={() => handleModeChange('manual')}
              className={`flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                mode === 'manual'
                  ? 'bg-teal-600 text-white'
                  : 'bg-gray-700 text-gray-400 hover:text-gray-200'
              }`}
            >
              수동실행
            </button>
            <button
              onClick={() => handleModeChange('schedule')}
              className={`flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                mode === 'schedule'
                  ? 'bg-teal-600 text-white'
                  : 'bg-gray-700 text-gray-400 hover:text-gray-200'
              }`}
            >
              스케줄
            </button>
          </div>
        </div>

        {/* Schedule settings */}
        {mode === 'schedule' && (
          <div className="space-y-3 bg-gray-900 rounded-lg p-3">
            <div className="text-xs text-teal-300/70 font-medium mb-2">스케줄 설정</div>

            <div>
              <label className="block text-[10px] text-gray-400 mb-1 uppercase tracking-wide">반복 유형</label>
              <select
                value={scheduleType}
                onChange={(e) => handleScheduleUpdate({ type: e.target.value })}
                className="w-full bg-gray-800 border border-gray-600 rounded px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-teal-500"
              >
                {SCHEDULE_TYPES.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            {scheduleType === 'weekly' && (
              <div>
                <label className="block text-[10px] text-gray-400 mb-1 uppercase tracking-wide">요일</label>
                <select
                  value={dayOfWeek}
                  onChange={(e) => handleScheduleUpdate({ dayOfWeek: Number(e.target.value) })}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-teal-500"
                >
                  {DAY_OF_WEEK_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
            )}

            {scheduleType === 'monthly' && (
              <div>
                <label className="block text-[10px] text-gray-400 mb-1 uppercase tracking-wide">일</label>
                <select
                  value={dayOfMonth}
                  onChange={(e) => handleScheduleUpdate({ dayOfMonth: Number(e.target.value) })}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-teal-500"
                >
                  {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
                    <option key={d} value={d}>{d}일</option>
                  ))}
                </select>
              </div>
            )}

            {scheduleType !== 'hourly' && (
              <div className="flex gap-2">
                <div className="flex-1">
                  <label className="block text-[10px] text-gray-400 mb-1 uppercase tracking-wide">시</label>
                  <select
                    value={hour}
                    onChange={(e) => handleScheduleUpdate({ hour: Number(e.target.value) })}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-teal-500"
                  >
                    {Array.from({ length: 24 }, (_, i) => i).map((h) => (
                      <option key={h} value={h}>{String(h).padStart(2, '0')}시</option>
                    ))}
                  </select>
                </div>
                <div className="flex-1">
                  <label className="block text-[10px] text-gray-400 mb-1 uppercase tracking-wide">분</label>
                  <select
                    value={minute}
                    onChange={(e) => handleScheduleUpdate({ minute: Number(e.target.value) })}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-teal-500"
                  >
                    {Array.from({ length: 60 }, (_, i) => i).map((m) => (
                      <option key={m} value={m}>{String(m).padStart(2, '0')}분</option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            {scheduleType === 'hourly' && (
              <div>
                <label className="block text-[10px] text-gray-400 mb-1 uppercase tracking-wide">분</label>
                <select
                  value={minute}
                  onChange={(e) => handleScheduleUpdate({ minute: Number(e.target.value) })}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-teal-500"
                >
                  {Array.from({ length: 60 }, (_, i) => i).map((m) => (
                    <option key={m} value={m}>{String(m).padStart(2, '0')}분</option>
                  ))}
                </select>
              </div>
            )}

            <div className="p-2 bg-yellow-900/20 border border-yellow-700/40 rounded-lg">
              <p className="text-[10px] text-yellow-400/80">
                실제 스케줄 실행은 미구현 상태입니다. 설정만 저장됩니다.
              </p>
            </div>
          </div>
        )}

        {/* API Definition selector */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5">API 정의 선택</label>
          {loading ? (
            <div className="text-gray-500 text-xs">로딩 중...</div>
          ) : (
            <select
              value={config.apiDefinitionId || config.docId || ''}
              onChange={(e) => handleApiDefSelect(e.target.value)}
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-teal-500"
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
                      methodColors[dispMethod] || 'bg-gray-600/60 text-gray-200'
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

            {/* Parameters (rich view) + default values */}
            <div>
              <div className="text-xs font-medium text-teal-400 mb-2">파라미터</div>
              {selectedDef && selectedDef.parameters.length > 0 ? (
                <div className="space-y-2">
                  {selectedDef.parameters.map((param: ApiParam) => (
                    <div key={param.name} className="bg-gray-900 rounded-lg px-3 py-2">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-gray-200 text-xs font-mono">{param.name}</span>
                        {param.required && (
                          <span className="text-red-400 text-xs font-bold leading-none" title="필수">*</span>
                        )}
                        <InBadge location={param.in} />
                        <TypeBadge type={param.type} />
                      </div>
                      {param.description && (
                        <div className="text-[10px] text-gray-500 mt-1 leading-snug">
                          {param.description}
                        </div>
                      )}
                      {/* Default value input for this param */}
                      <input
                        type="text"
                        value={config.defaultParams?.[param.name] || ''}
                        onChange={(e) => handleDefaultParamChange(param.name, e.target.value)}
                        placeholder="기본값 (선택사항)"
                        className="w-full mt-1.5 bg-gray-800 border border-gray-600 rounded px-2 py-1 text-[11px] text-gray-200 focus:outline-none focus:ring-1 focus:ring-teal-500"
                      />
                    </div>
                  ))}
                </div>
              ) : (config.inputFields || []).length > 0 ? (
                /* Fallback for placeholder-extracted fields */
                <div className="space-y-2">
                  {config.inputFields!.map(field => (
                    <div key={field} className="bg-gray-900 rounded-lg px-3 py-2">
                      <div className="flex items-center gap-2 mb-1">
                        <div className="w-1.5 h-1.5 rounded-full bg-teal-400" />
                        <span className="text-gray-300 text-xs font-mono">{field}</span>
                      </div>
                      <input
                        type="text"
                        value={config.defaultParams?.[field] || ''}
                        onChange={(e) => handleDefaultParamChange(field, e.target.value)}
                        placeholder="기본값 (선택사항)"
                        className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-[11px] text-gray-200 focus:outline-none focus:ring-1 focus:ring-teal-500"
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-gray-500 text-xs">파라미터 없음</p>
              )}
              <p className="text-[10px] text-gray-600 mt-1">
                URL, 헤더, 바디의 {'{{변수}}'} 패턴에서 자동 추출됩니다.
              </p>
            </div>

            {/* Node Output Format */}
            <div>
              <div className="text-xs font-medium text-blue-400 mb-2">노드 출력</div>
              <div className="bg-gray-900 rounded-lg overflow-hidden">
                <div className="px-3 py-2 border-b border-gray-800">
                  <div className="flex items-center gap-2">
                    <span className="text-gray-200 text-xs font-mono">status</span>
                    <TypeBadge type="number" />
                    <span className="ml-auto text-[10px] text-gray-500">HTTP 상태 코드</span>
                  </div>
                </div>
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

        {/* Info box */}
        <div className="bg-teal-900/20 border border-teal-700/40 rounded-lg p-3">
          <p className="text-xs text-teal-300/80 leading-relaxed">
            선택한 API를 호출하고 응답(Response)을 다음 노드로 전달합니다.
          </p>
        </div>
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-gray-700 space-y-2">
        {mode === 'manual' && (config.apiDefinitionId || config.docId) && (
          <button
            onClick={onExecute}
            disabled={executing}
            className={`w-full px-4 py-2.5 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
              executing
                ? 'bg-teal-700/50 text-teal-300/50 cursor-not-allowed'
                : 'bg-teal-600 text-white hover:bg-teal-500'
            }`}
          >
            {executing ? (
              <>
                <span className="animate-spin">⏳</span>
                실행 중...
              </>
            ) : (
              <>
                <span>▶</span>
                수동 실행
              </>
            )}
          </button>
        )}
        <button
          onClick={onDelete}
          className="w-full px-3 py-2 bg-red-600/20 text-red-400 rounded-lg hover:bg-red-600/30 text-sm transition-colors"
        >
          삭제
        </button>
      </div>
    </div>
  );
}
