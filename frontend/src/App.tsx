import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ToastProvider } from './components/common/Toast';
import { ErrorBoundary } from './components/common/ErrorBoundary';
import { Layout } from './components/common/Layout';

// Phase 3b: 새 대시보드 + 워크플로우 뷰어 + 인스턴스 상세
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const WorkflowListPage = lazy(() => import('./pages/WorkflowListPage'));
const WorkflowViewerPage = lazy(() => import('./pages/WorkflowViewerPage'));
const InstanceDetailPage = lazy(() => import('./pages/InstanceDetailPage'));

// Phase 3: 채팅 기반 워크플로우 생성
const ChatWorkflowGeneratorPage = lazy(() => import('./pages/ChatWorkflowGeneratorPage'));

// Phase 9: Blueprint import
const BlueprintImportPage = lazy(() => import('./pages/BlueprintImportPage'));

// 생성 히스토리 뷰어
const GenerationHistoryPage = lazy(() => import('./pages/GenerationHistoryPage'));

// Phase 3b: 읽기 전용 축소판
const KnowledgeViewerPage = lazy(() =>
  import('./pages/KnowledgeViewerPage').then((m) => ({ default: m.KnowledgeViewerPage })),
);
const KnowledgeGraphPage = lazy(() =>
  import('./pages/KnowledgeGraphPage').then((m) => ({ default: m.KnowledgeGraphPage })),
);
const ApiDefinitionViewerPage = lazy(() => import('./pages/ApiDefinitionViewerPage'));
const NodeCatalogPage = lazy(() =>
  import('./pages/NodeCatalogPage').then((m) => ({ default: m.NodeCatalogPage })),
);
const InstanceDBViewerPage = lazy(() =>
  import('./pages/InstanceDBViewerPage').then((m) => ({ default: m.InstanceDBViewerPage })),
);

const NotFoundPage = lazy(() =>
  import('./pages/NotFoundPage').then((m) => ({ default: m.NotFoundPage })),
);

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-full bg-slate-950">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-slate-700 border-t-sky-500 rounded-full animate-spin" />
        <span className="text-slate-500 text-xs font-mono tracking-wider">
          페이지 로딩 중...
        </span>
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
                {/* 대시보드 (실행현황 + 워크플로우 카드) */}
                <Route index element={<DashboardPage />} />

                {/* 워크플로우 */}
                <Route path="workflows" element={<WorkflowListPage />} />
                {/* Phase 3: 채팅 생성 — ":id" 라우트보다 먼저 */}
                <Route path="workflows/new/chat" element={<ChatWorkflowGeneratorPage />} />
                {/* Phase 9: Blueprint import — ":id" 라우트보다 먼저 */}
                <Route path="workflows/import" element={<BlueprintImportPage />} />
                {/* 생성 히스토리 뷰어 — ":id" 라우트보다 먼저 */}
                <Route path="workflows/generation-history" element={<GenerationHistoryPage />} />
                {/* 채팅 편집 모드 — ":id" 동적 라우트보다 먼저 */}
                <Route path="workflows/:id/edit" element={<ChatWorkflowGeneratorPage />} />
                <Route path="workflows/:id" element={<WorkflowViewerPage />} />
                <Route
                  path="workflows/:id/instances/:iid"
                  element={<InstanceDetailPage />}
                />

                {/* 읽기 전용 뷰어 페이지 */}
                <Route path="knowledge" element={<KnowledgeViewerPage />} />
                <Route path="knowledge/graph" element={<KnowledgeGraphPage />} />
                <Route path="api-definitions" element={<ApiDefinitionViewerPage />} />
                <Route path="nodes" element={<NodeCatalogPage />} />
                <Route path="instance-dbs" element={<InstanceDBViewerPage />} />

                {/* 레거시 경로 → 신규 경로 리다이렉트 (기존 북마크 사용자 대응) */}
                <Route path="factory" element={<Navigate to="/workflows" replace />} />
                <Route path="factory/:id" element={<Navigate to="/workflows" replace />} />
                <Route path="dashboard" element={<Navigate to="/" replace />} />
                <Route path="ops" element={<Navigate to="/" replace />} />
                <Route path="workflow" element={<Navigate to="/workflows" replace />} />
                <Route path="knowledge-base" element={<Navigate to="/knowledge" replace />} />
                <Route path="api-definition" element={<Navigate to="/api-definitions" replace />} />
                <Route path="node-management" element={<Navigate to="/nodes" replace />} />

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
