# Tarea #540 — T23.7 Métrica EDD citation_support con datasets golden y regressions en modo live

## 2026-11-23 10:20 — Completada ✅

- **Rama:** `feat/540-metrica-citation-support`
- **PR:** → `develop` (`Closes #540`)
- **Spec/ADR:** [SPEC-035](../specs/SPEC-035-citation-support-and-retractions.md) (AC8) · [ADR-0006](../adr/) (harness EDD) · ADR-0011 (falla cerrada)
- **Dependencias:** #536 (T23.3) cerrada/mergeada.

### Qué se hizo y por qué
- `backend/evals/agent_behavior/metrics/citation_support.py` (nuevo) y su alta en `metrics/__init__.py`. No reimplementa el criterio: reutiliza `check_citation_support` (T23.3), así el harness mide lo que la compuerta bloquea. Las citas se reconstruyen del caso: el `corpus` son los fragmentos, `assign_cite_ids` les da los alias `F#` del Redactor y `extract_citations` lee las del texto. Puntúa 0-100 como porcentaje de citas sin objeción; `passed` exige score >= `min_score` (100) y ninguna objeción de la compuerta. Falla cerrada: sin citas, marcador sin fragmento o solape bajo no pasan. Solo aplica a casos con `expect.citation_support`; el runner no se toca.
- Datasets `redactor-citation-support` (3 casos, pasa entero) y `redactor-citation-support-regressions` (5 casos, falla a propósito: fuera de tema, marcador inventado, fragmento sin texto, texto sin citas, una de dos sin respaldo). Nombres sin `-golden` (como `investigador-cobertura`, T22.9): no los recoge el gate y `thresholds.yaml` no cambia ni `enforce`.
- Modo `live`: cada caso fija `input.citation_map` (más `project_id`), que el Redactor ya acepta como `previous` en `assign_cite_ids`, para que sus alias coincidan con los que la métrica reconstruye. Un test comprueba que ese mapa es el que reconstruye la métrica.
- `backend/tests/test_edd_citation_support.py` (6 tests) y `backend/evals/agent_behavior/README.md` (métrica y datasets).

### Definition of Done
- [x] **AC8** — la métrica distingue golden (100, pasa) de regressions (los 5 casos fallan, scores 0 y 50) en `replay`; en `live` usa el proveedor de plataforma y el mismo texto de salida (ver límites).

### Verificación
- `python -m evals.agent_behavior.runner --dataset redactor-citation-support --mode replay` → pasa 3/3, `citation_support` 100.
- `... --dataset redactor-citation-support-regressions --mode replay` → falla 0/5 (código 1, a propósito).
- `python -m evals.agent_behavior.gate` → «Ninguna métrica por debajo de su umbral», código 0.
- `cd backend && DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q` → 1856 passed, 38 skipped, 1 failed (`test_no_tracked_databases.py::test_a_fresh_dev_database_is_created_and_migrated`, fallo conocido en Windows, WinError 32).

### Notas y límites
- **Procedencia `handwritten`**: las salidas están escritas a mano. Un verde dice que la métrica funciona, no que el modelo cite bien.
- **`live` no se ha ejecutado**: no hay Ollama ni Qdrant con el corpus indexado aquí. Solo se verificó que construye el proveedor de plataforma y que la métrica puntúa el texto que devuelva. En `live` el Redactor recupera de Qdrant: los fragmentos del `corpus` deben estar indexados en el proyecto `edd-citation-support`; si la recuperación devuelve otros, los marcadores no coincidirán y fallará con motivo.
- El solape es léxico y compara con el extracto de 280 caracteres: un solape bajo puede ser falso positivo (limitación heredada de T23.3). Un `[F1, F2]` se evalúa por separado contra cada fragmento.
- No toca frontend, rutas, `thresholds.yaml` ni `enforce`.
