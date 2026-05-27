/**
 * WorkflowDeleteConfirmModal
 *
 * 워크플로우 cascade 삭제 확인 모달.
 * 마운트 시 /delete-preview 로 영향 범위를 조회한 뒤,
 * 워크플로우 id 를 직접 입력해야 "삭제" 버튼이 활성된다.
 *
 * 스타일: knowledge/EdgeInspectorPanel 모달과 동일 톤
 * (slate-900 + backdrop-blur, 진입·퇴장 애니메이션)
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import { workflowApi } from '../../services/api';
import type { WorkflowDeletePreview } from '../../types';
import { useToast } from '../common/Toast';

interface WorkflowDeleteConfirmModalProps {
  workflowId: string;
  workflowName: string;
  onClose: () => void;
  onDeleted: () => void;
}

export function WorkflowDeleteConfirmModal({
  workflowId,
  workflowName,
  onClose,
  onDeleted,
}: WorkflowDeleteConfirmModalProps) {
  const { toast } = useToast();

  // ─── 애니메이션 상태 ─────────────────────────────────────────────────────────
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(t);
  }, []);

  const handleClose = useCallback(() => {
    setVisible(false);
    setTimeout(onClose, 300);
  }, [onClose]);

  // ─── ESC 닫기 ────────────────────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handleClose]);

  // ─── 백드롭 클릭 닫기 ────────────────────────────────────────────────────────
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) handleClose();
    },
    [handleClose],
  );

  // ─── Preview 로드 ─────────────────────────────────────────────────────────────
  const [preview, setPreview] = useState<WorkflowDeletePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(true);
  const [previewError, setPreviewError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setPreviewLoading(true);
    setPreviewError(null);
    workflowApi
      .deletePreview(workflowId)
      .then((data) => {
        if (!cancelled) setPreview(data);
      })
      .catch((e) => {
        if (!cancelled)
          setPreviewError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setPreviewLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workflowId]);

  // ─── 확인 입력 ───────────────────────────────────────────────────────────────
  const [confirmInput, setConfirmInput] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!previewLoading && inputRef.current) {
      inputRef.current.focus();
    }
  }, [previewLoading]);

  const canDelete = confirmInput === workflowId;

  // ─── 삭제 실행 ───────────────────────────────────────────────────────────────
  const [deleting, setDeleting] = useState(false);

  const handleDelete = useCallback(async () => {
    if (!canDelete || deleting) return;
    setDeleting(true);
    try {
      const result = await workflowApi.delete(workflowId);
      const c = result.cascadeCounts;
      toast.success(
        `"${workflowName}" 및 인스턴스 ${c.instances}건 · 창고 ${c.warehouseEntries}건 삭제됨`,
        5000,
      );
      onDeleted();
      handleClose();
    } catch (e) {
      toast.error(`삭제 실패: ${e instanceof Error ? e.message : String(e)}`);
      setDeleting(false);
    }
  }, [canDelete, deleting, workflowId, workflowName, toast, onDeleted, handleClose]);

  // ─── 렌더 ────────────────────────────────────────────────────────────────────
  return (
    <>
      {/* 백드롭 */}
      <div
        className={`fixed inset-0 z-40 bg-black/70 backdrop-blur-sm transition-opacity duration-300 ${
          visible ? 'opacity-100' : 'opacity-0'
        }`}
        onClick={handleBackdropClick}
      />

      {/* 모달 */}
      <div
        className={`fixed inset-0 z-50 flex items-center justify-center transition-opacity duration-300 ${
          visible ? 'opacity-100' : 'opacity-0'
        } pointer-events-none`}
      >
        <div
          className={`w-full max-w-md bg-slate-900 rounded-2xl shadow-2xl border border-slate-800 flex flex-col transition-transform duration-300 ease-out pointer-events-auto mx-4 ${
            visible ? 'scale-100' : 'scale-95'
          }`}
          onClick={(e) => e.stopPropagation()}
        >
          {/* 헤더 */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 flex-shrink-0">
            <div className="flex items-center gap-2">
              <span className="text-amber-400 text-base leading-none select-none">⚠</span>
              <span className="text-sm font-semibold text-slate-100">
                워크플로 삭제 — 되돌릴 수 없습니다
              </span>
            </div>
            <button
              type="button"
              onClick={handleClose}
              className="w-7 h-7 rounded flex items-center justify-center text-slate-500 hover:text-slate-200 hover:bg-slate-800 transition-colors flex-shrink-0"
              aria-label="닫기"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path
                  d="M1 1l12 12M13 1L1 13"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          </div>

          {/* 본문 */}
          <div className="px-6 py-5 space-y-5">
            {/* 워크플로 정보 */}
            <div className="rounded-lg bg-slate-800/60 border border-slate-700/60 px-4 py-3 space-y-1">
              <div className="flex items-baseline gap-2">
                <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">
                  워크플로
                </span>
              </div>
              <div className="text-sm font-medium text-slate-100">{workflowName}</div>
              <div className="text-[11px] font-mono text-slate-500 break-all">{workflowId}</div>
            </div>

            {/* 영향 범위 */}
            <div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-2">
                함께 삭제될 데이터
              </div>
              {previewLoading ? (
                <div className="flex items-center gap-2 py-2">
                  <div className="w-4 h-4 border-2 border-slate-700 border-t-amber-500 rounded-full animate-spin" />
                  <span className="text-xs text-slate-500">영향 범위 조회 중…</span>
                </div>
              ) : previewError ? (
                <div className="text-xs text-red-400 font-mono">{previewError}</div>
              ) : preview ? (
                <ul className="space-y-1.5">
                  <ImpactRow
                    label="실행 인스턴스"
                    count={preview.instanceCount}
                    warn={preview.instanceCount > 0}
                  />
                  <ImpactRow
                    label="창고(warehouse) 엔트리"
                    count={preview.warehouseEntryCount}
                    warn={preview.warehouseEntryCount > 0}
                  />
                  <ImpactRow
                    label="노드 결과"
                    count={preview.nodeResultCount}
                    warn={preview.nodeResultCount > 0}
                  />
                </ul>
              ) : null}
            </div>

            {/* 확인 입력 */}
            <div>
              <label className="block text-[11px] font-mono text-slate-400 mb-1.5">
                계속하려면 워크플로 id 를 입력하세요
              </label>
              <input
                ref={inputRef}
                type="text"
                value={confirmInput}
                onChange={(e) => setConfirmInput(e.target.value)}
                placeholder={workflowId}
                disabled={deleting}
                className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-sm font-mono text-slate-200 placeholder-slate-700 focus:outline-none focus:border-amber-600/60 transition-colors disabled:opacity-50"
              />
              {confirmInput.length > 0 && !canDelete && (
                <p className="mt-1 text-[10px] font-mono text-red-400">
                  id 가 일치하지 않습니다
                </p>
              )}
            </div>
          </div>

          {/* 푸터 */}
          <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-slate-800 flex-shrink-0">
            <button
              type="button"
              onClick={handleClose}
              disabled={deleting}
              className="px-4 py-2 rounded-lg text-sm font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors disabled:opacity-50"
            >
              취소
            </button>
            <button
              type="button"
              onClick={handleDelete}
              disabled={!canDelete || deleting}
              className="px-4 py-2 rounded-lg text-sm font-medium bg-red-600/20 border border-red-600/40 text-red-300 hover:bg-red-600/40 hover:border-red-500/60 hover:text-red-100 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {deleting ? '삭제 중…' : '삭제 (영원히)'}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

// ─── 내부 서브 컴포넌트 ───────────────────────────────────────────────────────

function ImpactRow({ label, count, warn }: { label: string; count: number; warn: boolean }) {
  return (
    <li className="flex items-center gap-2">
      <span
        className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
          warn ? 'bg-amber-500' : 'bg-slate-700'
        }`}
      />
      <span className="text-[12px] font-mono text-slate-400 flex-1">{label}</span>
      <span
        className={`text-[12px] font-mono font-semibold ${
          warn ? 'text-amber-300' : 'text-slate-600'
        }`}
      >
        {count.toLocaleString()}건
      </span>
    </li>
  );
}

export default WorkflowDeleteConfirmModal;
