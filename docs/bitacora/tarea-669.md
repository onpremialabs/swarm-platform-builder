# Tarea #669 — T24.12: Redactor, ventana dimensionada por el prompt, recorte de fragmentos por prioridad y sin intento perdido

## 2026-11-25 19:35 — Completada

- **Rama:** `fix/669-ventana-redactor-por-prompt`
- **PR:** pendiente de número → `develop` (`Closes #669`)
- **Spec/ADR:** SPEC-036 (AC13 y «Ventana del Redactor por el prompt»); base: T24.11 (#666, `platform/review_budget.py`) y T24.9/T24.10 (reintento de truncado)
- **Dependencias:** #666 (T24.11) mergeada

### Dónde estaba el problema
`adapters/redactor.py` usaba `num_ctx = resolve_agent_num_ctx(...)` tal cual, como tope. Reproducido el 2026-11-25 con `qwen3.5:9b` y `num_ctx=16384`: el prompt con 31 fragmentos citables mide 56 560 caracteres (≈16 000 tokens reales), llena la ventana, el proveedor corta con `length` a los ~107 s y el reintento de AC10 (32768) tarda 231 s más. Cada ejecución perdía un intento entero por una ventana que ya se podía saber insuficiente.

### Qué se hizo y por qué
- `platform/review_budget.py`: se extrae `size_window` (prompt estimado por exceso + margen de salida, redondeo a 1024, `num_ctx` de la cascada como mínimo, techo `model_context_window`, `fits`) y `size_review_budget` pasa a usarla (sin duplicar lógica; comportamiento del Revisor intacto). Nuevo `writer_output_margin`: `max_output_tokens` si está fijado; si no 2 tokens/palabra de `target_word_count` (mínimo 2048); sin objetivo, 4096.
- `platform/prompt_trim.py` (nuevo, puro): orden de quita de fragmentos por prioridad de sección. La sección de un fragmento sale de su `origin` (`[Sub-pregunta qN: …]`) cruzado con `research_coverage.subqueries`; `subqueries.SECCIONES` da la prioridad (problema > método > resultados > limitaciones). Orden: 1) sin sección (RAG propio del Redactor y consulta por título), 2) último fragmento de la sección con más fragmentos (empate: la de menor prioridad), 3) solo si cada sección tiene uno, la cobertura de la sección de menor prioridad.
- `adapters/redactor.py`: el prompt se arma con `_armar(fragmentos)` (marcadores `[F#]` y bloque citable salen de los fragmentos que se quedan). Se dimensiona la ventana; si no cabe se quitan fragmentos hasta que quepa (se conserva al menos uno); si ni así, `RuntimeError` con motivo **antes de generar**. `num_ctx` efectivo = ventana dimensionada. La ampliación de palabras también se dimensiona (y se omite con aviso si no cabe: el borrador original ya estaba entero). El reintento de truncado (AC10/AC11) no se toca: queda para cortes imprevisibles.
- `platform/explainability.py` + `application/use_cases.py`: `record_prompt_budget` / `with_prompt_budget` dejan `decision.prompt_budget` en la traza (ventana pedida y configurada, tokens, margen, `outcome` ok/trimmed/does_not_fit, fragmentos quitados con sección y motivo, `sections_lost`), también si el paso falla. Sin esquema nuevo.
- Paridad `adapters`/`capabilities`: las llamadas siguen yendo por `provider(...)` con los mismos argumentos; no cambia nada en el binding.
- `docs/api/agents.md`: sección de la ventana por el prompt y de `prompt_budget`.
- `tests/test_redactor_truncation.py`: el `num_ctx` esperado pasa de 4096 a 5120 (el mínimo 4096 + prompt corto + 4096 de salida sin objetivo de palabras), 10240 en el reintento.

### Definition of Done
- [x] Ventana por el prompt + margen de salida del objetivo de palabras, redondeada, acotada por la ventana del modelo, cascada como mínimo — `review_budget.size_window`, `test_la_ventana_configurada_es_minimo_no_tope`.
- [x] Si no cabe: no se envía; se quitan fragmentos por prioridad de sección y se registra cuántos y por qué; si ni así, falla con motivo antes de generar — `prompt_trim`, `test_prompt_que_no_cabe_quita_fragmentos_*`, `test_si_ni_recortando_cabe_falla_antes_de_generar`.
- [x] La generación no empieza con una ventana ya insuficiente; el reintento de AC10 queda para cortes imprevisibles — `test_el_reintento_de_ac10_sigue_para_cortes_imprevistos`.
- [x] Caso de ~16 000 tokens con `num_ctx=16384` enviado de una vez con ventana mayor, y caso que no cabe — `tests/test_redactor_window_budget.py`.

### Verificación
- `DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q tests/test_redactor_window_budget.py tests/test_redactor_*.py tests/test_explainability_trace.py tests/test_revisor_budget.py tests/test_engine_capability_parity.py` → verde.
- Suite completa de `backend/` (en segundo plano, tras el último cambio): 2105 passed, 38 skipped, 1 failed, 7 errors. Fallo: `test_no_tracked_databases` (WinError 32, conocido). Errors: `test_language_selector` y `test_traceability_abstention` (sin `node_modules` en el worktree, ajenos).
- Calibración: con `prompt1.txt` de la reproducción (56 560 caracteres) la estimación da ≈18 854 tokens, +4000 de salida (2000 palabras) → ventana 23 552, dentro de los 32 768 de qwen3.
- **No verificado:** no se ejecutó contra un Ollama real ni se repitió la prueba de punta a punta con `qwen3.5:9b`; las pruebas usan un LLM falso. Las constantes (3 car./token, 2 tokens/palabra de salida) son heurísticas por exceso. Frontend sin cambios.

### Notas
- El recorte solo quita fragmentos del bloque citable; `research_data` (síntesis, texto de fuentes) y el borrador en modo corrección no se recortan: si por sí solos exceden la ventana, el paso falla con motivo.
- Subir la ventana implica más VRAM en Ollama para prompts grandes, hasta la ventana del modelo.
