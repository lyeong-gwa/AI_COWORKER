import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ToastProvider } from './components/common/Toast';
import { ErrorBoundary } from './components/common/ErrorBoundary';
import { Layout } from './components/common/Layout';

const TaskBoardPage = lazy(() => import('./pages/TaskBoardPage').then(m => ({ default: m.TaskBoardPage })));
const KnowledgeBasePage = lazy(() => import('./pages/KnowledgeBasePage').then(m => ({ default: m.KnowledgeBasePage })));
const ApiDefinitionPage = lazy(() => import('./pages/ApiDefinitionPage'));
const NodeManagementPage = lazy(() => import('./pages/NodeManagementPage').then(m => ({ default: m.NodeManagementPage })));
const FactoryPage = lazy(() => import('./pages/FactoryPage').then(m => ({ default: m.FactoryPage })));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage').then(m => ({ default: m.NotFoundPage })));

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="flex flex-col items-center gap-3">
        <div className="w-10 h-10 border-4 border-gray-600 border-t-blue-500 rounded-full animate-spin" />
        <span className="text-gray-400 text-sm">페이지 로딩 중...</span>
      </div>
    </div>
  );
}

function App() {
  return (
    <ToastProvider>
      <ErrorBoundary>
        <BrowserRouter>
          <Suspense fallback={<PageLoader />}>
            <Routes>
              <Route path="/" element={<Layout />}>
                <Route index element={<TaskBoardPage />} />
                <Route path="knowledge" element={<KnowledgeBasePage />} />
                <Route path="api-definitions" element={
                  <Suspense fallback={<PageLoader />}>
                    <ApiDefinitionPage />
                  </Suspense>
                } />
                <Route path="nodes" element={<NodeManagementPage />} />
                <Route path="factory" element={<FactoryPage />} />
                <Route path="*" element={<NotFoundPage />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
      </ErrorBoundary>
    </ToastProvider>
  );
}

export default App;
