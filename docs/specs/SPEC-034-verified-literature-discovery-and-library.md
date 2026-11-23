# SPEC-034: Descubrimiento de literatura verificado y biblioteca de investigación

- **Estado:** Ready
- **Autor:** Equipo de plataforma (borrador asistido)
- **Fecha:** 2026-11-22
- **Épica:** E22 (GitHub Project)
- **ADR relacionado:** [SPEC-024](SPEC-024-egress-control-agent-tools.md) (egress) · [SPEC-032](SPEC-032-publication-gate-framework.md) (V09; decisión a/b/c de la matriz)
- **Severidad:** 🔴

> **Origen.** Análisis del 2026-11-22 y Framework v0.1 §10 (el Investigador
> busca en bases bibliográficas y registra la búsqueda) · plan SPEC-032 Fase 4
> (4.1, 4.5, 4.7, V07). Pasa a `Ready` por instrucción del equipo;
> `/speckit-clarify` y `/speckit-checklist` pendientes (no bloqueantes).

## 1. Problema

- El Investigador **solo consulta el RAG local** (`adapters/investigador.py`): no
  descubre literatura. Su perfil (`investigador.agent.md`) afirma consultar
  EuropePMC y OpenAlex y el código no lo hace.
- Las fuentes salen con `doi`, `year`, `journal` y `url` vacíos salvo que el autor
  los aporte a mano; con V09 estricta «casi ninguna fuente subida pasaría».
- Sin resultados RAG el agente **no se abstiene**: sintetiza desde conocimiento
  paramétrico (matriz 0.4, 4.7).
- `RAG_SCORE_THRESHOLD` existe y ningún llamador lo pasa (hallazgo N7); en la
  instancia de desarrollo una fuente figura con similitud 0,00.
- La pantalla **Documentos** muestra nombre y nº de fragmentos, sin DOI, año,
  revista, estado ni verificación.
- Existe una búsqueda arXiv/Wikipedia en `capabilities/tools.py`
  (`ddg_search_with_urls`) que el Investigador no invoca y que no cubre OpenAlex,
  Crossref, Semantic Scholar ni PubMed.
- **Hallazgo de T22.10 (2026-11-22):** el descubrimiento y la verificación
  (`run_literature_search`, `verification.add_candidate_to_library`) existen como
  librería y solo los ejecutan los tests: **ningún endpoint, nodo ni pantalla los
  invoca**. El panel de candidatos queda vacío porque nada crea filas
  `curation_status=candidate`, así que AC1 y AC3 no se pueden ejercer de punta a punta.
  Además, el flag `LITERATURE_DISCOVERY_ENABLED` del apartado 7 no existe en el código.
- **Hallazgo de la prueba manual de T22.5 (2026-11-23):** cuando el Investigador se
  abstiene, el motor detiene el flujo como pide AC7, pero la ejecución se presenta como
  **completada**: el paso se registra `completed` (`use_cases.py`, `log_run_end(..., "completed")`),
  se emite `done` y la pantalla de ejecución muestra «Pipeline completado», la insignia verde
  COMPLETADO y el botón «Ver artículo» activo, con los otros cuatro agentes en «PENDIENTE». El
  motivo real solo se ve en el log de eventos. La abstención es correcta; su **estado** no lo es:
  nada distingue «terminó» de «se detuvo por falta de fuentes verificadas».

## 2. Objetivos / No-objetivos

- **Objetivos:** (a) **descubrimiento** de candidatos en OpenAlex, Crossref,
  Semantic Scholar, arXiv y PubMed, **solo por `egress.safe_get`**; (b) cada
  candidato se **resuelve por DOI y se verifica** antes de ofrecerse; (c) el autor
  **cura** los candidatos y los incorpora a la **biblioteca** con metadatos
  bibliográficos; (d) el Redactor cita **solo** lo que está en la biblioteca
  verificada; (e) **registro de búsqueda** reproducible (bases, fechas, cadenas);
  (f) abstención si la evidencia es insuficiente.
