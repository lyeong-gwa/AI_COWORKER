import { useState, useEffect } from 'react';
import { factoryApi } from '../../services/api';
import type { WorkflowExecution } from '../../services/api';

interface ExecutionPanelProps {
  /** Currently running execution */
  currentExecution: WorkflowExecution | null;
  /** Real-time node progress from SSE */
  nodeProgress: Record<string, { status: string; output?: unknown; error?: string; startTime?: string; endTime?: string }>;
  onClose: () => void;
}

const statusColors: Record<string, string> = {
  pending: 'bg-gray-600 text-gray-300',
  running: 'bg-blue-600 text-blue-100',
  completed: 'bg-green-600 text-green-100',
  failed: 'bg-red-600 text-red-100',
  cancelled: 'bg-yellow-600 text-yellow-100',
};

const statusLabels: Record<string, string> = {
  pending: '대기',
  running: '실행중',
  completed: '완료',
  failed: '실패',
  cancelled: '취소',
};

export function ExecutionPanel({ currentExecution, nodeProgress, onClose }: ExecutionPanelProps) {
  const [history, setHistory] = useState<WorkflowExecution[]>([]);
  const [showHistory, setShowHistory] = useState(!currentExecution);
  const [expandedExec, setExpandedExec] = useState<string | null>(null);

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const execs = await factoryApi.listExecutions(20);
        setHistory(execs);
      } catch {
        // ignore
      }
    };
    fetchHistory();
  }, [currentExecution?.status]);

  const progressEntries = Object.entries(nodeProgress);

  return (
    <div className="border-t border-gray-700 bg-gray-900 max-h-[300px] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-700 flex-shrink-0">
        <div className="flex items-center gap-3">
          <h4 className="text-sm font-semibold text-white">
            {showHistory ? '실행 이력' : '실행 상태'}
          </h4>
          {currentExecution && (
            <span className={`px-2 py-0.5 text-xs rounded ${statusColors[currentExecution.status] || 'bg-gray-600 text-gray-300'}`}>
              {statusLabels[currentExecution.status] || currentExecution.status}
            </span>
          )}
          {currentExecution?.status === 'running' && (
            <div className="w-3 h-3 border-2 border-blue-400/30 border-t-blue-400 rounded-full animate-spin" />
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="text-xs text-gray-400 hover:text-gray-200 px-2 py-1 rounded bg-gray-800"
          >
            {showHistory ? '현재 실행' : '이력 보기'}
          </button>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-sm px-1">
            ✕
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto px-4 py-3">
        {!showHistory ? (
          /* Current execution progress */
          <div className="flex gap-3 overflow-x-auto pb-2">
            {progressEntries.length === 0 ? (
              <p className="text-gray-500 text-sm">실행 정보 없음</p>
            ) : (
              progressEntries.map(([nodeId, prog]) => (
                <div key={nodeId} className="flex-shrink-0 bg-gray-800 border border-gray-700 rounded-lg p-3 min-w-[180px] max-w-[280px]">
                  <div className="flex items-center gap-2 mb-2">
                    <div className={`w-2 h-2 rounded-full ${
                      prog.status === 'running' ? 'bg-blue-400 animate-pulse'
                      : prog.status === 'completed' ? 'bg-green-400'
                      : prog.status === 'failed' ? 'bg-red-400'
                      : 'bg-gray-500'
                    }`} />
                    <span className="text-white text-xs font-medium truncate">{nodeId}</span>
                  </div>
                  <span className={`px-2 py-0.5 text-[10px] rounded ${statusColors[prog.status] || 'bg-gray-600 text-gray-300'}`}>
                    {statusLabels[prog.status] || prog.status}
                  </span>
                  {prog.error && <p className="text-red-400 text-[10px] mt-1 break-words">{prog.error}</p>}
                  {!!prog.output && (
                    <details className="mt-2">
                      <summary className="text-gray-400 text-[10px] cursor-pointer">출력</summary>
                      <pre className="mt-1 text-[10px] text-gray-400 bg-gray-900 rounded p-1.5 overflow-auto max-h-24 whitespace-pre-wrap break-words">
                        {JSON.stringify(prog.output, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
              ))
            )}
          </div>
        ) : (
          /* Execution history */
          <div className="space-y-2">
            {history.length === 0 ? (
              <p className="text-gray-500 text-sm text-center py-4">실행 이력이 없습니다</p>
            ) : (
              history.map(exec => (
                <div key={exec.id} className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
                  <button
                    onClick={() => setExpandedExec(expandedExec === exec.id ? null : exec.id)}
                    className="w-full px-3 py-2 flex items-center justify-between hover:bg-gray-700/50 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 text-[10px] rounded ${statusColors[exec.status] || 'bg-gray-600'}`}>
                        {statusLabels[exec.status] || exec.status}
                      </span>
                      <span className="text-gray-400 text-xs font-mono">{exec.id}</span>
                    </div>
                    <span className="text-gray-500 text-[10px]">
                      {exec.createdAt ? new Date(exec.createdAt).toLocaleString('ko-KR') : ''}
                    </span>
                  </button>
                  {expandedExec === exec.id && (
                    <div className="px-3 pb-2 border-t border-gray-700">
                      {exec.errorMessage && (
                        <div className="text-red-400 text-xs mt-1">{exec.errorMessage}</div>
                      )}
                      {exec.outputData && (
                        <pre className="text-[10px] text-gray-400 bg-gray-900 rounded p-2 mt-1 overflow-auto max-h-32 whitespace-pre-wrap">
                          {JSON.stringify(exec.outputData, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
