// Catálogo de agentes de AlejandrIA Magazine (SPEC-013 / T8.6 / AC7).
//
// Qué agentes tiene este proyecto, cómo se llaman y de qué color son. Es
// **dato del proyecto**, no del builder: otro proyecto trae otros agentes, y el
// lienzo del Flow Designer tiene que saber pintarlos igual.
//
// Antes esto estaba escrito tres veces, en tres formas distintas:
//
//   * `components/flow/AgentNode.jsx` → AGENT_META (icono, color, etiqueta, desc)
//   * `pages/ExecutionPage.jsx`       → AGENT_META (etiqueta, color)
//   * `pages/ArticleDetailPage.jsx`   → AGENT_LABELS (solo etiquetas)
//
// Tres copias es una que se actualiza y dos que no. Y la primera vivía dentro de
// un componente del builder, que es el equivalente en el frontend de lo que T8.3
// quitó del motor: la pieza reutilizable conociendo por su nombre a los agentes
// de un proyecto concreto.
//
// El espejo de este fichero en el backend es
// `backend/projects/alejandria-magazine/template.yaml`. Si se añade un agente
// allí, se añade aquí.
import React from 'react';
import { Search, PenLine, Eye, FileText, Send, BarChart2 } from 'lucide-react';
import { useArticleStore } from './store/articleStore';

/**
 * Panel que el editor de agentes muestra al abrir el investigador.
 *
 * Explica su pipeline interno —etapas, APIs y modelos por defecto—, así que es
 * contenido de **este** proyecto. Vivía dentro de `AgentEditorModal`, un
 * componente del builder, detrás de un `agentSlug === 'investigador'`.
 */
const PanelInvestigador = () => (
    <div style={{
      background: 'rgba(6,182,212,0.08)', border: '1px solid rgba(6,182,212,0.25)',
      borderRadius: 'var(--radius-md)', padding: 'var(--space-4)',
      fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', lineHeight: 1.7,
    }}>
      <strong style={{ color: 'var(--agent-research)', display: 'block', marginBottom: 6 }}>Pipeline del Investigador</strong>
      El agente ejecuta las siguientes etapas en orden:
      <ol style={{ margin: '8px 0 0 16px', display: 'flex', flexDirection: 'column', gap: 4 }}>
        <li><strong>RAG local</strong> — búsqueda vectorial (cosine similarity) en Qdrant con las keywords del artículo como query. Controlado por <em>Top-K RAG</em> y <em>coleción</em> del tab RAG.</li>
        <li><strong>EuropePMC</strong> — consulta la API REST de EuropePMC y recupera artículos científicos en abierto relacionados con las keywords.</li>
        <li><strong>Web scraping</strong> — si EuropePMC no aporta suficiente contexto, raspa arXiv, Wikipedia y Semantic Scholar. Cuando <em>Semantic re-rank</em> está activo, re-ordena las páginas descargadas por similitud coseno antes de pasarlas al modelo.</li>
        <li><strong>Síntesis con Ollama</strong> — combina todas las fuentes y genera el campo <code>research_data</code> que recibe el Redactor.
          <ul style={{ margin: '4px 0 0 16px', display: 'flex', flexDirection: 'column', gap: 2 }}>
            <li>Con fuentes externas: usa el modelo configurado (por defecto <code>mistral:7b</code>) con <code>num_ctx = 8192</code> y timeout de 10 min.</li>
            <li>Sin fuentes (solo parametric): usa <code>llama3.2:1b</code> como fallback con <code>num_ctx = 2048</code> y timeout de 2 min.</li>
          </ul>
        </li>
      </ol>
      <div style={{ marginTop: 8 }}>Gestiona los documentos propios del investigador en el tab <strong>RAG</strong>. Cambia el modelo de síntesis en <em>Configuración → Agentes → Investigador</em>.</div>
    </div>
);

export const AGENT_CATALOG = {
  investigador: {
    icon: Search,
    emoji: '🔍',
    color: 'var(--agent-research)',
    label: 'Investigador',
    desc: 'Busca contexto en RAG y APIs científicas',
    help: <PanelInvestigador />,
  },
  redactor: {
    icon: PenLine,
    emoji: '✍️',
    color: 'var(--agent-write)',
    label: 'Redactor',
    desc: 'Genera el borrador con el LLM configurado',
  },
  revisor: {
    icon: Eye,
    emoji: '👁️',
    color: 'var(--agent-review)',
    label: 'Revisor',
    desc: 'Evalúa calidad (score 0-100)',
  },
  formateador: {
    icon: FileText,
    emoji: '📐',
    color: 'var(--agent-format)',
    label: 'Formateador',
    desc: 'Aplica formato APA/IEEE/Vancouver',
  },
  publicador: {
    icon: Send,
    emoji: '🚀',
    color: 'var(--agent-publish)',
    label: 'Publicador',
    desc: 'Publica el artículo en la base de datos',
  },
};

/** Agentes que consultan el RAG por su cuenta (y no vía el estado del pipeline). */
export const AGENTS_WITH_OWN_RAG = new Set(['investigador']);

/** Etiqueta legible de un agente; su propio identificador si no está en el catálogo. */
export function agentLabel(agentId) {
  return AGENT_CATALOG[agentId]?.label || agentId;
}

/** Metadatos de un agente, con huecos vacíos en vez de `undefined`. */
export function agentMeta(agentId) {
  return AGENT_CATALOG[agentId] || {};
}

/**
 * Entradas de menú que este proyecto añade al dashboard del builder.
 *
 * «Artículos» es el objeto que produce el pipeline de AlejandrIA; otro proyecto
 * traerá el suyo, o ninguno. Por eso lo aporta el proyecto y no el menú.
 */
export const PROJECT_NAV_ITEMS = [
  {
    to: '/dashboard/articles',
    icon: <FileText size={17} />,
    label: 'Artículos',
    roles: ['admin', 'redactor', 'lector'],
  },
  {
    to: '/dashboard/traceability',
    icon: <BarChart2 size={17} />,
    label: 'Trazabilidad',
    roles: ['admin', 'redactor'],
  },
];

/**
 * Cómo crea y renombra AlejandrIA lo que produce su pipeline: **artículos**.
 *
 * El Flow Designer lo pide al pulsar «Ejecutar». Antes lo hacía él mismo,
 * importando el store de artículos desde el builder.
 */
export const RUN_TARGET = {
  label: 'artículo',
  create: (title) => useArticleStore.getState().createArticle(title),
  rename: (id, title) => useArticleStore.getState().updateArticle(id, { title }),
};

/** Agente al que pertenecen las fuentes que se suben desde el lienzo. */
export const RAG_OWNER = 'investigador';

/** Agente que publica: un flujo que lo incluye publica solo. */
export const PUBLISHER = 'publicador';

/** A dónde lleva una notificación sobre un artículo. */
export const notificationRoute = (articleId) => `/dashboard/articles/${articleId}`;
