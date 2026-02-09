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
  filename: string;
  title: string;
  content: string;
  summary?: string;
  source?: string;
  category: string;
  // 벡터 DB 동기화 정보 (문서 전체가 하나의 청크)
  vectorId?: string;       // 벡터 DB 내 ID
  syncStatus: 'synced' | 'pending' | 'error';
  lastSyncedAt?: string;
  tokenCount?: number;     // 토큰 수 (청크 크기 참고용)
  createdAt: string;
  updatedAt: string;
  tags: string[];
  // 메타데이터 (필터링용)
  metadata?: Record<string, unknown>;
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

// --- 도구 정의 ---
export type ToolType = 'api_call' | 'file_read' | 'file_write' | 'code_execute' | 'database_query';

export interface ApiCallTool {
  type: 'api_call';
  id: string;
  name: string;
  description: string;
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  urlTemplate: string;              // {{input.baseUrl}}/api/tickets 형식
  headers?: Record<string, string>;
  bodyTemplate?: string;            // JSON 템플릿
  responseMapping?: string;         // 응답에서 추출할 경로 (예: "data.items")
}

export interface FileReadTool {
  type: 'file_read';
  id: string;
  name: string;
  description: string;
  pathTemplate: string;
  encoding?: string;
}

export interface FileWriteTool {
  type: 'file_write';
  id: string;
  name: string;
  description: string;
  pathTemplate: string;
  contentTemplate: string;
}

export interface CodeExecuteTool {
  type: 'code_execute';
  id: string;
  name: string;
  description: string;
  language: 'javascript' | 'python';
  code: string;
}

export interface DatabaseQueryTool {
  type: 'database_query';
  id: string;
  name: string;
  description: string;
  queryTemplate: string;
}

export type NodeTool = ApiCallTool | FileReadTool | FileWriteTool | CodeExecuteTool | DatabaseQueryTool;

// ─── Tool Library (중앙 관리용 도구 정의) ────────────────────────────────────

/** 타입별 설정 객체 (라이브러리 저장용 – id/name/description 중복 없이 config만) */
export interface ApiCallConfig {
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  urlTemplate: string;
  headers?: Record<string, string>;
  bodyTemplate?: string;
  responseMapping?: string;
  auth?: { type: 'bearer' | 'basic' | 'api_key'; value: string };
}

export interface FileReadConfig {
  pathTemplate: string;
  encoding?: string;
  parser: 'text' | 'json' | 'csv';
}

export interface FileWriteConfig {
  pathTemplate: string;
  contentTemplate: string;
}

export interface CodeExecuteConfig {
  language: 'javascript' | 'python';
  code: string;
}

export interface DatabaseQueryConfig {
  connectionId?: string;
  queryTemplate: string;
}

export type ToolConfig =
  | ApiCallConfig
  | FileReadConfig
  | FileWriteConfig
  | CodeExecuteConfig
  | DatabaseQueryConfig;

/** 라이브러리에 저장되는 재사용 가능한 도구 정의 */
export interface ToolDefinition {
  id: string;
  name: string;
  description: string;
  type: ToolType;
  icon: string;
  color: string;                // Tailwind bg-* class
  tags: string[];
  config: ToolConfig;
  createdAt: string;
  updatedAt: string;
}

/** 노드 내부에서 도구를 참조하는 방식 */
export interface NodeToolReference {
  mode: 'library' | 'embedded';
  toolId?: string;              // mode === 'library'일 때 ToolDefinition.id
  embeddedTool?: NodeTool;      // mode === 'embedded'일 때 인라인 도구
}

// --- 지식 베이스 필터 ---
export interface KnowledgeFilterCondition {
  field: 'tag' | 'metadata';
  key?: string;                   // metadata 필드명
  operator: 'equals' | 'contains' | 'in' | 'not_in';
  value: string | string[];
}

export interface KnowledgeConfig {
  enabled: boolean;
  filters: KnowledgeFilterCondition[];
  maxChunks: number;              // 최대 청크 수
  includeInPrompt: boolean;       // 프롬프트에 자동 포함 여부
  promptTemplate?: string;        // 지식 삽입 템플릿 (예: "관련 지식:\n{{knowledge}}")
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

  // 도구 설정 (라이브러리 참조 방식 - 읽기 전용)
  linkedToolIds: string[];          // ToolDefinition.id 참조 목록
  tools: NodeTool[];                // deprecated - 하위 호환용
  toolRefs?: NodeToolReference[];   // deprecated

  // 지식 베이스 설정
  knowledge: KnowledgeConfig;

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

  // 후처리 설정
  outputMapping?: string;         // LLM 응답에서 output 매핑 코드/표현식

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
  name: string;                   // 인스턴스 이름 (기본값: AINode.name)
  position: Position;

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
    type: 'manual' | 'schedule' | 'webhook' | 'event';
    config: Record<string, unknown>;
  };

  // 메타데이터
  tags: string[];
  createdAt: string;
  updatedAt: string;
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
  toolResults?: Array<{
    toolId: string;
    toolName: string;
    result: unknown;
    error?: string;
  }>;
  knowledgeUsed?: Array<{
    documentId: string;
    title: string;
    relevanceScore: number;
  }>;
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
  | 'json-schema'
  | 'tool-list'
  | 'knowledge-filter';

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
  | { type: 'tool'; data: ToolDefinition }
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
