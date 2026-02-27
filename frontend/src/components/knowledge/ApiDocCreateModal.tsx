import { useState, useMemo, useCallback } from 'react';
import { apiDocsApi, knowledgeApi } from '../../services/api';
import { useToast } from '../common/Toast';
import type { KnowledgeDocument } from '../../types';

interface ApiDocCreateModalProps {
  onClose: () => void;
  onCreated: (doc: KnowledgeDocument) => void;
}

interface HeaderRow {
  key: string;
  value: string;
}

const HTTP_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const;

/** Extract {{variable}} placeholders */
function extractVariables(texts: string[]): string[] {
  const vars = new Set<string>();
  for (const text of texts) {
    const matches = text.match(/\{\{([^}]+)\}\}/g) || [];
    for (const m of matches) {
      vars.add(m.replace(/^\{\{|\}\}$/g, '').trim());
    }
  }
  return [...vars];
}

/** Analyze JSON response to generate field table */
function analyzeJsonStructure(data: unknown, prefix = ''): { field: string; type: string; description: string }[] {
  const fields: { field: string; type: string; description: string }[] = [];

  if (Array.isArray(data)) {
    if (data.length > 0) {
      const firstItem = data[0];
      const innerFields = analyzeJsonStructure(firstItem, prefix ? `${prefix}[].` : '[].');
      fields.push(...innerFields);
    }
    return fields;
  }

  if (data && typeof data === 'object') {
    for (const [key, value] of Object.entries(data as Record<string, unknown>)) {
      const fullKey = prefix ? `${prefix}${key}` : key;

      if (Array.isArray(value)) {
        fields.push({ field: fullKey, type: 'array', description: '' });
        if (value.length > 0 && typeof value[0] === 'object' && value[0] !== null) {
          const inner = analyzeJsonStructure(value[0], `${fullKey}[].`);
          fields.push(...inner);
        }
      } else if (value && typeof value === 'object') {
        fields.push({ field: fullKey, type: 'object', description: '' });
        // Only go 2 levels deep
        if (prefix.split('.').length < 3) {
          const inner = analyzeJsonStructure(value, `${fullKey}.`);
          fields.push(...inner);
        }
      } else {
        const type = value === null ? 'null' : typeof value;
        fields.push({ field: fullKey, type, description: '' });
      }
    }
  }

  return fields;
}

/** Generate markdown content from form data + response */
function generateMarkdown(
  description: string,
  variables: { name: string; type: string; required: boolean; description: string }[],
  responseFields: { field: string; type: string; description: string }[],
): string {
  let md = '';

  // Description
  md += `## 설명\n${description || '(설명을 입력하세요)'}\n\n`;

  // REQUEST table
  if (variables.length > 0) {
    md += `## REQUEST\n`;
    md += `| 필드 | 타입 | 필수 | 설명 |\n`;
    md += `|------|------|------|------|\n`;
    for (const v of variables) {
      md += `| ${v.name} | ${v.type} | ${v.required ? 'Y' : 'N'} | ${v.description} |\n`;
    }
    md += '\n';
  }

  // RESPONSE table
  if (responseFields.length > 0) {
    md += `## RESPONSE\n`;
    md += `| 필드 | 타입 | 설명 |\n`;
    md += `|------|------|------|\n`;
    for (const f of responseFields) {
      md += `| ${f.field} | ${f.type} | ${f.description} |\n`;
    }
    md += '\n';
  }

  return md;
}

