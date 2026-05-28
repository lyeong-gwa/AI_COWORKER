/**
 * WorkflowScheduleCard
 *
 * Phase B — 워크플로우 스케줄러 설정 카드.
 * 토글 ON/OFF, 주기 선택(preset 7종 + 커스텀 cron), 트리거 입력값(payload), 즉시 실행, 저장.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { workflowApi } from '../../services/api';
import type { WorkflowNodeInstance, WorkflowScheduleConfig } from '../../types';
import { useToast } from '../common/Toast';

// ─── preset 매핑 (D3) ────────────────────────────────────────────────────────

interface Preset {
  label: string;
  cron: string;
}

export const SCHEDULE_PRESETS: Preset[] = [
  { label: '5분마다', cron: '*/5 * * * *' },
  { label: '10분마다', cron: '*/10 * * * *' },
  { label: '30분마다', cron: '*/30 * * * *' },
  { label: '1시간마다', cron: '0 * * * *' },
  { label: '6시간마다', cron: '0 */6 * * *' },
  { label: '매일 자정', cron: '0 0 * * *' },
  { label: '매주 월요일 09:00', cron: '0 9 * * 1' },
];

const CUSTOM_VALUE = '__custom__';

/** cron 문자열 → 사람이 읽기 좋은 라벨 (preset에 있으면 라벨, 없으면 cron 그대로) */
export function cronToLabel(cron: string): string {
  const preset = SCHEDULE_PRESETS.find((p) => p.cron === cron);
  return preset ? preset.label : cron;
}

function detectPresetValue(cron: string): string {
  const found = SCHEDULE_PRESETS.find((p) => p.cron === cron);
  return found ? found.cron : CUSTOM_VALUE;
}

function formatNextRun(iso: string | null | undefined, timezone: string): string {
  if (!iso) return '없음';
  try {
    const d = new Date(iso);
    return d.toLocaleString('ko-KR', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }) + ` (${timezone})`;
  } catch {
    return iso;
  }
}

// ─── Toggle Switch ────────────────────────────────────────────────────────────

function ToggleSwitch({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`
        relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full
        transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/60
        ${checked ? 'bg-cyan-500' : 'bg-slate-700'}
        ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
      `}
    >
      <span
        className={`
          inline-block h-4 w-4 transform rounded-full bg-white shadow-md
          transition-transform duration-200
          ${checked ? 'translate-x-6' : 'translate-x-1'}
        `}
      />
    </button>
  );
}

// ─── 트리거 입력값(payload) helpers ───────────────────────────────────────────

interface FormStartField {
  name: string;
  label?: string;
  type?: string;
  default?: unknown;
  required?: boolean;
}

/** triggerNode 가 form-start 이고 config.fields 가 비어있지 않으면 그 fields 반환. */
export function detectFormStartFields(triggerNode: WorkflowNodeInstance | null | undefined): FormStartField[] {
  if (!triggerNode) return [];
  if ((triggerNode.definitionType || '').toLowerCase() !== 'form-start') return [];
  const raw = (triggerNode.config as { fields?: unknown } | undefined)?.fields;
  if (!Array.isArray(raw)) return [];
  const out: FormStartField[] = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue;
    const f = item as Record<string, unknown>;
    const name = typeof f.name === 'string' ? f.name : '';
    if (!name) continue;
    out.push({
      name,
      label: typeof f.label === 'string' ? f.label : undefined,
      type: typeof f.type === 'string' ? f.type : 'string',
      default: f.default,
      required: !!f.required,
    });
  }
  return out;
}

/** field value 를 input 표시용 문자열로 강제 변환. */
function valueToInputString(v: unknown): string {
  if (v === undefined || v === null) return '';
  if (typeof v === 'string') return v;
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  try {
    return JSON.stringify(v);
  } catch {
    return '';
  }
}

/** field 의 type 에 맞춰 입력 문자열을 적절한 JS 값으로 파싱.
 *  string  → string (빈 문자열도 유지)
 *  number  → Number (NaN 이면 원문 string 보존)
 *  boolean → "true"/"false"/"1"/"0" 인식, 외엔 string
 *  기타    → string
 */
function parseInputValue(field: FormStartField, raw: string): unknown {
  const t = (field.type || 'string').toLowerCase();
  if (t === 'number') {
    if (raw.trim() === '') return '';
    const n = Number(raw);
    return Number.isFinite(n) ? n : raw;
  }
  if (t === 'boolean') {
    const lower = raw.trim().toLowerCase();
    if (lower === 'true' || lower === '1') return true;
    if (lower === 'false' || lower === '0') return false;
    return raw;
  }
  return raw;
}

