import { useState, useCallback, useRef, useEffect } from 'react';
import { factoryApi } from '../services/api';
import type { WorkflowExecution } from '../services/api';
import { useToast } from '../components/common/Toast';

interface NodeProgress {
  status: string;
  output?: unknown;
  error?: string;
  startTime?: string;
  endTime?: string;
}

export function useFactoryExecution() {
  const { toast } = useToast();
  const [executing, setExecuting] = useState(false);
  const [currentExecution, setCurrentExecution] = useState<WorkflowExecution | null>(null);
  const [nodeProgress, setNodeProgress] = useState<Record<string, NodeProgress>>({});
  const [showExecution, setShowExecution] = useState(false);

  const sseRef = useRef<EventSource | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (sseRef.current) {
        sseRef.current.close();
        sseRef.current = null;
      }
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, []);

  // Poll execution status (fallback)
  const pollExecutionStatus = useCallback(async (executionId: string) => {
    const poll = async () => {
      try {
        const exec = await factoryApi.getExecution(executionId);
        setCurrentExecution(exec);

        if (exec.nodeResults && typeof exec.nodeResults === 'object') {
          const progress: Record<string, NodeProgress> = {};
          for (const [nodeId, result] of Object.entries(exec.nodeResults)) {
            const r = result as Record<string, unknown>;
            progress[nodeId] = {
              status: (r.status as string) || 'pending',
              output: r.outputData,
              error: r.error as string | undefined,
              startTime: r.startTime as string | undefined,
              endTime: r.endTime as string | undefined,
            };
          }
          setNodeProgress(progress);
        }

        if (exec.status === 'completed' || exec.status === 'failed' || exec.status === 'cancelled') {
          setExecuting(false);
          if (exec.status === 'completed') toast.success('실행 완료');
          else if (exec.status === 'failed') toast.error(`실행 실패: ${exec.errorMessage || '알 수 없는 오류'}`);
        } else {
          pollTimerRef.current = setTimeout(poll, 1500);
        }
      } catch {
        setExecuting(false);
      }
    };
    poll();
  }, [toast]);

  // Execute factory
  const execute = useCallback(async (inputData: Record<string, unknown> = {}, triggerNodeId?: string) => {
    setExecuting(true);
    setShowExecution(true);
    setNodeProgress({});
    setCurrentExecution(null);

    try {
      // Include trigger node ID in input data for backend routing
      const finalInputData = triggerNodeId
        ? { ...inputData, _triggerNodeId: triggerNodeId }
        : inputData;
      const execution = await factoryApi.execute(finalInputData);
      setCurrentExecution(execution);

      // Try SSE streaming
      try {
        const es = factoryApi.streamExecution(execution.id);
        sseRef.current = es;

        es.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);

            if (data.status) {
              setCurrentExecution(prev => prev ? {
                ...prev,
                status: data.status,
                completedAt: data.completedAt,
                errorMessage: data.error,
              } : prev);
            }

            if (data.nodeResults && typeof data.nodeResults === 'object') {
              const progress: Record<string, NodeProgress> = {};
              for (const [nodeId, result] of Object.entries(data.nodeResults)) {
                const r = result as Record<string, unknown>;
                progress[nodeId] = {
                  status: (r.status as string) || 'pending',
                  output: r.outputData,
                  error: r.error as string | undefined,
                  startTime: r.startTime as string | undefined,
                  endTime: r.endTime as string | undefined,
                };
              }
              setNodeProgress(progress);
            }

            if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
              es.close();
              sseRef.current = null;
              setExecuting(false);
              if (data.status === 'completed') toast.success('실행 완료');
              else if (data.status === 'failed') toast.error(`실행 실패: ${data.error || '알 수 없는 오류'}`);
            }
          } catch {
            // Ignore SSE parse errors
          }
        };

        es.onerror = () => {
          es.close();
          sseRef.current = null;
          pollExecutionStatus(execution.id);
        };
      } catch {
        pollExecutionStatus(execution.id);
      }
    } catch (err) {
      const detail = err instanceof Error ? err.message : '';
      toast.error(`실행 실패${detail ? `: ${detail}` : ''}`);
      setExecuting(false);
    }
  }, [toast, pollExecutionStatus]);

  return {
    executing,
    currentExecution,
    nodeProgress,
    showExecution,
    setShowExecution,
    execute,
  };
}
