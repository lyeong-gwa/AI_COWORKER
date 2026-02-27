// ============================================
// Task Board Types (Trello-style)
// ============================================

export interface TodoItem {
  id: string;
  text: string;
  completed: boolean;
}

export interface Comment {
  id: string;
  authorId: string;
  authorName: string;
  content: string;
  createdAt: string;
}

export interface ActivityLog {
  id: string;
  userId: string;
  userName: string;
  action: string;
  detail: string;
  timestamp: string;
}

export interface ReferenceDoc {
  docId: string;
  title: string;
  content: string;
  category: string;
  score: number;
}

export interface TaskCard {
  id: string;
  title: string;
  description: string;
  status: 'backlog' | 'todo' | 'in-progress' | 'review' | 'done';
  priority: 'low' | 'medium' | 'high' | 'urgent';
  assigneeId?: string;
  assigneeName?: string;
  todos: TodoItem[];
  comments: Comment[];
  activityLog: ActivityLog[];
  references: ReferenceDoc[];
  tags: string[];
  dueDate?: string;
  createdAt: string;
  updatedAt: string;
}

// Task types for API compatibility
export type TaskStatus = 'backlog' | 'todo' | 'in-progress' | 'review' | 'done';
export type TaskPriority = 'low' | 'medium' | 'high' | 'urgent';

// Task (API response type) - alias to TaskCard for compatibility
export type Task = TaskCard;

export interface TaskColumn {
  id: string;
  title: string;
  status: TaskCard['status'];
  cards: TaskCard[];
}

// ============================================
// Knowledge Base Types
// 문서 1개 = 청크 1개 (1:1 매핑)
// ============================================

export interface KnowledgeDocument {
  id: string;
  title: string;
  content: string;
  source?: string;
  category: string;
  tags: string[];
  contentHash?: string;
  syncStatus: 'synced' | 'modified' | 'not_synced';
  createdAt: string;
  updatedAt: string;
}

// ============================================
// AI Node Types (LLM 기반 재사용 가능 노드)
// ============================================

// --- JSON 스키마 정의 ---
export interface JsonSchemaProperty {
  type: 'string' | 'number' | 'boolean' | 'object' | 'array';
  description?: string;
  items?: JsonSchemaProperty;     // array 타입용
  properties?: Record<string, JsonSchemaProperty>;  // object 타입용
  required?: string[];            // object 타입용
  enum?: string[];                // 선택 옵션
  default?: unknown;
}

export interface JsonSchema {
  type: 'object';
  description?: string;
  properties: Record<string, JsonSchemaProperty>;
  required?: string[];
}

// --- API 문서 메타데이터 (api-call 노드용) ---

/** API 메타데이터 */
export interface ApiDocMeta {
  method: string;
  url: string;
  headers?: Record<string, string>;
  bodyTemplate?: string;
}

/** API 문서 요약 (드롭다운 목록용) */
export interface ApiDocSummary {
  id: string;
  title: string;
  api?: ApiDocMeta;
  tags: string[];
}

// --- AI 노드 (재사용 가능한 LLM 노드) ---
export interface AINode {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  tags: string[];                 // 노드 분류용 태그

  // Input/Output 스키마 (JSON 강제)
  inputSchema: JsonSchema;
  outputSchema: JsonSchema;

  // LLM 프롬프트 설정
  systemPrompt: string;           // 시스템 프롬프트
  userPromptTemplate: string;     // 사용자 프롬프트 템플릿 ({{input.xxx}} 변수 사용)

  // LLM 설정
  llmConfig: {
    model: string;                // gpt-4o, claude-3, etc.
    temperature: number;
    maxTokens: number;
    responseFormat?: 'json' | 'text';  // JSON 강제 여부
  };

  // 출력 규격 강제 설정
  outputEnforcement?: {
    enabled: boolean;               // 출력 규격 강제 활성화
    includeSchemaInPrompt: boolean; // outputSchema를 프롬프트에 자동 삽입
    exampleOutput?: string;         // 예시 출력 (JSON 문자열)
    validationEnabled: boolean;     // 출력 검증 활성화
    retryOnFailure: boolean;        // 검증 실패 시 재시도
    maxRetries: number;             // 최대 재시도 횟수
  };

  createdAt: string;
  updatedAt: string;
}

