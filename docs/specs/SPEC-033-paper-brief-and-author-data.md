# SPEC-033: Brief del paper y datos del autor (ficha de estudio y log de resultados)

- **Estado:** Ready
- **Autor:** Equipo de plataforma (borrador asistido)
- **Fecha:** 2026-11-22
- **Épica:** E21 (GitHub Project)
- **ADR relacionado:** se apoya en [SPEC-032](SPEC-032-publication-gate-framework.md) (compuerta; criterios V01/V02) y [SPEC-030](SPEC-030-reference-input-and-run-control.md) (modal de ejecución)
- **Severidad:** 🔴

> **Origen.** Análisis «AlejandrIA Magazine como asistente para paper científico»
> (2026-11-22) y Framework v0.1 §9 (V01, V02, V05, V06). Pasa a `Ready` por
> instrucción del equipo; `/speckit-clarify` y `/speckit-checklist` quedan
> pendientes (recomendados por la DoR, no bloqueantes).

## 1. Problema

El pipeline redacta a partir de **texto de documentos subidos**, no de los datos
del estudio. Evidencia:

- `AgentState` (`modules/agents/domain/entities.py`) solo lleva `title`,
  `keywords`, `context_description` y `article_outline`: no hay tipo de estudio,
  pregunta, hipótesis, guía de reporte ni datos.
- El modal de primera ejecución pide título, descripción y fuentes (README,
  «Ejecutar el pipeline»). No hay dónde aportar resultados.
- Un artículo publicado de la instancia de desarrollo afirma «ganancias en
  pass@1 superiores al 10 %» sin que exista ningún dato del autor que lo
  respalde: el Redactor produce cifras desde el conocimiento del modelo.
- V01 (ficha con tipo de estudio y guía) y V02 (ítem de guía → ubicación en el
  texto) figuran **ausentes** en `docs/reports/matriz-implementacion.md`.

Un paper sin datos reales del autor no es verificable: la compuerta puede
comprobar que una cita existe, pero no que una cifra sea cierta.

## 2. Objetivos / No-objetivos

- **Objetivos:** (a) **ficha del estudio** obligatoria por artículo (pregunta,
  hipótesis, tipo de estudio, guía de reporte, congreso/revista objetivo);
  (b) **log de resultados** estructurado que el autor aporta (tablas, métricas,
  enlaces a código/datos); (c) el Redactor **solo usa cifras con origen** en ese
  log; (d) la compuerta detecta **números sin origen** y los ítems de la guía sin
  cubrir.
- **No-objetivos:** validar que los resultados del autor sean *correctos*;
  análisis estadístico automático; protocolo sellado y preregistro (V05/V06, Fase
  4 de SPEC-032); figuras generadas (ver SPEC-039).

## 3. Criterios de aceptación (Given/When/Then)

- [ ] **AC1** — *Given* un artículo nuevo *When* se abre el modal de ejecución
  *Then* exige la ficha (tipo de estudio, guía de reporte y pregunta) y no permite
  lanzar sin ella; la ficha se persiste con el artículo.
- [ ] **AC2** — *Given* un catálogo de guías de reporte como **dato del proyecto**
  (`template.yaml`) *When* el autor elige un tipo de estudio *Then* se le ofrecen
  solo las guías aplicables y sus ítems quedan asociados al artículo.
- [ ] **AC3** — *Given* un autor que sube un log de resultados (CSV/JSON/Markdown
  con tablas) *When* se guarda *Then* cada tabla y métrica recibe un identificador
  estable y un hash de contenido, y se muestra en el detalle del artículo.
- [ ] **AC4** — *Given* un artículo con log de resultados *When* corre el Redactor
  *Then* su contexto incluye el log y su prompt le prohíbe afirmar cifras que no
  figuren en él (cada cifra de Resultados cita su identificador).
- [ ] **AC5** — *Given* un texto final con una cifra de Resultados sin
  identificador de origen o que no coincide con el log *When* se evalúa la
  compuerta *Then* el criterio «cifra sin origen» queda `blocking` y el informe
  lista cada cifra.
- [ ] **AC6** — *Given* un artículo sin log de resultados *When* el tipo de estudio
  exige resultados empíricos *Then* la sección Resultados se genera como
  «pendiente de datos del autor» y la compuerta lo marca; el sistema no inventa
  valores.
