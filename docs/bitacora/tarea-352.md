# Tarea #352 — T16.1: Magnitudes de la portada definidas y documentadas

## 2026-11-04 — Completada ✅

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **PR:** la de esta rama → `develop` (`Closes #352`)
- **Spec:** SPEC-028 · Épica E16

### Qué se hizo y dónde

AC2 — Cada magnitud de la portada tiene su definición explícita en el código y en la UI:

- `backend/app/platform/summary.py` (nuevo): cabecera de módulo documenta qué cuenta
  cada campo (`tokens_in`, `tokens_out`, `latency_p50_ms`, `articles_analyzed`,
  `agent_runs_total`) y de qué tabla sale. En particular, `latency_p50_ms` es la
  **mediana** de `agent_run_steps.latency_ms` (latencia de paso de agente, no de
  petición HTTP), lo que el spec señala como el caso confuso.
- `backend/app/routers/dashboard.py` (nuevo): docstring del endpoint repite las
  definiciones en el contrato HTTP para que no queden solo en el módulo interno.
- `frontend/src/platform/api/dashboard.js` (nuevo): comentario sobre cada campo del
  response explica qué cuenta y por qué el interceptor ya adjunta `X-Project-Id`.
- `frontend/src/projects/alejandria-magazine/pages/MetricsDashboardPage.jsx`
  (modificado): subtítulos de los tiles dicen explícitamente de qué es la magnitud
  ("Mediana de agent_run_steps (no HTTP)", "filas en agent_runs del proyecto", etc.).
- Sección de anomalías en la portada: 4 condiciones enumeradas con su descripción
  (`status ≠ completed`, `iteration ≥ 3`, `latency > 60 s`, `rag_sources vacío`).
  Un pie de página explica que el cero significa «se comprobó y no se encontró ningún
  caso» (AC3).

### Definition of Done

- [x] AC2: cada tarjeta tiene su magnitud definida y documentada en código y UI.
- [x] La latencia dice explícitamente de qué es y con qué estadístico.
- [ ] Revisión formal del documento de magnitudes fuera del código (pendiente Fase 3).
