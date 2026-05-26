/**
 * LintRunModal — Karpathy v2 lint 실행 모달
 *
 * 옵션: categories 멀티셀렉트, dry_run 토글, llm_enabled 토글
 * 실행 후 응답 → LintReportViewer 에 전달
 */
import { useState } from 'react';
import { knowledgeApi } from '../../services/api';
import type { LintReport } from '../../types';
import { LintReportViewer } from './LintReportViewer';

interface LintRunModalProps {
  /** 사용 가능한 카테고리 목록 */
  categories: string[];
  onClose: () => void;
}

export function LintRunModal({ categories, onClose }: LintRunModalProps) {
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [dryRun, setDryRun] = useState(true);
  const [llmEnabled, setLlmEnabled] = useState(false);
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState<LintReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toggleCategory = (cat: string) => {
    setSelectedCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat],
    );
  };

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    setReport(null);
    try {
      const result = await knowledgeApi.runLint({
        categories: selectedCategories.length > 0 ? selectedCategories : null,
        dry_run: dryRun,
        llm_enabled: llmEnabled,
      });
      setReport(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-2xl bg-slate-900 border border-slate-700 rounded-xl shadow-2xl flex flex-col max-h-[90vh]">
        {/* 헤더 */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <div>
            <h2 className="text-base font-semibold text-slate-50">Lint 실행</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              위키 전체 점검 — 정적(schema/깨진 링크/고아) + 동적(LLM)
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-500 hover:text-slate-300 text-xl leading-none px-1"
          >
            ×
          </button>
        </div>

        {/* 옵션 */}
        {!report && (
          <div className="px-5 py-4 space-y-4 border-b border-slate-800">
            {/* 카테고리 멀티셀렉트 */}
            {categories.length > 0 && (
              <div>
                <label className="block text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-2">
                  카테고리 필터 (미선택 = 전체)
                </label>
                <div className="flex flex-wrap gap-2">
                  {categories.map((cat) => (
                    <button
                      key={cat}
                      type="button"
                      onClick={() => toggleCategory(cat)}
                      className={`px-2.5 py-1 rounded-full text-xs font-mono border transition-colors ${
                        selectedCategories.includes(cat)
                          ? 'bg-sky-600 border-sky-500 text-white'
                          : 'bg-slate-800/60 border-slate-700 text-slate-400 hover:border-slate-600'
                      }`}
                    >
                      {cat}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* 토글 옵션 */}
            <div className="flex gap-6">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={dryRun}
                  onChange={(e) => setDryRun(e.target.checked)}
                  className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500"
                />
                <span className="text-sm text-slate-300">Dry Run</span>
                <span className="text-[11px] text-slate-600">(정적 검사만, LLM 0호출)</span>
              </label>

              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={llmEnabled}
                  onChange={(e) => setLlmEnabled(e.target.checked)}
                  disabled={dryRun}
                  className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500 disabled:opacity-40"
                />
                <span className={`text-sm ${dryRun ? 'text-slate-600' : 'text-slate-300'}`}>
                  LLM 동적 검사
                </span>
                <span className="text-[11px] text-slate-600">(중복·모순·구식)</span>
              </label>
            </div>

            {error && (
              <div className="text-xs text-red-400 bg-red-950/40 border border-red-900/40 rounded-lg px-3 py-2">
                {error}
              </div>
            )}
          </div>
        )}

        {/* 결과 영역 */}
        {report && (
          <div className="flex-1 overflow-auto px-5 py-4">
            <LintReportViewer report={report} />
          </div>
        )}

        {/* 액션 버튼 */}
        <div className="flex gap-2 justify-end px-5 py-4 border-t border-slate-800">
          {report ? (
            <>
              <button
                type="button"
                onClick={() => setReport(null)}
                className="px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800/60 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors"
              >
                ↩ 다시 설정
              </button>
              <button
                type="button"
                onClick={onClose}
                className="px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-100 text-xs font-medium transition-colors"
              >
                닫기
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={onClose}
                disabled={running}
                className="px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-900/60 hover:bg-slate-800 text-slate-300 text-xs font-medium transition-colors disabled:opacity-50"
              >
                취소
              </button>
              <button
                type="button"
                onClick={handleRun}
                disabled={running}
                className="px-4 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-medium transition-colors disabled:opacity-60 min-w-[80px]"
              >
                {running ? '실행 중…' : '▶ 실행'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
