# Tarea #650 — T22.17 Investigador: recuperación por sub-preguntas de sección con cobertura declarada en la traza

## 2026-11-24 16:05 — Completada ✅

- **Rama:** `feat/650-subpreguntas-seccion`
- **PR:** ver la PR que cierra #650 → `develop`
- **Spec/ADR:** SPEC-034 (AC18), «Evidencia sustantiva (AC15–AC18)»
- **Dependencias:** #647 (T22.14) y #648 (T22.15) cerradas.

### Dónde estaba el problema
El Investigador recuperaba solo por el título (más palabras clave). Las consultas por tema traen lo más
parecido al tópico, no lo que cada sección IMRaD necesita, y nada declaraba qué parte del artículo se
quedaba sin respaldo: el Redactor, ante un hueco, lo rellenaba con conocimiento propio.

### Qué se hizo y por qué
- `platform/capabilities/subqueries.py` (nuevo, funciones puras): prompt de sub-preguntas que **solo**
  recibe título y enfoque del autor (`context_description`); análisis tolerante de la respuesta del modelo
  (entrada no confiable: secciones válidas, deduplicado, longitud acotada); plan acotado por `max_subqueries`
  que prioriza una sub-pregunta por sección (problema, método, resultados, limitaciones) y recurre a
  sub-preguntas deterministas derivadas del título si el modelo falla o no devuelve nada utilizable;
  cálculo de cobertura y aviso de huecos para el Redactor.
- `literature/research.py` + `template.yaml`: nueva clave `research.max_subqueries` (entero >= 1, defecto 6),
  validada al cargar con la misma regla que `min_sources`. El adapter la lee solo de la plantilla; un ajuste
  del artículo (`agent_settings`) se ignora y se avisa en el log.
- `adapters/investigador.py`: consulta por el título y por cada sub-pregunta (misma capacidad `rag_results`
  vía `provider`, así que `adapters` y `capabilities` siguen en paridad), fusiona por fragmento y le anota
  `subqueries` (ids que lo recuperaron). El modelo se resuelve con `resolve_agent_model` /
  `resolve_agent_temperature`. Los fragmentos sustantivos (T22.15, `_es_sustantivo`) de fuentes citables
  entran al material con la marca `[Sub-pregunta qN: sección]`, intercalados por sub-pregunta. Se calcula la
  cobertura por sección y se devuelve `research_coverage` (sub-preguntas con sus fragmentos, cobertura y
  `uncovered_sections`). La abstención también lleva las sub-preguntas.
- Traza (T9.1): `explainability.decision_of` registra sub-preguntas, cobertura y secciones sin cobertura en
  la columna `decision` existente (sin migración ni cambio de forma de la cadena de integridad).
- `adapters/redactor.py`: si hay secciones sin cobertura, añade al contexto el aviso «EVIDENCIA SIN COBERTURA»
  (también con plantilla propia del autor) y las plantillas por defecto (es/en) prohíben rellenarlas con
  conocimiento propio. `AgentState` gana `research_coverage`.
- Frontend: `ExplainPanel.jsx` muestra las sub-preguntas con sus fragmentos y las secciones sin cobertura
  (claves i18n `explain.decision.subqueries|subquery|uncovered|fullCoverage`, es/en).
- Docs: `investigador.agent.md`, `backend/README.md`, `docs/projects/alejandria.md`.
- Tests: `tests/test_investigador_subqueries.py`; el fixture `entorno` de `test_investigador_verified_only.py`
  separa las llamadas de sub-preguntas (`llm_subpreguntas`) de la síntesis (`llm`) para que sus afirmaciones
  «no se llamó al modelo para sintetizar» sigan significando lo mismo.

### Definition of Done (AC18)
- [x] Recupera por sub-pregunta de sección (problema, método, resultados, limitaciones) además de por el título; cada fragmento declara su sub-pregunta (`[Sub-pregunta qN: sección]`, `subqueries`).
- [x] Las propone el modelo solo desde título y enfoque del autor (test: el prompt no contiene texto de fuentes ni manuscrito) y se registran en la traza (`decision.subqueries`).
- [x] Acotadas por `research.max_subqueries` (defecto 6, entero >= 1, validado al cargar la plantilla, no cambiable desde el artículo).
- [x] Sección sin evidencia sustantiva declarada «sin cobertura» en la traza (`uncovered_sections`) y pasada al Redactor, que no la rellena (adapter y prompt).

### Verificación
- `cd backend && DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q` -> 2045 passed, 38 skipped, 1 failed
  (`test_no_tracked_databases::test_a_fresh_dev_database_is_created_and_migrated`, WinError 32, fallo conocido).
  (Una corrida anterior solapada con otra dio fallos `no such table` por compartir las BD SQLite de los tests;
  los ficheros afectados repetidos solos: 149 passed.)
- `tests/test_investigador_subqueries.py` + `test_llm_max_tokens.py`: 29 passed.
- `cd frontend && npm run build` -> OK; `python scripts/check_i18n.py` -> OK.

### Notas
- La cobertura cuenta fragmentos sustantivos de fuentes **citables** recuperados por las sub-preguntas de la sección; lo que solo trajo el título no cubre ninguna sección.
- Con `max_subqueries < 4` las secciones que el tope deja sin sub-pregunta quedan «sin cobertura» (`queried: false`).
- El tamaño de fragmento (500 caracteres) sigue pendiente de `/speckit-clarify`; no se toca.
