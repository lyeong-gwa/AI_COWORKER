/**
 * NodeInfoTab — 노드 검사 드로어의 "정보" 탭.
 *
 * 설계: `docs/node-inspector-plan.md` v2.1 §4 (Phase 1b) + §5 (Phase 1c §6 추가 정보)
 *
 * 섹션 구성:
 *   1. Header (이모지 + label + defType 배지 + category 배지 + 노드 ID)
 *   2. Purpose (catalog.purpose)
 *   3. 현재 워크플로우 Config — 인스턴스 표기 (camelCase)
 *   4. Inputs / Outputs — 카탈로그 표기 그대로
 *   5. Catalog Config 스펙 — 카탈로그 표기 그대로 (필드별 상이)
 *   6. 노드별 추가 정보 — Phase 1c (api-call, api-start, ai-api-router, ai-custom, instance-db-insert, instance-db-lookup, knowledge, mapper, sorter, result, markdown-viewer)
 *   7. UseCases
 *   8. ConnectsWellWith
 */
import { useEffect, useRef, useState } from 'react';
import type { Node } from '@xyflow/react';
import type { Workflow, ApiDefinition, AINode, InstanceDB } from '../../types';
import {
  apiDefinitionApi,
  nodeApi,
  instanceDbApi,
  factoryApi,
  knowledgeApi,
  workflowApi,
  type NodeCatalogEntry,
  type NodeCatalogIOField,
  type NodeCatalogConfigField,
} from '../../services/api';
import { JsonTreeView } from '../common/JsonTreeView';
import { nodeRegistry } from '../../nodes';
import { useToast } from '../common/Toast';

// 카테고리 배지 색상 매핑
const CATEGORY_COLORS: Record<string, string> = {
  starter: 'bg-amber-900/40 text-amber-300 border-amber-700/40',
  ai: 'bg-blue-900/40 text-blue-300 border-blue-700/40',
  logic: 'bg-violet-900/40 text-violet-300 border-violet-700/40',
  action: 'bg-cyan-900/40 text-cyan-300 border-cyan-700/40',
  output: 'bg-emerald-900/40 text-emerald-300 border-emerald-700/40',
};

const LEGACY_DEF_TYPE_MAP: Record<string, string> = { form: 'form-start' };

interface NodeInfoTabProps {
  node: Node<any>;
  workflow: Workflow;
  catalog: NodeCatalogEntry | null;
  /**
   * [P-6] 데이터 탭에서 캐시된 warehouse total 맵.
   * MapperExtra / WarehouseCountExtra 가 이 캐시를 먼저 확인해 limit=1 fetch 를 생략한다.
   */
  warehouseTotalCache?: ReadonlyMap<string, number>;
  /**
   * 인라인 노드 재료 편집 활성화 여부.
   * WorkflowViewerPage 에서 true, InstanceDetailPage 에서 false (기본).
   */
  editable?: boolean;
  /**
   * 재료 변경 후 워크플로우를 새로고침하는 콜백.
   */
  onWorkflowUpdated?: (updated: Workflow) => void;
}