- **No-objetivos:** raspado de páginas web; PDFs de pago o saltarse paywalls;
  revisiones sistemáticas completas con cribado (V08, Fase 4 de SPEC-032);
  fichas de afirmación (SPEC-040); una **excepción para «documento interno»**
  (descartada por [ADR-0011](../adr/0011-publication-gate-fail-closed.md)).

## Clarifications

### Session 2026-11-22

- Q: ¿Se admite una excepción para «documento interno» (sin DOI) como fuente
  citable? → A: No. Sin excepción (opción A): un documento sin DOI verificado se
  puede subir y consultar como contexto, pero no entra en `sources` ni en
  Referencias hasta que se resuelva o el autor aporte el DOI. Se mantiene
  ADR-0011.
- Q: ¿Qué se hace con un candidato aceptado sin texto completo? → A: Descarga
  automática solo si es acceso abierto (opción C): el PDF se baja desde la URL de
  acceso abierto que informa la base, por `safe_get`; si no hay URL o falla, se
  acepta como «solo resumen» y el autor puede subir el PDF después.
- Q: ¿Qué es la «fecha de corte» de los candidatos? → A: La fecha de la búsqueda
  (opción A). Solo se descartan candidatos con fecha de publicación posterior a
  ella (metadatos erróneos o preprints mal fechados); no hay corte configurable.
- Q: ¿Cuándo se abstiene el Investigador y quién fija N? → A: Configurable por
  proyecto (opción B): `research.min_sources` en `template.yaml`, por defecto 3,
  validado al cargar; no lo puede reducir el autor por artículo.
- Q: ¿Qué bases se consultan por defecto y quién las elige? → A: Por defecto
  OpenAlex y Crossref; el resto se activa por proyecto (opción B) en
  `research.sources` de `template.yaml`, validado al cargar. Semantic Scholar solo
  si hay clave configurada (variable de entorno); arXiv y PubMed según disciplina.

## 3. Criterios de aceptación (Given/When/Then)

- [ ] **AC1** — *Given* una consulta del autor *When* corre el descubrimiento
  *Then* se consultan las bases de `research.sources` (por defecto OpenAlex y
  Crossref; Semantic Scholar solo con clave de API en el entorno; arXiv y PubMed
  si el proyecto las activa; una base desconocida falla al cargar la plantilla)
  solo por `safe_get` con
  `quien="literature_discovery"`; con `EGRESS_ALLOWED_DOMAINS` definida, sus hosts
  se añaden **solo para esta capacidad** (como ya hace la compuerta).
- [ ] **AC2** — *Given* candidatos devueltos *When* se verifican *Then* se
  descartan los que no resuelven por DOI/ID, los duplicados (mismo DOI) y los que
  tienen fecha de publicación posterior a la **fecha de la búsqueda**; los no
  verificados **no** se ofrecen. La fecha de la búsqueda queda en el registro (AC6).
- [ ] **AC3** — *Given* candidatos verificados *When* el autor los revisa *Then*
  puede aceptar, descartar o marcar «imprescindible», y los aceptados se añaden a
  la biblioteca con `doi`, `year`, `journal`, `authors` y `source_db`.
- [ ] **AC4** — *Given* un PDF subido a mano *When* se indexa *Then* el sistema
  intenta resolver su DOI por título/autores (opción a de la matriz); si no se
  resuelve queda «sin verificar», visible y editable (el autor puede aportar el DOI,
  con registro de quién y cuándo) y **no puede figurar en Referencias** hasta
  entonces.
- [ ] **AC5** — *Given* un artículo en ejecución *When* el Investigador produce
  fuentes *Then* `sources` solo incluye documentos de la biblioteca **con DOI
  verificado** (resuelto por el sistema o aportado por el autor); un documento «sin
  verificar» puede consultarse como contexto pero no entra en `sources` ni en
  Referencias, y **no existe excepción para «documento interno»** (ADR-0011); el
  Redactor no añade fuentes propias fuera de `sources`.
