# Tarea #660 — T23.9 — Redactor: exigir citas [F#] en el cuerpo, rechazar autor-año inventadas, reintentar y diagnosticar el contexto

## 2026-11-25 07:50 — Completada ✅

- **Rama:** `fix/660-citas-autor-anio-sin-fid`
- **PR:** pendiente de número (ver enlace en el issue) → `develop`
- **Spec/ADR:** SPEC-035 (AC10), ADR-0011 (falla cerrada); coordina con SPEC-036/T24.9 (reintento por truncado) y SPEC-034/AC18 (sub-preguntas).
- **Dependencias:** #534 y #635, ambas cerradas.

### Diagnóstico: por qué salieron 0 `[F#]` (prueba de punta a punta con `qwen3.5:9b`)

Evidencia: el borrador `e2e-body6.md` no contiene ningún `[F#]` y cita «(HarnessDev, 2024)» y
«(Code as Agent Harness et al., 2024)», es decir, el **título de la obra como autor** y un año
(2024) que no es el de la ficha (el DOI dice 2026).

Lectura del código (`adapters/investigador.py` ≈ 480-500 y 570-578; `adapters/redactor.py`):

1. **La causa es mixta, pero la parte del contexto es nuestra.** Tras T22.17 el Investigador fusiona
   los fragmentos de todas las sub-preguntas y los entrega en `research_data` como
   `[Fuente: <Título>] [Sub-pregunta qN: <sección>] <texto>`, y la cabecera lista las fuentes como
   `- <Título> (<autores>, <año>) — DOI …`. **Ninguno de esos fragmentos lleva marcador `[F#]`**:
   `research_data` es un `str` y el Redactor no recibía los fragmentos estructurados.
