# Tarea #536 — T23.3 Criterio de compuerta de soporte con solape determinista y falla cerrada

## 2026-11-23 08:00 — Completada ✅

- **Rama:** `feat/536-compuerta-soporte`
- **PR:** → `develop` (`Closes #536`)
- **Spec/ADR:** [SPEC-035](../specs/SPEC-035-citation-support-and-retractions.md) (AC2, AC4) · [ADR-0011](../adr/0011-publication-gate-fail-closed.md) · [SPEC-032](../specs/SPEC-032-publication-gate-framework.md)
- **Dependencias:** #534 (T23.1) y #535 (T23.2) mergeadas (verificado con `gh`/`git log`).

### Dónde estaba el problema
La compuerta (`platform/publication_gate/gate.py`) comprobaba que las referencias existen, pero
nada contrastaba cada cita del texto con el fragmento al que apunta. `citation_links` (T23.2)
nacía `not_verified` pero ningún criterio lo leía.

### Qué se hizo y por qué
- `platform/publication_gate/citation_support.py` (nuevo): `check_citation_support(text, links, min_overlap)`,
  determinista y sin LLM (el juez es T23.4). Por cita:
  - sin `doc_id` o sin extracto -> `not_verified` (`no_fragment`); la confirmación manual **no** la rescata;
  - solape (fracción de palabras con contenido de la afirmación presentes en el extracto, sin
    acentos ni mayúsculas) por debajo de `min_overlap` -> `needs_human_review` (`low_overlap`) sin
    llamar a ningún juez; deja de bloquear cuando el autor la confirma (`confirmed_at`);
  - `[F#]` del texto sin fila en el mapa (`unmapped`), texto sin citas (`no_citations`), afirmación sin
    palabras con contenido (`no_claim`) y mapa ilegible (`map_unavailable`) -> `not_verified`.
  - Un solape alto solo deja la cita pasar a T23.4; no la declara soportada.
- `config.py`: `gate.citation_support.min_overlap` (0..1, por defecto 0.25) validado al cargar; sin el
  bloque, el criterio no se declara y la compuerta es la de siempre (`citation_support_min_overlap=None`).
- `gate.py`: `evaluate_gate(..., citations=)` añade el criterio si está declarado; `citations=None` da `not_verified`, nunca se omite.
- `service.py`: `evaluate_and_store` lee el mapa vigente (`current_citation_map`) cuando el criterio está declarado.
- `explain.py`: resumen del criterio para el informe.
- `tests/test_gate_citation_support.py`: 11 tests (unidad, configuración e integración con BD).

### Definition of Done
- [x] **AC2** — cita sin fragmento -> `not_verified` y bloquea (`test_ac2_*`, `test_falla_cerrada_*`).
- [x] **AC4** — solape bajo umbral configurable -> revisión humana sin juez (`test_ac4_*`).

### Verificación
- `DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q tests/test_gate_citation_support.py tests/test_publication_gate.py tests/test_gate_explain.py tests/test_citation_links.py` -> 52 passed.
- Suite completa de backend (`python -m pytest -q`, 34m46s) -> 1830 passed, 38 skipped, 1 failed: `test_no_tracked_databases.py::test_a_fresh_dev_database_is_created_and_migrated` por `PermissionError WinError 32` al borrar un tmp en Windows (fallo conocido, ajeno al cambio).

### Fuera de alcance / notas
- **No se activa en `projects/alejandria/template.yaml`**: el Publicador aún no persiste el mapa de citas
  (`save_citation_map` no se invoca en el pipeline), así que activarlo bloquearía toda publicación. Se
  activará cuando el pipeline guarde el mapa (seguimiento de T23.4/T23.6). Hasta entonces es opt-in por `gate.citation_support`.
- El solape se calcula sobre el `excerpt` guardado (inicio del fragmento), no el texto completo: puede dar falsos positivos, por eso es revisión humana.
- Sin cambios de esquema ni de retención.
