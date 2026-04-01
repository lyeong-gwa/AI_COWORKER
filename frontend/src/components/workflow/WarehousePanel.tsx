import { useState, useEffect, useCallback } from 'react';
import { factoryApi } from '../../services/api';
import type { WarehouseEntry } from '../../types';
import { WarehouseDataModal } from './WarehouseDataModal';

interface WarehousePanelProps {
  nodeId: string;
  nodeName: string;
  onUpdateName?: (name: string) => void;
  onClose: () => void;
}

export function WarehousePanel({ nodeId, nodeName, onUpdateName, onClose }: WarehousePanelProps) {
  const [entries, setEntries] = useState<WarehouseEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [modalEntry, setModalEntry] = useState<WarehouseEntry | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await factoryApi.getWarehouse(nodeId, 50);
      setEntries(result.items);
      setTotal(result.total);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [nodeId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Clear selection when entries change
  useEffect(() => {
    setSelectedIds(new Set());
  }, [entries]);

  const handleClearAll = async () => {
    if (!confirm('창고의 모든 데이터를 삭제하시겠습니까?')) return;
    setClearing(true);
    try {
      await factoryApi.clearWarehouse(nodeId);
      setEntries([]);
      setTotal(0);
    } catch {
      // ignore
    } finally {
      setClearing(false);
    }
  };

  const handleDeleteSelected = async () => {
    if (selectedIds.size === 0) return;
    setClearing(true);
    try {
      await factoryApi.deleteWarehouseEntries(nodeId, Array.from(selectedIds));
      setEntries((prev) => prev.filter((e) => !selectedIds.has(e.id)));
      setTotal((prev) => prev - selectedIds.size);
      setSelectedIds(new Set());
    } catch {
      // ignore
    } finally {
      setClearing(false);
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === entries.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(entries.map((e) => e.id)));
    }
  };

  const copyToClipboard = (data: Record<string, unknown>) => {
    navigator.clipboard.writeText(JSON.stringify(data, null, 2));
  };

  const isAllSelected = entries.length > 0 && selectedIds.size === entries.length;

  return (
    <div className="w-96 bg-gray-800 border-l border-gray-700 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-emerald-900 flex items-center justify-center text-xl">
              📦
            </div>
            <div>
              <div className="text-xs text-emerald-300/70 uppercase tracking-wider">창고</div>
              <input
                type="text"
                value={nodeName}
                onChange={(e) => onUpdateName?.(e.target.value)}
                className="bg-transparent text-white font-semibold text-sm border-none outline-none w-full"
                placeholder="이름 입력..."
              />
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl p-1">
            ✕
          </button>
        </div>
        <div className="flex items-center justify-between mt-3">
          <span className="text-gray-400 text-xs">{total}개 데이터 보관중</span>
          <div className="flex items-center gap-1.5">
            {selectedIds.size > 0 ? (
              <button
                onClick={handleDeleteSelected}
                disabled={clearing}
                className="px-2 py-1 bg-red-900/30 text-red-400 rounded text-xs hover:bg-red-900/50 disabled:opacity-50 transition-colors"
              >
                {clearing ? '삭제 중...' : `${selectedIds.size}개 선택 삭제`}
              </button>
            ) : (
              <button
                onClick={handleClearAll}
                disabled={clearing || total === 0}
                className="px-2 py-1 bg-red-900/30 text-red-400 rounded text-xs hover:bg-red-900/50 disabled:opacity-50 transition-colors"
              >
                {clearing ? '삭제 중...' : '전체 비우기'}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Select all bar */}
      {entries.length > 0 && (
        <div className="px-4 py-1.5 border-b border-gray-700/50 flex items-center gap-2">
          <input
            type="checkbox"
            checked={isAllSelected}
            onChange={toggleSelectAll}
            className="w-3.5 h-3.5 rounded border-gray-600 bg-gray-900 text-emerald-500 focus:ring-emerald-500 cursor-pointer"
          />
          <span className="text-gray-500 text-[11px]">
            {selectedIds.size > 0 ? `${selectedIds.size}개 선택됨` : '전체 선택'}
          </span>
        </div>
      )}

      {/* Data list */}
      <div className="flex-1 overflow-auto p-3 space-y-2">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <div className="w-6 h-6 border-2 border-emerald-500/30 border-t-emerald-500 rounded-full animate-spin" />
          </div>
        ) : entries.length === 0 ? (
          <div className="text-center py-8">
            <div className="text-3xl mb-2">📭</div>
            <p className="text-gray-500 text-sm">아직 데이터가 없습니다</p>
            <p className="text-gray-600 text-xs mt-1">공장을 실행하면 결과가 여기에 쌓입니다</p>
          </div>
        ) : (
          entries.map((entry) => (
            <div
              key={entry.id}
              className={`bg-gray-900 rounded-lg border overflow-hidden transition-colors ${
                selectedIds.has(entry.id) ? 'border-emerald-500/50 bg-emerald-950/20' : 'border-gray-700'
              }`}
            >
              {/* Entry header */}
              <div className="flex items-center">
                <label
                  className="flex items-center pl-3 py-2 cursor-pointer"
                  onClick={(e) => e.stopPropagation()}
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.has(entry.id)}
                    onChange={() => toggleSelect(entry.id)}
                    className="w-3.5 h-3.5 rounded border-gray-600 bg-gray-900 text-emerald-500 focus:ring-emerald-500 cursor-pointer"
                  />
                </label>
                <button
                  onClick={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
                  className="flex-1 px-2 py-2 flex items-center justify-between hover:bg-gray-800/50 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                    <span className="text-gray-300 text-xs font-mono">{entry.id}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-gray-500 text-[10px]">
                      {new Date(entry.createdAt).toLocaleString('ko-KR')}
                    </span>
                    <span className="text-gray-500 text-xs">{expandedId === entry.id ? '▲' : '▼'}</span>
                  </div>
                </button>
              </div>

              {/* Expanded data */}
              {expandedId === entry.id && (
                <div className="px-3 pb-3 border-t border-gray-700">
                  <div className="flex justify-end gap-2 mb-1">
                    <button
                      onClick={() => setModalEntry(entry)}
                      className="text-[10px] text-emerald-500 hover:text-emerald-300 transition-colors"
                    >
                      🔍 상세보기
                    </button>
                    <button
                      onClick={() => copyToClipboard(entry.data)}
                      className="text-[10px] text-gray-500 hover:text-gray-300"
                    >
                      📋 복사
                    </button>
                  </div>
                  <pre className="text-[10px] text-gray-400 bg-gray-950 rounded p-2 overflow-auto max-h-48 whitespace-pre-wrap break-words">
                    {JSON.stringify(entry.data, null, 2)}
                  </pre>
                  {entry.executionId && (
                    <div className="mt-1 text-[10px] text-gray-600">
                      실행: {entry.executionId}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-gray-700">
        <button
          onClick={fetchData}
          className="w-full px-3 py-1.5 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600 text-xs transition-colors"
        >
          🔄 새로고침
        </button>
      </div>

      {/* Detail Modal */}
      <WarehouseDataModal
        entry={modalEntry}
        onClose={() => setModalEntry(null)}
      />
    </div>
  );
}
