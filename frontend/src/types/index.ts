// ============================================
// Knowledge Base Types
// 문서 1개 = 청크 1개 (1:1 매핑)
// ============================================

// Karpathy v2: 5종 page_type enum
export type PageType = 'Summary' | 'Entity' | 'Concept' | 'Comparison' | 'Synthesis';

export interface KnowledgeDocument {
  id: string;
  title: string;
  content: string;
  source?: string;
  category: string;
  service: string;
  tags: string[];
  // Karpathy v2 신규 필드
  pageType?: PageType;
  version?: number;
  links?: string[];
  rawSourceId?: string | null;
  contentHash?: string;
  syncStatus: 'synced' | 'modified' | 'not_synced';
  createdAt: string;
  updatedAt: string;
}

// Multi-service 확장 (Phase 3)
export interface KnowledgeService {
  id: string;
  title: string;
  description: string;
}

// Karpathy v2: 그래프 응답
export interface KnowledgeGraphNode {
  id: string;
  title: string;
  pageType: PageType;
  category: string;
  service: string;
  backlinks_count?: number;
  // Phase 2 신규
  community: number;
  godScore: number;
  degree: number;
}

export interface KnowledgeGraphEdge {
  from: string;
  to: string;
  is_broken?: boolean;
  crossService?: boolean;
  // Phase 2 신규
  kind: 'explicit' | 'implicit';
  weight: number;
  similarity: number | null;
}

// Phase 2 신규
export interface KnowledgeCommunity {
  id: number;
  label: string;
  size: number;
  color?: string;
}

export interface KnowledgeGraphMeta {
  implicitThreshold: number;
  implicitMaxPerPage: number;
  explicitEdgeCount: number;
  implicitEdgeCount: number;
  communityCount: number;
}

export interface KnowledgeGraphResponse {
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
  // Phase 2 신규
  communities: KnowledgeCommunity[];
  meta: KnowledgeGraphMeta;
}

// Phase 2 신규: 엣지 상세 (GET /api/v1/knowledge/edge)
export interface KnowledgeEdgeDetail {
  from: KnowledgeDocument;
  to: KnowledgeDocument;
  edge: {
    kind: 'explicit' | 'implicit';
    weight: number;
    similarity: number | null;
    isBroken: boolean;
    crossService: boolean;
    fromToExplicit: boolean;
    toFromExplicit: boolean;
  } | null;
}

// Karpathy v2: Lint 보고서 (백엔드 실제 응답 shape)
export interface LintReport {
  report_path: string;
  history_path?: string;
  summary: {
    // 백엔드가 실제 반환하는 필드명
    errors?: number;
    warnings?: number;
    info?: number;
    llm_calls?: number;
    estimated_cost_usd?: number;
    // 계획서 기준 필드명 (alias)
    error_count?: number;
    warning_count?: number;
    info_count?: number;
  };
  // 섹션별 항목 배열
  duplicates?: unknown[];
  contradictions?: unknown[];
  orphans?: unknown[];
  outdated?: unknown[];
  broken_links?: unknown[];
  schema_violations?: unknown[];
  report_markdown?: string;
}

// Karpathy v2: Index rebuild 응답
export interface IndexRebuildResponse {
  rebuilt: string[];
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

// 워크플로우 내 노드 인스턴스
export interface WorkflowNodeInstance {
  id: string;                     // 인스턴스 ID
  nodeId: string;                 // AINode.id 참조
  definitionType?: string;        // "ai-custom" | "manual" | "schedule" | "form"
  aiNodeId?: string;              // AINode reference ID
  name: string;                   // 인스턴스 이름 (기본값: AINode.name)
  orderIndex?: number;            // 형제 노드 안정 순번 (자동 레이아웃 tie-break)

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

  // 스케줄 설정 (Phase B)
  scheduleConfig?: WorkflowScheduleConfig;

