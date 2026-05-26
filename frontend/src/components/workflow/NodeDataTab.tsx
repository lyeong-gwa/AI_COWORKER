/**
 * NodeDataTab — 노드 검사 드로어의 "데이터" 탭.
 *
 * 설계: `docs/node-inspector-plan.md` v2.1 §5 Phase 2
 *
 * 7종 분기:
 *   form-start      — config.fields read-only form preview (F-4)
 *   mapper          — factoryApi.getWarehouse(config.warehouseNodeId) entries
 *   knowledge       — knowledgeApi.list({ category, limit, offset })
 *   result          — factoryApi.getWarehouse(nodeId) entries, <pre> 렌더
 *   markdown-viewer — factoryApi.getWarehouse(nodeId) entries, StyledMarkdown 렌더
 *   instance-db-insert — instanceDbApi.listRecords(..., R-9 컨텍스트 필터)
 *   instance-db-lookup — 동일 + "조회만" 배너
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
/* eslint-disable react-hooks/set-state-in-effect */
import { useEffect, useState, useCallback } from 'react';
import type { Node } from '@xyflow/react';
import type { Workflow, WorkflowExecution, KnowledgeDocument, InstanceDBRecord } from '../../types';
import {
  factoryApi,
  knowledgeApi,
  instanceDbApi,
  type WarehouseInstanceEntry,
} from '../../services/api';
import { JsonTreeView } from '../common/JsonTreeView';
import { StyledMarkdown } from '../common/StyledMarkdown';
import { extractEntryBody } from './extractEntryBody';

const LEGACY_DEF_TYPE_MAP: Record<string, string> = { form: 'form-start' };

const PAGE_SIZE = 20;

// ─── Props ────────────────────────────────────────────────────────────────

export interface NodeDataTabProps {
  node: Node<any>;
  workflow: Workflow;
  /** InstanceDetailPage から渡す実行インスタンス */
  instance?: WorkflowExecution & { instanceId?: string; id?: string };
  /** 'workflow' = WorkflowViewerPage, 'instance' = InstanceDetailPage */
  pageContext: 'workflow' | 'instance';
  /**
   * [P-6] 데이터 탭에서 warehouse total 이 처음 도착하면 호출 —
   * NodeInspectorDrawer 가 캐시해 두었다가 정보 탭의 limit=1 fetch 를 생략시킨다.
   */
  onWarehouseTotalFetched?: (nodeId: string, total: number) => void;
}

// ─── Component ───────────────────────────────────────────────────────────

export function NodeDataTab({ node, workflow, instance, pageContext, onWarehouseTotalFetched }: NodeDataTabProps) {
  const inst = workflow.nodes.find((n) => n.id === node.id);
  const rawDefType = inst?.definitionType ?? (node.data?.definitionType as string | undefined) ?? '';
  const defType = LEGACY_DEF_TYPE_MAP[rawDefType] ?? rawDefType;
  const config = (inst?.config ?? {}) as Record<string, unknown>;

  switch (defType) {
    case 'form-start':
      return <FormStartDataTab config={config} />;
    case 'mapper':
      return <MapperDataTab config={config} onWarehouseTotalFetched={onWarehouseTotalFetched} />;
    case 'knowledge':
      return <KnowledgeDataTab config={config} />;
    case 'result':
      return <WarehouseDataTab nodeId={node.id} renderMode="pre" onWarehouseTotalFetched={onWarehouseTotalFetched} />;
    case 'markdown-viewer':
      return <WarehouseDataTab nodeId={node.id} renderMode="markdown" onWarehouseTotalFetched={onWarehouseTotalFetched} />;
    case 'instance-db-insert':
      return (
        <InstanceDbDataTab
          config={config}
          workflow={workflow}
          instance={instance}
          pageContext={pageContext}
          isLookup={false}
        />
      );
    case 'instance-db-lookup':
      return (
        <InstanceDbDataTab
          config={config}
          workflow={workflow}
          instance={instance}
          pageContext={pageContext}
          isLookup={true}
        />
      );
    default:
      return (
        <DataTabWrapper>
          <DataEmpty message="이 노드는 데이터 탭을 지원하지 않습니다." />
        </DataTabWrapper>
      );
  }
}

