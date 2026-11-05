# Tarea #369 — T18.6: Seguimiento de ejecución con bucle de revisión y progreso honesto

## 2026-11-04 — Completada ✅

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **PR:** la de esta rama → `develop` (`Closes #369`)
- **Spec:** SPEC-030 · Épica E18

### Qué se hizo y dónde

`frontend/src/projects/alejandria-magazine/pages/TraceabilityPage.jsx`:

**AC4 — Bucle revisor→redactor visible:**
- Nuevo estado `iterationCount: {agentName: n}`: se incrementa en cada evento
  `agent_start` del SSE.
- Cuando `redactor` arranca por segunda vez (o más), el log muestra
  *"Redactor: pasada 2 del bucle revisor→redactor"* en color de advertencia.
- La tarjeta del agente muestra *"Pasada N del bucle revisor→redactor"* debajo del
  nombre, resaltado en naranja, en lugar de la descripción genérica.
- La pausa por `await_decision` ya emitía el log *"El pipeline espera tu decisión
  (coherencia)"* y mostraba el panel HITL; ese comportamiento se mantiene sin cambios.

**AC5 — Progreso honesto, sin porcentajes de tokens ni de tiempo:**
- Eliminado el cálculo `Math.round(completedCnt / metricsAgents.length * 100)` que
  producía un "X %" sin respaldo real (el pipeline no emite unidades de trabajo
  fraccionadas).
- El tile de "Progreso" se renombra a **"Agentes completados"** y muestra
  *"3 / 5 agentes"*, que es una afirmación verificable: cada agente emite `agent_end`
  o `agent_error` al terminar, que es la unidad de trabajo real del pipeline.
- La barra indeterminada (`animate-pulse`) permanece para los agentes en ejecución:
  no afirma cuánto falta, solo que está activo.
- Comentario en código: *"no se deriva un % de tokens ni de tiempo (T18.6 AC5)"*.

### Qué NO se hizo

- **T18.4 — Evento SSE de progreso fraccionado**: el Redactor no emite aún unidades
  de sección (AC5 completo); requiere cambios en el adapter del Redactor y un evento
  nuevo en el SSE. Queda como T18.4, pendiente.
- **T18.1–T18.3, T18.5**: alcance de documento por ejecución, variante del GraphSpec,
  notas, pantalla de subida. Pendientes en sus propias issues.

### Definition of Done

- [x] AC4: el bucle revisor→redactor se muestra explícitamente en la UI.
- [x] AC5 parcial: no hay porcentaje derivado de tokens ni de tiempo.
- [x] AC5 completo: T18.4 (#367) ya está hecha — ver más abajo.

---

## 2026-11-05 — AC5 completo al cerrarse T18.4

Cuando se escribió esto, la mitad fraccional de AC5 no se podía cumplir: ningún
agente emitía unidades de trabajo, así que la interfaz mostraba estado
indeterminado y «X / Y agentes». Eso **ya satisfacía el criterio** —lo que AC5
exige es no fingir precisión—, pero dejaba su primera rama sin ejercitar.

Con T18.4 (#367) el Redactor emite `progress` al detectar el encabezado de cada
sección, y `TraceabilityPage` pinta «sección N de M» cuando llega ese evento y
una barra indeterminada cuando no. Las dos ramas del criterio están cubiertas:

- **Con unidades reales** → progreso fraccional, derivado de un hecho observado.
- **Sin unidades** → indeterminado, que es la respuesta honesta.

La prohibición sigue respetada: no hay ningún porcentaje derivado de tokens
emitidos ni de tiempo transcurrido, y hay dos tests en
`tests/test_progress_units.py` que fallarían si alguien lo introdujera.

Con esto se cierra también la dependencia formal de #369 sobre #367.
