/**
 * Node Catalog Page (`/nodes`)
 *
 * Phase 3b — 11종 범용 노드 카탈로그 + 커스텀 AI 노드 목록 (읽기 전용).
 * 편집·생성 UI 모두 제거. 모든 관리는 CLI로 이관.
 */
import { useEffect, useMemo, useState } from 'react';
import { nodeApi, type NodeCatalogEntry } from '../services/api';
import type { AINode } from '../types';
import { CliHint } from '../components/common/CliHint';
import { EmptyState } from '../components/common/EmptyState';
import { useToast } from '../components/common/Toast';

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

function CustomNodeCard({ node }: { node: AINode }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/30 px-4 py-3">
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
        </div>
      </div>
    </div>
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
