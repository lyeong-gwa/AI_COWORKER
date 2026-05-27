/**
 * API 서비스 레이어
 *
 * 백엔드 API와 통신하는 함수들을 정의
 * 모든 API 응답은 camelCase로 반환됨
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1';

// ─────────────────────────────────────────────────────────────────────────────
// 공통 유틸리티
// ─────────────────────────────────────────────────────────────────────────────

class ApiError extends Error {
  status: number;
  detail?: string;

  constructor(
    message: string,
    status: number,
    detail?: string
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;

  const config: RequestInit = {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  };

  try {
    const response = await fetch(url, config);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const detail = errorData.detail;
      // FastAPI validation errors return detail as array of objects
      const message = typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg?: string; loc?: string[] }) =>
              `${d.loc?.slice(1).join('.') || ''}: ${d.msg || ''}`
            ).join('; ')
          : `HTTP ${response.status}`;
      throw new ApiError(message, response.status, message);
    }

    // 204 No Content
    if (response.status === 204) {
      return undefined as T;
    }

    return response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError('네트워크 오류가 발생했습니다', 0, String(error));
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Knowledge API
// ─────────────────────────────────────────────────────────────────────────────

import type { KnowledgeDocument, KnowledgeGraphResponse, KnowledgeService, LintReport, IndexRebuildResponse, KnowledgeEdgeDetail } from '../types';

export interface CreateKnowledgeData {
  title: string;
  content: string;
  source?: string;
  category?: string;
  tags?: string[];
}

export interface UpdateKnowledgeData {
  title: string;
  content: string;
  source?: string;
  category?: string;
  tags?: string[];
}

export interface SearchKnowledgeData {
  query: string;
  topK?: number;
  category?: string;
}

export interface KnowledgeSearchResult {
  document: KnowledgeDocument;
  score: number;
}

export const knowledgeApi = {
  /**
   * 문서 목록 조회.
   *
   * Backward compatible 시그니처:
   *   - `knowledgeApi.list()` — 전체 조회
   *   - `knowledgeApi.list("foo")` — string 인자: category 필터 (legacy)
   *   - `knowledgeApi.list({ category, limit, offset })` — 객체 인자 (P-2)
   *
   * backend (`knowledge.py:82-87`) 가 category/skip/limit 파라미터를 모두 지원.
   */
  list: (
    params?: string | { category?: string; service?: string; limit?: number; offset?: number },
  ): Promise<KnowledgeDocument[]> => {
    // Legacy: string 인자는 category 로 해석
    const obj = typeof params === 'string' ? { category: params } : params;
    const qs = new URLSearchParams();
    if (obj?.category) qs.set('category', obj.category);
    if (obj?.service) qs.set('service', obj.service);
    if (obj?.limit !== undefined) qs.set('limit', String(obj.limit));
    if (obj?.offset !== undefined) qs.set('skip', String(obj.offset));
    const query = qs.toString();
    return request(`/knowledge${query ? `?${query}` : ''}`);
  },

  /** 문서 상세 조회 */
  get: (id: string): Promise<KnowledgeDocument> =>
    request(`/knowledge/${id}`),

  /** 문서 생성 */
  create: (data: CreateKnowledgeData): Promise<KnowledgeDocument> =>
    request('/knowledge', { method: 'POST', body: JSON.stringify(data) }),

  /** 문서 수정 */
  update: (id: string, data: UpdateKnowledgeData): Promise<KnowledgeDocument> =>
    request(`/knowledge/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  /** 문서 삭제 */
  delete: (id: string): Promise<void> =>
    request(`/knowledge/${id}`, { method: 'DELETE' }),

  /** 벡터 DB 동기화 (id: 단일 즉시, 없으면 전체 백그라운드) */
  sync: (id?: string): Promise<{ synced: number; total?: number; document?: KnowledgeDocument; message?: string; status?: string }> =>
    request(`/knowledge/sync${id ? `?id=${id}` : ''}`, { method: 'POST' }),

  /** 일괄 동기화 진행 상태 조회 */
  syncStatus: (): Promise<{ status: string; total: number; synced: number; failed: number }> =>
    request('/knowledge/sync/status'),

  /** 유사도 검색 */
  search: (data: SearchKnowledgeData): Promise<KnowledgeSearchResult[]> =>
    request('/knowledge/search', { method: 'POST', body: JSON.stringify(data) }),

  /** 고유 카테고리/태그 목록 + 카테고리별 태그 매핑 조회 */
  meta: (): Promise<{ categories: string[]; tags: string[]; categoryTags: Record<string, string[]> }> =>
    request('/knowledge/meta'),

  // ── Karpathy v2 신규 메서드 ──────────────────────────────────────────────

  /** 역참조(backlinks) 조회 — 이 페이지를 가리키는 모든 페이지 id 목록 */
  getBacklinks: (id: string): Promise<{ id: string; backlinks: string[] }> =>
    request(`/knowledge/${encodeURIComponent(id)}/backlinks`),

  /** 링크 그래프 조회 — nodes/edges */
  getGraph: (params?: { category?: string; page_type?: string; service?: string }): Promise<KnowledgeGraphResponse> => {
    const qs = new URLSearchParams();
    if (params?.category) qs.set('category', params.category);
    if (params?.page_type) qs.set('page_type', params.page_type);
    if (params?.service) qs.set('service', params.service);
    const query = qs.toString();
    return request(`/knowledge/graph${query ? `?${query}` : ''}`);
  },

  /** 등록된 서비스 목록 조회 */
  getServices: (): Promise<KnowledgeService[]> =>
    request('/knowledge/services'),

  /** on-demand lint 실행 */
  runLint: (body: {
    categories?: string[] | null;
    dry_run?: boolean;
    llm_enabled?: boolean;
  }): Promise<LintReport> =>
    request('/knowledge/lint', { method: 'POST', body: JSON.stringify(body) }),

  /** 인덱스 재생성 — `_index-{category}.md` 전체 재생성 */
  rebuildIndex: (body: { categories?: string[] | null }): Promise<IndexRebuildResponse> =>
    request('/knowledge/index/rebuild', { method: 'POST', body: JSON.stringify(body) }),

  /** Consumer B 전용 — CLI 어시스턴트 작업이해용 briefing */
  getBrief: (body: {
    topic?: string;
    query?: string;
    categories?: string[];
    maxPages?: number;
    includeLog?: boolean;
  }): Promise<{
    pages: Array<{ id: string; title: string; page_type: string; category: string; content: string; score: number }>;
    indexes: Array<{ category: string; content: string }>;
    recentChanges?: Array<{ timestamp: string; id: string; summary: string }>;
  }> =>
    request('/knowledge/brief', { method: 'POST', body: JSON.stringify(body) }),

  /** 엣지 상세 조회 — GET /api/v1/knowledge/edge?from=ID&to=ID */
  getEdge: ({ from, to }: { from: string; to: string }): Promise<KnowledgeEdgeDetail> =>
    request(`/knowledge/edge?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`),

  /** implicit → explicit 승격 — POST /api/v1/knowledge/edge/promote */
  promoteEdge: ({ from, to, anchorText }: { from: string; to: string; anchorText: string }): Promise<{
    from: string;
    to: string;
    newVersion: number;
    linkAdded: boolean;
    anchorText: string;
  }> =>
    request('/knowledge/edge/promote', { method: 'POST', body: JSON.stringify({ from, to, anchorText }) }),

  /** Raw 소스 업로드 — binary blob + RawSource row 생성 */
  uploadRaw: (file: File, derivedKnowledgeIds?: string[]): Promise<{
    id: string;
    filename: string;
    mime: string;
    size: number;
    content_hash: string;
    uploaded_at: string;
    original_blob_path: string;
    derived_knowledge_ids: string[];
  }> => {
    const formData = new FormData();
    formData.append('file', file);
    if (derivedKnowledgeIds?.length) {
      formData.append('derived_knowledge_ids', JSON.stringify(derivedKnowledgeIds));
    }
    return request('/knowledge/raw', {
      method: 'POST',
      body: formData,
      headers: {}, // Content-Type은 FormData 자동 설정
    });
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// API Docs API (api-call 노드용 API 문서)
// ─────────────────────────────────────────────────────────────────────────────

import type { ApiDocSummary } from '../types';

export interface ApiTestResult {
  success: boolean;
  output?: unknown;
  error?: string;
  executionTimeMs: number;
  logs: string[];
}

export const apiDocsApi = {
  /** API 지식 문서 목록 조회 */
  listApiDocs: (): Promise<ApiDocSummary[]> =>
    request('/tools/api-docs'),

  /** 지식 문서 기반 API 호출 실행 */
  executeApiDoc: (docId: string, inputData: Record<string, unknown>): Promise<ApiTestResult> =>
    request('/tools/execute-api-doc', { method: 'POST', body: JSON.stringify({ docId, inputData }) }),

  /** 원시 API 호출 테스트 (Postman 스타일) */
  testRawApi: (params: {
    method: string;
    url: string;
    headers: Record<string, string>;
    bodyTemplate?: string;
    inputData: Record<string, string>;
  }): Promise<ApiTestResult> =>
    request('/tools/test-raw-api', { method: 'POST', body: JSON.stringify(params) }),
};

// ─────────────────────────────────────────────────────────────────────────────
// API Definition API
// ─────────────────────────────────────────────────────────────────────────────

import type { ApiDefinition, CreateApiDefinitionData, UpdateApiDefinitionData } from '../types';

// ─── API Definition API ───────────────────────────────────────────────────────

export const apiDefinitionApi = {
  /** API 정의 목록 조회 */
  list: (params?: { category?: string }): Promise<ApiDefinition[]> => {
    const query = params?.category ? `?category=${encodeURIComponent(params.category)}` : '';
    return request(`/api-definitions${query}`);
  },

  /** API 정의 단건 조회 */
  get: (id: string): Promise<ApiDefinition> =>
    request(`/api-definitions/${id}`),

  /** API 정의 생성 */
  create: (data: CreateApiDefinitionData): Promise<ApiDefinition> =>
    request('/api-definitions', { method: 'POST', body: JSON.stringify(data) }),

  /** API 정의 수정 */
  update: (id: string, data: UpdateApiDefinitionData): Promise<ApiDefinition> =>
    request(`/api-definitions/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),

  /** API 정의 삭제 */
  delete: (id: string): Promise<void> =>
    request(`/api-definitions/${id}`, { method: 'DELETE' }),

  /** API 정의 기반 호출 실행 */
  execute: (id: string, inputData: Record<string, unknown>): Promise<ApiTestResult> =>
    request(`/api-definitions/${id}/execute`, { method: 'POST', body: JSON.stringify({ inputData }) }),

  /** 원시 API 테스트 (Postman 스타일) */
  testApi: (params: {
    method: string;
    url: string;
    headers: Record<string, string>;
    bodyTemplate?: string;
    inputData: Record<string, string>;
  }): Promise<ApiTestResult> =>
    request('/api-definitions/test-api', { method: 'POST', body: JSON.stringify(params) }),

  /** 테스트 응답에서 자동 스키마 추출 */
  capture: (responseData: unknown, urlTemplate?: string): Promise<{ parameters: any[]; responseSchema: any }> =>
    request('/api-definitions/capture', { method: 'POST', body: JSON.stringify({ responseData, urlTemplate: urlTemplate || '' }) }),
};

