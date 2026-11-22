# Tarea #531 — T22.8 Frontend: panel de candidatos y biblioteca con DOI, año, revista y estado, e importación BibTeX/DOI

## 2026-11-22 17:00 — Completada ✅

- **Rama:** `feat/531-panel-candidatos-biblioteca`
- **PR:** → `develop` (`Closes #531`)
- **Spec/ADR:** [SPEC-034](../specs/SPEC-034-verified-literature-discovery-and-library.md) (AC3, AC9) · [ADR-0011](../adr/0011-publication-gate-fail-closed.md) · SPEC-003 (estados y accesibilidad)
- **Dependencias:** #525 (T22.2) y #526 (T22.3) cerradas; T22.4 (#527) ya en `develop`.

### Dónde estaba el problema
La pantalla Documentos (`frontend/src/platform/pages/DocumentsPage.jsx`) solo listaba documentos vectorizados (nombre y chunks). Las fichas bibliográficas de `library_documents` (T22.3/T22.4) no tenían UI. En backend existían `GET`/`PATCH /agents/rag/library/records`, pero **faltaban** endpoints para aceptar/descartar/marcar «imprescindible» (`library.set_curation` sin API) y para importar BibTeX o DOI.

### Qué se hizo y por qué
- **Backend (mínimo, con tests)**
  - `backend/app/routers/agents.py`: `POST /agents/rag/library/records/{id}/curation` (estado + `must_cite`; 404 si es de otro proyecto, 422 estado inválido) y `POST /agents/rag/library/import` (`{bibtex}` o `{dois}`, exactamente uno; devuelve resultado por entrada). Ambos con `require_redactor` y `get_project_context`.
  - `backend/app/platform/library_import.py` (nuevo): parser BibTeX pequeño, parser de lista de DOI, e importación. Cada DOI se verifica con el mismo resolver de la compuerta (por `safe_get`, `quien=literature_discovery`); solo si resuelve y coincide queda `doi_resolved`. Lo demás se importa **sin verificar** (no citable, ADR-0011). Falla cerrada: resolver caído nunca verifica. Un lote no se aborta por una entrada mala; máx. 100 entradas.
  - `backend/app/platform/publication_gate/reference_resolver.py`: fachada pública `lookup_doi` sobre `_lookup_doi` (la lista de DOI no tiene título con el que usar `resolve_reference`).
  - `backend/app/platform/library_upload.py`: `document_view` incluye `must_cite`.
  - `backend/README.md`: tabla de endpoints.
- **Frontend**
  - `frontend/src/platform/api/agents.js`: `getLibraryRecords`, `updateLibraryRecord`, `curateLibraryRecord`, `importLibraryRecords`.
  - `frontend/src/platform/components/library/LibraryRecordsPanel.jsx` (nuevo): pestañas Candidatos / Biblioteca / Descartados con DOI, año, revista, base y estado de verificación (texto, no solo color); acciones Aceptar, Descartar, Imprescindible; modal de edición de metadatos (aportar DOI verifica como `author_supplied`); modal de importación BibTeX / lista de DOI con resultado por entrada.
  - `DocumentsPage.jsx`: monta el panel. Vive en `platform/` y no importa de `projects/`.
  - Estados: cargando y error con reintento (`AsyncState`, sin confundir fallo con vacío), vacío propio por pestaña, errores de formulario con `role="alert"`. Accesibilidad: `Modal` del sistema (foco atrapado, Esc), etiquetas `label`/`htmlFor`, `aria-pressed` en filtros, botones con `aria-label` que nombran la ficha.

### Definition of Done
- [x] **AC3** — el autor revisa candidatos y puede aceptar, descartar o marcar «imprescindible» (panel + `POST …/curation`; `test_api_importar_y_curar`); los aceptados quedan en la biblioteca con `doi`, `year`, `journal`, `authors`, `source_db` (visibles en la pestaña Biblioteca; ya los guarda `library_fields`/`add_document`).
- [x] **AC9** — Documentos muestra DOI, año, revista y estado de verificación; permite editar metadatos (`PATCH` existente) e importar BibTeX o lista de DOI (`tests/test_library_curation_import.py`).

### Verificación
- `cd backend && DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest tests/test_library_curation_import.py -q` → 6 passed (sin red real, `egress.safe_get` doblado).
- Suite completa `python -m pytest -q` → 1769 passed, 38 skipped, 1 failed: `tests/test_no_tracked_databases.py::test_a_fresh_dev_database_is_created_and_migrated` (WinError 32 en Windows, conocido y ajeno; ya fallaba en #527).
- `cd frontend && npm run build` → OK. `npm run build:public` → OK.

### Fuera de alcance / notas
- **No probado en navegador real**: solo build y tests de backend; no hay test de componentes en el repo. Conviene un repaso manual (foco de modales, teclado).
- Los candidatos aparecen cuando T22.7 los persista como `candidate`; hoy el panel puede estar vacío en esa pestaña.
- Importar crea fichas `accepted`, `abstract_only`, `source_db=manual` (lo pidió el autor). Una entrada BibTeX con DOI no verificable por «resolver caído» conserva el DOI para reintentar editándolo; con discrepancia, se descarta el DOI.
- El parser BibTeX no expande macros (`@string`, `#`).
- Sin descarga de PDF de acceso abierto (T22.10).
