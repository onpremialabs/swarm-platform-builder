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
  fichas de afirmación (SPEC-040).

## 3. Criterios de aceptación (Given/When/Then)

- [ ] **AC1** — *Given* una consulta del autor *When* corre el descubrimiento
  *Then* se consultan las fuentes configuradas solo por `safe_get` con
  `quien="literature_discovery"`; con `EGRESS_ALLOWED_DOMAINS` definida, sus hosts
  se añaden **solo para esta capacidad** (como ya hace la compuerta).
- [ ] **AC2** — *Given* candidatos devueltos *When* se verifican *Then* se
  descartan los que no resuelven por DOI/ID, los duplicados (mismo DOI) y los
  posteriores a la fecha de corte; los no verificados **no** se ofrecen.
- [ ] **AC3** — *Given* candidatos verificados *When* el autor los revisa *Then*
  puede aceptar, descartar o marcar «imprescindible», y los aceptados se añaden a
  la biblioteca con `doi`, `year`, `journal`, `authors` y `source_db`.
- [ ] **AC4** — *Given* un PDF subido a mano *When* se indexa *Then* el sistema
  intenta resolver su DOI por título/autores (opción a de la matriz); si no se
  resuelve queda «sin verificar», visible y editable (el autor puede aportar el DOI).
- [ ] **AC5** — *Given* un artículo en ejecución *When* el Investigador produce
  fuentes *Then* solo incluye documentos de la biblioteca verificada o marcados
  como «documento interno» con excepción registrada; el Redactor no añade fuentes
  propias fuera de `sources`.
- [ ] **AC6** — *Given* una búsqueda *When* termina *Then* se persiste un registro
  (bases, fecha, cadena, filtros, nº de resultados) exportable y visible en la
  traza.
- [ ] **AC7** — *Given* evidencia insuficiente (menos de N fuentes sobre el umbral
  de similitud) *When* corre el Investigador *Then* se abstiene, lo declara y no
  sintetiza desde conocimiento paramétrico.
- [ ] **AC8** — *Given* `RAG_SCORE_THRESHOLD` *When* se recupera *Then* el umbral
  se aplica de verdad (hay test que falla si un llamador lo omite).
- [ ] **AC9** — *Given* la pantalla Documentos *When* se abre *Then* muestra DOI,
  año, revista, estado de verificación y permite editar metadatos e importar
  BibTeX o una lista de DOI.
- [ ] **AC10** — *Given* un fallo o límite de una API externa *When* se consulta
  *Then* falla cerrada con reintentos y mensaje claro; nunca se acepta un
  candidato sin verificar.

## 4. Diseño propuesto

- **Capacidad nueva** `literature` en `platform/capabilities/registry.py`, con
  clientes por base (`platform/capabilities/literature/`), todos sobre
  `safe_get`; reutiliza el resolver de `publication_gate/reference_resolver.py`
  para no duplicar la verificación.
- **Datos:** metadatos por documento en el payload de Qdrant y en tabla propia
  (`library_documents`) vía Alembic; registro de búsqueda en `search_logs`.
- **Investigador:** perfil actualizado para reflejar lo que realmente hace;
  `template.yaml` declara `requires: [rag_results, llm, literature]`.
- **Frontend:** panel «Candidatos» (aceptar/descartar/imprescindible) y columnas
  nuevas en `DocumentsPage.jsx`.
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
    title: "Verificación de candidatos (DOI, duplicados, fecha de corte) reutilizando el resolver de la compuerta"
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
    depends_on: [T22.5]
    acceptance: [AC5, AC7]
```
