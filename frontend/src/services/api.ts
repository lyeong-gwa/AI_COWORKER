/**
 * API 서비스 레이어
 *
 * 백엔드 API와 통신하는 함수들을 정의
 * 모든 API 응답은 camelCase로 반환됨
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

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

import type { KnowledgeDocument } from '../types';

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
  /** 문서 목록 조회 */
  list: (category?: string): Promise<KnowledgeDocument[]> =>
    request(`/knowledge${category ? `?category=${category}` : ''}`),

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

  /** 벡터 DB 동기화 (id 없으면 전체) */
  sync: (id?: string): Promise<{ synced: number; total?: number; document?: KnowledgeDocument }> =>
    request(`/knowledge/sync${id ? `?id=${id}` : ''}`, { method: 'POST' }),

  /** 유사도 검색 */
  search: (data: SearchKnowledgeData): Promise<KnowledgeSearchResult[]> =>
    request('/knowledge/search', { method: 'POST', body: JSON.stringify(data) }),

  /** 고유 카테고리/태그 목록 + 카테고리별 태그 매핑 조회 */
  meta: (): Promise<{ categories: string[]; tags: string[]; categoryTags: Record<string, string[]> }> =>
    request('/knowledge/meta'),
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

export const nodeApi = {
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

import type { Workflow } from '../types';

export interface CreateWorkflowData {
  name: string;
  description?: string;
  tags?: string[];
  viewport?: { x: number; y: number; zoom: number };
  trigger?: { type: string; config: Record<string, unknown> };
  variables?: Record<string, unknown>;
  nodes?: Array<{
    id: string;
    nodeId: string;
    definitionType?: string;
    aiNodeId?: string;
    name: string;
    position: { x: number; y: number };
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

  /** 워크플로우 삭제 */
  delete: (id: string): Promise<void> =>
    request(`/workflows/${id}`, { method: 'DELETE' }),

  /** 워크플로우 실행 */
  execute: (id: string, inputData: Record<string, unknown> = {}): Promise<WorkflowExecution> =>
    request(`/workflows/${id}/execute`, { method: 'POST', body: JSON.stringify({ inputData }) }),

  /** 실행 목록 조회 */
  listExecutions: (workflowId: string): Promise<WorkflowExecution[]> =>
    request(`/workflows/${workflowId}/executions`),

  /** 실행 상세 조회 */
  getExecution: (executionId: string): Promise<WorkflowExecution> =>
    request(`/workflows/executions/${executionId}`),

  /** 실행 취소 */
  cancelExecution: (executionId: string): Promise<{ message: string }> =>
    request(`/workflows/executions/${executionId}/cancel`, { method: 'POST' }),

  /** 실행 스트리밍 (SSE) */
  streamExecution: (executionId: string): EventSource => {
    return new EventSource(`${API_BASE}/workflows/executions/${executionId}/stream`);
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Factory API (Factorio-style singleton factory map)
// ─────────────────────────────────────────────────────────────────────────────

import type { FactoryMap, WarehouseListResponse, QueueListResponse } from '../types';

export interface FactoryMapUpdateData {
  viewport?: { x: number; y: number; zoom: number };
  nodes?: Array<{
    id: string;
    nodeId: string;
    definitionType?: string;
    aiNodeId?: string;
    name: string;
    position: { x: number; y: number };
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

  /** 창고 데이터 조회 */
  getWarehouse: (nodeId: string, limit: number = 50): Promise<WarehouseListResponse> =>
    request(`/factory/warehouse/${nodeId}?limit=${limit}`),

  /** 창고 비우기 */
  clearWarehouse: (nodeId: string): Promise<void> =>
    request(`/factory/warehouse/${nodeId}`, { method: 'DELETE' }),

  /** 창고 항목 선택 삭제 */
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
    const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/api\/v1$/, '');
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

// Export error class
export { ApiError };
