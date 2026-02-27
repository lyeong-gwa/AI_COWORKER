import type { ChatMode, ChatAction } from '../../types';

interface ChatActionBarProps {
  mode: ChatMode;
  activeAction: ChatAction | null;
  onActionSelect: (action: ChatAction | null) => void;
}

interface ActionConfig {
  action: ChatAction;
  label: string;
  icon: string;
}

const MODE_ACTIONS: Partial<Record<ChatMode, ActionConfig[]>> = {
  taskboard: [
    { action: 'create', label: '새 태스크 생성', icon: '\uD83D\uDCDD' },
    { action: 'search', label: '이력 조회', icon: '\uD83D\uDD0D' },
  ],
  knowledge: [
    { action: 'search', label: '검색/질문', icon: '\uD83D\uDD0D' },
    { action: 'modify', label: '수정 요청', icon: '\u270F\uFE0F' },
  ],
  node: [
    { action: 'modify', label: '수정 요청', icon: '\u270F\uFE0F' },
    { action: 'explain', label: '설명', icon: '\uD83D\uDCA1' },
  ],
  workflow: [
    { action: 'modify', label: '수정 요청', icon: '\u270F\uFE0F' },
    { action: 'explain', label: '설명', icon: '\uD83D\uDCA1' },
  ],
};

export function ChatActionBar({ mode, activeAction, onActionSelect }: ChatActionBarProps) {
  const actions = MODE_ACTIONS[mode];

  if (!actions || actions.length === 0) return null;

  return (
    <div className="flex items-center gap-1.5 px-3 py-1.5 border-b border-gray-700/50">
      {actions.map(({ action, label, icon }) => (
        <button
          key={action}
          onClick={() => onActionSelect(activeAction === action ? null : action)}
          className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
            activeAction === action
              ? 'bg-blue-500/20 text-blue-400 border border-blue-500/50'
              : 'text-gray-400 hover:text-white hover:bg-gray-700/50 border border-transparent'
          }`}
        >
          <span>{icon}</span>
          <span>{label}</span>
        </button>
      ))}
    </div>
  );
}
