# Tarea #606 — T22.10 Descarga de PDF de acceso abierto por safe_get y estado «solo resumen» (text_status)

## 2026-11-22 — Completada ✅

- **Rama:** `feat/606-pdf-acceso-abierto`
- **PR:** → `develop` (`Closes #606`)
- **Spec/ADR:** [SPEC-034](../specs/SPEC-034-verified-literature-discovery-and-library.md) (AC11) · [ADR-0011](../adr/0011-publication-gate-fail-closed.md) · SPEC-024 (egress)
- **Dependencias:** #524 (T22.1) y #526 (T22.3) cerradas; T22.4, T22.8 y T22.2 ya en `develop`.

### Qué se hizo y por qué
- `backend/app/platform/library_fulltext.py` (nuevo):
  - `fetch_open_access_pdf(url)`: descarga **solo** por `egress.safe_get(quien="literature_discovery")` y **solo** la `open_access_url` de la ficha (nunca otra URL, ni `doi.org`, ni espejos; no se elude ningún paywall). Valida código 200, tipo de contenido (`application/pdf`/octet-stream; un `text/html` es una página, no un PDF), tamaño (`Content-Length` y bytes, 10 MB como la subida manual) y contenido real con `uploads.validate_upload` (magic bytes).
  - `index_pdf(...)`: extrae, trocea e indexa en la biblioteca del proyecto (`project.collection`, mismo camino que la subida manual).
  - `accept_with_fulltext(...)`: confirma la aceptación **antes** de intentar la descarga; si hay URL y todo sale bien, `text_status=full_text` con `doc_id`; sin URL o ante cualquier fallo (red, egreso bloqueado, no es PDF, tamaño, sin texto, índice caído) queda `abstract_only`. No reintenta al marcar «imprescindible» sobre una ficha ya aceptada.
- `backend/app/routers/agents.py`: `POST …/records/{id}/curation` usa lo anterior al aceptar y añade `fulltext` y `fulltext_detail` a la respuesta; `POST /rag/library/upload` acepta `document_id` opcional: indexa el PDF y pasa **esa** ficha a `full_text` (sin crear otra).
- Frontend mínimo (`LibraryRecordsPanel.jsx`, `api/agents.js`): etiqueta visible «solo resumen» (texto, no solo color), botón «Subir PDF» en fichas aceptadas `abstract_only`, y mensaje al aceptar según el resultado.
- `backend/tests/test_library_fulltext.py` (nuevo, 14 casos, sin red real).

### Definition of Done
- [x] **AC11** — con URL de acceso abierto: descarga por `safe_get` (`quien="literature_discovery"`), indexa y `full_text` (`test_aceptar_con_url_abierta…`); sin URL o con descarga fallida/ inválida (404, HTML, falso PDF, tamaño, red, egreso bloqueado, índice caído): se acepta como `abstract_only` con etiqueta «solo resumen»; subir el PDF después la pasa a `full_text` (`test_subir_el_pdf_despues…`). Nunca PDFs de pago ni evasión de paywalls: solo `open_access_url`.

### Verificación
- `cd backend && DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest tests/test_library_fulltext.py -q` → 14 passed.
- Suite completa del backend: 1348 passed, 38 skipped hasta `tests/test_no_tracked_databases.py::test_a_fresh_dev_database_is_created_and_migrated`, que falla solo en Windows (`PermissionError WinError 32` al borrar el directorio temporal con `dev.db` abierto; ajeno a esta tarea). El resto de ficheros posteriores, ejecutado aparte: 434 passed.
- `cd frontend && npm run build` → OK.

### Notas y límites
- **Hallazgo (no implementado):** nada en producción crea filas `library_documents` con `curation_status=candidate` desde una búsqueda. `run_literature_search` (T22.7) y `verification.add_candidate_to_library` (T22.2/T22.3) solo se llaman desde tests; no hay endpoint ni nodo del pipeline que los invoque. El panel de candidatos queda vacío salvo fichas importadas a mano. Requiere una tarea de cableado (endpoint de búsqueda y/o integración con el Investigador, SPEC-034 AC1/AC6).
- `safe_get` lee la respuesta completa en memoria: el tope de 10 MB se aplica por `Content-Length` y tras recibirla, no cortando el flujo. Una URL hostil puede hacernos leer más antes de rechazar.
- Sin Qdrant/Ollama ni red reales: la indexación y la descarga se probaron con dobles.
- Si la descarga falla no hay botón de reintento; la vía es subir el PDF.