// ─────────────────────────────────────────────────────────────────────────────
// InstanceDB API (Phase A — 메타 CRUD + records 조회)
// ─────────────────────────────────────────────────────────────────────────────
//
// 인스턴스DB는 워크플로우가 자동 누적하는 동질 record 컬렉션. records 추가는
// Phase B 의 노드 핸들러(`instance-db-insert`) 가 책임지므로 클라이언트는 GET 만 노출.
// Phase D 의 UI 가 이 API 클라이언트를 사용한다.

import type {
  InstanceDB,
  InstanceDBRecord,
  CreateInstanceDBData,
  UpdateInstanceDBData,
  InstanceDBRecordListResponse,
} from '../types';

export const instanceDbApi = {
  /** 인스턴스DB 목록 (q 검색 query 지원) */
  list: (q?: string): Promise<InstanceDB[]> =>
    request(`/instance-dbs${q ? `?q=${encodeURIComponent(q)}` : ''}`),

  /** 인스턴스DB 상세 */
  get: (id: string): Promise<InstanceDB> =>
    request(`/instance-dbs/${id}`),

  /** 인스턴스DB 등록 */
  create: (data: CreateInstanceDBData): Promise<InstanceDB> =>
    request('/instance-dbs', { method: 'POST', body: JSON.stringify(data) }),

  /** 인스턴스DB 수정 */
  update: (id: string, data: UpdateInstanceDBData): Promise<InstanceDB> =>
    request(`/instance-dbs/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  /** 인스턴스DB 삭제 (records cascade) */
  delete: (id: string): Promise<{ message: string; id: string }> =>
    request(`/instance-dbs/${id}`, { method: 'DELETE' }),

  /** records 리스트 (limit/offset/sourceWorkflowId/sourceExecutionId — R-9) */
  listRecords: (
    id: string,
    params: {
      limit?: number;
      offset?: number;
      /** R-9: WorkflowViewerPage 컨텍스트 필터 */
      sourceWorkflowId?: string;
      /** R-9: InstanceDetailPage 컨텍스트 필터 */
      sourceExecutionId?: string;
    } = {},
  ): Promise<InstanceDBRecordListResponse> => {
    const qs = new URLSearchParams();
    if (params.limit !== undefined) qs.set('limit', String(params.limit));
    if (params.offset !== undefined) qs.set('offset', String(params.offset));
    if (params.sourceWorkflowId !== undefined) qs.set('sourceWorkflowId', params.sourceWorkflowId);
    if (params.sourceExecutionId !== undefined) qs.set('sourceExecutionId', params.sourceExecutionId);
    const query = qs.toString();
    return request(`/instance-dbs/${id}/records${query ? `?${query}` : ''}`);
  },

  /** records 단건 조회 */
  getRecord: (id: string, recordId: string): Promise<InstanceDBRecord> =>
    request(`/instance-dbs/${id}/records/${recordId}`),

  /** record 단건 삭제 */
  deleteRecord: (idbId: string, recordId: string): Promise<{ deleted: boolean; recordId: string }> =>
    request(`/instance-dbs/${idbId}/records/${recordId}`, { method: 'DELETE' }),

  /** records bulk 삭제 */
  bulkDeleteRecords: (
    idbId: string,
    body: { recordIds?: string[]; filter?: Record<string, unknown> },
  ): Promise<{ deletedCount: number; deletedIds: string[] }> =>
    request(`/instance-dbs/${idbId}/records/delete`, { method: 'POST', body: JSON.stringify(body) }),

  /** records 전체 비우기 (메타 보존). confirmDbId 가 idbId 와 일치해야 진행. */
  clearInstanceDbRecords: (
    idbId: string,
  ): Promise<{ cleared: boolean; instanceDbId: string; deletedCount: number }> =>
    request(`/instance-dbs/${idbId}/records/clear`, {
      method: 'POST',
      body: JSON.stringify({ confirmDbId: idbId }),
    }),

  /**
   * record 즉석 변환 다운로드 URL 빌더.
   * 실제 fetch 없이 URL 문자열만 반환한다 (다운로드 트리거용).
   *
   * @param dbId      instance_db_id
   * @param recId     record_id
   * @param format    "md" | "csv" | "html" | "xlsx"
   * @param field     optional — record.data 의 특정 필드만 추출할 때
   */
  recordExportUrl: (
    dbId: string,
    recId: string,
    format: 'md' | 'csv' | 'html' | 'xlsx',
    field?: string,
  ): string => {
    const qs = new URLSearchParams({ format });
    if (field) qs.set('field', field);
    return `${API_BASE}/instance-dbs/${dbId}/records/${recId}/export?${qs.toString()}`;
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Node API
// ─────────────────────────────────────────────────────────────────────────────

import type { AINode } from '../types';

export interface CreateNodeData {
  name: string;
  description: string;
  icon?: string;
  color?: string;
  tags?: string[];
  systemPrompt?: string;
  userPromptTemplate?: string;
  inputSchema?: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
  outputEnforcement?: {
    enabled: boolean;
    includeSchemaInPrompt: boolean;
    exampleOutput?: string;
    validationEnabled: boolean;
    retryOnFailure: boolean;
    maxRetries: number;
  };
  llmConfig?: {
    model?: string;
    temperature?: number;
    maxTokens?: number;
  };
  isActive?: boolean;
}

export interface UpdateNodeData extends Partial<CreateNodeData> {}

export interface NodeTestResult {
  success: boolean;
  output?: unknown;
  error?: string;
  errorType?: string;
  logs: Array<{ timestamp: string; level: string; message: string; data?: unknown }>;
  renderedPrompt?: string;
  llmResponse?: string;
  validationPassed?: boolean;
  validationErrors?: string[];
  executionTimeMs: number;
  tokenUsage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
}

// ─── Node Catalog (11종 범용 노드 스펙) ─────────────────────────────────────

export interface NodeCatalogIOField {
  name: string;
  type: string;
  required: boolean;
  description: string;
  example?: unknown;
}

export interface NodeCatalogConfigField {
  name: string;
  type: string;
  default?: unknown;
  description: string;
  required: boolean;
}

export interface NodeCatalogEntry {
  defType: string;
  label: string;
  category: 'starter' | 'ai' | 'logic' | 'action' | 'output';
  purpose: string;
  inputs: NodeCatalogIOField[];
  outputs: NodeCatalogIOField[];
  config: NodeCatalogConfigField[];
  useCases: string[];
  connectsWellWith: string[];
  requiresUpstream: boolean;
  producesArray: boolean;
}

export const nodeApi = {
  /** 노드 카탈로그 조회 (11종 범용 노드 스펙) */
  getCatalog: (): Promise<NodeCatalogEntry[]> =>
    request('/nodes/catalog'),

  /** 노드 목록 조회 */
  list: (category?: string): Promise<AINode[]> =>
    request(`/nodes${category ? `?category=${category}` : ''}`),

  /** 노드 상세 조회 */
  get: (id: string): Promise<AINode> =>
    request(`/nodes/${id}`),

  /** 노드 생성 */
  create: (data: CreateNodeData): Promise<AINode> =>
    request('/nodes', { method: 'POST', body: JSON.stringify(data) }),

  /** 노드 수정 */
  update: (id: string, data: UpdateNodeData): Promise<AINode> =>
    request(`/nodes/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),

  /** 노드 삭제 */
  delete: (id: string): Promise<void> =>
    request(`/nodes/${id}`, { method: 'DELETE' }),

  /** 노드 테스트 */
  test: (
    id: string,
    inputData: Record<string, unknown>,
  ): Promise<NodeTestResult> =>
    request(`/nodes/${id}/test`, {
      method: 'POST',
      body: JSON.stringify({ inputData }),
    }),
};

