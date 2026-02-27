import { useState, useMemo, useEffect, useCallback } from 'react';
import type { Node, Edge } from '@xyflow/react';
import type { AINode } from '../../types';

// ─── Types ───────────────────────────────────────────────────────────────────

interface CustomNodeData extends Record<string, unknown> {
  nodeId: string;
  instanceName: string;
  inputMapping?: Record<string, string>;
  definitionType?: string;
  aiNodeId?: string;
}

interface DerivedTriggerField {
  name: string;
  type: string;
  description: string;
  required: boolean;
  sourceNodeName: string;
  enum?: string[];
}

interface TriggerConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  triggerConfig: { type: string; config: Record<string, unknown> };
  triggerNode: Node<CustomNodeData>;
  triggerNodeId: string;
  allNodes: Node<CustomNodeData>[];
  edges: Edge[];
  aiNodes: AINode[];
  onSaveTrigger: (triggerConfig: { type: string; config: Record<string, unknown> }) => void;
  onExecute: (inputData: Record<string, unknown>) => void;
  executing?: boolean;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function deriveTriggerFields(
  triggerNodeId: string,
  allNodes: Node<CustomNodeData>[],
  edges: Edge[],
  aiNodes: AINode[]
): DerivedTriggerField[] {
  // BFS through the graph to find all downstream ai-custom nodes
  const visited = new Set<string>();
  const queue: string[] = [triggerNodeId];
  visited.add(triggerNodeId);

  const seen = new Set<string>();
  const fields: DerivedTriggerField[] = [];

  while (queue.length > 0) {
    const currentId = queue.shift()!;
    const outEdges = edges.filter((e) => e.source === currentId);

    for (const edge of outEdges) {
      const targetId = edge.target;
      if (visited.has(targetId)) continue;
      visited.add(targetId);

      const node = allNodes.find((n) => n.id === targetId);
      if (!node) continue;

      const aiNodeId = node.data.aiNodeId || node.data.nodeId;
      const aiNode = aiNodes.find((n) => n.id === aiNodeId);

      if (aiNode?.inputSchema?.properties) {
        const required = aiNode.inputSchema.required || [];

        for (const [propName, propDef] of Object.entries(aiNode.inputSchema.properties)) {
          if (seen.has(propName)) continue;
          const propType = (propDef as Record<string, unknown>).type as string || 'string';
          // Skip array fields (auto-populated by upstream nodes like knowledge search)
          if (propType === 'array' || propType === 'object') continue;
          seen.add(propName);

          fields.push({
            name: propName,
            type: propType,
            description: (propDef as Record<string, unknown>).description as string || '',
            required: required.includes(propName),
            sourceNodeName: aiNode.name,
            enum: (propDef as Record<string, unknown>).enum as string[] | undefined,
          });
        }
      }

      // Continue traversing to find more downstream AI nodes
      queue.push(targetId);
    }
  }

  return fields;
}

type ScheduleType = 'specific' | 'hourly' | 'daily' | 'weekly' | 'monthly';
type ActiveTab = 'schedule' | 'form';

