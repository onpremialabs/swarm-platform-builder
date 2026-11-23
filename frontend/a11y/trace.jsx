// Banco de TraceabilityPage en vivo — fix de T22.12 (#628), SPEC-034/AC13.
//
// No es parte de la aplicación: lo construye `backend/tests/test_traceability_abstention.py`
// para montar la pantalla real con una ejecución en curso. El test sustituye `EventSource`
// por uno guionizado y le inyecta la secuencia de eventos del backend.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { setAgentCatalog } from '../src/platform/agentCatalog';
import { setProjectNavItems, setNotificationRoute } from '../src/platform/navigation';
import { setRunTarget } from '../src/platform/runTarget';
import { I18nProvider, registerMessages } from '../src/platform/i18n';
import platformEs from '../src/platform/i18n/es.json';
import platformEn from '../src/platform/i18n/en.json';
import { MESSAGES, NAMESPACE } from '../src/projects/alejandria-magazine/i18n';
import {
  AGENT_CATALOG, AGENTS_WITH_OWN_RAG, PROJECT_NAV_ITEMS, PUBLISHER, RAG_OWNER, RUN_TARGET, notificationRoute,
} from '../src/projects/alejandria-magazine/catalog';
import { useAuthStore } from '../src/platform/store/authStore';
import { useProjectStore } from '../src/platform/store/projectStore';
import TraceabilityPage from '../src/projects/alejandria-magazine/pages/TraceabilityPage';
import '../src/index.css';

setAgentCatalog(AGENT_CATALOG, AGENTS_WITH_OWN_RAG, RAG_OWNER, PUBLISHER);
setProjectNavItems(PROJECT_NAV_ITEMS);
setNotificationRoute(notificationRoute);
setRunTarget(RUN_TARGET);
registerMessages('platform', { es: platformEs, en: platformEn });
registerMessages(NAMESPACE, { es: MESSAGES.es, en: MESSAGES.en });

useAuthStore.setState({
  user: { role: 'admin', full_name: 'Ada Prueba' }, token: 't', isAuthenticated: true, hasHydrated: true,
});
useProjectStore.setState({ activeProject: { id: 'p1', name: 'Proyecto' } });

const entrada = {
  pathname: '/dashboard/articles/17102b15-0000-4000-8000-000000000000/traceability',
  state: { flowSequence: ['investigador', 'redactor', 'revisor', 'formateador', 'publicador'] },
};

createRoot(document.getElementById('root')).render(
  <I18nProvider>
    <MemoryRouter initialEntries={[entrada]}>
      <Routes>
        <Route path="/dashboard/articles/:articleId/traceability" element={<TraceabilityPage />} />
      </Routes>
    </MemoryRouter>
  </I18nProvider>,
);
