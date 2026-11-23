# Tarea #593 — T29.10 Selector de idioma accesible, detección inicial, lang del documento y formatos con Intl

## 2026-11-23 15:30 — Completada ✅

- **Rama:** `feat/593-selector-idioma`
- **PR:** ver el PR de la rama (`Closes #593`) → `develop`
- **Spec/ADR:** `docs/specs/SPEC-041-ui-theme-and-language.md` (E29; AC1, AC6, AC12)
- **Dependencias:** #589 (T29.6, infraestructura i18n) mergeada

### Dónde estaba el problema
- `frontend/src/platform/i18n/core.js` ya detectaba (guardado -> navegador -> es) y cambiaba
  el idioma en caliente, pero **no había ningún control** para hacerlo, y los dos puntos de
  entrada (`main.jsx`, `projects/alejandria-magazine/public/main.jsx`) solo registraban `es`:
  `en` no se cargaba nunca.
- El lienzo del Flow Designer **copia** `label`/`desc` del catálogo del proyecto (getters que
  traducen al leerse) a la paleta y a los nodos al crearlos; al cambiar de idioma esas copias
  quedaban en el idioma anterior. El test de navegador lo reprodujo.
- `MagazinePage` tenía un fallo latente: el JSX de `<article>` se evalúa aunque `AsyncState`
  muestre el estado vacío, y con la lista vacía `article.scientific_format` lanzaba
  (`undefined`) y la revista pública se quedaba en blanco.
- Varias fechas se formateaban con `toLocaleDateString('es-ES')` en vez de `Intl` con el
  idioma activo (AC6).

### Qué se hizo y por qué
- `frontend/src/platform/components/ui/LanguageSelector.jsx` (nuevo): grupo de botones nativos
  `role="group"` con `aria-label` = «Idioma» (en el idioma activo), `aria-pressed` en el activo,
  `lang` propio en cada opción y una región `role="status" aria-live="polite"` (`sr-only`) que
  anuncia «Idioma cambiado a X» ya compuesta con el catálogo del idioma elegido. Botones nativos:
  Tab/Shift+Tab/Enter/Espacio sin código extra; el foco visible lo da el `:focus-visible` global.
- `frontend/src/index.css`: `.lang-switch` / `.lang-switch-btn`, solo con tokens (`--border-default`,
  `--bg-hover`, `--text-*`, `--brand-primary`, `--radius-md`); el activo se marca con peso y
  subrayado, no solo con color.
- Ubicación: barra superior del dashboard (`DashboardPage.jsx`, junto a notificaciones y usuario) y
  cabecera de la revista pública (`MagazinePage.jsx`, que monta `index.public.html`).
- `main.jsx` y `public/main.jsx`: registran también `en` (`platformEn`); `alejandria-magazine/i18n/index.js`
  exporta `{ es, en }`.
- Cadenas del selector (`language.label|es|en|changed`) en `platform/i18n/es.json` y `en.json`
  (paridad; sin literales nuevos en `.jsx`). `en.json` sigue siendo la **copia provisional en español**
  (T29.9 la traducirá, no se ha tocado): **al elegir inglés el texto sigue en español** salvo
  `<html lang>`, el formato de fechas/números y el propio selector. Los nombres «Español»/«English»
  son iguales en ambos catálogos a propósito (endónimos).
- `FlowDesignerPage.jsx`: `useTranslation()` expone `locale` y un efecto relee `label`/`desc` del
  catálogo en la paleta cuando cambia; el efecto existente propaga eso a los nodos del lienzo. El menú
  del proyecto y el botón Ejecutar ya se repintaban (leen el getter dentro de componentes con hook).
- Fechas con `formatDate` (Intl, idioma activo) en `MagazinePage`, `LectorPage`, `ArticlesPage`,
  `ArticleDetailPage` y `GateReportPanel`.
- `MagazinePage.jsx`: `{article && (...)}` para no romper con la lista vacía.
- Tests: `frontend/src/platform/i18n/i18n.test.mjs` (+4, node) y
  `backend/tests/test_language_selector.py` (estructural + navegador). Banco
  `frontend/a11y/language.{html,jsx}` (+ entrada en `a11y/vite.config.js`) que monta las pantallas reales
  con `en` marcado con prefijo «[en] » para ver qué se repinta.