const SCHEDULE_OPTIONS: { value: ScheduleType; label: string }[] = [
  { value: 'specific', label: '특정 시간' },
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

// ─── Component ───────────────────────────────────────────────────────────────

function TriggerConfigModal({
  isOpen,
  onClose,
  triggerConfig,
  triggerNode: _triggerNode,
  triggerNodeId,
  allNodes,
  edges,
  aiNodes,
  onSaveTrigger,
  onExecute,
  executing = false,
}: TriggerConfigModalProps) {
  // Tab state
  const [activeTab, setActiveTab] = useState<ActiveTab>(
    triggerConfig.type === 'form' ? 'form' : 'schedule'
  );

  // Schedule state
  const [scheduleType, setScheduleType] = useState<ScheduleType>(
    (triggerConfig.config.scheduleType as ScheduleType) || 'daily'
  );
  const [hour, setHour] = useState<number>(
    (triggerConfig.config.hour as number) ?? 9
  );
  const [minute, setMinute] = useState<number>(
    (triggerConfig.config.minute as number) ?? 0
  );
  const [dayOfWeek, setDayOfWeek] = useState<number>(
    (triggerConfig.config.dayOfWeek as number) ?? 0
  );
  const [dayOfMonth, setDayOfMonth] = useState<number>(
    (triggerConfig.config.dayOfMonth as number) ?? 1
  );
  const [specificDate, setSpecificDate] = useState<string>(
    (triggerConfig.config.specificDate as string) || ''
  );

  // Derive fields from connected factory nodes' inputSchema
  const derivedFields = useMemo(
    () => deriveTriggerFields(triggerNodeId, allNodes, edges, aiNodes),
    [triggerNodeId, allNodes, edges, aiNodes]
  );

  const [formValues, setFormValues] = useState<Record<string, string>>({});

  // Initialize form values when derived fields change
  useEffect(() => {
    setFormValues((prev) => {
      const next: Record<string, string> = {};
      for (const field of derivedFields) {
        next[field.name] = prev[field.name] || '';
      }
      return next;
    });
  }, [derivedFields]);

  // Escape key handler
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Backdrop click handler
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose]
  );

  // Save handler
  const handleSave = useCallback(() => {
    if (activeTab === 'schedule') {
      const config: Record<string, unknown> = { scheduleType, hour, minute };
      if (scheduleType === 'weekly') config.dayOfWeek = dayOfWeek;
      if (scheduleType === 'monthly') config.dayOfMonth = dayOfMonth;
      if (scheduleType === 'specific') config.specificDate = specificDate;
      onSaveTrigger({ type: 'schedule', config });
    } else {
      onSaveTrigger({ type: 'form', config: { fields: derivedFields.map(f => f.name) } });
    }
  }, [
    activeTab, scheduleType, hour, minute, dayOfWeek, dayOfMonth,
    specificDate, derivedFields, onSaveTrigger,
  ]);

  // Execute handler
  const handleExecute = useCallback(() => {
    const inputData: Record<string, unknown> = {};
    for (const field of derivedFields) {
      const val = formValues[field.name] || '';
      if (field.type === 'number') {
        inputData[field.name] = val === '' ? 0 : Number(val);
      } else if (field.type === 'boolean') {
        inputData[field.name] = formValues[field.name] === 'true';
      } else {
        inputData[field.name] = val;
      }
    }
    onExecute(inputData);
  }, [derivedFields, formValues, onExecute]);

  // Form field change
  const handleFieldChange = useCallback((field: string, value: string) => {
    setFormValues((prev) => ({ ...prev, [field]: value }));
  }, []);

  if (!isOpen) return null;

  // ─── Render helpers ────────────────────────────────────────────────────────

  const renderScheduleTab = () => (
    <div className="space-y-4">
      {/* Schedule type selector */}
      <div>
        <label className="block text-sm text-gray-300 mb-1">반복 유형</label>
        <select
          value={scheduleType}
          onChange={(e) => setScheduleType(e.target.value as ScheduleType)}
          className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
        >
          {SCHEDULE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Specific date */}
      {scheduleType === 'specific' && (
        <div>
          <label className="block text-sm text-gray-300 mb-1">날짜</label>
          <input
            type="date"
            value={specificDate}
            onChange={(e) => setSpecificDate(e.target.value)}
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
          />
        </div>
      )}

      {/* Day of week (weekly) */}
      {scheduleType === 'weekly' && (
        <div>
          <label className="block text-sm text-gray-300 mb-1">요일</label>
          <select
            value={dayOfWeek}
            onChange={(e) => setDayOfWeek(Number(e.target.value))}
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
          >
            {DAY_OF_WEEK_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Day of month (monthly) */}
      {scheduleType === 'monthly' && (
        <div>
          <label className="block text-sm text-gray-300 mb-1">일</label>
          <select
            value={dayOfMonth}
            onChange={(e) => setDayOfMonth(Number(e.target.value))}
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
          >
            {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
              <option key={d} value={d}>
                {d}일
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Hour + Minute (all except hourly) */}
      {scheduleType !== 'hourly' && (
        <div className="flex gap-3">
          <div className="flex-1">
            <label className="block text-sm text-gray-300 mb-1">시</label>
            <select
              value={hour}
              onChange={(e) => setHour(Number(e.target.value))}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
            >
              {Array.from({ length: 24 }, (_, i) => i).map((h) => (
                <option key={h} value={h}>
                  {String(h).padStart(2, '0')}시
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label className="block text-sm text-gray-300 mb-1">분</label>
            <select
              value={minute}
              onChange={(e) => setMinute(Number(e.target.value))}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
            >
              {Array.from({ length: 60 }, (_, i) => i).map((m) => (
                <option key={m} value={m}>
                  {String(m).padStart(2, '0')}분
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* Minute only (hourly) */}
      {scheduleType === 'hourly' && (
        <div>
          <label className="block text-sm text-gray-300 mb-1">분</label>
          <select
            value={minute}
            onChange={(e) => setMinute(Number(e.target.value))}
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
          >
            {Array.from({ length: 60 }, (_, i) => i).map((m) => (
              <option key={m} value={m}>
                {String(m).padStart(2, '0')}분
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Info note */}
      <div className="mt-4 p-3 bg-yellow-900/20 border border-yellow-700/40 rounded-lg">
        <p className="text-xs text-yellow-400/80">
          실제 스케줄 실행은 미구현 상태입니다. 설정만 저장됩니다.
        </p>
      </div>
    </div>
  );

  const renderFormTab = () => (
    <div className="space-y-4">
      {derivedFields.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          <div className="text-3xl mb-3">🔗</div>
          <p className="text-sm">
            채굴기를 공장에 연결하면 입력 폼이 자동 생성됩니다.
          </p>
          <p className="text-xs mt-2 text-gray-600">
            좌측 팔레트에서 공장을 추가하고 연결해 보세요.
          </p>
        </div>
      ) : (
        <>
          {derivedFields.map((field) => {
            const label = field.description || field.name;
            const isUrl = field.type === 'string' && /url/i.test(field.name);
            const isPassword = field.type === 'string' && /token|password|secret|key/i.test(field.name);
            const isLongText = field.type === 'string' && /content|body|text|description|message|prompt/i.test(field.name);

            return (
              <div key={field.name}>
                <label className="block text-sm text-gray-300 mb-1">
                  {label}
                  {field.required && <span className="text-red-400 ml-1">*</span>}
                </label>

                {/* source badge */}
                <div className="text-[10px] text-gray-600 mb-1.5">
                  {field.sourceNodeName} 에서 사용
                </div>

                {/* Enum → select */}
                {field.enum ? (
                  <select
                    value={formValues[field.name] || ''}
                    onChange={(e) => handleFieldChange(field.name, e.target.value)}
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                  >
                    <option value="">선택...</option>
                    {field.enum.map((opt) => (
                      <option key={opt} value={opt}>{opt}</option>
                    ))}
                  </select>
                ) : field.type === 'boolean' ? (
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formValues[field.name] === 'true'}
                      onChange={(e) => handleFieldChange(field.name, e.target.checked ? 'true' : 'false')}
                      className="w-4 h-4 rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500"
                    />
                    <span className="text-gray-300 text-sm">{label}</span>
                  </label>
                ) : isLongText ? (
                  <textarea
                    value={formValues[field.name] || ''}
                    onChange={(e) => handleFieldChange(field.name, e.target.value)}
                    placeholder={`${field.name} 입력...`}
                    rows={3}
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500 resize-y"
                  />
                ) : (
                  <input
                    type={
                      isPassword ? 'password' :
                      isUrl ? 'url' :
                      field.type === 'number' ? 'number' :
                      'text'
                    }
                    value={formValues[field.name] || ''}
                    onChange={(e) => handleFieldChange(field.name, e.target.value)}
                    placeholder={
                      isUrl ? 'https://...' :
                      isPassword ? '보안 값 입력' :
                      `${field.name} 입력...`
                    }
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                  />
                )}
              </div>
            );
          })}
        </>
      )}
    </div>
  );

  // ─── Main render ───────────────────────────────────────────────────────────

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={handleBackdropClick}
    >
      <div className="bg-gray-800 border border-gray-700 rounded-xl shadow-2xl w-full max-w-lg mx-4 flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700">
          <h2 className="text-lg font-semibold text-white">트리거 설정</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-300 transition-colors text-xl leading-none"
            title="닫기"
          >
            &times;
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-700">
          <button
            onClick={() => setActiveTab('schedule')}
            className={`flex-1 px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === 'schedule'
                ? 'text-blue-400 border-b-2 border-blue-400 bg-gray-800'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            스케줄러
          </button>
          <button
            onClick={() => setActiveTab('form')}
            className={`flex-1 px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === 'form'
                ? 'text-blue-400 border-b-2 border-blue-400 bg-gray-800'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            폼 입력
          </button>
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {activeTab === 'schedule' ? renderScheduleTab() : renderFormTab()}
        </div>

        {/* Footer buttons */}
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-gray-700">
          {activeTab === 'form' && (
            <button
              onClick={handleExecute}
              disabled={executing}
              className="flex items-center gap-1.5 px-4 py-2 bg-green-600 hover:bg-green-500 disabled:bg-green-800 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
            >
              {executing && (
                <svg
                  className="animate-spin h-4 w-4"
                  viewBox="0 0 24 24"
                  fill="none"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
              )}
              {executing ? '실행 중...' : '실행'}
            </button>
          )}
          <button
            onClick={handleSave}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            저장
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 text-sm font-medium rounded-lg transition-colors"
          >
            취소
          </button>
        </div>
      </div>
    </div>
  );
}

export { TriggerConfigModal };
export default TriggerConfigModal;