export function ApiDocCreateModal({ onClose, onCreated }: ApiDocCreateModalProps) {
  const { toast } = useToast();

  // Step state
  const [step, setStep] = useState<1 | 2>(1);

  // Step 1: API test form
  const [method, setMethod] = useState<string>('GET');
  const [url, setUrl] = useState('');
  const [headers, setHeaders] = useState<HeaderRow[]>([
    { key: 'Accept', value: 'application/json' },
  ]);
  const [bodyTemplate, setBodyTemplate] = useState('');
  const [variableValues, setVariableValues] = useState<Record<string, string>>({});
  const [testing, setTesting] = useState(false);
  const [testResponse, setTestResponse] = useState<{ success: boolean; status?: number; data?: unknown; error?: string; time?: number } | null>(null);

  // Step 2: Document form
  const [docTitle, setDocTitle] = useState('');
  const [docTags, setDocTags] = useState('');
  const [docSource, setDocSource] = useState('API문서');
  const [docDescription, setDocDescription] = useState('');
  const [variableMeta, setVariableMeta] = useState<{ name: string; type: string; required: boolean; description: string }[]>([]);
  const [responseFields, setResponseFields] = useState<{ field: string; type: string; description: string }[]>([]);
  const [saving, setSaving] = useState(false);

  // Auto-detect variables from all template strings
  const detectedVars = useMemo(() => {
    const allTexts = [
      url,
      ...headers.map(h => `${h.key}: ${h.value}`),
      bodyTemplate,
    ];
    return extractVariables(allTexts);
  }, [url, headers, bodyTemplate]);

  // Method badge colors
  const methodColor = (m: string) => {
    const colors: Record<string, string> = {
      GET: 'bg-green-600 text-green-100',
      POST: 'bg-blue-600 text-blue-100',
      PUT: 'bg-amber-600 text-amber-100',
      PATCH: 'bg-orange-600 text-orange-100',
      DELETE: 'bg-red-600 text-red-100',
    };
    return colors[m] || 'bg-gray-600 text-gray-100';
  };

  // Header add/remove
  const addHeader = () => setHeaders(prev => [...prev, { key: '', value: '' }]);
  const removeHeader = (index: number) => setHeaders(prev => prev.filter((_, i) => i !== index));
  const updateHeader = (index: number, field: 'key' | 'value', val: string) => {
    setHeaders(prev => prev.map((h, i) => i === index ? { ...h, [field]: val } : h));
  };

  // Test API call
  const handleTest = useCallback(async () => {
    if (!url.trim()) {
      toast.warning('URL을 입력해주세요.');
      return;
    }
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      toast.warning('URL은 http:// 또는 https://로 시작해야 합니다.');
      return;
    }

    setTesting(true);
    setTestResponse(null);

    const headersObj: Record<string, string> = {};
    for (const h of headers) {
      if (h.key.trim()) headersObj[h.key.trim()] = h.value;
    }

    try {
      const result = await apiDocsApi.testRawApi({
        method,
        url,
        headers: headersObj,
        bodyTemplate: bodyTemplate || undefined,
        inputData: variableValues,
      });

      if (result.success) {
        const responseData = result.output;
        const statusCode = typeof responseData === 'object' && responseData !== null && 'status' in responseData
          ? (responseData as Record<string, unknown>).status as number | undefined
          : undefined;
        setTestResponse({
          success: true,
          status: statusCode,
          data: responseData,
          time: result.executionTimeMs,
        });
      } else {
        setTestResponse({
          success: false,
          error: result.error || '알 수 없는 오류',
          time: result.executionTimeMs,
        });
      }
    } catch (err) {
      setTestResponse({
        success: false,
        error: err instanceof Error ? err.message : '요청 실패',
      });
    } finally {
      setTesting(false);
    }
  }, [method, url, headers, bodyTemplate, variableValues, toast]);

  // Transition to Step 2
  const handleProceedToStep2 = useCallback(() => {
    if (!testResponse?.success) {
      toast.warning('먼저 API를 성공적으로 호출하세요.');
      return;
    }

    // Auto-generate title from URL
    try {
      const urlObj = new URL(url.replace(/\{\{[^}]+\}\}/g, 'x'));
      const pathParts = urlObj.pathname.split('/').filter(Boolean);
      const suggestedTitle = pathParts.slice(-2).join(' ') + ' API';
      setDocTitle(suggestedTitle);
    } catch {
      setDocTitle('새 API 문서');
    }

    // Auto-generate variable metadata
    setVariableMeta(detectedVars.map(name => ({
      name,
      type: 'string',
      required: true,
      description: '',
    })));

    // Auto-analyze response structure
    if (testResponse.data) {
      const fields = analyzeJsonStructure(testResponse.data);
      setResponseFields(fields.slice(0, 30)); // limit to 30 fields
    }

    setStep(2);
  }, [testResponse, url, detectedVars, toast]);

  // Save document
  const handleSave = useCallback(async () => {
    if (!docTitle.trim()) {
      toast.warning('제목을 입력해주세요.');
      return;
    }

    setSaving(true);

    const headersObj: Record<string, string> = {};
    for (const h of headers) {
      if (h.key.trim()) headersObj[h.key.trim()] = h.value;
    }

    // Build YAML frontmatter manually (it will be part of the content)
    const tags = docTags.split(',').map(t => t.trim()).filter(Boolean);
    const tagsYaml = tags.length > 0 ? `[${tags.join(', ')}]` : '[]';

    const headersYaml = Object.entries(headersObj)
      .map(([k, v]) => `    ${k}: ${v.includes("'") ? `"${v}"` : `'${v}'`}`)
      .join('\n');

    const bodyLine = bodyTemplate ? `\n  bodyTemplate: |\n    ${bodyTemplate.split('\n').join('\n    ')}` : '';

    const frontmatter = [
      '---',
      `title: ${docTitle.trim()}`,
      `category: 도구-API`,
      `tags: ${tagsYaml}`,
      `source: ${docSource || 'API문서'}`,
      `created: '${new Date().toISOString().split('T')[0]}'`,
      `api:`,
      `  method: ${method}`,
      `  url: ${url}`,
      headersYaml ? `  headers:\n${headersYaml}` : '',
      bodyLine,
      '---',
    ].filter(Boolean).join('\n');

    const markdownBody = generateMarkdown(docDescription, variableMeta, responseFields);
    const fullContent = markdownBody;

    try {
      const created = await knowledgeApi.create({
        title: docTitle.trim(),
        content: fullContent,
        category: '도구-API',
        tags,
        source: docSource || 'API문서',
      });

      // The backend creates the file with frontmatter from the API fields
      // But we need to update the file to include our custom api: metadata
      // Do a PUT update with the full content including frontmatter hint
      try {
        await knowledgeApi.update(created.id, {
          title: docTitle.trim(),
          content: `${frontmatter}\n\n${markdownBody}`,
          category: '도구-API',
          tags,
        });
      } catch {
        // If update fails, the base document was still created
      }

      onCreated(created);
      toast.success('API 문서가 생성되었습니다.');
      onClose();
    } catch (err) {
      const detail = err instanceof Error ? err.message : '';
      toast.error(`문서 생성 실패${detail ? `: ${detail}` : ''}`);
    } finally {
      setSaving(false);
    }
  }, [docTitle, docTags, docSource, docDescription, method, url, headers, bodyTemplate, variableMeta, responseFields, onCreated, onClose, toast]);

  // Suppress unused variable warning
  void removeHeader;

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-2">
      <div className="bg-gray-800 rounded-xl w-full max-w-5xl max-h-[92vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-gray-700 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">&#x1F310;</span>
            <div>
              <h2 className="text-lg font-bold text-white">API 문서 추가</h2>
              <div className="flex items-center gap-2 mt-1">
                <div className={`px-2 py-0.5 text-xs rounded-full ${step === 1 ? 'bg-cyan-600 text-white' : 'bg-gray-700 text-gray-400'}`}>
                  1. API 테스트
                </div>
                <span className="text-gray-600">{'\u2192'}</span>
                <div className={`px-2 py-0.5 text-xs rounded-full ${step === 2 ? 'bg-cyan-600 text-white' : 'bg-gray-700 text-gray-400'}`}>
                  2. 문서 작성
                </div>
              </div>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-2xl">&times;</button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto">
          {step === 1 && (
            <div className="flex h-full">
              {/* Left: Request form */}
              <div className="flex-1 p-4 space-y-4 overflow-auto border-r border-gray-700">
                {/* Method + URL */}
                <div>
                  <label className="block text-xs text-gray-400 mb-1">요청</label>
                  <div className="flex gap-2">
                    <select
                      value={method}
                      onChange={(e) => setMethod(e.target.value)}
                      className={`px-3 py-2 rounded-lg text-sm font-bold ${methodColor(method)} border-none focus:outline-none cursor-pointer`}
                    >
                      {HTTP_METHODS.map(m => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                    <input
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      placeholder="https://api.example.com/v1/{{resource}}/{{id}}"
                      className="flex-1 bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 font-mono placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    />
                  </div>
                  {url && !url.startsWith('http') && (
                    <p className="text-red-400 text-[10px] mt-1">URL은 https:// 또는 http://로 시작해야 합니다</p>
                  )}
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
                        <input
                          value={h.key}
                          onChange={(e) => updateHeader(i, 'key', e.target.value)}
                          placeholder="Header-Name"
                          className="w-1/3 bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 font-mono focus:outline-none focus:ring-1 focus:ring-cyan-500"
                        />
                        <input
                          value={h.value}
                          onChange={(e) => updateHeader(i, 'value', e.target.value)}
                          placeholder="value or {{variable}}"
                          className="flex-1 bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 font-mono focus:outline-none focus:ring-1 focus:ring-cyan-500"
                        />
                        <button
                          onClick={() => setHeaders(prev => prev.filter((_, idx) => idx !== i))}
                          className="text-gray-500 hover:text-red-400 text-xs px-1"
                        >{'\u2715'}</button>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Body (for POST/PUT/PATCH) */}
                {['POST', 'PUT', 'PATCH'].includes(method) && (
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">바디 템플릿</label>
                    <textarea
                      value={bodyTemplate}
                      onChange={(e) => setBodyTemplate(e.target.value)}
                      rows={5}
                      placeholder={'{\n  "field": "{{variable}}"\n}'}
                      className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-xs text-gray-200 font-mono resize-y focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    />
                  </div>
                )}

                {/* Detected variables */}
                {detectedVars.length > 0 && (
                  <div>
                    <label className="block text-xs text-gray-400 mb-1.5">변수 값 (테스트용)</label>
                    <div className="space-y-1.5">
                      {detectedVars.map(varName => (
                        <div key={varName} className="flex items-center gap-2">
                          <span className="text-xs text-cyan-300 font-mono w-28 truncate flex-shrink-0">{`{{${varName}}}`}</span>
                          <input
                            value={variableValues[varName] || ''}
                            onChange={(e) => setVariableValues(prev => ({ ...prev, [varName]: e.target.value }))}
                            placeholder={`${varName} 값 입력`}
                            className="flex-1 bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Test button */}
                <button
                  onClick={handleTest}
                  disabled={testing || !url.trim()}
                  className="w-full py-2.5 bg-cyan-600 text-white rounded-lg hover:bg-cyan-700 transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {testing ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      호출 중...
                    </>
                  ) : (
                    <>{'\uD83D\uDE80'} API 호출</>
                  )}
                </button>
              </div>

              {/* Right: Response */}
              <div className="w-[45%] p-4 overflow-auto">
                <label className="block text-xs text-gray-400 mb-2">응답</label>
                {testResponse ? (
                  <div className="space-y-3">
                    {/* Status badge */}
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-1 text-xs rounded font-bold ${testResponse.success ? 'bg-green-600/40 text-green-300' : 'bg-red-600/40 text-red-300'}`}>
                        {testResponse.success ? 'SUCCESS' : 'FAILED'}
                      </span>
                      {testResponse.time && (
                        <span className="text-gray-500 text-[10px]">{Math.round(testResponse.time)}ms</span>
                      )}
                    </div>

                    {/* Error */}
                    {testResponse.error && (
                      <div className="bg-red-900/30 border border-red-700/50 rounded-lg p-3 text-red-300 text-xs">
                        {testResponse.error}
                      </div>
                    )}

                    {/* Response body */}
                    {testResponse.data && (
                      <pre className="bg-gray-900 border border-gray-700 rounded-lg p-3 text-xs text-gray-300 font-mono overflow-auto max-h-[50vh] whitespace-pre-wrap">
                        {typeof testResponse.data === 'string'
                          ? testResponse.data
                          : JSON.stringify(testResponse.data, null, 2)}
                      </pre>
                    )}
                  </div>
                ) : (
                  <div className="bg-gray-900 rounded-lg p-8 text-center">
                    <div className="text-3xl mb-2 opacity-30">{'\uD83D\uDCE1'}</div>
                    <p className="text-gray-500 text-sm">API를 호출하면 응답이 여기에 표시됩니다</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="p-4 space-y-4 overflow-auto">
              {/* Basic info */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">제목 <span className="text-red-400">*</span></label>
                  <input
                    value={docTitle}
                    onChange={(e) => setDocTitle(e.target.value)}
                    className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">출처</label>
                  <input
                    value={docSource}
                    onChange={(e) => setDocSource(e.target.value)}
                    className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">태그 (쉼표 구분)</label>
                <input
                  value={docTags}
                  onChange={(e) => setDocTags(e.target.value)}
                  placeholder="예: GitHub, 커밋이력"
                  className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                />
              </div>

              {/* API summary (read-only) */}
              <div className="bg-gray-900 rounded-lg p-3">
                <div className="text-xs text-gray-500 mb-1">API 요약</div>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 text-[10px] rounded font-bold ${methodColor(method)}`}>{method}</span>
                  <span className="text-gray-300 text-xs font-mono truncate">{url}</span>
                </div>
              </div>

              {/* Description */}
              <div>
                <label className="block text-xs text-gray-400 mb-1">설명</label>
                <textarea
                  value={docDescription}
                  onChange={(e) => setDocDescription(e.target.value)}
                  rows={3}
                  placeholder="이 API가 무엇을 하는지 설명하세요..."
                  className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 resize-y focus:outline-none focus:ring-1 focus:ring-cyan-500"
                />
              </div>

              {/* REQUEST fields */}
              {variableMeta.length > 0 && (
                <div>
                  <label className="block text-xs text-gray-400 mb-1.5">REQUEST 필드</label>
                  <div className="bg-gray-900 rounded-lg overflow-hidden">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-gray-700">
                          <th className="text-left px-3 py-2 text-gray-400 font-medium">필드</th>
                          <th className="text-left px-3 py-2 text-gray-400 font-medium w-20">타입</th>
                          <th className="text-center px-3 py-2 text-gray-400 font-medium w-12">필수</th>
                          <th className="text-left px-3 py-2 text-gray-400 font-medium">설명</th>
                        </tr>
                      </thead>
                      <tbody>
                        {variableMeta.map((v, i) => (
                          <tr key={v.name} className="border-b border-gray-800">
                            <td className="px-3 py-1.5 text-cyan-300 font-mono">{v.name}</td>
                            <td className="px-3 py-1.5">
                              <select
                                value={v.type}
                                onChange={(e) => setVariableMeta(prev => prev.map((item, idx) => idx === i ? { ...item, type: e.target.value } : item))}
                                className="bg-gray-800 border border-gray-700 rounded px-1 py-0.5 text-gray-300 w-full"
                              >
                                <option value="string">string</option>
                                <option value="number">number</option>
                                <option value="boolean">boolean</option>
                              </select>
                            </td>
                            <td className="px-3 py-1.5 text-center">
                              <input
                                type="checkbox"
                                checked={v.required}
                                onChange={(e) => setVariableMeta(prev => prev.map((item, idx) => idx === i ? { ...item, required: e.target.checked } : item))}
                                className="accent-cyan-500"
                              />
                            </td>
                            <td className="px-3 py-1.5">
                              <input
                                value={v.description}
                                onChange={(e) => setVariableMeta(prev => prev.map((item, idx) => idx === i ? { ...item, description: e.target.value } : item))}
                                placeholder="설명..."
                                className="bg-transparent border-b border-gray-700 w-full text-gray-300 focus:outline-none focus:border-cyan-500 py-0.5"
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* RESPONSE fields */}
              {responseFields.length > 0 && (
                <div>
                  <label className="block text-xs text-gray-400 mb-1.5">RESPONSE 필드 (자동 감지)</label>
                  <div className="bg-gray-900 rounded-lg overflow-hidden max-h-60 overflow-y-auto">
                    <table className="w-full text-xs">
                      <thead className="sticky top-0 bg-gray-900">
                        <tr className="border-b border-gray-700">
                          <th className="text-left px-3 py-2 text-gray-400 font-medium">필드</th>
                          <th className="text-left px-3 py-2 text-gray-400 font-medium w-20">타입</th>
                          <th className="text-left px-3 py-2 text-gray-400 font-medium">설명</th>
                        </tr>
                      </thead>
                      <tbody>
                        {responseFields.map((f, i) => (
                          <tr key={`${f.field}-${i}`} className="border-b border-gray-800">
                            <td className="px-3 py-1.5 text-green-300 font-mono">{f.field}</td>
                            <td className="px-3 py-1.5 text-gray-400">{f.type}</td>
                            <td className="px-3 py-1.5">
                              <input
                                value={f.description}
                                onChange={(e) => setResponseFields(prev => prev.map((item, idx) => idx === i ? { ...item, description: e.target.value } : item))}
                                placeholder="설명..."
                                className="bg-transparent border-b border-gray-700 w-full text-gray-300 focus:outline-none focus:border-cyan-500 py-0.5"
                              />
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
              <button
                onClick={() => setStep(1)}
                className="px-4 py-2 text-gray-400 hover:text-white text-sm"
              >
                {'\u2190'} API 테스트로 돌아가기
              </button>
            )}
          </div>
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 text-sm"
            >
              취소
            </button>
            {step === 1 ? (
              <button
                onClick={handleProceedToStep2}
                disabled={!testResponse?.success}
                className="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-700 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                다음: 문서 작성 {'\u2192'}
              </button>
            ) : (
              <button
                onClick={handleSave}
                disabled={saving || !docTitle.trim()}
                className="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-700 text-sm disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {saving ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    저장 중...
                  </>
                ) : (
                  '문서 저장'
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
