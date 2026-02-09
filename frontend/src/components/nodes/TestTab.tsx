import { useState, useCallback } from 'react';
import type { JsonSchema, JsonSchemaProperty } from '../../types';

// ============================================
// Dynamic test input form + mock execution
// ============================================

// ─── Mock output generator ───────────────────────────────────────────────────
// Deterministically produces plausible values that match the outputSchema shape.

function mockValue(prop: JsonSchemaProperty): unknown {
  switch (prop.type) {
    case 'string':
      if (prop.enum && prop.enum.length > 0) return prop.enum[0];
      if (prop.description?.includes('ID')) return 'id-' + Math.random().toString(36).slice(2, 9);
      if (prop.description?.includes('URL') || prop.description?.includes('url'))
        return 'https://api.example.com/result';
      if (prop.description?.includes('날짜') || prop.description?.includes('일'))
        return new Date().toISOString();
      return '(mock) ' + (prop.description || 'value');
    case 'number':
      if (prop.description?.includes('수') || prop.description?.includes('count'))
        return Math.floor(Math.random() * 100) + 1;
      if (prop.description?.includes('신뢰') || prop.description?.includes('confidence'))
        return Math.round(Math.random() * 100) / 100;
      return Math.floor(Math.random() * 1000);
    case 'boolean':
      return true;
    case 'object':
      if (prop.properties) {
        const obj: Record<string, unknown> = {};
        for (const [k, v] of Object.entries(prop.properties)) {
          obj[k] = mockValue(v);
        }
        return obj;
      }
      return { sample: 'object' };
    case 'array':
      if (prop.items) {
        return [mockValue(prop.items), mockValue(prop.items)];
      }
      return ['item-1', 'item-2'];
  }
}

function generateMockOutput(schema: JsonSchema): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, prop] of Object.entries(schema.properties)) {
    result[key] = mockValue(prop);
  }
  return result;
}

// ─── Single dynamic input field ──────────────────────────────────────────────