- [ ] **AC6** — *Given* una búsqueda *When* termina *Then* se persiste un registro
  (bases, fecha, cadena, filtros, nº de resultados) exportable y visible en la
  traza.
- [ ] **AC7** — *Given* evidencia insuficiente, es decir **menos de N fuentes
  verificadas por encima del umbral de similitud** *When* corre el Investigador
  *Then* se abstiene, lo declara en la traza y al autor, y no sintetiza desde
  conocimiento paramétrico. `N` es `research.min_sources` en `template.yaml` (por
  defecto **3**), se valida al cargar la plantilla (entero ≥ 1) y no lo puede bajar
  el autor desde el artículo.
- [ ] **AC8** — *Given* `RAG_SCORE_THRESHOLD` *When* se recupera *Then* el umbral
  se aplica de verdad (hay test que falla si un llamador lo omite).
- [ ] **AC9** — *Given* la pantalla Documentos *When* se abre *Then* muestra DOI,
  año, revista, estado de verificación y permite editar metadatos e importar
  BibTeX o una lista de DOI.
- [ ] **AC10** — *Given* un fallo o límite de una API externa *When* se consulta
  *Then* falla cerrada con reintentos y mensaje claro; nunca se acepta un
  candidato sin verificar.
- [ ] **AC11** — *Given* un candidato aceptado *When* la base informa una URL de
  acceso abierto *Then* el PDF se descarga por `safe_get`
  (`quien="literature_discovery"`), se indexa y el documento queda con
  `text_status=full_text`; *When* no hay URL de acceso abierto o la descarga falla
  *Then* se acepta con `text_status=abstract_only`, con etiqueta visible «solo
  resumen», y el autor puede subir el PDF después (pasa a `full_text`). Nunca se
  descargan PDFs de pago ni se eluden paywalls.
- [ ] **AC12** — *Given* la persona autora en la pantalla Documentos del proyecto activo
  *When* lanza una búsqueda con su consulta *Then* se ejecuta `run_literature_search`
  sobre las bases de `research.sources` del proyecto (por defecto OpenAlex y Crossref),
  se escribe su registro (AC6) y **cada candidato verificado cuyo DOI aún no está en la
  biblioteca del proyecto** se guarda con `curation_status=candidate` y sus `doi`, `year`,
  `journal`, `authors`, `source_db` y la URL de acceso abierto si la hay; aparece en el
  panel «Candidatos». *And* un candidato no verificado nunca se guarda; un DOI ya presente
  en la biblioteca (aceptado, candidato o descartado) no se vuelve a crear ni a ofrecer; y la
  respuesta indica cuántos candidatos nuevos hubo y el estado de cada base (una base caída
  o limitada no oculta a las demás). *And* con `LITERATURE_DISCOVERY_ENABLED` apagado el
  endpoint responde «descubrimiento desactivado», no hace ninguna petición de red y el
  panel sigue funcionando con lo ya importado.
- [ ] **AC13** — *Given* una ejecución en la que el Investigador se abstiene (AC7) *When*
  el flujo se detiene *Then* la ejecución **no** se registra ni se muestra como completada:
  queda con un estado propio de «detenida por abstención» distinto de `completed`, `failed`
  y `cancelled`, visible en la lista de ejecuciones y en la traza. *And* la pantalla de
  ejecución muestra, en lugar de «Pipeline completado», un aviso destacado «El Investigador
  se abstuvo» con las fuentes verificadas frente al mínimo (`k/N`) y el mensaje de qué
  hacer, y no ofrece «Ver artículo» como si hubiera contenido. *And* los agentes que no
  llegaron a ejecutarse se muestran como «No ejecutado» y no como «PENDIENTE» indefinido.
  *And* el artículo permanece en borrador y ningún agente posterior se ejecuta. *And* una
  ejecución que sí completa el flujo sigue mostrándose como completada, sin cambios.

