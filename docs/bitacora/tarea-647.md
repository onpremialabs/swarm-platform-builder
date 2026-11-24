# Tarea #647 — T22.14 Indexación: detectar y excluir la sección de referencias del índice de recuperación y etiquetar `section` en el payload

## 2026-11-24 11:15 — Completada ✅

- **Rama:** `feat/647-excluir-referencias-del-indice`
- **PR:** ver PR de la rama → `develop` (`Closes #647`)
- **Spec/ADR:** SPEC-034 (AC15, sección «Evidencia sustantiva»), SPEC-035 (mapas de citas, no tocados)
- **Dependencias:** #606 (cerrada)

### Dónde estaba el problema
`rag.chunk_text` (`backend/app/platform/capabilities/rag.py`) troceaba por párrafos sin
distinguir secciones; las listas bibliográficas de los PDF puntúan alto frente a consultas por
tema y se recuperaban como evidencia (en una ejecución real, los 10 fragmentos del mapa de citas
eran entradas de referencias).

### Qué se hizo y por qué
- `backend/app/platform/capabilities/sections.py` (nuevo): `split_sections` detecta de forma
  determinista (sin LLM) encabezados de línea completa (abstract, introduction, methods, results,
  discussion, conclusion, references, ES/EN, con numeración) y devuelve tramos contiguos sin
  pérdida de texto. Conservador: `references` solo si hay encabezado inequívoco **y** el tramo
  tiene densidad de años/DOI de bibliografía (`parece_bibliografia`); un encabezado sobre prosa,
  o un texto sin encabezados, queda `other`. Acknowledgements/Appendix/Funding/etc. cierran el
  tramo de referencias y quedan `other`.
- `rag.py`: `chunk_text_sections` (trocea por sección y devuelve `(chunks, sections)`; sin
  encabezados da los mismos fragmentos que `chunk_text`); `upsert_chunks(..., sections=)` escribe
  `section` en el payload de Qdrant y en el respaldo local (por defecto `other`); la búsqueda
  semántica, `_fetch_agent_results` y `fetch_agent_context` excluyen `section=references` con
  `must_not` en Qdrant (los puntos antiguos sin `section` siguen siendo recuperables hasta el
  reindexado de AC17) y en el respaldo local, más una defensa en profundidad sobre los
  resultados. Los resultados llevan `section`. `fetch_doc_head`/`list_documents`/backfill no
  filtran: el texto de referencias se conserva en el documento (AC4).
- Llamadores que indexan: `routers/agents.py` (2), `routers/ai.py`, `platform/library_fulltext.py`
  (descarga AC11) usan `chunk_text_sections` y pasan `sections`. El nombre de colección sigue
  derivándose de `project_context` y la dimensión de `embed_vector_size()`; no se tocaron.
- Sin cambio de esquema relacional: `section` es solo payload de Qdrant, no hay migración Alembic.
- `backend/tests/fixtures/scipy-1.0-oa.pdf`: PDF real de acceso abierto (arXiv 1907.10121,
  «SciPy 1.0», CC-BY 4.0, 160 referencias) para el test de aceptación.

### Definition of Done
- [x] Referencias detectadas y marcadas `section=references`, fuera de la búsqueda semántica del
  Investigador y del Redactor — filtro `must_not` en las tres rutas de lectura de `rag.py`.
- [x] Los demás fragmentos llevan `section` (`abstract`, `introduction`, `methods`, `results`,
  `discussion`, `conclusion`, `other`) — `split_sections`.
- [x] Determinista y conservadora (ante duda `other`) — sin LLM; tests de prosa bajo «References»
  y de texto sin encabezados.
- [x] El texto de referencias se conserva en el documento — test lee el documento guardado.
- [x] Caso con PDF real con >100 referencias donde ningún fragmento recuperado es una entrada
  bibliográfica — `test_pdf_real_ningun_fragmento_recuperado_es_una_entrada_bibliografica`.

### Verificación
- `cd backend && DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q tests/test_rag_sections.py` → 10 passed.
- Suite completa `python -m pytest -q` → 1995 passed, 38 skipped, 2 failed: `test_no_tracked_databases` (WinError 32, fallo conocido que ya falla en develop) y un test de la propia tarea (texto de ejemplo con líneas que eran encabezados), corregido y reverificado en verde.

### Fuera de alcance / notas
- Reindexado de documentos ya indexados (AC17), abstención por contenido (AC16) y recuperación por
  sub-preguntas (AC18) son tareas aparte.
- No hay detección de bibliografía sin encabezado (extracción que pierda la línea «References»):
  por la regla conservadora se queda como `other`.
- El tramo tras `References` y antes del siguiente encabezado conocido se considera bibliografía
  (en SciPy, las afiliaciones finales quedan en `other` por «Competing Interests»).
