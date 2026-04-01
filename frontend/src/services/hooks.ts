/**
 * API 데이터 패칭 훅
 *
 * 로딩, 에러, 리페치 상태 관리
 */

import { useState, useEffect, useCallback } from 'react';
import {
  knowledgeApi,
  nodeApi,
  workflowApi,
  apiDefinitionApi,
  ApiError,
} from './api';
import type {
  KnowledgeDocument,
  AINode,
  Workflow,
  ApiDefinition,
} from '../types';
import type { WorkflowSummary, WorkflowExecution } from './api';

// ─────────────────────────────────────────────────────────────────────────────
// 공통 타입
// ─────────────────────────────────────────────────────────────────────────────

interface UseQueryResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}


// ─────────────────────────────────────────────────────────────────────────────
// Knowledge 훅
// ─────────────────────────────────────────────────────────────────────────────

export function useKnowledgeDocuments(category?: string): UseQueryResult<KnowledgeDocument[]> {
  const [data, setData] = useState<KnowledgeDocument[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await knowledgeApi.list(category);
      setData(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '데이터를 불러오는데 실패했습니다');
    } finally {
      setLoading(false);
    }
  }, [category]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { data, loading, error, refetch: fetch };
}

// ─────────────────────────────────────────────────────────────────────────────
// Node 훅
// ─────────────────────────────────────────────────────────────────────────────

export function useNodes(category?: string): UseQueryResult<AINode[]> {
  const [data, setData] = useState<AINode[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await nodeApi.list(category);
      setData(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '데이터를 불러오는데 실패했습니다');
    } finally {
      setLoading(false);
    }
  }, [category]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { data, loading, error, refetch: fetch };
}

export function useNode(id: string | null): UseQueryResult<AINode> {
  const [data, setData] = useState<AINode | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const result = await nodeApi.get(id);
      setData(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '데이터를 불러오는데 실패했습니다');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { data, loading, error, refetch: fetch };
}

// ─────────────────────────────────────────────────────────────────────────────
// Workflow 훅
// ─────────────────────────────────────────────────────────────────────────────

export function useWorkflows(): UseQueryResult<WorkflowSummary[]> {
  const [data, setData] = useState<WorkflowSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await workflowApi.list();
      setData(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '데이터를 불러오는데 실패했습니다');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { data, loading, error, refetch: fetch };
}

export function useWorkflow(id: string | null): UseQueryResult<Workflow> {
  const [data, setData] = useState<Workflow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const result = await workflowApi.get(id);
      setData(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '데이터를 불러오는데 실패했습니다');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { data, loading, error, refetch: fetch };
}

export function useWorkflowExecutions(workflowId: string | null): UseQueryResult<WorkflowExecution[]> {
  const [data, setData] = useState<WorkflowExecution[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    if (!workflowId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await workflowApi.listExecutions(workflowId);
      setData(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '데이터를 불러오는데 실패했습니다');
    } finally {
      setLoading(false);
    }
  }, [workflowId]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { data, loading, error, refetch: fetch };
}

// ─────────────────────────────────────────────────────────────────────────────
// API Definition 훅
// ─────────────────────────────────────────────────────────────────────────────

export function useApiDefinitions() {
  const [apiDefs, setApiDefs] = useState<ApiDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiDefinitionApi.list()
      .then(setApiDefs)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return { apiDefs, loading, error, refetch: () => {
    setLoading(true);
    apiDefinitionApi.list()
      .then(setApiDefs)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }};
}

// ─────────────────────────────────────────────────────────────────────────────
// 연결 상태 확인 훅
// ─────────────────────────────────────────────────────────────────────────────

import { healthApi } from './api';

export function useApiHealth() {
  const [connected, setConnected] = useState<boolean | null>(null);
  const [checking, setChecking] = useState(true);

  const check = useCallback(async () => {
    setChecking(true);
    try {
      await healthApi.check();
      setConnected(true);
    } catch {
      setConnected(false);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    check();
    // 30초마다 연결 상태 확인
    const interval = setInterval(check, 30000);
    return () => clearInterval(interval);
  }, [check]);

  return { connected, checking, recheck: check };
}
