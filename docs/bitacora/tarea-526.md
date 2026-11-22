# Tarea #526 — T22.3 Migración y modelos: library_documents y search_logs con metadatos bibliográficos

## 2026-11-22 12:10 — Completada ✅

- **Rama:** `feat/526-library-documents-search-logs`
- **PR:** ver enlace en la PR (`Closes #526`) → `develop`
- **Spec/ADR:** SPEC-034 (AC3, AC6; Clarifications 2026-11-22), ADR-0011, SPEC-020 (retención)
- **Dependencias:** ninguna

### Dónde estaba el problema
No existía ninguna tabla para los metadatos bibliográficos (DOI, autores, año, revista,
base de origen), ni para la curación del autor, ni para el registro de búsqueda. El RAG solo
guardaba esos datos, si el autor los aportaba, en el payload de Qdrant.

### Qué se hizo y por qué
Solo capa de datos; sin clientes externos (T22.1), verificación (T22.2), API/UI (T22.8),
exportación en la traza (T22.7) ni descarga de PDF (T22.10).

- `backend/app/models/library_document.py` (nuevo): `LibraryDocumentModel` y enums `SourceDB`,
  `TextStatus`, `CurationStatus`, `VerificationMethod`, más `normalize_doi`. Campos: `project_id`
  (FK CASCADE), `doc_id` (RAG), `doi`, `title`, `authors` (JSON), `year`, `journal`, `abstract`,
  `url`, `open_access_url` y `source_id` (los necesitan T22.2/T22.10), `source_db`, `text_status`
  (defecto `abstract_only`), `curation_status` (defecto `candidate`), `must_cite`, `verified`,
  `verification_method`, `verified_at`, `verified_by`, `added_by`, `created_at`, `updated_at`.
- `backend/app/models/search_log.py` (nuevo): `SearchLogModel`: `project_id`, `article_id`
  (SET NULL), `user_id`, `query`, `sources`, `filters`, `result_count`, `verified_count`,
  `per_source`, `discarded`, `status` (`completed|partial|failed`, AC10) y `searched_at`
  (= fecha de corte, AC2). No guarda texto del manuscrito ni claves.
- `backend/alembic/versions/0008_library_search_logs.py`: migración **0008**, generada con
  `--autogenerate` y revisada (el ciclo de FKs `users`↔`projects` no interviene: solo se
  referencian). Reversible; downgrade probado.
- `backend/app/platform/library.py` (nuevo): persistencia mínima (añadir con DOI duplicado
  detectado, listar, `citable_documents` = aceptado + verificado, `set_curation`, `mark_verified`
  —`author_supplied` exige `verified_by`—, `set_text_status`, `record_search`, `list_searches`).
  Todo filtra por `project_id`.
- Retención: `RETENTION_SEARCH_LOGS_DAYS` (config.py, config.yaml), purga en
  `app/platform/retention.py` y documentación en `docs/governance/data-retention.md`.
- `backend/tests/test_library_models.py` (nuevo, 23 tests).

### Decisiones
1. **Unicidad del DOI** (la spec la dejó abierta): `UNIQUE (project_id, doi)` con el DOI
   **normalizado** (minúsculas, sin `https://doi.org/` ni `doi:`). Unicidad **por proyecto**, no
   global, porque la biblioteca está aislada por proyecto (T8.5) y dos proyectos pueden citar el
   mismo paper. Con DOI nulo no hay restricción (cada `NULL` es distinto en SQLite y Postgres), así
   que varios documentos «sin verificar» conviven (AC4). Se usa un `UniqueConstraint` normal y no
   un índice parcial: es portable y equivalente.
2. **Estados como `String` + `CHECK`**, no enums nativos de Postgres, para no repetir el problema
   de 0002 (etiquetas del enum nativo difíciles de ampliar: `ALTER TYPE … ADD VALUE` fuera de
   transacción). Los valores se validan además en el modelo (`@validates`).
3. **Invariantes ADR-0011 en la base**: `verified = true` exige `doi`, `verification_method` y
   `verified_at`; `must_cite` solo con `curation_status = 'accepted'`. Que `author_supplied`
   registre quién lo aportó se exige en `library.mark_verified` y **no** en un CHECK, porque
   `verified_by` es `ON DELETE SET NULL` y un CHECK haría fallar el borrado de ese usuario en
   Postgres.
4. **Retención de `search_logs`: 365 días, y no caduca si el artículo está publicado.** Es el
   apartado de métodos de un artículo que se escribe durante meses (90 días lo borraría antes de
   que sirva); la cadena de búsqueda es texto del autor, así que no se acumula indefinidamente. Las
   búsquedas sin artículo o de borradores caducan. `library_documents` no caduca (contenido del
   producto).

### Definition of Done
- [x] **AC3** — `library_documents` guarda `doi`, `year`, `journal`, `authors` y `source_db`, el
  estado `candidate|accepted|discarded` y la marca `must_cite`; `library.set_curation` acepta,
  descarta o marca imprescindible. (La UI es T22.8.)
- [x] **AC6** — `search_logs` persiste bases (`sources`), fecha (`searched_at`), cadena (`query`),
  `filters` y `result_count` (más `verified_count`, `per_source`, `discarded`, `status` para
  reproducir); `library.record_search` lo escribe. (Exportación y traza son T22.7.)
- [x] Migración Alembic reversible, `test_migrations.py` (esquema migrado = `create_all`) en verde.
- [x] Tablas documentadas en `data-retention.md` con ventana definida y purga implementada.

### Verificación
- `python -m pytest -q tests/test_library_models.py tests/test_migrations.py tests/test_data_retention.py`
  → 70 passed (antes de quitar el CHECK `author_supplied`, ver decisión 3).
- `DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q` (backend, suite completa, tras el último cambio) → 1592 passed, 38 skipped, 1 failed: `tests/test_no_tracked_databases.py::test_a_fresh_dev_database_is_created_and_migrated` (conocido, PermissionError WinError 32 en Windows, sin relación con este cambio).
- **Postgres real: NO verificado** (no hay Postgres ni Docker en esta máquina). Solo se compiló el
  DDL de ambas tablas con el dialecto `postgresql` de SQLAlchemy (sintaxis válida: `UNIQUE`,
  `CHECK`, `BOOLEAN`). La job «Migraciones · Postgres real» de la CI es la comprobación real;
  `scripts/verify_postgres_schema.py` no se ha ampliado.

### Fuera de alcance / notas
- EDD (DoR/DoD de agentes): no aplica, no se tocan agentes, prompts, dispatcher ni siembra.
- Sin migración de datos: las tablas nacen vacías. Qdrant no se toca.
- Pendiente para T22.4/T22.5: enlazar `doc_id` con el indexado y filtrar `sources` por
  `library.citable_documents`.
