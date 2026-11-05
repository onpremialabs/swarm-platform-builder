import React, { useEffect, useState } from 'react';
import { LoadingState } from './platform/components/ui/states';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { useAuthStore } from './platform/store/authStore';
import { useProjectStore } from './platform/store/projectStore';

import AuthPage          from './platform/pages/AuthPage';
import ProjectSelectionPage from './platform/pages/ProjectSelectionPage';
import DashboardPage     from './platform/pages/DashboardPage';
import FlowDesignerPage  from './platform/pages/FlowDesignerPage';
import FlowsPage         from './platform/pages/FlowsPage';
import AgentsPage        from './platform/pages/AgentsPage';
import ArticlesPage      from './projects/alejandria-magazine/pages/ArticlesPage';
import ArticleDetailPage from './projects/alejandria-magazine/pages/ArticleDetailPage';
import ConfigPage        from './platform/pages/ConfigPage';
import DocumentsPage     from './platform/pages/DocumentsPage';
import ExecutionPage     from './projects/alejandria-magazine/pages/ExecutionPage';
import TraceabilityPage    from './projects/alejandria-magazine/pages/TraceabilityPage';
import MetricsDashboardPage from './projects/alejandria-magazine/pages/MetricsDashboardPage';
import UsersPage         from './platform/pages/UsersPage';
import MagazinePage      from './projects/alejandria-magazine/pages/MagazinePage';
import LectorPage        from './projects/alejandria-magazine/pages/LectorPage';
import PaperViewPage     from './projects/alejandria-magazine/pages/PaperViewPage';
import PaperDesignPage   from './projects/alejandria-magazine/pages/PaperDesignPage';

function RouteTitleHandler() {
  const location = useLocation();

  useEffect(() => {
    const path = location.pathname;
    if (path.startsWith('/projects') || path.startsWith('/auth') || path === '/') {
      document.title = 'SwarmPlatformBuilder';
    } else {
      document.title = 'AlejandrIA Magazine';
    }
  }, [location]);

  return null;
}

function AppBootGate({ children }) {
  const [hasHydrated, setHasHydrated] = useState(() => useAuthStore.persist?.hasHydrated?.() ?? true);

  useEffect(() => {
    const persistApi = useAuthStore.persist;
    if (!persistApi) {
      setHasHydrated(true);
      return undefined;
    }

    const unsubscribeHydrate = persistApi.onHydrate?.(() => setHasHydrated(false));
    const unsubscribeFinishHydration = persistApi.onFinishHydration?.(() => setHasHydrated(true));

    if (!persistApi.hasHydrated()) {
      persistApi.rehydrate();
    } else {
      setHasHydrated(true);
    }

    return () => {
      unsubscribeHydrate?.();
      unsubscribeFinishHydration?.();
    };
  }, []);

  if (!hasHydrated) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--bg-canvas)' }}>
        <LoadingState label="Iniciando…" />
      </div>
    );
  }

  return children;
}

/**
 * Todo lo que hay bajo el dashboard trabaja **dentro de un proyecto**: los
 * documentos, los agentes y los flujos se piden con la cabecera `X-Project-Id`
 * (SPEC-013 / T8.5 / AC6). Sin proyecto activo esas llamadas responden 400, así
 * que se vuelve a la selección en vez de enseñar una página de error que no
 * explica qué falta.
 */
function RequireProject({ children }) {
  const { activeProject } = useProjectStore();
  if (!activeProject?.id) return <Navigate to="/projects" replace />;
  return children;
}

function ProtectedRoute({ children, allowedRoles }) {
  const { isAuthenticated, user } = useAuthStore();
  if (!isAuthenticated) return <Navigate to="/auth" replace />;
  // Lectors and Publicos must stay in their own reader view
  const isReaderRole = user?.role === 'lector' || user?.role === 'publico';
  if (isReaderRole && (!allowedRoles || !allowedRoles.includes(user.role))) {
    return <Navigate to="/reader" replace />;
  }
  if (allowedRoles && !allowedRoles.includes(user?.role)) return <Navigate to="/dashboard/articles" replace />;
  return children;
}

function PublicRoute({ children }) {
  const { isAuthenticated, user } = useAuthStore();
  if (isAuthenticated) {
    const isReaderRole = user?.role === 'lector' || user?.role === 'publico';
    return <Navigate to={isReaderRole ? '/reader' : '/projects'} replace />;
  }
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <RouteTitleHandler />
      <AppBootGate>
        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              background: 'var(--bg-surface)',
              color: 'var(--text-body)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              fontSize: 'var(--font-size-sm)',
              boxShadow: 'var(--shadow-3)',
            },
            success: { iconTheme: { primary: 'var(--success)', secondary: 'var(--bg-surface)' } },
            error:   { iconTheme: { primary: 'var(--error)',   secondary: 'var(--bg-surface)' } },
          }}
        />
        <Routes>
          {/* Fully public — no auth needed */}
          <Route path="/auth"     element={<PublicRoute><AuthPage /></PublicRoute>} />
          <Route path="/magazine" element={<MagazinePage />} />

          {/* Lector reader view */}
          <Route path="/reader" element={
            <ProtectedRoute allowedRoles={['lector', 'publico']}><LectorPage /></ProtectedRoute>
          } />

          {/* Project selection (requires auth, not for lectors) */}
          <Route path="/projects" element={
            <ProtectedRoute allowedRoles={['admin', 'redactor']}><ProjectSelectionPage /></ProtectedRoute>
          } />

          {/* Execution (full screen, no dashboard shell) */}
          <Route path="/execution/:articleId" element={
            <ProtectedRoute><RequireProject><ExecutionPage /></RequireProject></ProtectedRoute>
          } />

          {/* Paper-layout printable view (full screen) */}
          <Route path="/articles/:id/design" element={
            <ProtectedRoute><PaperDesignPage /></ProtectedRoute>
          } />
          <Route path="/articles/:id/paper" element={
            <ProtectedRoute><PaperViewPage /></ProtectedRoute>
          } />

          {/* Dashboard */}
          <Route path="/dashboard" element={
            <ProtectedRoute><RequireProject><DashboardPage /></RequireProject></ProtectedRoute>
          }>
            <Route index element={<Navigate to="articles" replace />} />
            <Route path="flow-designer" element={<FlowDesignerPage />} />
            <Route path="flows"         element={<FlowsPage />} />
            <Route path="agents"        element={<AgentsPage />} />
            <Route path="articles"            element={<ArticlesPage />} />
            <Route path="articles/:id"        element={<ArticleDetailPage />} />
            <Route path="execution/:articleId" element={<TraceabilityPage />} />
            <Route path="traceability"         element={<MetricsDashboardPage />} />
            <Route path="documents"           element={<DocumentsPage />} />
            <Route path="config"        element={<ConfigPage />} />
            <Route path="users"         element={
              <ProtectedRoute allowedRoles={['admin']}>
                <UsersPage />
              </ProtectedRoute>
            } />
          </Route>

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/projects" replace />} />
        </Routes>
      </AppBootGate>
    </BrowserRouter>
  );
}
