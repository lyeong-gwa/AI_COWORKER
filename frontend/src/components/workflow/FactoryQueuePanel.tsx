import { useState, useEffect, useCallback } from 'react';
import { factoryApi } from '../../services/api';
import type { QueueItem } from '../../types';

interface FactoryQueuePanelProps {
  nodeId: string;
  nodeName: string;
  onClose: () => void;
}

const statusConfig: Record<string, { label: string; color: string; dot: string }> = {
  pending: { label: '대기', color: 'text-amber-300 bg-amber-900/40 border-amber-700/50', dot: 'bg-amber-400' },
  processing: { label: '처리중', color: 'text-blue-300 bg-blue-900/40 border-blue-700/50', dot: 'bg-blue-400 animate-pulse' },
  completed: { label: '완료', color: 'text-green-300 bg-green-900/40 border-green-700/50', dot: 'bg-green-400' },
  failed: { label: '실패', color: 'text-red-300 bg-red-900/40 border-red-700/50', dot: 'bg-red-400' },
};

export function FactoryQueuePanel({ nodeId, nodeName, onClose }: FactoryQueuePanelProps) {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [total, setTotal] = useState(0);
  const [pending, setPending] = useState(0);
  const [processing, setProcessing] = useState(0);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);
  const [filterStatus, setFilterStatus] = useState<string | ''>('');

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await factoryApi.getQueue(nodeId, 50);
      setItems(filterStatus ? result.items.filter(i => i.status === filterStatus) : result.items);
      setTotal(result.total);
      setPending(result.pending);
      setProcessing(result.processing);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [nodeId, filterStatus]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000); // 3초마다 자동 갱신
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleClearCompleted = async () => {
    setClearing(true);
    try {
      await factoryApi.clearQueue(nodeId, 'completed');
      await fetchData();
    } catch { /* ignore */ } finally {
      setClearing(false);
    }
  };

  const handleClearAll = async () => {
    if (!confirm('큐의 모든 아이템을 삭제하시겠습니까?')) return;
    setClearing(true);
    try {
      await factoryApi.clearQueue(nodeId);
      await fetchData();
    } catch { /* ignore */ } finally {
      setClearing(false);
    }
  };

  const copyToClipboard = (data: Record<string, unknown>) => {
    navigator.clipboard.writeText(JSON.stringify(data, null, 2));
  };

  return (
    <div className="w-96 bg-gray-800 border-l border-gray-700 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-slate-700 flex items-center justify-center text-xl">
              🏭
            </div>
            <div>
              <div className="text-xs text-blue-300/70 uppercase tracking-wider">입력 큐</div>
              <div className="text-white font-semibold">{nodeName}</div>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl p-1">
            ✕
          </button>
        </div>

        {/* Stats */}
        <div className="flex items-center gap-3 mt-3">
          <div className="flex items-center gap-1">
            <span className="text-amber-400 font-bold text-sm">{pending}</span>
            <span className="text-gray-500 text-xs">대기</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="text-blue-400 font-bold text-sm">{processing}</span>
            <span className="text-gray-500 text-xs">처리중</span>
          </div>
          <div className="text-gray-600 text-xs">총 {total}건</div>
          <div className="flex-1" />
          <div className="flex gap-1">
            <button
              onClick={handleClearCompleted}
              disabled={clearing}
              className="px-2 py-1 bg-gray-700 text-gray-400 rounded text-[10px] hover:bg-gray-600 disabled:opacity-50"
            >
              완료 정리
            </button>
            <button
              onClick={handleClearAll}
              disabled={clearing || total === 0}
              className="px-2 py-1 bg-red-900/30 text-red-400 rounded text-[10px] hover:bg-red-900/50 disabled:opacity-50"
            >
              전체 비우기
            </button>
          </div>
        </div>

        {/* Filter tabs */}
        <div className="flex gap-1 mt-2">
          {['', 'pending', 'processing', 'completed', 'failed'].map((s) => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                filterStatus === s
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
              }`}
            >
              {s === '' ? '전체' : statusConfig[s]?.label || s}
            </button>
          ))}
        </div>
      </div>

      {/* Queue list */}
      <div className="flex-1 overflow-auto p-3 space-y-2">
        {loading && items.length === 0 ? (
          <div className="flex items-center justify-center py-8">
            <div className="w-6 h-6 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-8">
            <div className="text-3xl mb-2">📭</div>
            <p className="text-gray-500 text-sm">큐가 비어있습니다</p>
            <p className="text-gray-600 text-xs mt-1">공장을 실행하면 입력이 여기에 쌓입니다</p>
          </div>
        ) : (
          items.map((item, index) => {
            const cfg = statusConfig[item.status] || statusConfig.pending;
            return (
              <div
                key={item.id}
                className={`bg-gray-900 rounded-lg border overflow-hidden transition-colors ${
                  item.status === 'processing' ? 'border-blue-500/50' : 'border-gray-700'
                }`}
              >
                {/* Item header */}
                <button
                  onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
                  className="w-full px-3 py-2 flex items-center justify-between hover:bg-gray-800/50 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-gray-600 text-[10px] font-mono w-5">#{index + 1}</span>
                    <div className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
                    <span className={`px-1.5 py-0.5 text-[10px] rounded border ${cfg.color}`}>
                      {cfg.label}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-gray-500 text-[10px]">
                      {new Date(item.createdAt).toLocaleString('ko-KR')}
                    </span>
                    <span className="text-gray-500 text-xs">{expandedId === item.id ? '▲' : '▼'}</span>
                  </div>
                </button>

                {/* Expanded data */}
                {expandedId === item.id && (
                  <div className="px-3 pb-3 border-t border-gray-700 space-y-2">
                    {/* Input data */}
                    <div>
                      <div className="flex justify-between items-center mt-2 mb-1">
                        <span className="text-[10px] text-slate-500 uppercase">입력 데이터</span>
                        <button
                          onClick={() => copyToClipboard(item.data)}
                          className="text-[10px] text-gray-500 hover:text-gray-300"
                        >
                          복사
                        </button>
                      </div>
                      <pre className="text-[10px] text-gray-400 bg-gray-950 rounded p-2 overflow-auto max-h-32 whitespace-pre-wrap break-words">
                        {JSON.stringify(item.data, null, 2)}
                      </pre>
                    </div>

                    {/* Result (if completed) */}
                    {item.result && (
                      <div>
                        <div className="flex justify-between items-center mb-1">
                          <span className="text-[10px] text-green-500 uppercase">출력 결과</span>
                          <button
                            onClick={() => copyToClipboard(item.result!)}
                            className="text-[10px] text-gray-500 hover:text-gray-300"
                          >
                            복사
                          </button>
                        </div>
                        <pre className="text-[10px] text-green-400/80 bg-green-950/20 rounded p-2 overflow-auto max-h-32 whitespace-pre-wrap break-words">
                          {JSON.stringify(item.result, null, 2)}
                        </pre>
                      </div>
                    )}

                    {/* Error (if failed) */}
                    {item.error && (
                      <div className="text-[10px] text-red-400 bg-red-950/20 rounded p-2">
                        {item.error}
                      </div>
                    )}

                    {/* Meta */}
                    <div className="flex items-center gap-3 text-[10px] text-gray-600">
                      {item.executionId && <span>실행: {item.executionId}</span>}
                      {item.processedAt && <span>처리: {new Date(item.processedAt).toLocaleString('ko-KR')}</span>}
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-gray-700">
        <button
          onClick={fetchData}
          className="w-full px-3 py-1.5 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600 text-xs transition-colors"
        >
          새로고침
        </button>
      </div>
    </div>
  );
}
