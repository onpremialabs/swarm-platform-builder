# Tarea #590 — T29.7 Extraer cadenas del builder (platform) al catálogo español

## 2026-11-23 14:40 — Completada

- **Rama:** `feat/590-extraer-cadenas-builder`
- **PR:** ver la PR abierta contra `develop` (`Closes #590`)
- **Spec/ADR:** SPEC-041 (E29; AC6 y AC11)
- **Dependencias:** #589 (T29.6, infraestructura i18n) y #596 (T29.13, controles de CI) mergeadas

### Dónde estaba el problema
Todos los textos de la capa `frontend/src/platform/` (el builder) estaban escritos en español dentro de los
`.jsx`: títulos, botones, `placeholder`, `title`, `aria-label`, `alt`, toasts, `confirm()`, mensajes de error y
formatos de fecha/número (`toLocaleDateString('es-ES')`, `toLocaleString('es-ES')`). Sin claves no hay nada que
traducir (AC6). `scripts/i18n_literals_baseline.json` registraba 635 literales en 31 ficheros, 275 de ellos en 16
ficheros de `platform/`.

### Qué se hizo y por qué
- **`frontend/src/platform/i18n/es.json`** (de `{}` a 640 mensajes) agrupado en espacios por pantalla/componente:
  `edge`, `node`, `states`, `modal`, `flows`, `auth`, `users`, `projects`, `agentsPage`, `documents`,
  `dashboard`, `configPage`, `flowDesigner`, `explain`, `library`, `agentEditor`. Textos **idénticos** a los de
  antes. Interpolación `{var}` en lugar de concatenar; plurales `_one/_other` donde había números.
- **Componentes migrados** (`useTranslation()`; en callbacks asíncronos, `translate()`, que lee el idioma en el
  momento de la llamada y no el del render que creó el callback): `components/ui/{Modal,states}.jsx`,
  `components/flow/{AgentNode,DeletableEdge}.jsx`, `components/explain/ExplainPanel.jsx`,
  `components/library/LibraryRecordsPanel.jsx`, `components/agents/AgentEditorModal.jsx`, y las páginas
  `AuthPage`, `AgentsPage`, `ConfigPage`, `DashboardPage`, `DocumentsPage`, `FlowDesignerPage`, `FlowsPage`,
  `ProjectSelectionPage`, `UsersPage`.
- **Datos con texto** (`SECTIONS` de ConfigPage, `ROLES`, `USE_CASES`, `PESTANAS`, menú del Dashboard...): ahora
  llevan `labelKey`/`descKey` (claves) y se traducen al pintar. El menú del Dashboard acepta de las entradas del
  proyecto tanto `labelKey` como el `label` ya resuelto de antes, para no romper el contrato con
  `setProjectNavItems` mientras T29.8 migra `projects/`.
- **Formatos con `Intl`** (`formatDate`/`formatNumber` de `useTranslation`): fechas de FlowsPage, UsersPage y
  notificaciones; números, duraciones y porcentajes de ExplainPanel. En `es` el resultado es el mismo salvo el
  espacio entre número y `%` (ahora U+00A0, el del propio `Intl`).
- **Frases con una palabra en negrita** («El <strong>Investigador</strong> la usa…»): nuevo `Trans` en
  `i18n/index.jsx` + parser puro `i18n/rich.js` (probado en `rich.test.mjs`). Se traduce la frase entera con
  marcas `<strong>/<em>/<code>` en vez de partirla en trozos con un orden de palabras fijo.
- **`en.json` provisional** (`frontend/src/platform/i18n/en.json`): copia de `es.json` con los mismos textos en
  español, **pendiente de traducir (T29.9)**. Motivo: `check_i18n.py` trata un `en.json` ausente como catálogo
  vacío y, con `es.json` relleno, la paridad falla por diseño. Es la opción menos invasiva (no se desactiva el
  control, no se toca el script) y no cambia el comportamiento: `translate()` ya caía al español y `main.jsx` no
  registra `en` todavía. Documentado en `frontend/src/platform/i18n/README.md`.
- **Línea base** (`python scripts/check_i18n.py --update`): 635 → 355 literales; **0 en `platform/`**, los 355
  restantes son de `projects/` (T29.8). De los 275 literales de `platform/`, 256 se extraen a claves y 19 pasan a excepciones (ver abajo).
- **Excepciones** (`scripts/i18n_literals_exceptions.json`, con motivo): `RAG` (sigla), `Alexandria` (alt del
  logotipo), `Alej` + `andrIA` (marca partida en dos nodos para colorearla), `rag_docs` (identificador
  técnico), `×` (símbolo), y 8 **falsos positivos del detector** (14 entradas en total) (ternarios y claves de objeto entre etiquetas,
  y el CSS de un `<style>`). Son globales por texto, así que también eximen esos mismos textos si aparecen en
  `projects/`.
- **Tests nuevos:** `backend/tests/test_platform_i18n_keys.py` (toda clave que pide `platform/` existe en
  `es.json`; las variables `{x}` del mensaje se pasan en la llamada y no sobran —87 llamadas revisadas—; plurales
  con `_other`; marcas `<x>` bien cerradas; la línea base no tiene `platform/`; el builder no importa de
  `projects/`) y `i18n/rich.test.mjs`.
