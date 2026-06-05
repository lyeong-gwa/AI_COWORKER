/**
 * BlueprintExportModal
 *
 * 워크플로우 설계도(blueprint)를 내보내는 모달.
 * - 백엔드에서 받은 JSON을 pretty-print 로 textarea 에 표시
 * - "복사" 버튼으로 클립보드 복사
 * - redactedFields 개수 표시 + 안내 메시지
 */
import { useEffect, useState } from 'react';
import { blueprintApi, type Blueprint } from '../../services/api';
import { useToast } from '../common/Toast';

interface Props {
  workflowId: string;
  workflowName: string;
  onClose: () => void;
}

export function BlueprintExportModal({ workflowId, workflowName, onClose }: Props) {
  const { toast } = useToast();
  const [blueprint, setBlueprint] = useState<Blueprint | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    blueprintApi
      .export(workflowId)
      .then((bp) => {
        if (!cancelled) setBlueprint(bp);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workflowId]);

  const jsonText = blueprint ? JSON.stringify(blueprint, null, 2) : '';
  const redactedCount = blueprint?.redactedFields?.length ?? 0;

  const handleCopy = async () => {
    if (!jsonText) return;
    try {
      await navigator.clipboard.writeText(jsonText);
      setCopied(true);
      toast.success('클립보드에 복사되었습니다');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('복사 실패 — 수동으로 선택 후 복사하세요');
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-2xl rounded-xl bg-slate-900 border border-slate-700 shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex-shrink-0">
          <div className="text-[10px] font-mono tracking-[0.25em] uppercase text-sky-400 mb-1">
            설계도 내보내기
          </div>
          <h2 className="text-lg font-semibold text-slate-50 truncate">{workflowName}</h2>
          <p className="text-xs text-slate-500 mt-0.5 font-mono">
            blueprint · {blueprint?.blueprintVersion ?? '—'} · {blueprint ? new Date(blueprint.exportedAt).toLocaleString('ko-KR') : '—'}
          </p>
        </div>

        {/* Body */}
        <div className="flex-1 min-h-0 overflow-auto px-6 py-5 space-y-4">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="flex flex-col items-center gap-3">
                <div className="w-7 h-7 border-2 border-slate-700 border-t-sky-500 rounded-full animate-spin" />
                <span className="text-xs text-slate-500 font-mono">설계도 생성 중...</span>
              </div>
            </div>
          ) : error ? (
            <div className="rounded-lg border border-rose-700/60 bg-rose-950/40 px-4 py-3 text-sm text-rose-300">
              내보내기 실패: {error}
            </div>
          ) : (
            <>
              {/* Redacted notice */}
              {redactedCount > 0 && (
                <div className="rounded-lg border border-amber-700/50 bg-amber-950/30 px-4 py-3 text-xs text-amber-300 leading-relaxed">
                  <strong className="font-semibold">보안 주의</strong> — 인증 정보 및 초기 입력값({redactedCount}개 필드)은 제거되어 있습니다.
                  받는 쪽에서 가져오기 후 <strong>보정(reconciliation)</strong> 단계에서 실제 값을 입력해야 합니다.
                </div>
              )}

              {/* JSON textarea */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-[11px] font-mono uppercase tracking-wider text-slate-400">
                    blueprint JSON
                  </label>
                  <button
                    onClick={handleCopy}
                    className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                      copied
                        ? 'bg-emerald-700/50 text-emerald-300 border border-emerald-600/50'
                        : 'bg-slate-800 text-slate-300 border border-slate-700 hover:bg-slate-700 hover:text-slate-100'
                    }`}
                  >
                    {copied ? '복사됨 ✓' : '복사'}
                  </button>
                </div>
                <textarea
                  readOnly
                  value={jsonText}
                  rows={20}
                  className="w-full px-3 py-3 rounded-lg bg-slate-950 border border-slate-700 text-xs font-mono text-slate-300 focus:outline-none focus:border-sky-700 resize-none leading-relaxed"
                  onClick={(e) => (e.target as HTMLTextAreaElement).select()}
                />
              </div>

              {/* Stats */}
              {blueprint && (
                <div className="flex flex-wrap gap-4 text-[11px] font-mono text-slate-500">
                  <span>노드: {Object.keys((blueprint.workflow as any)?.nodes ?? {}).length > 0
                    ? ((blueprint.workflow as any)?.nodes?.length ?? '—')
                    : (blueprint.workflow as any)?.nodes?.length ?? '—'}</span>
                  <span>인스턴스DB: {blueprint.dependencies.instanceDbs.length}</span>
                  <span>지식 카테고리: {blueprint.dependencies.knowledge.length}</span>
                  <span className="text-amber-500/80">제거된 민감 필드: {redactedCount}</span>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-800 flex-shrink-0 flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium transition-colors"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}
