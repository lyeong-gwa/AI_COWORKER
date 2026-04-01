import type {
  KnowledgeDocument,
  AINode,
  Workflow,
  User,
} from '../types';

// ============================================
// Users
// ============================================

export const mockUsers: User[] = [];

// ============================================
// Knowledge Base Data
// ============================================

export const mockDocuments: KnowledgeDocument[] = [];

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
