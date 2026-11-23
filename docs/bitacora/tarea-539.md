# Tarea #539 — T23.6 Frontend: estado de cada cita, extracto y confirmación manual en la pestaña Fuentes

## 2026-11-23 09:00 — Completada

- **Rama:** `feat/539-estado-citas-frontend`
- **PR:** ver la PR con `Closes #539` → `develop`
- **Spec/ADR:** SPEC-035 (E23) AC6; ADR-0011 (falla cerrada)
- **Dependencias:** #536 (T23.3) resuelta

### Dónde estaba el problema
Existían el modelo `CitationLinkModel` y `app/platform/citations.py` (`current_citation_map`, `confirm_citation`), pero ninguna ruta los exponía y la pestaña «Fuentes» de `ArticleTraceHistoryPage.jsx` solo mostraba las fuentes RAG recuperadas, sin relación con las citas del texto.

### Qué se hizo y por qué
- `backend/app/routers/articles.py`: dos rutas nuevas.
  - `GET /api/v1/articles/{id}/citations` — mapa vigente (huella del cuerpo actual). Autoriza como la compuerta (autor, revisor asignado, admin) y exige `get_project_context`; un artículo de otro proyecto da 404.
  - `POST /api/v1/articles/{id}/citations/{link_id}/confirm` — `require_redactor` + `get_project_context`; solo autor o admin (el revisor lee pero no confirma); 409 si está publicado; 404 si la cita no pertenece al mapa vigente. Registra `confirmed_by`/`confirmed_at` y no toca `status`.
- `frontend/.../api/articles.js`: `citations` y `confirmCitation`.
- `frontend/.../components/ArticleCitations.jsx` (capa `projects/`, no se importa desde `platform/`): lista por cita con estado (texto + icono, no solo color), afirmación, extracto, enlace a documento/página, botón de confirmar con `aria-label`, y estados de carga (`role=status`, `aria-busy`), vacío, error con «Reintentar» (`role=alert`) y error de acción.
- `ArticleTraceHistoryPage.jsx`: monta el componente al inicio de la pestaña Fuentes.
- `backend/tests/test_article_citations_api.py`: 9 tests (lectura, vacío, confirmación, 404 de cita ajena, sin cabecera 400, otro proyecto 404, tercero, lector, revisor 403).

### Definition of Done
- [x] AC6: con citas evaluadas, la pestaña Fuentes muestra estado, extracto y enlace a documento/página, y permite confirmar registrando quién y cuándo — rutas + componente descritos arriba; probado por API; la UI solo se verificó por build (ver notas).

### Verificación
- `DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q tests/test_article_citations_api.py` (backend/) → 9 passed
- `DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q` completa (backend/, 1h30) → 1859 passed, 38 skipped, 1 failed: `test_no_tracked_databases.py::test_a_fresh_dev_database_is_created_and_migrated` (fallo conocido por WinError 32 en Windows, ajeno al cambio)
- `npm run build` y `npm run build:public` (frontend/) → correctos

### Fuera de alcance / notas
- **Conocido: nada en `backend/app` llama aún a `save_citation_map`.** Ningún flujo persiste el mapa, así que hoy en una instalación real la pestaña muestra siempre el estado vacío («No hay citas evaluadas para la versión actual del texto»). La UI y las rutas están listas y probadas con mapas sembrados en tests; cablear la persistencia (y la evaluación que fija `status`, hoy siempre `not_verified`) queda para otra tarea.
- El enlace a documento apunta a `/dashboard/documents?doc=…&page=…`; `DocumentsPage` aún no interpreta esos parámetros, así que abre la biblioteca sin posicionarse.
- No se probó en navegador real, ni con lector de pantalla; solo builds y tests de API.
- No se tocó `backend/evals` (T23.7, otro agente).
