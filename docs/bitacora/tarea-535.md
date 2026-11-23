# Tarea #535 — T23.2 Migración y persistencia del mapa cita→fragmento versionado con el texto

## 2026-11-23 05:10 — Completada ✅

- **Rama:** `feat/535-mapa-cita-fragmento`
- **PR:** → `develop` (`Closes #535`)
- **Spec/ADR:** [SPEC-035](../specs/SPEC-035-citation-support-and-retractions.md) (AC1, AC6, §4 «Datos») · [ADR-0011](../adr/0011-publication-gate-fail-closed.md) (falla cerrada)
- **Dependencias:** ninguna.

### Qué se hizo y por qué
Solo la capa de datos; no se tocan prompts ni el adapter del Redactor (es #534/T23.1).
- `backend/app/models/citation_link.py` (nuevo): `CitationLinkModel` (`citation_links`), una fila por cita del texto: `article_id` (CASCADE), `run_id` (SET NULL), `text_sha256` (la versión), `citation_key`, `claim_index`, `claim`, `doc_id`, `page`, `section`, `excerpt`, `excerpt_sha256`, `status` (`not_verified|supported|partial|unsupported`, CHECK, por defecto `not_verified` = falla cerrada), `rationale`, y la confirmación manual `confirmed_by`/`confirmed_at`. Único por (artículo, huella, cita, índice). Más `CitationLinkResponse`. Exportado en `app/models/__init__.py`.
- `backend/alembic/versions/0010_citation_links.py`: generada con `alembic revision --autogenerate` sobre una base migrada a `0009`; revisada (sin SQL a mano, sin ciclo de FKs implicado), con índices y `downgrade` simétrico.
- `backend/app/platform/citations.py` (nuevo): `save_citation_map` (versiona por huella del texto; re-guardar la misma huella reemplaza y es idempotente, otras versiones se conservan; las confirmaciones se conservan solo si cita, frase y extracto no cambiaron), `get_citation_map`, `current_citation_map` (la de la huella del cuerpo actual) y `confirm_citation` (registra quién y cuándo, sin tocar `status`: veredicto automático y humano van separados). Recorta `claim` (1.000) y `excerpt` (2.000): nunca el manuscrito entero.
- Retención: `RETENTION_CITATION_LINKS_DAYS` (90 días, solo artículos no publicados, como los informes de la compuerta) en `config.py`, `config.yaml`, `retention.py` y `docs/governance/data-retention.md` (tabla, razonamiento y ejemplo YAML). `tests/test_data_retention.py` incluye el nuevo conjunto en `EXPIRING`.
- `backend/tests/test_citation_links.py` (nuevo, 10 casos).

### Definition of Done
- [x] **AC1** — se guarda el mapa `cita → {doc_id, página, extracto, hash}` por afirmación citada, versionado con la huella SHA-256 del texto evaluado (`test_saves_map_…`, `test_new_text_version_keeps_the_previous_map`, `test_current_map_is_the_one_for_the_current_body`). **Alcance:** la persistencia está lista; que el Redactor al terminar llame a `save_citation_map` con las citas extraídas depende de #534 (T23.1) y no se cableó aquí a propósito.
- [x] **AC6 (parte de datos)** — hay estado por cita, extracto, `doc_id`/página para el enlace, y confirmación manual con quién y cuándo (`test_confirm_records_who_and_when…`, `test_resaving_same_text_is_idempotent_and_keeps_confirmations`, `test_changed_excerpt_drops_the_confirmation`). **Fuera:** endpoint de lectura/confirmación y vista de la pestaña Fuentes (T23.6, depende de T23.3).
- [x] Migración Alembic + `test_migrations.py` (migrado == `create_all`) en verde.
- [x] Retención documentada y probada (`test_retention_purges_old_drafts_but_not_published`, tests de `test_data_retention.py`).

### Verificación
- `cd backend && DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q tests/test_citation_links.py tests/test_data_retention.py tests/test_migrations.py` → 58 passed (655 s: la máquina iba cargada con otras ejecuciones en paralelo).
- `alembic upgrade head` sobre una base vacía llega a `0010` y `alembic revision --autogenerate` posterior no detecta diferencias de esquema (lo cubre `test_migrations.py`).
- **No ejecutado:** la suite completa del backend (por tiempo; las ejecuciones en esta máquina tardaron >10 min para 58 tests) ni `npm run build` (no se tocó el frontend). Queda para la CI de la PR.

### Notas y límites
- **Numeración Alembic:** `0010_citation_links` con `down_revision = 0009_step_searches`, que es la última de `develop` a esta fecha. Si #534 u otra PR añaden también una `0010`, quien mergee segundo debe renumerar a la siguiente libre y reencadenar `down_revision` (`alembic heads` debe dar una sola cabeza).
- No probado contra PostgreSQL: solo SQLite (los tests de migración de la suite). El CHECK y las FKs son estándar.
- SQLite de test no aplica FKs en cascada (sin PRAGMA): el CASCADE se verifica por declaración, no por borrado real.
- No hay endpoint ni UI todavía; `status` solo nace `not_verified` (lo cambiará la compuerta en T23.3/T23.4).