// ─── Shared UI helpers ────────────────────────────────────────────────────

function DataTabWrapper({ children }: { children: React.ReactNode }) {
  return <div className="px-4 py-4 space-y-4 text-sm">{children}</div>;
}

function DataLoading() {
  return (
    <div className="flex items-center gap-2 py-6 text-gray-500 text-xs">
      <span className="animate-spin text-base">↻</span>
      <span>불러오는 중…</span>
    </div>
  );
}

function DataError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-md border border-rose-700/40 bg-rose-950/30 px-3 py-2.5 space-y-2">
      <p className="text-xs text-rose-300">{message}</p>
      <button
        onClick={onRetry}
        className="text-[10px] font-mono text-rose-400 hover:text-rose-200 underline"
      >
        재시도 ↻
      </button>
    </div>
  );
}

function DataEmpty({ message }: { message: string }) {
  return (
    <p className="text-xs text-gray-500 italic py-4 text-center">{message}</p>
  );
}

interface PaginatorProps {
  page: number;
  total: number;
  pageSize: number;
  onPrev: () => void;
  onNext: () => void;
}

function Paginator({ page, total, pageSize, onPrev, onNext }: PaginatorProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex items-center justify-between pt-3 border-t border-slate-800 text-[11px] text-gray-400">
      <button
        onClick={onPrev}
        disabled={page === 0}
        className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        ← 이전
      </button>
      <span>
        {page + 1} / {totalPages}{' '}
        <span className="text-gray-600">(전체 {total}개)</span>
      </span>
      <button
        onClick={onNext}
        disabled={(page + 1) * pageSize >= total}
        className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        다음 →
      </button>
    </div>
  );
}

function RefreshHeader({ title, onRefresh }: { title: string; onRefresh: () => void }) {
  return (
    <div className="flex items-center justify-between mb-2">
      <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
        {title}
      </span>
      <button
        onClick={onRefresh}
        title="새로고침 (M-2)"
        className="text-gray-600 hover:text-gray-300 transition-colors text-sm leading-none"
        aria-label="새로고침"
      >
        ↻
      </button>
    </div>
  );
}

// ─── 1. form-start — read-only form preview (F-4) ────────────────────────

interface FormField {
  name: string;
  label?: string;
  type?: string;
  placeholder?: string;
  defaultValue?: unknown;
  options?: Array<{ label: string; value: string }>;
  required?: boolean;
}

function FormStartDataTab({ config }: { config: Record<string, unknown> }) {
  const fields = (config.fields as FormField[] | undefined) ?? [];

  if (fields.length === 0) {
    return (
      <DataTabWrapper>
        <DataEmpty message="config.fields 가 없습니다. CLI 로 폼 필드를 정의하세요." />
      </DataTabWrapper>
    );
  }

  return (
    <DataTabWrapper>
      <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-3">
        폼 미리보기 (read-only)
      </div>
      <div className="space-y-3">
        {fields.map((f, i) => (
          <FormFieldPreview key={f.name ?? i} field={f} />
        ))}
      </div>
      <p className="text-[10px] text-gray-600 italic mt-3 border-t border-slate-800 pt-2">
        실제 제출 없음 — 워크플로우 실행 시 사용자가 입력하는 폼입니다.
      </p>
    </DataTabWrapper>
  );
}

