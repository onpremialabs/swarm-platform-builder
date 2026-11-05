# Tarea #358 — T17.1: Vista de trazabilidad del proyecto sobre agent_run_steps

## 2026-11-04 — Completada ✅ (parcial — ver notas)

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **PR:** la de esta rama → `develop` (`Closes #358`)
- **Spec:** SPEC-029 · Épica E17

### Qué se hizo y dónde

AC1 — Vista de trazabilidad que lee `agent_run_steps` (no OpenTelemetry):

- `frontend/src/projects/alejandria-magazine/pages/TraceabilityPage.jsx` (nuevo):
  página de 3 pestañas para un artículo dado:
  1. **Ejecución en tiempo real**: tarjetas de agentes por SSE, terminal de eventos,
     detección del bucle revisor→redactor.
  2. **Trazas por agente**: `ExplainPanel` cargado con `GET /agents/{id}/explain`,
     que lee directamente de `agent_run_steps`.
  3. **Métricas**: gráficos de latencia y tokens por agente desde la misma traza.

  El panel usa `display:none/block` (no `&&`), así que `ExplainPanel` permanece
  montado aunque no sea la pestaña activa — evita el bucle remount de React.

- El aislamiento es inherente: `GET /agents/{id}/explain` está bajo
  `get_project_context`, y `article_id` pertenece al proyecto activo.
  El test de aislamiento de esta ruta ya existe en `test_explain_endpoint.py`.

- `frontend/src/projects/alejandria-magazine/catalog.jsx`: enlace de sidebar con
  `BarChart2` a `/dashboard/traceability`.

- `frontend/src/projects/alejandria-magazine/pages/MetricsDashboardPage.jsx` (nuevo):
  vista transversal del proyecto en `/dashboard/traceability` con todos los artículos.

### Qué NO se hizo

- **Vista de proyecto completa con listado de ejecuciones sin seleccionar artículo**:
  requiere endpoint propio no existente todavía. Actualmente la vista es
  per-artículo (articulo se elige en la tabla de MetricsDashboardPage).
- **T17.2 cadena SHA-256** / T17.3 verificación / T17.4 exportación JSONL / T17.5 log
  en vivo por proyecto / T17.6 pestaña de integridad: quedan para issues separadas.

### Definition of Done

- [x] AC1 parcial: vista de ejecuciones por artículo leyendo `agent_run_steps`.
- [ ] AC1 completo: listado de ejecuciones del **proyecto** sin filtrar por artículo.
- [ ] AC2–AC7: T17.2 a T17.6, abiertos como issues separadas.

---

## 2026-11-05 — AC1 completo

### Lo que faltaba

La portada listaba **artículos**, no ejecuciones. `project_articles_summary`
agrupa por `article_id`, así que un artículo reejecutado sumaba las dos pasadas en
una sola fila y la segunda desaparecía. AC1 pide listar «las ejecuciones del
proyecto con sus pasos, estado y coste», y una reejecución es precisamente lo que
hay que poder ver por separado.

En la base de desarrollo eran 3 artículos de 9 los que estaban reejecutados, uno de
ellos tres veces: 13 ejecuciones escondidas en 9 filas.

### Qué se hizo y dónde

- `backend/app/platform/summary.py` — nueva `project_executions()`: una fila por
  pasada, con sus pasos, agentes, tokens, latencia, vueltas del bucle y estado.
  La separación la decide `group_executions()` de `platform/explainability.py`,
  que ya existía y es la que usa `/explain`; SPEC-029 §4 pide explícitamente ese
  mismo criterio para que una reejecución no se lea como cadena rota.
- `backend/app/routers/dashboard.py` — devuelve `executions` junto a `articles`.
  Se mantienen las dos: AC5 de SPEC-028 pide la lista de **papers** con su estado,
  y AC1 de SPEC-029 pide la de **ejecuciones**. Son preguntas distintas.
- `MetricsDashboardPage.jsx` — sección «Ejecuciones del proyecto». Cuando un
  artículo tiene varias, cada fila dice «pasada N de M», que es lo que distingue
  una reejecución de un retroceso inexplicado.

### Un tile que mentía

`agent_runs_total` contaba filas de `agent_runs` bajo la etiqueta «Ejecuciones de
pipeline». Pero `log_run_start` mina un `run_id` **por paso**, no por ejecución
—lo advierte la docstring de `group_executions`—, así que el número era el de
pasos: la portada decía 65 ejecuciones donde había 13. Pasa a llamarse
`executions_total` y se calcula con la misma agrupación.

Esto también explica por qué AC2 (T16.1) no bastaba con documentar la magnitud:
estaba documentada y era falsa.

### Un fallo que el test destapó al escribirse

Al añadir `test_reejecucion_aparece_como_dos_ejecuciones` el endpoint devolvió 500:
el `select` de `project_summary` no pedía `step_index`, que es lo que
`group_executions` lee. No fallaba antes porque con **un solo paso** por artículo
el `or` de la condición hace cortocircuito y nunca llega a mirarlo; los cinco tests
que ya había usan un paso por proyecto.

### Arreglos de ruta

Tres tests que fallaban en la suite completa, dos de ellos por culpa de esta rama:

- `test_frontend_layers::test_el_catalogo_no_esta_duplicado` — `MetricsDashboardPage`
  y `TraceabilityPage` traían cada una su `AGENT_COLORS`, copia de los colores que
  el catálogo ya define. Sustituido por `agentMeta(n).color`.
- `test_flow_designer_run_state` — el lienzo navega desde esta rama a
  `/dashboard/execution/…` (la vista nueva), y el test seguía buscando
  `/execution/…` contra `ExecutionPage`. Apunta ya al destino real.
- `test_dashboard_summary` — los cinco daban ERROR al correr la suite entera.
  `engine` es un singleton de módulo y lo fija el primer test que importe
  `app.core.database`; el fixture borraba *su* fichero mientras el engine usaba
  otro, y las filas del test anterior seguían ahí. Ahora vacía el esquema en vez
  del fichero, que además evita el `PermissionError` de Windows.

### Definition of Done

- [x] AC1: lista las **ejecuciones** del proyecto, con pasos, estado y coste.
- [x] Leído de `agent_run_steps`, no de OpenTelemetry.
- [x] Aislamiento por proyecto, cubierto por los tests de T16.2.
- [x] Una reejecución se ve como pasada aparte (`test_reejecucion_…`).
- [ ] AC2–AC7: T17.2 a T17.6, abiertas como issues separadas.