- `frontend/src/platform/i18n/README.md` actualizado.

### Definition of Done
- [x] **AC1** — `detectLocale` (guardado -> navegador es/en -> `es`) ya existía; ahora tiene tests: node
  (`['en-US','es']`->en, `['fr-FR','de']`->es, `fr,en`->en, vacío->es, guardado inválido ignorado) y
  navegador real con `locale` del contexto en-US/es-CL/fr-FR/de-DE. *(La parte de tema del AC1 es de
  T29.1/T29.2 y no se toca aquí.)*
- [x] **AC6** — cambio sin recargar (test con marca `window.__sin_recarga`), `<html lang>` actualizado,
  preferencia en `localStorage` (`ui.locale`) con try/catch (test con almacenamiento que lanza o ausente) y
  persistente tras recargar; menú del proyecto, catálogo de agentes (paleta y nodos) y botón Ejecutar se
  repintan; fechas con `Intl`/idioma activo y números con `formatNumber` (test node `1.234.567,5` vs
  `1,234,567.5`). *Parcial hasta T29.9/seguimiento: ver la lista de abajo.*
- [x] **AC12** — operable con teclado (Tab, Enter, Espacio), nombre accesible en el idioma activo,
  anuncio por `role=status`/`aria-live=polite`, foco visible (outline sólido comprobado en navegador).

### Verificación
- `node --test frontend/src/platform/i18n/i18n.test.mjs` -> 9 pasan.
- `python -m pytest tests/test_language_selector.py -q` (backend/, con Chromium local y npx) -> 11 pasan.
- `python scripts/check_i18n.py` -> OK (paridad; deuda de línea base sin ampliar: 2).
- `npm run build` y `npm run build:public` -> OK.
- Suite completa de backend (`DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q`, una vez, 27 min) -> **1914 pasan, 38 omitidos, 1 falla**: `test_no_tracked_databases.py::test_a_fresh_dev_database_is_created_and_migrated` por `PermissionError: [WinError 32]` al borrar `dev.db` temporal en Windows (fallo conocido del entorno, ajeno a esta tarea).

### Fuera de alcance / notas — seguimiento
Texto visible que **sigue en español** al cambiar de idioma (módulos `.js` y formatos con configuración
regional fija; no migrados aquí):
- `platform/flowValidation.js` (mensajes de validación del lienzo), `platform/store/*` (authStore y otros:
  errores/mensajes), `platform/api/errors.js`, `App.jsx` (títulos de ruta y textos de guardas).
- `projects/alejandria-magazine/gate.js` (`CRITERION_LABELS`, `ACTION_LABELS`, «Reejecutar desde …») y
  `store/articleStore.js`.
- Formatos con `'es-ES'`/`'es-CL'` fijo o locale por defecto: `MetricsDashboardPage.jsx` (duración, número,
  fecha), `TraceabilityPage.jsx` (`toLocaleString('es-ES')`, `toLocaleTimeString()`),
  `ArticleTraceHistoryPage.jsx` (`num`), `ExecutionPage.jsx` (`toLocaleTimeString()`).
- `en.json` (platform y alejandria-magazine) es copia en español hasta T29.9.
- No se tocó el tema (T29.1/T29.2).

### Pantallas / flujos para revisar a mano
1. Dashboard: barra superior -> selector es/en con teclado (Tab, Enter/Espacio); foco visible; el lector de
   pantalla anuncia «Idioma cambiado a …»; recargar mantiene la elección.
2. Flow Designer: paleta, nodos del lienzo y botón «Ejecutar» tras cambiar de idioma (sin recargar).
3. Revista pública (`npm run build:public`, `/magazine`) con lista vacía (antes se rompía) y con artículos:
   fecha de publicación en el formato del idioma.
4. Listado de artículos, detalle de artículo (fechas) y panel del informe de la compuerta (fecha de evaluación).
5. Navegador con idioma en/fr/es y sin preferencia guardada: idioma inicial correcto; con
   `localStorage` bloqueado la interfaz sigue funcionando.
6. Con inglés elegido: comprobar que el texto sigue en español (esperado hasta T29.9) y que solo cambian
   `lang`, formatos y el selector.
