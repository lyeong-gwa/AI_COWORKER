import { useState, useEffect } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
// Phase 1c: 플로팅 챗 비활성화 — ChatProvider / ChatAssistant 마운트 해제.
// 복원 시: 아래 두 import 주석 해제 후 return 문의 ChatProvider 래핑 + ChatAssistant 마운트 복구.
// import { ChatProvider } from '../../contexts/ChatContext';
// import { ChatAssistant } from './ChatAssistant';
import { healthApi } from '../../services/api';

// Phase 3b: 실행/조회 전용 대시보드로 재구성.
// 대시보드(실행현황) → 워크플로우 목록 → 지식/API/노드 뷰어.
// 편집/생성 기능은 모두 CLI로 이관되었으므로 메뉴에서 생략.
const navItems = [
  { path: '/', label: '대시보드', icon: '⌂', shortcut: '1' },
  { path: '/workflows', label: '업무자동화', icon: '◇', shortcut: '2' },
  { path: '/workflows/generation-history', label: '∟ 생성 로그', icon: '🧾', shortcut: '', sub: true },
  { path: '/knowledge', label: '지식', icon: '📚', shortcut: '3', end: true },
  { path: '/knowledge/graph', label: '∟ 그래프', icon: '◈', shortcut: '', sub: true },
  { path: '/api-definitions', label: 'API 명세', icon: '🌐', shortcut: '4' },
  { path: '/nodes', label: '노드 카탈로그', icon: '⬡', shortcut: '5' },
  { path: '/instance-dbs', label: '인스턴스DB', icon: '📦', shortcut: '6' },
];

