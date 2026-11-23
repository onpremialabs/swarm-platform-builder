# Tarea #628 — T22.12 Mostrar la abstención como ejecución detenida, no completada

## 2026-11-23 11:40 — Completada

- **Rama:** `feat/628-abstencion-estado`
- **PR:** ver enlace en la PR abierta contra `develop` (`Closes #628`)
- **Spec/ADR:** SPEC-034 (AC7, AC13, apartado «Estado de la abstención»)
- **Dependencias:** #528 (T22.5) cerrada

### Dónde estaba el problema
- `backend/app/modules/agents/application/use_cases.py` — `make_node_wrapper` cerraba siempre el paso con
  `log_run_end(..., "completed")` y `log_run_step(status="completed")`, aunque el agente devolviera
  `abstained`; y `Orchestrator.run` emitía un `done` indistinguible tras el corte del motor
  (`engine/routing.py`, `engine/graph.py`).
- `frontend/.../ExecutionPage.jsx` — «Pipeline completado», insignia «Completo» y «Ver artículo» activo; los
  agentes sin ejecutar quedaban en «Esperando…».

### Comprobaciones previas (documentadas por exigencia de la spec)
1. **¿El estado es un enum nativo?** No. `agent_runs.status` y `agent_run_steps.status` son `String(16)`
   (`app/models/agent_run.py`, `agent_run_step.py`). La migración `0002_native_enum_labels` solo toca el enum
   `scientificformat`. `abstained` (9 caracteres) cabe. **Sin migración Alembic**; no hay cambio de esquema
   (`tests/test_migrations.py` sigue en verde).
2. **¿Entra en el canon de integridad?** `status` ya figura en `_CAMPOS_CANONICOS`, pero lo que obliga a subir
   `CANON_VERSION` es *ampliar la lista de campos o cambiar su formato*, no estrenar un valor de un campo ya
   canónico. Se mantiene `CANON_VERSION = 2`. Las cadenas ya escritas siguen verificándose y el paso abstenido
   se sella y verifica igual (test `test_el_paso_abstenido_entra_en_la_cadena_sin_subir_la_version`).
   `data-retention.md` no menciona valores de estado ni `CANON_VERSION`; no hay ventana ni tabla nueva, así que
   no requiere cambios.

### Qué se hizo y por qué
- `backend/app/platform/explainability.py`: `STATUS_ABSTAINED = "abstained"` y `ESTADOS_SIN_FALLO`
  (`completed`, `running`, `abstained`); `totals_of` ya no cuenta la abstención como paso fallido.
- `backend/app/modules/agents/application/use_cases.py`: si el agente devuelve `abstained`, el run y el paso se
  registran como `abstained` (también para la métrica del agente); `Orchestrator.run` cierra con
  `done` + `outcome: "abstained"`, `message`, `verified_sources`, `min_sources` y deja el log como «detenido por
  abstención». Una ejecución normal sigue emitiendo exactamente `{"type": "done"}`. El artículo no se toca
  (sigue en borrador) y el enrutador ya impedía ejecutar agentes posteriores.
- `backend/app/platform/summary.py`: `_execution_outcome` devuelve `status: "abstained"` (no `failed`) cuando
  el último paso se abstuvo, para la lista de ejecuciones y el historial; anomalías y contadores de error de
  agente/artículo usan `ESTADOS_SIN_FALLO`.
- `frontend/.../ExecutionPage.jsx`: estado `abstained`; cabecera «Pipeline detenido por abstención» con icono de
  aviso; aviso `role="alert"` «El Investigador se abstuvo» con `k/N` y el mensaje de qué hacer (texto, no solo
  color); sin «Ver artículo» ni «Completo» (se ofrece «Ver borrador» y «Volver al diseñador»); el paso del
  Investigador pasa a «Se abstuvo» y los demás a «No ejecutado» en lugar de «Esperando…». Se resetea al
  reejecutar/reanudar.
- `ArticleTraceHistoryPage.jsx` + `article-trace-history.css`, `TraceabilityPage.jsx`: etiqueta e insignia
  «Detenida por abstención» / «Se abstuvo» en la traza y en la lista de ejecuciones.
- `docs/specs/SPEC-034-...md`: se fija el nombre del estado y el resultado de las comprobaciones.
- `backend/tests/test_abstention_state.py` (nuevo, 6 tests).

### Definition of Done
- [x] **AC7** — la abstención (< N fuentes verificadas, `research.min_sources`) ya estaba implementada en T22.5;
  aquí se verifica que queda declarada en la traza y al autor (`abstained` + estado propio) y que no se
  sintetiza (el flujo se corta, `llamados == ["investigador"]`).
- [x] **AC13** estado propio distinto de completed/failed/cancelled, visible en lista de ejecuciones y traza —
  `abstained` en `agent_runs`, `agent_run_steps` y `_execution_outcome`.
- [x] **AC13** pantalla: aviso «El Investigador se abstuvo» con `k/N` y qué hacer, sin «Pipeline completado» ni
  «Ver artículo».
- [x] **AC13** agentes no ejecutados como «No ejecutado», no «Esperando/PENDIENTE».
- [x] **AC13** artículo en borrador y ningún agente posterior se ejecuta — test.
- [x] **AC13** una ejecución que completa no cambia — test de no regresión (`done` sin `outcome`, todo
  `completed`).

### Verificación
- `python -m pytest tests/test_abstention_state.py tests/test_dashboard_summary.py -q` → 17 passed.
- Suite completa backend (`DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q`, desde
  `backend/`) → **1 failed, 1871 passed, 38 skipped** en 10m47s. El único fallo es
  `test_no_tracked_databases::test_a_fresh_dev_database_is_created_and_migrated` (WinError 32, conocido en
  Windows). Una primera pasada con `-p no:logging` dio 17 errores de `caplog` y 6 fallos de
  `test_dashboard_summary` provocados por un error mío (`_completed` eliminado); corregido y repetida la suite
  entera.
- `npm run build` → OK; `npm run build:public` → OK.
- `python scripts/validate_specs.py` → OK.

### Fuera de alcance / notas
- **No probado en navegador real**: la pantalla solo se verificó con builds y revisión de código; no hay test de
  componente. Pendiente de comprobación visual de la pantalla de ejecución con un Investigador que se abstiene.
- Las ejecuciones antiguas (registradas como `completed` antes de este cambio) no se reescriben.
