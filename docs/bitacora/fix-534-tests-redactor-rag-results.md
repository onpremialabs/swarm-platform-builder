# Fix: tests del Redactor tras T23.1 (#621)

## 2026-11-23 — Éxito ✅

- **Rama:** `fix/534-tests-redactor-rag-results`
- **Origen:** la PR #621 (T23.1) se mergeó con `Backend · pytest` en rojo; los commits de
  corrección (`703d47e`, `cdf66c8`) llegaron a la rama después del merge y no entraron en
  `develop`. GitHub no relanzó el CI de la PR porque ya estaba mergeada.

### Qué se hizo y dónde

- `backend/app/modules/agents/adapters/redactor.py`: la plantilla en inglés vuelve a
  incluir «ONLY the sources listed as citable» (regla de T22.5), junto al marcador `[F#]`.
- `backend/tests/test_investigador_verified_only.py`: el Redactor ahora usa la capacidad
  `rag_results`; el test parchea `semantic_search_results` y devuelve fragmentos.
- `backend/tests/test_project_template.py`: `CAPACIDADES_ESPERADAS` del redactor pasa a
  `rag_results` (cambio deliberado de T23.1).

### Verificación

- Ver la sección de PR: el CI de esta PR es la comprobación de la suite completa.

### Qué NO se hizo

- No se cambió ninguna regla de producto: solo se restauró una frase del prompt y se
  alinearon dos tests con la capacidad que T23.1 ya había introducido.
