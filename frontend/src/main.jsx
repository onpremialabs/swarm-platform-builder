import React from 'react';
import { setAgentCatalog } from './platform/agentCatalog';
import { setProjectNavItems, setNotificationRoute } from './platform/navigation';
import { setRunTarget } from './platform/runTarget';
import { I18nProvider, registerMessages } from './platform/i18n';
import platformEs from './platform/i18n/es.json';
import { MESSAGES as MAGAZINE_MESSAGES, NAMESPACE as MAGAZINE_NS } from './projects/alejandria-magazine/i18n';
import { AGENT_CATALOG, AGENTS_WITH_OWN_RAG, PROJECT_NAV_ITEMS, PUBLISHER, RAG_OWNER, RUN_TARGET, notificationRoute } from './projects/alejandria-magazine/catalog';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

// El proyecto se da de alta en el builder antes de montar nada
// (SPEC-013/T8.6/AC7): el lienzo pregunta al pintar el primer nodo.
setAgentCatalog(AGENT_CATALOG, AGENTS_WITH_OWN_RAG, RAG_OWNER, PUBLISHER);
setProjectNavItems(PROJECT_NAV_ITEMS);
setNotificationRoute(notificationRoute);
setRunTarget(RUN_TARGET);
// Mensajes: el builder aporta los suyos y el proyecto registra los suyos (SPEC-041/AC8).
registerMessages('platform', { es: platformEs });
registerMessages(MAGAZINE_NS, MAGAZINE_MESSAGES);

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </React.StrictMode>
);