// ─── Component ────────────────────────────────────────────────────────────────

interface WorkflowScheduleCardProps {
  workflowId: string;
  initialConfig: WorkflowScheduleConfig;
  /** 첫 노드(트리거). form-start 의 fields 자동 감지에 사용. */
  triggerNode?: WorkflowNodeInstance | null;
  onSaved?: () => void;
}

export function WorkflowScheduleCard({
  workflowId,
  initialConfig,
  triggerNode,
  onSaved,
}: WorkflowScheduleCardProps) {
  const { toast } = useToast();

  const [enabled, setEnabled] = useState(initialConfig.enabled);
  const [presetValue, setPresetValue] = useState<string>(
    detectPresetValue(initialConfig.cronExpr),
  );
  const [customCron, setCustomCron] = useState(
    detectPresetValue(initialConfig.cronExpr) === CUSTOM_VALUE
      ? initialConfig.cronExpr
      : '',
  );
  const [timezone] = useState(initialConfig.timezone || 'Asia/Seoul');

  // ── 트리거 입력값(payload) 상태 ────────────────────────────────────────────
  const formFields = useMemo<FormStartField[]>(
    () => detectFormStartFields(triggerNode ?? null),
    [triggerNode],
  );
  const initialPayload = useMemo<Record<string, unknown>>(
    () => (initialConfig.payload && typeof initialConfig.payload === 'object' ? initialConfig.payload : {}),
    [initialConfig.payload],
  );
  // 폼 모드: 필드별 문자열 input 값 (저장 시 type 에 맞춰 변환)
  const [fieldInputs, setFieldInputs] = useState<Record<string, string>>(() => {
    const out: Record<string, string> = {};
    for (const f of formFields) {
      if (Object.prototype.hasOwnProperty.call(initialPayload, f.name)) {
        out[f.name] = valueToInputString(initialPayload[f.name]);
      } else {
        out[f.name] = '';
      }
    }
    return out;
  });
  // JSON 폴백 모드: 직접 JSON 텍스트 편집
  const [jsonText, setJsonText] = useState<string>(() => {
    if (formFields.length > 0) return '';
    try {
      return Object.keys(initialPayload).length > 0
        ? JSON.stringify(initialPayload, null, 2)
        : '{}';
    } catch {
      return '{}';
    }
  });
  const [payloadError, setPayloadError] = useState<string | null>(null);

  const [nextRunTime, setNextRunTime] = useState<string | null>(null);
  const [nextRunLoading, setNextRunLoading] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [triggerLoading, setTriggerLoading] = useState(false);
  const [cronError, setCronError] = useState<string | null>(null);

  // 다음 실행 시간 조회
  const fetchNextRun = useCallback(async () => {
    setNextRunLoading(true);
    try {
      const res = await workflowApi.getScheduleNextRun(workflowId);
      setNextRunTime(res.nextRunTime);
    } catch {
      setNextRunTime(null);
    } finally {
      setNextRunLoading(false);
    }
  }, [workflowId]);

  useEffect(() => {
    fetchNextRun();
  }, [fetchNextRun]);

  // 현재 선택된 cron 문자열
  const currentCron =
    presetValue === CUSTOM_VALUE ? customCron.trim() : presetValue;

  // payload 조립 — 실패 시 setPayloadError + null 반환
  const buildPayload = (): Record<string, unknown> | null => {
    if (formFields.length > 0) {
      const out: Record<string, unknown> = {};
      for (const f of formFields) {
        const raw = fieldInputs[f.name] ?? '';
        // 빈 문자열은 payload 에 포함하지 않는다 — backend 가 form-start default 처리
        if (raw === '') continue;
        out[f.name] = parseInputValue(f, raw);
      }
      return out;
    }
    // JSON 폴백
    const trimmed = jsonText.trim();
    if (!trimmed) return {};
    try {
      const parsed = JSON.parse(trimmed);
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        setPayloadError('JSON 객체 형태여야 합니다. 예: { "status": "신규" }');
        return null;
      }
      return parsed as Record<string, unknown>;
    } catch (e) {
      setPayloadError(`JSON 파싱 실패: ${e instanceof Error ? e.message : String(e)}`);
      return null;
    }
  };

  const handleSave = async () => {
    if (!currentCron) {
      setCronError('cron 표현식을 입력하세요.');
      return;
    }
    setCronError(null);
    setPayloadError(null);
    const payload = buildPayload();
    if (payload === null) return; // payload 에러는 buildPayload 가 setState
    setSaveLoading(true);
    try {
      const res = await workflowApi.updateSchedule(workflowId, {
        enabled,
        cronExpr: currentCron,
        timezone,
        payload,
      });
      toast.success('스케줄이 저장되었습니다.');
      setNextRunTime(res.nextRunTime ?? null);
      onSaved?.();
    } catch (e: unknown) {
      const err = e as { status?: number; message?: string };
      if (err?.status === 422) {
        setCronError('잘못된 cron 표현식입니다. 형식을 확인하세요.');
      } else {
        toast.error(`저장 실패: ${err?.message ?? String(e)}`);
      }
    } finally {
      setSaveLoading(false);
    }
  };

  const handleTriggerNow = async () => {
    setTriggerLoading(true);
    try {
      const res = await workflowApi.triggerNow(workflowId);
      toast.success('즉시 실행이 시작되었습니다.');
      if (res.instanceId) {
        // 실행 인스턴스 페이지 이동 옵션 — 별도 토스트로 안내
        setTimeout(() => {
          const go = window.confirm(
            `실행이 시작되었습니다.\n인스턴스 페이지로 이동하시겠습니까?\n(${res.instanceId})`,
          );
          if (go) {
            window.location.href = `/workflows/${workflowId}/instances/${res.instanceId}`;
          }
        }, 400);
      }
    } catch (e: unknown) {
      const err = e as { message?: string };
      toast.error(`즉시 실행 실패: ${err?.message ?? String(e)}`);
    } finally {
      setTriggerLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900/60 overflow-hidden">
      {/* Card header */}
      <div className="px-5 py-3.5 border-b border-slate-800/80 flex items-center gap-2">
        <span className="text-base leading-none select-none" aria-hidden="true">
          &#x23F0;
        </span>
        <span className="text-[11px] font-mono tracking-[0.2em] uppercase text-slate-400">
          스케줄러
        </span>
        {enabled && (
          <span className="ml-auto inline-flex items-center gap-1 rounded-full border border-cyan-600/50 bg-cyan-900/30 px-2 py-0.5 text-[10px] font-mono text-cyan-300">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
            ON
          </span>
        )}
      </div>

      {/* Card body */}
      <div className="px-5 py-4 space-y-4">
        {/* Toggle row */}
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-slate-200">
              {enabled ? '스케줄 활성' : '스케줄 비활성'}
            </p>
            <p className="text-[11px] text-slate-500 mt-0.5">
              저장 후 즉시 적용됩니다.
            </p>
          </div>
          <ToggleSwitch
            checked={enabled}
            onChange={setEnabled}
            disabled={saveLoading}
          />
        </div>

        {/* Preset selector */}
        <div>
          <label className="block text-[11px] font-mono tracking-wider uppercase text-slate-400 mb-1.5">
            주기
          </label>
          <div className="relative">
            <select
              value={presetValue}
              onChange={(e) => setPresetValue(e.target.value)}
              disabled={saveLoading}
              className="w-full appearance-none pl-3 pr-8 py-2 rounded-lg bg-slate-950 border border-slate-700 text-sm text-slate-200 focus:outline-none focus:border-cyan-600/60 disabled:opacity-50"
            >
              {SCHEDULE_PRESETS.map((p) => (
                <option key={p.cron} value={p.cron}>
                  {p.label}
                </option>
              ))}
              <option value={CUSTOM_VALUE}>커스텀&hellip;</option>
            </select>
            <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 text-xs">
              &#x25BE;
            </span>
          </div>
        </div>

        {/* Custom cron input */}
        {presetValue === CUSTOM_VALUE && (
          <div>
            <label className="block text-[11px] font-mono tracking-wider uppercase text-slate-400 mb-1.5">
              cron 표현식
            </label>
            <input
              type="text"
              value={customCron}
              onChange={(e) => {
                setCustomCron(e.target.value);
                setCronError(null);
              }}
              placeholder="예: */15 * * * *"
              disabled={saveLoading}
              className={`
                w-full px-3 py-2 rounded-lg bg-slate-950 border text-sm font-mono text-slate-200
                focus:outline-none disabled:opacity-50
                ${cronError ? 'border-rose-600/70 focus:border-rose-500' : 'border-slate-700 focus:border-cyan-600/60'}
              `}
            />
            <p className="text-[10px] text-slate-500 mt-1 font-mono">
              분 시 일 월 요일 &nbsp;·&nbsp; 예: <code>0 9 * * 1-5</code> (평일 오전 9시)
            </p>
          </div>
        )}

        {/* cron error */}
        {cronError && (
          <div className="rounded-lg border border-rose-700/50 bg-rose-950/30 px-3 py-2 text-xs text-rose-300">
            {cronError}
          </div>
        )}

        {/* ── 트리거 입력값 (payload) ───────────────────────────────────────── */}
        <div className="pt-1 border-t border-slate-800/80">
          <div className="flex items-center justify-between mb-1.5 mt-3">
            <label className="block text-[11px] font-mono tracking-wider uppercase text-slate-400">
              트리거 입력값
            </label>
            <span className="text-[10px] font-mono text-slate-600">
              {formFields.length > 0 ? `form-start · ${formFields.length} field${formFields.length > 1 ? 's' : ''}` : 'JSON'}
            </span>
          </div>

          {formFields.length > 0 ? (
            <div className="space-y-2.5">
              {formFields.map((f) => {
                const placeholder = f.default !== undefined && f.default !== null
                  ? valueToInputString(f.default)
                  : '';
                return (
                  <div key={f.name}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[11px] font-mono text-slate-400">
                        {f.label || f.name}
                        {f.required && <span className="text-rose-400 ml-1">*</span>}
                      </span>
                      <span className="text-[10px] font-mono text-slate-600">
                        {f.type || 'string'}
                      </span>
                    </div>
                    <input
                      type="text"
                      value={fieldInputs[f.name] ?? ''}
                      onChange={(e) => {
                        const v = e.target.value;
                        setFieldInputs((prev) => ({ ...prev, [f.name]: v }));
                        setPayloadError(null);
                      }}
                      placeholder={placeholder}
                      disabled={saveLoading}
                      className="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-700 text-sm text-slate-200 focus:outline-none focus:border-cyan-600/60 disabled:opacity-50 font-mono"
                    />
                  </div>
                );
              })}
              <p className="text-[10px] text-slate-500 mt-1.5 font-mono leading-relaxed">
                비워두면 트리거 노드의 default 값이 사용됩니다.
              </p>
            </div>
          ) : (
            <div className="space-y-1.5">
              <textarea
                value={jsonText}
                onChange={(e) => {
                  setJsonText(e.target.value);
                  setPayloadError(null);
                }}
                rows={4}
                disabled={saveLoading}
                placeholder='{ "key": "value" }'
                className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-600/60 disabled:opacity-50"
              />
              <p className="text-[10px] text-slate-500 font-mono leading-relaxed">
                트리거가 form-start 가 아닙니다. JSON 객체로 직접 입력하세요.
                비우면 빈 객체로 전달됩니다.
              </p>
            </div>
          )}

          {payloadError && (
            <div className="mt-2 rounded-lg border border-rose-700/50 bg-rose-950/30 px-3 py-2 text-xs text-rose-300">
              {payloadError}
            </div>
          )}
        </div>

        {/* Next run time */}
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 px-4 py-3">
          <div className="text-[10px] font-mono tracking-wider uppercase text-slate-500 mb-1">
            다음 실행
          </div>
          {nextRunLoading ? (
            <div className="h-4 w-48 rounded bg-slate-800 animate-pulse" />
          ) : (
            <p className="text-[13px] font-mono text-slate-300">
              {formatNextRun(nextRunTime, timezone)}
            </p>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center justify-between gap-3 pt-1">
          {/* 즉시 실행 */}
          <button
            type="button"
            onClick={handleTriggerNow}
            disabled={triggerLoading || saveLoading}
            className="
              inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg
              border border-slate-700 bg-slate-800/60 hover:bg-slate-800
              text-xs font-mono text-slate-300 hover:text-slate-100
              disabled:opacity-40 disabled:cursor-not-allowed
              transition-colors
            "
          >
            {triggerLoading ? (
              <span className="w-3 h-3 border-2 border-slate-600 border-t-slate-300 rounded-full animate-spin" />
            ) : (
              <span className="text-emerald-400 text-[11px]">&#x25B6;</span>
            )}
            즉시 실행
          </button>

          {/* 저장 */}
          <button
            type="button"
            onClick={handleSave}
            disabled={saveLoading || triggerLoading || (!currentCron && presetValue === CUSTOM_VALUE)}
            className="
              inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg
              bg-cyan-600 hover:bg-cyan-500
              disabled:bg-slate-800 disabled:text-slate-600
              text-xs font-semibold text-white
              transition-colors shadow-sm shadow-cyan-900/40
            "
          >
            {saveLoading ? (
              <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
            ) : (
              <span className="text-[11px]">&#x1F4BE;</span>
            )}
            저장
          </button>
        </div>
      </div>
    </div>
  );
}
