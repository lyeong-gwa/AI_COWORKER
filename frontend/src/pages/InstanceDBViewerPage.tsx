/**
 * InstanceDB Viewer Page (`/instance-dbs`)
 *
 * Phase D — 읽기 전용. 생성·수정·삭제는 CLI로만 가능.
 * 레이아웃 패턴: KnowledgeViewerPage (좌 목록 + 우 상세) 동일.
 *
 * viewerHints 지원: 컬렉션 메타의 viewerHints 를 참조해 필드별 렌더러 적용.
 * markdown | text | tag | code | json
 */
import { useEffect, useMemo, useState } from 'react';
import { instanceDbApi } from '../services/api';
import type { InstanceDB, InstanceDBRecord, InstanceDBRecordListResponse } from '../types';
import { CliHint } from '../components/common/CliHint';
import { EmptyState } from '../components/common/EmptyState';
import { useToast } from '../components/common/Toast';
import { StyledMarkdown } from '../components/common/StyledMarkdown';

const RECORDS_LIMIT = 20;

// ─── Field renderer ───────────────────────────────────────────────────────────

function FieldValue({
  value,
  hint,
}: {
  value: unknown;
  hint?: string;
}) {
  const str = typeof value === 'string' ? value : JSON.stringify(value, null, 2);

  switch (hint) {
    case 'markdown':
      return (
        <div className="mt-1 rounded-lg border border-slate-700/60 bg-slate-950/60 px-4 py-3 text-sm text-slate-200">
          <StyledMarkdown variant="comment">{str}</StyledMarkdown>
        </div>
      );
    case 'tag':
      return (
        <div className="mt-1 flex flex-wrap gap-1.5">
          {str.split(',').map((v, i) => (
            <span
              key={i}
              className="px-2 py-0.5 rounded-full bg-cyan-900/40 text-cyan-300 text-xs border border-cyan-800/50"
            >
              {v.trim()}
            </span>
          ))}
        </div>
      );
    case 'code':
      return (
        <pre className="mt-1 text-[11px] font-mono bg-slate-800/60 text-emerald-300 rounded px-3 py-2 whitespace-pre-wrap break-all">
          {str}
        </pre>
      );
    case 'json':
      return (
        <pre className="mt-1 text-[11px] font-mono bg-slate-800/60 text-amber-300 rounded px-3 py-2 whitespace-pre-wrap break-all">
          {(() => {
            try {
              return JSON.stringify(typeof value === 'string' ? JSON.parse(value) : value, null, 2);
            } catch {
              return str;
            }
          })()}
        </pre>
      );
    case 'text':
      return (
        <p className="mt-1 text-sm text-slate-200 whitespace-pre-wrap leading-relaxed">{str}</p>
      );
    default:
      // plain — compact single-line for short values, preformatted for long/nested
      if (typeof value === 'object' && value !== null) {
        return (
          <pre className="mt-1 text-[11px] font-mono text-slate-300 whitespace-pre-wrap break-all">
            {JSON.stringify(value, null, 2)}
          </pre>
        );
      }
      return <span className="ml-2 text-sm text-slate-300 font-mono">{str}</span>;
  }
}

// ─── Record card ──────────────────────────────────────────────────────────────

// ─── Download buttons ─────────────────────────────────────────────────────────

const EXPORT_FORMATS: Array<{ fmt: 'md' | 'csv' | 'html' | 'xlsx'; label: string; title: string }> = [
  { fmt: 'md',   label: 'MD',   title: 'Markdown 다운로드' },
  { fmt: 'csv',  label: 'CSV',  title: 'CSV 다운로드 (UTF-8 BOM)' },
  { fmt: 'html', label: 'HTML', title: 'HTML 다운로드' },
  { fmt: 'xlsx', label: 'XLSX', title: 'Excel 다운로드' },
];

