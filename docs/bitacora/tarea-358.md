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
