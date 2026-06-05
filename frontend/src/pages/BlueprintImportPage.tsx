/**
 * BlueprintImportPage (`/workflows/import`)
 *
 * 설계도(blueprint) JSON을 붙여넣고 가져오는 페이지.
 *
 * 흐름:
 * 1. textarea 에 blueprint JSON 붙여넣기
 * 2. "미리보기" → dryRun=true → plan + reconciliation 표시
 * 3. "가져오기" → dryRun=false → 성공 시 새 워크플로우 상세로 이동 + 보정 패널
 */
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { blueprintApi, type ImportDryRunResult, type ImportCommitResult, type Reconciliation } from '../services/api';
import { ReconciliationPanel } from '../components/blueprint/ReconciliationPanel';
import { useToast } from '../components/common/Toast';

// ── Plan preview ─────────────────────────────────────────────────────────────

function PlanPreview({ plan }: { plan: ImportDryRunResult['plan'] }) {
  const remapCount = Object.keys(plan.nodeIdRemap).length;
  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900/40 divide-y divide-slate-800">
      <div className="px-5 py-3">
        <div className="text-[10px] font-mono tracking-[0.2em] uppercase text-slate-500 mb-2">가져오기 계획</div>
        <div className="flex flex-wrap gap-4 text-sm text-slate-300">
          <span>
            <span className="text-slate-500 text-xs mr-1">노드</span>
            <strong className="text-sky-300">{plan.nodeCount}</strong>
          </span>
          <span>
            <span className="text-slate-500 text-xs mr-1">연결</span>
            <strong className="text-sky-300">{plan.connectionCount}</strong>
          </span>
          <span>
            <span className="text-slate-500 text-xs mr-1">ID 재매핑</span>
            <strong className="text-slate-200">{remapCount}</strong>
          </span>
        </div>
      </div>

      {/* InstanceDB actions */}
      {plan.instanceDbs.length > 0 && (
        <div className="px-5 py-3">
          <div className="text-[11px] font-mono text-slate-500 mb-2">인스턴스DB 처리</div>
          <div className="space-y-1.5">
            {plan.instanceDbs.map((db) => (
              <div key={db.localId} className="flex items-center gap-3 text-xs font-mono">
                <span className={`px-2 py-0.5 rounded text-[10px] border ${
                  db.action === 'reuse'
                    ? 'bg-emerald-900/30 border-emerald-700/40 text-emerald-300'
                    : 'bg-sky-900/30 border-sky-700/40 text-sky-300'
                }`}>
                  {db.action === 'reuse' ? '재사용' : '신규 생성'}
                </span>
                <span className="text-slate-300">{db.name}</span>
                <span className="text-slate-600">({db.localId})</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Error display ────────────────────────────────────────────────────────────

function ErrorDisplay({ error }: { error: string }) {
  const isBlueprintIncompatible = error.includes('BLUEPRINT_INCOMPATIBLE');
  const isWorkflowInvalid = error.includes('WORKFLOW_INVALID');

  return (
    <div className="rounded-lg border border-rose-700/60 bg-rose-950/30 px-4 py-4 text-sm text-rose-300 space-y-2">
      <div className="font-semibold text-rose-200">
        {isBlueprintIncompatible
          ? '설계도 호환 오류 (BLUEPRINT_INCOMPATIBLE)'
          : isWorkflowInvalid
          ? '워크플로우 구조 오류 (WORKFLOW_INVALID)'
          : '가져오기 오류'}
      </div>
      <div className="text-rose-400/90 text-xs leading-relaxed">{error}</div>
      {isBlueprintIncompatible && (
        <div className="text-xs text-rose-500/80">
          이 설계도는 현재 시스템 버전과 호환되지 않습니다. 올바른 설계도 JSON인지 확인하세요.
        </div>
      )}
      {isWorkflowInvalid && (
        <div className="text-xs text-rose-500/80">
          설계도의 워크플로우 구조가 유효하지 않습니다. 설계도를 내보낸 시스템과 구조 차이가 있을 수 있습니다.
        </div>
      )}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function BlueprintImportPage() {
  const navigate = useNavigate();
  const { toast } = useToast();

  const [jsonText, setJsonText] = useState('');
  const [step, setStep] = useState<'input' | 'preview' | 'done'>('input');

  const [dryRunResult, setDryRunResult] = useState<ImportDryRunResult | null>(null);
  const [commitResult, setCommitResult] = useState<ImportCommitResult | null>(null);
  const [reconciliation, setReconciliation] = useState<Reconciliation | null>(null);

  const [loadingPreview, setLoadingPreview] = useState(false);
  const [loadingCommit, setLoadingCommit] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parseBlueprint = (): unknown | null => {
    const text = jsonText.trim();
    if (!text) {
      setError('설계도 JSON을 붙여넣어 주세요');
      return null;
    }
    try {
      return JSON.parse(text);
    } catch (e) {
      setError(`JSON 파싱 실패: ${e instanceof Error ? e.message : String(e)}`);
      return null;
    }
  };

  const handlePreview = async () => {
    const bp = parseBlueprint();
    if (!bp) return;
    setError(null);
    setLoadingPreview(true);
    try {
      const result = await blueprintApi.import(JSON.stringify(bp), true) as ImportDryRunResult;
      setDryRunResult(result);
      setStep('preview');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleCommit = async () => {
    const bp = parseBlueprint();
    if (!bp) return;
    setError(null);
    setLoadingCommit(true);
    try {
      const result = await blueprintApi.import(JSON.stringify(bp), false) as ImportCommitResult;
      setCommitResult(result);
      setReconciliation(result.reconciliation);
      setStep('done');
      toast.success('워크플로우가 가져와졌습니다');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingCommit(false);
    }
  };

  const handleGoToWorkflow = () => {
    if (commitResult?.workflowId) {
      navigate(`/workflows/${commitResult.workflowId}`);
    }
  };

  return (
    <div className="h-full overflow-auto bg-slate-950">
      <div className="w-full max-w-3xl mx-auto px-6 py-8">
        {/* Header */}
        <header className="mb-8">
          <Link
            to="/workflows"
            className="inline-flex items-center gap-2 text-xs text-slate-500 hover:text-slate-300 transition-colors mb-4 font-mono"
          >
            ← 업무자동화 목록
          </Link>
          <div className="text-[11px] font-mono tracking-[0.25em] uppercase text-slate-500 mb-2">
            업무자동화
          </div>
          <h1 className="text-3xl font-light text-slate-50 tracking-tight flex items-center gap-3">
            <span>설계도 가져오기</span>
          </h1>
          <p className="text-sm text-slate-500 mt-2">
            다른 시스템에서 내보낸 blueprint JSON을 붙여넣어 워크플로우를 가져옵니다.
          </p>
        </header>

        {/* Step indicator */}
        <div className="flex items-center gap-3 mb-8 text-xs font-mono">
          {(['input', 'preview', 'done'] as const).map((s, idx) => {
            const labels = ['1. JSON 입력', '2. 미리보기', '3. 완료'];
            const isActive = s === step;
            const isDone = (step === 'preview' && idx === 0) || (step === 'done' && idx < 2);
            return (
              <span
                key={s}
                className={`px-3 py-1 rounded-full border transition-colors ${
                  isActive
                    ? 'border-sky-600/70 bg-sky-900/30 text-sky-300'
                    : isDone
                    ? 'border-emerald-700/40 bg-emerald-950/20 text-emerald-400'
                    : 'border-slate-700/60 bg-slate-900/20 text-slate-500'
                }`}
              >
                {isDone ? `✓ ${labels[idx]}` : labels[idx]}
              </span>
            );
          })}
        </div>

        {/* ── Step 1: JSON input ─────────────────────────────────────────── */}
        {step === 'input' && (
          <div className="space-y-6">
            <div>
              <label className="block text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-2">
                Blueprint JSON 붙여넣기
              </label>
              <textarea
                value={jsonText}
                onChange={(e) => { setJsonText(e.target.value); setError(null); }}
                rows={18}
                className="w-full px-4 py-3 rounded-xl bg-slate-900 border border-slate-700 text-xs font-mono text-slate-300 focus:outline-none focus:border-sky-600 resize-none leading-relaxed placeholder-slate-600"
                placeholder={'{\n  "blueprintVersion": "1.0",\n  "kind": "workflow-blueprint",\n  ...\n}'}
              />
            </div>

            {error && <ErrorDisplay error={error} />}

            <div className="flex justify-end">
              <button
                onClick={handlePreview}
                disabled={loadingPreview || !jsonText.trim()}
                className="px-6 py-2.5 rounded-xl bg-sky-700/80 hover:bg-sky-600/80 disabled:bg-slate-800 disabled:text-slate-600 text-white text-sm font-medium transition-all inline-flex items-center gap-2 border border-sky-600/50 disabled:border-slate-700"
              >
                {loadingPreview && (
                  <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                )}
                미리보기
              </button>
            </div>
          </div>
        )}

        {/* ── Step 2: Preview ────────────────────────────────────────────── */}
        {step === 'preview' && dryRunResult && (
          <div className="space-y-6">
            <PlanPreview plan={dryRunResult.plan} />

            <div className="border-t border-slate-800 pt-6">
              <div className="text-[10px] font-mono tracking-[0.2em] uppercase text-amber-400 mb-4">보정 미리보기</div>
              <ReconciliationPanel
                workflowId="__preview__"
                reconciliation={dryRunResult.reconciliation}
                onUpdated={() => {}}
                showHeader={true}
              />
            </div>

            {error && <ErrorDisplay error={error} />}

            <div className="flex items-center justify-between gap-3 border-t border-slate-800 pt-4">
              <button
                onClick={() => { setStep('input'); setError(null); }}
                className="px-4 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200 transition-colors"
              >
                ← 뒤로
              </button>
              <button
                onClick={handleCommit}
                disabled={loadingCommit}
                className="px-6 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:bg-sky-900 disabled:text-sky-400/50 text-white text-sm font-semibold transition-colors inline-flex items-center gap-2"
              >
                {loadingCommit && (
                  <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                )}
                가져오기 확정
              </button>
            </div>
          </div>
        )}

        {/* ── Step 3: Done ───────────────────────────────────────────────── */}
        {step === 'done' && commitResult && (
          <div className="space-y-6">
            <div className="rounded-xl border border-emerald-700/40 bg-emerald-950/20 px-6 py-5">
              <div className="flex items-center gap-3 mb-2">
                <span className="text-2xl">✓</span>
                <div>
                  <div className="text-lg font-semibold text-emerald-300">가져오기 완료</div>
                  <div className="text-xs font-mono text-emerald-500 mt-0.5">
                    워크플로우 ID: {commitResult.workflowId}
                  </div>
                </div>
              </div>
              <button
                onClick={handleGoToWorkflow}
                className="mt-3 px-4 py-2 rounded-lg bg-emerald-700/50 hover:bg-emerald-600/50 text-emerald-200 text-sm font-medium transition-colors border border-emerald-600/40"
              >
                워크플로우 상세 보기 →
              </button>
            </div>

            {/* Reconciliation panel after import */}
            {reconciliation && (
              <div className="border-t border-slate-800 pt-6">
                <ReconciliationPanel
                  workflowId={commitResult.workflowId}
                  reconciliation={reconciliation}
                  onUpdated={setReconciliation}
                  showHeader={true}
                />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
