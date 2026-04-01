interface ExecutionStatusBadgeProps {
  status?: string;
}

export function ExecutionStatusBadge({ status }: ExecutionStatusBadgeProps) {
  if (!status || status === 'idle') return null;

  if (status === 'running') {
    return (
      <div
        className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin flex-shrink-0"
        title="실행 중"
      />
    );
  }

  if (status === 'completed') {
    return (
      <svg
        className="w-4 h-4 text-green-400 flex-shrink-0"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-label="완료"
      >
        <polyline points="2.5,8.5 6,12 13.5,4.5" />
      </svg>
    );
  }

  if (status === 'failed') {
    return (
      <svg
        className="w-4 h-4 text-red-400 flex-shrink-0"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth={2.5}
        strokeLinecap="round"
        aria-label="실패"
      >
        <line x1="3" y1="3" x2="13" y2="13" />
        <line x1="13" y1="3" x2="3" y2="13" />
      </svg>
    );
  }

  return null;
}
