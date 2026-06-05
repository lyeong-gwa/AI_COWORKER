/**
 * ReconciliationPanel
 *
 * 워크플로우 가져오기 후 보정(reconciliation)을 처리하는 재사용 컴포넌트.
 *
 * - materialsToFill: 인증·초기값 입력 (authSecret → password 타입)
 * - knowledge: 카테고리별 충족 상태 + 재매핑 드롭다운
 * - warnings: 경고 목록 표시
 */
import { useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import type {
  Reconciliation,
  ReconciliationMaterialToFill,
  ReconciliationKnowledgeItem,
} from '../../services/api';
import { blueprintApi } from '../../services/api';
import { useToast } from '../common/Toast';

// ── Traffic light status indicator ─────────────────────────────────────────

function KnowledgeStatusDot({ status }: { status: 'satisfied' | 'partial' | 'missing' }) {
  const map = {
    satisfied: { cls: 'bg-emerald-500', label: '충족' },
    partial: { cls: 'bg-amber-400', label: '부분 충족' },
    missing: { cls: 'bg-rose-500', label: '미충족' },
  };
  const { cls, label } = map[status];
  return (
    <span className="inline-flex items-center gap-1.5" title={label}>
      <span className={`inline-block w-2.5 h-2.5 rounded-full flex-shrink-0 ${cls}`} />
      <span className="text-[11px] font-mono text-slate-400">{label}</span>
    </span>
  );
}

// ── Materials section ────────────────────────────────────────────────────────

interface MaterialsProps {
  workflowId: string;
  items: ReconciliationMaterialToFill[];
  onUpdated: (rec: Reconciliation) => void;
}

function MaterialsSection({ workflowId, items, onUpdated }: MaterialsProps) {
  const { toast } = useToast();
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  // Group by nodeRef
  const grouped = useMemo(() => {
    const map = new Map<string, ReconciliationMaterialToFill[]>();
    for (const item of items) {
      const list = map.get(item.nodeRef) ?? [];
      list.push(item);
      map.set(item.nodeRef, list);
    }
    return map;
  }, [items]);

  const key = (item: ReconciliationMaterialToFill) => `${item.nodeRef}::${item.path}`;

  const handleSave = useCallback(async () => {
    const filled = Object.entries(values).filter(([, v]) => v.trim() !== '');
    if (filled.length === 0) {
      toast.warning('입력할 값이 없습니다');
      return;
    }
    setSaving(true);
    try {
      const payload = filled.map(([k, value]) => {
        const [nodeRef, ...rest] = k.split('::');
        return { nodeRef, path: rest.join('::'), value };
      });
      const updated = await blueprintApi.fillMaterials(workflowId, payload);
      toast.success('재료값이 저장되었습니다');
      setValues({});
      onUpdated(updated);
    } catch (e) {
      toast.error(`저장 실패: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  }, [values, workflowId, onUpdated, toast]);

  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-emerald-700/40 bg-emerald-950/20 px-4 py-3 text-xs text-emerald-400">
        모든 재료값이 입력되었습니다.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {Array.from(grouped.entries()).map(([nodeRef, nodeItems]) => (
        <div key={nodeRef} className="rounded-lg border border-slate-700/60 bg-slate-900/40">
          <div className="px-4 py-2 border-b border-slate-700/40">
            <span className="text-[11px] font-mono text-sky-400">{nodeRef}</span>
          </div>
          <div className="px-4 py-3 space-y-3">
            {nodeItems.map((item) => {
              const k = key(item);
              const isSecret = item.kind === 'authSecret' || /secret|token|password|key/i.test(item.path);
              return (
                <div key={k}>
                  <label className="block text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-1.5">
                    {item.path}
                    {isSecret && (
                      <span className="ml-2 px-1.5 py-0.5 rounded bg-amber-900/40 text-amber-400 text-[9px] border border-amber-700/40">
                        인증
                      </span>
                    )}
                  </label>
                  <input
                    type={isSecret ? 'password' : 'text'}
                    value={values[k] ?? ''}
                    onChange={(e) => setValues((v) => ({ ...v, [k]: e.target.value }))}
                    placeholder={`${item.path} 값 입력...`}
                    className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-sm text-slate-200 focus:outline-none focus:border-sky-600 placeholder-slate-600"
                  />
                </div>
              );
            })}
          </div>
        </div>
      ))}

      <button
        onClick={handleSave}
        disabled={saving}
        className="px-5 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:bg-sky-900 disabled:text-sky-400/50 text-white text-sm font-medium transition-colors inline-flex items-center gap-2"
      >
        {saving && <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />}
        저장
      </button>
    </div>
  );
}

// ── Knowledge section ────────────────────────────────────────────────────────

interface KnowledgeProps {
  workflowId: string;
  items: ReconciliationKnowledgeItem[];
  onUpdated: (rec: Reconciliation) => void;
}

function KnowledgeSection({ workflowId, items, onUpdated }: KnowledgeProps) {
  const { toast } = useToast();
  const navigate = useNavigate();
  // remaps: nodeRef::from → chosen "to" category
  const [remaps, setRemaps] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const handleRemap = useCallback(async (nodeRef: string, from: string, to: string) => {
    setSaving(true);
    try {
      const updated = await blueprintApi.knowledgeRemap(workflowId, [{ nodeRef, from, to }]);
      toast.success('카테고리 재매핑이 적용되었습니다');
      onUpdated(updated);
    } catch (e) {
      toast.error(`재매핑 실패: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  }, [workflowId, onUpdated, toast]);

  if (items.length === 0) {
    return (
      <div className="text-xs text-slate-500 italic">지식 요건 없음</div>
    );
  }

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div
          key={`${item.nodeRef}::${item.requirement}`}
          className="rounded-lg border border-slate-700/60 bg-slate-900/30 px-4 py-3"
        >
          <div className="flex items-start justify-between gap-3 mb-2">
            <div className="min-w-0">
              <div className="text-[11px] font-mono text-sky-400 truncate">{item.nodeRef}</div>
              <div className="text-xs text-slate-300 font-medium mt-0.5 truncate">{item.requirement}</div>
            </div>
            <KnowledgeStatusDot status={item.status} />
          </div>

          {item.missingCategories.length > 0 && (
            <div className="mb-2">
              <span className="text-[11px] text-slate-500">미충족 카테고리: </span>
              {item.missingCategories.map((cat) => (
                <span key={cat} className="mr-1 inline-block text-[11px] font-mono px-1.5 py-0.5 rounded bg-rose-900/40 text-rose-300 border border-rose-700/40">
                  {cat}
                </span>
              ))}
            </div>
          )}

          {item.availableCategories.length > 0 && (
            <div className="mb-2">
              <span className="text-[11px] text-slate-500">사용 가능 카테고리: </span>
              {item.availableCategories.map((cat) => (
                <span key={cat} className="mr-1 inline-block text-[11px] font-mono px-1.5 py-0.5 rounded bg-slate-800/60 text-slate-400 border border-slate-700/40">
                  {cat}
                </span>
              ))}
            </div>
          )}

          {/* Remap for missing categories */}
          {item.status !== 'satisfied' && item.missingCategories.length > 0 && item.availableCategories.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2 items-center">
              {item.missingCategories.map((from) => {
                const remapKey = `${item.nodeRef}::${from}`;
                return (
                  <div key={from} className="flex items-center gap-2">
                    <span className="text-[11px] font-mono text-rose-400">{from}</span>
                    <span className="text-[11px] text-slate-500">→</span>
                    <select
                      value={remaps[remapKey] ?? ''}
                      onChange={(e) => setRemaps((r) => ({ ...r, [remapKey]: e.target.value }))}
                      className="px-2 py-1 rounded bg-slate-800 border border-slate-600 text-xs text-slate-200 focus:outline-none focus:border-sky-600"
                    >
                      <option value="">카테고리 선택...</option>
                      {item.availableCategories.map((cat) => (
                        <option key={cat} value={cat}>{cat}</option>
                      ))}
                    </select>
                    <button
                      onClick={() => {
                        const to = remaps[remapKey];
                        if (!to) { toast.warning('카테고리를 선택하세요'); return; }
                        handleRemap(item.nodeRef, from, to);
                      }}
                      disabled={saving || !remaps[remapKey]}
                      className="px-2 py-1 rounded text-[11px] bg-sky-700/60 hover:bg-sky-600/60 text-sky-200 disabled:opacity-40 transition-colors border border-sky-600/40"
                    >
                      적용
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          {/* Link to knowledge page when missing and no available categories */}
          {item.status === 'missing' && item.availableCategories.length === 0 && (
            <button
              onClick={() => navigate('/knowledge')}
              className="mt-2 text-[11px] text-sky-400 hover:text-sky-300 underline underline-offset-2 transition-colors"
            >
              /knowledge 에서 문서 등록하기 →
            </button>
          )}

          {item.suggestedActions.length > 0 && (
            <div className="mt-2 text-[11px] text-slate-500 italic">
              제안: {item.suggestedActions.join(' · ')}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Warnings section ─────────────────────────────────────────────────────────

function WarningsSection({ warnings }: { warnings: Reconciliation['warnings'] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="space-y-2">
      {warnings.map((w, i) => (
        <div
          key={i}
          className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-xs text-amber-300"
        >
          <span className="font-mono text-amber-400 mr-2">[{w.kind}]</span>
          {w.message}
          {w.nodeRef && (
            <span className="ml-2 text-amber-500/70 font-mono">({w.nodeRef})</span>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface ReconciliationPanelProps {
  workflowId: string;
  reconciliation: Reconciliation;
  onUpdated: (rec: Reconciliation) => void;
  /** 패널 헤더 표시 여부 (독립 페이지에서는 false로 사용 가능) */
  showHeader?: boolean;
}

export function ReconciliationPanel({
  workflowId,
  reconciliation,
  onUpdated,
  showHeader = true,
}: ReconciliationPanelProps) {
  const { summary } = reconciliation;
  const allGood =
    summary.materialsToFill === 0 &&
    summary.knowledge.missing === 0 &&
    summary.knowledge.partial === 0 &&
    summary.warnings === 0;

  return (
    <div className="space-y-6">
      {showHeader && (
        <div>
          <div className="text-[10px] font-mono tracking-[0.25em] uppercase text-amber-400 mb-1">
            보정 (Reconciliation)
          </div>
          {/* Summary badges */}
          <div className="flex flex-wrap gap-3 mt-2">
            <span className={`text-xs font-mono px-2.5 py-1 rounded-full border ${
              summary.materialsToFill > 0
                ? 'bg-rose-900/30 border-rose-600/50 text-rose-300'
                : 'bg-emerald-900/20 border-emerald-700/40 text-emerald-400'
            }`}>
              재료 입력 필요: {summary.materialsToFill}
            </span>
            <span className={`text-xs font-mono px-2.5 py-1 rounded-full border ${
              summary.knowledge.missing > 0
                ? 'bg-rose-900/30 border-rose-600/50 text-rose-300'
                : summary.knowledge.partial > 0
                ? 'bg-amber-900/30 border-amber-600/50 text-amber-300'
                : 'bg-emerald-900/20 border-emerald-700/40 text-emerald-400'
            }`}>
              지식: 충족 {summary.knowledge.satisfied} / 부분 {summary.knowledge.partial} / 미충족 {summary.knowledge.missing}
            </span>
            {summary.warnings > 0 && (
              <span className="text-xs font-mono px-2.5 py-1 rounded-full border bg-amber-900/30 border-amber-600/50 text-amber-300">
                경고: {summary.warnings}
              </span>
            )}
          </div>

          {allGood && (
            <div className="mt-3 rounded-lg border border-emerald-700/40 bg-emerald-950/20 px-4 py-2.5 text-sm text-emerald-400">
              모든 보정이 완료되었습니다. 워크플로우를 바로 실행할 수 있습니다.
            </div>
          )}
        </div>
      )}

      {/* Materials */}
      {reconciliation.materialsToFill.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
            재료 입력
            <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-rose-900/40 text-rose-300 border border-rose-700/40">
              {reconciliation.materialsToFill.length}
            </span>
          </h3>
          <MaterialsSection
            workflowId={workflowId}
            items={reconciliation.materialsToFill}
            onUpdated={onUpdated}
          />
        </section>
      )}

      {/* Knowledge */}
      {reconciliation.knowledge.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
            지식 카테고리 매핑
          </h3>
          <KnowledgeSection
            workflowId={workflowId}
            items={reconciliation.knowledge}
            onUpdated={onUpdated}
          />
        </section>
      )}

      {/* Warnings */}
      {reconciliation.warnings.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
            경고
            <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-amber-900/40 text-amber-300 border border-amber-700/40">
              {reconciliation.warnings.length}
            </span>
          </h3>
          <WarningsSection warnings={reconciliation.warnings} />
        </section>
      )}
    </div>
  );
}
