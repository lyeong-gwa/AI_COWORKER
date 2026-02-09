import { createContext, useContext, useState, useCallback, useRef, useMemo, useEffect } from 'react';
import type { ReactNode } from 'react';
import type { ChatMessage, ChatContextType } from '../types';
import { chatApi } from '../services/api';

interface ChatContextState {
  isOpen: boolean;
  messages: ChatMessage[];
  selectedContext: ChatContextType;
  isLoading: boolean;
  sessionId: string | null;
  isConnected: boolean;
}

interface ChatContextValue extends ChatContextState {
  toggleChat: () => void;
  openChat: () => void;
  sendMessage: (content: string) => Promise<void>;
  setContext: (context: ChatContextType) => void;
  clearContext: () => void;
  onDataChange: (callback: (target: string) => void) => () => void;
}

const ChatContext = createContext<ChatContextValue | undefined>(undefined);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: '1',
      role: 'assistant',
      content: '안녕하세요! AI 어시스턴트입니다. 무엇을 도와드릴까요?',
      timestamp: new Date().toISOString(),
    },
  ]);
  const [selectedContext, setSelectedContext] = useState<ChatContextType>({ type: 'none' });
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const retryCountRef = useRef(0);
  const dataChangeListenersRef = useRef<Set<(target: string) => void>>(new Set());

  // Check connection on mount
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/api\/v1$/, '');
        const res = await fetch(`${baseUrl}/health`);
        setIsConnected(res.ok);
      } catch {
        setIsConnected(false);
      }
    };
    checkHealth();
  }, []);

  const toggleChat = useCallback(() => {
    setIsOpen(prev => !prev);
  }, []);

  const openChat = useCallback(() => {
    setIsOpen(true);
  }, []);

  const onDataChange = useCallback((callback: (target: string) => void) => {
    dataChangeListenersRef.current.add(callback);
    return () => {
      dataChangeListenersRef.current.delete(callback);
    };
  }, []);

  const sendMessage = useCallback(async (content: string) => {
    // Add user message
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content,
      context: selectedContext.type !== 'none' ? selectedContext : undefined,
      timestamp: new Date().toISOString(),
    };

    setMessages(prev => [...prev, userMessage]);
    setIsLoading(true);

    try {
      // Prepare context for API
      const contextForApi = selectedContext.type !== 'none' ? {
        type: selectedContext.type,
        id: selectedContext.data?.id,
      } : undefined;

      // Call backend API
      const response = await chatApi.sendMessage({
        content,
        context: contextForApi,
        sessionId: sessionId || undefined,
      });

      // Update session ID
      if (response.sessionId && !sessionId) {
        setSessionId(response.sessionId);
      }

      // Add assistant message
      const assistantMessage: ChatMessage = {
        id: response.id,
        role: 'assistant',
        content: response.content,
        timestamp: response.timestamp,
      };

      setMessages(prev => [...prev, assistantMessage]);
      setIsConnected(true);
      retryCountRef.current = 0;

      // If action was performed, trigger data refresh
      if (response.action) {
        const target = response.action.target || response.action.type || '';
        dataChangeListenersRef.current.forEach(cb => cb(target));
      }

    } catch (error) {
      console.error('Chat API error:', error);
      setIsConnected(false);

      // Fallback response when API is not available
      let fallbackContent = '죄송합니다. 현재 AI 서비스에 연결할 수 없습니다. ';

      if (retryCountRef.current < 3) {
        fallbackContent += '잠시 후 다시 시도해주세요.';
        retryCountRef.current++;
      } else {
        fallbackContent += '백엔드 서버가 실행 중인지 확인해주세요. (http://localhost:8000)';
      }

      // Generate local fallback response based on context
      if (selectedContext.type !== 'none') {
        switch (selectedContext.type) {
          case 'task':
            fallbackContent = `[오프라인] 선택된 태스크: "${selectedContext.data.title}"\n서버 연결 후 작업이 가능합니다.`;
            break;
          case 'tool':
            fallbackContent = `[오프라인] 선택된 도구: "${selectedContext.data.name}"\n서버 연결 후 활용이 가능합니다.`;
            break;
          case 'node':
            fallbackContent = `[오프라인] 선택된 노드: "${selectedContext.data.name}"\n서버 연결 후 작업이 가능합니다.`;
            break;
          case 'workflow':
            fallbackContent = `[오프라인] 선택된 워크플로우: "${selectedContext.data.name}"\n서버 연결 후 실행이 가능합니다.`;
            break;
          case 'document':
            fallbackContent = `[오프라인] 선택된 문서: "${selectedContext.data.title}"\n서버 연결 후 참조가 가능합니다.`;
            break;
        }
      }

      const fallbackMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: fallbackContent,
        timestamp: new Date().toISOString(),
      };

      setMessages(prev => [...prev, fallbackMessage]);
    } finally {
      setIsLoading(false);
    }
  }, [selectedContext, sessionId]);

  const setContext = useCallback((context: ChatContextType) => {
    setSelectedContext(context);
  }, []);

  const clearContext = useCallback(() => {
    setSelectedContext({ type: 'none' });
  }, []);

  const contextValue = useMemo(() => ({
    isOpen,
    messages,
    selectedContext,
    isLoading,
    sessionId,
    isConnected,
    toggleChat,
    openChat,
    sendMessage,
    setContext,
    clearContext,
    onDataChange,
  }), [isOpen, messages, selectedContext, isLoading, sessionId, isConnected,
       toggleChat, openChat, sendMessage, setContext, clearContext, onDataChange]);

  return (
    <ChatContext.Provider value={contextValue}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChatContext() {
  const context = useContext(ChatContext);
  if (context === undefined) {
    throw new Error('useChatContext must be used within a ChatProvider');
  }
  return context;
}
