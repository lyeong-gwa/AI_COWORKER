import { useState, useRef, useEffect } from 'react';
import { useChatContext } from '../../contexts/ChatContext';
import type { ChatContextType, ChatMode, ChatAction } from '../../types';
import { StyledMarkdown } from './StyledMarkdown';
import { ChatModeSelector } from '../chat/ChatModeSelector';
import { ChatActionBar } from '../chat/ChatActionBar';

function getContextIcon(contextType: ChatContextType['type']): string {
  switch (contextType) {
    case 'task': return '📋';
    case 'node': return '🔷';
    case 'workflow': return '⚙️';
    case 'document': return '📚';
    default: return '';
  }
}

function getContextLabel(context: ChatContextType): string {
  switch (context.type) {
    case 'task': return `[태스크] ${context.data.title}`;
    case 'node': return `[노드] ${context.data.name}`;
    case 'workflow': return `[워크플로우] ${context.data.name}`;
    case 'document': return `[문서] ${context.data.title}`;
    default: return '';
  }
}

function getPlaceholder(mode: ChatMode, action: ChatAction | null): string {
  if (mode === 'taskboard') {
    if (action === 'create') return '이메일 내용이나 작업 내용을 붙여넣으세요...';
    if (action === 'search') return '찾고 싶은 태스크를 설명하세요...';
    return '태스크에 대해 물어보세요...';
  }
  if (mode === 'knowledge') return '지식 베이스에서 검색하거나 질문하세요...';
  if (mode === 'node') return '노드 수정 사항을 설명하세요...';
  if (mode === 'workflow') return '워크플로우 수정 사항을 설명하세요...';
  return '메시지를 입력하세요...';
}

export function ChatAssistant() {
  const {
    isOpen, messages, selectedContext, isLoading, isConnected,
    activeMode, pendingAction,
    toggleChat, sendMessage, clearContext, setMode, setAction,
  } = useChatContext();
  const [inputValue, setInputValue] = useState('');
  const [isMinimized, setIsMinimized] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (isOpen && !isMinimized) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isOpen, isMinimized]);

  // Focus input when chat opens
  useEffect(() => {
    if (isOpen && !isMinimized) {
      inputRef.current?.focus();
    }
  }, [isOpen, isMinimized]);

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;

    await sendMessage(inputValue);
    setInputValue('');
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  if (!isOpen) {
    return (
      <button
        onClick={toggleChat}
        className="fixed bottom-6 right-6 w-14 h-14 bg-gradient-to-br from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white rounded-full shadow-lg hover:shadow-xl transition-all duration-300 flex items-center justify-center text-2xl z-50 group"
        aria-label="AI 어시스턴트 열기"
      >
        <span className="group-hover:scale-110 transition-transform">🤖</span>
      </button>
    );
  }

  return (
    <div
      className={`fixed bottom-6 right-6 w-[936px] bg-gray-800 border border-gray-700 rounded-xl shadow-2xl overflow-hidden flex flex-col transition-all duration-300 z-50 ${
        isMinimized ? 'h-14' : 'h-[600px]'
      }`}
    >
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 to-blue-700 p-4 flex items-center justify-between border-b border-blue-500">
        <div className="flex items-center gap-2 text-white">
          <span className="text-xl">🤖</span>
          <span className="font-semibold">AI 어시스턴트</span>
          <span
            className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-400' : 'bg-red-400'}`}
            title={isConnected ? '서버 연결됨' : '서버 연결 안됨'}
          />
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsMinimized(!isMinimized)}
            className="text-white hover:bg-blue-500/30 rounded p-1 transition-colors"
            aria-label={isMinimized ? '확대' : '최소화'}
          >
            <span className="text-lg leading-none">{isMinimized ? '□' : '─'}</span>
          </button>
          <button
            onClick={toggleChat}
            className="text-white hover:bg-blue-500/30 rounded p-1 transition-colors"
            aria-label="닫기"
          >
            <span className="text-xl leading-none">×</span>
          </button>
        </div>
      </div>

      {!isMinimized && (
        <>
          {/* Mode Selector */}
          <ChatModeSelector activeMode={activeMode} onModeChange={setMode} />

          {/* Context Display */}
          {selectedContext.type !== 'none' && (
            <div className="bg-gray-750 border-b border-gray-700 p-3">
              <div className="flex items-center justify-between bg-gray-700 rounded-lg p-2">
                <div className="flex items-center gap-2 text-sm">
                  <span>{getContextIcon(selectedContext.type)}</span>
                  <span className="text-gray-300">선택된 항목:</span>
                  <span className="text-white font-medium truncate">
                    {getContextLabel(selectedContext)}
                  </span>
                </div>
                <button
                  onClick={clearContext}
                  className="text-gray-400 hover:text-white transition-colors"
                  aria-label="컨텍스트 제거"
                >
                  <span className="text-lg leading-none">×</span>
                </button>
              </div>
            </div>
          )}

          {/* Action Bar */}
          <ChatActionBar mode={activeMode} activeAction={pendingAction} onActionSelect={setAction} />

          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-850">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] rounded-lg p-3 ${
                    message.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-700 text-gray-100'
                  }`}
                >
                  <div className="flex items-start gap-2">
                    {message.role === 'assistant' && (
                      <span className="text-lg flex-shrink-0">🤖</span>
                    )}
                    <div className="flex-1">
                      {message.role === 'assistant' ? (
                        <StyledMarkdown variant="chat">{message.content}</StyledMarkdown>
                      ) : (
                        <StyledMarkdown variant="chat-user">{message.content}</StyledMarkdown>
                      )}
                      {message.context && message.context.type !== 'none' && (
                        <div className="mt-2 text-xs opacity-70">
                          <span>{getContextIcon(message.context.type)}</span>{' '}
                          {getContextLabel(message.context)}
                        </div>
                      )}
                    </div>
                    {message.role === 'user' && (
                      <span className="text-lg flex-shrink-0">👤</span>
                    )}
                  </div>
                  <div className={`text-xs mt-1 ${message.role === 'user' ? 'text-blue-200/60' : 'text-gray-500'}`}>
                    {new Date(message.timestamp).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
                  </div>
                </div>
              </div>
            ))}

            {/* Loading indicator */}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-gray-700 text-gray-100 rounded-lg p-3">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">🤖</span>
                    <div className="flex gap-1">
                      <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                      <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                      <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input Area */}
          <div className="border-t border-gray-700 p-4 bg-gray-800">
            <div className="flex gap-2">
              <input
                ref={inputRef}
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyPress}
                placeholder={getPlaceholder(activeMode, pendingAction)}
                disabled={isLoading}
                className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed text-sm"
              />
              <button
                onClick={handleSendMessage}
                disabled={!inputValue.trim() || isLoading}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
                aria-label="전송"
              >
                <span className="text-xl">📤</span>
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
