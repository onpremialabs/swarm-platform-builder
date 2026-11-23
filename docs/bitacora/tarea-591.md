# Tarea #591 — T29.8 Extraer cadenas de AlejandrIA Magazine (projects) al catálogo español

## 2026-11-23 14:30 — Completada

- **Rama:** `feat/591-extraer-cadenas-alejandria`
- **PR:** ver PR enlazada al issue #591 → `develop`
- **Spec/ADR:** SPEC-041 (E29; AC6, AC8, AC11)
- **Dependencias:** #589 (T29.6, infraestructura) y #596 (T29.13, controles de CI), ambas mergeadas

### Dónde estaba el problema
Todo el texto visible de `frontend/src/projects/alejandria-magazine/` estaba escrito en español dentro del JSX (358 literales detectados por `scripts/check_i18n.py`, deuda de la línea base). El catálogo `i18n/es.json` del proyecto estaba vacío, así que ninguna pantalla del proyecto podía cambiar de idioma.

### Qué se hizo y por qué
- **Catálogo** `projects/alejandria-magazine/i18n/es.json`: 614 claves anidadas por área (`citations`, `gate`, `stages`, `articles`, `magazine`, `lector`, `paperView`, `paperDesign`, `detail`, `execution`, `history`, `traceability`, `metrics`, `agents`, `nav`, `investigatorPanel`, `common`...). El texto español se conserva tal cual; interpolación `{var}` y plurales `_one`/`_other` donde hay números (p. ej. `articles.total`, `history.logsPage`, `metrics.loops`, `traceability.integrity.verifiedOf`).
- **Helpers** (solo en la capa del proyecto): `i18n/useT.js` (`useT()` = `useTranslation` ligado al espacio `alejandria-magazine`; `tr()` = traducción sin hook para callbacks/SSE/toasts que no deben depender del idioma) e `i18n/Rich.jsx` (frases con `<strong>/<em>/<code>` como UNA clave, sin `dangerouslySetInnerHTML`).
- **Componentes**: los 15 ficheros `.jsx` de la capa sustituyen literales por `t('clave')`: atributos visibles (`aria-label`, `title`, `placeholder`), toasts, mensajes de log SSE y confirmaciones incluidos. `catalog.jsx`: el panel del Investigador usa `Rich`, y `label`/`desc` de los agentes, el menú y el `RUN_TARGET` son getters que traducen al leerse (el builder sigue leyendo `meta.label` como cadena).
- **T22.12 y T23.6**: ExecutionPage/TraceabilityPage/ArticleTraceHistoryPage/ArticleCitations conservan texto y accesibilidad: `role="alert"` para la abstención, `role="status"` para el resto de avisos, `aria-label` de estado/confirmación/citas; estados «Detenida por abstención», «Se abstuvo», «No ejecutado» intactos. Los errores de ArticleCitations/ArticleTraceHistory se guardan como **clave** y se traducen al pintar (así no se refetch al cambiar de idioma).
- **Revista pública**: `public/main.jsx` (entry de `index.public.html`) no montaba el proveedor ni registraba mensajes; con el cambio la revista mostraría las claves en crudo. Cambio mínimo: `registerMessages('platform', ...)`, `registerMessages(NAMESPACE, MESSAGES)` y `<I18nProvider>`, igual que `main.jsx`.
- **en.json provisional**: `i18n/en.json` es una copia exacta de `es.json` (mismas claves y valores, en español) **pendiente de traducir en T29.9**. Motivo: sin `en.json` la paridad de T29.13 cuenta un catálogo vacío y falla por diseño; así el control sigue activo (no se desactivó ni se tocó `check_i18n.py`). `index.js` sigue exportando solo `{ es }`: el inglés no se registra hasta T29.9, así que este fichero solo lo lee el control de CI.
- **Control de literales**: `python scripts/check_i18n.py --update` redujo la línea base de **635 a 273** literales (31 → 17 ficheros; ninguno de `projects/`). Se añadieron excepciones con motivo en `scripts/i18n_literals_exceptions.json`: marca `Alej`/`andrIA`/`Magazine` (AlejandrIA partida en el JSX), `INFO`/`ERROR` (niveles de log), `agent_runs` (tabla), `![pie](asset:…)` (sintaxis Markdown) y 13 falsos positivos del detector (fragmentos de código JS entre `>` y `<`, p. ej. `, current:`, `) : error ? (`). Efecto lateral: `Alej`/`andrIA` también existen en `DashboardPage.jsx` y `ProjectSelectionPage.jsx` (platform), así que 4 literales de la línea base de platform quedan exentos por ser marca; T29.7 los verá ya fuera de su deuda.
- **Ajustes de código para que el control (que empareja comillas sin entender de regex ni de comentarios) no se confundiera**: `ArticleDetailPage.stripMarkdown` escribe el acento grave como `\x60` en sus regex (equivalente), y se quitó un apóstrofo y unos acentos graves de comentarios de `PaperDesignPage.jsx`; las llamadas `t()` no se anidan en plantillas de texto.
- **Test** `backend/tests/test_i18n_alejandria_keys.py` (corre en CI): toda clave `t('x')`/`tr('x')` existe en `es.json`; las plantillas `t(`a.${x}`)` tienen prefijo; las claves guardadas como dato (`label: 'citations.status.supported'`) existen; cada `{variable}` del mensaje se pasa en la llamada; los plurales traen `_other`; `en.json` provisional tiene las mismas claves; el entry público monta el proveedor. Comprobado por mutación: una clave mal escrita lo hace fallar.

