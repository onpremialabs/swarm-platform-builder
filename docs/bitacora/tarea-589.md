# Tarea #589 — T29.6 Infraestructura i18n con espacios de nombres, registro de mensajes por proyecto y respeto de capas

## 2026-11-23 — Completada

- **Rama:** `feat/589-infraestructura-i18n`
- **PR:** ver PR enlazada al issue #589 → `develop`
- **Spec/ADR:** SPEC-041 (AC6, AC8)
- **Dependencias:** ninguna

### Dónde estaba el problema
El frontend no tenía ninguna infraestructura de i18n: los textos están en español dentro del JSX y no existía un sitio donde el proyecto aportara los suyos sin que `platform/` importara de `projects/`.

### Qué se hizo y por qué
- `frontend/src/platform/i18n/core.js`: núcleo sin React ni dependencias. `registerMessages(namespace, {es,en})` (registro, mismo patrón que `setAgentCatalog`), claves `espacio:ruta.anidada`, interpolación `{var}`, plurales con `Intl.PluralRules` (`clave_one`/`clave_other`, variable `count`), `detectLocale` (guardado -> navegador -> es), `setLocale` (sin recarga, actualiza `<html lang>`, persiste en localStorage), fallback idioma activo -> español -> clave, `formatNumber`/`formatDate` con `Intl`.
- `frontend/src/platform/i18n/index.jsx`: `useTranslation(ns)` (con `useSyncExternalStore`, repinta al cambiar de idioma) e `I18nProvider`.
- `platform/i18n/es.json` y `projects/alejandria-magazine/i18n/{es.json,index.js}`: catálogos vacíos y punto de registro del proyecto; las cadenas se extraen en T29.7/T29.8.
- `frontend/src/main.jsx` (cambio mínimo, por coincidir con T29.1): imports, dos llamadas a `registerMessages` y envoltorio `<I18nProvider>`.
- Decisión: **sin dependencia npm** (la spec proponía i18next); `Intl` cubre plurales/formatos y no se toca `package.json` ni el lock.
- Tests: `frontend/src/platform/i18n/i18n.test.mjs` (`node --test`) y `backend/tests/test_frontend_i18n.py` (lo ejecuta en CI y comprueba que el builder no importa de `projects/` y que main.jsx registra el proyecto).

### Definition of Done
- [x] AC6 (infraestructura) — cambio de idioma en caliente, `<html lang>`, `Intl` para números/fechas/plurales. La extracción de cadenas y el selector quedan para T29.7-T29.10.
- [x] AC8 — el proyecto rellena el registro desde `main.jsx`; `test_frontend_layers.py` sigue en verde.

### Verificación
- `node --test frontend/src/platform/i18n/i18n.test.mjs` -> 5 pasan.
- `npm run build` y `npm run build:public` -> OK.
- `pytest tests/test_frontend_layers.py tests/test_frontend_i18n.py tests/test_design_tokens.py` -> 25 pasan.
- Suite completa de backend (`DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q`) -> 1 failed, 1873 passed, 38 skipped; el único fallo es `test_no_tracked_databases::test_a_fresh_dev_database_is_created_and_migrated` (WinError 32, conocido). Una primera pasada detectó que `test_async_states` (lint de errores tragados) rechazaba los `catch` de `core.js`; se anotaron con `mejor-esfuerzo`.

### Fuera de alcance / notas
- Sin extracción de cadenas, sin catálogo en inglés, sin selector, sin tema.
- `npm audit` informa 5 vulnerabilidades ya existentes; no se añadió ninguna dependencia.
- main.jsx puede entrar en conflicto trivial con T29.1 (#584).
