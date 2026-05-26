/**
 * API Definition Viewer Page (`/api-definitions`)
 *
 * Phase 3b — 읽기 전용 축소판. 생성·수정·삭제 버튼 모두 제거.
 */
import { useEffect, useMemo, useState } from 'react';
import { apiDefinitionApi } from '../services/api';
import type { ApiDefinition } from '../types';
import { CliHint } from '../components/common/CliHint';
import { EmptyState } from '../components/common/EmptyState';
import { useToast } from '../components/common/Toast';

const METHOD_TONE: Record<string, string> = {
  GET: 'bg-emerald-900/40 text-emerald-200 border-emerald-700/60',
  POST: 'bg-sky-900/40 text-sky-200 border-sky-700/60',
  PUT: 'bg-amber-900/40 text-amber-200 border-amber-700/60',
  PATCH: 'bg-amber-900/40 text-amber-200 border-amber-700/60',
  DELETE: 'bg-rose-900/40 text-rose-200 border-rose-700/60',
};

export default function ApiDefinitionViewerPage() {
  const { toast } = useToast();
  const [defs, setDefs] = useState<ApiDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const data = await apiDefinitionApi.list();
        if (!cancelled) {
          setDefs(data);
          if (data.length > 0 && !selectedId) setSelectedId(data[0].id);
        }
      } catch (e) {
        toast.error(`API 명세 조회 실패: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toast]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return defs;
    return defs.filter(
      (d) =>
        d.name.toLowerCase().includes(q) ||
        d.urlTemplate.toLowerCase().includes(q) ||
        d.tags?.some((t) => t.toLowerCase().includes(q)),
    );
  }, [defs, query]);

  const selected = defs.find((d) => d.id === selectedId) ?? null;

  return (
    <div className="h-full flex flex-col bg-slate-950">
      <div className="px-6 pt-6 pb-4 border-b border-slate-800">
        <div className="w-full">
          <div className="text-[11px] font-mono tracking-[0.25em] uppercase text-slate-500 mb-1">
            API Definitions
          </div>
          <h1 className="text-2xl font-light text-slate-50 tracking-tight mb-3">API 명세</h1>
          <CliHint tone="subtle">
            API 명세의 생성·수정·삭제는 CLI로만 가능합니다. 웹 UI에서는 조회만 지원합니다.
          </CliHint>
        </div>
      </div>

      <div className="flex-1 overflow-hidden flex">
        {/* List */}
        <aside className="w-96 flex-shrink-0 border-r border-slate-800 bg-slate-950 flex flex-col">
          <div className="p-3 border-b border-slate-800">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="이름·URL·태그 검색"
              className="w-full px-3 py-2 rounded-lg bg-slate-900/60 border border-slate-800 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-sky-600"
            />
          </div>
          <div className="flex-1 overflow-auto">
            {loading ? (
              <div className="p-4 space-y-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="h-14 bg-slate-900/40 rounded animate-pulse" />
                ))}
              </div>
            ) : filtered.length === 0 ? (
              <div className="p-6 text-center text-xs text-slate-500">
                {defs.length === 0 ? '등록된 API 명세가 없습니다' : '조건에 맞는 항목 없음'}
              </div>
            ) : (
              <ul>
                {filtered.map((d) => (
                  <li key={d.id}>
                    <button
                      onClick={() => setSelectedId(d.id)}
                      className={`w-full text-left px-4 py-3 border-l-2 transition-colors ${
                        selectedId === d.id
                          ? 'bg-slate-900 border-sky-500 text-slate-100'
                          : 'border-transparent text-slate-400 hover:bg-slate-900/60 hover:text-slate-200'
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold border ${
                            METHOD_TONE[d.method] ?? 'bg-slate-800 text-slate-300 border-slate-700'
                          }`}
                        >
                          {d.method}
                        </span>
                        <span className="text-sm font-medium truncate">{d.name}</span>
                      </div>
                      <div className="text-[10px] font-mono text-slate-500 truncate">
                        {d.urlTemplate}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>

        {/* Detail */}
        <main className="flex-1 overflow-auto">
          {selected ? (
            <div className="w-full px-8 py-8 space-y-6">
              <header>
                <div className="flex items-center gap-3 mb-2">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-mono font-bold border ${
                      METHOD_TONE[selected.method] ?? 'bg-slate-800 text-slate-300 border-slate-700'
                    }`}
                  >
                    {selected.method}
                  </span>
                  <h2 className="text-2xl font-semibold text-slate-50">{selected.name}</h2>
                </div>
                {selected.description && (
                  <p className="text-sm text-slate-400">{selected.description}</p>
                )}
                <div className="text-[11px] font-mono text-slate-600 mt-2">{selected.id}</div>
              </header>

              <section>
                <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-1.5">
                  URL
                </div>
                <pre className="text-sm font-mono text-sky-200 px-4 py-3 rounded-lg bg-slate-900/60 border border-slate-800 break-all whitespace-pre-wrap">
                  {selected.urlTemplate}
                </pre>
              </section>

              {selected.parameters.length > 0 && (
                <section>
                  <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-1.5">
                    Parameters ({selected.parameters.length})
                  </div>
                  <div className="rounded-lg border border-slate-800 overflow-hidden">
                    <table className="w-full text-xs">
                      <thead className="bg-slate-900 text-slate-400 font-mono uppercase text-[10px] tracking-wider">
                        <tr>
                          <th className="text-left px-3 py-2">Name</th>
                          <th className="text-left px-3 py-2">In</th>
                          <th className="text-left px-3 py-2">Type</th>
                          <th className="text-left px-3 py-2">Req</th>
                          <th className="text-left px-3 py-2">Description</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800">
                        {selected.parameters.map((p) => (
                          <tr key={`${p.in}-${p.name}`} className="bg-slate-950/40">
                            <td className="px-3 py-2 font-mono text-slate-200">{p.name}</td>
                            <td className="px-3 py-2 font-mono text-slate-400">{p.in}</td>
                            <td className="px-3 py-2 font-mono text-slate-400">{p.type}</td>
                            <td className="px-3 py-2">
                              {p.required ? (
                                <span className="text-rose-300">●</span>
                              ) : (
                                <span className="text-slate-600">○</span>
                              )}
                            </td>
                            <td className="px-3 py-2 text-slate-400">{p.description}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              {(selected.responseSchema?.fields?.length ?? 0) > 0 && (
                <section>
                  <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-1.5">
                    Response Schema
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-1.5">
                    {selected.responseSchema?.fields?.map((f) => (
                      <div
                        key={f.field}
                        className="flex items-baseline gap-3 text-xs font-mono"
                      >
                        <span className="text-slate-200 flex-shrink-0">{f.field}</span>
                        <span className="text-slate-500">{f.type}</span>
                        <span className="text-slate-600 truncate">{f.description}</span>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {selected.bodyTemplate && (
                <section>
                  <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-1.5">
                    Body Template
                  </div>
                  <pre className="text-xs font-mono text-slate-200 px-4 py-3 rounded-lg bg-slate-900/60 border border-slate-800 whitespace-pre-wrap break-all">
                    {selected.bodyTemplate}
                  </pre>
                </section>
              )}
            </div>
          ) : !loading ? (
            <EmptyState
              icon={'∅'}
              title="API 명세가 없습니다"
              description="CLI로 API 명세를 등록하세요."
              hint="curl -X POST http://localhost:8002/api/v1/api-definitions"
            />
          ) : null}
        </main>
      </div>
    </div>
  );
}
