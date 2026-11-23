# Tarea #617 — T22.11 Cablear la búsqueda: endpoint y formulario que crean candidatos verificados, y flag LITERATURE_DISCOVERY_ENABLED

## 2026-11-22 20:20 — Completada ✅

- **Rama:** `feat/617-cablear-busqueda`
- **PR:** → `develop` (`Closes #617`)
- **Spec/ADR:** [SPEC-034](../specs/SPEC-034-verified-literature-discovery-and-library.md) (AC12, apartado 4 «Cableado del descubrimiento») · [ADR-0011](../adr/0011-publication-gate-fail-closed.md) · SPEC-024 (egress)
- **Dependencias:** #524, #525, #526, #530 y #531 cerradas (verificado con `gh`).

### Qué se hizo y por qué
Cierra el hallazgo de la bitácora de #606: nada en producción creaba candidatos desde una búsqueda.
Lo dispara la persona autora, no el Investigador.
- `backend/app/platform/library_discovery.py` (nuevo): `discover_and_store` llama a `run_literature_search` (registro de búsqueda AC6 incluido) y guarda con `verification.add_candidate_to_library` solo los verificados cuyo DOI no está ya en la biblioteca del proyecto (`library_dois_of`: mismo proyecto, cualquier estado; además captura `DuplicateDocumentError` por carreras). Devuelve nuevos, ya existentes, descartados sin verificar y el estado por base. De cada base solo se devuelve una etiqueta cerrada, nunca `BaseReport.message` (puede llevar URL con clave o correo). Con el flag apagado responde sin tocar la red ni escribir nada.
- `backend/app/routers/agents.py`: `POST /rag/library/search` (`require_redactor` + `get_project_context`; bases pedidas limitadas a `research.sources` del proyecto vía `alejandria.package().research`; 422 por base no activa o consulta no válida, incluida la de más de 300 caracteres de `clean_query`; 429 con `Retry-After`; 502 genérico ante fallo inesperado) y `GET /rag/library/search/config` (para que el panel sepa si está activo y qué bases hay).
- `backend/app/core/config.py`, `.env.example` (raíz y `backend/`): `LITERATURE_DISCOVERY_ENABLED` (apagado por defecto), `LITERATURE_SEARCH_RATELIMIT_MAX` (5) y `..._WINDOW_SECONDS` (60), también en `config.yaml` (`literature:`).
- `backend/app/core/rate_limit.py`: `literature_search_limiter` (el `SlidingWindowCounter` existente), por usuario; entra en `reset_auth_throttling`.
- Frontend: `SearchForm` en `LibraryRecordsPanel.jsx` (consulta, bases activas, resultado por base, cargando/error, `aria-live`, etiquetas y ayuda; con el flag apagado el panel lo dice y sigue funcionando) y dos métodos en `api/agents.js`. `platform/` no importa de `projects/`.
- `backend/README.md`: dos filas en la tabla de endpoints. `data-retention.md` sin cambios: no hay tablas nuevas; el registro de búsqueda ya está cubierto por `search_logs`.
- `backend/tests/test_library_discovery_endpoint.py` (nuevo, 12 casos, sin red real).

### Definition of Done
- [x] **AC12** — búsqueda sobre `research.sources` (por defecto OpenAlex y Crossref) con registro AC6; cada verificado nuevo se guarda como `candidate` con doi, year, journal, authors, source_db y `open_access_url` (`test_guarda_solo_verificados…`), y aparece en `/records` (panel «Candidatos»).
- [x] No verificado nunca se guarda (el candidato «inventado» queda descartado); DOI ya presente en cualquier estado no se recrea (`test_doi_ya_en_la_biblioteca…[candidate|accepted|discarded]`, `test_repetir…`); la respuesta indica nuevos y estado por base, y una base caída no oculta a las demás (`test_una_base_caida…`, `test_todas_caidas…`).
- [x] Flag apagado: «descubrimiento desactivado», cero peticiones, sin registro ni fichas (`test_apagado…`, `test_flag_apagado_por_defecto`); el panel sigue con lo ya importado.
- [x] Limitador aplicado (`test_limitador_y_permisos`), aislamiento entre proyectos (`test_aislamiento_entre_proyectos`).

### Verificación
- `cd backend && DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest tests/test_library_discovery_endpoint.py -q` → 12 passed.
- Suite completa del backend: 1795 passed, 38 skipped, 1 failed (`tests/test_no_tracked_databases.py::test_a_fresh_dev_database_is_created_and_migrated`, fallo conocido solo en Windows por `PermissionError` al borrar el temporal; ajeno a esta tarea, ya anotado en #606).
- `cd frontend && npm run build` → OK; `npm run build:public` → OK.

### Notas y límites
- No probado contra OpenAlex/Crossref reales ni en navegador: tests con dobles de `egress.safe_get`; el formulario solo se compiló.
- El limitador es en memoria por proceso (como el de auth); con varias réplicas el tope se multiplica.
- La respuesta con el flag apagado es 200 con `enabled: false`, no un error: el panel lo trata como estado, no como fallo.
- Las bases de una búsqueda salen de la plantilla de AlejandrIA (`alejandria.package()`), igual que el Investigador; si hubiera plantillas por proyecto habría que resolverlas por proyecto.
- Sigue fuera de alcance que el Investigador lance búsquedas por su cuenta.