2. El único bloque con `[F#]` («### Fragmentos citables») lo construía el Redactor con **una segunda
   consulta RAG propia** (`título + palabras clave`, `limit=10`, filtrada a `sources`). Esa consulta
   es independiente de las sub-preguntas: puede devolver otros fragmentos, ninguno (timeout de 25 s,
   Qdrant caído, la excepción se tragaba y se seguía) o los mismos sin relación con lo que el
   Investigador recuperó por sección. Cuando eso pasa, el prompt llega al modelo con material
   «citable» etiquetado solo por `[Fuente: Título]` y una lista `Título (autores, año)`: el único
   formato de cita que el contexto le **enseña** es autor-año con el título como autor.
3. El prompt por defecto decía «cita SOLO las fuentes listadas como citables» pero **no mostraba un
   ejemplo** del formato `[F#]` ni prohibía el autor-año; la regla vivía únicamente dentro del bloque
   «Fragmentos citables» (que, según el punto 2, podía no existir).
4. La parte del **modelo** (un 9B ignora instrucciones tardías y largas) no se puede descartar, pero
   con lo anterior el modelo no tenía qué copiar: por eso se corrige el contexto **y** se añade
   detección + un reintento.

Reproducción (`tests/test_redactor_citation_format.py`): con la salida del Investigador tal cual y la
consulta RAG propia sin resultados, el prompt del Redactor no contiene el bloque
«Fragmentos citables» (`test_el_contexto_del_investigador_sin_fragmentos_estructurados_no_lleva_marcadores`);
con los fragmentos estructurados del Investigador, lleva `[F1]`, `[F2]` aunque el RAG propio falle y cada
uno conserva su origen `[Sub-pregunta qN: …]`.

### Qué se hizo y por qué

- `backend/app/modules/agents/adapters/investigador.py`: devuelve `research_fragments` (fragmentos
  sustantivos citables estructurados: `doc_id`, `chunk_id`, `chunk_index`, `filename`, `text`, `origin`).
  Es el cambio que corrige la causa del contexto.
- `backend/app/modules/agents/adapters/redactor.py`:
  - `_fusionar_fragmentos`: los fragmentos del Investigador + los del RAG propio, sin duplicar y solo de
    `sources`, reciben `[F#]` (`assign_cite_ids`) **aunque el RAG propio falle**.
  - Plantillas por defecto es/en con el formato de cita, un ejemplo `[F1]` y la prohibición del autor-año
    (también recordatorio en las plantillas de corrección).
  - Tras la ampliación de palabras, si hay fragmentos citables y 0 `[F#]` válidos, **un único reintento**
    con `citas.format_reminder` añadido al prompt, reutilizando `_generar` (misma resolución de modelo,
    temperatura, `num_ctx` y tope de salida por la cascada; no se duplica el mecanismo de truncado de
    T24.9, que falla el paso: este solo avisa). Si el reintento sale truncado/vacío se conserva el
    borrador. Si persiste, `citation_check.no_citations = True` y un aviso al autor en el log del paso; el
    paso **no falla**.
- `backend/app/platform/citations.py`: `extract_citations` reconoce citas autor-año entre paréntesis
  (`_AUTOR_ANIO`) y las trata como **cita sin fragmento** (entran en `citations`/`unresolved` con
  `fragment_id=None`, así que la compuerta las deja `not_verified`); devuelve `author_year` y
  `valid_citations`. `render_fragments` muestra el origen por sub-pregunta y prohíbe el autor-año.
  `format_reminder` (es/en).
- `backend/app/platform/explainability.py`: `decision_of` traza `no_citations` / `citation_retry` /
  `author_year_citations` / `citable_fragments` en la columna `decision` (T9.1), sin esquema nuevo y solo
  cuando hubo algo que decir.
- `backend/app/modules/agents/adapters/revisor.py`: si `citation_check.no_citations`, el prompt lleva el
  aviso y el feedback incluye, de forma determinista, un comentario sobre las citas (no altera la puntuación).
- `backend/app/modules/agents/domain/entities.py`: claves `research_fragments` y `citation_check` en `AgentState`.
- Paridad `AGENT_ENGINE`: todo pasa por `provider(state, "llm_stream"/"rag_results", …)` como antes; los
  tests usan el bundle de capacidades.

### Definition of Done

- [x] El texto cita con `[F#]` y una cita autor-año inventada no es válida (se trata como cita sin fragmento) — `extract_citations` + test `test_un_borrador_con_autor_anio_y_ningun_marcador_se_marca_sin_citas_validas`.
- [x] Sin ninguna cita `[F#]` habiendo fragmentos: detecta, reintenta una vez con recordatorio y, si persiste, `no_citations` en la traza y aviso a Revisor y autor sin fallar el paso — tests de reintento, `no_citations` en traza y aviso al Revisor.
- [x] Prompt por defecto es/en con ejemplo `[F#]` y prohibición del autor-año — `test_el_prompt_por_defecto_muestra_el_formato_y_prohibe_autor_anio`.
- [x] Diagnóstico documentado (arriba) y causa del contexto corregida (`research_fragments`).
- [x] Caso de prueba con «(HarnessDev, 2024)» y ningún `[F#]` marcado como sin citas válidas.
- [x] Un borrador correcto no se reintenta (`test_un_borrador_correcto_no_se_reintenta_ni_deja_traza`).

### Verificación

- `cd backend && DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q tests/test_redactor_citation_format.py tests/test_redactor_citations.py tests/test_redactor_truncation.py` → 47 passed.
- `DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q` (backend/) → 2077 passed, 38 skipped, 1 failed, 7 errors. El fallo es el conocido `test_no_tracked_databases` (WinError 32); los 7 errores (`test_language_selector`, `test_traceability_abstention`) son de entorno: el worktree nuevo no tiene `frontend/node_modules` y Vite no carga su config; no tocan este cambio.
- No se tocó frontend ni i18n: no se corrió `npm run build`.

### Fuera de alcance / notas

- El reintento regenera el borrador completo, así que no se vuelve a aplicar la ampliación de palabras
  tras él; es el coste de un único reintento.
- La compuerta `citation_support` sigue en modo aviso (sin cambios).
- No se verificó con el modelo real `qwen3.5:9b`; la causa del contexto está reproducida con dobles.
