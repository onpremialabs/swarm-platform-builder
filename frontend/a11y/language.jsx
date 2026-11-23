// Banco del selector de idioma — SPEC-041 / T29.10 / AC1, AC6, AC12.
//
// No es parte de la aplicación: lo construye `backend/tests/test_language_selector.py`
// para conducir las pantallas **reales** (DashboardPage con su menú y su barra
// superior, FlowDesignerPage con paleta, nodos y botón Ejecutar, MagazinePage)
// con el mismo cableado que `main.jsx`. Una diferencia deliberada: `en.json` es hoy
// una copia en español (T29.9 la traducirá), así que aquí cada cadena inglesa
// lleva el prefijo «[en] » para que se vea qué se ha repintado y qué no.
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
import { useFlowStore } from '../src/platform/store/flowStore';
import { useProjectStore } from '../src/platform/store/projectStore';
import DashboardPage from '../src/platform/pages/DashboardPage';
import FlowDesignerPage from '../src/platform/pages/FlowDesignerPage';
import MagazinePage from '../src/projects/alejandria-magazine/pages/MagazinePage';
import '../src/index.css';

const marcar = (obj) => JSON.parse(JSON.stringify(obj), (_k, v) => (typeof v === 'string' ? `[en] ${v}` : v));

setAgentCatalog(AGENT_CATALOG, AGENTS_WITH_OWN_RAG, RAG_OWNER, PUBLISHER);
setProjectNavItems(PROJECT_NAV_ITEMS);
setNotificationRoute(notificationRoute);
setRunTarget(RUN_TARGET);
registerMessages('platform', { es: platformEs, en: marcar(platformEn) });
registerMessages(NAMESPACE, { es: MESSAGES.es, en: marcar(MESSAGES.en) });

useAuthStore.setState({
  user: { role: 'admin', full_name: 'Ada Prueba' }, token: 't', isAuthenticated: true, hasHydrated: true,
});
useProjectStore.setState({ activeProject: { id: 'p1', name: 'Proyecto' } });

// Un nodo ya en el lienzo, con el texto copiado del catálogo al crearlo (como al arrastrarlo).
useFlowStore.setState({
  draftNodes: [{
    id: 'n1', type: 'agent', position: { x: 80, y: 80 },
    data: { agentId: 'investigador', label: AGENT_CATALOG.investigador.label, desc: AGENT_CATALOG.investigador.desc, icon: AGENT_CATALOG.investigador.icon },
  }],
  draftEdges: [],
});

const ruta = new URLSearchParams(location.search).get('ruta') || '/magazine';

createRoot(document.getElementById('root')).render(
  <I18nProvider>
    <MemoryRouter initialEntries={[ruta]}>
      <Routes>
        <Route path="/magazine" element={<MagazinePage />} />
        <Route path="/dashboard" element={<DashboardPage />}>
          <Route path="flow-designer" element={<FlowDesignerPage />} />
        </Route>
      </Routes>
    </MemoryRouter>
  </I18nProvider>,
);
