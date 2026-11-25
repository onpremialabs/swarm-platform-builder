# Tarea #657 — T24.9: Redactor, detectar salida truncada y resolver el límite de salida por la cascada

## 2026-11-25 06:30 — Completada ✅

- **Rama:** `fix/657-redactor-truncado`
- **PR:** pendiente de número → `develop` (`Closes #657`)
- **Spec/ADR:** SPEC-036 (AC10 y «Decisión por omisión y truncado»); SPEC-014/T9.1 (traza)
- **Dependencias:** ninguna

### Dónde estaba el problema
`backend/app/modules/agents/adapters/redactor.py` fijaba `num_ctx=4096` en la generación y en la
ampliación de palabras, y daba por bueno lo que devolviera el stream. En una prueba de punta a punta
con `qwen3.5:9b` la salida se cortó a ≈2046 tokens («…métricas como el tiempo de», sin Discusión) y el
borrador siguió al Revisor y al Publicador. `llm.py` descartaba el motivo de parada (`done_reason`)
del proveedor.

### Qué se hizo y por qué
- `backend/app/platform/llm.py`: `resolve_agent_num_ctx` y `resolve_agent_max_output_tokens`
  (cascada ajustes de la ejecución → `.agent.md` → defecto, validadas, acotadas por
  `model_context_window`), `validate_output_limit`, `enlarge_output_budget` (reintento: el doble sin
  pasar de la ventana). `call_llm_stream` acepta `max_tokens` opcional (Ollama `num_predict`,
  Anthropic/OpenAI su tope; si es `None` no se envía nada) y expone el motivo de parada por
  `last_stop_reason()` (ContextVar: `done_reason`, `stop_reason`, `finish_reason`) sin cambiar la
  firma para otros llamadores.
- `backend/app/platform/draft_integrity.py` (nuevo): `detect_truncation` — motivo de parada
  `length`/`max_tokens`; sin motivo, heurística (faltan secciones del IMRaD o frase sin cierre). Un
  motivo de fin natural (`stop`) no se cuestiona por la heurística.
- `adapters/redactor.py`: cada generación se verifica; si se trunca, se anota en la traza, se
  reintenta **una vez** con más presupuesto y, si persiste o no hay más presupuesto que dar, el paso
  **falla** con motivo (no hay `draft_text` que llegue al Revisor). Una ampliación de palabras truncada
  se descarta y se conserva el borrador entero. Plantilla propia: no se exige el IMRaD.
- `platform/explainability.py` + `use_cases.py`: `record_truncation`/`with_truncations` anotan cada
  intento cortado en la columna `decision` (clave `truncation`), tanto en pasos completados como
  fallidos; sin esquema nuevo. `params_of` incluye `max_output_tokens`.
- `platform/projects/loader.py`: `num_ctx`/`max_output_tokens` del perfil se validan al cargar el
  proyecto (`TemplateError`). `redactor.agent.md` declara `num_ctx: 4096`.
- Investigador/Revisor/Formateador no resuelven ni pasan el tope: sin cambios de comportamiento.
- Tests: `tests/test_redactor_truncation.py` (nuevo); dobles de streaming de otros tests ahora declaran
  fin natural o un borrador entero (`test_agent_temperature`, `test_redactor_citations`,
  `test_investigador_*`, `test_published_single_gate`).
- Docs: `docs/api/agents.md`.

### Definition of Done
- [x] El adapter detecta el truncado (motivo de parada y, sin él, secciones/frase sin cerrar) — `draft_integrity.detect_truncation` + `llm.last_stop_reason`.
- [x] Lo registra en la traza — `explainability.record_truncation` → `decision.truncation`.
- [x] No lo entrega como borrador completo: reintenta con más presupuesto o falla con motivo — `run_redactor`.
- [x] Límite de salida por la cascada, validado al cargar y acotado por la ventana del modelo — `resolve_agent_*`, `loader._validar_limites_perfil`.
- [x] Caso de prueba con respuesta cortada a mitad de frase que no pasa al Revisor — `test_un_borrador_cortado_a_mitad_de_frase_no_pasa_al_revisor`.

### Verificación
- `DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q` (backend, sin `-p no:logging`) →
  2051 passed antes de ajustar los dobles; 12 failed + 7 errors: 8 fallos por dobles de streaming
  incompletos (corregidos), `test_no_tracked_databases` (WinError 32, conocido) y 7 errors de
  `test_language_selector`/`test_traceability_abstention` (`vite build` sin `node_modules` en el worktree,
  ajeno al cambio).
- Re-ejecución de los ficheros afectados (`test_redactor_truncation`, `test_investigador_*`,
  `test_published_single_gate`, `test_redactor_citations`, `test_agent_temperature`,
  `test_langgraph_agent_flow`, `test_project_template`) → 161 passed.
- Frontend sin cambios: no se ejecutó `npm run build` ni `check_i18n.py`.

### Fuera de alcance / notas
- Un reintento vuelve a emitir tokens por SSE; el `draft_text` final es el del reintento.
- La ventana del modelo sale de una tabla por prefijo (`VENTANAS_MODELO`); un modelo desconocido usa 8192.
- La heurística exige las cinco secciones; un modelo que omita el encabezado «Resumen» agotará el reintento y fallará con motivo.
