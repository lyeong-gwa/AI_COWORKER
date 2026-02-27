import { useState, useCallback, useRef, useEffect } from 'react';
import { factoryApi, nodeApi } from '../services/api';
import type { FactoryMapUpdateData } from '../services/api';
import type { Workflow, AINode } from '../types';
import { useToast } from '../components/common/Toast';

export function useFactoryMap() {
  const { toast } = useToast();
  const [factoryMap, setFactoryMap] = useState<Workflow | null>(null);
  const [aiNodes, setAiNodes] = useState<AINode[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState<string | undefined>();
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  // Auto-save debounce
  const autoSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingSaveRef = useRef<FactoryMapUpdateData | null>(null);

  // Load factory map and AI nodes
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [map, nodes] = await Promise.all([
        factoryApi.getMap(),
        nodeApi.list(),
      ]);
      setFactoryMap(map);
      setAiNodes(nodes);
    } catch {
      // Fallback - create empty state
      setFactoryMap(null);
      setAiNodes([]);
      toast.info('백엔드 연결 대기중...');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Save factory map (canvas is source of truth — don't overwrite local state with response)
  const saveMap = useCallback(async (data: FactoryMapUpdateData) => {
    // Cancel pending auto-save to avoid race condition
    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
      autoSaveTimerRef.current = null;
    }
    pendingSaveRef.current = null;

    setSaving(true);
    try {
      await factoryApi.saveMap(data);
      setHasUnsavedChanges(false);
      setLastSaved(new Date().toISOString());
    } catch (err) {
      const detail = err instanceof Error ? err.message : '';
      toast.error(`저장 실패${detail ? `: ${detail}` : ''}`);
      throw err;
    } finally {
      setSaving(false);
    }
  }, [toast]);

  // Auto-save with 2s debounce
  const scheduleAutoSave = useCallback((data: FactoryMapUpdateData) => {
    pendingSaveRef.current = data;
    setHasUnsavedChanges(true);

    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
    }

    autoSaveTimerRef.current = setTimeout(async () => {
      const saveData = pendingSaveRef.current;
      if (saveData) {
        try {
          await saveMap(saveData);
        } catch {
          // Already toasted in saveMap
        }
        pendingSaveRef.current = null;
      }
    }, 2000);
  }, [saveMap]);

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (autoSaveTimerRef.current) {
        clearTimeout(autoSaveTimerRef.current);
      }
    };
  }, []);

  return {
    factoryMap,
    aiNodes,
    loading,
    saving,
    lastSaved,
    hasUnsavedChanges,
    loadData,
    saveMap,
    scheduleAutoSave,
  };
}
