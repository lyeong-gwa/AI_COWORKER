/**
 * ReferencedPagesSection — 본문 하단 "📎 이 페이지가 참조하는 글" 카드 섹션.
 *
 * - 본문에서 추출된 outgoing link id 목록을 받아 각 타겟 카드를 표시.
 * - 카드: page_type 배지 + 제목 + 본문 200자 발췌 + "전체 보기 →"
 * - broken 카드(존재하지 않는 페이지): 빨간 카드
 * - N=0 이면 섹션 자체 숨김.
 *
 * 데이터 로딩: 각 id 별로 knowledgeApi.get(id) — 가능하면 WikiLinkChip 캐시 활용 위해
 * 동일 fetchPreview 패턴을 단순 useEffect 로 재구현 (모듈 경계 분리 유지).
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { knowledgeApi } from '../../services/api';
import type { KnowledgeDocument } from '../../types';
import { PageTypeBadge } from './PageTypeBadge';

interface ReferencedPagesSectionProps {
  /** 본문에서 추출된 [[...]] target 목록 (deleted: prefix 제외) */
  links: string[];
  /** 카드 클릭 시 호출 — id 전달. 없으면 router navigate 사용 */
  onNavigate?: (id: string) => void;
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'hit'; doc: KnowledgeDocument }
  | { kind: 'miss' };

const EXCERPT_LEN = 200;

function makeExcerpt(content: string): string {
  return (content ?? '')
    .replace(/^#+\s+/gm, '')
    .replace(/```[\s\S]*?```/g, '')
    .replace(/\[\[([^\]]+)\]\]/g, '$1')
    .replace(/[*_`>]+/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, EXCERPT_LEN);
}

export function ReferencedPagesSection({ links, onNavigate }: ReferencedPagesSectionProps) {
  const navigate = useNavigate();
  const [items, setItems] = useState<Record<string, LoadState>>({});

  // 중복 제거 + 순서 유지
  const uniqueLinks = Array.from(new Set(links.filter((l) => !l.startsWith('deleted:'))));

  useEffect(() => {
    if (uniqueLinks.length === 0) {
      setItems({});
      return;
    }
    let cancelled = false;
    // 초기 상태: 전부 loading
    setItems(
      Object.fromEntries(uniqueLinks.map((id) => [id, { kind: 'loading' } as LoadState])),
    );
    // 병렬 fetch
    Promise.all(
      uniqueLinks.map(async (id) => {
        try {
          const doc = await knowledgeApi.get(id);
          return [id, { kind: 'hit', doc } as LoadState] as const;
        } catch {
          return [id, { kind: 'miss' } as LoadState] as const;
        }
      }),
    ).then((results) => {
      if (cancelled) return;
      setItems(Object.fromEntries(results));
    });
    return () => {
      cancelled = true;
    };
    // uniqueLinks를 join하여 deps 안정화 (배열 ref 변경 무시)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uniqueLinks.join('|')]);

  if (uniqueLinks.length === 0) return null;

  const handleClick = (id: string) => {
    if (onNavigate) onNavigate(id);
    else navigate(`/knowledge?id=${encodeURIComponent(id)}`);
  };

  return (
    <section className="mt-8 pt-6 border-t border-slate-800">
      <div className="flex items-baseline gap-2 mb-4">
        <span className="text-base">📎</span>
        <h3 className="text-sm font-semibold text-slate-200 tracking-wide">
          이 페이지가 참조하는 글
        </h3>
        <span className="text-[11px] font-mono text-slate-500">({uniqueLinks.length})</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {uniqueLinks.map((id) => {
          const state = items[id] ?? { kind: 'loading' };
          if (state.kind === 'loading') {
            return (
              <div
                key={id}
                className="rounded-lg border border-slate-800 bg-slate-900/40 p-4"
              >
                <div className="h-3 w-1/3 bg-slate-800 rounded animate-pulse mb-2" />
                <div className="h-4 w-2/3 bg-slate-800 rounded animate-pulse mb-3" />
                <div className="h-2 w-full bg-slate-800/60 rounded animate-pulse mb-1" />
                <div className="h-2 w-5/6 bg-slate-800/60 rounded animate-pulse" />
              </div>
            );
          }
          if (state.kind === 'miss') {
            return (
              <button
                key={id}
                type="button"
                onClick={() => handleClick(id)}
                className="text-left rounded-lg border border-red-900/60 border-dashed bg-red-950/20 p-4 hover:bg-red-950/30 transition-colors group"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-red-400">⚠</span>
                  <span className="text-[10px] font-mono uppercase tracking-wider text-red-400/80">
                    존재하지 않는 페이지
                  </span>
                </div>
                <div className="text-[13px] font-mono text-red-200 break-all">{id}</div>
                <div className="text-[10px] text-red-400/60 mt-2">
                  (이 링크는 깨졌습니다)
                </div>
              </button>
            );
          }
          const doc = state.doc;
          const excerpt = makeExcerpt(doc.content);
          return (
            <button
              key={id}
              type="button"
              onClick={() => handleClick(id)}
              className="text-left rounded-lg border border-slate-800 bg-slate-900/40 p-4 hover:border-cyan-700/60 hover:bg-slate-900/70 hover:shadow-lg hover:shadow-cyan-950/30 transition-all group"
            >
              <div className="flex items-start justify-between gap-2 mb-1.5">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 truncate">
                    {doc.category || 'uncategorized'}
                  </span>
                </div>
                {doc.pageType && <PageTypeBadge type={doc.pageType} />}
              </div>
              <div className="text-[14px] font-semibold text-slate-100 group-hover:text-cyan-200 mb-2 leading-snug">
                {doc.title}
              </div>
              {excerpt ? (
                <p className="text-[12px] text-slate-400 leading-relaxed line-clamp-3">
                  {excerpt}
                  {(doc.content?.length ?? 0) > EXCERPT_LEN && '…'}
                </p>
              ) : (
                <p className="text-[12px] text-slate-600 italic">(본문 없음)</p>
              )}
              <div className="mt-3 text-[11px] font-mono text-cyan-400/80 group-hover:text-cyan-300">
                전체 보기 →
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
