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
// Task API
// ─────────────────────────────────────────────────────────────────────────────

import type { Task, TaskStatus, TaskPriority } from '../types';

export interface CreateTaskData {
  title: string;
  description?: string;
  status?: TaskStatus;
  priority?: TaskPriority;
  tags?: string[];
  assigneeId?: string;
  assigneeName?: string;
  dueDate?: string;
  relatedNodeId?: string;
}

export interface UpdateTaskData extends Partial<CreateTaskData> {
  todos?: Array<{ id: string; text: string; completed: boolean }>;
  comments?: Array<{ id: string; userId: string; userName: string; content: string; createdAt: string }>;
  activityLog?: Array<{ id: string; userId: string; userName: string; action: string; details?: string; createdAt: string }>;
}

export const taskApi = {
  /** 태스크 목록 조회 */
  list: (status?: TaskStatus): Promise<Task[]> =>
    request(`/tasks${status ? `?status=${status}` : ''}`),

  /** 태스크 상세 조회 */
  get: (id: string): Promise<Task> =>
    request(`/tasks/${id}`),

  /** 태스크 생성 */
  create: (data: CreateTaskData): Promise<Task> =>
    request('/tasks', { method: 'POST', body: JSON.stringify(data) }),

  /** 태스크 수정 */
  update: (id: string, data: UpdateTaskData): Promise<Task> =>
    request(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),

  /** 태스크 상태 변경 */
  updateStatus: (id: string, status: TaskStatus): Promise<Task> =>
    request(`/tasks/${id}/status?status=${status}`, { method: 'PATCH' }),

  /** 태스크 삭제 */
  delete: (id: string): Promise<void> =>
    request(`/tasks/${id}`, { method: 'DELETE' }),

  /** 댓글 삭제 */
  deleteComment: async (taskId: string, commentId: string): Promise<void> => {
    await request(`/tasks/${taskId}/comments/${commentId}`, { method: 'DELETE' });
  },

  /** 활동 이력 삭제 */
  deleteActivity: async (taskId: string, logId: string): Promise<void> => {
    await request(`/tasks/${taskId}/activity/${logId}`, { method: 'DELETE' });
  },

  /** 참조 자료 추가 */
  addReference: async (taskId: string, ref: { docId: string; title: string; content: string; category: string }): Promise<Task> => {
    return request(`/tasks/${taskId}/references`, { method: 'POST', body: JSON.stringify(ref) });
  },

  /** 참조 자료 삭제 */
  deleteReference: async (taskId: string, docId: string): Promise<void> => {
    await request(`/tasks/${taskId}/references/${docId}`, { method: 'DELETE' });
  },
};

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
};

// ─────────────────────────────────────────────────────────────────────────────
// Tool API
// ─────────────────────────────────────────────────────────────────────────────

import type { ToolDefinition, ToolType, ToolConfig } from '../types';

export interface CreateToolData {
  name: string;
  description: string;
  type: ToolType;
  icon?: string;
  color?: string;
  config: ToolConfig;
  tags?: string[];
}

export interface UpdateToolData extends Partial<Omit<CreateToolData, 'type'>> {}

export interface ToolTestResult {
  success: boolean;
  output?: unknown;
  error?: string;
  executionTimeMs: number;
  logs: string[];
}

export const toolApi = {
  /** 도구 목록 조회 */
  list: (type?: ToolType): Promise<ToolDefinition[]> =>
    request(`/tools${type ? `?type=${type}` : ''}`),

  /** 도구 상세 조회 */
  get: (id: string): Promise<ToolDefinition> =>
    request(`/tools/${id}`),

  /** 도구 생성 */
  create: (data: CreateToolData): Promise<ToolDefinition> =>
    request('/tools', { method: 'POST', body: JSON.stringify(data) }),

  /** 도구 수정 */
  update: (id: string, data: UpdateToolData): Promise<ToolDefinition> =>
    request(`/tools/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),

  /** 도구 삭제 */
  delete: (id: string): Promise<void> =>
    request(`/tools/${id}`, { method: 'DELETE' }),

  /** 도구 테스트 */
  test: (id: string, inputData: Record<string, unknown>): Promise<ToolTestResult> =>
    request(`/tools/${id}/test`, { method: 'POST', body: JSON.stringify({ inputData }) }),
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
  linkedToolIds?: string[];
  knowledge?: {
    linkedIds: string[];
    filters?: Record<string, unknown>;
    maxTokens?: number;
  };
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
  toolResults?: Record<string, unknown>;
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
    mockToolResults?: Record<string, unknown>,
    mockKnowledge?: string
  ): Promise<NodeTestResult> =>
    request(`/nodes/${id}/test`, {
      method: 'POST',
      body: JSON.stringify({ inputData, mockToolResults, mockKnowledge }),
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

// Export error class
export { ApiError };
