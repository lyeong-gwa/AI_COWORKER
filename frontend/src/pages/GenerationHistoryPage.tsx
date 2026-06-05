/**
 * GenerationHistoryPage (`/workflows/generation-history`)
 *
 * 워크플로우 채팅 생성 히스토리 뷰어.
 * 좌측: 트레이스 요약 목록 (최신순)
 * 우측: 선택한 트레이스 전체 상세
 *   - 헤더 (traceId, 질문, mode, 결과, baseDraftProvided)
 *   - LLM 호출 타임라인 (callType, durationMs, tokenUsage, systemPrompt/prompt/response 토글)
 *   - 검증 이력 (attempt별 valid/err/warn + 이슈 목록)
 *   - 산출물 (finalDraft 노드·연결 요약 + JSON 접기/펼치기)
 *   - 최종 검증 배지
 */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  generationTraceApi,
  type GenerationTraceSummary,
  type GenerationTraceDetail,
  type LlmCall,
  type ValidationAttempt,
  type ValidationIssueDetail,
} from '../services/api';
import { useToast } from '../components/common/Toast';

// ─── 유틸 ─────────────────────────────────────────────────────────────────────

function formatLocalDateTime(iso: string): string {
  try {
    const d = new Date(iso);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
  } catch {
    return iso;
  }
}