- [ ] **AC7** — *Given* una guía de reporte asociada *When* termina la redacción
  *Then* el informe indica, por ítem aplicable, si hay ubicación en el texto
  (cubierto / sin cubrir / no aplica) como advertencia en esta spec (V02 bloqueante
  queda para la Fase 3 de SPEC-032).
- [ ] **AC8** — *Given* las métricas del harness EDD *When* se añaden los datasets
  de este cambio *Then* hay casos `golden` (cifra con origen) y `regressions`
  (cifra inventada) que el gate distingue.

## 4. Diseño propuesto

- **Modelo:** campos `study_brief` (JSON) y `results_log` (referencia a tabla
  propia `article_results_items`: id, tipo, contenido, hash) mediante migración
  Alembic; **nunca** `ALTER TABLE` a mano.
- **Contrato:** `AgentState.study_brief` y `AgentState.results_items`; el
  Redactor los recibe como bloque aparte, **no** mezclado con `research_data`.
- **API:** `PUT /articles/{id}/brief`, `POST /articles/{id}/results`; ambos con
  `get_project_context` y límites de tamaño/tipo (reutilizar `platform/uploads.py`).
- **Compuerta:** nuevo criterio determinista en `platform/publication_gate/`
  (extracción de números de Resultados y cotejo con `results_items`).
- **Frontend:** paso «Brief» en el modal y panel «Datos del estudio» en
  `ArticleDetailPage`.
- **Catálogo de guías:** `gate.reporting_guides` en `template.yaml`, validado al
  cargar como el resto de la plantilla.

## 5. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Extraer cifras de prosa da falsos positivos (años, referencias) | Alto | Contexto limitado a la sección Resultados; listas de exclusión; `warning` hasta medir falsos positivos |
| El autor percibe el brief como fricción | Medio | Campos mínimos obligatorios, el resto opcional; plantillas por tipo de estudio |
| Datos sensibles del estudio enviados a un LLM externo | Alto | Aviso por proveedor activo; opción de proveedor local; ver SPEC-037 (privacidad) |
| Subida de ficheros maliciosos | Medio | Reutilizar validación de `uploads.py`; tamaño máximo; sin ejecución de contenido |

## 6. Plan de pruebas

Unitarias del extractor de cifras y de la validación de `reporting_guides`;
integración API con aislamiento de proyecto; prueba de migración
(`tests/test_migrations.py` compara con `create_all`); casos EDD golden/regressions
(AC8); manual: flujo del modal con y sin log.

## 7. Impacto operativo / observabilidad

Migración aditiva y reversible. Métrica: porcentaje de artículos con brief y con
log. Retención: documentar la nueva tabla en `docs/governance/data-retention.md`
(hay un test que lo comprueba). Rollback: ocultar el paso tras un flag
`PAPER_BRIEF_ENABLED`.

## 8. Backlog (sincronización SDD)

```yaml
# sdd-sync v1
epic:
  id: E21
  title: "Brief del paper y datos del autor"
  area: area/backend
tasks:
  - id: T21.1
    title: "Migración y modelos: study_brief y article_results_items (con hash) y retención documentada"
    sev: high
    depends_on: []
    acceptance: [AC1, AC3]
  - id: T21.2
    title: "Catálogo de guías de reporte en template.yaml con validación al cargar"
    sev: medium
    depends_on: []
    acceptance: [AC2]
  - id: T21.3
    title: "API del brief y del log de resultados con límites y aislamiento de proyecto"
    sev: high
    depends_on: [T21.1]
    acceptance: [AC1, AC3]
  - id: T21.4
    title: "Frontend: paso Brief en el modal de ejecución y panel Datos del estudio"
    sev: high
    depends_on: [T21.3]
    acceptance: [AC1, AC3]
  - id: T21.5
    title: "AgentState y Redactor: contexto de resultados y prohibición de cifras sin origen"
    sev: high
    depends_on: [T21.3]
    acceptance: [AC4, AC6]
  - id: T21.6
    title: "Criterio de compuerta «cifra sin origen» y cobertura de ítems de la guía"
    sev: high
    depends_on: [T21.5]
    acceptance: [AC5, AC7]
  - id: T21.7
    title: "Datasets EDD golden y regressions para cifras con y sin origen"
    sev: medium
    depends_on: [T21.5]
    acceptance: [AC8]
```
