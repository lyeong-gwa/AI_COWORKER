import { useState, useMemo } from 'react';
import type { Node, Edge } from '@xyflow/react';
import type { AINode } from '../../types';

interface ScheduleConfig {
  type?: string;
  hour?: number;
  minute?: number;
  dayOfWeek?: number;
  dayOfMonth?: number;
}

interface FormStartConfig {
  mode?: 'manual' | 'schedule';
  scheduleConfig?: ScheduleConfig;
  defaultValues?: Record<string, any>;
}

interface DerivedTriggerField {
  name: string;
  type: string;
  description: string;
  required: boolean;
  sourceNodeName: string;
  enum?: string[];
}

interface FormStartConfigPanelProps {
  nodeId: string;
  nodeName: string;
  config: FormStartConfig;
  onUpdateName: (name: string) => void;
  onUpdateConfig: (config: FormStartConfig) => void;
  onExecute: (inputData: Record<string, unknown>) => void;
  executing?: boolean;
  onDelete: () => void;
  onClose: () => void;
  allNodes?: Node[];
  edges?: Edge[];
  aiNodes?: AINode[];
}

function deriveTriggerFields(
  triggerNodeId: string,
  allNodes: Node[],
  edges: Edge[],
  aiNodes: AINode[]
): DerivedTriggerField[] {
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

      const aiNodeId = (node.data as any).aiNodeId || (node.data as any).nodeId;
      const aiNode = aiNodes.find((n) => n.id === aiNodeId);

      if (aiNode?.inputSchema?.properties) {
        const required = aiNode.inputSchema.required || [];

        for (const [propName, propDef] of Object.entries(aiNode.inputSchema.properties)) {
          if (seen.has(propName)) continue;
          const propType = (propDef as unknown as Record<string, unknown>).type as string || 'string';
          if (propType === 'array' || propType === 'object') continue;
          seen.add(propName);

          fields.push({
            name: propName,
            type: propType,
            description: (propDef as unknown as Record<string, unknown>).description as string || '',
            required: required.includes(propName),
            sourceNodeName: aiNode.name,
            enum: (propDef as unknown as Record<string, unknown>).enum as string[] | undefined,
          });
        }
      }

      queue.push(targetId);
    }
  }

  return fields;
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

