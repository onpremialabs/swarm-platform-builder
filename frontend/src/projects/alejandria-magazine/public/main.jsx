import React from 'react';
import { setAgentCatalog } from '../../../platform/agentCatalog';
import { setProjectNavItems, setNotificationRoute } from '../../../platform/navigation';
import { setRunTarget } from '../../../platform/runTarget';
import { I18nProvider, registerMessages } from '../../../platform/i18n';
import platformEs from '../../../platform/i18n/es.json';
import platformEn from '../../../platform/i18n/en.json';
import { MESSAGES, NAMESPACE } from '../i18n';
import { AGENT_CATALOG, AGENTS_WITH_OWN_RAG, PROJECT_NAV_ITEMS, PUBLISHER, RAG_OWNER, RUN_TARGET, notificationRoute } from '../catalog';
import ReactDOM from 'react-dom/client';
import PublicApp from './PublicApp';
import '../../../index.css';

// El proyecto se da de alta en el builder antes de montar nada
// (SPEC-013/T8.6/AC7): el lienzo pregunta al pintar el primer nodo.
setAgentCatalog(AGENT_CATALOG, AGENTS_WITH_OWN_RAG, RAG_OWNER, PUBLISHER);
setProjectNavItems(PROJECT_NAV_ITEMS);
setNotificationRoute(notificationRoute);
setRunTarget(RUN_TARGET);
// La revista pública es otro punto de entrada (index.public.html): monta su propio
// proveedor y registra los mensajes, igual que main.jsx (SPEC-041/AC8).
registerMessages('platform', { es: platformEs, en: platformEn });
registerMessages(NAMESPACE, MESSAGES);

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <I18nProvider>
      <PublicApp />
    </I18nProvider>
  </React.StrictMode>
);
