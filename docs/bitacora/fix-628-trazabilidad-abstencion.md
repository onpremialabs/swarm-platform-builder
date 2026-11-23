# Fix de T22.12 (#628) — «Trazabilidad y observabilidad» presentaba la abstención como completada

## 2026-11-23 16:10 — Completada

- **Rama:** `fix/628-trazabilidad-abstencion`
- **PR:** ver la PR abierta contra `develop` (`Refs #628`; el issue ya está cerrado, no se reabre ni se cierra de nuevo)
- **Spec/ADR:** SPEC-034 (AC7, AC13, «Estado de la abstención»)
- **Dependencias:** T22.12 (#628, PR #629), ya integrada

### Cómo se descubrió
Captura de la persona usuaria del 2026-11-23: la ejecución `17102b15` en la pantalla «Trazabilidad y observabilidad»
(pestaña «Ejecución en tiempo real») mostraba el Investigador como **COMPLETADO**, «Pipeline completado», «Ver
artículo» activo y los demás pasos «PENDIENTE», aunque el backend había registrado la ejecución como `abstained`.
T22.12 había verificado la abstención en `ExecutionPage` y en el historial, no en esta segunda pantalla.

### Dónde estaba el problema
`frontend/src/projects/alejandria-magazine/pages/TraceabilityPage.jsx` tiene **su propio** manejador
`evtSource.onmessage`, duplicado del de `ExecutionPage.jsx`. T22.12 solo actualizó este último. En
`TraceabilityPage` no había rama para el evento `abstained` y la rama `done` ignoraba `outcome`; el backend sí emite
bien `abstained` y luego `done` con `outcome: "abstained"`, `message`, `verified_sources` y `min_sources`. Resultado:
el `agent_end` marcaba el paso «completed», el `done` ponía `done=true` sin más, la insignia de cabecera decía
«Completado», se ofrecía «Ver artículo» y los pasos sin ejecutar se quedaban en «waiting» («Pendiente»).

### Qué se hizo y por qué
- `frontend/src/projects/alejandria-magazine/pipelineEvents.js` (nuevo): funciones **puras** que interpretan los
  eventos de cierre (`isAbstainedEvent`, `isAbstainedDone`, `abstentionNotice`, `settleUnrunSteps`). Es la lógica
  que antes estaba copiada; ahora la usan las dos pantallas. Sin React ni i18n, para probarla con `node --test`.
  Extracción de bajo riesgo: solo mueve las condiciones y la transformación de pasos; los manejadores siguen en cada
  página (no se unifica el resto del SSE, que difiere: la traza lleva tiempos, iteraciones y métricas).
- `TraceabilityPage.jsx`: estado `abstained`; rama `abstained` (aviso + paso «Se abstuvo»); rama `done` con
  `outcome === 'abstained'` (pasos sin ejecutar a «No ejecutado», sin «completado»); efecto que lleva los pasos a
  `not_run` si el stream se corta tras `abstained` sin `done` (`onerror` ya marcaba `done`); insignia de cabecera
  «Detenida por abstención»; aviso `role="alert"` con k/N y el mensaje; «Ver borrador» + «Volver al diseñador» en
  lugar de «Ver artículo»; sin bloque de asignar revisor; insignia de la vista previa «Detenido» en lugar de
  «Borrador»; reinicio de `abstained`/`gateNotice` al reejecutar o reanudar. `STATUS_KEYS` incluye `not_run`.
- `ExecutionPage.jsx`: pasa a usar el módulo compartido (mismo comportamiento, menos duplicación).
- `i18n/es.json` y `i18n/en.json` (`en` es copia provisional en español): `traceability.badge.abstained` y
  `traceability.status.not_run`; el resto de textos reutiliza claves `execution.*`. **Sin literales nuevos en
  `.jsx`**: `python scripts/check_i18n.py` pasa sin ampliar la línea base (deuda 2, la misma).
- `frontend/src/index.css`: `.trace-step-not_run` y `.trace-step-abstained` (los pasos sin clase quedaban sin
  estilo propio).
- Revisión de las demás pantallas: `grep` de `EventSource`, `getStreamUrl`, `getStreamTicket`, `'done'`, `agent_end`
  en `frontend/src`. **Solo `ExecutionPage` y `TraceabilityPage` abren el stream**; `platform/api/agents.js` solo
  define el cliente y los `'done'` de `gate.js` son estados de una etapa de interfaz, no eventos del pipeline.
  `ArticleTraceHistoryPage` ya mostraba el estado `abstained` desde T22.12. No hay más pantallas afectadas.

### Tests que habrían detectado el defecto
- `backend/tests/test_stream_pages_abstention.py` (estático, siempre corre): recorre **todo** `frontend/src`; cada
  `.jsx` con `new EventSource(` debe tratar `abstained` y el `outcome` de `done`, tener estado propio, pasos
  `not_run`, `!abstained` en los controles de «completado» y un aviso `alert`. Verificado en rojo: con la
  `TraceabilityPage.jsx` anterior el test falla (1 failed); con el arreglo pasa. También ejecuta el test de node.
- `frontend/src/projects/alejandria-magazine/pipelineEvents.test.mjs` (`node --test`, 4 tests).
- `backend/tests/test_traceability_abstention.py` + banco `frontend/a11y/trace.jsx` / `trace.html` (navegador real
  con Playwright, se salta sin Chromium): monta la pantalla real con un `EventSource` guionizado y le inyecta
  `agent_start, log, agent_end, abstained, done{outcome:'abstained'}`; comprueba que no hay «Completado» ni
  «Pipeline completado» ni «Ver artículo», que sí hay el aviso (1/3 + mensaje), «Se abstuvo» y 4 pasos «No
  ejecutado»; el corte tras `abstained` sin `done`; y que una ejecución normal sigue completándose.

### Definition of Done
- [x] `TraceabilityPage` con el mismo comportamiento que `ExecutionPage` ante la abstención (pasos, insignia, aviso,
  botones, corte del stream).
- [x] i18n con paridad es/en y sin literales nuevos (`check_i18n.py`).
- [x] Resto de pantallas con stream revisadas (ninguna más afectada).
- [x] Duplicación reducida con un módulo puro y su test de node.
- [x] Test estructural que falla si una página con `EventSource` ignora `abstained`/`outcome`.
- [x] Verificación en navegador real.

### Deuda que se deja
Los manejadores SSE de las dos páginas siguen siendo dos copias (`agent_start`, `agent_end`, `await_decision`,
`gate_failed`, `done_error`, `cancelled`...). Unificarlos en un hook (`usePipelineStream`) exige reconciliar lo que
solo hace la traza (tiempos, iteraciones, métricas, `currentAgentRef`) y se deja para una tarea propia; el test
estructural protege entretanto contra una tercera divergencia en el cierre.

### Verificación
- `npm run build` y `npm run build:public` (frontend): OK.
- `python scripts/check_i18n.py`: OK (paridad; deuda de literales en línea base: 2, sin ampliar).
- `node --test frontend/src/projects/alejandria-magazine/pipelineEvents.test.mjs`: 4 de 4.
- Navegador real (Chromium + Playwright, banco `frontend/a11y/trace.jsx`):
  `python -m pytest -q tests/test_traceability_abstention.py` desde `backend/`: 3 de 3. Contra la
  `TraceabilityPage.jsx` anterior fallan 2 de 3 (abstención y corte del stream), con la nueva pasan.
- `python -m pytest -q tests/test_traceability_abstention.py tests/test_stream_pages_abstention.py
  tests/test_language_selector.py tests/test_async_states.py tests/test_modal_a11y.py tests/test_i18n_checks.py
  tests/test_frontend_gate.py`: 66 passed, 14 skipped.
- Suite completa (`DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q`, una vez, desde `backend/`):
  1929 passed, 38 skipped, 1 failed. El fallo es `test_no_tracked_databases.py::test_a_fresh_dev_database_is_created_and_migrated`
  (`PermissionError WinError 32` al borrar el `dev.db` temporal en Windows; fallo conocido del entorno, ajeno a este cambio).
  Esa pasada se lanzó antes de añadir `test_traceability_abstention.py`, que se ejecutó aparte (arriba).

### Notas
- Los badges se muestran en mayúsculas por CSS (`text-transform`); los tests de navegador comparan con `text_content`.
- `en.json` del proyecto sigue siendo una copia provisional en español (T29.9 la traducirá).