export function FormStartConfigPanel({
  nodeId,
  nodeName,
  config,
  onUpdateName,
  onUpdateConfig,
  onExecute,
  executing,
  onDelete,
  onClose,
  allNodes,
  edges,
  aiNodes,
}: FormStartConfigPanelProps) {
  const mode = config.mode || 'manual';
  const scheduleConfig = config.scheduleConfig || {};
  const fields = (config as any).fields as Array<{name: string; label: string; type: string; required: boolean}> | undefined;

  // BFS로 하류 AI 노드의 inputSchema에서 필드 도출 (config.fields 없을 때 fallback)
  const derivedFields = useMemo(() => {
    if (fields && fields.length > 0) return null; // config.fields가 있으면 그대로 사용
    if (!allNodes || !edges || !aiNodes) return null;
    return deriveTriggerFields(nodeId, allNodes, edges, aiNodes);
  }, [fields, nodeId, allNodes, edges, aiNodes]);

  // 최종 사용할 필드: config.fields 우선, 없으면 derivedFields
  const effectiveFields = fields && fields.length > 0
    ? fields
    : derivedFields?.map(df => ({ name: df.name, label: df.description || df.name, type: df.type, required: df.required }));

  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [scheduleType, setScheduleType] = useState(scheduleConfig.type || 'daily');
  const [hour, setHour] = useState(scheduleConfig.hour ?? 9);
  const [minute, setMinute] = useState(scheduleConfig.minute ?? 0);
  const [dayOfWeek, setDayOfWeek] = useState(scheduleConfig.dayOfWeek ?? 0);
  const [dayOfMonth, setDayOfMonth] = useState(scheduleConfig.dayOfMonth ?? 1);

  // Suppress unused var lint
  void nodeId;

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

  const handleFieldChange = (name: string, value: string) => {
    setFormValues(prev => ({ ...prev, [name]: value }));
  };

  return (
    <div className="w-96 bg-gray-800 border-l border-gray-700 flex flex-col animate-slide-in-right">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-amber-900 flex items-center justify-center text-xl">
              {'\u{1F4CB}'}
            </div>
            <div>
              <div className="text-xs text-amber-300/70 uppercase tracking-wider">폼 시작 설정</div>
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
                  ? 'bg-amber-600 text-white'
                  : 'bg-gray-700 text-gray-400 hover:text-gray-200'
              }`}
            >
              수동실행
            </button>
            <button
              onClick={() => handleModeChange('schedule')}
              className={`flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                mode === 'schedule'
                  ? 'bg-amber-600 text-white'
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
            <div className="text-xs text-amber-300/70 font-medium mb-2">스케줄 설정</div>

            {/* Schedule type */}
            <div>
              <label className="block text-[10px] text-gray-400 mb-1 uppercase tracking-wide">반복 유형</label>
              <select
                value={scheduleType}
                onChange={(e) => handleScheduleUpdate({ type: e.target.value })}
                className="w-full bg-gray-800 border border-gray-600 rounded px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-amber-500"
              >
                {SCHEDULE_TYPES.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            {/* Day of week (weekly) */}
            {scheduleType === 'weekly' && (
              <div>
                <label className="block text-[10px] text-gray-400 mb-1 uppercase tracking-wide">요일</label>
                <select
                  value={dayOfWeek}
                  onChange={(e) => handleScheduleUpdate({ dayOfWeek: Number(e.target.value) })}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-amber-500"
                >
                  {DAY_OF_WEEK_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
            )}

            {/* Day of month (monthly) */}
            {scheduleType === 'monthly' && (
              <div>
                <label className="block text-[10px] text-gray-400 mb-1 uppercase tracking-wide">일</label>
                <select
                  value={dayOfMonth}
                  onChange={(e) => handleScheduleUpdate({ dayOfMonth: Number(e.target.value) })}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-amber-500"
                >
                  {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
                    <option key={d} value={d}>{d}일</option>
                  ))}
                </select>
              </div>
            )}

            {/* Hour + Minute */}
            {scheduleType !== 'hourly' && (
              <div className="flex gap-2">
                <div className="flex-1">
                  <label className="block text-[10px] text-gray-400 mb-1 uppercase tracking-wide">시</label>
                  <select
                    value={hour}
                    onChange={(e) => handleScheduleUpdate({ hour: Number(e.target.value) })}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-amber-500"
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
                    className="w-full bg-gray-800 border border-gray-600 rounded px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-amber-500"
                  >
                    {Array.from({ length: 60 }, (_, i) => i).map((m) => (
                      <option key={m} value={m}>{String(m).padStart(2, '0')}분</option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            {/* Minute only (hourly) */}
            {scheduleType === 'hourly' && (
              <div>
                <label className="block text-[10px] text-gray-400 mb-1 uppercase tracking-wide">분</label>
                <select
                  value={minute}
                  onChange={(e) => handleScheduleUpdate({ minute: Number(e.target.value) })}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-amber-500"
                >
                  {Array.from({ length: 60 }, (_, i) => i).map((m) => (
                    <option key={m} value={m}>{String(m).padStart(2, '0')}분</option>
                  ))}
                </select>
              </div>
            )}

            {/* Info note */}
            <div className="p-2 bg-yellow-900/20 border border-yellow-700/40 rounded-lg">
              <p className="text-[10px] text-yellow-400/80">
                실제 스케줄 실행은 미구현 상태입니다. 설정만 저장됩니다.
              </p>
            </div>
          </div>
        )}

        {/* Info box */}
        <div className="bg-amber-900/20 border border-amber-700/40 rounded-lg p-3">
          <p className="text-xs text-amber-300/80 leading-relaxed">
            이 시작노드는 다음 연결된 노드의 입력 양식을 폼으로 제공합니다.
          </p>
        </div>

        {/* Form fields from config */}
        {effectiveFields && effectiveFields.length > 0 && (
          <div className="space-y-3 bg-gray-900 rounded-lg p-3">
            <div className="text-xs text-amber-300/70 font-medium mb-2">입력 폼</div>
            {effectiveFields.map((field) => (
              <div key={field.name}>
                <label className="block text-[10px] text-gray-400 mb-1 uppercase tracking-wide">
                  {field.label}
                  {field.required && <span className="text-red-400 ml-1">*</span>}
                </label>
                <input
                  type={/token|password|secret|key/i.test(field.name) ? 'password' : 'text'}
                  value={formValues[field.name] || ''}
                  onChange={(e) => handleFieldChange(field.name, e.target.value)}
                  placeholder={`${field.label} 입력...`}
                  className="w-full bg-gray-800 border border-gray-600 rounded px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-amber-500"
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-gray-700 space-y-2">
        {mode === 'manual' && (
          <button
            onClick={() => {
              const inputData: Record<string, unknown> = {};
              if (effectiveFields) {
                for (const field of effectiveFields) {
                  inputData[field.name] = formValues[field.name] || '';
                }
              }
              onExecute(inputData);
            }}
            disabled={executing}
            className={`w-full px-4 py-2.5 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
              executing
                ? 'bg-amber-700/50 text-amber-300/50 cursor-not-allowed'
                : 'bg-amber-600 text-white hover:bg-amber-500'
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
