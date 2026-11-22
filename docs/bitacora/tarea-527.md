# Tarea #527 — T22.4 Resolución de DOI de PDFs subidos y edición manual de metadatos

## 2026-11-22 15:45 — Completada ✅

- **Rama:** `feat/527-doi-pdfs-subidos`
- **PR:** pendiente de número → `develop` (`Closes #527`)
- **Spec/ADR:** [SPEC-034](../specs/SPEC-034-verified-literature-discovery-and-library.md) (AC4) · [ADR-0011](../adr/0011-publication-gate-fail-closed.md)
- **Dependencias:** #525 (T22.2, verificación) y #526 (T22.3, modelos) cerradas; #611 (T22.5) ya mergeada en `develop`.

### Dónde estaba el problema
`POST /agents/rag/library/upload` (`backend/app/routers/agents.py`) indexaba el documento en el RAG y respondía «indexado», pero **no dejaba ficha** en `library_documents`: sin ficha el Investigador (T22.5) lo trata como «sin verificar», y no había forma de resolverle el DOI ni de que el autor lo aportara. `library.mark_verified` existía sin API.

### Qué se hizo y por qué
- **`backend/app/platform/library_upload.py` (nuevo)**
  - `register_uploaded_document`: crea la ficha (`source_db=manual`, `full_text`, `accepted` —el autor la subió a propósito—, **sin verificar**) y llama a `attempt_resolution`.
  - `attempt_resolution`: reutiliza `literature.verification.verify_candidates` (mismo resolver que la compuerta; sale por `safe_get` con `quien=literature_discovery`; no se abre ninguna conexión nueva). Solo si el registro coincide en título/autores se marca `doi_resolved` (vía `library.mark_verified`) y se completan año/revista. Resolver caído, error inesperado, sin coincidencia o DOI ya presente en el proyecto → la ficha queda sin verificar, **la subida no falla** (falla cerrada). Resolver acotado (`UPLOAD_RESOLVER`: 1 reintento, 30 s en total) para no colgar la petición.
  - `update_metadata`: edita título/autores/año/revista; un DOI nuevo verifica como `author_supplied` registrando `verified_by` y `verified_at` (lo exige `mark_verified`); vaciar el DOI **retira** la verificación; DOI repetido en el proyecto → `DuplicateDocumentError` sin cambiar nada.
  - `document_view`: la ficha tal como la ve el autor (incluye `verified`, `verification_method`, `verified_at`, `verified_by`, `citable`).
- **`backend/app/routers/agents.py`**: la subida crea la ficha y devuelve `library_document`, `doi_resolution` y `doi_resolution_detail`; nuevos `GET /agents/rag/library/records` (fichas del proyecto) y `PATCH /agents/rag/library/records/{id}` (404 si es de otro proyecto, 409 DOI repetido, 422 título vacío). Todo con `get_project_context`.
- **`backend/README.md`**: tabla de endpoints.
- **No se tocó** `library.py` ni `investigador.py` (sin conflicto con #611). «No puede figurar en Referencias» lo garantiza `library.is_citable` (aceptado + verificado + DOI), que ya usa el Investigador: una ficha sin verificar solo es contexto.

### Definition of Done
- [x] **AC4** — PDF subido → se intenta resolver el DOI por título/autores (`test_subir_crea_la_ficha_y_resuelve_el_doi_por_titulo_y_autores`); si no resuelve queda sin verificar (`test_sin_coincidencia…`, `test_un_registro_que_no_coincide…`, `test_resolver_caido…`, `test_sin_titulo_o_autores…`), visible (`GET …/records`) y editable (`PATCH`), el autor aporta el DOI con quién y cuándo (`test_el_autor_aporta_el_doi_con_quien_y_cuando`, `test_api_editar_y_aportar_doi`) y mientras tanto no es citable (`test_un_documento_sin_verificar_no_llega_a_sources_del_investigador`, `citable_documents` vacío).

### Verificación
- `cd backend && DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest tests/test_library_upload_doi.py -q` → 15 passed (sin red real: `egress.safe_get` sustituido por un doble; un test comprueba que todo sale con `quien=literature_discovery`).
- Suite completa `python -m pytest -q` (backend) → 1763 passed, 38 skipped, 1 failed. El único fallo es `tests/test_no_tracked_databases.py::test_a_fresh_dev_database_is_created_and_migrated` (WinError 32 en Windows, conocido y ajeno; el mismo de #528).
- Sin frontend tocado: `npm run build` no aplica.

### Notas y límites
- **Sin UI**: la edición/visualización está solo en API; el panel de biblioteca es T22.8.
- El DOI aportado por el autor **no se contrasta** con el registro al aceptarlo (ADR-0011: `author_supplied` es un método válido); la compuerta de publicación (V09) lo resuelve igualmente al publicar.
- Los documentos subidos **antes** de esta tarea siguen sin ficha (= sin verificar); no hay backfill (seguimiento posible).
- Subida de `.txt/.md/.docx` también crea ficha; sin título o autores extraídos queda `no_metadata` (se usa el nombre de fichero como título).
- EDD: no se tocan perfiles, prompts ni adapters del motor; el gate EDD no se dispara.
