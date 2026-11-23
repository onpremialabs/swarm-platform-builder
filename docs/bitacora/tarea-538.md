# Tarea #538 — T23.5 Comprobación de retractaciones y expresiones de preocupación vía Crossref

## 2026-11-23 — Completada ✅

- **Rama:** `feat/538-retractaciones`
- **PR:** → `develop` (`Closes #538`)
- **Spec/ADR:** [SPEC-035](../specs/SPEC-035-citation-support-and-retractions.md) (AC5) · [SPEC-032](../specs/SPEC-032-publication-gate-framework.md) / [ADR-0011](../adr/0011-publication-gate-fail-closed.md) · SPEC-024 (egress)
- **Dependencias:** ninguna.

### Qué se hizo y por qué
- `backend/app/platform/publication_gate/retractions.py` (nuevo): criterio `retractions`. Por cada referencia citable con DOI consulta `GET api.crossref.org/works/<DOI>` y lee `updated-by`: `retraction`, `withdrawal` y `removal` son «retractada»; `expression_of_concern` es «preocupación»; el resto (correcciones, nuevas versiones) se ignora. Sale por `egress.safe_get(quien="publication_gate")` (reutiliza la sesión del resolver: reintentos, backoff, tiempo máximo). Un DOI repetido se consulta una vez.
- **Falla cerrada (ADR-0011):** red, 5xx, 429, JSON inválido, forma inesperada o tiempo agotado dejan la referencia `not_verified` (bloquea). En la evidencia solo se guarda un código fijo (`crossref_unavailable` / `crossref_bad_response`), nunca el texto de la excepción, que puede llevar la URL. Un 404 de Crossref, una referencia sin DOI o un DOI de DataCite (`10.48550/`) no se juzgan aquí: lo cubre `reference_existence`.
- **Severidad configurable** (`gate.retractions` en `template.yaml`): `retracted: block|warn` (por defecto `block`) y `concern: block|warn` (por defecto `warn`). Con `warn` el criterio pasa pero el aviso queda en la evidencia (`severity: warn`). Declarar el bloque activa el criterio; sin él la compuerta no cambia (así no se alteran otros proyectos ni tests).
- `config.py`: `GateConfig.retractions` y validación al cargar. `gate.py`: ejecuta el criterio tras los demás sobre las fuentes ya enriquecidas, con el mismo `fetch`/`sleep`/`clock` (cambio mínimo; no toca `citations.py` ni el criterio de soporte de T23.3). `explain.py`: resumen (`retracted`, `concern`, `unchecked`, `warnings`).
- `template.yaml` de AlejandrIA: activa el criterio y lo asigna a `investigador` en `gate.responsible`.
- Frontend `gate.js`: etiqueta y líneas de resumen del criterio (sin esto el informe mostraba el código crudo).
- `docs/governance/data-retention.md`: qué sale a Crossref (solo el DOI), sin tabla nueva ni caché persistente.
- Tests: `backend/tests/test_gate_retractions.py` (20 casos, `fetch` simulado) y ajuste de `test_publication_gate.py` (la plantilla ahora declara un criterio más).
- **Sin migración**: no hay tabla nueva; los avisos viajan en `publication_gate_reports.criteria`.

### Definition of Done
- [x] **AC5** — con DOI se consulta Crossref y se detecta retractada o con expresión de preocupación (`test_retractada_bloquea…`, `test_expresion_de_preocupacion…`); la compuerta bloquea o avisa según severidad configurada (`test_severidad_configurable`, `test_config_valida_severidades`); si no se puede consultar, falla cerrada (`test_si_crossref_no_responde…`).

### Verificación
- `cd backend && DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q` (suite completa) → 1837 passed, 38 skipped, 2 failed: `test_no_tracked_databases.py::test_a_fresh_dev_database_is_created_and_migrated` (fallo conocido en Windows, WinError 32) y `test_publication_gate.py::test_manuscrito_valido_pasa_y_lista_lo_pendiente` (lista de criterios de la plantilla; corregido en esta PR).
- Tras el ajuste: `pytest tests/test_publication_gate.py tests/test_gate_retractions.py tests/test_gate_deployment.py tests/test_gate_explain.py tests/test_frontend_gate.py -q` → 72 passed. No se repitió la suite completa tras ese cambio de una línea en un test.
- `cd frontend && npm run build` → OK.

### Fuera de alcance / notas
- No se probó contra Crossref real (solo respuestas simuladas con la forma documentada de `updated-by`).
- No se consulta `relation`/`update-to` ni Retraction Watch directamente; se confía en `updated-by` de Crossref.
- La pestaña Fuentes por cita (T23.6) y el criterio de soporte (T23.3) quedan fuera.
