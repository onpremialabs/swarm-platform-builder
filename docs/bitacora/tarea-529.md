# Tarea #529 — T22.6 Aplicar de verdad RAG_SCORE_THRESHOLD en todos los llamadores con test

## 2026-11-22 — Completada ✅

- **Rama:** `feat/529-rag-score-threshold`
- **PR:** ver PR de la rama → `develop` (`Closes #529`)
- **Spec/ADR:** SPEC-034 §1 (hallazgo N7), AC8; `docs/governance/edd-discipline.md`
- **Dependencias:** ninguna

### Dónde estaba el problema
`backend/app/platform/capabilities/rag.py` (`semantic_search_results`, `semantic_search_context`):
`score_threshold` tenía default `0.0` y ningún llamador (`adapters/investigador.py`,
`redactor.py`, `generic.py`, ni `graph_rag_search_context`) lo pasaba, así que
`RAG_SCORE_THRESHOLD` (`core/config.py`) era configuración muerta; una fuente pudo
figurar con similitud 0,00. Además, si fallaba el embedding, Qdrant o la búsqueda,
`_fetch_agent_results` (scroll) devolvía fragmentos sin ranking.

### Qué se hizo y por qué
- `rag.py`: nuevo `resolve_score_threshold()`; el parámetro pasa a `Optional[float] = None`
  y `None` significa «el ajuste global». Así ningún llamador puede olvidarlo: se
  resuelve dentro de la capacidad. `0.0` explícito sigue desactivando el filtro.
- `rag.py`: además del filtro en Qdrant, se descartan en cliente los resultados con
  score ausente o menor al umbral (defensa en profundidad).
- **Decisión sobre el respaldo sin ranking:** con el umbral activo, los tres caminos de
  respaldo (Qdrant no disponible, embedding fallido, error/estado ≠ 200 de la búsqueda)
  devuelven lista vacía y avisan en el log (`_fallback_sin_ranking`): un fragmento sin
  puntuación no se puede demostrar sobre el umbral y devolverlo reintroduciría lo que
  el umbral filtra. Excepción: si la persona eligió `doc_ids`, esa elección es la
  señal de relevancia y el respaldo se conserva. Con umbral 0.0 nada cambia.
- **Valor por defecto: 0.3** (código `config.py` y `rag.score_threshold` en ambos
  `config.yaml`; antes 0.0 en código y 0.5 en yaml, que nunca se aplicó). 0.5 sin
  haberse validado nunca arriesgaba dejar al Investigador sin fuentes con embeddings
  tipo `nomic-embed-text`; 0.3 excluye el ruido (0.00) con margen. Es ajustable por
  `RAG_SCORE_THRESHOLD` o `rag.score_threshold`.
- `tests/test_rag_score_threshold.py` (nuevo): estructurales (default `None`, ningún
  llamador fija `score_threshold=0`, ninguno busca en Qdrant fuera de `rag.py`, los
  tres adapters heredan el ajuste) y de comportamiento (se envía el umbral a Qdrant,
  se filtran resultados bajo el umbral, 0.0 lo apaga, respaldo vacío / conservado).
  Comprobado que muerde: añadir `score_threshold=0.0` en `redactor.py` los hace fallar.
- `tests/test_explainability_trace.py`: ese test usa a propósito el respaldo local sin
  ranking; fija `score_threshold=0.0` para seguir probando la traza.

### Evaluación (EDD, DoR/DoD)
- Qué puede romperse: Investigador/Redactor reciben menos o ninguna fuente si el
  umbral es alto o Qdrant/embeddings fallan. Lo miden `citation_fidelity` y `budget`.
- Los datasets golden son `handwritten`/`replay` y no invocan la búsqueda real, por lo
  que este gate no ejercita el umbral; el cambio de comportamiento real solo se vería
  en `live`. No se modifican datasets ni `thresholds.yaml`.

### Definition of Done
- [x] **AC8** — el umbral se aplica de verdad en todos los llamadores (resuelto en la
  capacidad) y hay test que falla si un llamador lo omite/apaga.

### Verificación
- `python -m pytest -q tests/test_rag_score_threshold.py tests/test_explainability_trace.py` → 30 passed (13 nuevos).
- Mutación `score_threshold=0.0` en `redactor.py` → 2 tests nuevos fallan (revertida).
- `python -m evals.agent_behavior.gate` → «Ninguna métrica por debajo de su umbral», exit 0.
- Suite completa (`DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q`, backend/) → 1560 passed, 38 skipped, 1 failed: `test_no_tracked_databases.py::test_a_fresh_dev_database_is_created_and_migrated` (PermissionError WinError 32 en Windows, preexistente y ajeno).

### Fuera de alcance / notas
- Sin Qdrant (modo desarrollo con almacenamiento local) y umbral > 0, el RAG devuelve
  vacío: con `RAG_SCORE_THRESHOLD=0` se recupera el comportamiento anterior.
- No se tocan datasets ni la tarea #557.
