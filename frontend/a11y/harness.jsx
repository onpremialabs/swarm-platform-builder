// Banco de pruebas de teclado del modal — SPEC-003 / T7.2 / AC2.
//
// No es parte de la aplicación: lo construye `backend/tests/test_modal_a11y.py`
// para conducir el componente **real** (`src/components/ui/Modal.jsx`) con un
// navegador de verdad. Un focus trap no se puede comprobar leyendo el código:
// depende de qué considera enfocable el navegador y de en qué orden.
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import Modal from '../src/platform/components/ui/Modal';
import { registerMessages } from '../src/platform/i18n';
import platformEs from '../src/platform/i18n/es.json';
import '../src/index.css';

// Los componentes del builder piden sus textos al catálogo (T29.7): sin esto el
// banco enseñaría las claves.
registerMessages('platform', { es: platformEs });

function Banco() {
  const [abierto, setAbierto] = useState(false);
  const [anidado, setAnidado] = useState(false);
  const [vacio, setVacio] = useState(false);
  const [cierres, setCierres] = useState(0);

  const cerrar = () => { setAbierto(false); setCierres((n) => n + 1); };

  return (
    <div style={{ padding: 40 }}>
      <button id="antes" className="btn btn-secondary">Antes</button>
      <button id="disparador" className="btn btn-primary" onClick={() => setAbierto(true)}>
        Abrir modal
      </button>
      <button id="disparador-vacio" className="btn btn-secondary" onClick={() => setVacio(true)}>
        Abrir modal sin controles
      </button>
      <button id="despues" className="btn btn-secondary">Después</button>
      <output id="cierres">{cierres}</output>

      {abierto && (
        <Modal onClose={cerrar} title="Diálogo de prueba">
          <div className="modal-body">
            <input id="campo-1" className="input" placeholder="uno" />
            <input id="campo-2" className="input" placeholder="dos" />
            <button id="anidar" className="btn btn-ghost" onClick={() => setAnidado(true)}>Anidar</button>
          </div>
          <div className="modal-footer">
            <button id="cancelar" className="btn btn-ghost" onClick={cerrar}>Cancelar</button>
          </div>
          {anidado && (
            <Modal onClose={() => setAnidado(false)} title="Diálogo interior">
              <div className="modal-body">
                <input id="campo-interior" className="input" placeholder="interior" />
              </div>
            </Modal>
          )}
        </Modal>
      )}

      {vacio && (
        <Modal onClose={() => setVacio(false)} showClose={false} ariaLabel="Sin controles">
          <div className="modal-body">Solo texto, nada enfocable.</div>
        </Modal>
      )}
    </div>
  );
}

createRoot(document.getElementById('root')).render(<Banco />);
