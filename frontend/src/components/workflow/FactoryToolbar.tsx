interface FactoryToolbarProps {
  onSave: () => void;
  onExecute: () => void;
  onToggleHistory: () => void;
  isSaving: boolean;
  isExecuting: boolean;
  lastSaved?: string;
}

export function FactoryToolbar({
  onSave,
  onExecute,
  onToggleHistory,
  isSaving,
  isExecuting,
  lastSaved,
}: FactoryToolbarProps) {
  return (
    <div className="h-12 bg-gray-800 border-b border-gray-700 flex items-center justify-between px-4">
      {/* Left: Title */}
      <div className="flex items-center gap-3">
        <span className="text-xl">⚙️</span>
        <h1 className="text-white font-bold text-lg">공장 맵</h1>
        {lastSaved && (
          <span className="text-gray-500 text-xs">
            마지막 저장: {new Date(lastSaved).toLocaleTimeString('ko-KR')}
          </span>
        )}
        {isSaving && (
          <span className="flex items-center gap-1.5 text-blue-400 text-xs">
            <div className="w-3 h-3 border-2 border-blue-400/30 border-t-blue-400 rounded-full animate-spin" />
            저장 중...
          </span>
        )}
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-2">
        <button
          onClick={onSave}
          disabled={isSaving}
          className="px-3 py-1.5 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 disabled:opacity-50 transition-colors text-sm flex items-center gap-1.5"
        >
          💾 저장
        </button>

        <button
          onClick={onExecute}
          disabled={isExecuting}
          className="px-3 py-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors text-sm flex items-center gap-1.5"
        >
          {isExecuting ? (
            <>
              <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              실행 중...
            </>
          ) : (
            <>▶ 전체 실행</>
          )}
        </button>

        <button
          onClick={onToggleHistory}
          className="px-3 py-1.5 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 transition-colors text-sm flex items-center gap-1.5"
        >
          📊 실행 이력
        </button>
      </div>
    </div>
  );
}
