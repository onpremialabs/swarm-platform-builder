// Diálogo modal accesible — SPEC-003 / T7.2 / AC2.
//
// Un modal accesible no es "un div encima": mientras está abierto, el resto de la
// página deja de existir para el teclado. Eso son cuatro cosas que hay que hacer
// juntas o no sirve ninguna, y por eso viven aquí y no repetidas en cada página:
//
//   1. El foco **entra** al abrir. Si no, `Tab` sigue recorriendo la página de
//      detrás y quien navega con teclado no llega nunca al diálogo.
//   2. El foco **no sale**. `Tab` en el último elemento vuelve al primero y
//      `Shift+Tab` en el primero va al último.
//   3. `Esc` cierra. Solo el modal de más arriba, si hay varios apilados.
//   4. El foco **vuelve** a lo que abrió el modal. Cerrar y quedarse en `body`
//      es perder el sitio: el siguiente `Tab` empieza desde el principio de la
//      página.
//
// `aria-modal="true"` y `role="dialog"` van en el **panel**, no en el velo: el
// velo es la parte oscurecida, y anunciarlo como el diálogo mete el fondo dentro
// de lo que el lector de pantalla considera el contenido del diálogo.
import React, { useCallback, useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';
import { useTranslation } from '../../i18n';

/** Selector de lo que el navegador considera enfocable con `Tab`. */
const ENFOCABLES = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
  '[contenteditable="true"]',
].join(',');

/**
 * Pila de modales abiertos. `Esc` y el bloqueo de scroll son globales, así que
 * necesitan saber cuál es el de arriba: con dos modales anidados, `Esc` debe
 * cerrar solo el interior, y restaurar el scroll al cerrar el interior dejaría
 * la página de detrás desplazándose bajo el exterior.
 */
const pila = [];

/**
 * El `overflow` que tenía el body **antes del primer** modal. Guardarlo por
 * instancia no vale: React desmonta el contenedor antes que su hijo, así que al
 * cerrar dos modales anidados el último en limpiar es el interior, que había
 * capturado el `hidden` que puso el exterior — y la página se quedaba sin scroll
 * para siempre. Comprobado con teclado en Chromium, no deducido.
 */
let scrollPrevio = '';

function enfocables(raiz) {
  if (!raiz) return [];
  return Array.from(raiz.querySelectorAll(ENFOCABLES)).filter(
    (el) => el.offsetParent !== null || el === document.activeElement,
  );
}

export default function Modal({
  open = true,
  onClose,
  title,
  labelledBy,
  ariaLabel,
  size = 'md',
  showClose = true,
  headerActions = null,
  initialFocusRef,
  className = '',
  panelStyle,
  children,
}) {
  const { t } = useTranslation();
  const panelRef = useRef(null);
  // Identidad estable de esta instancia dentro de `pila`.
  const identidadRef = useRef(null);
  if (identidadRef.current === null) identidadRef.current = {};
  const identidad = identidadRef.current;
  const disparadorRef = useRef(null);
  const pulsadoEnVelo = useRef(false);
  const idGenerado = useId();
  const idTitulo = labelledBy || (title ? `modal-title-${idGenerado}` : undefined);

  // Registro en la pila + bloqueo de scroll del fondo.
  useEffect(() => {
    if (!open) return undefined;
    if (pila.length === 0) scrollPrevio = document.body.style.overflow;
    pila.push(identidad);
    document.body.style.overflow = 'hidden';
    return () => {
      const indice = pila.indexOf(identidad);
      if (indice !== -1) pila.splice(indice, 1);
      if (pila.length === 0) document.body.style.overflow = scrollPrevio;
    };
  }, [open, identidad]);

  // El foco entra al abrir y vuelve al disparador al cerrar.
  useEffect(() => {
    if (!open) return undefined;
    disparadorRef.current = document.activeElement;

    // En el primer render los hijos ya están montados, pero un autoFocus del
    // navegador puede llegar después; el rAF deja que se resuelva antes.
    const marco = requestAnimationFrame(() => {
      const preferido = initialFocusRef?.current;
      const destino = preferido || enfocables(panelRef.current)[0] || panelRef.current;
      destino?.focus();
    });

    return () => {
      cancelAnimationFrame(marco);
      const volverA = disparadorRef.current;
      // El disparador puede haber desaparecido con el propio cambio (borrar una
      // fila desde su modal); solo se devuelve el foco si sigue en el documento.
      if (volverA && document.contains(volverA)) volverA.focus();
    };
  }, [open, initialFocusRef]);

  const alPulsarTecla = useCallback(
    (evento) => {
      if (evento.key === 'Escape') {
        // Solo cierra el de más arriba. El manejador vive en el panel, pero un
        // modal anidado se renderiza **dentro** del exterior: sin esta guarda, un
        // `Esc` mientras el foco sigue en el exterior cerraría los dos de golpe.
        if (pila[pila.length - 1] !== identidad) return;
        evento.stopPropagation();
        onClose?.();
        return;
      }
      if (evento.key !== 'Tab') return;

      const candidatos = enfocables(panelRef.current);
      if (candidatos.length === 0) {
        // Un modal sin nada enfocable: el foco se queda en el panel y `Tab` no
        // puede escaparse a la página de detrás.
        evento.preventDefault();
        panelRef.current?.focus();
        return;
      }
      const primero = candidatos[0];
      const ultimo = candidatos[candidatos.length - 1];
      const activo = document.activeElement;

      if (evento.shiftKey && (activo === primero || activo === panelRef.current)) {
        evento.preventDefault();
        ultimo.focus();
      } else if (!evento.shiftKey && activo === ultimo) {
        evento.preventDefault();
        primero.focus();
      } else if (!panelRef.current?.contains(activo)) {
        // El foco se fue fuera (clic en el fondo, extensión del navegador…).
        evento.preventDefault();
        primero.focus();
      }
    },
    [onClose, identidad],
  );

  if (!open) return null;

  const cerrarDesdeVelo = (evento) => {
    // Solo cierra si el gesto **empieza y acaba** en el velo. Con `onClick` a
    // secas, seleccionar texto dentro del panel y soltar fuera cerraba el modal
    // y se perdía lo escrito.
    if (evento.target !== evento.currentTarget) return;
    if (!pulsadoEnVelo.current) return;
    pulsadoEnVelo.current = false;
    onClose?.();
  };

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(evento) => {
        pulsadoEnVelo.current = evento.target === evento.currentTarget;
      }}
      onClick={cerrarDesdeVelo}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={idTitulo}
        aria-label={idTitulo ? undefined : ariaLabel}
        tabIndex={-1}
        className={`modal${size === 'lg' ? ' modal-lg' : ''}${className ? ` ${className}` : ''}`}
        style={panelStyle}
        onKeyDown={alPulsarTecla}
      >
        {(title || showClose || headerActions) && (
          <div className="modal-header">
            {title ? <h3 id={idTitulo}>{title}</h3> : <span />}
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
              {headerActions}
              {showClose && (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm btn-icon"
                  onClick={() => onClose?.()}
                  aria-label={t('modal.close')}
                >
                  <X size={16} />
                </button>
              )}
            </div>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
