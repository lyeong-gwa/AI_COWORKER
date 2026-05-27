/**
 * RecordsClearConfirmModal
 *
 * records 전체 비우기 전 강한 confirm 모달.
 * 사용자가 idbId 를 직접 입력해야 "비우기" 버튼이 활성화된다.
 */
import { useState, useRef, useEffect } from 'react';

interface Props {
  idbId: string;
  idbName: string;
  recordCount: number;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
}

export function RecordsClearConfirmModal({
  idbId,
  idbName,
  recordCount,
  onConfirm,
  onCancel,
}: Props) {
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const isMatched = inputValue === idbId;

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function handleConfirm() {
    if (!isMatched || loading) return;
    setLoading(true);
    try {
      await onConfirm();
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Escape') onCancel();
    if (e.key === 'Enter' && isMatched) handleConfirm();
  }

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        className="w-full max-w-md mx-4 rounded-xl border border-red-800/60 bg-slate-900 shadow-2xl shadow-black/60"
        onKeyDown={handleKeyDown}
      >
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-slate-800">
          <div className="flex items-center gap-2.5">
            <span className="text-2xl">⚠</span>
            <div>
              <h2 className="text-base font-semibold text-red-400">
                records 전체 비우기 — 되돌릴 수 없습니다
              </h2>
            </div>
          </div>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-4">
          {/* Info rows */}
          <div className="space-y-1.5 text-sm">
            <div className="flex gap-2">
              <span className="text-slate-500 w-28 flex-shrink-0">인스턴스DB</span>
              <span className="text-slate-200 font-medium">
                {idbName}{' '}
                <span className="font-mono text-slate-500 text-xs">({idbId})</span>
              </span>
            </div>
            <div className="flex gap-2">
              <span className="text-slate-500 w-28 flex-shrink-0">현재 records</span>
              <span className="text-slate-200 font-medium">{recordCount}건</span>
            </div>
          </div>

          {/* Notice */}
          <div className="rounded-lg bg-slate-800/60 border border-slate-700/50 px-4 py-3 text-xs text-slate-400 leading-relaxed space-y-1">
            <div className="flex gap-1.5">
              <span className="text-sky-400 flex-shrink-0">ⓘ</span>
              <span>
                인스턴스DB 메타(스키마·이름)는 유지됩니다.
              </span>
            </div>
            <div className="flex gap-1.5">
              <span className="text-sky-400 flex-shrink-0">ⓘ</span>
              <span>
                워크플로우의 sorter 룰이 다음 실행부터 다시 신규로 인식합니다.
              </span>
            </div>
          </div>

          {/* Confirmation input */}
          <div>
            <label className="block text-xs text-slate-400 mb-1.5">
              계속하려면 인스턴스DB id 를 정확히 입력하세요:
            </label>
            <div className="relative">
              <input
                ref={inputRef}
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder={idbId}
                spellCheck={false}
                className={`w-full px-3 py-2 rounded-lg border text-sm font-mono transition-colors bg-slate-950 text-slate-200 placeholder-slate-700 focus:outline-none ${
                  inputValue === ''
                    ? 'border-slate-700'
                    : isMatched
                    ? 'border-green-600/70 focus:border-green-500'
                    : 'border-red-700/70 focus:border-red-600'
                }`}
              />
              {inputValue !== '' && (
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm">
                  {isMatched ? (
                    <span className="text-green-400">✓</span>
                  ) : (
                    <span className="text-red-400">✗</span>
                  )}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 pb-6 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors disabled:opacity-50"
          >
            취소
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!isMatched || loading}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              isMatched && !loading
                ? 'bg-red-700 hover:bg-red-600 text-white'
                : 'bg-slate-800 text-slate-600 cursor-not-allowed'
            }`}
          >
            {loading ? '비우는 중…' : '비우기 (영원히)'}
          </button>
        </div>
      </div>
    </div>
  );
}
