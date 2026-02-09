import { useRef, useState, useMemo } from 'react';
import type { JsonSchema, ToolDefinition } from '../../types';

// ============================================
// 프롬프트 변수 타입
// ============================================

interface PromptVariable {
  name: string;
  template: string;
  description?: string;
  type?: string;
  category: 'input' | 'tool' | 'knowledge';
}

// ============================================
// 출력 규격 강제 설정 타입
// ============================================

export interface OutputEnforcementConfig {
  enabled: boolean;
  includeSchemaInPrompt: boolean;
  exampleOutput?: string;
  validationEnabled: boolean;
  retryOnFailure: boolean;
  maxRetries: number;
}

export const defaultOutputEnforcement: OutputEnforcementConfig = {
  enabled: true,
  includeSchemaInPrompt: true,
  exampleOutput: '',
  validationEnabled: true,
  retryOnFailure: true,
  maxRetries: 2,
};

// ============================================
// 변수 팔레트 컴포넌트
// ============================================

function VariablePalette({
  variables,
  onInsert,
  category,
  title,
  icon,
  emptyMessage,
  accentColor,
}: {
  variables: PromptVariable[];
  onInsert: (template: string) => void;
  category: string;
  title: string;
  icon: string;
  emptyMessage: string;
  accentColor: string;
}) {
  const [expanded, setExpanded] = useState(true);
  const filtered = variables.filter(v => v.category === category);

  return (
    <div className="border border-gray-700 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-3 py-2 flex items-center justify-between bg-gray-800 hover:bg-gray-750 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span>{icon}</span>
          <span className={`text-sm font-medium ${accentColor}`}>{title}</span>
          <span className="text-xs text-gray-500">({filtered.length})</span>
        </div>
        <span className="text-gray-500 text-xs">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="p-2 bg-gray-900/50 space-y-1 max-h-40 overflow-y-auto">
          {filtered.length === 0 ? (
            <p className="text-xs text-gray-600 italic px-2 py-2">{emptyMessage}</p>
          ) : (
            filtered.map((v, idx) => (
              <button
                key={idx}
                onClick={() => onInsert(v.template)}
                className="w-full text-left px-2 py-1.5 rounded hover:bg-gray-800 transition-colors group"
                title={`클릭하여 삽입: ${v.template}`}
              >
                <div className="flex items-center justify-between">
                  <code className="text-xs text-blue-400 font-mono">{v.template}</code>
                  <span className="text-xs text-gray-600 opacity-0 group-hover:opacity-100 transition-opacity">
                    + 삽입
                  </span>
                </div>
                {v.description && (
                  <p className="text-xs text-gray-500 mt-0.5 truncate">{v.description}</p>
                )}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ============================================
// 스키마를 읽기 쉬운 형식으로 변환
// ============================================

function schemaToReadableFormat(schema: JsonSchema, indent = 0): string {
  const spaces = '  '.repeat(indent);
  const lines: string[] = ['{'];

  for (const [key, prop] of Object.entries(schema.properties)) {
    const required = schema.required?.includes(key) ? '' : '?';
    const desc = prop.description ? ` // ${prop.description}` : '';

    if (prop.type === 'object' && prop.properties) {
      lines.push(`${spaces}  "${key}"${required}: ${schemaToReadableFormat(
        { type: 'object', properties: prop.properties, required: prop.required },
        indent + 1
      )}${desc}`);
    } else if (prop.type === 'array' && prop.items) {
      if (prop.items.type === 'object' && prop.items.properties) {
        lines.push(`${spaces}  "${key}"${required}: [${schemaToReadableFormat(
          { type: 'object', properties: prop.items.properties, required: prop.items.required },
          indent + 1
        )}, ...]${desc}`);
      } else {
        lines.push(`${spaces}  "${key}"${required}: ${prop.items.type}[]${desc}`);
      }
    } else {
      const enumStr = prop.enum ? ` (${prop.enum.join(' | ')})` : '';
      lines.push(`${spaces}  "${key}"${required}: ${prop.type}${enumStr}${desc}`);
    }
  }

  lines.push(`${spaces}}`);
  return lines.join('\n');
}

// ============================================
// 스키마에서 예시 JSON 생성
// ============================================

function generateExampleFromSchema(schema: JsonSchema): Record<string, unknown> {
  const result: Record<string, unknown> = {};

  for (const [key, prop] of Object.entries(schema.properties)) {
    if (prop.type === 'string') {
      result[key] = prop.enum?.[0] || prop.default || `예시_${key}`;
    } else if (prop.type === 'number') {
      result[key] = prop.default ?? 0;
    } else if (prop.type === 'boolean') {
      result[key] = prop.default ?? true;
    } else if (prop.type === 'array') {
      if (prop.items?.type === 'object' && prop.items.properties) {
        result[key] = [generateExampleFromSchema({
          type: 'object',
          properties: prop.items.properties,
          required: prop.items.required,
        })];
      } else {
        result[key] = [];
      }
    } else if (prop.type === 'object' && prop.properties) {
      result[key] = generateExampleFromSchema({
        type: 'object',
        properties: prop.properties,
        required: prop.required,
      });
    }
  }

  return result;
}

// ============================================
// 스키마에서 변수 추출
// ============================================

function extractInputVariables(schema: JsonSchema, prefix = 'input'): PromptVariable[] {
  const variables: PromptVariable[] = [];

  for (const [key, prop] of Object.entries(schema.properties)) {
    const fullPath = `${prefix}.${key}`;
    const template = `{{${fullPath}}}`;

    variables.push({
      name: fullPath,
      template,
      description: prop.description,
      type: prop.type,
      category: 'input',
    });

    if (prop.type === 'object' && prop.properties) {
      const nested = extractInputVariables(
        { type: 'object', properties: prop.properties, required: prop.required },
        fullPath
      );
      variables.push(...nested);
    }

    if (prop.type === 'array' && prop.items?.type === 'object' && prop.items.properties) {
      variables.push({
        name: `#each ${fullPath}`,
        template: `{{#each ${fullPath}}}...{{/each}}`,
        description: `${prop.description || key} 반복`,
        type: 'loop',
        category: 'input',
      });
    }
  }

  return variables;
}

function extractToolVariables(tools: ToolDefinition[]): PromptVariable[] {
  return tools.map(tool => ({
    name: `toolResults.${tool.id}`,
    template: `{{toolResults.${tool.id}}}`,
    description: `${tool.name} 실행 결과`,
    type: tool.type,
    category: 'tool' as const,
  }));
}

// ============================================
// 프롬프트 에디터 Props
// ============================================

interface PromptEditorProps {
  systemPrompt: string;
  userPromptTemplate: string;
  onSystemPromptChange: (value: string) => void;
  onUserPromptTemplateChange: (value: string) => void;

  inputSchema: JsonSchema;
  outputSchema: JsonSchema;
  linkedTools: ToolDefinition[];
  knowledgeEnabled: boolean;

  model: string;
  temperature: number;
  maxTokens: number;
  onModelChange: (value: string) => void;
  onTemperatureChange: (value: number) => void;
  onMaxTokensChange: (value: number) => void;

  // 출력 규격 강제 설정
  outputEnforcement: OutputEnforcementConfig;
  onOutputEnforcementChange: (config: OutputEnforcementConfig) => void;
}

// ============================================
// 메인 컴포넌트
// ============================================

export function PromptEditor({
  systemPrompt,
  userPromptTemplate,
  onSystemPromptChange,
  onUserPromptTemplateChange,
  inputSchema,
  outputSchema,
  linkedTools,
  knowledgeEnabled,
  model,
  temperature,
  maxTokens,
  onModelChange,
  onTemperatureChange,
  onMaxTokensChange,
  outputEnforcement,
  onOutputEnforcementChange,
}: PromptEditorProps) {
  const userPromptRef = useRef<HTMLTextAreaElement>(null);
  const systemPromptRef = useRef<HTMLTextAreaElement>(null);
  const [activeField, setActiveField] = useState<'system' | 'user'>('user');
  const [showEnforcement, setShowEnforcement] = useState(outputEnforcement.enabled);

  // 변수 목록 생성
  const inputVariables = extractInputVariables(inputSchema);
  const toolVariables = extractToolVariables(linkedTools);
  const knowledgeVariables: PromptVariable[] = knowledgeEnabled
    ? [{ name: 'knowledge', template: '{{knowledge}}', description: '지식 베이스 검색 결과', type: 'string', category: 'knowledge' }]
    : [];

  const allVariables = [...inputVariables, ...toolVariables, ...knowledgeVariables];

  // 출력 스키마 미리보기
  const schemaPreview = useMemo(() => schemaToReadableFormat(outputSchema), [outputSchema]);
  const generatedExample = useMemo(() => JSON.stringify(generateExampleFromSchema(outputSchema), null, 2), [outputSchema]);

  // 변수 삽입
  const insertVariable = (template: string) => {
    const ref = activeField === 'user' ? userPromptRef : systemPromptRef;
    const setter = activeField === 'user' ? onUserPromptTemplateChange : onSystemPromptChange;
    const currentValue = activeField === 'user' ? userPromptTemplate : systemPrompt;

    if (ref.current) {
      const start = ref.current.selectionStart;
      const end = ref.current.selectionEnd;
      const newValue = currentValue.substring(0, start) + template + currentValue.substring(end);
      setter(newValue);
      setTimeout(() => {
        if (ref.current) {
          ref.current.focus();
          ref.current.selectionStart = ref.current.selectionEnd = start + template.length;
        }
      }, 0);
    } else {
      setter(currentValue + template);
    }
  };

  const updateEnforcement = (updates: Partial<OutputEnforcementConfig>) => {
    onOutputEnforcementChange({ ...outputEnforcement, ...updates });
  };

  return (
    <div className="flex gap-4 h-full">
      {/* 왼쪽: 프롬프트 편집 영역 */}
      <div className="flex-1 space-y-4 min-w-0 overflow-y-auto">
        {/* LLM 설정 */}
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-2">LLM 모델</label>
            <select
              value={model}
              onChange={(e) => onModelChange(e.target.value)}
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-4 py-2 text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="gpt-4o">GPT-4o</option>
              <option value="gpt-4o-mini">GPT-4o-mini</option>
              <option value="claude-3-opus">Claude 3 Opus</option>
              <option value="claude-3-sonnet">Claude 3 Sonnet</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Temperature</label>
            <input
              type="number"
              value={temperature}
              onChange={(e) => onTemperatureChange(Number(e.target.value))}
              min={0}
              max={2}
              step={0.1}
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-4 py-2 text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Max Tokens</label>
            <input
              type="number"
              value={maxTokens}
              onChange={(e) => onMaxTokensChange(Number(e.target.value))}
              min={100}
              max={8000}
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-4 py-2 text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
        </div>

        {/* 시스템 프롬프트 */}
        <div>
          <div className="flex justify-between items-center mb-2">
            <label className="block text-sm text-gray-400">
              시스템 프롬프트
              {activeField === 'system' && <span className="ml-2 text-xs text-blue-400">(편집 중)</span>}
            </label>
            {systemPrompt.length > 500 && (
              <span className={`text-xs ${systemPrompt.length > 900 ? 'text-red-400' : systemPrompt.length > 750 ? 'text-yellow-400' : 'text-gray-500'}`}>
                {systemPrompt.length}자
              </span>
            )}
          </div>
          <textarea
            ref={systemPromptRef}
            value={systemPrompt}
            onChange={(e) => onSystemPromptChange(e.target.value)}
            onFocus={() => setActiveField('system')}
            placeholder="AI의 역할과 규칙을 정의합니다..."
            rows={4}
            className={`w-full bg-gray-900 border rounded-lg px-4 py-3 text-gray-200 font-mono text-sm focus:outline-none resize-none transition-colors ${
              activeField === 'system' ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-600'
            }`}
          />
        </div>

        {/* 사용자 프롬프트 템플릿 */}
        <div>
          <label className="block text-sm text-gray-400 mb-2">
            사용자 프롬프트 템플릿
            {activeField === 'user' && <span className="ml-2 text-xs text-blue-400">(편집 중)</span>}
          </label>
          <textarea
            ref={userPromptRef}
            value={userPromptTemplate}
            onChange={(e) => onUserPromptTemplateChange(e.target.value)}
            onFocus={() => setActiveField('user')}
            placeholder="실행 시 전달될 프롬프트 템플릿..."
            rows={8}
            className={`w-full bg-gray-900 border rounded-lg px-4 py-3 text-gray-200 font-mono text-sm focus:outline-none resize-none transition-colors ${
              activeField === 'user' ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-600'
            }`}
          />
        </div>

        {/* 출력 규격 강제 섹션 */}
        <div className="border border-gray-700 rounded-lg overflow-hidden">
          <button
            onClick={() => setShowEnforcement(!showEnforcement)}
            className="w-full px-4 py-3 flex items-center justify-between bg-gray-800 hover:bg-gray-750 transition-colors"
          >
            <div className="flex items-center gap-3">
              <span className="text-lg">🎯</span>
              <span className="text-sm font-medium text-orange-400">출력 규격 강제</span>
              {outputEnforcement.enabled && (
                <span className="px-2 py-0.5 text-xs bg-orange-900/50 text-orange-300 rounded">활성</span>
              )}
            </div>
            <span className="text-gray-500 text-xs">{showEnforcement ? '▲' : '▼'}</span>
          </button>

          {showEnforcement && (
            <div className="p-4 bg-gray-900/50 space-y-4">
              {/* 활성화 토글 */}
              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="enforcement-enabled"
                  checked={outputEnforcement.enabled}
                  onChange={(e) => updateEnforcement({ enabled: e.target.checked })}
                  className="w-4 h-4 rounded accent-orange-500"
                />
                <label htmlFor="enforcement-enabled" className="text-sm text-white">
                  출력 규격 강제 활성화
                </label>
              </div>

              {outputEnforcement.enabled && (
                <>
                  {/* 안내 */}
                  <div className="bg-gray-800 rounded-lg p-3 border-l-4 border-orange-500">
                    <p className="text-xs text-gray-400">
                      LLM이 지정된 <strong className="text-orange-300">Output Schema</strong>를 정확히 따르도록 강제합니다.
                      스키마와 예시를 프롬프트에 자동 삽입하고, 출력을 검증합니다.
                    </p>
                  </div>

                  {/* 옵션들 */}
                  <div className="grid grid-cols-2 gap-4">
                    <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={outputEnforcement.includeSchemaInPrompt}
                        onChange={(e) => updateEnforcement({ includeSchemaInPrompt: e.target.checked })}
                        className="w-4 h-4 rounded accent-orange-500"
                      />
                      스키마를 프롬프트에 삽입
                    </label>
                    <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={outputEnforcement.validationEnabled}
                        onChange={(e) => updateEnforcement({ validationEnabled: e.target.checked })}
                        className="w-4 h-4 rounded accent-orange-500"
                      />
                      출력 검증 활성화
                    </label>
                    <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={outputEnforcement.retryOnFailure}
                        onChange={(e) => updateEnforcement({ retryOnFailure: e.target.checked })}
                        className="w-4 h-4 rounded accent-orange-500"
                      />
                      검증 실패 시 재시도
                    </label>
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-gray-400">최대 재시도:</span>
                      <input
                        type="number"
                        value={outputEnforcement.maxRetries}
                        onChange={(e) => updateEnforcement({ maxRetries: Number(e.target.value) })}
                        min={1}
                        max={5}
                        disabled={!outputEnforcement.retryOnFailure}
                        className="w-16 bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200 disabled:opacity-50"
                      />
                      <span className="text-sm text-gray-500">회</span>
                    </div>
                  </div>

                  {/* Output Schema 미리보기 */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <label className="text-sm text-gray-400">Output Schema (자동 삽입됨)</label>
                      <button
                        onClick={() => {
                          const schemaText = `\n\n[출력 형식]\n다음 JSON 스키마를 정확히 따르세요:\n\`\`\`\n${schemaPreview}\n\`\`\``;
                          onUserPromptTemplateChange(userPromptTemplate + schemaText);
                        }}
                        className="text-xs text-orange-400 hover:text-orange-300"
                      >
                        수동 삽입
                      </button>
                    </div>
                    <pre className="bg-gray-800 border border-gray-700 rounded-lg p-3 text-xs text-gray-300 font-mono overflow-x-auto max-h-32">
                      {schemaPreview}
                    </pre>
                  </div>

                  {/* 예시 출력 */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <label className="text-sm text-gray-400">예시 출력 (Few-shot)</label>
                      <div className="flex gap-2">
                        <button
                          onClick={() => updateEnforcement({ exampleOutput: generatedExample })}
                          className="text-xs text-blue-400 hover:text-blue-300"
                        >
                          자동 생성
                        </button>
                        <button
                          onClick={() => {
                            const exampleText = `\n\n[출력 예시]\n\`\`\`json\n${outputEnforcement.exampleOutput || generatedExample}\n\`\`\``;
                            onUserPromptTemplateChange(userPromptTemplate + exampleText);
                          }}
                          className="text-xs text-orange-400 hover:text-orange-300"
                        >
                          프롬프트에 삽입
                        </button>
                      </div>
                    </div>
                    <textarea
                      value={outputEnforcement.exampleOutput || ''}
                      onChange={(e) => updateEnforcement({ exampleOutput: e.target.value })}
                      placeholder={generatedExample}
                      rows={6}
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg p-3 text-xs text-gray-300 font-mono resize-none focus:outline-none focus:ring-1 focus:ring-orange-500"
                    />
                  </div>

                  {/* 자동 삽입 미리보기 */}
                  {outputEnforcement.includeSchemaInPrompt && (
                    <div className="bg-orange-900/20 border border-orange-800 rounded-lg p-3">
                      <p className="text-xs text-orange-300 mb-2">✨ 실행 시 프롬프트 끝에 자동 추가됩니다:</p>
                      <pre className="text-xs text-gray-400 font-mono whitespace-pre-wrap">
{`[출력 형식]
다음 JSON 스키마를 정확히 따라 응답하세요. 다른 형식의 응답은 허용되지 않습니다.
${schemaPreview}

반드시 유효한 JSON만 출력하세요. 설명이나 주석을 추가하지 마세요.`}
                      </pre>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 오른쪽: 변수 팔레트 */}
      <div className="w-64 shrink-0 space-y-3 overflow-y-auto">
        <div className="bg-gray-800 rounded-lg p-3 border border-gray-700">
          <h3 className="text-sm font-medium text-white mb-1 flex items-center gap-2">
            <span>🎯</span> 사용 가능한 변수
          </h3>
          <p className="text-xs text-gray-500">클릭하여 삽입</p>
        </div>

        <VariablePalette
          variables={allVariables}
          onInsert={insertVariable}
          category="input"
          title="INPUT 변수"
          icon="📥"
          emptyMessage="Input Schema에 필드 추가 필요"
          accentColor="text-green-400"
        />

        <VariablePalette
          variables={allVariables}
          onInsert={insertVariable}
          category="tool"
          title="도구 결과"
          icon="🔧"
          emptyMessage="연결된 도구 없음"
          accentColor="text-blue-400"
        />

        <VariablePalette
          variables={allVariables}
          onInsert={insertVariable}
          category="knowledge"
          title="지식 베이스"
          icon="📚"
          emptyMessage="지식 베이스 비활성화"
          accentColor="text-purple-400"
        />

        {/* 통계 */}
        <div className="bg-gray-900 rounded-lg p-3 border border-gray-700 text-xs text-gray-500 space-y-1">
          <div className="flex justify-between">
            <span>변수:</span>
            <span className="text-gray-300">{allVariables.length}개</span>
          </div>
          <div className="flex justify-between">
            <span>시스템:</span>
            <span className="text-gray-300">{systemPrompt.length}자</span>
          </div>
          <div className="flex justify-between">
            <span>사용자:</span>
            <span className="text-gray-300">{userPromptTemplate.length}자</span>
          </div>
          {outputEnforcement.enabled && (
            <div className="flex justify-between text-orange-400">
              <span>출력 강제:</span>
              <span>활성</span>
            </div>
          )}
        </div>

        <div className="text-xs text-gray-600 space-y-1 px-1">
          <p>💡 <code className="text-gray-500">{'{{변수}}'}</code> 형식</p>
          <p>💡 배열: <code className="text-gray-500">{'{{#each}}'}</code></p>
        </div>
      </div>
    </div>
  );
}