export function Layout() {
  const navigate = useNavigate();
  const [isCollapsed, setIsCollapsed] = useState(() => {
    const saved = localStorage.getItem('sidebar-collapsed');
    return saved === 'true';
  });
  const [isConnected, setIsConnected] = useState<boolean | null>(null);
  const [hoveredItem, setHoveredItem] = useState<string | null>(null);
  const [isMobile, setIsMobile] = useState(false);

  // Mobile detection
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 767px)');
    setIsMobile(mq.matches);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  // API connection status check
  useEffect(() => {
    const checkConnection = async () => {
      try {
        await healthApi.check();
        setIsConnected(true);
      } catch {
        setIsConnected(false);
      }
    };

    checkConnection();
    const interval = setInterval(checkConnection, 30000); // Check every 30s

    return () => clearInterval(interval);
  }, []);

  // Toggle sidebar and persist to localStorage
  const toggleSidebar = () => {
    setIsCollapsed((prev) => {
      const newValue = !prev;
      localStorage.setItem('sidebar-collapsed', String(newValue));
      return newValue;
    });
  };

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && !e.shiftKey && !e.altKey) {
        const index = parseInt(e.key, 10);
        if (index >= 1 && index <= navItems.length) {
          e.preventDefault();
          navigate(navItems[index - 1].path);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [navigate]);

  return (
    // Phase 1c: ChatProvider 비활성화. 복원 시 <ChatProvider> 래핑 추가.
    <div className="flex h-screen bg-gray-900">
        {/* Mobile backdrop */}
        {isMobile && !isCollapsed && (
          <div
            className="fixed inset-0 bg-black/50 z-30"
            onClick={() => setIsCollapsed(true)}
          />
        )}

        {/* Sidebar */}
        <aside
          className={`bg-gray-800 border-r border-gray-700 flex flex-col transition-all duration-300 ease-in-out ${
            isMobile ? 'fixed inset-y-0 left-0 z-40' : 'relative'
          } ${
            isCollapsed && isMobile ? '-translate-x-full' : 'translate-x-0'
          } ${
            isCollapsed && !isMobile ? 'w-16' : 'w-64'
          }`}
        >
          {/* Logo */}
          <div className="p-4 border-b border-gray-700 relative">
            <div className="flex items-center gap-2">
              <span className="text-2xl flex-shrink-0">🤖</span>
              {!isCollapsed && (
                <h1 className="text-xl font-bold text-white whitespace-nowrap overflow-hidden">
                  AI 업무도우미
                </h1>
              )}
            </div>
            {/* Connection Status Indicator */}
            {isConnected !== null && (
              <div
                className={`absolute top-2 right-2 w-2 h-2 rounded-full ${
                  isConnected ? 'bg-green-500' : 'bg-red-500'
                } ${isConnected ? 'shadow-[0_0_8px_rgba(34,197,94,0.8)]' : 'shadow-[0_0_8px_rgba(239,68,68,0.8)]'}`}
                title={isConnected ? '연결됨' : '연결 끊김'}
              />
            )}
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-2">
            <ul className="space-y-1">
              {navItems.map((item) => (
                <li
                  key={item.path}
                  className="relative"
                  onMouseEnter={() => isCollapsed && !isMobile && !item.sub && setHoveredItem(item.path)}
                  onMouseLeave={() => setHoveredItem(null)}
                >
                  {/* 서브 메뉴 항목 (접힌 사이드바에서 숨김) */}
                  {item.sub && (isCollapsed && !isMobile) ? null : (
                    <NavLink
                      to={item.path}
                      end={item.end}
                      onClick={() => isMobile && setIsCollapsed(true)}
                      className={({ isActive }) =>
                        `flex items-center gap-3 px-3 rounded-lg transition-all duration-200 relative ${
                          item.sub ? 'py-1.5' : 'py-3'
                        } ${
                          isActive
                            ? item.sub
                              ? 'text-blue-400 bg-blue-900/20'
                              : 'bg-blue-600 text-white border-l-4 border-blue-400 pl-2'
                            : item.sub
                            ? 'text-gray-500 hover:text-gray-300 hover:bg-gray-700/50'
                            : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                        } ${isCollapsed && !isMobile ? 'justify-center' : ''}`
                      }
                    >
                      <span className={`flex-shrink-0 ${item.sub ? 'text-sm' : 'text-xl'}`}>
                        {item.icon}
                      </span>
                      {!(isCollapsed && !isMobile) && (
                        <div className="flex-1 flex items-center justify-between min-w-0">
                          <span className={`truncate ${item.sub ? 'text-sm' : 'font-medium'}`}>
                            {item.sub ? item.label.replace('∟ ', '') : item.label}
                          </span>
                          {item.shortcut && (
                            <span className="text-xs text-gray-400 opacity-60 ml-2 flex-shrink-0">
                              ⌃{item.shortcut}
                            </span>
                          )}
                        </div>
                      )}
                    </NavLink>
                  )}

                  {/* Tooltip on collapsed mode (메인 항목만) */}
                  {!item.sub && isCollapsed && !isMobile && hoveredItem === item.path && (
                    <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-3 py-2 bg-gray-700 text-white text-sm rounded-lg shadow-lg whitespace-nowrap z-50 pointer-events-none">
                      {item.label}
                      {item.shortcut && (
                        <span className="text-xs text-gray-400 ml-2">Ctrl+{item.shortcut}</span>
                      )}
                      <div className="absolute right-full top-1/2 -translate-y-1/2 w-0 h-0 border-y-4 border-y-transparent border-r-4 border-r-gray-700" />
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </nav>

          {/* Footer with toggle button */}
          <div className="border-t border-gray-700">
            {/* User info */}
            {!(isCollapsed && !isMobile) && (
              <div className="p-4">
                <div className="flex items-center gap-3 text-gray-400 text-sm">
                  <div className="w-8 h-8 rounded-full bg-gray-600 flex items-center justify-center flex-shrink-0">
                    👤
                  </div>
                  <div className="min-w-0">
                    <div className="text-gray-200 truncate">사용자</div>
                    <div className="text-xs flex items-center gap-1">
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${
                          isConnected ? 'bg-green-500' : 'bg-red-500'
                        }`}
                      />
                      {isConnected ? '온라인' : '오프라인'}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Toggle button - hide on mobile */}
            {!isMobile && (
              <div className="p-2">
                <button
                  onClick={toggleSidebar}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-gray-400 hover:bg-gray-700 hover:text-white transition-colors"
                  title={isCollapsed ? '사이드바 확장' : '사이드바 축소'}
                >
                  <span className="text-lg">{isCollapsed ? '→' : '←'}</span>
                  {!isCollapsed && <span className="text-sm font-medium">축소</span>}
                </button>
              </div>
            )}
          </div>
        </aside>

        {/* Main Content */}
        <main className="flex-1 overflow-auto">
          {/* Hamburger menu for mobile */}
          {isMobile && (
            <button
              onClick={() => setIsCollapsed(false)}
              className="fixed top-3 left-3 z-20 p-2 bg-gray-800 rounded-lg text-gray-400 hover:text-white shadow-lg"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          )}
          <Outlet />
        </main>

        {/* Phase 1c: ChatAssistant 비활성화. 복원 시 <ChatAssistant /> 마운트 복구. */}
      </div>
  );
}