- **Tests existentes ajustados:** `test_flow_designer_edges.py` (buscaba «Eliminar» en el código fuente; ahora lo
  busca en el catálogo) y `test_explain_panel.py` (el `%` de `Intl` lleva U+00A0). Los bancos de navegador
  `frontend/a11y/{harness,states,explain}.jsx` registran `es.json`, porque renderizan componentes reales y sin
  catálogo enseñarían las claves.

### Definition of Done
- [x] **AC6 (parte del builder)** — toda cadena visible de `platform/**/*.jsx` sale del catálogo; el selector de
  idioma y el catálogo inglés son T29.10/T29.9. Fechas, números y plurales usan `Intl`.
- [x] Claves bien escritas — `test_platform_i18n_keys.py` (existencia, variables, plurales).
- [x] AC11 / línea base — baja de 635 a 355 sin ampliarla; 0 literales en `platform/`.
- [x] CI verde con paridad activa — `en.json` provisional con las mismas claves/variables.

### Verificación
- `python scripts/check_i18n.py` → `[OK] paridad de catálogos; sin literales nuevos (deuda en línea base: 355)`.
- `cd frontend && npm run build` y `npm run build:public` → OK (tras `npm ci`).
- `node --test frontend/src/platform/i18n/{i18n,rich}.test.mjs` → OK (desde pytest).
- Navegador real (Playwright + Chromium headless; en Windows se necesita un shim de `npx.cmd` porque los tests
  llaman a `npx` sin extensión): `test_async_states.py`, `test_explain_panel.py`, `test_modal_a11y.py`,
  `test_flow_designer_edges.py` → 54 passed. Renderizan `Modal`, `states` y `ExplainPanel` con el catálogo real.
- Suite completa `cd backend && DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q` →
  **7 failed, 1890 passed, 38 skipped** (16 min 43 s). Los 7: `test_no_tracked_databases::test_a_fresh_dev_database_is_created_and_migrated`
  (WinError 32, fallo conocido en Windows) y 6 de lectura estructural de ficheros de `projects/alejandria-magazine`
  (`test_frontend_gate.py` x5 y `test_paper_design_back.py` x1). Esos 6 fallaron porque, **durante** la ejecución, los
  ficheros de `projects/` que leen ya contenían claves `t('detail.confirmReject')` (es decir, texto de T29.8, tarea que
  no está en esta rama: `git status` de `frontend/src/projects` está limpio); al volver a lanzarlos tras terminar
  la suite pasan (`test_frontend_gate.py` + `test_paper_design_back.py` → 13 passed). Lo más probable es que otro
  agente tocara por error esa ruta mientras corría la suite; no es un cambio de esta PR.

### Fuera de alcance / notas
- **Revisar a mano en el navegador** (no hay tests de componente; se comprobó el código, el build y los tres
  componentes de los bancos, no cada pantalla): Inicio de sesión/registro (`AuthPage`), selección de proyecto y
  modal «Nuevo proyecto», Dashboard (barra lateral, cabecera de proyecto, campana de notificaciones), Agentes
  (tarjetas, editor y modal «Nuevo agente»: pestañas Markdown/Parámetros/RAG), Flujos, Flow Designer (paleta,
  barra, panel de problemas, modal «Ejecutar pipeline» con opciones avanzadas), Documentos (subida, colecciones,
  panel de referencias bibliográficas con búsqueda, importación y edición), Configuración (todas las secciones y
  la de agentes), Usuarios (tabla y acceso a proyectos), panel «Por qué este resultado», estados cargando/vacío/
  error y modales (cierre con Esc).
- Cambios visibles mínimos y a propósito: plurales correctos con 1 («1 chunk», «1 colección», «1 candidato nuevo»,
  «1 detectado») donde antes se concatenaba un plural fijo o «(s)».
- **No se tocan** textos de módulos `.js` del builder (no son `.jsx`): `flowValidation.js` (mensajes de
  validación del lienzo), `store/*.js`, `api/errors.js` y los mensajes de error que llegan del backend. Siguen en
  español y no los detecta `check_i18n.py`; conviene una tarea de seguimiento. Tampoco `src/App.jsx` ni
  `index.html` (fuera de `platform/`), ni el contenido por defecto del Markdown de un agente nuevo
  (`Descripción.`), que es dato y no interfaz.
- El detector de `check_i18n.py` empareja comillas sin entender comentarios: un apóstrofo en un comentario puede
  hacer que parezca «sin usar» una clave que sí se usa (pasó dos veces en `FlowDesignerPage.jsx`; se reescribieron
  los comentarios). Tampoco ve una clave escrita dentro de una plantilla `` `${t('x')}` ``.
- Posible conflicto trivial con la PR de T29.8 en `scripts/i18n_literals_baseline.json` (y quizá en
  `i18n_literals_exceptions.json`): se regenera con `python scripts/check_i18n.py --update`.
- Seguimiento: T29.9 traduce `en.json`; T29.10 lo registra desde `main.jsx` y añade el selector.
