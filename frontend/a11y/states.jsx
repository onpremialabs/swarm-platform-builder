// Banco de pruebas de los estados remotos — SPEC-003 / T7.3 / AC4.
//
// Igual que `harness.jsx`, no es parte de la aplicación: lo construye
// `backend/tests/test_async_states.py` para conducir los componentes **reales**
// de `src/components/ui/states.jsx`. Lo que se comprueba aquí no se puede leer
// en el código: que el estado de error se anuncia como tal, que no se parece al
// vacío, y que el botón de reintentar vuelve a lanzar la carga de verdad.
import React, { useCallback, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { FileText } from 'lucide-react';
import { AsyncState, EmptyState } from '../src/platform/components/ui/states';
import { registerMessages } from '../src/platform/i18n';
import platformEs from '../src/platform/i18n/es.json';
import '../src/index.css';

// Los componentes del builder piden sus textos al catálogo (T29.7): sin esto el
// banco enseñaría las claves.
registerMessages('platform', { es: platformEs });

/** Carga simulada: el resultado lo decide el banco, no la red. */
function Banco() {
  const [modo, setModo] = useState('vacio');   // vacio | cargando | error | datos
  const [reintentos, setReintentos] = useState(0);

  const reintentar = useCallback(() => setReintentos((n) => n + 1), []);

  return (
    <div style={{ padding: 40 }}>
      {['cargando', 'vacio', 'error', 'datos'].map((m) => (
        <button key={m} id={`modo-${m}`} className="btn btn-secondary" onClick={() => setModo(m)}>
          {m}
        </button>
      ))}
      <output id="reintentos">{reintentos}</output>

      <div id="zona">
        <AsyncState
          loading={modo === 'cargando'}
          error={modo === 'error' ? 'El servidor ha fallado al responder.' : null}
          isEmpty={modo !== 'datos'}
          onRetry={reintentar}
          loadingLabel="Cargando artículos…"
          empty={(
            <EmptyState
              icon={<FileText size={28} />}
              title="Sin artículos"
              description="Ejecuta un pipeline para generar el primero."
            />
          )}
        >
          <ul id="datos"><li>un artículo</li></ul>
        </AsyncState>
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<Banco />);
