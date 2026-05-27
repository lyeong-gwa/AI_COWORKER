/**
 * EdgeInspectorPanel — 엣지 클릭 시 우측 슬라이드 드로어
 *
 * 3-col 구조:
 *   좌 (40%): 페이지 A — 서비스/타입 배지 + 제목 + MarkdownView
 *   중 (20%): 관계 메타 + 승격 액션
 *   우 (40%): 페이지 B
 *
 * 백엔드 API: GET /api/v1/knowledge/edge, POST /api/v1/knowledge/edge/promote
 */
import React, { useEffect, useState, useCallback } from 'react';
import { knowledgeApi } from '../../services/api';
import type { KnowledgeEdgeDetail } from '../../types';
import { MarkdownView } from './MarkdownView';
import { ServiceBadge } from './ServiceBadge';
import { PageTypeBadge } from './PageTypeBadge';
import { useToast } from '../common/Toast';
import type { PageType } from '../../types';

interface EdgeInspectorPanelProps {
  from: string;
  to: string;
  onClose: () => void;
  onPromoted: () => void;
}

export function EdgeInspectorPanel({ from, to, onClose, onPromoted }: EdgeInspectorPanelProps) {
  const { toast } = useToast();
  const [detail, setDetail] = useState<KnowledgeEdgeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState(false);

  // 모달 진입 애니메이션
  useEffect(() => {
    const t = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(t);
  }, []);

  // 데이터 로드
  useEffect(() => {
    setLoading(true);
    setError(null);
    knowledgeApi.getEdge({ from, to })
      .then(setDetail)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [from, to]);

  const handleClose = useCallback(() => {
    setVisible(false);
    setTimeout(onClose, 300);
  }, [onClose]);

  // ESC 키 닫기
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handleClose]);

  // 백드롭 클릭 핸들러 (모달 자체 클릭은 전파 방지)
  const handleBackdropClick = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      handleClose();
    }
  }, [handleClose]);

  const handlePromote = useCallback(async (direction: 'fromTo' | 'toFrom') => {
    if (!detail?.edge) return;
    const [src, dst] = direction === 'fromTo'
      ? [detail.from.id, detail.to.id]
      : [detail.to.id, detail.from.id];

    const defaultAnchor = '관련';
    const anchorText = window.prompt(`앵커 텍스트를 입력하세요 (기본값: "${defaultAnchor}")`, defaultAnchor);
    if (anchorText === null) return; // 취소

    try {
      await knowledgeApi.promoteEdge({ from: src, to: dst, anchorText: anchorText || defaultAnchor });
      toast.success('명시 링크가 추가되었습니다.');
      handleClose();
      onPromoted();
    } catch (e: unknown) {
      const status = (e as { status?: number })?.status;
      if (status === 409) {
        toast.error('이미 명시 링크가 존재합니다.');
      } else {
        toast.error(e instanceof Error ? e.message : '승격에 실패했습니다.');
      }
    }
  }, [detail, toast, handleClose, onPromoted]);

  return (
    <>
      {/* 백드롭 */}
      <div
        className={`fixed inset-0 z-40 bg-black/70 backdrop-blur-sm transition-opacity duration-300 ${visible ? 'opacity-100' : 'opacity-0'}`}
        onClick={handleBackdropClick}
      />

      {/* 모달 */}
      <div
        className={`fixed inset-0 z-50 flex items-center justify-center transition-opacity duration-300 ${visible ? 'opacity-100' : 'opacity-0'} pointer-events-none`}
      >
        <div
          className={`w-[95vw] h-[92vh] max-w-[1600px] max-h-[1200px] bg-slate-900 rounded-2xl shadow-2xl border border-slate-800 flex flex-col transition-transform duration-300 ease-out ${visible ? 'scale-100' : 'scale-95'} pointer-events-auto`}
          onClick={(e) => e.stopPropagation()}
        >
          {/* 모달 헤더 */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 flex-shrink-0">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono tracking-[0.2em] uppercase text-slate-500">
                Edge Inspector
              </span>
              {detail?.edge && (
                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono border ${
                  detail.edge.kind === 'explicit'
                    ? 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30'
                    : 'bg-slate-500/15 text-slate-400 border-slate-500/30'
                }`}>
                  {detail.edge.kind}
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={handleClose}
              className="w-7 h-7 rounded flex items-center justify-center text-slate-500 hover:text-slate-200 hover:bg-slate-800 transition-colors"
              aria-label="닫기"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M1 1l12 12M13 1L1 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
              </svg>
            </button>
          </div>

          {/* 모달 본문 */}
          <div className="flex-1 overflow-hidden">
          {loading ? (
            <div className="h-full flex items-center justify-center">
              <div className="flex flex-col items-center gap-3">
                <div className="w-8 h-8 border-2 border-slate-700 border-t-cyan-500 rounded-full animate-spin" />
                <span className="text-slate-500 text-xs font-mono">엣지 정보 로딩 중...</span>
              </div>
            </div>
          ) : error ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-center space-y-2">
                <p className="text-red-400 text-sm">{error}</p>
                <button type="button" onClick={handleClose} className="text-xs text-slate-400 underline">닫기</button>
              </div>
            </div>
          ) : !detail ? null : detail.edge === null ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-center space-y-2">
                <p className="text-slate-400 text-sm">이 두 페이지 사이엔 엣지가 없습니다.</p>
                <button type="button" onClick={handleClose} className="text-xs text-slate-400 underline">닫기</button>
              </div>
            </div>
          ) : (
            <div className="h-full grid grid-cols-[2fr_1fr_2fr] divide-x divide-slate-800">
              {/* 좌측: 페이지 A */}
              <DocPane
                doc={detail.from}
                label="A"
                onNavigate={() => window.open(`/knowledge?id=${encodeURIComponent(detail.from.id)}`, '_blank')}
              />

              {/* 중앙: 관계 메타 + 액션 */}
              <div className="flex flex-col gap-0 overflow-y-auto">
                <div className="p-4 border-b border-slate-800">
                  <div className="text-[10px] font-mono tracking-[0.15em] uppercase text-slate-500 mb-3">관계 메타</div>
                  <div className="space-y-2.5">
                    {/* Kind */}
                    <MetaRow label="종류">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono border ${
                        detail.edge.kind === 'explicit'
                          ? 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30'
                          : 'bg-slate-500/15 text-slate-400 border-slate-500/30'
                      }`}>
                        {detail.edge.kind === 'explicit' ? '명시' : '암묵'}
                      </span>
                    </MetaRow>

                    {/* Weight */}
                    <MetaRow label="가중치">
                      <span className="text-[12px] font-mono text-slate-300">{detail.edge.weight.toFixed(3)}</span>
                    </MetaRow>

                    {/* Similarity (implicit only) */}
                    {detail.edge.similarity !== null && (
                      <MetaRow label="유사도">
                        <span className="text-[12px] font-mono text-sky-300">{detail.edge.similarity.toFixed(3)}</span>
                      </MetaRow>
                    )}

                    {/* Cross-service */}
                    {detail.edge.crossService && (
                      <MetaRow label="교차 서비스">
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono bg-purple-500/15 text-purple-300 border border-purple-500/30">cross</span>
                      </MetaRow>
                    )}

                    {/* Directionality */}
                    <div className="pt-1">
                      <div className="text-[10px] font-mono text-slate-500 mb-1.5">방향성</div>
                      <div className="space-y-1">
                        <div className={`text-[11px] font-mono flex items-center gap-1.5 ${detail.edge.fromToExplicit ? 'text-cyan-300' : 'text-slate-600'}`}>
                          <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${detail.edge.fromToExplicit ? 'bg-cyan-400' : 'bg-slate-700'}`} />
                          A → B {detail.edge.fromToExplicit ? '명시' : '미명시'}
                        </div>
                        <div className={`text-[11px] font-mono flex items-center gap-1.5 ${detail.edge.toFromExplicit ? 'text-cyan-300' : 'text-slate-600'}`}>
                          <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${detail.edge.toFromExplicit ? 'bg-cyan-400' : 'bg-slate-700'}`} />
                          B → A {detail.edge.toFromExplicit ? '명시' : '미명시'}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* 액션 버튼 */}
                <div className="p-4 space-y-2">
                  <div className="text-[10px] font-mono tracking-[0.15em] uppercase text-slate-500 mb-3">액션</div>

                  <ActionBtn
                    onClick={() => window.open(`/knowledge?id=${encodeURIComponent(detail.from.id)}`, '_blank')}
                    label="↗ A 페이지로"
                    variant="ghost"
                  />
                  <ActionBtn
                    onClick={() => window.open(`/knowledge?id=${encodeURIComponent(detail.to.id)}`, '_blank')}
                    label="↗ B 페이지로"
                    variant="ghost"
                  />

                  {!detail.edge.fromToExplicit && (
                    <ActionBtn
                      onClick={() => handlePromote('fromTo')}
                      label="⇄ A → B 명시 링크 추가"
                      variant="promote"
                    />
                  )}
                  {!detail.edge.toFromExplicit && (
                    <ActionBtn
                      onClick={() => handlePromote('toFrom')}
                      label="⇄ B → A 명시 링크 추가"
                      variant="promote"
                    />
                  )}

                  {detail.edge.fromToExplicit && detail.edge.toFromExplicit && (
                    <p className="text-[10px] text-slate-600 font-mono text-center pt-1">양방향 명시 링크 완비</p>
                  )}
                </div>
              </div>

              {/* 우측: 페이지 B */}
              <DocPane
                doc={detail.to}
                label="B"
                onNavigate={() => window.open(`/knowledge?id=${encodeURIComponent(detail.to.id)}`, '_blank')}
              />
            </div>
          )}
          </div>
        </div>
      </div>
    </>
  );
}

