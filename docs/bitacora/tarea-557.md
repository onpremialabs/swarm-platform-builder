# Tarea #557 — T25.8 — Etiqueta veraz en Flujos y test de la puerta única a published

## 2026-11-22 11:40 — Completada ✅

- **Rama:** `feat/557-etiqueta-flujos-puerta-unica`
- **PR:** (ver enlace en la PR; cierra #557)
- **Spec/ADR:** SPEC-037 (AC8, §1) · SPEC-032 / ADR-0011 (puerta única `can_publish`)
- **Dependencias:** ninguna

### Dónde estaba el problema
`frontend/src/platform/pages/FlowsPage.jsx` mostraba «Auto-publica» para cualquier flujo
con Publicador y «Revisión manual» para el resto. Desde SPEC-032 el Publicador nunca deja
un artículo en `published` (lo manda a `in_review` o `draft`), y publicar exige compuerta
determinista y aprobación humana: la etiqueta era falsa. «Revisión manual» tampoco era
veraz: un flujo sin Publicador no revisa nada, simplemente no publica.

### Qué se hizo y por qué
- `FlowsPage.jsx`: las dos etiquetas pasan a una constante `FLOW_LABELS` (en español,
  agrupadas para extraerlas con el i18n de SPEC-041; no se introduce i18n propia).
  Con Publicador: **«Pasa por compuerta y aprobación humana»** (clase `badge-pending`,
  «a la espera de una persona», en lugar de `badge-published`, que sugería ya publicado).
  Sin Publicador: **«No publica: queda en borrador»** (`badge-draft`). Solo tokens del
  sistema de diseño; `platform/` no importa de `projects/` (sigue usando
  `flowAutoPublishes` de `agentCatalog`).
- `backend/tests/test_published_single_gate.py` (nuevo), complementa a
  `test_can_publish.py` (tabla de verdad, endpoints, regex sobre `status = ArticleStatus.PUBLISHED`)
  sin duplicarlo:
  1. **Estructural por AST** sobre `backend/app/` (salvo `decision.py`): falla ante
     asignación directa, `setattr(..., "status", PUBLISHED)`, `status=PUBLISHED` en
     constructores/`.values()`/`dict(...)`, `{"status": PUBLISHED}` o SQL crudo
     `UPDATE ... SET status = 'published'`. Verificado por mutación: un `setattr` y un
     `dict(status=...)` añadidos a `routers/magazine.py` lo hicieron fallar.
  2. `assign_published` solo se llama desde tres sitios declarados (siembra de desarrollo,
     Publicador con proyecto sin `gate:`, `routers/articles.py`) y con la decisión
     prevista; en `articles.py` la decisión sale de `can_publish` (409 si no permitida) o
     `legacy_decision()`; solo `approve` y `publish` delegan en `_publish_through_the_gate`.
  3. Ningún DTO de escritura de artículos admite `status`.
  4. **Flujo guardado de extremo a extremo**: se guarda por la API un `SavedFlow`
     `[redactor, revisor, publicador]` («Flujo rápido de publicación»), se ejecuta con el
     orquestador real y LLM simulado. Tres casos: compuerta superada -> `in_review`, sin
     aprobación ni `published_at`, con informe; solo `approve` lo publica. Bloqueante IMRAD
     -> `draft`, y `approve` no publica. **Sin Investigador no hay fuentes -> `draft`**
     (reference_existence queda `not_verified`): el flujo rápido, tal cual, no puede
     superar la compuerta (para el caso feliz el test simula las fuentes que aportaría
     el Investigador).

### Hallazgos
- **No se encontró ningún bypass** hacia `published`. Los tres caminos históricos (Publicador,
  `approve`, `publish`) pasan por `assign_published`; la siembra de desarrollo exige
  `ENABLE_DEV_SEED`.
- Dos excepciones **deliberadas** y ahora fijadas por test: `legacy_decision()` (un proyecto
  que no declara `gate:` publica sin compuerta, tanto en el Publicador como en
  `approve`/`publish`) y `dev_seed_decision()`. AlejandrIA declara `gate:`, por lo que no
  le afectan; un proyecto nuevo sin `gate:` sí publicaría sin control (fuera de alcance).

### Definition of Done
- [x] **AC8** — La etiqueta de un flujo con Publicador es «Pasa por compuerta y aprobación
  humana» (no «Auto-publica») y hay tests que verifican que ni los flujos guardados ni
  ningún otro camino alcanzan `published` sin la puerta única.

### Verificación
- `cd backend && DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest tests/test_published_single_gate.py -q` -> 8 passed.
- Suite completa (`DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q`): 1555 passed, 38 skipped, 1 failed (el conocido `test_no_tracked_databases.py::test_a_fresh_dev_database_is_created_and_migrated`, WinError 32).
- `cd frontend && npm ci && npm run build` -> OK. `npm run build:public` -> OK.
- No se capturó pantalla (requiere backend, Qdrant y sesión en marcha).

### Notas
- `tests/test_no_tracked_databases.py::test_a_fresh_dev_database_is_created_and_migrated`
  falla en Windows (PermissionError WinError 32), sin relación con este cambio.