export function NodeInfoTab({ node, workflow, catalog, warehouseTotalCache, editable = false, onWorkflowUpdated }: NodeInfoTabProps) {
  const inst = workflow.nodes.find((n) => n.id === node.id);
  const rawDefType = inst?.definitionType ?? (node.data?.definitionType as string | undefined) ?? '';
  const defType = LEGACY_DEF_TYPE_MAP[rawDefType] ?? rawDefType;
  const instanceName = inst?.name ?? (node.data?.instanceName as string | undefined) ?? node.id;
  const config = (inst?.config ?? {}) as Record<string, unknown>;
  const inputMapping = inst?.inputMapping ?? {};

  // Header 표기에 사용할 아이콘 (registry palette 의 icon)
  const palette = nodeRegistry.get(defType)?.palette;
  const icon = palette?.icon ?? '◆';

  return (
    <div className="px-4 py-4 space-y-5 text-sm text-gray-200">
      {/* 섹션 1 — Header */}
      <header className="flex items-start gap-3 pb-3 border-b border-slate-800">
        <div className="w-10 h-10 rounded-lg bg-slate-800 flex items-center justify-center text-xl shrink-0">
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-base font-semibold text-white truncate">{instanceName}</div>
          <div className="flex flex-wrap items-center gap-1.5 mt-1">
            {defType && (
              <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-300 border border-slate-700">
                {defType}
              </span>
            )}
            {catalog?.category && (
              <span
                className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-mono border ${
                  CATEGORY_COLORS[catalog.category] ?? 'bg-slate-800 text-slate-300 border-slate-700'
                }`}
              >
                {catalog.category}
              </span>
            )}
          </div>
          <div className="text-[10px] font-mono text-gray-500 mt-1 truncate">{node.id}</div>
        </div>
      </header>

      {/* inst 가 없으면 (workflow 에 없는 노드) §1 만 표시 */}
      {!inst && (
        <SectionTitle>주의</SectionTitle>
      )}
      {!inst && (
        <p className="text-xs text-rose-300/80">
          이 노드는 현재 워크플로우 정의에서 찾을 수 없습니다 (id: {node.id}).
        </p>
      )}

      {inst && (
        <>
          {/* 섹션 2 — Purpose */}
          <Section title="용도 (Purpose)">
            {catalog ? (
              <p className="text-[13px] text-slate-300 leading-relaxed">
                {catalog.purpose || <span className="text-gray-500 italic">설명 없음</span>}
              </p>
            ) : (
              <p className="text-xs text-gray-500 italic">카탈로그를 불러오는 중입니다…</p>
            )}
          </Section>

          {/* 섹션 3 — 현재 워크플로우 Config (인스턴스 표기) */}
          <Section
            title="현재 노드 인스턴스 Config"
            subtitle="인스턴스 표기 그대로"
          >
            <ConfigTable config={config} catalog={catalog} />
            {Object.keys(inputMapping).length > 0 && (
              <div className="mt-3">
                <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1">
                  Input Mapping
                </div>
                <table className="w-full text-[11px] font-mono">
                  <tbody>
                    {Object.entries(inputMapping).map(([k, v]) => (
                      <tr key={k} className="border-b border-slate-800/60 last:border-0">
                        <td className="py-1 pr-2 text-gray-400 align-top whitespace-nowrap">
                          {k}
                        </td>
                        <td className="py-1 text-gray-500">←</td>
                        <td className="py-1 pl-2 text-emerald-300 break-all">{v}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          {/* catalog 가 있을 때만 §4-§8 표시 */}
          {catalog && (
            <>
              {/* 섹션 4 — Inputs / Outputs */}
              <Section
                title="노드 카탈로그 Inputs/Outputs"
                subtitle="카탈로그가 정의한 표기 그대로"
              >
                {catalog.producesArray && (
                  <p className="text-[10px] text-amber-300/80 italic mb-2">
                    이 노드는 배열을 언팩합니다 (producesArray).
                  </p>
                )}
                <div className="space-y-3">
                  <IOFieldTable label="Inputs" fields={catalog.inputs} />
                  <IOFieldTable label="Outputs" fields={catalog.outputs} />
                </div>
              </Section>

              {/* 섹션 5 — Catalog Config 스펙 */}
              <Section
                title="노드 카탈로그 Config 스펙"
                subtitle="카탈로그가 정의한 표기 그대로 (필드별 상이)"
              >
                <ConfigSpecTable fields={catalog.config} />
              </Section>

              {/* 섹션 6 — 노드별 추가 정보 (Phase 1c) */}
              <NodeExtraInfoSection
                defType={defType}
                config={config}
                workflow={workflow}
                nodeInstanceId={node.id}
                catalog={catalog}
                warehouseTotalCache={warehouseTotalCache}
                editable={editable}
                onWorkflowUpdated={onWorkflowUpdated}
              />

              {/* 섹션 7 — UseCases */}
              {catalog.useCases.length > 0 && (
                <Section title="Use Cases">
                  <ul className="list-disc list-outside pl-5 space-y-1 text-[12px] text-slate-300">
                    {catalog.useCases.map((u, i) => (
                      <li key={i}>{u}</li>
                    ))}
                  </ul>
                </Section>
              )}

              {/* 섹션 8 — ConnectsWellWith */}
              {catalog.connectsWellWith.length > 0 && (
                <Section title="Connects Well With">
                  <div className="flex flex-wrap gap-1.5">
                    {catalog.connectsWellWith.map((dt) => (
                      <span
                        key={dt}
                        className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-300 border border-slate-700"
                      >
                        {dt}
                      </span>
                    ))}
                  </div>
                </Section>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

// ─── Generic helpers ──────────────────────────────────────────────────────

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
      {children}
    </div>
  );
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-2">
      <div>
        <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">{title}</div>
        {subtitle && (
          <div className="text-[10px] text-gray-600 italic mt-0.5">{subtitle}</div>
        )}
      </div>
      <div>{children}</div>
    </section>
  );
}

// ─── Config table (instance) ─────────────────────────────────────────────

function ConfigTable({
  config,
  catalog,
}: {
  config: Record<string, unknown>;
  catalog: NodeCatalogEntry | null;
}) {
  const keys = Object.keys(config);
  if (keys.length === 0) {
    return <p className="text-xs text-gray-500 italic">config 없음</p>;
  }
  const requiredKeys = new Set(
    (catalog?.config ?? []).filter((c) => c.required).map((c) => c.name),
  );
  const documentedKeys = new Set((catalog?.config ?? []).map((c) => c.name));

  return (
    <table className="w-full text-[11px] font-mono">
      <tbody>
        {keys.map((k) => {
          const v = config[k];
          const isObject = v !== null && typeof v === 'object';
          const required = requiredKeys.has(k);
          const empty =
            v === null ||
            v === undefined ||
            v === '' ||
            (Array.isArray(v) && v.length === 0);
          const undocumented = catalog && !documentedKeys.has(k);

          return (
            <tr key={k} className="border-b border-slate-800/60 last:border-0 align-top">
              <td className="py-1.5 pr-3 text-gray-400 whitespace-nowrap">
                <div className="flex items-center gap-1">
                  <span>{k}</span>
                  {required && empty && (
                    <span title="필수 필드 누락" className="text-amber-400">
                      ⚠
                    </span>
                  )}
                  {undocumented && (
                    <span className="text-[9px] text-gray-600 italic">(undocumented)</span>
                  )}
                </div>
              </td>
              <td className="py-1.5 text-gray-200 break-all">
                {isObject ? (
                  <div className="bg-slate-950/40 border border-slate-800 rounded px-2 py-1">
                    <JsonTreeView data={v} maxDepth={1} />
                  </div>
                ) : v === null || v === undefined ? (
                  <span className="text-gray-500 italic">null</span>
                ) : v === '' ? (
                  <span className="text-gray-500 italic">""</span>
                ) : typeof v === 'string' ? (
                  <span className="text-green-400">"{String(v)}"</span>
                ) : typeof v === 'number' ? (
                  <span className="text-yellow-400">{String(v)}</span>
                ) : typeof v === 'boolean' ? (
                  <span className="text-blue-400">{String(v)}</span>
                ) : (
                  String(v)
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// ─── IO field table ──────────────────────────────────────────────────────

function IOFieldTable({ label, fields }: { label: string; fields: NodeCatalogIOField[] }) {
  return (
    <div>
      <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1">{label}</div>
      {fields.length === 0 ? (
        <p className="text-xs text-gray-600 italic">없음</p>
      ) : (
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-[9px] text-gray-500 uppercase tracking-wider border-b border-slate-800">
              <th className="text-left py-1 pr-2 font-medium">name</th>
              <th className="text-left py-1 pr-2 font-medium">type</th>
              <th className="text-left py-1 pr-2 font-medium">req</th>
              <th className="text-left py-1 font-medium">description</th>
            </tr>
          </thead>
          <tbody>
            {fields.map((f) => (
              <tr key={f.name} className="border-b border-slate-800/60 last:border-0 align-top">
                <td className="py-1 pr-2 font-mono text-emerald-300 whitespace-nowrap">{f.name}</td>
                <td className="py-1 pr-2 font-mono text-sky-300 whitespace-nowrap">{f.type}</td>
                <td className="py-1 pr-2 text-center">
                  {f.required ? <span className="text-amber-400">●</span> : <span className="text-gray-700">○</span>}
                </td>
                <td className="py-1 text-gray-400">{f.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ─── Catalog config spec table ───────────────────────────────────────────

function ConfigSpecTable({ fields }: { fields: NodeCatalogConfigField[] }) {
  if (fields.length === 0) {
    return <p className="text-xs text-gray-600 italic">없음</p>;
  }
  return (
    <table className="w-full text-[11px]">
      <thead>
        <tr className="text-[9px] text-gray-500 uppercase tracking-wider border-b border-slate-800">
          <th className="text-left py-1 pr-2 font-medium">name</th>
          <th className="text-left py-1 pr-2 font-medium">type</th>
          <th className="text-left py-1 pr-2 font-medium">req</th>
          <th className="text-left py-1 pr-2 font-medium">default</th>
          <th className="text-left py-1 font-medium">description</th>
        </tr>
      </thead>
      <tbody>
        {fields.map((f) => (
          <tr key={f.name} className="border-b border-slate-800/60 last:border-0 align-top">
            <td className="py-1 pr-2 font-mono text-amber-300 whitespace-nowrap">{f.name}</td>
            <td className="py-1 pr-2 font-mono text-sky-300 whitespace-nowrap">{f.type}</td>
            <td className="py-1 pr-2 text-center">
              {f.required ? <span className="text-amber-400">●</span> : <span className="text-gray-700">○</span>}
            </td>
            <td className="py-1 pr-2 font-mono text-gray-400 break-all max-w-[120px]">
              {f.default === undefined ? (
                <span className="text-gray-700 italic">—</span>
              ) : typeof f.default === 'object' ? (
                JSON.stringify(f.default)
              ) : (
                String(f.default)
              )}
            </td>
            <td className="py-1 text-gray-400">{f.description}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ─── §6 Material Edit Dropdown (editable=true 전용) ─────────────────────

interface MaterialEditDropdownProps {
  /** 현재 저장된 ID (config 에서 읽은 값) */
  currentId: string;
  /** 드롭다운에서 선택 중인 ID */
  selectedId: string;
  onSelect: (id: string) => void;
  saving: boolean;
  onApply: () => void;
  listLoading: boolean;
  /** 드롭다운 옵션 목록 */
  options: Array<{ id: string; label: string; sub?: string }>;
  /** 현재 값의 표시 레이블 (목록에 없을 때 폴백) */
  currentLabel: string;
}

function MaterialEditDropdown({
  currentId,
  selectedId,
  onSelect,
  saving,
  onApply,
  listLoading,
  options,
  currentLabel,
}: MaterialEditDropdownProps) {
  // 현재 값이 목록에 없으면 추가 (현재 값 항상 표시)
  const hasCurrentInOptions = options.some((o) => o.id === currentId);
  const augmentedOptions = hasCurrentInOptions || !currentId
    ? options
    : [{ id: currentId, label: currentLabel, sub: '(현재 값)' }, ...options];

  const isDirty = selectedId !== currentId;

  return (
    <div className="mb-3 rounded-md border border-sky-800/50 bg-sky-950/20 p-3 space-y-2.5">
      <div className="text-[10px] font-semibold text-sky-300 uppercase tracking-wider">
        재료 변경
      </div>
      <div className="flex gap-2 items-start">
        <div className="flex-1 min-w-0">
          {listLoading ? (
            <div className="text-[11px] text-slate-500 italic">목록 불러오는 중…</div>
          ) : (
            <select
              value={selectedId}
              onChange={(e) => onSelect(e.target.value)}
              disabled={saving}
              className="w-full px-2 py-1.5 rounded bg-slate-900 border border-slate-700 text-[11px] font-mono text-slate-200 focus:outline-none focus:border-sky-600 disabled:opacity-50"
            >
              {augmentedOptions.length === 0 && (
                <option value="">등록된 재료가 없습니다</option>
              )}
              {augmentedOptions.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}{o.sub ? ` — ${o.sub}` : ''}
                </option>
              ))}
            </select>
          )}
        </div>
        <button
          onClick={onApply}
          disabled={saving || !isDirty || listLoading}
          className="flex-shrink-0 px-3 py-1.5 rounded bg-sky-700 hover:bg-sky-600 disabled:bg-slate-800 disabled:text-slate-600 text-white text-[11px] font-medium transition-colors inline-flex items-center gap-1"
        >
          {saving ? (
            <>
              <span className="w-3 h-3 border border-white/40 border-t-white rounded-full animate-spin inline-block" />
              저장 중
            </>
          ) : (
            '변경 적용'
          )}
        </button>
      </div>
      <p className="text-[10px] text-sky-400/60 italic">
        변경 시 자동으로 해당 명세를 재동결(스냅샷)합니다.
      </p>
    </div>
  );
}

// ─── §6 Extra info — Phase 1c ────────────────────────────────────────────

interface ExtraInfoProps {
  defType: string;
  config: Record<string, unknown>;
  workflow: Workflow;
  nodeInstanceId: string;
  catalog: NodeCatalogEntry;
  /** [P-6] 데이터 탭 warehouse fetch 결과 캐시 — 있으면 limit=1 추가 fetch 생략 */
  warehouseTotalCache?: ReadonlyMap<string, number>;
  /** 인라인 재료 편집 활성화 여부 */
  editable?: boolean;
  /** 재료 변경 PATCH 성공 후 워크플로우 갱신 콜백 */
  onWorkflowUpdated?: (updated: Workflow) => void;
}

function NodeExtraInfoSection(props: ExtraInfoProps) {
  const { defType } = props;

  // 노드별 분기
  switch (defType) {
    case 'api-call':
    case 'api-start':
      return <ApiDefinitionExtra {...props} />;
    case 'ai-api-router':
      return <AiApiRouterExtra {...props} />;
    case 'ai-custom':
      return <AiCustomExtra {...props} />;
    case 'instance-db-insert':
    case 'instance-db-lookup':
      return <InstanceDbExtra {...props} />;
    case 'knowledge':
      return <KnowledgeExtra {...props} />;
    case 'mapper':
      return <MapperExtra {...props} />;
    case 'sorter':
      return <SorterExtra {...props} />;
    case 'result':
    case 'markdown-viewer':
      return <WarehouseCountExtra {...props} />;
    case 'form-start':
    case 'unpacker':
    default:
      return null;
  }
}

// ─── §6 Material Edit Hook ────────────────────────────────────────────────────

/**
 * 재료 변경 PATCH 를 처리하는 로컬 훅.
 * refKey: 변경할 config 키 (e.g. 'apiDefinitionId')
 * extraKeys: config 외에 노드 최상위에도 기록할 키 (e.g. 'aiNodeId')
 */
function useMaterialEdit(
  workflow: Workflow,
  nodeInstanceId: string,
  refKey: string,
  currentValue: string,
  extraTopLevelKeys: string[] = [],
  onWorkflowUpdated?: (updated: Workflow) => void,
) {
  const { toast } = useToast();
  const [selectedId, setSelectedId] = useState(currentValue);
  const [saving, setSaving] = useState(false);

  // currentValue が変わったとき (e.g. 親が rerender) に同期
  const prevValueRef = useRef(currentValue);
  if (prevValueRef.current !== currentValue) {
    prevValueRef.current = currentValue;
    setSelectedId(currentValue);
  }

  const handleApply = async () => {
    if (selectedId === currentValue) return;
    setSaving(true);
    try {
      // deep-copy nodes, update the target node's config ref key
      const updatedNodes = workflow.nodes.map((n) => {
        if (n.id !== nodeInstanceId) return n;
        const newConfig = { ...(n.config ?? {}), [refKey]: selectedId };
        const base: typeof n = { ...n, config: newConfig };
        // ai-custom: also mirror to top-level aiNodeId if requested
        for (const topKey of extraTopLevelKeys) {
          (base as any)[topKey] = selectedId;
        }
        return base;
      });

      const updated = await workflowApi.update(workflow.id, {
        nodes: updatedNodes as any,
        connections: workflow.connections as any,
      });

      toast.success('재료가 변경되었습니다. 스냅샷이 자동 갱신됩니다.');
      onWorkflowUpdated?.(updated);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(`변경 실패: ${msg}`);
    } finally {
      setSaving(false);
    }
  };

  return { selectedId, setSelectedId, saving, handleApply };
}

// ─── §6 Generic loading/error ────────────────────────────────────────────

function ExtraLoading() {
  return <p className="text-xs text-gray-500 italic">불러오는 중…</p>;
}

function ExtraError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-md border border-rose-700/40 bg-rose-950/30 px-3 py-2">
      <p className="text-xs text-rose-300 mb-1.5">{message}</p>
      <button
        onClick={onRetry}
        className="text-[10px] font-mono text-rose-400 hover:text-rose-200 underline"
      >
        재시도 ↻
      </button>
    </div>
  );
}

function ExtraEmpty({ message }: { message: string }) {
  return <p className="text-xs text-gray-500 italic">{message}</p>;
}

// ─── §6 api-call / api-start ─────────────────────────────────────────────

function ApiDefinitionExtra({ config, workflow, nodeInstanceId, editable, onWorkflowUpdated }: ExtraInfoProps) {
  const apiId = (config.apiDefinitionId as string | undefined) ?? '';
  const [data, setData] = useState<ApiDefinition | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  // 드롭다운용 전체 목록
  const [allDefs, setAllDefs] = useState<ApiDefinition[]>([]);
  const [listLoading, setListLoading] = useState(false);

  const { selectedId, setSelectedId, saving, handleApply } = useMaterialEdit(
    workflow, nodeInstanceId, 'apiDefinitionId', apiId, [], onWorkflowUpdated,
  );

  useEffect(() => {
    if (!editable) return;
    setListLoading(true);
    apiDefinitionApi.list().then(setAllDefs).catch(() => setAllDefs([])).finally(() => setListLoading(false));
  }, [editable]);

  useEffect(() => {
    if (!apiId) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }
    const controller = new AbortController();
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiDefinitionApi
      .get(apiId)
      .then((d) => {
        if (cancelled) return;
        setData(d);
      })
      .catch((e) => {
        if (cancelled) return;
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
  }, [apiId, retryToken]);

  return (
    <Section title="추가 정보 — API 명세">
      {editable && (
        <MaterialEditDropdown
          currentId={apiId}
          selectedId={selectedId}
          onSelect={setSelectedId}
          saving={saving}
          onApply={handleApply}
          listLoading={listLoading}
          options={allDefs.map((d) => ({
            id: d.id,
            label: `[${d.method}] ${d.name}`,
            sub: d.urlTemplate,
          }))}
          currentLabel={data ? `[${data.method}] ${data.name}` : apiId}
        />
      )}
      {!apiId ? (
        <ExtraEmpty message="API 명세 미연결 — config.apiDefinitionId 가 비어있습니다. CLI 로 설정하세요." />
      ) : loading ? (
        <ExtraLoading />
      ) : error ? (
        <ExtraError message={`API 명세 조회 실패: ${error}`} onRetry={() => setRetryToken((t) => t + 1)} />
      ) : data ? (
        <ApiDefinitionCard def={data} />
      ) : (
        <ExtraEmpty message="API 명세를 찾을 수 없습니다." />
      )}
    </Section>
  );
}

function ApiDefinitionCard({ def }: { def: ApiDefinition }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/40 p-3 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono bg-cyan-900/40 text-cyan-300 border border-cyan-700/40">
          {def.method}
        </span>
        <span className="text-[12px] font-semibold text-slate-100 truncate">{def.name}</span>
      </div>
      <div className="text-[11px] font-mono text-emerald-300 break-all">{def.urlTemplate}</div>
      {def.description && (
        <p className="text-[11px] text-slate-400">{def.description}</p>
      )}
      {def.parameters.length > 0 && (
        <div>
          <div className="text-[9px] font-semibold text-gray-500 uppercase tracking-wider mt-1 mb-1">
            Parameters
          </div>
          <table className="w-full text-[10px] font-mono">
            <tbody>
              {def.parameters.map((p) => (
                <tr key={p.name} className="border-b border-slate-800/60 last:border-0">
                  <td className="py-0.5 pr-1.5 text-amber-300">{p.name}</td>
                  <td className="py-0.5 pr-1.5 text-sky-300">{p.type}</td>
                  <td className="py-0.5 pr-1.5 text-gray-500">{p.in}</td>
                  <td className="py-0.5 text-center">
                    {p.required ? <span className="text-amber-400">●</span> : <span className="text-gray-700">○</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── §6 ai-api-router ────────────────────────────────────────────────────

function AiApiRouterExtra({ config }: ExtraInfoProps) {
  const apiIds = (config.apiIds as string[] | undefined) ?? [];
  const [data, setData] = useState<ApiDefinition[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        if (apiIds.length > 0 && apiIds.length <= 10) {
          // 10개 이하면 병렬 단건 조회
          const results = await Promise.all(apiIds.map((id) => apiDefinitionApi.get(id)));
          if (cancelled) return;
          setData(results);
        } else {
          // 10개 초과 또는 빈 배열 — list 1회 + 클라이언트 필터
          const list = await apiDefinitionApi.list();
          if (cancelled) return;
          if (apiIds.length === 0) {
            setData(list);
          } else {
            const set = new Set(apiIds);
            setData(list.filter((d) => set.has(d.id)));
          }
        }
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (cancelled) return;
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiIds.join(','), retryToken]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Section
      title="추가 정보 — 라우팅 후보 API"
      subtitle={
        apiIds.length === 0
          ? '전체 활성 API'
          : `${apiIds.length}개 후보`
      }
    >
      {loading ? (
        <ExtraLoading />
      ) : error ? (
        <ExtraError message={`API 목록 조회 실패: ${error}`} onRetry={() => setRetryToken((t) => t + 1)} />
      ) : !data || data.length === 0 ? (
        <ExtraEmpty message="해당하는 API 명세가 없습니다." />
      ) : (
        <div className="space-y-1.5">
          {data.slice(0, 20).map((d) => (
            <div
              key={d.id}
              className="flex items-center gap-2 px-2 py-1 rounded bg-slate-950/40 border border-slate-800"
            >
              <span className="inline-block px-1.5 py-0.5 rounded text-[9px] font-mono bg-cyan-900/40 text-cyan-300 border border-cyan-700/40 shrink-0">
                {d.method}
              </span>
              <span className="text-[11px] text-slate-200 truncate">{d.name}</span>
              <span className="text-[10px] font-mono text-emerald-300 truncate">{d.urlTemplate}</span>
            </div>
          ))}
          {data.length > 20 && (
            <p className="text-[10px] text-gray-500 italic">외 {data.length - 20}개</p>
          )}
        </div>
      )}
    </Section>
  );
}

// ─── §6 ai-custom ────────────────────────────────────────────────────────

function AiCustomExtra({ config, workflow, nodeInstanceId, editable, onWorkflowUpdated }: ExtraInfoProps) {
  // ai-custom uses ai_node_id in config; top-level aiNodeId may also be present
  const aiNodeId = (config.ai_node_id as string | undefined) ?? (config.aiNodeId as string | undefined) ?? '';
  const [data, setData] = useState<AINode | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const [systemPromptOpen, setSystemPromptOpen] = useState(false);
  const [userPromptOpen, setUserPromptOpen] = useState(false);

  // 드롭다운용 전체 목록
  const [allNodes, setAllNodes] = useState<AINode[]>([]);
  const [listLoading, setListLoading] = useState(false);

  const { selectedId, setSelectedId, saving, handleApply } = useMaterialEdit(
    workflow, nodeInstanceId, 'ai_node_id', aiNodeId, ['aiNodeId'], onWorkflowUpdated,
  );

  useEffect(() => {
    if (!editable) return;
    setListLoading(true);
    nodeApi.list().then(setAllNodes).catch(() => setAllNodes([])).finally(() => setListLoading(false));
  }, [editable]);

  useEffect(() => {
    if (!aiNodeId) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    nodeApi
      .get(aiNodeId)
      .then((d) => {
        if (cancelled) return;
        setData(d);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [aiNodeId, retryToken]);

  return (
    <Section title="추가 정보 — AI 노드">
      {editable && (
        <MaterialEditDropdown
          currentId={aiNodeId}
          selectedId={selectedId}
          onSelect={setSelectedId}
          saving={saving}
          onApply={handleApply}
          listLoading={listLoading}
          options={allNodes.map((n) => ({
            id: n.id,
            label: `${n.icon || ''} ${n.name}`.trim(),
            sub: n.description ?? '',
          }))}
          currentLabel={data ? `${data.icon || ''} ${data.name}`.trim() : aiNodeId}
        />
      )}
      {!aiNodeId ? (
        <ExtraEmpty message="ai_node_id 가 설정되어 있지 않습니다." />
      ) : loading ? (
        <ExtraLoading />
      ) : error ? (
        <ExtraError message={`AI 노드 조회 실패: ${error}`} onRetry={() => setRetryToken((t) => t + 1)} />
      ) : !data ? (
        <ExtraEmpty message="AI 노드를 찾을 수 없습니다." />
      ) : (
        <div className="rounded-md border border-slate-800 bg-slate-950/40 p-3 space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-lg">{data.icon || '🤖'}</span>
            <div className="min-w-0">
              <div className="text-[12px] font-semibold text-slate-100 truncate">{data.name}</div>
              {data.description && (
                <div className="text-[10px] text-slate-400 truncate">{data.description}</div>
              )}
            </div>
          </div>

          {/* LLM Config */}
          <div>
            <div className="text-[9px] font-semibold text-gray-500 uppercase tracking-wider mb-1">
              LLM Config
            </div>
            <table className="w-full text-[10px] font-mono">
              <tbody>
                {(['model', 'temperature', 'maxTokens'] as const).map((k) => (
                  <tr key={k} className="border-b border-slate-800/60 last:border-0">
                    <td className="py-0.5 pr-2 text-gray-500">{k}</td>
                    <td className="py-0.5 text-gray-200">
                      {data.llmConfig?.[k] === undefined ? (
                        <span className="text-gray-700 italic">—</span>
                      ) : (
                        String(data.llmConfig[k])
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* System prompt collapsed */}
          <div>
            <button
              onClick={() => setSystemPromptOpen((v) => !v)}
              className="w-full flex items-center justify-between px-2 py-1 rounded bg-slate-800/40 hover:bg-slate-800 text-left text-[10px] font-mono text-gray-400"
            >
              <span>System Prompt {data.systemPrompt ? `(${data.systemPrompt.length}자)` : '(없음)'}</span>
              <span>{systemPromptOpen ? '▴' : '▾'}</span>
            </button>
            {systemPromptOpen && (
              <pre className="mt-1.5 rounded bg-slate-950 border border-slate-800 px-2 py-1.5 text-[10px] text-slate-300 whitespace-pre-wrap break-words max-h-48 overflow-auto">
                {data.systemPrompt || <span className="text-gray-600 italic">(비어있음)</span>}
              </pre>
            )}
          </div>

          {/* User prompt template collapsed */}
          <div>
            <button
              onClick={() => setUserPromptOpen((v) => !v)}
              className="w-full flex items-center justify-between px-2 py-1 rounded bg-slate-800/40 hover:bg-slate-800 text-left text-[10px] font-mono text-gray-400"
            >
              <span>User Prompt Template {data.userPromptTemplate ? `(${data.userPromptTemplate.length}자)` : '(없음)'}</span>
              <span>{userPromptOpen ? '▴' : '▾'}</span>
            </button>
            {userPromptOpen && (
              <pre className="mt-1.5 rounded bg-slate-950 border border-slate-800 px-2 py-1.5 text-[10px] text-slate-300 whitespace-pre-wrap break-words max-h-48 overflow-auto">
                {data.userPromptTemplate || <span className="text-gray-600 italic">(비어있음)</span>}
              </pre>
            )}
          </div>

          {/* Schemas */}
          {data.inputSchema && Object.keys(data.inputSchema).length > 0 && (
            <div>
              <div className="text-[9px] font-semibold text-gray-500 uppercase tracking-wider mb-1">
                Input Schema
              </div>
              <div className="rounded bg-slate-950 border border-slate-800 px-2 py-1.5">
                <JsonTreeView data={data.inputSchema} maxDepth={1} />
              </div>
            </div>
          )}
          {data.outputSchema && Object.keys(data.outputSchema).length > 0 && (
            <div>
              <div className="text-[9px] font-semibold text-gray-500 uppercase tracking-wider mb-1">
                Output Schema
              </div>
              <div className="rounded bg-slate-950 border border-slate-800 px-2 py-1.5">
                <JsonTreeView data={data.outputSchema} maxDepth={1} />
              </div>
            </div>
          )}
        </div>
      )}
    </Section>
  );
}

// ─── §6 instance-db-insert / instance-db-lookup ──────────────────────────

function InstanceDbExtra({ config, workflow, nodeInstanceId, editable, onWorkflowUpdated }: ExtraInfoProps) {
  const instanceDbId = (config.instanceDbId as string | undefined) ?? '';
  const [data, setData] = useState<InstanceDB | null>(null);
  const [recordCount, setRecordCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  // 드롭다운용 전체 목록
  const [allDbs, setAllDbs] = useState<InstanceDB[]>([]);
  const [listLoading, setListLoading] = useState(false);

  const { selectedId, setSelectedId, saving, handleApply } = useMaterialEdit(
    workflow, nodeInstanceId, 'instanceDbId', instanceDbId, [], onWorkflowUpdated,
  );

  useEffect(() => {
    if (!editable) return;
    setListLoading(true);
    instanceDbApi.list().then(setAllDbs).catch(() => setAllDbs([])).finally(() => setListLoading(false));
  }, [editable]);

  useEffect(() => {
    if (!instanceDbId) {
      setData(null);
      setRecordCount(null);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const [meta, records] = await Promise.all([
          instanceDbApi.get(instanceDbId),
          instanceDbApi.listRecords(instanceDbId, { limit: 1 }).catch(() => null),
        ]);
        if (cancelled) return;
        setData(meta);
        setRecordCount(records?.total ?? null);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (cancelled) return;
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [instanceDbId, retryToken]);

  return (
    <Section title="추가 정보 — 인스턴스DB">
      {editable && (
        <MaterialEditDropdown
          currentId={instanceDbId}
          selectedId={selectedId}
          onSelect={setSelectedId}
          saving={saving}
          onApply={handleApply}
          listLoading={listLoading}
          options={allDbs.map((d) => ({
            id: d.id,
            label: d.name,
            sub: d.description ?? '',
          }))}
          currentLabel={data?.name ?? instanceDbId}
        />
      )}
      {!instanceDbId ? (
        <ExtraEmpty message="instanceDbId 가 설정되어 있지 않습니다." />
      ) : loading ? (
        <ExtraLoading />
      ) : error ? (
        <ExtraError message={`인스턴스DB 조회 실패: ${error}`} onRetry={() => setRetryToken((t) => t + 1)} />
      ) : !data ? (
        <ExtraEmpty message="인스턴스DB를 찾을 수 없습니다." />
      ) : (
        <div className="rounded-md border border-slate-800 bg-slate-950/40 p-3 space-y-2">
          <div className="flex items-baseline justify-between gap-2">
            <div className="text-[12px] font-semibold text-slate-100 truncate">{data.name}</div>
            {recordCount !== null && (
              <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-900/40 text-emerald-300 border border-emerald-700/40 shrink-0">
                records {recordCount}
              </span>
            )}
          </div>
          {data.description && (
            <p className="text-[11px] text-slate-400">{data.description}</p>
          )}
          {data.tags?.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {data.tags.map((t) => (
                <span
                  key={t}
                  className="inline-block px-1.5 py-0.5 rounded text-[9px] font-mono bg-slate-800 text-slate-400 border border-slate-700"
                >
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </Section>
  );
}

// ─── §6 knowledge ────────────────────────────────────────────────────────

function KnowledgeExtra({ config }: ExtraInfoProps) {
  const categories = (config.categories as string[] | undefined) ?? [];
  const tags = (config.tags as string[] | undefined) ?? [];
  const maxResults = config.maxResults as number | undefined;
  const searchField = config.searchField as string | undefined;
  const firstCategory = categories[0];

  const [count, setCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    knowledgeApi
      .list({ category: firstCategory, limit: 1 })
      .then((docs) => {
        if (cancelled) return;
        // 백엔드는 limit/skip 만 지원하고 total 메타가 없으므로 limit=1 로는 정확한 total 추출 불가.
        // 임시로 .length 만 표시 — Phase 2 에서 별도 count 메커니즘 검토.
        setCount(docs.length);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [firstCategory, retryToken]);

  return (
    <Section title="추가 정보 — 지식문서 검색 설정">
      <div className="rounded-md border border-slate-800 bg-slate-950/40 p-3 space-y-2 text-[11px] font-mono">
        {searchField && (
          <div>
            <span className="text-gray-500">searchField: </span>
            <span className="text-emerald-300">{searchField}</span>
          </div>
        )}
        {maxResults !== undefined && (
          <div>
            <span className="text-gray-500">maxResults: </span>
            <span className="text-yellow-400">{maxResults}</span>
          </div>
        )}
        {categories.length > 0 && (
          <div>
            <span className="text-gray-500">categories: </span>
            <div className="flex flex-wrap gap-1 mt-1">
              {categories.map((c) => (
                <span
                  key={c}
                  className="inline-block px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300 border border-slate-700"
                >
                  {c}
                </span>
              ))}
            </div>
          </div>
        )}
        {tags.length > 0 && (
          <div>
            <span className="text-gray-500">tags: </span>
            <div className="flex flex-wrap gap-1 mt-1">
              {tags.map((t) => (
                <span
                  key={t}
                  className="inline-block px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400 border border-slate-700"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        )}
        <div className="pt-2 border-t border-slate-800/60">
          <span className="text-gray-500">매칭 카테고리 문서 수: </span>
          {loading ? (
            <span className="text-gray-500 italic">로딩…</span>
          ) : error ? (
            <span className="text-rose-400">조회 실패</span>
          ) : count === null ? (
            <span className="text-gray-700">—</span>
          ) : (
            <span className="text-emerald-300">{count}개{firstCategory ? ` (limit=1 응답)` : ''}</span>
          )}
          {error && (
            <button
              onClick={() => setRetryToken((t) => t + 1)}
              className="ml-2 text-[10px] text-rose-400 hover:text-rose-200 underline"
            >
              재시도
            </button>
          )}
        </div>
      </div>
    </Section>
  );
}

// ─── §6 mapper ───────────────────────────────────────────────────────────

function MapperExtra({ config, workflow, warehouseTotalCache }: ExtraInfoProps) {
  const warehouseNodeId = (config.warehouseNodeId as string | undefined) ?? '';
  const matchKey = config.matchKey as string | undefined;

  // [P-6] 캐시 hit 여부 — 데이터 탭이 이미 fetch 했으면 재사용
  const cachedCount = warehouseNodeId ? warehouseTotalCache?.get(warehouseNodeId) ?? null : null;

  const [count, setCount] = useState<number | null>(cachedCount);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  // 참조 창고 노드의 인스턴스 이름 lookup
  const warehouseNodeName = warehouseNodeId
    ? workflow.nodes.find((n) => n.id === warehouseNodeId)?.name ?? '(이름 미상)'
    : null;

  useEffect(() => {
    if (!warehouseNodeId) {
      setCount(null);
      setLoading(false);
      setError(null);
      return;
    }
    // [P-6] 캐시에 있으면 fetch 생략
    const cached = warehouseTotalCache?.get(warehouseNodeId);
    if (cached !== undefined) {
      setCount(cached);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    factoryApi
      .getWarehouse(warehouseNodeId, { limit: 1 })
      .then((res) => {
        if (cancelled) return;
        setCount(res.total);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [warehouseNodeId, retryToken, warehouseTotalCache]);

  return (
    <Section title="추가 정보 — 참조 창고">
      {!warehouseNodeId ? (
        <ExtraEmpty message="참조 창고 미설정 — config.warehouseNodeId 가 비어있습니다." />
      ) : (
        <div className="rounded-md border border-slate-800 bg-slate-950/40 p-3 space-y-1.5 text-[11px]">
          <div>
            <span className="text-gray-500 font-mono">warehouseNodeId: </span>
            <span className="text-emerald-300 font-mono">{warehouseNodeId}</span>
          </div>
          {warehouseNodeName && (
            <div>
              <span className="text-gray-500 font-mono">name: </span>
              <span className="text-slate-200">{warehouseNodeName}</span>
            </div>
          )}
          {matchKey && (
            <div>
              <span className="text-gray-500 font-mono">matchKey: </span>
              <span className="text-amber-300 font-mono">{matchKey}</span>
            </div>
          )}
          <div className="pt-1.5 border-t border-slate-800/60">
            <span className="text-gray-500">적재 카운트: </span>
            {loading ? (
              <span className="text-gray-500 italic">로딩…</span>
            ) : error ? (
              <>
                <span className="text-rose-400">조회 실패</span>
                <button
                  onClick={() => setRetryToken((t) => t + 1)}
                  className="ml-2 text-[10px] text-rose-400 hover:text-rose-200 underline"
                >
                  재시도
                </button>
              </>
            ) : count === null ? (
              <span className="text-gray-700">—</span>
            ) : (
              <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-900/40 text-emerald-300 border border-emerald-700/40">
                {count}개
              </span>
            )}
          </div>
        </div>
      )}
    </Section>
  );
}

// ─── §6 sorter ───────────────────────────────────────────────────────────

function SorterExtra({ config }: ExtraInfoProps) {
  const rules = (config.rules as Array<Record<string, unknown>> | undefined) ?? [];
  // dataSource 가 instance-db 인 룰들의 첫 instanceDbId 추출
  const firstInstanceDbId = (() => {
    for (const r of rules) {
      const ds = r.dataSource as Record<string, unknown> | undefined;
      if (ds?.type === 'instance-db' && typeof ds.instanceDbId === 'string') {
        return ds.instanceDbId as string;
      }
    }
    return null;
  })();

  const [meta, setMeta] = useState<InstanceDB | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    if (!firstInstanceDbId) {
      setMeta(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    instanceDbApi
      .get(firstInstanceDbId)
      .then((d) => {
        if (cancelled) return;
        setMeta(d);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [firstInstanceDbId, retryToken]);

  if (rules.length === 0) {
    return (
      <Section title="추가 정보 — 분류 룰">
        <ExtraEmpty message="rules 가 비어있습니다." />
      </Section>
    );
  }

  return (
    <Section title="추가 정보 — 분류 룰" subtitle={`${rules.length}개`}>
      <div className="space-y-1.5">
        {rules.slice(0, 8).map((r, i) => {
          const handle = (r.handle as string | undefined) ?? `rule-${i}`;
          const field = r.field as string | undefined;
          const operator = r.operator as string | undefined;
          const value = r.value;
          return (
            <div
              key={i}
              className="rounded bg-slate-950/40 border border-slate-800 px-2 py-1 text-[10px] font-mono"
            >
              <span className="text-cyan-300">{handle}</span>
              <span className="text-gray-600">: </span>
              {field && <span className="text-amber-300">{field} </span>}
              {operator && <span className="text-gray-500">{operator} </span>}
              {value !== undefined && (
                <span className="text-emerald-300 break-all">
                  {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                </span>
              )}
            </div>
          );
        })}
        {rules.length > 8 && <p className="text-[10px] text-gray-500 italic">외 {rules.length - 8}개</p>}
      </div>
      {firstInstanceDbId && (
        <div className="mt-3">
          <div className="text-[9px] font-semibold text-gray-500 uppercase tracking-wider mb-1">
            첫 instance-db dataSource
          </div>
          {loading ? (
            <ExtraLoading />
          ) : error ? (
            <ExtraError message={`인스턴스DB 조회 실패: ${error}`} onRetry={() => setRetryToken((t) => t + 1)} />
          ) : meta ? (
            <div className="rounded-md border border-slate-800 bg-slate-950/40 px-2.5 py-1.5 text-[11px]">
              <div className="font-semibold text-slate-200 truncate">{meta.name}</div>
              {meta.description && (
                <div className="text-[10px] text-slate-400 truncate">{meta.description}</div>
              )}
            </div>
          ) : null}
        </div>
      )}
    </Section>
  );
}

// ─── §6 result / markdown-viewer (warehouse count) ───────────────────────

function WarehouseCountExtra({ nodeInstanceId, config, defType, warehouseTotalCache }: ExtraInfoProps) {
  // [P-6] 캐시 hit 여부 — 데이터 탭이 이미 fetch 했으면 재사용
  const cachedCount = warehouseTotalCache?.get(nodeInstanceId) ?? null;

  const [count, setCount] = useState<number | null>(cachedCount);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);

  useEffect(() => {
    // [P-6] 캐시에 있으면 fetch 생략
    const cached = warehouseTotalCache?.get(nodeInstanceId);
    if (cached !== undefined) {
      setCount(cached);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    factoryApi
      .getWarehouse(nodeInstanceId, { limit: 1 })
      .then((res) => {
        if (cancelled) return;
        setCount(res.total);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [nodeInstanceId, retryToken, warehouseTotalCache]);

  const displayKey = config.displayKey as string | undefined;

  return (
    <Section title="추가 정보 — 창고 적재">
      <div className="rounded-md border border-slate-800 bg-slate-950/40 p-3 space-y-1.5 text-[11px]">
        <div>
          <span className="text-gray-500">적재 카운트: </span>
          {loading ? (
            <span className="text-gray-500 italic">로딩…</span>
          ) : error ? (
            <>
              <span className="text-rose-400">조회 실패</span>
              <button
                onClick={() => setRetryToken((t) => t + 1)}
                className="ml-2 text-[10px] text-rose-400 hover:text-rose-200 underline"
              >
                재시도
              </button>
            </>
          ) : count === null ? (
            <span className="text-gray-700">—</span>
          ) : (
            <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-900/40 text-emerald-300 border border-emerald-700/40">
              {count}개
            </span>
          )}
        </div>
        {defType === 'markdown-viewer' && displayKey && (
          <div>
            <span className="text-gray-500 font-mono">렌더 필드 (displayKey): </span>
            <span className="text-amber-300 font-mono">{displayKey}</span>
          </div>
        )}
      </div>
    </Section>
  );
}

export default NodeInfoTab;