function formatMs(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms}ms`;
}

// ─── 결과 배지 ───────────────────────────────────────────────────────────────

type TraceResult = 'valid' | 'invalid' | 'error';

const RESULT_THEME: Record<TraceResult, { bg: string; text: string; border: string; dot: string; label: string }> = {
  valid: {
    bg: 'bg-emerald-900/30',
    text: 'text-emerald-300',
    border: 'border-emerald-700/60',
    dot: 'bg-emerald-400',
    label: '성공',
  },
  invalid: {
    bg: 'bg-amber-900/30',
    text: 'text-amber-300',
    border: 'border-amber-700/60',
    dot: 'bg-amber-400',
    label: '검증 실패',
  },
  error: {
    bg: 'bg-rose-900/30',
    text: 'text-rose-300',
    border: 'border-rose-700/60',
    dot: 'bg-rose-400',
    label: '오류',
  },
};

function ResultBadge({ result, size = 'sm' }: { result: TraceResult; size?: 'xs' | 'sm' }) {
  const theme = RESULT_THEME[result] ?? RESULT_THEME.error;
  const sizeClass = size === 'xs' ? 'text-[10px] px-1.5 py-0.5 gap-1' : 'text-xs px-2.5 py-1 gap-1.5';
  const dotSize = size === 'xs' ? 'w-1.5 h-1.5' : 'w-2 h-2';
  return (
    <span className={`inline-flex items-center rounded-full border font-mono tracking-wide ${sizeClass} ${theme.bg} ${theme.text} ${theme.border}`}>
      <span className={`${dotSize} rounded-full flex-shrink-0 ${theme.dot}`} />
      <span className="uppercase">{theme.label}</span>
    </span>
  );
}

// ─── 섹션 헤더 ───────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-500 mb-2">
      {children}
    </div>
  );
}

// ─── 이슈 아이템 ─────────────────────────────────────────────────────────────

function IssueItem({ issue }: { issue: ValidationIssueDetail }) {
  const isError = issue.severity === 'error';
  return (
    <div
      className={`rounded-md px-3 py-2 text-xs border ${
        isError
          ? 'bg-red-950/40 border-red-800/50 text-red-200'
          : 'bg-amber-950/30 border-amber-800/40 text-amber-200'
      }`}
    >
      <span className={`font-mono mr-1.5 ${isError ? 'text-red-400' : 'text-amber-400'}`}>
        [{issue.code}]
      </span>
      {issue.nodeName && (
        <span className={`mr-1 ${isError ? 'text-red-300' : 'text-amber-300'}`}>
          {issue.nodeName}:
        </span>
      )}
      {issue.message}
    </div>
  );
}

// ─── LLM 호출 카드 ───────────────────────────────────────────────────────────

const CALL_TYPE_COLOR: Record<string, string> = {
  stage_a: 'text-sky-400 border-sky-700/60 bg-sky-900/20',
  stage_b: 'text-violet-400 border-violet-700/60 bg-violet-900/20',
  repair: 'text-amber-400 border-amber-700/60 bg-amber-900/20',
  plan: 'text-teal-400 border-teal-700/60 bg-teal-900/20',
  assemble: 'text-blue-400 border-blue-700/60 bg-blue-900/20',
  validate_repair: 'text-orange-400 border-orange-700/60 bg-orange-900/20',
};

function LlmCallCard({ call, index }: { call: LlmCall; index: number }) {
  const [open, setOpen] = useState(false);
  const [showSystem, setShowSystem] = useState(false);

  const colorClass =
    CALL_TYPE_COLOR[call.callType] ??
    'text-slate-400 border-slate-700/60 bg-slate-800/20';

  const tokens = call.tokenUsage;
  const totalTokens = tokens?.total_tokens ?? (
    (tokens?.prompt_tokens ?? 0) + (tokens?.completion_tokens ?? 0)
  );

  return (
    <div className="border border-slate-800 rounded-xl overflow-hidden">
      {/* 카드 헤더 */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-slate-800/40 transition-colors text-left"
      >
        {/* 순서 */}
        <span className="flex-shrink-0 w-6 h-6 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-[10px] font-mono text-slate-400">
          {index + 1}
        </span>

        {/* callType 라벨 */}
        <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-mono font-semibold ${colorClass}`}>
          {call.callType}
        </span>

        {/* ok 배지 */}
        {call.ok ? (
          <span className="text-[10px] font-mono text-emerald-400">✓ OK</span>
        ) : (
          <span className="text-[10px] font-mono text-rose-400">✗ FAIL</span>
        )}

        {/* 소요 시간 */}
        <span className="text-[11px] font-mono text-slate-500 ml-auto flex-shrink-0">
          {formatMs(call.durationMs)}
        </span>

        {/* 토큰 */}
        {totalTokens > 0 && (
          <span className="text-[11px] font-mono text-slate-500 flex-shrink-0 ml-2">
            {totalTokens.toLocaleString()} tok
          </span>
        )}

        {/* 펼치기 토글 */}
        <span className="text-slate-600 flex-shrink-0 ml-2 text-xs">
          {open ? '▲' : '▼'}
        </span>
      </button>

      {/* 펼쳐진 내용 */}
      {open && (
        <div className="border-t border-slate-800 bg-slate-950/40 px-4 py-3 space-y-3">
          {/* 토큰 상세 */}
          {tokens && (tokens.prompt_tokens || tokens.completion_tokens) && (
            <div className="flex gap-4 text-[11px] font-mono text-slate-500">
              {tokens.prompt_tokens != null && (
                <span>입력 {tokens.prompt_tokens.toLocaleString()}</span>
              )}
              {tokens.completion_tokens != null && (
                <span>출력 {tokens.completion_tokens.toLocaleString()}</span>
              )}
            </div>
          )}

          {/* systemPrompt 토글 */}
          {call.systemPrompt && (
            <div>
              <button
                type="button"
                onClick={() => setShowSystem((v) => !v)}
                className="text-[10px] font-mono uppercase tracking-widest text-slate-500 hover:text-slate-300 transition-colors mb-1"
              >
                SYSTEM PROMPT {showSystem ? '▲' : '▼'}
              </button>
              {showSystem && (
                <pre className="bg-slate-900 border border-slate-800 rounded-lg p-3 text-[11px] font-mono text-slate-300 whitespace-pre-wrap overflow-x-auto max-h-64 leading-relaxed">
                  {call.systemPrompt}
                </pre>
              )}
            </div>
          )}

          {/* INPUT (prompt) */}
          <div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-sky-500/80 mb-1">
              INPUT
            </div>
            <pre className="bg-slate-900 border border-slate-800 rounded-lg p-3 text-[11px] font-mono text-slate-300 whitespace-pre-wrap overflow-x-auto max-h-64 leading-relaxed">
              {call.prompt}
            </pre>
          </div>

          {/* OUTPUT (response) */}
          <div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-violet-400/80 mb-1">
              OUTPUT
            </div>
            <pre className="bg-slate-900 border border-slate-800 rounded-lg p-3 text-[11px] font-mono text-slate-300 whitespace-pre-wrap overflow-x-auto max-h-64 leading-relaxed">
              {call.response}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── 검증 이력 카드 ──────────────────────────────────────────────────────────

function ValidationAttemptCard({ attempt }: { attempt: ValidationAttempt }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-slate-800 rounded-xl overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-slate-800/40 transition-colors text-left"
      >
        <span className="flex-shrink-0 w-6 h-6 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-[10px] font-mono text-slate-400">
          {attempt.attempt}
        </span>
        {attempt.valid ? (
          <span className="text-[11px] font-mono text-emerald-400">✓ 검증 통과</span>
        ) : (
          <span className="text-[11px] font-mono text-rose-400">
            오류 {attempt.errorCount}건 · 경고 {attempt.warningCount}건
          </span>
        )}
        <span className="ml-auto text-slate-600 text-xs flex-shrink-0">{open ? '▲' : '▼'}</span>
      </button>
      {open && (attempt.errors.length > 0 || attempt.warnings.length > 0) && (
        <div className="border-t border-slate-800 bg-slate-950/40 px-4 py-3 space-y-2">
          {attempt.errors.map((issue, i) => (
            <IssueItem key={i} issue={issue} />
          ))}
          {attempt.warnings.map((issue, i) => (
            <IssueItem key={`w${i}`} issue={{ ...issue, severity: 'warning' }} />
          ))}
        </div>
      )}
      {open && attempt.valid && attempt.warnings.length === 0 && (
        <div className="border-t border-slate-800 bg-slate-950/40 px-4 py-2 text-xs text-slate-500">
          이슈 없음
        </div>
      )}
    </div>
  );
}

// ─── 노드 config 패널 ────────────────────────────────────────────────────────

function NodeConfigPanel({ config }: { config: Record<string, unknown> | undefined }) {
  const [open, setOpen] = useState(false);
  if (!config || Object.keys(config).length === 0) return null;
  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-[10px] font-mono text-slate-600 hover:text-slate-400 transition-colors"
      >
        config {open ? '▲' : '▼'}
      </button>
      {open && (
        <pre className="mt-1 bg-slate-950 border border-slate-800 rounded-md p-2 text-[11px] font-mono text-slate-400 whitespace-pre-wrap overflow-x-auto max-h-48 leading-relaxed">
          {JSON.stringify(config, null, 2)}
        </pre>
      )}
    </div>
  );
}