## 4. Diseño propuesto

- **Capacidad nueva** `literature` en `platform/capabilities/registry.py`, con
  clientes por base (`platform/capabilities/literature/`), todos sobre
  `safe_get`; reutiliza el resolver de `publication_gate/reference_resolver.py`
  para no duplicar la verificación.
- **Datos:** metadatos por documento en el payload de Qdrant y en tabla propia
  (`library_documents`, con `text_status`: `full_text` | `abstract_only`) vía
  Alembic; registro de búsqueda en `search_logs`. SPEC-035 debe tratar `abstract_only`
  como soporte débil: solo puede comprobar una cita contra el resumen.
- **Investigador:** perfil actualizado para reflejar lo que realmente hace;
  `template.yaml` declara `requires: [rag_results, llm, literature]`.
- **Frontend:** panel «Candidatos» (aceptar/descartar/imprescindible) y columnas
  nuevas en `DocumentsPage.jsx`.
- **Cableado del descubrimiento (AC12, T22.11).** Lo dispara la **persona autora**, no el
  Investigador: un endpoint `POST /agents/rag/library/search` (con `require_redactor` y
  `get_project_context`, como el resto de la biblioteca) llama a `run_literature_search` con
  las bases de `research.sources` del proyecto y persiste los verificados nuevos como
  candidatos con `verification.add_candidate_to_library`. El panel gana un formulario de
  búsqueda (consulta y bases activas) y muestra el resultado por base. Se mantiene así que
  la consulta es del autor (AC1) y que el Investigador no inventa cadenas de búsqueda: sigue
  usando solo la biblioteca verificada (T22.5). El flag `LITERATURE_DISCOVERY_ENABLED`
  (apartado 7) se implementa en esta tarea, apagado por defecto, y se declara en
  `.env.example`; la búsqueda se limita con el limitador de peticiones existente. Queda fuera
  de esta spec que el Investigador lance búsquedas por su cuenta durante la ejecución.
- **Estado de la abstención (AC13, T22.12).** El orquestador ya conoce la abstención
  (`res["abstained"]`, evento SSE `abstained`); falta que la **ejecución** la refleje. La
  tarea añade un estado terminal propio para la ejecución y su paso (nombre a fijar al
  implementar, p. ej. `abstained`) y hace que el evento final lo lleve (`done` con un
  `outcome` distinto, o un evento de cierre específico) en lugar de un `done` indistinguible.
  El frontend (`ExecutionPage.jsx`) usa ese dato para la insignia, el aviso destacado y los
  pasos «No ejecutado». **Comprobar antes de implementar** si el estado de `agent_runs` y
  `agent_run_steps` es un enum nativo (hay una migración `native_enum_labels`): de serlo,
  el valor nuevo va por una migración Alembic, nunca con SQL a mano; y si el estado forma
  parte del canon de la cadena de integridad, ver la regla de `CANON_VERSION` en
  `data-retention.md`.
  **Resuelto en T22.12:** el estado es `abstained` (`explainability.STATUS_ABSTAINED`); es un
  `String(16)`, no un enum nativo (sin migración), y `status` ya estaba en el canon, así que un
  valor nuevo no cambia el formato ni sube `CANON_VERSION`. El cierre es `done` con
  `outcome: "abstained"`. La traza de explicabilidad ya registra la abstención
  (`explainability.py`) y no cambia.
- **Seguridad:** claves de API solo por variable de entorno; User-Agent genérico
  de la plataforma (sin datos del usuario) y cabecera de contacto configurable.