// ============================================
// Workflow Types (AI 노드 기반)
// ============================================

export interface Position {
  x: number;
  y: number;
}

// 워크플로우 내 노드 인스턴스
export interface WorkflowNodeInstance {
  id: string;                     // 인스턴스 ID
  nodeId: string;                 // AINode.id 참조
  definitionType?: string;        // "ai-custom" | "manual" | "schedule" | "form"
  aiNodeId?: string;              // AINode reference ID
  name: string;                   // 인스턴스 이름 (기본값: AINode.name)
  position: Position;

  // 노드별 설정 (JSON) — 분류기 규칙 등
  config?: Record<string, unknown>;

  // 노드별 설정 오버라이드 (선택적)
  configOverrides?: {
    llmConfig?: Partial<AINode['llmConfig']>;
    userPromptTemplate?: string;
  };

  // 입력 매핑 (이전 노드 출력 → 현재 노드 입력)
  inputMapping?: Record<string, string>;  // { "현재입력필드": "{{prev.출력필드}}" }
}

// 노드 간 연결
export interface WorkflowConnection {
  id: string;
  sourceNodeId: string;           // WorkflowNodeInstance.id
  targetNodeId: string;           // WorkflowNodeInstance.id
  sourceHandle?: string;
  targetHandle?: string;
  // 조건부 연결 (선택적)
  condition?: {
    field: string;                // 소스 출력 필드
    operator: 'equals' | 'not_equals' | 'contains' | 'greater_than' | 'less_than';
    value: string;
  };
}

// 워크플로우 정의
export interface Workflow {
  id: string;
  name: string;
  description: string;

  // 노드 인스턴스들
  nodes: WorkflowNodeInstance[];

  // 연결
  connections: WorkflowConnection[];

  // 워크플로우 레벨 변수
  variables: Record<string, unknown>;

  // 트리거 설정
  trigger: {
    type: 'manual' | 'schedule' | 'webhook' | 'event' | 'form';
    config: Record<string, unknown>;
  };

  // 메타데이터
  tags: string[];
  createdAt: string;
  updatedAt: string;
}

// Factory Map (Factorio-style singleton)
export type FactoryMap = Workflow;  // 내부 구조 동일, 항상 1개

export interface WarehouseEntry {
  id: string;
  nodeInstanceId: string;
  executionId?: string;
  data: Record<string, unknown>;
  createdAt: string;
}

export interface WarehouseListResponse {
  items: WarehouseEntry[];
  total: number;
  nodeInstanceId: string;
}

export interface QueueItem {
  id: string;
  nodeInstanceId: string;
  executionId?: string;
  data: Record<string, unknown>;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  result?: Record<string, unknown>;
  error?: string;
  createdAt: string;
  processedAt?: string;
}

export interface QueueListResponse {
  items: QueueItem[];
  total: number;
  pending: number;
  processing: number;
  nodeInstanceId: string;
}

export interface SorterRule {
  id: string;
  field: string;
  operator: 'equals' | 'notEquals' | 'contains' | 'startsWith' | 'endsWith' | 'greaterThan' | 'lessThan' | 'exists' | 'notExists' | 'regex';
  value: string;
  label: string;
}

// ============================================
// Execution Types
// ============================================

export type ExecutionStatus = 'pending' | 'running' | 'success' | 'error' | 'cancelled';

export interface NodeExecutionLog {
  timestamp: string;
  type: 'info' | 'warning' | 'error' | 'debug';
  message: string;
  data?: unknown;
}

export interface NodeExecutionResult {
  nodeInstanceId: string;
  status: ExecutionStatus;
  input?: unknown;
  output?: unknown;
  llmResponse?: {
    rawResponse: string;
    parsedOutput: unknown;
    tokensUsed: number;
  };
  logs: NodeExecutionLog[];
  startedAt?: string;
  completedAt?: string;
  error?: string;
}

export interface WorkflowExecution {
  id: string;
  workflowId: string;
  status: ExecutionStatus;
  triggerInput?: unknown;
  nodeResults: NodeExecutionResult[];
  finalOutput?: unknown;
  startedAt: string;
  completedAt?: string;
  error?: string;
}

// ============================================
// Common Types
// ============================================

export interface User {
  id: string;
  name: string;
  avatar?: string;
  email: string;
}

// ============================================
// Legacy Types (하위 호환성)
// ============================================