// ─── 트레이스 상세 패널 ──────────────────────────────────────────────────────

function TraceDetail({ detail }: { detail: GenerationTraceDetail }) {
  const result = detail.result as TraceResult;

  return (
    <div className="h-full overflow-y-auto px-5 py-5 space-y-7">
      {/* 헤더 */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <ResultBadge result={result} />
          <span className="text-[10px] font-mono text-slate-500 bg-slate-800/60 border border-slate-700/60 rounded-md px-2 py-1">
            {detail.mode}
          </span>
          {detail.baseDraftProvided && (
            <span className="text-[10px] font-mono text-sky-400/80 bg-sky-900/20 border border-sky-800/40 rounded-md px-2 py-1">
              초안 기반 편집
            </span>
          )}
          <span className="text-[10px] font-mono text-slate-600 ml-auto">
            자동 교정 {detail.attempts}회
          </span>
        </div>

        {/* traceId */}
        <div className="text-[10px] font-mono text-slate-600 break-all">
          ID: {detail.traceId}
        </div>

        {/* 질문 전체 */}
        <div className="bg-slate-800/40 border border-slate-700/60 rounded-xl px-4 py-3">
          <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-1.5">
            요청 질문
          </div>
          <p className="text-sm text-slate-200 leading-relaxed">{detail.description}</p>
        </div>

        {/* 재료 크기 */}
        {detail.materialsSummaryChars > 0 && (
          <div className="text-[10px] font-mono text-slate-600">
            재료 요약 {detail.materialsSummaryChars.toLocaleString()} chars
          </div>
        )}

        {/* 오류 메시지 */}
        {detail.error && (
          <div className="bg-rose-950/30 border border-rose-800/50 rounded-xl px-4 py-3 text-xs text-rose-300 font-mono">
            {detail.error}
          </div>
        )}
      </div>

      {/* LLM 호출 타임라인 */}
      {detail.llmCalls && detail.llmCalls.length > 0 && (
        <div>
          <SectionLabel>단계별 LLM 호출 ({detail.llmCalls.length})</SectionLabel>
          <div className="space-y-2">
            {detail.llmCalls.map((call, i) => (
              <LlmCallCard key={i} call={call} index={i} />
            ))}
          </div>
        </div>
      )}

      {/* 검증 이력 */}
      {detail.validationHistory && detail.validationHistory.length > 0 && (
        <div>
          <SectionLabel>검증 이력 ({detail.validationHistory.length}회)</SectionLabel>
          <div className="space-y-2">
            {detail.validationHistory.map((attempt, i) => (
              <ValidationAttemptCard key={i} attempt={attempt} />
            ))}
          </div>
        </div>
      )}

      {/* 산출물 (finalDraft) */}
      {detail.finalDraft && (
        <div>
          <SectionLabel>산출물</SectionLabel>
          <div className="border border-slate-800 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-800 bg-slate-900/40">
              <div className="text-sm font-semibold text-slate-100">{detail.finalDraft.name}</div>
              {detail.finalDraft.description && (
                <div className="text-xs text-slate-400 mt-0.5">{detail.finalDraft.description}</div>
              )}
              <div className="text-[11px] font-mono text-slate-500 mt-1.5">
                노드 {detail.finalDraft.nodes.length}개 · 연결 {detail.finalDraft.connections.length}개
              </div>
            </div>
            <div className="px-4 py-3 space-y-2">
              {detail.finalDraft.nodes.map((node, i) => (
                <div
                  key={i}
                  className="bg-slate-900/60 border border-slate-800 rounded-lg px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-mono text-sky-400/80 bg-sky-900/20 border border-sky-800/40 rounded px-1.5 py-0.5">
                      {node.definitionType}
                    </span>
                    <span className="text-xs text-slate-200 font-medium">{node.name}</span>
                  </div>
                  <NodeConfigPanel config={node.config} />
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 최종 검증 */}
      {detail.finalValidation && (
        <div>
          <SectionLabel>최종 검증 결과</SectionLabel>
          <div className="border border-slate-800 rounded-xl px-4 py-3 space-y-2">
            <div className="flex items-center gap-2">
              {detail.finalValidation.valid ? (
                <span className="text-xs font-mono text-emerald-400">✓ 검증 통과</span>
              ) : (
                <span className="text-xs font-mono text-rose-400">
                  오류 {detail.finalValidation.errorCount}건 · 경고 {detail.finalValidation.warningCount}건
                </span>
              )}
            </div>
            {detail.finalValidation.errors.map((issue, i) => (
              <IssueItem key={i} issue={issue} />
            ))}
            {detail.finalValidation.warnings.map((issue, i) => (
              <IssueItem key={`w${i}`} issue={{ ...issue, severity: 'warning' }} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── 트레이스 목록 아이템 ────────────────────────────────────────────────────

function TraceListItem({
  trace,
  selected,
  onClick,
}: {
  trace: GenerationTraceSummary;
  selected: boolean;
  onClick: () => void;
}) {
  const result = trace.result as TraceResult;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full text-left px-4 py-3.5 border-b border-slate-800/60 transition-colors ${
        selected ? 'bg-slate-800/80 border-l-2 border-l-sky-500' : 'hover:bg-slate-800/40'
      }`}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <ResultBadge result={result} size="xs" />
        <span className="text-[10px] font-mono text-slate-500 ml-auto flex-shrink-0">
          {formatLocalDateTime(trace.createdAt)}
        </span>
      </div>
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-[10px] font-mono text-slate-600 bg-slate-800/60 border border-slate-700/50 rounded px-1 py-0.5">
          {trace.mode}
        </span>
      </div>
      <p className="text-xs text-slate-300 leading-snug line-clamp-2">
        {trace.description}
      </p>
      <div className="flex items-center gap-3 mt-1.5 text-[10px] font-mono text-slate-600">
        <span>노드 {trace.nodeCount}개</span>
        <span>·</span>
        <span>{trace.attempts}회 교정</span>
        {trace.errorCount > 0 && (
          <>
            <span>·</span>
            <span className="text-rose-500">오류 {trace.errorCount}</span>
          </>
        )}
        {trace.warningCount > 0 && (
          <>
            <span>·</span>
            <span className="text-amber-500">경고 {trace.warningCount}</span>
          </>
        )}
      </div>
    </button>
  );
}

// ─── 메인 페이지 ──────────────────────────────────────────────────────────────

export default function GenerationHistoryPage() {
  const { toast } = useToast();
  const [traces, setTraces] = useState<GenerationTraceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<GenerationTraceDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadTraces = useCallback(async () => {
    setLoading(true);
    try {
      const data = await generationTraceApi.list(50);
      setTraces(data);
    } catch (err) {
      toast.error(`목록 조회 실패: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadTraces();
  }, [loadTraces]);

  const handleSelect = useCallback(
    async (traceId: string) => {
      if (selectedId === traceId) return;
      setSelectedId(traceId);
      setDetail(null);
      setDetailLoading(true);
      try {
        const data = await generationTraceApi.get(traceId);
        setDetail(data);
      } catch (err) {
        toast.error(`상세 조회 실패: ${err instanceof Error ? err.message : String(err)}`);
      } finally {
        setDetailLoading(false);
      }
    },
    [selectedId, toast]
  );

  return (
    <div className="flex flex-col h-full bg-slate-950 overflow-hidden">
      {/* 헤더 */}
      <header className="flex-shrink-0 px-6 py-4 border-b border-slate-800 flex items-center gap-4">
        <Link
          to="/workflows"
          className="text-slate-500 hover:text-slate-300 transition-colors text-sm font-mono"
        >
          ← 목록
        </Link>
        <div>
          <div className="text-[10px] font-mono tracking-[0.25em] uppercase text-slate-500">
            워크플로우 생성
          </div>
          <h1 className="text-base font-semibold text-slate-100 leading-tight">
            생성 로그
          </h1>
        </div>
        <div className="ml-auto">
          <button
            type="button"
            onClick={loadTraces}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-300 hover:bg-slate-700 hover:text-slate-100 transition-colors disabled:opacity-40"
          >
            {loading ? '로딩 중...' : '새로고침'}
          </button>
        </div>
      </header>

      {/* 본체: 2열 */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* ── 좌측: 목록 ─────────────────────────────────────────── */}
        <div className="w-[340px] min-w-[280px] flex-shrink-0 border-r border-slate-800 flex flex-col">
          <div className="flex-shrink-0 px-4 py-2.5 border-b border-slate-800 flex items-center justify-between">
            <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
              최신순
            </span>
            <span className="text-[10px] font-mono text-slate-600">
              {traces.length}건
            </span>
          </div>

          <div className="flex-1 overflow-y-auto">
            {loading && traces.length === 0 && (
              <div className="flex items-center justify-center py-12">
                <div className="w-5 h-5 border-2 border-slate-700 border-t-sky-500 rounded-full animate-spin" />
              </div>
            )}

            {!loading && traces.length === 0 && (
              <div className="flex flex-col items-center justify-center py-12 px-6 text-center">
                <div className="w-10 h-10 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center mb-3 text-slate-600 text-xl">
                  ◻
                </div>
                <p className="text-sm text-slate-500">생성 로그가 없습니다</p>
                <p className="text-xs text-slate-600 mt-1">
                  채팅으로 워크플로우를 생성하면 여기에 기록됩니다.
                </p>
              </div>
            )}

            {traces.map((trace) => (
              <TraceListItem
                key={trace.traceId}
                trace={trace}
                selected={trace.traceId === selectedId}
                onClick={() => handleSelect(trace.traceId)}
              />
            ))}
          </div>
        </div>

        {/* ── 우측: 상세 ──────────────────────────────────────────── */}
        <div className="flex-1 min-w-0 overflow-hidden">
          {!selectedId && (
            <div className="flex flex-col items-center justify-center h-full text-center p-8">
              <div className="w-14 h-14 rounded-2xl bg-slate-900/60 border border-slate-800 flex items-center justify-center mb-4 text-slate-600 text-2xl">
                🧾
              </div>
              <p className="text-sm text-slate-400 font-medium">
                좌측 목록에서 로그를 선택하세요
              </p>
              <p className="text-xs text-slate-600 mt-1.5 leading-relaxed max-w-[320px]">
                선택한 생성 요청의 LLM 단계별 IN/OUT, 검증 이력, 산출물을 확인할 수 있습니다.
              </p>
            </div>
          )}

          {selectedId && detailLoading && (
            <div className="flex items-center justify-center h-full">
              <div className="flex flex-col items-center gap-3">
                <div className="w-7 h-7 border-2 border-slate-700 border-t-sky-500 rounded-full animate-spin" />
                <span className="text-xs font-mono text-slate-500">상세 로딩 중...</span>
              </div>
            </div>
          )}

          {selectedId && !detailLoading && detail && (
            <TraceDetail detail={detail} />
          )}
        </div>
      </div>
    </div>
  );
}
