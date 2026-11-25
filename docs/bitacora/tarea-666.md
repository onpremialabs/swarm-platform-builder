# Tarea #666 — T24.11: Revisor, tiempo de espera y ventana por la cascada, dimensionados por el borrador

## 2026-11-25 13:05 — Completada

- **Rama:** `fix/666-revisor-presupuesto`
- **PR:** pendiente de número → `develop` (`Closes #666`)
- **Spec/ADR:** SPEC-036 (AC12 y «Presupuesto del Revisor»); SPEC-032/AC15 (`not_verified`); modelo seguido: T24.9 (#657)
- **Dependencias:** ninguna

### Dónde estaba el problema
`backend/app/modules/agents/adapters/revisor.py` llamaba a `call_llm` con `timeout=45.0, num_ctx=4096` fijos. En una prueba de punta a punta con `qwen3.5:9b` un borrador de 2270 palabras agotó 45 s cuatro veces (la capa de reintentos de `llm.py` repite con el mismo límite: 20 min), puntuó 0 por falla cerrada y volvió al Redactor sin revisarse. Además ese borrador no cabe en 4096 tokens: Ollama lo recorta en silencio.

### Qué se hizo y por qué
- `backend/app/platform/review_budget.py` (nuevo, función pura): `size_review_budget` dimensiona la ventana (prompt estimado por exceso, 3 caracteres/token, + 1024 de margen de salida, redondeo a 1024) y el tiempo (120 s + 0,1 s por token de prompt). Lo configurado por la cascada es el **mínimo**; el techo de la ventana es `model_context_window`. Si no cabe, `fits=False`. `raised_timeout` da el único aumento permitido tras un timeout (el doble).
- `backend/app/platform/llm.py`: `resolve_agent_timeout` / `validate_timeout` (clave `timeout_seconds`, cascada ajustes de la ejecución → `.agent.md`); `LLMTimeoutError` (subclase de `TransientLLMError`, también para `APITimeoutError` de Anthropic/OpenAI); `call_llm(retry_on_timeout=True)` y `_retry_async(retry_on_timeout=...)`: con `False` el timeout se propaga sin reintentar con el mismo límite. El defecto no cambia, así que el resto de agentes se comportan como antes. `num_ctx` reutiliza `resolve_agent_num_ctx` de T24.9.
- `adapters/revisor.py`: ya no hay 45/4096 en el código. Si el prompt no cabe no se llama al proveedor: `review_status=not_verified` con motivo. Un timeout se reintenta una vez con el doble de límite o falla con motivo. El resultado lleva `review_budget` (ventana, límite, tokens estimados, `timeout_retries`, `elapsed_seconds`, `outcome`).
- `platform/explainability.py`: `decision_of` copia `review_budget` a la columna `decision` (sin esquema nuevo), visible en `GET /agents/{id}/explain`.
- `platform/projects/loader.py`: `timeout_seconds` del perfil se valida al cargar (`TemplateError`).
- La llamada va por `provider(state, "llm", call_llm)`: el camino `capabilities` recibe los mismos argumentos (test de paridad).
- Docs: `docs/api/agents.md`.

### Definition of Done
- [x] Tiempo y `num_ctx` por la cascada, validados al cargar — `resolve_agent_timeout`/`resolve_agent_num_ctx`, `loader._validar_limites_perfil`.
- [x] Dimensionados por el borrador (texto + rúbrica + margen de salida), acotados por la ventana del modelo — `review_budget.size_review_budget`.
- [x] Si el prompt no cabe: no se envía recortado, se registra en la traza y falla cerrado `not_verified` con motivo — `test_prompt_que_no_cabe_no_se_envia_y_es_not_verified`.
- [x] Timeout no reintentado con el mismo límite: sube una vez o falla con motivo; la traza dice reintentos y tiempo consumido — `test_timeout_*`, `review_budget.timeout_retries/elapsed_seconds`.
- [x] Caso de ~2300 palabras revisado con LLM falso sin recorte, y caso que no cabe → `not_verified` — `tests/test_revisor_budget.py`.

### Verificación
- `DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q tests/test_revisor_budget.py tests/test_revisor_fail_closed.py` → verde (13 + 10).
- Suite completa de `backend/` (sin `-p no:logging`, en segundo plano): 2097 passed, 38 skipped, 2 failed, 7 errors. Fallos: `test_no_tracked_databases` (WinError 32, conocido) y `test_redactor_truncation::test_los_demas_agentes_no_cambian_de_comportamiento[revisor]` (guarda de T24.9 que prohibía `resolve_agent_num_ctx` en el Revisor; ajustada en esta PR y vuelta a pasar). Errors: `test_language_selector` y `test_traceability_abstention` (`vite build` sin `node_modules` en el worktree, ajenos). Tras el ajuste solo se reejecutaron `test_redactor_truncation` y `test_revisor_budget` (verdes), no la suite entera.
- No se ejecutó contra un Ollama real ni se repitió la prueba de punta a punta con `qwen3.5:9b`: la estimación de tokens (3 car./token) y los 0,1 s/token son heurísticas sin calibrar con medidas reales. Frontend sin cambios (no se ejecutó `npm run build`).

### Notas
- `timeout_seconds` y `num_ctx` actúan como mínimo, no como tope: un borrador más grande sube la ventana hasta la del modelo (VRAM mayor para borradores grandes).
- Fuera de alcance: Investigador y Formateador conservan sus 4096 fijos.
