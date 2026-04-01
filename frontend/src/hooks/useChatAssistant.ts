import { useCallback } from 'react';
import { useChatContext } from '../contexts/ChatContext';
import type { AINode, Workflow, KnowledgeDocument } from '../types';

/**
 * Convenience hook for setting chat context from different pages.
 * Context is set silently — user opens chat manually when needed.
 */
export function useChatAssistant() {
  const { setContext, clearContext, setMode, setAction, setKnowledgeFilter } = useChatContext();

  const setNodeContext = useCallback((node: AINode) => {
    setContext({ type: 'node', data: node });
  }, [setContext]);

  const setWorkflowContext = useCallback((workflow: Workflow) => {
    setContext({ type: 'workflow', data: workflow });
  }, [setContext]);

  const setDocumentContext = useCallback((document: KnowledgeDocument) => {
    setContext({ type: 'document', data: document });
  }, [setContext]);

  return {
    setNodeContext,
    setWorkflowContext,
    setDocumentContext,
    clearContext,
    setMode,
    setAction,
    setKnowledgeFilter,
  };
}
