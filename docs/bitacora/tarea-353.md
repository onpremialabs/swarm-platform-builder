# Tarea #353 — T16.2: Endpoint GET /dashboard/summary con aislamiento probado

## 2026-11-04 — Completada ✅

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **PR:** la de esta rama → `develop` (`Closes #353`)
- **Spec:** SPEC-028 · Épica E16

### Qué se hizo y dónde

**Backend** (archivos nuevos):

- `backend/app/platform/summary.py` — las dos consultas de agregación:
  - `project_summary(session, project_id)`: devuelve tokens, latencia p50, artículos
    analizados, ejecuciones y anomalías. Toda la consulta filtra por `project_id`; no
    puede incluir datos de otro proyecto.
  - `project_articles_summary(session, project_id)`: estado real del pipeline por
    artículo leyendo de `agent_run_steps`, no de `ArticleModel.status` que puede
    haber quedado desfasado (AC5).
  - Presupuestos (`MAX_REVIEW_LOOPS`, `LATENCY_BUDGET_MS`) declarados como constantes,
    no incrustados en la consulta — mismo patrón que `thresholds.yaml`.

- `backend/app/routers/dashboard.py` — `GET /dashboard/summary`:
  - Usa `Depends(get_project_context)`: el aislamiento es obligatorio y no se puede
    olvidar por diseño (AC1).
  - No reutiliza `GET /metrics` (anónima y sin proyecto).

- `backend/app/main.py` — registra el nuevo router.

**Tests** (`backend/tests/test_dashboard_summary.py`):
  - `test_summary_devuelve_solo_datos_del_proyecto_activo`: proyecto A con 300 tokens,
    proyecto B con 700; la portada de A no puede superar 300 (AC6).
  - `test_summary_proyecto_b_no_ve_proyecto_a`: verifica el caso inverso.
  - `test_summary_incluye_articulos_con_estado_del_pipeline`: el campo viene de
    `agent_run_steps`, no de `ArticleModel` (AC5).
  - `test_summary_sin_proyecto_devuelve_422`: sin `X-Project-Id` la dependencia rechaza.
  - `test_anomalias_detectan_paso_fallido`: un paso con `status='error'` incrementa
    `failed_step`; `checks_applied` tiene siempre 4 condiciones (AC3).

**Frontend**:
  - `frontend/src/platform/api/dashboard.js` (nuevo): un solo endpoint `getSummary()`.
  - `MetricsDashboardPage.jsx`: sustituye las N peticiones a `/agents/{id}/explain`
    por una sola llamada a `/dashboard/summary`. Las tarjetas de anomalías muestran las
    4 condiciones con su descripción y el aviso de que el cero tiene semántica.

### Definition of Done

- [x] AC1: `GET /dashboard/summary` con `X-Project-Id`, resuelto por `get_project_context`.
- [x] AC5: artículos muestran estado real de `agent_run_steps`.
- [x] AC6: test que crea ejecuciones en dos proyectos y verifica que no se cruzan.
- [ ] AC3 en la UI: anomalías visibles en la portada. ✅ (incluido en este PR)
- [ ] AC4 (estado del enjambre en tiempo real) — pendiente T16.4.
- [ ] AC7 (degradación cuando una fuente cae) — pendiente T16.6.
