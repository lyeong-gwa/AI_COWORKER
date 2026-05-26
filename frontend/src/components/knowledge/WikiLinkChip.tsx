/**
 * WikiLinkChip — Obsidian-style `[[link]]` chip with hover preview.
 *
 * - 일반 링크: 청록 chip, 클릭 시 `/knowledge?id=...` 로 이동
 * - `deleted:` prefix: 빨간 strikethrough 마커 ("(삭제됨)")
 * - broken (타겟 없음): 빨간 테두리 + 호버 시 "존재하지 않는 페이지"
 * - 호버 200ms 후 툴팁: 제목 + page_type 배지 + 본문 발췌
 *
 * 데이터: knowledgeApi.get(id) 결과를 모듈 레벨 캐시에 저장 → 재호출 없음
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { knowledgeApi } from '../../services/api';
import type { KnowledgeDocument } from '../../types';
import { PageTypeBadge } from './PageTypeBadge';

// ── 캐시 ────────────────────────────────────────────────────────────────
// 'hit' = 로드 성공, 'miss' = 404/오류, undefined = 아직 로드 안함
type CacheEntry =
  | { state: 'hit'; doc: KnowledgeDocument }
  | { state: 'miss' }
  | { state: 'loading'; promise: Promise<void> };

const previewCache = new Map<string, CacheEntry>();

async function fetchPreview(id: string): Promise<CacheEntry> {
  const existing = previewCache.get(id);
  if (existing && existing.state !== 'loading') return existing;
  if (existing && existing.state === 'loading') {
    await existing.promise;
    return previewCache.get(id) ?? { state: 'miss' };
  }
  let resolveFn: () => void = () => undefined;
  const promise = new Promise<void>((res) => {
    resolveFn = res;
  });
  previewCache.set(id, { state: 'loading', promise });
  try {
    const doc = await knowledgeApi.get(id);
    const entry: CacheEntry = { state: 'hit', doc };
    previewCache.set(id, entry);
    resolveFn();
    return entry;
  } catch {
    const entry: CacheEntry = { state: 'miss' };
    previewCache.set(id, entry);
    resolveFn();
    return entry;
  }
}

// ── 컴포넌트 ────────────────────────────────────────────────────────────

interface WikiLinkChipProps {
  /** 링크 대상 — `[[X]]` 안의 X (가공 전 raw 문자열) */
  target: string;
  /** SPA 내비게이션 핸들러(있으면) — 없으면 router navigate 사용 */
  onNavigate?: (id: string) => void;
}

interface TooltipState {
  visible: boolean;
  x: number;
  y: number;
}

const HOVER_DELAY_MS = 200;
const EXCERPT_LEN = 120;

