import { useState } from 'react';

interface NodeOutputPillProps {
  output?: unknown;
  error?: string;
  status?: string;
}

export function NodeOutputPill({ output, error, status }: NodeOutputPillProps) {
  const [expanded, setExpanded] = useState(false);

  if (!status || status === 'idle') return null;

  if (status === 'running') {
    return (
      <div className="nodrag nopan mt-1.5 mx-1 mb-1 px-2.5 py-1.5 rounded-lg bg-gray-900/80 border border-blue-700/40 flex items-center gap-2">
        <div className="w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin flex-shrink-0" />
        <span className="text-[10px] text-blue-300/80">실행 중...</span>
      </div>
    );
  }

  if (status === 'failed') {
    return (
      <div className="nodrag nopan mt-1.5 mx-1 mb-1 px-2.5 py-1.5 rounded-lg bg-red-900/60 border border-red-700/50">
        <span className="text-[10px] text-red-300 break-words">{error || '실행 실패'}</span>
      </div>
    );
  }

  if (status === 'completed') {
    const isObj = output !== null && output !== undefined && typeof output === 'object';
    const keys = isObj ? Object.keys(output as Record<string, unknown>) : [];
    const summary = isObj
      ? `출력 ${keys.length}필드`
      : output !== undefined && output !== null
        ? '출력 결과'
        : '완료';

    return (
      <div
        className="nodrag nopan mt-1.5 mx-1 mb-1 rounded-lg bg-gray-900/80 border border-green-700/40 overflow-hidden cursor-pointer"
        onClick={() => setExpanded(v => !v)}
      >
        {/* Summary row */}
        <div className="px-2.5 py-1.5 flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-green-400 flex-shrink-0" />
            <span className="text-[10px] text-green-300/90 font-medium">{summary}</span>
          </div>
          <span className="text-[9px] text-gray-500 flex-shrink-0">{expanded ? '▲' : '▼'}</span>
        </div>

        {/* Expanded detail */}
        {expanded && (
          <div className="px-2.5 pb-2 max-h-[120px] overflow-auto border-t border-white/5">
            {isObj ? (
              <table className="w-full text-[9px] mt-1.5">
                <tbody>
                  {keys.map(k => (
                    <tr key={k} className="border-b border-white/5 last:border-0">
                      <td className="py-0.5 pr-2 text-gray-400 align-top font-mono whitespace-nowrap">{k}</td>
                      <td className="py-0.5 text-gray-200 break-all">
                        {typeof (output as Record<string, unknown>)[k] === 'object'
                          ? JSON.stringify((output as Record<string, unknown>)[k])
                          : String((output as Record<string, unknown>)[k])}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <pre className="text-[9px] text-gray-200 mt-1.5 break-all whitespace-pre-wrap">
                {JSON.stringify(output, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    );
  }

  return null;
}