// ─── 내부 서브 컴포넌트 ───────────────────────────────────────────────────────

interface DocPaneProps {
  doc: { id: string; title: string; content: string; service: string; pageType?: string; version?: number };
  label: 'A' | 'B';
  onNavigate: () => void;
}

function DocPane({ doc, label, onNavigate }: DocPaneProps) {
  return (
    <div className="flex flex-col overflow-hidden">
      {/* 문서 헤더 */}
      <div className="px-4 pt-4 pb-3 border-b border-slate-800 flex-shrink-0">
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <span className="text-[10px] font-mono text-slate-600 bg-slate-800 px-1.5 py-0.5 rounded">
            {label}
          </span>
          <ServiceBadge serviceId={doc.service} />
          {doc.pageType && (
            <PageTypeBadge type={doc.pageType as PageType} />
          )}
          {doc.version !== undefined && (
            <span className="text-[10px] font-mono text-slate-500">v{doc.version}</span>
          )}
        </div>
        <h3 className="text-sm font-medium text-slate-100 leading-snug line-clamp-2">{doc.title}</h3>
        <button
          type="button"
          onClick={onNavigate}
          className="mt-2 text-[10px] font-mono text-sky-500 hover:text-sky-300 transition-colors"
        >
          ↗ 페이지로 이동
        </button>
      </div>

      {/* 문서 본문 */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        <MarkdownView content={doc.content} className="text-sm" />
      </div>
    </div>
  );
}

interface MetaRowProps {
  label: string;
  children: React.ReactNode;
}

function MetaRow({ label, children }: MetaRowProps) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-[10px] font-mono text-slate-500 flex-shrink-0">{label}</span>
      {children}
    </div>
  );
}

interface ActionBtnProps {
  onClick: () => void;
  label: string;
  variant: 'ghost' | 'promote';
}

function ActionBtn({ onClick, label, variant }: ActionBtnProps) {
  const base = 'w-full text-left px-3 py-2 rounded-lg text-[11px] font-mono transition-colors';
  const styles = {
    ghost: 'text-slate-400 hover:text-slate-200 hover:bg-slate-800 border border-transparent hover:border-slate-700',
    promote: 'text-cyan-300 hover:text-white hover:bg-cyan-600/20 border border-cyan-500/30 hover:border-cyan-500/60',
  };
  return (
    <button type="button" onClick={onClick} className={`${base} ${styles[variant]}`}>
      {label}
    </button>
  );
}

