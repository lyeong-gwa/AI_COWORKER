import type {
  TaskCard,
  TaskColumn,
  KnowledgeDocument,
  AINode,
  Workflow,
  User,
  ToolDefinition,
} from '../types';

// ============================================
// Users
// ============================================

export const mockUsers: User[] = [];

// ============================================
// Task Board Data
// ============================================

export const mockTasks: TaskCard[] = [];

export const mockColumns: TaskColumn[] = [
  {
    id: 'col-1',
    title: 'Backlog',
    status: 'backlog',
    cards: mockTasks.filter((t) => t.status === 'backlog'),
  },
  {
    id: 'col-2',
    title: 'To Do',
    status: 'todo',
    cards: mockTasks.filter((t) => t.status === 'todo'),
  },
  {
    id: 'col-3',
    title: 'In Progress',
    status: 'in-progress',
    cards: mockTasks.filter((t) => t.status === 'in-progress'),
  },
  {
    id: 'col-4',
    title: 'Review',
    status: 'review',
    cards: mockTasks.filter((t) => t.status === 'review'),
  },
  {
    id: 'col-5',
    title: 'Done',
    status: 'done',
    cards: mockTasks.filter((t) => t.status === 'done'),
  },
];

// ============================================
// Knowledge Base Data
// ============================================

export const mockDocuments: KnowledgeDocument[] = [];

// ============================================
// Tool Definitions (라이브러리 – 중앙 관리용 도구)
// ============================================

export const mockToolDefinitions: ToolDefinition[] = [];

// Helper: 도구 타입으로 필터링
export function getToolDefinitionsByType(type: string): ToolDefinition[] {
  return mockToolDefinitions.filter(t => t.type === type);
}

// Helper: 도구 ID로 찾기
export function getToolDefinitionById(id: string): ToolDefinition | undefined {
  return mockToolDefinitions.find(t => t.id === id);
}

// ============================================
// AI Nodes (재사용 가능한 LLM 노드)
// ============================================

export const mockAINodes: AINode[] = [];

// ============================================
// Workflows (AI 노드 기반)
// ============================================

export const mockWorkflows: Workflow[] = [];

// Helper: 노드 ID로 AINode 찾기
export function getAINodeById(nodeId: string): AINode | undefined {
  return mockAINodes.find(node => node.id === nodeId);
}

// Helper: 워크플로우 ID로 Workflow 찾기
export function getWorkflowById(workflowId: string): Workflow | undefined {
  return mockWorkflows.find(wf => wf.id === workflowId);
}
