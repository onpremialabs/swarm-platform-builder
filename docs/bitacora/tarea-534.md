# Tarea #534 — T23.1 Redactor con citas por identificador de fragmento y sin fuentes fuera de sources

## 2026-11-23 05:00 — Completada ✅

- **Rama:** `feat/534-citas-por-fragmento`
- **PR:** ver la PR con `Closes #534` → `develop`
- **Spec/ADR:** SPEC-035 (E23, AC1), ADR-0011 (falla cerrada, para T23.3)
- **Dependencias:** ninguna

### Dónde estaba el problema
`backend/app/modules/agents/adapters/redactor.py`: la capacidad `rag` devolvía solo texto
concatenado, sin identidad de fragmento, así que el borrador no podía vincular una cita a un
fragmento concreto. El texto se citaba «por fuente», no por pasaje.

### Qué se hizo y por qué
- `backend/app/platform/citations.py` (fusionado con el de T23.2, #620, sin borrar `save_citation_map`/`get_citation_map`/`current_citation_map`/`confirm_citation`): se añade el **contrato** de T23.1 para T23.2/T23.3, determinista y sin E/S.
  - `fragment_id` = `"<doc_id>#<chunk_index>"` (cae a `chunk_id` si el índice no da `chunk_index`).
  - `cite_id` = alias `F<n>`; el Redactor escribe `[F3]` / `[F1, F3]`. Los alias se conservan entre vueltas del bucle del revisor.
  - `citation_map`: `F# → {fragment_id, doc_id, chunk_index, filename, page, extract, hash}`; `hash` = SHA-256 del fragmento, `page` = `None` hasta que la indexación la guarde (SPEC-035 §5).
  - `extract_citations`: lee el borrador y devuelve `citations` (una por afirmación×marcador, con `claim`), `unresolved` (marcadores no presentes en el mapa) y `text_hash` del borrador evaluado.
- `to_citation_inputs(citations)`: puente de las citas del Redactor a `CitationInput` para `save_citation_map`. **El Redactor no persiste**: su adaptador no tiene sesión de BD y el texto evaluado puede cambiar aguas abajo; quien orqueste (T23.3) llama `save_citation_map(session, article_id, texto, to_citation_inputs(state['citations']))`. Sin migración nueva (la 0010 es de T23.2).
- `redactor.py`: pasa de la capacidad `rag` a `rag_results`, filtra de nuevo por `sources`, ofrece cada fragmento con su `[F#]` y la regla de cita (también en modo corrección, cuyo prompt no lleva `research_data`) y devuelve `citation_map`, `citations`, `citations_unresolved`, `citations_text_hash`.
- `capabilities/rag.py`: los resultados de búsqueda exponen `chunk_index` (3 rutas) para que el identificador sea estable.
- `domain/entities.py`: claves nuevas en `AgentState` (si no, LangGraph las descarta).
- `projects/alejandria-magazine/template.yaml` y `tests/test_engine_capability_parity.py`: el redactor declara `rag_results` en lugar de `rag` (paridad adapters/capabilities intacta).
- `tests/test_redactor_citations.py` (nuevo).
- Se respetan `resolve_agent_model` / `resolve_agent_temperature` (sin tocar).

### Definition of Done
- [x] **AC1 (parte T23.1)** — el Redactor cita por identificador de fragmento y deja el mapa `cita → {doc_id, página, extracto, hash}` versionado con el hash del texto (`citations_text_hash`) en el estado. El Redactor no añade fuentes fuera de `sources`. **La persistencia en BD es T23.2** (no incluida).

### Verificación
- `DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q tests/test_redactor_citations.py tests/test_engine_capability_parity.py` → verde.
- Fix tras CI roja de la PR: `test_investigador_verified_only.py` (parchea ahora `semantic_search_results` y devuelve fragmentos; el cambio de capacidad es deliberado), `test_project_template.py` (`CAPACIDADES_ESPERADAS` del redactor = `rag_results`) y las frases «SOLO las fuentes listadas como citables» / «ONLY the sources listed as citable» se conservan en los prompts. Subconjunto de 19 ficheros relacionados: 362 passed, 1 failed (el corregido) -> tras el arreglo `test_investigador_verified_only.py` + `test_project_template.py`: 62 passed.

### Fuera de alcance / notas
- Sin migración ni persistencia (T23.2); sin criterio de compuerta ni juez (T23.3/T23.4).
- `page` es `None`: la indexación no guarda página.
- El Formateador debe respetar los marcadores `[F#]` o resolverlos sin alterar el mapa; no se tocó aquí.
- El Redactor es un LLM: puede omitir marcadores o inventarlos; los inventados quedan en `citations_unresolved`.
