// Banco de pruebas del panel «Por qué este resultado» — SPEC-014 / T9.2 / AC2.
//
// Igual que `harness.jsx` y `states.jsx`, no es parte de la aplicación: lo
// construye `backend/tests/test_explain_panel.py` para conducir el componente
// **real** (`src/platform/components/explain/ExplainPanel.jsx`) con un navegador.
//
// Lo que se comprueba aquí no se lee en el código: que el detalle de un paso se
// abre y se cierra de verdad —`hidden` lo decide el navegador—, que los dos
// scores que conviven no se pintan como el mismo número, y que un fallo de carga
// no acaba enseñando «sin traza que explicar», que es la mentira que T7.3 fue a
// arreglar y que este panel podría repetir.
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import ExplainPanel from '../src/platform/components/explain/ExplainPanel';
import { setAgentCatalog } from '../src/platform/agentCatalog';
import { registerMessages } from '../src/platform/i18n';
import platformEs from '../src/platform/i18n/es.json';
import '../src/index.css';

// Los componentes del builder piden sus textos al catálogo (T29.7): sin esto el
// banco enseñaría las claves.
registerMessages('platform', { es: platformEs });

// El panel pregunta al registro cómo se llama cada agente. Sin proyecto dado de
// alta enseñaría los identificadores crudos, así que el banco registra uno.
setAgentCatalog({
  investigador: { label: 'Investigador', color: 'var(--agent-research)' },
  redactor: { label: 'Redactor', color: 'var(--agent-write)' },
  revisor: { label: 'Revisor', color: 'var(--agent-review)' },
});

const TRAZA = {
  article_id: 'a1',
  title: 'Un artículo',
  executions: 2,
  scope: 'last',
  available: true,
  steps: [
    {
      id: 'p1', agent_name: 'investigador', step_index: 0, iteration: 0,
      status: 'completed', model: 'qwen2.5:3b', params: { temperature: 0.2 },
      input_digest: 'Título: Corales', output_text: 'material',
      tokens_in: 400, tokens_out: 120, latency_ms: 1500,
      rag_sources: [
        { doc_id: 'd1', title: 'Blanqueamiento de corales', score: 0.91, chunk_ids: [1, 2] },
      ],
      decision: null, rationale: null,
    },
    {
      id: 'p2', agent_name: 'revisor', step_index: 1, iteration: 1,
      status: 'completed', model: 'qwen2.5:3b', params: {},
      output_text: '{}', tokens_in: 300, tokens_out: 40, latency_ms: 900,
      rag_sources: [],
      decision: { score: 82, coherent: true, hitl_outcome: null },
      rationale: '- Falta metodología',
    },
  ],
  sources: [
    {
      doc_id: 'd1', title: 'Blanqueamiento de corales', authors: 'Autora',
      score: 0.91, chunk_ids: [1, 2], used_by: ['investigador'],
    },
  ],
  totals: {
    steps: 2, agents: ['investigador', 'revisor'], tokens_in: 700,
    tokens_out: 160, latency_ms: 2400, loops: 1, failed_steps: 0,
  },
};

const VACIA = {
  article_id: 'a1', title: 'Un artículo', executions: 0, scope: 'last',
  available: false, steps: [], sources: [],
  totals: { steps: 0, agents: [], tokens_in: 0, tokens_out: 0, latency_ms: 0, loops: 0, failed_steps: 0 },
};

function Banco() {
  const [modo, setModo] = useState('datos');   // datos | vacio | error

  // `useState` y no una constante: el panel guarda `load` en las dependencias de
  // su carga, así que cambiar de modo tiene que cambiar la identidad de la función.
  const cargar = React.useCallback(async (articleId, scope) => {
    if (modo === 'error') throw new Error('boom');
    if (modo === 'vacio') return VACIA;
    return scope === 'all'
      ? { ...TRAZA, scope: 'all', steps: [...TRAZA.steps, ...TRAZA.steps.map(
          (p) => ({ ...p, id: `${p.id}-bis` }))] }
      : TRAZA;
  }, [modo]);

  return (
    <div style={{ padding: 40, maxWidth: 900 }}>
      {['datos', 'vacio', 'error'].map((m) => (
        <button key={m} id={`modo-${m}`} className="btn btn-secondary" onClick={() => setModo(m)}>
          {m}
        </button>
      ))}
      <div id="zona" style={{ marginTop: 24 }}>
        <ExplainPanel articleId="a1" load={cargar} />
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<Banco />);