// ─────────────────────────────────────────────────────────────────────────────
// Workflow API
// ─────────────────────────────────────────────────────────────────────────────

import type { Workflow, WorkflowDeletePreview } from '../types';

export interface CreateWorkflowData {
  name: string;
  description?: string;
  tags?: string[];
  createdBy?: string;
  trigger?: { type: string; config: Record<string, unknown> };
  variables?: Record<string, unknown>;
  nodes?: Array<{
    id: string;
    nodeId: string;
    definitionType?: string;
    aiNodeId?: string;
    name: string;
    orderIndex?: number;
    configOverrides?: Record<string, unknown>;
    inputMapping?: Record<string, string>;
  }>;
  connections?: Array<{
    id: string;
    sourceNodeId: string;
    targetNodeId: string;
    condition?: { field: string; operator: string; value: unknown };
  }>;
}

export interface UpdateWorkflowData extends Partial<CreateWorkflowData> {
  status?: 'draft' | 'active' | 'paused' | 'archived';
}

export interface WorkflowSummary {
  id: string;
  name: string;
  description?: string;
  status: 'draft' | 'active' | 'paused' | 'archived';
  tags: string[];
  nodeCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowExecution {
  id: string;
  workflowId: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  inputData: Record<string, unknown>;
  outputData?: Record<string, unknown>;
  nodeResults: Record<string, unknown>;
  errorMessage?: string;
  errorNodeId?: string;
  startedAt?: string;
  completedAt?: string;
  createdAt: string;
}

export interface RunWorkflowResponse {
  instanceId: string;
  workflowId: string;
  status: 'queued';
  createdAt: string | null;
}

export const workflowApi = {
  /** 워크플로우 목록 조회 */
  list: (status?: string): Promise<WorkflowSummary[]> =>
    request(`/workflows${status ? `?status=${status}` : ''}`),

  /** 워크플로우 상세 조회 */
  get: (id: string): Promise<Workflow> =>
    request(`/workflows/${id}`),

  /** 워크플로우 생성 */
  create: (data: CreateWorkflowData): Promise<Workflow> =>
    request('/workflows', { method: 'POST', body: JSON.stringify(data) }),

  /** 워크플로우 수정 */
  update: (id: string, data: UpdateWorkflowData): Promise<Workflow> =>
    request(`/workflows/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),

  /** 워크플로우 삭제 preview — 함께 삭제될 데이터 카운트 조회 */
  deletePreview: (id: string): Promise<WorkflowDeletePreview> =>
    request(`/workflows/${id}/delete-preview`),

  /** 워크플로우 삭제 (cascade). 200 + body 반환. */
  delete: (id: string): Promise<{ deleted: boolean; workflowId: string; cascadeCounts: { instances: number; warehouseEntries: number; nodeResults: number } }> =>
    request(`/workflows/${id}`, { method: 'DELETE' }),

  /** 워크플로우 실행 (레거시 동기 경로) */
  execute: (id: string, inputData: Record<string, unknown> = {}): Promise<WorkflowExecution> =>
    request(`/workflows/${id}/execute`, { method: 'POST', body: JSON.stringify({ inputData }) }),

  /**
   * Phase 2b 표준 실행 진입점 — 백그라운드 실행, 202 즉시 반환.
   * 후속 진행상황은 warehouseApi.streamInstance 또는 warehouseApi.getInstance 로 관찰.
   */
  run: (id: string, inputData: Record<string, unknown> = {}): Promise<RunWorkflowResponse> =>
    request(`/workflows/${id}/run`, { method: 'POST', body: JSON.stringify({ inputData }) }),

  /** 인스턴스(실행) 목록 — /workflows/{id}/instances (설계서 섹션 5.2) */
  listInstances: (workflowId: string, limit: number = 20): Promise<WorkflowExecution[]> =>
    request(`/workflows/${workflowId}/instances?limit=${limit}`),

  /** 실행 목록 조회 (레거시 별칭) */
  listExecutions: (workflowId: string): Promise<WorkflowExecution[]> =>
    request(`/workflows/${workflowId}/executions`),

  /** 실행 상세 조회 */
  getExecution: (executionId: string): Promise<WorkflowExecution> =>
    request(`/workflows/executions/${executionId}`),

  /** 실행 취소 */
  cancelExecution: (executionId: string): Promise<{ message: string }> =>
    request(`/workflows/executions/${executionId}/cancel`, { method: 'POST' }),

  /** 실행 기록 단건 삭제 */
  deleteExecution: (executionId: string, force = false): Promise<{ message: string; id: string }> =>
    request(`/workflows/executions/${executionId}${force ? '?force=true' : ''}`, { method: 'DELETE' }),

  /** 워크플로우 실행 기록 일괄 정리 */
  cleanupExecutions: (
    workflowId: string,
    params: {
      olderThanDays?: number;
      status?: string;
      dryRun?: boolean;
    } = {},
  ): Promise<{
    candidateCount: number;
    deletedCount: number;
    warehouseEntriesDeleted: number;
    dryRun: boolean;
    olderThanDays: number;
    statuses: string[];
  }> => {
    const qs = new URLSearchParams();
    if (params.olderThanDays !== undefined) qs.set('olderThanDays', String(params.olderThanDays));
    if (params.status !== undefined) qs.set('status', params.status);
    if (params.dryRun !== undefined) qs.set('dryRun', String(params.dryRun));
    const query = qs.toString();
    return request(`/workflows/${workflowId}/executions/cleanup${query ? `?${query}` : ''}`, { method: 'POST' });
  },

  /** 실행 스트리밍 (SSE, 레거시 경로) */
  streamExecution: (executionId: string): EventSource => {
    return new EventSource(`${API_BASE}/workflows/executions/${executionId}/stream`);
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Warehouse / Instance API (Phase 2b)
// ─────────────────────────────────────────────────────────────────────────────

export interface WarehouseInstanceEntry {
  id: string;
  nodeInstanceId: string;
  executionId?: string;
  createdAt: string | null;
  data: Record<string, unknown>;
}

export const warehouseApi = {
  /** 인스턴스 상세 (창고 포함) */
  getInstance: (instanceId: string): Promise<WorkflowExecution & { instanceId: string }> =>
    request(`/warehouse/instances/${instanceId}`),

  /** 인스턴스가 적재한 창고 항목 목록 */
  listInstanceEntries: (instanceId: string, limit: number = 100): Promise<WarehouseInstanceEntry[]> =>
    request(`/warehouse/instances/${instanceId}/entries?limit=${limit}`),

  /** SSE 스트림 — 노드별 진행상황 실시간 */
  streamInstance: (instanceId: string): EventSource => {
    return new EventSource(`${API_BASE}/warehouse/instances/${instanceId}/stream`);
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Factory API (Factorio-style singleton factory map)
// ─────────────────────────────────────────────────────────────────────────────

import type { FactoryMap, WarehouseListResponse, QueueListResponse } from '../types';

export interface FactoryMapUpdateData {
  nodes?: Array<{
    id: string;
    nodeId: string;
    definitionType?: string;
    aiNodeId?: string;
    name: string;
    orderIndex?: number;
    config?: Record<string, unknown>;
    configOverrides?: Record<string, unknown>;
    inputMapping?: Record<string, string>;
  }>;
  connections?: Array<{
    id: string;
    sourceNodeId: string;
    targetNodeId: string;
    sourceHandle?: string;
    targetHandle?: string;
    condition?: { field: string; operator: string; value: unknown };
  }>;
}

export const factoryApi = {
  /** 싱글톤 팩토리 맵 조회 (없으면 자동 생성) */
  getMap: (): Promise<FactoryMap> =>
    request('/factory'),

  /** 팩토리 맵 저장 (노드, 연결, 뷰포트) */
  saveMap: (data: FactoryMapUpdateData): Promise<FactoryMap> =>
    request('/factory', { method: 'PATCH', body: JSON.stringify(data) }),

  /** 팩토리 전체 실행 */
  execute: (inputData: Record<string, unknown> = {}): Promise<WorkflowExecution> =>
    request('/factory/execute', { method: 'POST', body: JSON.stringify({ inputData }) }),

  /** 실행 이력 조회 */
  listExecutions: (limit: number = 20): Promise<WorkflowExecution[]> =>
    request(`/factory/executions?limit=${limit}`),

  /** 실행 상세 조회 */
  getExecution: (executionId: string): Promise<WorkflowExecution> =>
    request(`/factory/executions/${executionId}`),

  /** 실행 취소 */
  cancelExecution: (executionId: string): Promise<{ message: string }> =>
    request(`/factory/executions/${executionId}/cancel`, { method: 'POST' }),

  /** 실행 스트리밍 (SSE) */
  streamExecution: (executionId: string): EventSource => {
    return new EventSource(`${API_BASE}/factory/executions/${executionId}/stream`);
  },

  /**
   * 창고 데이터 조회 (B-1, P-2).
   *
   * Backward compatible 시그니처:
   *   - `factoryApi.getWarehouse(id)` — 기본 limit=50
   *   - `factoryApi.getWarehouse(id, 1)` — number 인자: limit (legacy)
   *   - `factoryApi.getWarehouse(id, { limit, skip, executionId })` — 객체 인자 (신규)
   */
  getWarehouse: (
    nodeId: string,
    params?: number | { limit?: number; skip?: number; executionId?: string },
  ): Promise<WarehouseListResponse> => {
    // Legacy: number 인자는 limit 로 해석
    const obj =
      typeof params === 'number'
        ? { limit: params }
        : (params ?? { limit: 50 });
    const qs = new URLSearchParams();
    qs.set('limit', String(obj.limit ?? 50));
    if (obj.skip !== undefined) qs.set('skip', String(obj.skip));
    if ('executionId' in obj && obj.executionId) qs.set('execution_id', obj.executionId);
    return request(`/factory/warehouse/${nodeId}?${qs.toString()}`);
  },

  /** 창고 비우기 */
  clearWarehouse: (nodeId: string): Promise<void> =>
    request(`/factory/warehouse/${nodeId}`, { method: 'DELETE' }),

  /** 창고 항목 선택 삭제 (1~N건). 인터페이스 계약: DELETE /factory/warehouse/{nodeId}/entries body {entryIds:[...]} */
  deleteEntries: (nodeId: string, entryIds: string[]): Promise<void> =>
    request(`/factory/warehouse/${nodeId}/entries`, {
      method: 'DELETE',
      body: JSON.stringify({ entryIds }),
    }),

  /** 창고 항목 선택 삭제 (legacy alias) */
  deleteWarehouseEntries: (nodeId: string, entryIds: string[]): Promise<void> =>
    request(`/factory/warehouse/${nodeId}/entries?${entryIds.map(id => `ids=${id}`).join('&')}`, { method: 'DELETE' }),

  /** 공장 노드 큐 조회 */
  getQueue: (nodeId: string, limit: number = 50): Promise<QueueListResponse> =>
    request(`/factory/queue/${nodeId}?limit=${limit}`),

  /** 공장 노드 큐 카운트 (빠른 조회) */
  getQueueCount: (nodeId: string): Promise<{ nodeInstanceId: string; total: number; pending: number; processing: number }> =>
    request(`/factory/queue/${nodeId}/count`),

  /** 공장 노드 큐 비우기 */
  clearQueue: (nodeId: string, status?: string): Promise<void> =>
    request(`/factory/queue/${nodeId}${status ? `?status=${status}` : ''}`, { method: 'DELETE' }),

  /** 노드 삭제 */
  deleteNode: (nodeId: string): Promise<void> =>
    request(`/factory/nodes/${nodeId}`, { method: 'DELETE' }),
};

// ─────────────────────────────────────────────────────────────────────────────
// Chat API
// ─────────────────────────────────────────────────────────────────────────────

import type { ChatMessage } from '../types';

export interface ChatMessageRequest {
  content: string;
  context?: {
    type: string;
    id?: string;
  };
  sessionId?: string;
  mode?: string;
  action?: string;
  knowledgeFilter?: {
    category?: string;
    tags?: string[];
    visibleDocIds?: string[];
  };
}

export interface AgentAction {
  type: 'explain' | 'view' | 'create' | 'update' | 'delete' | 'execute' | 'search' | 'fill_form';
  target: string;
  targetId?: string;
  success: boolean;
  result?: Record<string, unknown>;
  error?: string;
}

export interface ChatMessageResponse {
  id: string;
  role: 'assistant';
  content: string;
  timestamp: string;
  action?: AgentAction;
  sessionId: string;
}

export interface ChatHistoryResponse {
  sessionId: string;
  messages: ChatMessage[];
  totalCount: number;
}

export interface ChatSession {
  id: string;
  createdAt: string;
  lastMessageAt: string;
  messageCount: number;
}

export const chatApi = {
  /** 메시지 전송 */
  sendMessage: (data: ChatMessageRequest): Promise<ChatMessageResponse> =>
    request('/chat/message', { method: 'POST', body: JSON.stringify(data) }),

  /** 세션 히스토리 조회 */
  getHistory: (sessionId: string): Promise<ChatHistoryResponse> =>
    request(`/chat/session/${sessionId}`),

  /** 세션 목록 조회 */
  listSessions: (): Promise<ChatSession[]> =>
    request('/chat/sessions'),

  /** 새 세션 생성 */
  createSession: (): Promise<{ sessionId: string; message: string }> =>
    request('/chat/session', { method: 'POST' }),

  /** 세션 삭제 */
  deleteSession: (sessionId: string): Promise<{ message: string; sessionId: string }> =>
    request(`/chat/session/${sessionId}`, { method: 'DELETE' }),
};

// ─────────────────────────────────────────────────────────────────────────────
// 헬스 체크
// ─────────────────────────────────────────────────────────────────────────────

export const healthApi = {
  check: async (): Promise<{ status: string; database: string; version: string }> => {
    const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/api\/v1$/, '');
    const response = await fetch(`${baseUrl}/health`);
    if (!response.ok) throw new Error('Health check failed');
    return response.json();
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Export / Import API
// ─────────────────────────────────────────────────────────────────────────────

export interface ImportResult {
  created: number;
  updated: number;
  skipped: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Ops Dashboard API
// ─────────────────────────────────────────────────────────────────────────────

export interface OpsDashboardResponse {
  period: { from: string; to: string };
  workflows: {
    total: number;
    active: number;
    executionsLast7d: number;
    successRate: number;
    failureCount: number;
    avgDurationSec: number;
    topWorkflows: Array<{ id: string; name: string; count: number; failureRate: number }>;
  };
  tickets: {
    total: number;
    byStatus: Record<string, number>;
    byCategory: Record<string, number>;
    byPriority: Record<string, number>;
    slaBreach: number;
    openCount: number;
  };
  recentExecutions: Array<{
    id: string;
    workflowId: string;
    workflowName: string;
    status: string;
    startedAt: string | null;
    completedAt: string | null;
    createdAt: string | null;
    duration: number | null;
    errorMessage: string | null;
  }>;
  recentTickets: Array<{
    id: string;
    title: string;
    category: string;
    priority: string;
    status: string;
    requester: string;
    assignee: string | null;
    slaDueAt: string | null;
    createdAt: string | null;
  }>;
}

export const opsApi = {
  getDashboard: (): Promise<OpsDashboardResponse> => request('/ops/dashboard'),
};

export const exportImportApi = {
  exportNodes: (): Promise<any[]> =>
    request('/export/nodes'),
  importNodes: (data: any[]): Promise<ImportResult> =>
    request('/import/nodes', { method: 'POST', body: JSON.stringify(data) }),

  exportApiDefinitions: (): Promise<any[]> =>
    request('/export/api-definitions'),
  importApiDefinitions: (data: any[]): Promise<ImportResult> =>
    request('/import/api-definitions', { method: 'POST', body: JSON.stringify(data) }),

  exportKnowledge: (): Promise<any[]> =>
    request('/export/knowledge'),
  importKnowledge: (data: any[]): Promise<ImportResult> =>
    request('/import/knowledge', { method: 'POST', body: JSON.stringify(data) }),

  exportWorkflow: (id: string): Promise<any> =>
    request(`/export/workflows/${id}`),
  exportAllWorkflows: (): Promise<any[]> =>
    request('/export/workflows'),
  importWorkflows: (data: any[]): Promise<ImportResult> =>
    request('/import/workflows', { method: 'POST', body: JSON.stringify(data) }),

  // 로컬 파일 기반 가져오기 (DLP 우회)
  listLocalFiles: (): Promise<{ name: string; size: number; modifiedAt: number }[]> =>
    request('/local-files'),
  importLocalFile: (filename: string): Promise<ImportResult & { type: string }> =>
    request(`/import/local/${encodeURIComponent(filename)}`, { method: 'POST' }),
};

// ─────────────────────────────────────────────────────────────────────────────
// Dashboard API (Phase 4c)
// ─────────────────────────────────────────────────────────────────────────────

export interface DashboardCounts {
  todayRuns: number;
  inProgress: number;
  failed: number;
  completed: number;
}

export interface DashboardLatestInstance {
  id: string;
  status: string;
  startedAt: string | null;
  completedAt: string | null;
  createdAt: string | null;
}

export interface DashboardWorkflowSummary {
  id: string;
  name: string;
  description?: string;
  status: 'draft' | 'active' | 'paused' | 'archived';
  nodeCount: number;
  tags: string[];
  createdAt: string;
  updatedAt: string;
  latestInstance: DashboardLatestInstance | null;
}

export interface DashboardSummary {
  counts: DashboardCounts;
  workflows: DashboardWorkflowSummary[];
}

export const dashboardApi = {
  /**
   * 대시보드 집계 요약 — 단일 호출로 counts + workflows 반환.
   * N+1 listInstances 호출 대체.
   */
  getSummary: (): Promise<DashboardSummary> =>
    request('/dashboard/summary'),
};

// Export error class
export { ApiError };