function TestInputField({
  name,
  prop,
  value,
  onChange,
}: {
  name: string;
  prop: JsonSchemaProperty;
  value: unknown;
  onChange: (val: unknown) => void;
}) {
  const strVal = value !== undefined && value !== null ? String(value) : '';

  switch (prop.type) {
    case 'string':
      if (prop.enum && prop.enum.length > 0) {
        return (
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              <span className="text-gray-300 font-medium">{name}</span>
              {prop.description && <span className="text-gray-600 ml-2">{prop.description}</span>}
            </label>
            <select
              value={strVal}
              onChange={(e) => onChange(e.target.value)}
              className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="">— 선택 —</option>
              {prop.enum.map((opt) => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          </div>
        );
      }
      return (
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            <span className="text-gray-300 font-medium">{name}</span>
            {prop.description && <span className="text-gray-600 ml-2">{prop.description}</span>}
          </label>
          <input
            type="text"
            value={strVal}
            onChange={(e) => onChange(e.target.value)}
            placeholder={prop.default !== undefined ? String(prop.default) : name}
            className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>
      );

    case 'number':
      return (
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            <span className="text-gray-300 font-medium">{name}</span>
            {prop.description && <span className="text-gray-600 ml-2">{prop.description}</span>}
          </label>
          <input
            type="number"
            value={strVal}
            onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
            placeholder={prop.default !== undefined ? String(prop.default) : '0'}
            className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>
      );

    case 'boolean':
      return (
        <div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={!!value}
              onChange={(e) => onChange(e.target.checked)}
              className="w-4 h-4 accent-blue-500"
            />
            <span className="text-sm text-gray-300">{name}</span>
            {prop.description && <span className="text-xs text-gray-600">{prop.description}</span>}
          </label>
        </div>
      );

    case 'object':
    case 'array':
      // complex types → JSON textarea
      return (
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            <span className="text-gray-300 font-medium">{name}</span>
            <span className="text-gray-600 ml-1">({prop.type})</span>
            {prop.description && <span className="text-gray-600 ml-2">{prop.description}</span>}
          </label>
          <textarea
            value={typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
            onChange={(e) => {
              try {
                onChange(JSON.parse(e.target.value));
              } catch {
                onChange(e.target.value);
              }
            }}
            rows={3}
            placeholder={prop.type === 'array' ? '[\n  "item1"\n]' : '{\n  "key": "value"\n}'}
            className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono resize-none"
          />
        </div>
      );
  }
}

// ─── Execution status types ──────────────────────────────────────────────────

type TestStatus = 'idle' | 'running' | 'success' | 'error';

interface TestResult {
  status: TestStatus;
  output?: Record<string, unknown>;
  error?: string;
  durationMs?: number;
  startedAt?: string;
  completedAt?: string;
  logs: { type: 'info' | 'warning' | 'error'; message: string; timestamp: string }[];
}

// ─── Public: TestTab ─────────────────────────────────────────────────────────

export function TestTab({
  inputSchema,
  outputSchema,
  tools,
  knowledgeEnabled,
}: {
  inputSchema: JsonSchema;
  outputSchema: JsonSchema;
  tools: { name: string; type: string }[];
  knowledgeEnabled: boolean;
}) {
  // Build initial values from defaults or empty
  const buildDefaults = useCallback(() => {
    const defaults: Record<string, unknown> = {};
    for (const [key, prop] of Object.entries(inputSchema.properties)) {
      if (prop.default !== undefined) {
        defaults[key] = prop.default;
      } else {
        switch (prop.type) {
          case 'string': defaults[key] = ''; break;
          case 'number': defaults[key] = ''; break;
          case 'boolean': defaults[key] = false; break;
          case 'array': defaults[key] = []; break;
          case 'object': defaults[key] = {}; break;
        }
      }
    }
    return defaults;
  }, [inputSchema]);

  const [inputValues, setInputValues] = useState<Record<string, unknown>>(buildDefaults);
  const [result, setResult] = useState<TestResult>({ status: 'idle', logs: [] });

  const updateInput = (key: string, val: unknown) => {
    setInputValues((prev) => ({ ...prev, [key]: val }));
  };

  const resetForm = () => {
    setInputValues(buildDefaults());
    setResult({ status: 'idle', logs: [] });
  };

  // ── Simulate execution ────────────────────────────────────────────────────
  const runTest = () => {
    const startedAt = new Date().toISOString();
    const logs: TestResult['logs'] = [];
    setResult({ status: 'running', logs: [{ type: 'info', message: '테스트 실행 시작...', timestamp: startedAt }] });

    // Phase 1: input validation (instant)
    const requiredFields = inputSchema.required || [];
    const missing = requiredFields.filter((f) => {
      const v = inputValues[f];
      return v === undefined || v === null || v === '' || (Array.isArray(v) && v.length === 0);
    });

    if (missing.length > 0) {
      setResult({
        status: 'error',
        error: `필수 필드 누락: ${missing.join(', ')}`,
        startedAt,
        completedAt: new Date().toISOString(),
        logs: [
          ...logs,
          { type: 'error', message: `필수 필드 누락: ${missing.join(', ')}`, timestamp: new Date().toISOString() },
        ],
      });
      return;
    }

    // Phase 2: simulate async processing with staggered logs
    const stages: { delay: number; log: TestResult['logs'][0] }[] = [
      { delay: 200, log: { type: 'info', message: `입력값 검증 완료 (${Object.keys(inputValues).length}개 필드)`, timestamp: '' } },
    ];

    tools.forEach((t) => {
      stages.push({
        delay: stages.length * 300 + 200,
        log: { type: 'info', message: `도구 실행: ${t.name} (${t.type})`, timestamp: '' },
      });
      stages.push({
        delay: stages.length * 300 + 400,
        log: { type: 'info', message: `도구 응답 수신: ${t.name}`, timestamp: '' },
      });
    });

    if (knowledgeEnabled) {
      stages.push({
        delay: stages.length * 300 + 150,
        log: { type: 'info', message: '지식 베이스 검색 중...', timestamp: '' },
      });
      stages.push({
        delay: stages.length * 300 + 350,
        log: { type: 'info', message: '관련 문서 2건 검색 완료', timestamp: '' },
      });
    }

    stages.push({
      delay: stages.length * 300 + 200,
      log: { type: 'info', message: 'LLM 응답 생성 중...', timestamp: '' },
    });

    const totalDelay = stages.length * 300 + 600;

    // Fire off staggered log updates
    let accumulated: TestResult['logs'] = [{ type: 'info', message: '테스트 실행 시작...', timestamp: startedAt }];
    stages.forEach((stage) => {
      setTimeout(() => {
        const ts = new Date().toISOString();
        accumulated = [...accumulated, { ...stage.log, timestamp: ts }];
        setResult((prev) => ({
          ...prev,
          logs: accumulated,
        }));
      }, stage.delay);
    });

    // Final completion
    setTimeout(() => {
      const completedAt = new Date().toISOString();
      const mockOutput = generateMockOutput(outputSchema);
      const finalLogs: TestResult['logs'] = [
        ...accumulated,
        { type: 'info', message: 'LLM 응답 파싱 및 검증 완료', timestamp: completedAt },
        { type: 'info', message: '테스트 실행 완료', timestamp: completedAt },
      ];
      setResult({
        status: 'success',
        output: mockOutput,
        startedAt,
        completedAt,
        durationMs: new Date(completedAt).getTime() - new Date(startedAt).getTime(),
        logs: finalLogs,
      });
    }, totalDelay);
  };

  const hasFields = Object.keys(inputSchema.properties).length > 0;

  return (
    <div className="flex gap-6 h-full">
      {/* ── Left: Input form ─────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-300">테스트 입력값</h3>
          <div className="flex items-center gap-2">
            <button
              onClick={resetForm}
              className="px-3 py-1 text-xs bg-gray-700 text-gray-400 rounded hover:bg-gray-600 hover:text-gray-200 transition-colors"
            >
              초기화
            </button>
            <button
              onClick={runTest}
              disabled={result.status === 'running'}
              className={`px-4 py-1.5 text-sm font-medium rounded transition-colors flex items-center gap-2 ${
                result.status === 'running'
                  ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                  : 'bg-blue-600 text-white hover:bg-blue-700'
              }`}
            >
              {result.status === 'running' ? (
                <>
                  <span className="inline-block w-3 h-3 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
                  실행 중...
                </>
              ) : (
                '▶ 테스트 실행'
              )}
            </button>
          </div>
        </div>

        {hasFields ? (
          <div className="space-y-3 flex-1 overflow-auto">
            {Object.entries(inputSchema.properties).map(([key, prop]) => (
              <div
                key={key}
                className={`p-3 rounded-lg border ${
                  (inputSchema.required || []).includes(key)
                    ? 'border-gray-600 bg-gray-800'
                    : 'border-gray-700 bg-gray-800/60'
                }`}
              >
                {(inputSchema.required || []).includes(key) && (
                  <span className="inline-block text-xs bg-red-900 text-red-300 px-1.5 py-0.5 rounded mb-1.5">
                    필수
                  </span>
                )}
                <TestInputField
                  name={key}
                  prop={prop}
                  value={inputValues[key]}
                  onChange={(val) => updateInput(key, val)}
                />
              </div>
            ))}
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center text-gray-600">
              <p className="text-sm">Input Schema에 필드가 없습니다.</p>
              <p className="text-xs mt-1">Schema 탭에서 입력 필드를 먼저 추가하세요.</p>
            </div>
          </div>
        )}

        {/* Input JSON preview */}
        <div className="mt-4">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-gray-600">입력값 JSON 미리보기</span>
          </div>
          <pre className="bg-gray-900 border border-gray-700 rounded p-2 text-xs text-gray-400 font-mono overflow-auto max-h-24">
            {JSON.stringify(inputValues, null, 2)}
          </pre>
        </div>
      </div>

      {/* ── Right: Execution log + Output ─────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Status badge */}
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-300">실행 결과</h3>
          {result.status !== 'idle' && (
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${
                  result.status === 'running'
                    ? 'bg-yellow-900 text-yellow-300'
                    : result.status === 'success'
                    ? 'bg-green-900 text-green-300'
                    : 'bg-red-900 text-red-300'
                }`}
              >
                {result.status === 'running' && (
                  <span className="inline-block w-2 h-2 bg-yellow-400 rounded-full animate-pulse" />
                )}
                {result.status === 'success' && <span>{'✓'}</span>}
                {result.status === 'error' && <span>{'✕'}</span>}
                {result.status === 'running' ? '실행 중' : result.status === 'success' ? '성공' : '실패'}
              </span>
              {result.durationMs !== undefined && (
                <span className="text-xs text-gray-600">{result.durationMs}ms</span>
              )}
            </div>
          )}
        </div>

        {/* Execution log */}
        <div className="bg-gray-900 border border-gray-700 rounded-lg flex-1 overflow-auto min-h-0 max-h-48">
          {result.logs.length === 0 ? (
            <div className="p-4 text-center text-gray-600 text-sm">실행 로그가 여기에 표시됩니다</div>
          ) : (
            <div className="divide-y divide-gray-800">
              {result.logs.map((log, idx) => (
                <div key={idx} className="flex items-start gap-2 px-3 py-1.5">
                  <span
                    className={`text-xs mt-0.5 shrink-0 ${
                      log.type === 'info' ? 'text-blue-400' : log.type === 'warning' ? 'text-yellow-400' : 'text-red-400'
                    }`}
                  >
                    {log.type === 'info' ? 'ℹ' : log.type === 'warning' ? '⚠' : '✕'}
                  </span>
                  <span className="text-xs text-gray-300 flex-1">{log.message}</span>
                  <span className="text-xs text-gray-700 font-mono shrink-0">
                    {log.timestamp ? new Date(log.timestamp).toLocaleTimeString('ko-KR', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Error message */}
        {result.status === 'error' && result.error && (
          <div className="mt-3 bg-red-900/30 border border-red-800 rounded-lg p-3">
            <p className="text-red-300 text-sm">{result.error}</p>
          </div>
        )}

        {/* Output preview */}
        {result.status === 'success' && result.output && (
          <div className="mt-3">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs text-gray-500 font-medium">출력값 미리보기 (Mock)</span>
              <span className="text-xs text-gray-600 italic">실제 LLM 응답과 다를 수 있음</span>
            </div>
            <pre className="bg-gray-900 border border-green-800 rounded-lg p-3 text-xs text-green-300 font-mono overflow-auto max-h-48">
              {JSON.stringify(result.output, null, 2)}
            </pre>
          </div>
        )}

        {/* Idle state hint */}
        {result.status === 'idle' && (
          <div className="mt-3 flex-1 flex items-center justify-center">
            <div className="text-center text-gray-700">
              <p className="text-sm">왼쪽에서 입력값을 채운 후</p>
              <p className="text-sm">"테스트 실행" 버튼을 클릭하세요</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
