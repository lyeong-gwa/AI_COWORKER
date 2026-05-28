/**
 * Node Catalog Page (`/nodes`)
 *
 * Phase 3b — 11종 범용 노드 카탈로그 + 커스텀 AI 노드 목록 (읽기 전용).
 * 편집·생성 UI 모두 제거. 모든 관리는 CLI로 이관.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { nodeApi, type NodeCatalogEntry } from '../services/api';
import type { AINode } from '../types';
import { CliHint } from '../components/common/CliHint';
import { EmptyState } from '../components/common/EmptyState';
import { useToast } from '../components/common/Toast';
import { JsonTreeView } from '../components/common/JsonTreeView';

const CATEGORY_ORDER: NodeCatalogEntry['category'][] = [
  'starter',
  'ai',
  'logic',
  'action',
  'output',
];

const CATEGORY_LABEL: Record<NodeCatalogEntry['category'], string> = {
  starter: 'STARTER · 트리거',
  ai: 'AI',
  logic: 'LOGIC · 흐름제어',
  action: 'ACTION · 외부연동',
  output: 'OUTPUT · 저장/표시',
};

const CATEGORY_TONE: Record<NodeCatalogEntry['category'], string> = {
  starter: 'text-amber-300 border-amber-700/40',
  ai: 'text-violet-300 border-violet-700/40',
  logic: 'text-sky-300 border-sky-700/40',
  action: 'text-emerald-300 border-emerald-700/40',
  output: 'text-slate-300 border-slate-700/40',
};

function CatalogCard({ entry }: { entry: NodeCatalogEntry }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={`rounded-xl border bg-slate-900/40 overflow-hidden transition-all ${CATEGORY_TONE[entry.category]}`}>
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full px-5 py-4 text-left flex items-start gap-4"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-mono text-xs uppercase tracking-wider">
              {entry.category}
            </span>
            {entry.requiresUpstream === false && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-900/30 text-amber-300 border border-amber-700/40">
                TRIGGER
              </span>
            )}
            {entry.producesArray && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-sky-900/30 text-sky-300 border border-sky-700/40">
                ARRAY
              </span>
            )}
          </div>
          <div className="flex items-baseline gap-3">
            <h3 className="text-base font-semibold text-slate-100">{entry.label}</h3>
            <code className="text-[11px] font-mono text-slate-500">{entry.defType}</code>
          </div>
          <p className="text-xs text-slate-400 mt-1 leading-relaxed">{entry.purpose}</p>
        </div>
        <span className={`text-slate-600 transition-transform flex-shrink-0 ${expanded ? 'rotate-90' : ''}`}>
          ›
        </span>
      </button>

      {expanded && (
        <div className="px-5 pb-5 space-y-4 border-t border-slate-800/60 pt-4">
          {entry.inputs.length > 0 && (
            <div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-1.5">
                Inputs ({entry.inputs.length})
              </div>
              <div className="space-y-1">
                {entry.inputs.map((f) => (
                  <div key={f.name} className="text-[11px] font-mono flex gap-2">
                    <span className="text-slate-200">{f.name}</span>
                    <span className="text-slate-500">{f.type}</span>
                    {f.required && <span className="text-rose-300">●</span>}
                    <span className="text-slate-500 truncate">· {f.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {entry.outputs.length > 0 && (
            <div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-1.5">
                Outputs ({entry.outputs.length})
              </div>
              <div className="space-y-1">
                {entry.outputs.map((f) => (
                  <div key={f.name} className="text-[11px] font-mono flex gap-2">
                    <span className="text-slate-200">{f.name}</span>
                    <span className="text-slate-500">{f.type}</span>
                    <span className="text-slate-500 truncate">· {f.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {entry.config.length > 0 && (
            <div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-1.5">
                Config ({entry.config.length})
              </div>
              <div className="space-y-1">
                {entry.config.map((c) => (
                  <div key={c.name} className="text-[11px] font-mono">
                    <span className="text-slate-200">{c.name}</span>{' '}
                    <span className="text-slate-500">{c.type}</span>
                    {c.required && <span className="text-rose-300 ml-1">●</span>}
                    {c.default !== null && c.default !== undefined && (
                      <span className="text-slate-600 ml-2">
                        default={JSON.stringify(c.default)}
                      </span>
                    )}
                    <div className="text-slate-500 ml-2 break-words">{c.description}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {entry.useCases.length > 0 && (
            <div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-1.5">
                Use Cases
              </div>
              <ul className="space-y-1">
                {entry.useCases.map((u, i) => (
                  <li key={i} className="text-xs text-slate-400 flex gap-2">
                    <span className="text-slate-600">—</span>
                    <span>{u}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {entry.connectsWellWith.length > 0 && (
            <div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-1.5">
                Connects Well With
              </div>
              <div className="flex flex-wrap gap-1.5">
                {entry.connectsWellWith.map((t) => (
                  <span
                    key={t}
                    className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800/60 text-slate-300 border border-slate-700/60"
                  >
                    → {t}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── 커스텀 AI 노드 상세 모달 ────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handle = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard API 실패 시 무시
    }
  }, [text]);
  return (
    <button
      type="button"
      onClick={handle}
      className="text-[10px] font-mono px-2 py-0.5 rounded border border-slate-700/60 text-slate-500 hover:text-slate-200 hover:border-slate-500 transition-colors"
    >
      {copied ? '복사됨' : '복사'}
    </button>
  );
}

/** {{변수}} 를 강조한 userPromptTemplate 렌더러 */
function PromptTemplateView({ text }: { text: string }) {
  // {{...}} 패턴을 분리하여 강조 표시
  const parts = text.split(/({{[^}]+}})/g);
  return (
    <pre className="text-[11px] font-mono leading-relaxed whitespace-pre-wrap break-words text-slate-300">
      {parts.map((part, i) =>
        /^{{[^}]+}}$/.test(part) ? (
          <mark key={i} className="bg-violet-500/20 text-violet-300 rounded px-0.5 not-italic">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </pre>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-500 mb-2">
      {children}
    </div>
  );
}

function BoolBadge({ value, trueLabel = 'ON', falseLabel = 'OFF' }: { value: boolean; trueLabel?: string; falseLabel?: string }) {
  return value ? (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-900/30 text-emerald-300 border border-emerald-700/40">
      {trueLabel}
    </span>
  ) : (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800/60 text-slate-500 border border-slate-700/40">
      {falseLabel}
    </span>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString('ko-KR', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function CustomNodeDetailModal({ node, onClose }: { node: AINode; onClose: () => void }) {
  const [visible, setVisible] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);

  // 진입 애니메이션
  useEffect(() => {
    const t = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(t);
  }, []);

  const handleClose = useCallback(() => {
    setVisible(false);
    setTimeout(onClose, 280);
  }, [onClose]);

  // ESC 닫기
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') handleClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handleClose]);

  // 백드롭 클릭 닫기
  const handleBackdropClick = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget) handleClose();
  }, [handleClose]);

  const enf = node.outputEnforcement;

  return (
    <>
      {/* 백드롭 */}
      <div
        className={`fixed inset-0 z-40 bg-black/70 backdrop-blur-sm transition-opacity duration-280 ${visible ? 'opacity-100' : 'opacity-0'}`}
        onClick={handleBackdropClick}
      />

      {/* 모달 컨테이너 */}
      <div
        className={`fixed inset-0 z-50 flex items-center justify-center p-4 transition-opacity duration-280 ${visible ? 'opacity-100' : 'opacity-0'} pointer-events-none`}
        onClick={handleBackdropClick}
      >
        <div
          ref={modalRef}
          className={`w-full max-w-2xl max-h-[90vh] bg-slate-900 rounded-2xl shadow-2xl border border-slate-800 flex flex-col transition-transform duration-280 ease-out ${visible ? 'scale-100' : 'scale-95'} pointer-events-auto`}
          onClick={(e) => e.stopPropagation()}
        >
          {/* 헤더 */}
          <div className="flex items-center gap-3 px-5 py-4 border-b border-slate-800 flex-shrink-0">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center text-base flex-shrink-0"
              style={{ backgroundColor: node.color ? `${node.color}25` : '#334155', color: node.color || '#94a3b8' }}
            >
              {node.icon || 'N'}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-base font-semibold text-slate-100 truncate">{node.name}</h2>
                {node.isActive !== undefined && (
                  <BoolBadge value={node.isActive} trueLabel="ACTIVE" falseLabel="INACTIVE" />
                )}
              </div>
              <code className="text-[10px] font-mono text-slate-500">{node.id}</code>
            </div>
            <button
              type="button"
              onClick={handleClose}
              className="w-7 h-7 rounded flex items-center justify-center text-slate-500 hover:text-slate-200 hover:bg-slate-800 transition-colors flex-shrink-0"
              aria-label="닫기"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M1 1l12 12M13 1L1 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
              </svg>
            </button>
          </div>

          {/* 본문 (스크롤) */}
          <div className="flex-1 overflow-y-auto px-5 py-5 space-y-6">
            {/* Description + Tags */}
            <div>
              <p className="text-sm text-slate-300 leading-relaxed">{node.description || '—'}</p>
              {node.tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {node.tags.map((t) => (
                    <span
                      key={t}
                      className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800/60 text-slate-400 border border-slate-700/60"
                    >
                      #{t}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* LLM 설정 */}
            <div>
              <SectionLabel>LLM 설정</SectionLabel>
              <div className="rounded-lg bg-slate-800/40 border border-slate-700/50 px-4 py-3 flex flex-wrap gap-x-6 gap-y-2">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono text-slate-500">Model</span>
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono bg-violet-900/30 text-violet-300 border border-violet-700/40">
                    {node.llmConfig.model}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono text-slate-500">Temperature</span>
                  <span className="text-[12px] font-mono text-amber-300">{node.llmConfig.temperature}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono text-slate-500">Max Tokens</span>
                  <span className="text-[12px] font-mono text-sky-300">{node.llmConfig.maxTokens.toLocaleString()}</span>
                </div>
                {node.llmConfig.responseFormat && (
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-mono text-slate-500">Format</span>
                    <span className="text-[11px] font-mono text-slate-300">{node.llmConfig.responseFormat}</span>
                  </div>
                )}
              </div>
            </div>

            {/* System Prompt */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <SectionLabel>System Prompt</SectionLabel>
                {node.systemPrompt && <CopyButton text={node.systemPrompt} />}
              </div>
              {node.systemPrompt ? (
                <div className="rounded-lg bg-slate-950/80 border border-slate-700/50 px-4 py-3">
                  <pre className="text-[11px] font-mono leading-relaxed whitespace-pre-wrap break-words text-slate-300">
                    {node.systemPrompt}
                  </pre>
                </div>
              ) : (
                <p className="text-xs text-slate-600 italic">설정 없음</p>
              )}
            </div>

            {/* User Prompt Template */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <SectionLabel>User Prompt Template</SectionLabel>
                {node.userPromptTemplate && <CopyButton text={node.userPromptTemplate} />}
              </div>
              {node.userPromptTemplate ? (
                <div className="rounded-lg bg-slate-950/80 border border-slate-700/50 px-4 py-3">
                  <PromptTemplateView text={node.userPromptTemplate} />
                </div>
              ) : (
                <p className="text-xs text-slate-600 italic">설정 없음</p>
              )}
            </div>

            {/* 입력 스키마 */}
            <div>
              <SectionLabel>입력 스키마 (inputSchema)</SectionLabel>
              <div className="rounded-lg bg-slate-950/80 border border-slate-700/50 px-3 py-2.5">
                <JsonTreeView data={node.inputSchema} maxDepth={2} />
              </div>
            </div>

            {/* 출력 스키마 */}
            <div>
              <SectionLabel>출력 스키마 (outputSchema)</SectionLabel>
              <div className="rounded-lg bg-slate-950/80 border border-slate-700/50 px-3 py-2.5">
                <JsonTreeView data={node.outputSchema} maxDepth={2} />
              </div>
            </div>

            {/* Output Enforcement */}
            {enf && (
              <div>
                <SectionLabel>Output Enforcement</SectionLabel>
                <div className="rounded-lg bg-slate-800/40 border border-slate-700/50 px-4 py-3 space-y-3">
                  <div className="flex flex-wrap gap-x-5 gap-y-2">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-slate-500">enabled</span>
                      <BoolBadge value={enf.enabled} />
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-slate-500">validation</span>
                      <BoolBadge value={enf.validationEnabled} />
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-slate-500">retry</span>
                      <BoolBadge value={enf.retryOnFailure} />
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-slate-500">maxRetries</span>
                      <span className="text-[12px] font-mono text-slate-300">{enf.maxRetries}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-slate-500">schemaInPrompt</span>
                      <BoolBadge value={enf.includeSchemaInPrompt} />
                    </div>
                  </div>
                  {enf.exampleOutput && (
                    <div>
                      <div className="text-[10px] font-mono text-slate-500 mb-1.5">exampleOutput</div>
                      <div className="rounded bg-slate-950/80 border border-slate-700/40 px-3 py-2">
                        <pre className="text-[11px] font-mono text-slate-400 whitespace-pre-wrap break-words">
                          {enf.exampleOutput}
                        </pre>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 시각 */}
            <div className="flex gap-6 pt-1">
              <div>
                <span className="text-[10px] font-mono text-slate-600">생성</span>
                <span className="text-[10px] font-mono text-slate-500 ml-2">{formatDate(node.createdAt)}</span>
              </div>
              <div>
                <span className="text-[10px] font-mono text-slate-600">수정</span>
                <span className="text-[10px] font-mono text-slate-500 ml-2">{formatDate(node.updatedAt)}</span>
              </div>
            </div>
          </div>

          {/* 하단 안내 */}
          <div className="flex-shrink-0 px-5 py-3 border-t border-slate-800/60 bg-slate-950/40 rounded-b-2xl">
            <p className="text-[10px] font-mono text-slate-600 text-center">
              커스텀 AI 노드의 생성·수정·삭제는 CLI 전용입니다. 이 화면은 조회용입니다.
            </p>
          </div>
        </div>
      </div>
    </>
  );
}

// ─── 커스텀 AI 노드 카드 ──────────────────────────────────────────────────────

function CustomNodeCard({ node }: { node: AINode }) {
  const [modalOpen, setModalOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setModalOpen(true)}
        className="w-full text-left rounded-lg border border-slate-800 bg-slate-900/30 px-4 py-3 hover:bg-slate-900/60 hover:border-slate-700 transition-colors cursor-pointer"
      >
        <div className="flex items-start gap-3">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center text-sm flex-shrink-0"
            style={{ backgroundColor: node.color ? `${node.color}30` : undefined, color: node.color }}
          >
            {node.icon || 'N'}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-2 min-w-0">
              <h4 className="text-sm font-semibold text-slate-100 truncate">{node.name}</h4>
              <code className="text-[10px] font-mono text-slate-500 truncate">{node.id}</code>
            </div>
            <p className="text-xs text-slate-400 mt-0.5 line-clamp-2">{node.description}</p>
            {node.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-1.5">
                {node.tags.map((t) => (
                  <span
                    key={t}
                    className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800/60 text-slate-400 border border-slate-700/60"
                  >
                    #{t}
                  </span>
                ))}
              </div>
            )}
            <div className="mt-2 text-[10px] font-mono text-slate-600">
              클릭하여 상세 보기 →
            </div>
          </div>
        </div>
      </button>

      {modalOpen && (
        <CustomNodeDetailModal node={node} onClose={() => setModalOpen(false)} />
      )}
    </>
  );
}

export function NodeCatalogPage() {
  const { toast } = useToast();
  const [catalog, setCatalog] = useState<NodeCatalogEntry[]>([]);
  const [customNodes, setCustomNodes] = useState<AINode[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [cat, customs] = await Promise.all([
          nodeApi.getCatalog(),
          nodeApi.list().catch(() => [] as AINode[]),
        ]);
        if (!cancelled) {
          setCatalog(cat);
          setCustomNodes(customs);
        }
      } catch (e) {
        toast.error(`노드 카탈로그 조회 실패: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [toast]);

  const byCategory = useMemo(() => {
    const groups = new Map<NodeCatalogEntry['category'], NodeCatalogEntry[]>();
    for (const e of catalog) {
      const arr = groups.get(e.category) ?? [];
      arr.push(e);
      groups.set(e.category, arr);
    }
    return groups;
  }, [catalog]);

  return (
    <div className="h-full overflow-auto bg-slate-950">
      <div className="w-full px-6 py-8 space-y-8">
        <header>
          <div className="text-[11px] font-mono tracking-[0.25em] uppercase text-slate-500 mb-1">
            Nodes
          </div>
          <h1 className="text-3xl font-light text-slate-50 tracking-tight mb-3">
            노드 카탈로그
          </h1>
          <CliHint tone="subtle">
            범용 11종 노드는 시스템 내장입니다. 커스텀 AI 노드의 등록·수정·삭제는 CLI로만 가능합니다.
          </CliHint>
        </header>

        {/* Catalog (11 built-in) */}
        <section>
          <h2 className="text-sm font-mono tracking-[0.2em] uppercase text-slate-400 mb-3">
            기본 제공 노드 ({catalog.length})
          </h2>
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-20 rounded-xl bg-slate-900/40 border border-slate-800 animate-pulse" />
              ))}
            </div>
          ) : catalog.length === 0 ? (
            <EmptyState
              icon={'⚠'}
              title="카탈로그를 로드할 수 없습니다"
              description="백엔드 /api/v1/nodes/catalog 응답을 확인하세요."
            />
          ) : (
            <div className="space-y-6">
              {CATEGORY_ORDER.map((cat) => {
                const items = byCategory.get(cat) ?? [];
                if (items.length === 0) return null;
                return (
                  <div key={cat}>
                    <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-500 mb-2">
                      {CATEGORY_LABEL[cat]}
                    </div>
                    <div className="space-y-2">
                      {items.map((e) => (
                        <CatalogCard key={e.defType} entry={e} />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Custom AI nodes */}
        <section>
          <h2 className="text-sm font-mono tracking-[0.2em] uppercase text-slate-400 mb-3">
            커스텀 AI 노드 ({customNodes.length})
          </h2>
          {customNodes.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-800 px-6 py-8 text-center text-sm text-slate-500">
              등록된 커스텀 AI 노드가 없습니다. CLI로 등록하세요.
              <div className="mt-2 text-[11px] font-mono text-sky-300">
                curl -X POST http://localhost:8002/api/v1/nodes
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {customNodes.map((n) => (
                <CustomNodeCard key={n.id} node={n} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