function RecordExportButtons({
  dbId,
  recId,
}: {
  dbId: string;
  recId: string;
}) {
  return (
    <div className="flex items-center gap-1 flex-wrap">
      <span className="text-[9px] font-mono text-slate-600 mr-0.5">Export:</span>
      {EXPORT_FORMATS.map(({ fmt, label, title }) => (
        <a
          key={fmt}
          href={instanceDbApi.recordExportUrl(dbId, recId, fmt)}
          download
          title={title}
          className="px-1.5 py-0.5 rounded border border-slate-700/60 text-[9px] font-mono text-slate-400 hover:text-slate-100 hover:border-slate-500 hover:bg-slate-800/60 transition-colors select-none"
        >
          {label}
        </a>
      ))}
    </div>
  );
}

// ─── Record card ──────────────────────────────────────────────────────────────

function RecordCard({
  record,
  dbId,
  viewerHints,
}: {
  record: InstanceDBRecord;
  dbId: string;
  viewerHints: Record<string, string>;
}) {
  const [expanded, setExpanded] = useState(false);

  const hasHints = Object.keys(viewerHints).length > 0;

  // Keys with markdown hint should always be expanded-visible (they're big)
  const mdKeys = Object.entries(viewerHints)
    .filter(([, h]) => h === 'markdown')
    .map(([k]) => k);

  const dataKeys = Object.keys(record.data);

  // For the collapsed preview: show non-markdown fields inline
  const previewStr = useMemo(() => {
    try {
      if (hasHints) {
        const previewObj: Record<string, unknown> = {};
        dataKeys.forEach((k) => {
          if (!mdKeys.includes(k)) previewObj[k] = record.data[k];
        });
        return JSON.stringify(previewObj);
      }
      return JSON.stringify(record.data);
    } catch {
      return String(record.data);
    }
  }, [record.data, hasHints, dataKeys, mdKeys]);

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 overflow-hidden">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-b border-slate-800 bg-slate-900/60">
        <span className="font-mono text-[10px] text-slate-500 truncate max-w-[140px]" title={record.id}>
          {record.id.slice(0, 16)}…
        </span>
        {record.sourceWorkflowId && (
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800/60 border border-slate-700/50 text-slate-400 truncate max-w-[120px]" title={record.sourceWorkflowId}>
            wf: {record.sourceWorkflowId.slice(0, 8)}
          </span>
        )}
        {record.sourceExecutionId && (
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800/60 border border-slate-700/50 text-slate-400 truncate max-w-[120px]" title={record.sourceExecutionId}>
            ex: {record.sourceExecutionId.slice(0, 8)}
          </span>
        )}
        <span className="ml-auto text-[10px] font-mono text-slate-600 flex-shrink-0">
          {new Date(record.createdAt).toLocaleString('ko-KR')}
        </span>
      </div>

      {/* Body */}
      <div className="px-4 py-3">
        {hasHints ? (
          /* hints-aware rendering:
             - collapsed: markdown fields always visible + compact preview line for rest
             - expanded: all fields visible with their renderer */
          <dl className="space-y-3">
            {/* Always show markdown fields */}
            {mdKeys.map((key) => (
              <div key={key}>
                <dt className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-0.5">
                  {key}
                </dt>
                <dd>
                  <FieldValue value={record.data[key]} hint="markdown" />
                </dd>
              </div>
            ))}
            {/* Non-markdown fields: collapsed preview or expanded rows */}
            {!expanded ? (
              <div>
                <p className="text-[11px] font-mono text-slate-500 truncate">{previewStr}</p>
              </div>
            ) : (
              dataKeys
                .filter((k) => !mdKeys.includes(k))
                .map((key) => {
                  const hint = viewerHints[key];
                  return (
                    <div key={key}>
                      <dt className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-0.5">
                        {key}
                      </dt>
                      <dd>
                        <FieldValue value={record.data[key]} hint={hint} />
                      </dd>
                    </div>
                  );
                })
            )}
          </dl>
        ) : (
          /* no hints — original plain JSON view */
          expanded ? (
            <pre className="text-[11px] font-mono text-slate-300 whitespace-pre-wrap break-all leading-relaxed">
              {JSON.stringify(record.data, null, 2)}
            </pre>
          ) : (
            <p className="text-[11px] font-mono text-slate-400 truncate">{previewStr}</p>
          )
        )}
        <div className="mt-2 flex items-center justify-between flex-wrap gap-2">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-[10px] font-mono text-sky-400 hover:text-sky-300 transition-colors"
          >
            {expanded ? '▲ 접기' : '▼ 모든 필드 펼치기'}
          </button>
          <RecordExportButtons dbId={dbId} recId={record.id} />
        </div>
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export function InstanceDBViewerPage() {
  const { toast } = useToast();
  const [dbs, setDbs] = useState<InstanceDB[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  // Records state
  const [records, setRecords] = useState<InstanceDBRecord[]>([]);
  const [recordsTotal, setRecordsTotal] = useState(0);
  const [recordsOffset, setRecordsOffset] = useState(0);
  const [recordsLoading, setRecordsLoading] = useState(false);

  // Load InstanceDB list
  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const data = await instanceDbApi.list();
        if (!cancelled) {
          setDbs(data);
          if (data.length > 0 && !selectedId) setSelectedId(data[0].id);
        }
      } catch (e) {
        toast.error(`인스턴스DB 조회 실패: ${e instanceof Error ? e.message : String(e)}`);
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

  // Load records when selected DB changes
  useEffect(() => {
    if (!selectedId) {
      setRecords([]);
      setRecordsTotal(0);
      setRecordsOffset(0);
      return;
    }
    let cancelled = false;
    async function loadRecords() {
      setRecordsLoading(true);
      setRecordsOffset(0);
      try {
        const res: InstanceDBRecordListResponse = await instanceDbApi.listRecords(selectedId!, {
          limit: RECORDS_LIMIT,
          offset: 0,
        });
        if (!cancelled) {
          setRecords(res.items ?? []);
          setRecordsTotal(res.total ?? 0);
          setRecordsOffset(res.offset ?? 0);
        }
      } catch (e) {
        if (!cancelled) {
          toast.error(`레코드 조회 실패: ${e instanceof Error ? e.message : String(e)}`);
        }
      } finally {
        if (!cancelled) setRecordsLoading(false);
      }
    }
    loadRecords();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  // Load more records
  async function loadMore() {
    if (!selectedId) return;
    const nextOffset = recordsOffset + RECORDS_LIMIT;
    setRecordsLoading(true);
    try {
      const res: InstanceDBRecordListResponse = await instanceDbApi.listRecords(selectedId, {
        limit: RECORDS_LIMIT,
        offset: nextOffset,
      });
      setRecords((prev) => [...prev, ...(res.items ?? [])]);
      setRecordsOffset(nextOffset);
    } catch (e) {
      toast.error(`레코드 추가 조회 실패: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setRecordsLoading(false);
    }
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return dbs;
    return dbs.filter(
      (d) =>
        d.name.toLowerCase().includes(q) ||
        (d.description ?? '').toLowerCase().includes(q) ||
        d.tags?.some((t) => t.toLowerCase().includes(q)),
    );
  }, [dbs, query]);

  const selected = dbs.find((d) => d.id === selectedId) ?? null;

  const hasMoreRecords = records.length < recordsTotal;

  return (
    <div className="h-full flex flex-col bg-slate-950">
      {/* Header */}
      <div className="px-6 pt-6 pb-4 border-b border-slate-800">
        <div className="w-full">
          <div className="text-[11px] font-mono tracking-[0.25em] uppercase text-slate-500 mb-1">
            Instance DBs
          </div>
          <h1 className="text-2xl font-light text-slate-50 tracking-tight mb-3">인스턴스DB</h1>
          <CliHint tone="subtle">
            인스턴스DB의 생성·수정·삭제는 CLI로만 가능합니다. 웹 UI에서는 조회만 지원합니다.
          </CliHint>
        </div>
      </div>

      <div className="flex-1 overflow-hidden flex">
        {/* Sidebar list */}
        <aside className="w-96 flex-shrink-0 border-r border-slate-800 bg-slate-950 flex flex-col">
          <div className="p-3 border-b border-slate-800">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="이름·설명·태그 검색"
              className="w-full px-3 py-2 rounded-lg bg-slate-900/60 border border-slate-800 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-sky-600"
            />
          </div>

          <div className="flex-1 overflow-auto">
            {loading ? (
              <div className="p-4 space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="h-14 bg-slate-900/40 rounded animate-pulse" />
                ))}
              </div>
            ) : filtered.length === 0 ? (
              <div className="p-6 text-center text-xs text-slate-500">
                {dbs.length === 0 ? '등록된 인스턴스DB가 없습니다' : '조건에 맞는 항목 없음'}
              </div>
            ) : (
              <ul>
                {filtered.map((db) => (
                  <li key={db.id}>
                    <button
                      onClick={() => setSelectedId(db.id)}
                      className={`w-full text-left px-4 py-3 border-l-2 transition-colors ${
                        selectedId === db.id
                          ? 'bg-slate-900 border-teal-500 text-slate-100'
                          : 'border-transparent text-slate-400 hover:bg-slate-900/60 hover:text-slate-200'
                      }`}
                    >
                      <div className="text-sm font-medium truncate">{db.name}</div>
                      <div className="text-[10px] font-mono text-slate-500 mt-0.5 truncate">
                        {db.description
                          ? db.description.slice(0, 60)
                          : 'no description'}
                      </div>
                      {db.tags?.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {db.tags.slice(0, 4).map((t) => (
                            <span
                              key={t}
                              className="text-[9px] font-mono px-1 py-0.5 rounded bg-teal-900/30 border border-teal-800/50 text-teal-400"
                            >
                              #{t}
                            </span>
                          ))}
                        </div>
                      )}
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
            <div className="w-full px-8 py-8 space-y-8">
              {/* Meta header */}
              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500">
                  Instance DB
                </div>
                <h2 className="text-2xl font-semibold text-slate-50 mt-1">{selected.name}</h2>
                {selected.description && (
                  <p className="text-sm text-slate-400 mt-1 leading-relaxed">{selected.description}</p>
                )}
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {selected.tags?.map((t) => (
                    <span
                      key={t}
                      className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-teal-900/30 border border-teal-700/50 text-teal-300"
                    >
                      #{t}
                    </span>
                  ))}
                </div>
                <div className="text-[11px] font-mono text-slate-600 mt-2">
                  {selected.id}
                  {' · '}
                  생성 {new Date(selected.createdAt).toLocaleString('ko-KR')}
                  {' · '}
                  수정 {new Date(selected.updatedAt).toLocaleString('ko-KR')}
                </div>
              </div>

              {/* Records section */}
              <section>
                <div className="flex items-baseline gap-3 mb-3">
                  <h3 className="text-xs font-mono uppercase tracking-[0.2em] text-slate-500">
                    Records
                  </h3>
                  <span className="text-[10px] font-mono text-slate-600">
                    {recordsLoading && records.length === 0
                      ? '로딩 중…'
                      : `${records.length} / ${recordsTotal}`}
                  </span>
                </div>

                {recordsLoading && records.length === 0 ? (
                  <div className="space-y-2">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <div key={i} className="h-16 bg-slate-900/40 rounded-lg animate-pulse" />
                    ))}
                  </div>
                ) : records.length === 0 ? (
                  <EmptyState
                    icon={'∅'}
                    title="레코드가 없습니다"
                    description="워크플로우의 instance-db-insert 노드가 실행되면 레코드가 누적됩니다."
                  />
                ) : (
                  <div className="space-y-3">
                    {records.map((rec) => (
                      <RecordCard key={rec.id} record={rec} dbId={selected!.id} viewerHints={selected?.viewerHints ?? {}} />
                    ))}

                    {hasMoreRecords && (
                      <button
                        onClick={loadMore}
                        disabled={recordsLoading}
                        className="w-full py-2.5 rounded-lg border border-slate-700/60 text-xs font-mono text-slate-400 hover:text-slate-200 hover:border-slate-600 transition-colors disabled:opacity-50"
                      >
                        {recordsLoading ? '로딩 중…' : `더보기 (${recordsTotal - records.length}건 남음)`}
                      </button>
                    )}
                  </div>
                )}
              </section>
            </div>
          ) : !loading ? (
            <EmptyState
              icon={'📦'}
              title="등록된 인스턴스DB가 없습니다"
              description="CLI로 인스턴스DB를 등록하세요."
              hint="curl -X POST http://localhost:8002/api/v1/instance-dbs"
            />
          ) : null}
        </main>
      </div>
    </div>
  );
}