export function WikiLinkChip({ target, onNavigate }: WikiLinkChipProps) {
  const navigate = useNavigate();

  // deleted: prefix 처리
  const isDeleted = target.startsWith('deleted:');
  const cleanTarget = isDeleted ? target.slice('deleted:'.length).trim() : target.trim();

  // 표시 라벨: alias `[[id|label]]` 지원, 없으면 마지막 slug
  let displayLabel = cleanTarget;
  let resolvedId = cleanTarget;
  const pipeIdx = cleanTarget.indexOf('|');
  if (pipeIdx >= 0) {
    resolvedId = cleanTarget.slice(0, pipeIdx).trim();
    displayLabel = cleanTarget.slice(pipeIdx + 1).trim();
  } else if (cleanTarget.includes('/')) {
    displayLabel = cleanTarget.split('/').pop() ?? cleanTarget;
  }

  // ── 호버 / 툴팁 상태 ───────────────────────────────────────────────
  const [tooltip, setTooltip] = useState<TooltipState>({ visible: false, x: 0, y: 0 });
  const [preview, setPreview] = useState<CacheEntry | null>(
    () => previewCache.get(resolvedId) ?? null,
  );
  const hoverTimerRef = useRef<number | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);

  const clearHoverTimer = useCallback(() => {
    if (hoverTimerRef.current !== null) {
      window.clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
  }, []);

  const handleMouseEnter = useCallback(
    (e: React.MouseEvent<HTMLAnchorElement>) => {
      if (isDeleted) return; // 삭제 마커는 툴팁 없음
      const targetX = e.clientX;
      const targetY = e.clientY;
      clearHoverTimer();
      hoverTimerRef.current = window.setTimeout(() => {
        setTooltip({ visible: true, x: targetX, y: targetY });
        // 캐시 미스면 fetch
        if (!previewCache.has(resolvedId)) {
          fetchPreview(resolvedId).then((entry) => {
            setPreview(entry);
          });
        } else {
          setPreview(previewCache.get(resolvedId) ?? null);
        }
      }, HOVER_DELAY_MS);
    },
    [isDeleted, resolvedId, clearHoverTimer],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLAnchorElement>) => {
      if (!tooltip.visible) return;
      setTooltip((prev) => ({ ...prev, x: e.clientX, y: e.clientY }));
    },
    [tooltip.visible],
  );

  const handleMouseLeave = useCallback(() => {
    clearHoverTimer();
    setTooltip({ visible: false, x: 0, y: 0 });
  }, [clearHoverTimer]);

  // unmount 시 timer 정리
  useEffect(() => () => clearHoverTimer(), [clearHoverTimer]);

  // 화면 가장자리 회피 (오른쪽/하단)
  const TOOLTIP_W = 320;
  const TOOLTIP_H = 160;
  const PAD = 12;
  let tx = tooltip.x + 14;
  let ty = tooltip.y + 18;
  if (typeof window !== 'undefined') {
    if (tx + TOOLTIP_W + PAD > window.innerWidth) tx = tooltip.x - TOOLTIP_W - 14;
    if (ty + TOOLTIP_H + PAD > window.innerHeight) ty = tooltip.y - TOOLTIP_H - 14;
    if (tx < PAD) tx = PAD;
    if (ty < PAD) ty = PAD;
  }

  // ── 클릭 핸들러 ────────────────────────────────────────────────────
  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLAnchorElement>) => {
      e.preventDefault();
      if (isDeleted) return;
      if (onNavigate) {
        onNavigate(resolvedId);
      } else {
        navigate(`/knowledge?id=${encodeURIComponent(resolvedId)}`);
      }
    },
    [isDeleted, onNavigate, navigate, resolvedId],
  );

  // ── deleted 마커 ──────────────────────────────────────────────────
  if (isDeleted) {
    return (
      <span
        className="inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 rounded text-[12px] line-through text-red-400/80 bg-red-950/30 border border-red-900/50 font-mono"
        title={`삭제된 페이지: ${cleanTarget}`}
      >
        <span className="text-red-500/70 not-italic">⊘</span>
        {displayLabel}
        <span className="text-[10px] text-red-500/60">(삭제됨)</span>
      </span>
    );
  }

  // ── 일반 chip ─────────────────────────────────────────────────────
  const isBroken = preview?.state === 'miss';
  const chipBase =
    'inline-flex items-baseline gap-0.5 px-1.5 py-0.5 mx-0.5 rounded text-[12px] font-mono cursor-pointer transition-colors no-underline';
  const chipOk =
    'text-cyan-300 bg-cyan-500/10 border border-cyan-500/30 hover:bg-cyan-500/20 hover:text-cyan-200 hover:border-cyan-400/50';
  const chipBroken =
    'text-red-300 bg-red-950/30 border border-red-700/60 border-dashed hover:bg-red-900/30';

  return (
    <>
      <a
        href={`/knowledge?id=${encodeURIComponent(resolvedId)}`}
        onClick={handleClick}
        onMouseEnter={handleMouseEnter}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        className={`${chipBase} ${isBroken ? chipBroken : chipOk}`}
      >
        <span className="opacity-60">[[</span>
        <span>{displayLabel}</span>
        <span className="opacity-60">]]</span>
      </a>

      {tooltip.visible && (
        <div
          ref={tooltipRef}
          role="tooltip"
          style={{
            position: 'fixed',
            left: tx,
            top: ty,
            width: TOOLTIP_W,
            zIndex: 9999,
            pointerEvents: 'none',
          }}
          className="rounded-lg border bg-slate-900/95 backdrop-blur-sm shadow-2xl shadow-black/60 p-3 animate-[fadeIn_120ms_ease-out]"
        >
          {(() => {
            if (!preview || preview.state === 'loading') {
              return (
                <div className="space-y-2">
                  <div className="h-3 w-2/3 bg-slate-800 rounded animate-pulse" />
                  <div className="h-2 w-full bg-slate-800/60 rounded animate-pulse" />
                  <div className="h-2 w-5/6 bg-slate-800/60 rounded animate-pulse" />
                </div>
              );
            }
            if (preview.state === 'miss') {
              return (
                <div className="flex items-start gap-2">
                  <span className="text-red-400 text-base leading-none mt-0.5">⚠</span>
                  <div>
                    <div className="text-xs font-semibold text-red-300">
                      이 페이지는 존재하지 않습니다
                    </div>
                    <div className="text-[10px] text-red-400/60 font-mono mt-1 break-all">
                      {resolvedId}
                    </div>
                  </div>
                </div>
              );
            }
            const doc = preview.doc;
            const excerpt = (doc.content ?? '')
              .replace(/^#+\s+/gm, '')
              .replace(/\[\[([^\]]+)\]\]/g, '$1')
              .replace(/\s+/g, ' ')
              .trim()
              .slice(0, EXCERPT_LEN);
            return (
              <>
                <div className="flex items-start gap-2 mb-1.5">
                  <div className="text-[13px] font-semibold text-slate-100 flex-1 leading-tight">
                    {doc.title}
                  </div>
                  {doc.pageType && <PageTypeBadge type={doc.pageType} />}
                </div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-2">
                  {doc.category || 'uncategorized'}
                </div>
                {excerpt ? (
                  <p className="text-[11px] text-slate-300 leading-relaxed line-clamp-4">
                    {excerpt}
                    {(doc.content?.length ?? 0) > EXCERPT_LEN && '…'}
                  </p>
                ) : (
                  <p className="text-[11px] text-slate-500 italic">(본문 없음)</p>
                )}
              </>
            );
          })()}
          <style>{`
            @keyframes fadeIn {
              from { opacity: 0; transform: translateY(-2px); }
              to   { opacity: 1; transform: translateY(0); }
            }
          `}</style>
        </div>
      )}
    </>
  );
}
