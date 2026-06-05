/**
 * ResyncModal
 *
 * 워크플로우 스냅샷 재동기화 모달.
 * 1. 열릴 때 dryRun=true 로 변경 미리보기 조회
 * 2. 사용자가 "적용" 클릭 시 dryRun=false 로 실제 적용
 */
import { useEffect, useState } from 'react';
import { workflowApi } from '../../services/api';
import { useToast } from '../common/Toast';

interface ResyncNode {
  nodeId: string;
  definitionType: string;
  changed: boolean;
  changedFields: string[];
  unsyncable?: boolean;
  reason?: string;
}

interface Props {
  workflowId: string;
  workflowName: string;
  onClose: () => void;
  onApplied: () => void;
}

export function ResyncModal({ workflowId, workflowName, onClose, onApplied }: Props) {
  const { toast } = useToast();
  const [nodes, setNodes] = useState<ResyncNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    workflowApi
      .resyncSnapshots(workflowId, { dryRun: true })
      .then((res) => {
        if (!cancelled) setNodes(res.nodes);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [workflowId]);

  const changedCount = nodes.filter((n) => n.changed && !n.unsyncable).length;
  const unsyncableCount = nodes.filter((n) => n.unsyncable).length;

  const handleApply = async () => {
    setApplying(true);
    try {
      await workflowApi.resyncSnapshots(workflowId, { dryRun: false });
      toast.success('재동기화가 적용되었습니다');
      setApplied(true);
      onApplied();
    } catch (e) {
      toast.error(`재동기화 실패: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setApplying(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget && !applying) onClose();
      }}
    >
      <div className="w-full max-w-2xl rounded-xl bg-slate-900 border border-slate-700 shadow-2xl flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex-shrink-0">
          <div className="text-[10px] font-mono tracking-[0.25em] uppercase text-sky-400 mb-1">
            스냅샷 재동기화
          </div>
          <h2 className="text-lg font-semibold text-slate-50 truncate">{workflowName}</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            최신 API·AI 명세를 노드 스냅샷으로 반영합니다. 아래 변경 내역을 확인 후 적용하세요.
          </p>
        </div>

        {/* Body */}
        <div className="flex-1 min-h-0 overflow-auto px-6 py-5 space-y-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="flex flex-col items-center gap-3">
                <div className="w-7 h-7 border-2 border-slate-700 border-t-sky-500 rounded-full animate-spin" />
                <span className="text-xs text-slate-500 font-mono">변경 내역 분석 중...</span>
              </div>
            </div>
          ) : error ? (
            <div className="rounded-lg border border-rose-700/60 bg-rose-950/40 px-4 py-3 text-sm text-rose-300">
              미리보기 실패: {error}
            </div>
          ) : applied ? (
            <div className="rounded-lg border border-emerald-700/40 bg-emerald-950/20 px-4 py-4 text-sm text-emerald-400 text-center">
              재동기화가 성공적으로 적용되었습니다.
            </div>
          ) : (
            <>
              {/* Summary */}
              <div className="flex flex-wrap gap-3 text-xs font-mono">
                <span className="px-2.5 py-1 rounded-full border border-slate-700/60 bg-slate-800/40 text-slate-400">
                  전체 노드: {nodes.length}
                </span>
                <span className={`px-2.5 py-1 rounded-full border ${
                  changedCount > 0
                    ? 'bg-sky-900/30 border-sky-600/50 text-sky-300'
                    : 'bg-slate-800/40 border-slate-700/60 text-slate-400'
                }`}>
                  변경: {changedCount}
                </span>
                {unsyncableCount > 0 && (
                  <span className="px-2.5 py-1 rounded-full border bg-amber-900/30 border-amber-600/50 text-amber-300">
                    동기화 불가: {unsyncableCount}
                  </span>
                )}
              </div>

              {nodes.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-700 py-8 text-center text-sm text-slate-500">
                  동기화할 노드가 없습니다.
                </div>
              ) : (
                <div className="space-y-2">
                  {nodes.map((node) => (
                    <div
                      key={node.nodeId}
                      className={`rounded-lg border px-4 py-3 ${
                        node.unsyncable
                          ? 'border-amber-700/40 bg-amber-950/10'
                          : node.changed
                          ? 'border-sky-700/40 bg-sky-950/20'
                          : 'border-slate-700/40 bg-slate-900/20'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-[11px] font-mono text-slate-400 truncate">{node.nodeId}</div>
                          <div className="text-xs text-slate-300 font-medium mt-0.5">{node.definitionType}</div>
                        </div>
                        <span className={`flex-shrink-0 text-[11px] font-mono px-2 py-0.5 rounded ${
                          node.unsyncable
                            ? 'bg-amber-900/40 text-amber-300'
                            : node.changed
                            ? 'bg-sky-900/40 text-sky-300'
                            : 'bg-slate-800/60 text-slate-500'
                        }`}>
                          {node.unsyncable ? '동기화 불가' : node.changed ? '변경됨' : '변경 없음'}
                        </span>
                      </div>

                      {node.unsyncable && node.reason && (
                        <div className="mt-2 text-[11px] text-amber-400 italic">{node.reason}</div>
                      )}

                      {node.changed && node.changedFields.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {node.changedFields.map((f) => (
                            <span
                              key={f}
                              className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800/60 text-slate-400 border border-slate-700/40"
                            >
                              {f}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-800 flex-shrink-0 flex items-center justify-between gap-3">
          <button
            onClick={onClose}
            disabled={applying}
            className="px-4 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200 transition-colors disabled:opacity-40"
          >
            {applied ? '닫기' : '취소'}
          </button>
          {!applied && !loading && !error && (
            <button
              onClick={handleApply}
              disabled={applying || changedCount === 0}
              className="px-5 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:bg-slate-800 disabled:text-slate-600 text-white text-sm font-medium transition-colors inline-flex items-center gap-2"
            >
              {applying && (
                <span className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
              )}
              {applying ? '적용 중...' : `적용 (${changedCount}개 노드)`}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