### Definition of Done
- [x] AC6 (parte de projects) — toda cadena visible de la capa `alejandria-magazine` sale del catálogo `alejandria-magazine`; al cambiar de idioma (selector: T29.10, inglés: T29.9) cambiará sin recargar porque los componentes usan `useTranslation`. Fechas y números: ver notas.
- [x] Sin cambio visual: texto español exacto (salvo el plural correcto «1 artículo»/«1 registro», antes «1 artículos»/«1 registros»).
- [x] CI verde con catálogo relleno: paridad vía `en.json` provisional; línea base bajada con `--update`, nunca ampliada.
- [x] Revista pública verificada: `npm run build:public` OK y su entry registra mensajes y proveedor.

### Verificación
- `python scripts/check_i18n.py` -> OK (paridad; 273 de deuda restante, toda en `platform/`, de T29.7).
- `pytest tests/test_i18n_alejandria_keys.py tests/test_i18n_checks.py` -> 23 pasan (9 + 14).
- `node --test frontend/src/platform/i18n/i18n.test.mjs` -> pasa; humo con `core.js` + `es.json` real: plurales e interpolación correctos.
- `npm run build` y `npm run build:public` -> OK (node_modules del repo principal enlazado por junction en el worktree; no entra en el commit).
- Suite completa de backend (`DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q`, una sola vez): **7 failed, 1890 passed, 38 skipped** (16 min 43 s). Los 7: `test_no_tracked_databases::test_a_fresh_dev_database_is_created_and_migrated` (WinError 32, fallo conocido) y 6 tests estructurales que buscaban texto literal en el JSX y ahora lo tienen en el catálogo (`test_frontend_gate.py` x5, `test_paper_design_back.py` x1). Se adaptaron para leer el catálogo (`_con_textos`) y la regex de «Volver» sigue `aria-label={t('common.back')}`; tras el cambio `pytest tests/test_frontend_gate.py tests/test_paper_design_back.py` -> 13 pasan. No se repitió la suite completa (el único fallo restante esperado es el conocido de WinError 32).

### Pantallas tocadas (revisar a mano en el navegador, en español)
1. **Artículos** (`/dashboard/articles`): pestañas, buscador, tarjetas (editar/eliminar/guardar), estados vacíos, toasts, confirmación de borrado.
2. **Detalle de artículo** (`/dashboard/articles/:id`): estados y banners, panel Compuerta, Autor responsable, Revisión humana, metadatos del paper, modales «Reejecutar pipeline» y «Rechazar», línea de etapas, toasts.
3. **Citas del artículo** (pestaña Fuentes de la traza): estados, confirmar manualmente, `role="alert"`/`status`.
4. **Ejecución** (`/dashboard/execution/:id`): cabecera, tarjetas de paso («Se abstuvo», «No ejecutado»), aviso de abstención (`role="alert"`), coherencia insuficiente, log, vista previa.
5. **Trazabilidad en vivo** (`TraceabilityPage`, con `flowSequence`): pestañas, métricas, integridad, vista previa.
6. **Historial de trazas** (`/dashboard/articles/:id/observability`): resumen, trazas por agente, logs, métricas, fuentes/búsquedas, integridad, exportar JSONL.
7. **Métricas del proyecto** (`MetricsDashboardPage`, «Trazabilidad del proyecto»): tiles, estado del enjambre, anomalías, tabla de ejecuciones.
8. **Diseño del paper** (`/articles/:id/design`) y **Vista de maquetación** (`/articles/:id/paper`).
9. **Revista** (`MagazinePage`, también en la build pública `index.public.html`) y **Lector** (`LectorPage`).
10. **Editor de agentes -> Investigador** (panel «Pipeline del Investigador», `catalog.jsx`), menú del dashboard («Artículos», «Trazabilidad») y etiqueta «artículo» del botón Ejecutar del Flow Designer.

### Fuera de alcance / notas
- **No extraído** (no es `.jsx` ni lo detecta el control): `gate.js` (etiquetas de criterios, `describeApiError`, textos de siguiente paso), `store/articleStore.js`, `api/articles.js`, y formatos de fecha/número con `es-ES`/`es-CL` en los componentes (`toLocaleString`, `fmtSeg`...). Pasarlos a `Intl` según el idioma activo queda para T29.9/T29.10; `GateReportPanel` sigue mostrando en español lo que sale de `gate.js`.
- Los textos que llegan del backend (mensajes de error, nombres de criterio, `rationale`) no se traducen aquí.
- La clave `investigatorPanel.rag` conserva la errata original «coleción» para no cambiar el texto; corregirla en T29.9.
- Frases con énfasis dentro de `<li>` usan `Rich`; las que mezclan componentes (`<strong>` + texto) en otros sitios se parten en dos claves (`*Before`/`*After`) para no pasar JSX por el catálogo.
- **Conflicto previsto con la PR de T29.7** en `scripts/i18n_literals_baseline.json` (ambas lo regeneran): al mergear la segunda, resolver con `python scripts/check_i18n.py --update` sobre el resultado fusionado. También `scripts/i18n_literals_exceptions.json` si T29.7 añade excepciones.
- No se tocó `frontend/src/platform/`, ni el tema, ni `check_i18n.py`.