function FormFieldPreview({ field }: { field: FormField }) {
  const label = field.label ?? field.name;
  const type = field.type ?? 'text';
  const placeholder = field.placeholder ?? '';
  const defaultVal =
    field.defaultValue !== undefined && field.defaultValue !== null
      ? String(field.defaultValue)
      : '';

  return (
    <div className="space-y-1">
      <label className="text-[11px] font-medium text-gray-300 flex items-center gap-1">
        {label}
        {field.required && <span className="text-amber-400 text-[10px]">*</span>}
        <span className="text-[9px] font-mono text-gray-600 ml-1">({type})</span>
      </label>
      {type === 'textarea' ? (
        <textarea
          disabled
          placeholder={placeholder}
          defaultValue={defaultVal}
          rows={3}
          className="w-full text-[11px] font-mono bg-slate-900 border border-slate-700/60 rounded px-2.5 py-1.5 text-gray-400 resize-none opacity-70 cursor-not-allowed"
        />
      ) : type === 'select' ? (
        <select
          disabled
          defaultValue={defaultVal}
          className="w-full text-[11px] font-mono bg-slate-900 border border-slate-700/60 rounded px-2.5 py-1.5 text-gray-400 opacity-70 cursor-not-allowed"
        >
          {!defaultVal && <option value="">— 선택 —</option>}
          {(field.options ?? []).map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      ) : (
        <input
          disabled
          type={type === 'number' ? 'number' : 'text'}
          placeholder={placeholder}
          defaultValue={defaultVal}
          className="w-full text-[11px] font-mono bg-slate-900 border border-slate-700/60 rounded px-2.5 py-1.5 text-gray-400 opacity-70 cursor-not-allowed"
        />
      )}
    </div>
  );
}

// ─── 2. mapper — warehouse entries (H-1) ─────────────────────────────────

function MapperDataTab({
  config,
  onWarehouseTotalFetched,
}: {
  config: Record<string, unknown>;
  onWarehouseTotalFetched?: (nodeId: string, total: number) => void;
}) {
  const warehouseNodeId = (config.warehouseNodeId as string | undefined) ?? '';
  const [items, setItems] = useState<WarehouseInstanceEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  const fetchData = useCallback(() => {
    if (!warehouseNodeId) return;
    let cancelled = false;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    factoryApi
      .getWarehouse(warehouseNodeId, { limit: PAGE_SIZE, skip: page * PAGE_SIZE })
      .then((res) => {
        if (cancelled) return;
        setItems(res.items as unknown as WarehouseInstanceEntry[]);
        setTotal(res.total);
        // [P-6] 첫 응답 도착 시 total 을 드로어 캐시에 저장 (정보 탭 limit=1 fetch 생략용)
        onWarehouseTotalFetched?.(warehouseNodeId, res.total);
      })
      .catch((e) => {
        if (cancelled || (e as DOMException)?.name === 'AbortError') return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [warehouseNodeId, page, retryToken, onWarehouseTotalFetched]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const cleanup = fetchData();
    return cleanup;
  }, [fetchData]);

  if (!warehouseNodeId) {
    return (
      <DataTabWrapper>
        <DataEmpty message="참조 창고 미설정 — config.warehouseNodeId 가 비어있습니다." />
      </DataTabWrapper>
    );
  }

  return (
    <DataTabWrapper>
      <div className="rounded bg-sky-900/20 border border-sky-700/30 px-3 py-1.5 text-[11px] text-sky-300 mb-1">
        이 미리보기는 mapper 가 매칭에 사용하는 창고(<span className="font-mono">{warehouseNodeId.slice(0, 12)}…</span>)의 records 입니다.
      </div>
      <RefreshHeader
        title={`창고 Records${total > 0 ? ` (${total}개)` : ''}`}
        onRefresh={() => { setPage(0); setRetryToken((t) => t + 1); }}
      />
      {loading ? (
        <DataLoading />
      ) : error ? (
        <DataError message={`창고 조회 실패: ${error}`} onRetry={() => setRetryToken((t) => t + 1)} />
      ) : items.length === 0 ? (
        <DataEmpty message="적재된 데이터가 없습니다. 워크플로우를 실행하면 데이터가 생성됩니다." />
      ) : (
        <>
          <WarehouseEntryList items={items} renderMode="pre" />
          <Paginator page={page} total={total} pageSize={PAGE_SIZE} onPrev={() => setPage((p) => Math.max(0, p - 1))} onNext={() => setPage((p) => p + 1)} />
        </>
      )}
    </DataTabWrapper>
  );
}

// ─── 3. knowledge — knowledge documents (H-2) ────────────────────────────

function KnowledgeDataTab({ config }: { config: Record<string, unknown> }) {
  const categories = (config.categories as string[] | undefined) ?? [];
  const tags = (config.tags as string[] | undefined) ?? [];
  const firstCategory = categories[0];

  const [docs, setDocs] = useState<KnowledgeDocument[]>([]);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    knowledgeApi
      .list({ category: firstCategory, limit: PAGE_SIZE, offset: page * PAGE_SIZE })
      .then((results) => {
        if (cancelled) return;
        // 클라이언트 태그 필터 (AND)
        const filtered =
          tags.length > 0
            ? results.filter((d) => tags.every((t) => d.tags.includes(t)))
            : results;
        setDocs(filtered);
      })
      .catch((e) => {
        if (cancelled || (e as DOMException)?.name === 'AbortError') return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [firstCategory, tags.join(','), page, retryToken]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <DataTabWrapper>
      <RefreshHeader
        title="지식문서"
        onRefresh={() => { setPage(0); setRetryToken((t) => t + 1); }}
      />
      {loading ? (
        <DataLoading />
      ) : error ? (
        <DataError message={`지식문서 조회 실패: ${error}`} onRetry={() => setRetryToken((t) => t + 1)} />
      ) : docs.length === 0 ? (
        <DataEmpty message={firstCategory ? `'${firstCategory}' 카테고리에 해당하는 지식문서가 없습니다.` : '지식문서가 없습니다.'} />
      ) : (
        <div className="space-y-2">
          {docs.map((doc) => (
            <KnowledgeDocRow
              key={doc.id}
              doc={doc}
              expanded={expandedId === doc.id}
              onToggle={() => setExpandedId((id) => (id === doc.id ? null : doc.id))}
            />
          ))}
          {/* [M4] 마지막 페이지 감지: 응답 docs < PAGE_SIZE 이면 다음 페이지 없음 */}
          <Paginator
            page={page}
            total={docs.length < PAGE_SIZE ? (page * PAGE_SIZE + docs.length) : ((page + 1) * PAGE_SIZE + 1)}
            pageSize={PAGE_SIZE}
            onPrev={() => setPage((p) => Math.max(0, p - 1))}
            onNext={() => setPage((p) => p + 1)}
          />
        </div>
      )}
    </DataTabWrapper>
  );
}

function KnowledgeDocRow({
  doc,
  expanded,
  onToggle,
}: {
  doc: KnowledgeDocument;
  expanded: boolean;
  onToggle: () => void;
}) {
  const preview = doc.content.slice(0, 200);
  return (
    <div
      className="rounded-md border border-slate-800 bg-slate-950/40 overflow-hidden"
    >
      <button
        onClick={onToggle}
        className="w-full text-left px-3 py-2 hover:bg-slate-800/50 transition-colors"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="text-[12px] font-medium text-slate-200 truncate">{doc.title}</div>
            <div className="flex flex-wrap gap-1 mt-1">
              {doc.category && (
                <span className="text-[9px] font-mono px-1 py-0.5 rounded bg-violet-900/40 text-violet-300 border border-violet-700/40">
                  {doc.category}
                </span>
              )}
              {doc.tags.slice(0, 4).map((t) => (
                <span key={t} className="text-[9px] font-mono px-1 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                  {t}
                </span>
              ))}
            </div>
          </div>
          <span className="text-gray-600 text-xs shrink-0 mt-0.5">{expanded ? '▴' : '▾'}</span>
        </div>
        {!expanded && (
          <p className="text-[10px] text-gray-500 mt-1 line-clamp-2">
            {preview}{doc.content.length > 200 ? '…' : ''}
          </p>
        )}
      </button>
      {expanded && (
        <div className="px-3 pb-3 border-t border-slate-800/60 pt-2">
          <StyledMarkdown variant="comment">{doc.content}</StyledMarkdown>
        </div>
      )}
    </div>
  );
}

// ─── 4/5. result / markdown-viewer — warehouse entries ───────────────────

type WarehouseRenderMode = 'pre' | 'markdown';

function WarehouseDataTab({
  nodeId,
  renderMode,
  onWarehouseTotalFetched,
}: {
  nodeId: string;
  renderMode: WarehouseRenderMode;
  onWarehouseTotalFetched?: (nodeId: string, total: number) => void;
}) {
  const [items, setItems] = useState<WarehouseInstanceEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    factoryApi
      .getWarehouse(nodeId, { limit: PAGE_SIZE, skip: page * PAGE_SIZE })
      .then((res) => {
        if (cancelled) return;
        setItems(res.items as unknown as WarehouseInstanceEntry[]);
        setTotal(res.total);
        // [P-6] 첫 응답 도착 시 total 을 드로어 캐시에 저장 (정보 탭 limit=1 fetch 생략용)
        onWarehouseTotalFetched?.(nodeId, res.total);
      })
      .catch((e) => {
        if (cancelled || (e as DOMException)?.name === 'AbortError') return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [nodeId, page, retryToken]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <DataTabWrapper>
      <RefreshHeader
        title={`창고 Records${total > 0 ? ` (${total}개)` : ''}`}
        onRefresh={() => { setPage(0); setRetryToken((t) => t + 1); }}
      />
      {loading ? (
        <DataLoading />
      ) : error ? (
        <DataError message={`창고 조회 실패: ${error}`} onRetry={() => setRetryToken((t) => t + 1)} />
      ) : items.length === 0 ? (
        <DataEmpty message="적재된 데이터가 없습니다. 워크플로우를 실행하면 데이터가 생성됩니다." />
      ) : (
        <>
          <WarehouseEntryList items={items} renderMode={renderMode} />
          <Paginator
            page={page}
            total={total}
            pageSize={PAGE_SIZE}
            onPrev={() => setPage((p) => Math.max(0, p - 1))}
            onNext={() => setPage((p) => p + 1)}
          />
        </>
      )}
    </DataTabWrapper>
  );
}

// ─── Warehouse entry list (mapper/result/markdown-viewer 공유) ────────────

function WarehouseEntryList({
  items,
  renderMode,
}: {
  items: WarehouseInstanceEntry[];
  renderMode: WarehouseRenderMode;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <div className="space-y-1.5">
      {items.map((item) => (
        <WarehouseEntryRow
          key={item.id}
          item={item}
          renderMode={renderMode}
          expanded={expandedId === item.id}
          onToggle={() => setExpandedId((id) => (id === item.id ? null : item.id))}
        />
      ))}
    </div>
  );
}

function WarehouseEntryRow({
  item,
  renderMode,
  expanded,
  onToggle,
}: {
  item: WarehouseInstanceEntry;
  renderMode: WarehouseRenderMode;
  expanded: boolean;
  onToggle: () => void;
}) {
  const body = extractEntryBody(item.data);
  const dateStr = item.createdAt ? new Date(item.createdAt).toLocaleString('ko-KR') : '—';
  const summaryText =
    body.kind === 'text'
      ? body.content.slice(0, 80)
      : `{JSON ${body.content.length}자}`;

  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/40 overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full text-left px-3 py-2 hover:bg-slate-800/50 transition-colors"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1 space-y-0.5">
            <div className="text-[10px] font-mono text-gray-500 flex items-center gap-2 flex-wrap">
              <span>{dateStr}</span>
            </div>
            {!expanded && (
              <div className="text-[11px] text-gray-400 truncate">
                {summaryText || <span className="italic text-gray-600">(내용 없음)</span>}
              </div>
            )}
          </div>
          <span className="text-gray-600 text-xs shrink-0">{expanded ? '▴' : '▾'}</span>
        </div>
      </button>
      {expanded && (
        <div className="border-t border-slate-800/60">
          <WarehouseBodyRender body={body} renderMode={renderMode} />
          <div className="px-3 pb-2 pt-1 border-t border-slate-800/40">
            <div className="text-[9px] font-semibold text-gray-600 uppercase tracking-wider mb-1">
              Raw JSON
            </div>
            <div className="bg-slate-900 rounded p-2">
              <JsonTreeView data={item.data} maxDepth={1} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function WarehouseBodyRender({
  body,
  renderMode,
}: {
  body: ReturnType<typeof extractEntryBody>;
  renderMode: WarehouseRenderMode;
}) {
  if (!body.content) {
    return <p className="px-3 py-2 text-xs text-gray-600 italic">본문 없음</p>;
  }

  if (renderMode === 'pre') {
    if (body.kind === 'json') {
      return (
        <pre className="px-3 py-2 text-[11px] font-mono text-slate-300 whitespace-pre-wrap break-words max-h-64 overflow-auto bg-slate-900/60">{`\`\`\`json\n${body.content}\n\`\`\``}</pre>
      );
    }
    return (
      <pre className="px-3 py-2 text-[11px] font-mono text-slate-300 whitespace-pre-wrap break-words max-h-64 overflow-auto bg-slate-900/60">
        {body.content}
      </pre>
    );
  }

  // markdown 렌더
  const mdContent =
    body.kind === 'json' ? `\`\`\`json\n${body.content}\n\`\`\`` : body.content;

  return (
    <div className="px-3 py-2 max-h-72 overflow-auto">
      <StyledMarkdown variant="comment">{mdContent}</StyledMarkdown>
    </div>
  );
}

// ─── 6/7. instance-db-insert / instance-db-lookup (R-9) ─────────────────

interface InstanceDbDataTabProps {
  config: Record<string, unknown>;
  workflow: Workflow;
  instance?: WorkflowExecution & { instanceId?: string; id?: string };
  pageContext: 'workflow' | 'instance';
  isLookup: boolean;
}

function InstanceDbDataTab({
  config,
  workflow,
  instance,
  pageContext,
  isLookup,
}: InstanceDbDataTabProps) {
  const instanceDbId = (config.instanceDbId as string | undefined) ?? '';

  const [records, setRecords] = useState<InstanceDBRecord[]>([]);
  const [filteredTotal, setFilteredTotal] = useState<number | null>(null);
  const [globalTotal, setGlobalTotal] = useState<number | null>(null);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // R-9: 컨텍스트별 필터 파라미터
  const filterParams =
    pageContext === 'workflow'
      ? { sourceWorkflowId: workflow.id }
      : pageContext === 'instance' && instance
      ? { sourceExecutionId: instance.id ?? instance.instanceId }
      : {};

  // [M3] globalTotal: instanceDbId 변경 시에만 1회 fetch (page/필터 변동 시 재호출 없음)
  useEffect(() => {
    if (!instanceDbId) return;
    let cancelled = false;
    instanceDbApi
      .listRecords(instanceDbId, { limit: 1, offset: 0 })
      .then((res) => {
        if (cancelled) return;
        setGlobalTotal(res.total);
      })
      .catch(() => {
        // globalTotal 실패해도 메인 fetch 에 영향 없음
      });
    return () => {
      cancelled = true;
    };
  }, [instanceDbId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!instanceDbId) return;
    let cancelled = false;
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    instanceDbApi.listRecords(instanceDbId, {
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
      ...filterParams,
    })
      .then((filtered) => {
        if (cancelled) return;
        setRecords(filtered.items);
        setFilteredTotal(filtered.total);
      })
      .catch((e) => {
        if (cancelled || (e as DOMException)?.name === 'AbortError') return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [instanceDbId, page, retryToken, pageContext, workflow.id, instance?.id, instance?.instanceId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!instanceDbId) {
    return (
      <DataTabWrapper>
        <DataEmpty message="instanceDbId 가 설정되어 있지 않습니다." />
      </DataTabWrapper>
    );
  }

  return (
    <DataTabWrapper>
      {isLookup && (
        <div className="rounded bg-amber-900/20 border border-amber-700/30 px-3 py-1.5 text-[11px] text-amber-300 mb-1">
          이 노드는 적재하지 않고 조회만 합니다 — 아래 records 는 다른 노드가 적재한 데이터입니다.
        </div>
      )}
      <RefreshHeader
        title={
          filteredTotal !== null && globalTotal !== null
            ? `Records — 필터: ${filteredTotal}개 / 전체: ${globalTotal}개`
            : 'Records'
        }
        onRefresh={() => { setPage(0); setRetryToken((t) => t + 1); }}
      />
      <div className="text-[10px] text-gray-600 italic -mt-2 mb-1">
        {pageContext === 'workflow'
          ? `이 워크플로우(sourceWorkflowId)로 필터링 중`
          : `이 실행(sourceExecutionId)으로 필터링 중`}
      </div>
      {loading ? (
        <DataLoading />
      ) : error ? (
        <DataError message={`Records 조회 실패: ${error}`} onRetry={() => setRetryToken((t) => t + 1)} />
      ) : records.length === 0 ? (
        <DataEmpty
          message={
            isLookup
              ? '이 노드 컨텍스트로 적재된 records 가 없습니다 (lookup 노드는 직접 적재하지 않습니다).'
              : '이 컨텍스트로 적재된 records 가 없습니다. 워크플로우를 실행하면 데이터가 생성됩니다.'
          }
        />
      ) : (
        <>
          <div className="space-y-1.5">
            {records.map((record) => (
              <InstanceDbRecordRow
                key={record.id}
                record={record}
                expanded={expandedId === record.id}
                onToggle={() => setExpandedId((id) => (id === record.id ? null : record.id))}
              />
            ))}
          </div>
          {filteredTotal !== null && (
            <Paginator
              page={page}
              total={filteredTotal}
              pageSize={PAGE_SIZE}
              onPrev={() => setPage((p) => Math.max(0, p - 1))}
              onNext={() => setPage((p) => p + 1)}
            />
          )}
        </>
      )}
    </DataTabWrapper>
  );
}

function InstanceDbRecordRow({
  record,
  expanded,
  onToggle,
}: {
  record: InstanceDBRecord;
  expanded: boolean;
  onToggle: () => void;
}) {
  const dateStr = record.createdAt ? new Date(record.createdAt).toLocaleString('ko-KR') : '—';
  const dataKeys = Object.keys(record.data ?? {});
  const dataSummary = `{${dataKeys.length}개 키}`;

  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/40 overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full text-left px-3 py-2 hover:bg-slate-800/50 transition-colors"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1 space-y-0.5">
            <div className="text-[10px] font-mono text-gray-500 flex items-center gap-2 flex-wrap">
              <span className="text-gray-600 truncate max-w-[100px]">{record.id.slice(0, 8)}…</span>
              <span>{dateStr}</span>
            </div>
            {!expanded && (
              <div className="text-[11px] text-gray-400">{dataSummary}</div>
            )}
          </div>
          <span className="text-gray-600 text-xs shrink-0">{expanded ? '▴' : '▾'}</span>
        </div>
      </button>
      {expanded && (
        <div className="px-3 pb-3 border-t border-slate-800/60 pt-2 space-y-2">
          {record.sourceWorkflowId && (
            <div className="text-[10px] font-mono">
              <span className="text-gray-500">sourceWorkflowId: </span>
              <span className="text-gray-400">{record.sourceWorkflowId.slice(0, 16)}…</span>
            </div>
          )}
          {record.sourceExecutionId && (
            <div className="text-[10px] font-mono">
              <span className="text-gray-500">sourceExecutionId: </span>
              <span className="text-gray-400">{record.sourceExecutionId.slice(0, 16)}…</span>
            </div>
          )}
          <div>
            <div className="text-[9px] font-semibold text-gray-600 uppercase tracking-wider mb-1">
              data
            </div>
            <div className="bg-slate-900 rounded p-2">
              <JsonTreeView data={record.data} maxDepth={1} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default NodeDataTab;