  // 메타데이터
  tags: string[];
  createdBy?: string;              // 'cli' | 'web'
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
  nodeInstanceId?: string;
  status?: ExecutionStatus | string;
  /** legacy 키 (input). 백엔드는 inputData/outputData 를 보내므로 양쪽 모두 호환 */
  input?: unknown;
  output?: unknown;
  /** 백엔드 응답 표준 키 (warehouse.py 응답 변환) */
  inputData?: unknown;
  outputData?: unknown;
  /** 백엔드 응답에 포함된 노드 정의 타입 (예: 'ai-custom') */
  definitionType?: string;
  llmResponse?: {
    rawResponse: string;
    parsedOutput: unknown;
    tokensUsed: number;
  };
  logs?: NodeExecutionLog[];
  /** 백엔드는 startTime/endTime 으로 보냄 — 양쪽 모두 호환 */
  startedAt?: string;
  completedAt?: string;
  startTime?: string;
  endTime?: string;
  error?: string;
}

export interface WorkflowExecution {
  id: string;
  workflowId: string;
  status: ExecutionStatus;
  triggerInput?: unknown;
  /**
   * P-1 / C-1 정정: backend `app/models/workflow.py:192` 는 `Mapped[Dict[str, Any]]`,
   * 응답 변환 `app/api/routes/warehouse.py:98` 도 dict 그대로 반환한다.
   * 이전 `NodeExecutionResult[]` (배열) 은 잘못된 타입이었음.
   */
  nodeResults: Record<string, NodeExecutionResult>;
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
  orderIndex?: number;
  config: Record<string, unknown>;
  branches?: ConditionBranch[];
}

// ============================================
// Chat Assistant Types
// ============================================

export type ChatContextType =
  | { type: 'none' }
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

export type ChatMode = 'general' | 'knowledge' | 'node' | 'workflow';
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

// ─── InstanceDB (Phase A: 1급 자원 — 동질 record 컬렉션) ─────────────────────
//
// 지식문서가 사람이 RAG용으로 등록하는 컬렉션이라면, 인스턴스DB는 워크플로우가
// 자동 누적하는 동질 데이터셋이다. 메타(InstanceDB)는 JSON Schema 를 갖고,
// 그 스키마를 통과한 record(InstanceDBRecord)들이 누적된다.
// Phase D (UI) 에서 사용 예정.

/** 필드별 렌더러 힌트. key = record.data 의 필드명, value = 렌더러 타입 */
export type ViewerHintType = 'markdown' | 'text' | 'tag' | 'code' | 'json';

export interface InstanceDB {
  id: string;
  name: string;
  description?: string | null;
  tags: string[];
  viewerHints: Record<string, string>;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
}

export interface InstanceDBRecord {
  id: string;
  instanceDbId: string;
  data: Record<string, unknown>;
  sourceWarehouseId?: string | null;
  sourceWorkflowId?: string | null;
  sourceExecutionId?: string | null;
  createdAt: string;
}

export interface CreateInstanceDBData {
  name: string;
  description?: string;
  tags?: string[];
  viewerHints?: Record<string, string>;
}

export type UpdateInstanceDBData = Partial<CreateInstanceDBData>;

export interface InstanceDBRecordListResponse {
  items: InstanceDBRecord[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Workflow Schedule Types (Phase B) ───────────────────────────────────────

export interface WorkflowScheduleConfig {
  enabled: boolean;
  cronExpr: string;
  timezone: string;
}

export interface WorkflowScheduleUpdateResponse {
  workflowId: string;
  scheduleConfig: WorkflowScheduleConfig;
  nextRunTime?: string | null;
}

export interface WorkflowScheduleNextRun {
  workflowId: string;
  nextRunTime: string | null;
  registered: boolean;
}

// ─── Workflow Delete Preview ──────────────────────────────────────────────────

export interface WorkflowDeletePreview {
  workflowId: string;
  workflowName: string;
  instanceCount: number;
  warehouseEntryCount: number;
  nodeResultCount: number;
  willCascadeDelete: boolean;
}
