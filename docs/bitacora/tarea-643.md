# Tarea #643 — T22.13 Fuentes aportadas por el autor: declararlas, citarlas etiquetadas y abstención solo por falta de fuentes citables

## 2026-11-24 05:23 — Completada ✅

- **Rama:** `feat/643-fuentes-aportadas-por-el-autor`
- **PR:** ver la PR que cierra #643 → `develop`
- **Spec/ADR:** SPEC-034 (AC4, AC5, AC7, AC14); ADR-0013 (enmienda de ADR-0011). Nota: ADR-0013 y el AC14
  viven en la rama `docs/adr-0013-fuentes-del-autor` (commit e966859), aún no integrada en `develop`
  al momento de esta entrega; el código sigue su texto.
- **Dependencias:** #527, #528, #531 cerradas.

### Dónde estaba el problema
`backend/app/platform/library.py::is_citable` exigía `verified and doi`; el Investigador
(`modules/agents/adapters/investigador.py`) se abstenía con 0/3 fuentes «verificadas» teniendo
documentos propios sin DOI, y no había forma de que una persona los declarase citables.

### Qué se hizo y por qué
- `models/library_document.py` + migración `alembic/versions/0011_author_provided_sources.py`: columnas
  `author_provided`, `author_provided_at`, `author_provided_by` y CHECK `author_provided = false OR (doi IS NULL AND author_provided_at IS NOT NULL)`
  (un DOI declarado no se «lava», AC14).
- `platform/library.py`: `source_class` (`identified` / `author_provided` / `None`), `is_citable` y
  `citable_documents` sobre ella, `declare_author_provided` (exige persona, documento aceptado y sin DOI)
  y `revoke_author_provided` (reversible). `mark_verified` limpia la declaración: un DOI verificado pasa a la clase identificada.
- `routers/agents.py`: `POST /agents/rag/library/records/{id}/author-provided` (`{declared: bool}`), 409 si el
  documento tiene DOI o no está aceptado. `library_upload.document_view` expone clase y registro de quién/cuándo.
- `adapters/investigador.py`: cuenta fuentes citables de ambas clases; cada entrada de `sources` lleva
  `source_class` (y `author_provided_at`); el mensaje de abstención habla de «citables» y dice cómo resolverlo
  (verificar el DOI **o** declararlo «aportado por el autor»); `abstention.citable_sources` se añade (se conserva
  `verified_sources` por compatibilidad con trazas y evals). El listado de fuentes al Redactor no inventa DOI.
- Frontend (`LibraryRecordsPanel.jsx`, `api/agents.js`, i18n es/en): acción «Declarar aportado por el autor» /
  «Quitar declaración» y etiqueta visible «Aportado por el autor».
- Tests: `tests/test_author_provided_sources.py` (12) y ajuste del texto en `test_investigador_verified_only.py`.

### Definition of Done
- [x] AC4 — un documento sin DOI resoluble queda «sin verificar» y solo puede figurar en Referencias si se verifica el DOI, lo aporta el autor o lo declara «aportado por el autor».
- [x] AC5 — `sources` solo incluye aceptados citables de las dos clases, con `source_class`; sin declarar sigue siendo contexto; sin excepción implícita.
- [x] AC7 — abstención solo por menos de `research.min_sources` fuentes citables; no sintetiza (test: el LLM no se llama).
- [x] AC14 — declaración con quién/cuándo, reversible, solo persona, rechazada con DOI declarado; el Investigador no se abstiene por falta de DOI; mensaje accionable; ejecución con todas las fuentes identificadas, sin cambios.

### Verificación
- `cd backend && DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q` → 1937 passed; 1 fallo preexistente (`test_no_tracked_databases::test_a_fresh_dev_database_is_created_and_migrated`, bloqueo de fichero en Windows, falla igual en develop). Los 17 errores vistos eran por correr con `-p no:logging` (fixture caplog); sin esa bandera pasan.
- `tests/test_author_provided_sources.py`, `test_investigador_verified_only.py`, `test_migrations.py`, `test_i18n_checks.py` → 77 passed.
- `cd frontend && npm run build` → OK; `python scripts/check_i18n.py` → OK.

### Fuera de alcance / notas
- Compuerta (SPEC-032 AC17/AC18, V09 `author_supplied`, severidad por proyecto, etiqueta en Referencias): tarea propia. Hasta entonces la comprobación de estructura de referencias puede marcar una fuente sin identificador.
- Datasets EDD de T22.9 que afirman «un documento interno sin verificar no se cita» no se tocan; se actualizan junto con la compuerta.
