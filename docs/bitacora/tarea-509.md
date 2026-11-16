# Tarea #509 — Cancelar la generación no libera el modelo de Ollama

## 2026-11-16 15:32 (-03:00) — Completada ✅

- **Rama:** `fix/509-cancelar-libera-modelo-ollama`
- **PR:** la de esta rama → `develop` (`Closes #509`)
- **Spec/ADR:** — (issue `bug`, `area/backend`, `sev/high`; toca la traza de SPEC-014/T9.1 y el bus de SPEC-018/T4.3)
- **Dependencias:** ninguna

### Dónde estaba el problema

- `backend/app/platform/llm.py`: cada agente pide `keep_alive=0`, que Ollama aplica **al terminar la petición**. Cancelar abandona el stream a mitad, así que
  la directiva puede no aplicarse y el modelo se queda con el keep-alive por defecto ocupando la VRAM. No había descarga explícita en ninguna parte.
- `backend/app/modules/agents/application/use_cases.py`, `make_node_wrapper`: la issue habla de «la rama `except asyncio.CancelledError` del wrapper de
  nodo, que ya cierra el run y escribe la traza», pero **esa rama no existía**. El wrapper solo tenía `except Exception`, y `CancelledError` hereda de
  `BaseException` desde Python 3.8: al cancelar, el `agent_run` se quedaba en `running` y el paso no dejaba traza (T9.1/AC1 pide la traza «cuando termina
  **o se cancela**»). Solo el nivel del pipeline (`Orchestrator.run`) atendía la cancelación, y allí ya no se sabe qué modelo usaba el agente.

### Qué se hizo y por qué

- `backend/app/platform/llm.py` — nueva `unload_model(model) -> bool`: `POST /api/generate` con `model`, `prompt: ""`, `stream: false` y `keep_alive: 0`
  contra `settings.OLLAMA_BASE_URL`, con timeout corto (`UNLOAD_TIMEOUT_SECONDS = 5`). **Nunca lanza**: un fallo de red o un HTTP ≠ 200 se registra en
  WARNING con modelo y motivo y devuelve `False`. Con `LLM_PROVIDER` `anthropic`/`openai` vuelve sin llamar a nadie (mismo criterio que el dispatcher, que
  envía a Ollama todo lo demás). No pasa por `egress.py`: la URL sale de la configuración (CLAUDE.md, «Ollama… quedan fuera a propósito»).
- `backend/app/modules/agents/application/use_cases.py`:
  - Nueva rama `except asyncio.CancelledError` en el wrapper de nodo: primero libera el modelo, luego cierra el `agent_run` como `cancelled` y escribe el
    paso de traza con `status="cancelled"` (tokens y fuentes acumulados hasta ese momento), y relanza la cancelación.
  - Nuevo `_release_model_after_cancel(agent_name, model)`: el modelo es el que ya resolvió el paso (`resolve_agent_model`, el mismo que va a la traza); si
    el agente no usa LLM (`model is None`) no hace nada. La descarga corre en una **tarea aparte** (`ensure_future` + `shield`) porque la actual está
    cancelada, y se espera como mucho `UNLOAD_WAIT_SECONDS = 6`; un timeout o cualquier excepción se registra y la cancelación sigue.
  - Funciona igual con un solo worker que con varios: la rama corre en el worker **que ejecuta** el pipeline, tanto si la cancelación llegó por
    `active_tasks` como por la señal del bus.
- `backend/tests/test_cancel_unloads_model.py` (nuevo, 14 tests): la forma exacta de la petición a Ollama; proveedor remoto sin llamadas; fallo de red y
  HTTP 404 sin excepción y con motivo en el log; de extremo a extremo con `Orchestrator.run` cancelado a mitad del Redactor: pide la descarga del modelo
  resuelto, la petición HTTP real sale desde la tarea cancelada, con Anthropic no sale ninguna, un `unload_model` que revienta o se cuelga no impide
  completar la cancelación, y el run y el paso quedan como `cancelled`. Más uno de la cuestión adyacente del backoff (abajo).

### Definition of Done

- [x] AC1 — con `LLM_PROVIDER=ollama`, cancelar pide a Ollama `keep_alive: 0` sobre el modelo del agente, que es lo que lo saca de `ollama ps`.
  Verificado con transporte HTTP simulado; **no se ha comprobado contra un Ollama real** con `ollama ps` (ver notas).
- [x] AC2 — la descarga se pide explícitamente con una petición propia, no se depende del `keep_alive` de la petición abortada.
- [x] AC3 — fallo de descarga (excepción, HTTP de error o cuelgue) → WARNING con el motivo; la cancelación se completa (`CancelledError` propagada, run y
  paso `cancelled`). Tiempo máximo añadido: 6 s.
- [x] AC4 — con Anthropic/OpenAI `unload_model` vuelve sin hacer ninguna petición (test unitario y de extremo a extremo).
- [x] AC5 — `test_cancelar_pide_la_descarga_del_modelo_del_agente` y `test_cancelar_llega_a_ollama_por_http`.
- [x] Sin secretos ni PII en el diff.

### Verificación

- `DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q tests/test_cancel_unloads_model.py` → 14 passed.
- `DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q --deselect tests/test_no_tracked_databases.py::test_a_fresh_dev_database_is_created_and_migrated`
  → 1456 passed, 38 skipped, 1 deselected (5 min 52 s). El test deseleccionado falla solo en Windows por bloqueo del fichero SQLite (no relacionado); la CI en Linux lo corre.

### Cuestiones adyacentes de la issue

- **`task.cancel()` dentro del backoff de `_retry_stream`** — revisado, **no requiere cambio**: el backoff espera con `asyncio.sleep(delay)`, que es un
  punto de cancelación; `task.cancel()` lo interrumpe al instante, no al vencer el retraso. Queda fijado con
  `test_cancelar_durante_el_backoff_del_stream_es_inmediato` (backoff de 60 s, cancelación en < 1 s). Lo que sí puede retrasar una cancelación es código
  **síncrono** que bloquee el bucle de eventos (extracción de PDF, embeddings síncronos): no hay `await` donde entregarla. No se ha visto un caso concreto en
  el camino del pipeline; queda anotado como **pendiente de observar**, no como bug.
- **`active_tasks` por proceso con varios workers** — revisado, **no se cambia aquí**. Con `REDIS_ENABLED=true` (`RedisBus`, SPEC-018/T4.3) la señal viaja por Redis y la
  cancela el worker dueño; la descarga nueva corre en ese worker, así que también se libera el modelo. Con el bus **en proceso** y varios workers la
  cancelación desde otro worker no puede funcionar (responde 409): es una configuración no soportada para multi-worker, no algo arreglable de forma acotada en
  esta tarea. **Pendiente**: si se quiere, que el arranque avise (o falle) con `workers > 1` y bus en proceso.

### Fuera de alcance / notas

- No se ha probado contra un Ollama real (`ollama ps` tras cancelar). La forma de la petición es la documentada por Ollama para descargar un modelo.
- Solo se descarga el modelo de **generación** del agente. El de embeddings (`OLLAMA_EMBED_MODEL`) no se toca: es pequeño, sus peticiones no son streams
  largos y lo comparten otras rutas (indexación).
- La issue indicaba como punto de enganche una rama que no existía; se creó, y con ello el paso cancelado queda trazado y el `agent_run` deja de quedarse
  en `running` — efecto lateral deseado (T9.1/AC1), cubierto por los mismos tests.
