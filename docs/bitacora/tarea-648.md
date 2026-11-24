# Tarea #648 — T22.15 Investigador: abstenerse por falta de fragmentos sustantivos con motivo propio

## 2026-11-24 11:50 — Completada ✅

- **Rama:** `feat/648-abstencion-fragmentos-sustantivos`
- **PR:** ver la PR que cierra #648 → `develop`
- **Spec/ADR:** SPEC-034 (AC16; AC7 y AC11 como contexto), «Evidencia sustantiva (AC15–AC18)»
- **Dependencias:** #647 (T22.14) y #643 (T22.13) cerradas.

### Dónde estaba el problema
El Investigador (`modules/agents/adapters/investigador.py`) solo se abstenía por número de fuentes
citables (AC7). Con 3 fuentes cuyos fragmentos recuperados eran bibliografía, o un resumen repetido,
investigaba igualmente y sintetizaba sin contenido real que la respaldase.

### Qué se hizo y por qué
- `platform/capabilities/literature/research.py`: nueva clave `research.min_substantive_fragments`
  (entero >= 1, defecto 3), validada al cargar la plantilla con la misma regla que `min_sources`
  (se factoriza `_entero_minimo_1`); `bool`, 0, negativos, decimales y cadenas se rechazan.
- `projects/alejandria-magazine/template.yaml`: declara `min_substantive_fragments: 3` con comentario.
- `adapters/investigador.py`: tras la abstención de AC7 y antes de sintetizar, cuenta fragmentos
  sustantivos de las fuentes citables (`section != references` y al menos 3 palabras con letras).
  Un documento `abstract_only` suma como máximo 1. Con menos de K devuelve el mismo contrato
  `abstained`/`abstention` con `reason: insufficient_substantive_content`, un mensaje propio (subir el PDF
  completo, reindexar, o aportar el texto) y los campos `substantive_fragments`,
  `min_substantive_fragments`, `abstract_only_documents`. La bibliografía tampoco entra ya en el
  material de síntesis. K solo se lee de la plantilla: los ajustes de la ejecución no lo mueven.
- Se reutiliza el mecanismo de T22.12: el motor ya detiene el flujo con `abstained`; `explainability.decision_of`
  y los eventos `abstained`/`done` de `use_cases.py` propagan el motivo y los nuevos campos (sin segundo camino).
- Frontend: `ExplainPanel.jsx` distingue el motivo (clave i18n `explain.decision.abstainedContent`, es/en).
- Docs: `investigador.agent.md`, `backend/README.md`, `docs/projects/alejandria.md`.
- Tests: `tests/test_investigador_substantive_fragments.py` (17).

### Definition of Done (AC16)
- [x] Cuenta como evidencia solo fragmentos sustantivos (no `references`, texto utilizable) y se abstiene con menos de K entre las fuentes citables aunque haya N fuentes.
- [x] K = `research.min_substantive_fragments` en `template.yaml`, defecto 3, validado al cargar (entero >= 1), no bajable por el autor desde el artículo (test con `agent_settings`).
- [x] El motivo distingue `insufficient_verified_sources` (AC7) de `insufficient_substantive_content`, con mensaje de qué hacer.
- [x] Los documentos `abstract_only` cuentan como un fragmento sustantivo como máximo.

### Verificación
- `cd backend && DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q` → 1996 passed, 1 failed
  (`test_no_tracked_databases::test_a_fresh_dev_database_is_created_and_migrated`, WinError 32, conocido), y 17 errores
  de fixture `caplog` por haber lanzado esa corrida con `-p no:logging`; esos ficheros repetidos sin la bandera
  (`test_rag_embeddings_provider_decoupled`, `test_tracing`, `test_investigador_*`) → 85 passed.
- `cd frontend && npm run build` → OK; `python scripts/check_i18n.py` → OK.

### Notas
- «Texto utilizable» es una heurística determinista (>= 3 palabras alfabéticas); si hace falta afinarla, es una constante en el adapter.
- AC17 (reindexado) y AC18 (sub-preguntas) quedan en sus tareas.
