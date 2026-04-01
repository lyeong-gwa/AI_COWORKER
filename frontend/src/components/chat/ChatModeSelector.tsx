import type { ChatMode } from '../../types';

interface ChatModeSelectorProps {
  activeMode: ChatMode;
  onModeChange: (mode: ChatMode) => void;
}

const MODE_CONFIG: { mode: ChatMode; label: string; icon: string }[] = [
  { mode: 'general', label: '일반', icon: '\uD83D\uDCAC' },
  { mode: 'knowledge', label: '지식', icon: '\uD83D\uDCDA' },
  { mode: 'node', label: '노드', icon: '\uD83D\uDD37' },
  { mode: 'workflow', label: '워크플로우', icon: '\u2699\uFE0F' },
];

export function ChatModeSelector({ activeMode, onModeChange }: ChatModeSelectorProps) {
  return (
    <div className="flex items-center gap-1 px-3 py-1.5 bg-gray-800/50 border-b border-gray-700 overflow-x-auto">
      {MODE_CONFIG.map(({ mode, label, icon }) => (
        <button
          key={mode}
          onClick={() => onModeChange(mode)}
          className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
            activeMode === mode
              ? 'bg-blue-600 text-white'
              : 'text-gray-400 hover:text-white hover:bg-gray-700'
          }`}
        >
          <span className="text-sm">{icon}</span>
          <span>{label}</span>
        </button>
      ))}
    </div>
  );
}
