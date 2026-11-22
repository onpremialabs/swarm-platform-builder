# Tarea #530 — T22.7 — Registro de búsqueda reproducible en la traza y exportación

## 2026-11-22 16:00 — Completada ✅

- **Rama:** `feat/530-registro-busqueda-traza`
- **PR:** (ver enlace en la PR; cierra #530)
- **Spec/ADR:** SPEC-034 (AC6) · SPEC-014 (traza de explicabilidad) · SPEC-029 (integridad y exportación JSONL) · SPEC-013/T8.5 (aislamiento por proyecto)
- **Dependencias:** #524 (T22.1, capacidad `literature`) y #526 (T22.3, `search_logs`), cerradas; verificación de candidatos (T22.2, PR #609) ya en `develop`.

### Dónde estaba el problema
T22.1, T22.2 y T22.3 dejaron las piezas (descubrimiento, verificación y la tabla/función `record_search`) pero **nada las unía**: quien llamara a `search_literature` no dejaba rastro, y ni la traza de explicabilidad ni la exportación JSONL conocían las búsquedas. AC6 pide un registro «exportable y visible en la traza».

### Qué se hizo y por qué
- `backend/app/platform/capabilities/literature/run.py` (nuevo): `run_literature_search(session, project_id, query, sources, *, article_id, user_id, filters, ...)` ejecuta descubrimiento + verificación + registro y devuelve `LiteratureSearchOutcome`. Escribe el `SearchLog` también cuando la búsqueda es **parcial** (alguna base o el resolver fallan) o **fallida** (ninguna base responde, o algo revienta a medias: se registra y se propaga). Una consulta inválida o una base desconocida no es una búsqueda y no deja registro. De los errores de las bases solo se guarda `error_kind` (etiqueta cerrada), nunca el mensaje, que puede llevar la URL con clave o correo de contacto. Los filtros se sanean (`sanitize_filters`) y se registra el tope (`limit`) con el que se consultó.
- `backend/app/platform/explainability.py`: `StepAccumulator.searches` y `record_search()` (mismo patrón que `record_rag_hits`): la búsqueda se anota en el paso en curso y el orquestador la recoge al cerrar el paso (`use_cases.py`, los tres desenlaces), así el Investigador quedará trazado cuando T22.5 lo cablee, sin tocarlo. Solo viajan los campos de `CAMPOS_BUSQUEDA`. La cadena de integridad sube a **canon v2** (`searches` entra en el hash); la v1 se conserva intacta (`_CAMPOS_POR_VERSION`) para que las cadenas ya escritas sigan verificándose.
- `backend/app/models/agent_run_step.py` + migración `0009_step_searches.py`: columna `agent_run_steps.searches` (JSON, `server_default '[]'`). `AgentRunStepResponse.searches` y `ArticleExplainResponse.searches`.
- `backend/app/platform/library.py`: `search_record()` y `SEARCH_RECORD_FIELDS/VERSION`: el formato estable y versionado del registro (sin `user_id`; `searched_at` UTC con `Z`).
- `backend/app/routers/agents.py`: `GET /agents/{article_id}/searches` (exige `get_project_context` y que el artículo sea de quien pregunta o admin, como la traza); `/explain` y `/history/{execution_id}` devuelven `searches`; la exportación `export.jsonl` sube a `schema_version` 2: los pasos llevan `searches` y, tras ellos, una línea `{"type": "search", ...}` por búsqueda; la cabecera declara `searches`, `search_schema` y `search_schema_version`. Las búsquedas van enteras aunque `scope=last` (son el método del artículo, no de una ejecución). Filtradas por artículo y por el proyecto del artículo.
- `frontend/.../ArticleTraceHistoryPage.jsx`: tarjeta «Búsquedas bibliográficas» en la pestaña «Fuentes» (texto como nodos React, sin HTML ejecutable; clases existentes) y el JSONL de esa página incluye líneas `type: search`.
- `docs/governance/data-retention.md`: `searches` en el paso (90 días con la traza) y qué no guarda `search_logs`.
- `backend/tests/test_literature_search_record.py` (nuevo, 19 tests).

### Definition of Done
- [x] **AC6** — Given una búsqueda, When termina, Then se persiste un registro (bases, fecha, cadena, filtros, nº de resultados) exportable y visible en la traza — `run_literature_search` escribe `search_logs` (+ verificados, descartados con motivo y estado); visible en `/explain`, `/history/{id}`, pestaña «Fuentes» y `GET /agents/{id}/searches`; exportable en `export.jsonl` (líneas `type=search`) y en el JSONL del historial.

### Formato de la exportación (`schema_version` 2)
Línea 1 `{"type":"header", "schema":[...pasos...], "schema_version":2, "canon_version":2, "article_id", "scope", "executions", "steps", "searches":N, "search_schema":[...], "search_schema_version":1, "search_note", "note"}`; luego una línea por paso (campos de `EXPORT_SCHEMA`, ahora con `searches`); luego una por búsqueda: `{"type":"search","id","article_id","query","sources","filters","searched_at","status","result_count","verified_count","discarded","per_source"}`. `per_source[base] = {status, returned, verified, dropped, attempts, error_kind}`. El orden y los campos los fija `SEARCH_RECORD_FIELDS` (test de formato estable).

### Verificación
- `DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q tests/test_literature_search_record.py tests/test_integrity_chain.py tests/test_migrations.py tests/test_explain_endpoint.py tests/test_explainability_trace.py tests/test_article_trace_history.py tests/test_data_retention.py` → verde.
- Suite completa (`DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q`, desde `backend/`) → 1713 passed, 38 skipped, 1 failed: `test_no_tracked_databases.py::test_a_fresh_dev_database_is_created_and_migrated` (PermissionError de Windows al limpiar un directorio temporal; conocido, sin relación).
- `PYTHONIOENCODING=utf-8 python -m evals.agent_behavior.gate` → «Ninguna métrica por debajo de su umbral» (los golden son `handwritten`: dicen que la métrica funciona, no que el modelo se comporte así).
- `npm run build` y `npm run build:public` (desde `frontend/`) → OK.
- `python scripts/validate_specs.py` → OK.

### EDD (DoR/DoD de `edd-discipline.md`)
Toca la traza que usa el motor para todos los agentes. Qué puede romperse: que un paso se escriba mal o con otro hash (canon v2) y la cadena de integridad dé falsos «rota», o que un agente sin búsquedas cambie su traza. Lo miden `test_integrity_chain.py` (incluye v1 intacta y v2 con `searches`), `test_explainability_trace.py` y el gate `evals.agent_behavior.gate` (los golden no tocan la traza: confirma que el motor y los perfiles siguen igual). No se cambian perfiles ni prompts ni umbrales.

### Fuera de alcance / notas
- No se cablea al Investigador (T22.5), ni UI de curación (T22.8), ni descarga de PDFs (T22.10): `run_literature_search` queda listo para que T22.5 lo invoque.
- El registro guarda recuentos y motivos, no la lista de DOI verificados: reproducir la consulta es posible (bases, cadena, filtros, fecha), reproducir exactamente los mismos resultados no lo garantiza el servicio externo.
- Si `record_search` falla al persistir (BD), la excepción se propaga: no se devuelven resultados sin registro.
- Textos de la UI en español sin i18n propia (SPEC-041).