## 5. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Cobertura desigual por disciplina | Alto | Fuentes configurables por proyecto; PubMed/arXiv según área |
| Límites de tasa y caídas de las APIs | Medio | Reintentos con espera exponencial, caché de positivos (patrón de la compuerta) |
| SSRF por URLs de candidatos | Alto | Todo por `safe_get`; test estructural contra `httpx.AsyncClient` fuera de la puerta |
| Fuga de la consulta del autor a terceros | Medio | Aviso en la UI; la consulta no incluye texto del manuscrito |
| Sesgo hacia artículos muy citados | Medio | Mostrar año/citas y permitir filtros; el autor decide |

## 6. Plan de pruebas

Unitarias por cliente con respuestas grabadas (sin red); test estructural de
egress; integración del flujo candidato→biblioteca; prueba de abstención; casos
EDD de cobertura sobre un conjunto de papers abiertos; manual con y sin
`EGRESS_ALLOWED_DOMAINS`.

## 7. Impacto operativo / observabilidad

Métricas: consultas, aciertos de verificación, tasa de abstención. Documentar la
retención del registro de búsqueda en `data-retention.md`. Flag
`LITERATURE_DISCOVERY_ENABLED` para desplegar sin riesgo y volver al RAG solo.

## 8. Backlog (sincronización SDD)

```yaml
# sdd-sync v1
epic:
  id: E22
  title: "Descubrimiento de literatura verificado y biblioteca de investigación"
  area: area/backend
tasks:
  - id: T22.1
    title: "Capacidad literature con clientes OpenAlex, Crossref, Semantic Scholar, arXiv y PubMed por safe_get"
    sev: high
    depends_on: []
    acceptance: [AC1, AC10]
  - id: T22.2
    title: "Verificación de candidatos (DOI, duplicados, fecha futura) reutilizando el resolver de la compuerta"
    sev: high
    depends_on: [T22.1]
    acceptance: [AC2]
  - id: T22.3
    title: "Migración y modelos: library_documents y search_logs con metadatos bibliográficos"
    sev: high
    depends_on: []
    acceptance: [AC3, AC6]
  - id: T22.4
    title: "Resolución de DOI de PDFs subidos y edición manual de metadatos"
    sev: high
    depends_on: [T22.2, T22.3]
    acceptance: [AC4]
  - id: T22.5
    title: "Investigador: solo biblioteca verificada, abstención y perfil alineado con el código"
    sev: high
    depends_on: [T22.3]
    acceptance: [AC5, AC7]
  - id: T22.6
    title: "Aplicar de verdad RAG_SCORE_THRESHOLD en todos los llamadores con test"
    sev: medium
    depends_on: []
    acceptance: [AC8]
  - id: T22.7
    title: "Registro de búsqueda reproducible en la traza y exportación"
    sev: medium
    depends_on: [T22.1, T22.3]
    acceptance: [AC6]
  - id: T22.8
    title: "Frontend: panel de candidatos y biblioteca con DOI, año, revista y estado, e importación BibTeX/DOI"
    sev: high
    depends_on: [T22.2, T22.3]
    acceptance: [AC3, AC9]
  - id: T22.9
    title: "Casos EDD de cobertura bibliográfica sobre papers de acceso abierto"
    sev: medium
    depends_on: [T22.5, T22.11]
    acceptance: [AC5, AC7]
  - id: T22.10
    title: "Descarga de PDF de acceso abierto por safe_get y estado «solo resumen» (text_status)"
    sev: medium
    depends_on: [T22.1, T22.3]
    acceptance: [AC11]
  - id: T22.11
    title: "Cablear la búsqueda: endpoint y formulario que crean candidatos verificados, y flag LITERATURE_DISCOVERY_ENABLED"
    sev: high
    depends_on: [T22.1, T22.2, T22.3, T22.7, T22.8]
    acceptance: [AC12]
  - id: T22.12
    title: "Mostrar la abstención como ejecución detenida, no completada: estado propio, aviso destacado y pasos no ejecutados"
    sev: high
    depends_on: [T22.5]
    acceptance: [AC7, AC13]
```