// 이전 NodeDefinition 타입 (팔레트용 - deprecated)
export type NodeCategory =
  | 'trigger'
  | 'action'
  | 'logic'
  | 'transform'
  | 'ai'
  | 'output';

export type DataType =
  | 'string'
  | 'number'
  | 'boolean'
  | 'object'
  | 'array'
  | 'any';

export interface PortDefinition {
  id: string;
  name: string;
  dataType: DataType;
  required?: boolean;
  description?: string;
}

export type FieldType =
  | 'text'
  | 'textarea'
  | 'number'
  | 'select'
  | 'multiselect'
  | 'boolean'
  | 'code'
  | 'condition'
  | 'keyvalue'
  | 'expression'
  | 'json-schema';

export interface FieldOption {
  label: string;
  value: string;
}

export interface ConfigFieldDefinition {
  key: string;
  label: string;
  type: FieldType;
  required?: boolean;
  defaultValue?: unknown;
  placeholder?: string;
  description?: string;
  options?: FieldOption[];
  codeLanguage?: string;
  validation?: {
    min?: number;
    max?: number;
    pattern?: string;
  };
}

export interface NodeDefinition {
  type: string;
  name: string;
  description: string;
  category: NodeCategory;
  icon: string;
  color: string;
  inputs: PortDefinition[];
  outputs: PortDefinition[];
  configFields: ConfigFieldDefinition[];
  defaultConfig: Record<string, unknown>;
}

export type ConditionOperator =
  | 'equals'
  | 'not_equals'
  | 'contains'
  | 'not_contains'
  | 'starts_with'
  | 'ends_with'
  | 'greater_than'
  | 'less_than'
  | 'is_empty'
  | 'is_not_empty'
  | 'regex_match';

export interface ConditionRule {
  id: string;
  field: string;
  operator: ConditionOperator;
  value: string;
}

export interface ConditionGroup {
  id: string;
  logic: 'AND' | 'OR';
  rules: ConditionRule[];
}

export interface ConditionBranch {
  id: string;
  name: string;
  conditions: ConditionGroup[];
  isDefault?: boolean;
}

export interface WorkflowNode {
  id: string;
  definitionType: string;
  name: string;
  position: Position;
  config: Record<string, unknown>;
  branches?: ConditionBranch[];
}

// ============================================
// Chat Assistant Types
// ============================================

export type ChatContextType =
  | { type: 'none' }
  | { type: 'task'; data: TaskCard }
  | { type: 'node'; data: AINode }
  | { type: 'workflow'; data: Workflow }
  | { type: 'document'; data: KnowledgeDocument };

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  context?: ChatContextType;
  timestamp: string;
}

// ============================================
// Chat Mode Types (구조화된 질문 시스템)
// ============================================

export type ChatMode = 'general' | 'taskboard' | 'knowledge' | 'node' | 'workflow';
export type ChatAction = 'create' | 'search' | 'ask' | 'modify' | 'explain';

export interface KnowledgeFilterState {
  category?: string;
  tags?: string[];
  visibleDocIds?: string[];
}

// ─── API Definition ───────────────────────────────────────────────────────────

export interface ApiParam {
  name: string;
  in: 'path' | 'query' | 'header' | 'body';
  type: string;
  required: boolean;
  description: string;
  default?: string;
}

export interface ResponseField {
  field: string;
  type: string;
  description: string;
}

export interface ApiDefinition {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  category: string;
  tags: string[];
  method: string;
  urlTemplate: string;
  headers: Record<string, string>;
  bodyTemplate: string | null;
  authType: 'none' | 'bearer' | 'basic' | 'api_key';
  authConfig: Record<string, any>;
  parameters: ApiParam[];
  responseSchema: {
    fields: ResponseField[];
    example?: any;
  };
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface CreateApiDefinitionData {
  name: string;
  description?: string;
  icon?: string;
  color?: string;
  category?: string;
  tags?: string[];
  method: string;
  urlTemplate: string;
  headers?: Record<string, string>;
  bodyTemplate?: string;
  authType?: string;
  authConfig?: Record<string, any>;
  parameters?: ApiParam[];
  responseSchema?: { fields: ResponseField[]; example?: any };
}

export type UpdateApiDefinitionData = Partial<CreateApiDefinitionData> & { isActive?: boolean };
