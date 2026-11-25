# SPEC-035: Soporte de cada cita y comprobación de retractaciones

- **Estado:** Ready
- **Autor:** Equipo de plataforma (borrador asistido)
- **Fecha:** 2026-11-22
- **Épica:** E23 (GitHub Project)
- **ADR relacionado:** [SPEC-032](SPEC-032-publication-gate-framework.md) / [ADR-0011](../adr/0011-publication-gate-fail-closed.md) · [SPEC-029](SPEC-029-traceability-view-and-integrity.md)
- **Severidad:** 🔴

> **Origen.** Análisis del 2026-11-22 y Framework v0.1 §9 (V10, V11). Pasa a
> `Ready` por instrucción del equipo; `/speckit-clarify` y `/speckit-checklist`
> pendientes (no bloqueantes).

## 1. Problema

La compuerta comprueba que una referencia **existe**; no que **sustente la frase**
que acompaña. Evidencia:

- La pestaña **Fuentes** del historial de generación advierte textualmente:
  «Recuperación RAG registrada; no demuestra que el artículo final cite estas
  fuentes. No se guardó el texto completo de los fragmentos».
- El Revisor puntúa en bloque; no ve pasajes ni citas (V10 **ausente**).
- No hay fuente de retractaciones (V11 **ausente**).
- El Redactor añade su propia consulta RAG que no pasa por `sources`, así que
  puede usar fragmentos sin que figuren en Referencias (matriz 0.6).
- **Hallazgo de la implementación de T23.1 a T23.7 (2026-11-23):** las piezas existen
  pero **nada las conecta**. `save_citation_map` y `to_citation_inputs`
  (`platform/citations.py`) no tienen ningún llamador fuera de ese módulo, así que el mapa
  de AC1 no se guarda en ninguna ejecución. Consecuencias: el criterio `citation_support`
  (T23.3) no puede declararse en `projects/alejandria-magazine/template.yaml` sin bloquear
  toda publicación por `no_citations`; la pestaña Fuentes (T23.6) muestra siempre el estado
  vacío; y el juez (T23.4) no tendría fragmentos que juzgar fuera de los tests. Además, el
  enlace «documento/página» de la pestaña apunta a `/dashboard/documents?doc=…&page=…` y
  `DocumentsPage` no lee esos parámetros, así que no coloca al usuario en el documento.

## 2. Objetivos / No-objetivos

- **Objetivos:** (a) vincular **cada cita del texto** a un fragmento concreto
  (documento, página, extracto) de la biblioteca; (b) comprobar el **soporte** con
  un solape determinista y un **juez de modelo distinto** del redactor; (c) marcar
  «cita sin soporte» y mostrarlo en la UI; (d) detectar **fuentes retractadas**;
  (e) medirlo con EDD.
- **No-objetivos:** garantizar que la interpretación del autor sea correcta;
  sustituir la lectura humana de la muestra que exige el framework; análisis de
  figuras o tablas dentro de los PDFs.

## 3. Criterios de aceptación (Given/When/Then)

- [ ] **AC1** — *Given* un borrador con citas *When* termina el Redactor *Then* se
  guarda un mapa `cita → {doc_id, página, extracto, hash}` por cada afirmación
  citada, versionado con el texto evaluado.
- [ ] **AC2** — *Given* una cita sin fragmento asociado *When* se evalúa *Then* el
  criterio de soporte la marca `not_verified` y bloquea, en línea con la política
  de falla cerrada de ADR-0011.
- [ ] **AC3** — *Given* una afirmación y su fragmento *When* corre el juez
  independiente *Then* emite `supported | partial | unsupported` con una
  justificación breve, y el modelo del juez es distinto del de redacción
  (verificado por configuración).
- [ ] **AC4** — *Given* el solape de texto entre afirmación y fragmento por debajo
  de un umbral configurable *When* se evalúa *Then* se marca revisión humana sin
  esperar al juez.
- [ ] **AC5** — *Given* una referencia con DOI *When* se consulta Crossref *Then*
  se detecta si está **retractada o con expresión de preocupación** y la compuerta
  bloquea o avisa según severidad configurada.
- [ ] **AC6** — *Given* un artículo con citas evaluadas *When* se abre la pestaña
  Fuentes *Then* muestra por cita su estado, el extracto y un enlace al
  documento/página, y permite al autor **confirmar manualmente** una cita
  (registrando quién y cuándo).
- [ ] **AC7** — *Given* el informe de compuerta *When* se genera *Then* incluye el
  recuento de citas por estado y una **muestra** para verificación humana (tamaño
  configurable).
- [ ] **AC8** — *Given* el harness EDD *When* se añaden los datasets *Then* una
  métrica `citation_support` distingue casos golden y regressions y se ejecuta en
  modo `live` además de `replay`.
- [ ] **AC9** — *Given* una ejecución completa de AlejandrIA en la que el Redactor produce
  un borrador con citas *When* termina el flujo y el texto final está fijado *Then* el mapa
  cita→fragmento se guarda con `save_citation_map` **versionado con la huella del texto
  final** (el que evalúa la compuerta, no el de salida del Redactor si el Formateador lo
  modifica), de modo que `current_citation_map` lo devuelve para el artículo; *And* el
  criterio `citation_support` está declarado en `template.yaml` y la compuerta lo evalúa
  con ese mapa, **en modo aviso** (no bloquea) hasta medir falsos positivos, con
  `CITATION_SUPPORT_ENFORCE` como interruptor documentado en `.env.example`; *And* la
  pestaña Fuentes muestra esas citas con su estado y permite confirmarlas, y el enlace a
  documento/página **coloca** al usuario en el documento indicado; *And* una ejecución cuyo
  texto no tiene citas o cuyo mapa no se pudo guardar queda `not_verified` (falla cerrada)
  y lo dice, no se omite en silencio; *And* una ejecución sin `gate.citation_support`
  declarado se comporta como antes.
- [ ] **AC10** — *Given* un borrador con afirmaciones sustantivas y fragmentos citables
  con marcador `[F#]` *When* termina el Redactor *Then* el texto **cita con el marcador
  `[F#]`** y no con otro formato: una cita autor-año inventada («(Título, 2024)», con el
  título de la obra como autor o un año que no es el de la ficha) **no es una cita válida** y
  se trata como cita sin fragmento. *And* si el borrador no contiene ninguna cita `[F#]`
  habiendo fragmentos citables, el adapter lo **detecta**, reintenta una vez con un
  recordatorio explícito del formato y, si persiste, lo registra en la traza como
  `no_citations` y avisa al Revisor y al autor (no falla el paso: la compuerta
  `citation_support` sigue en modo aviso). *And* el prompt por defecto del Redactor
  (es/en) muestra un ejemplo del formato `[F#]` y prohíbe las citas autor-año. *And* se
  **diagnostica y documenta** por qué una ejecución completa con `qwen3.5:9b` produjo 0
  citas `[F#]` pese a tener fragmentos (marcadores ausentes del contexto del Redactor tras
  las sub-preguntas de SPEC-034/AC18, o el modelo los ignora) y se corrige si la causa es
  del contexto. *And* hay un caso de prueba con un borrador que cita «(HarnessDev, 2024)»
  y ningún `[F#]` que se marca como sin citas válidas.

## 4. Diseño propuesto

- **Redactor:** instruido para citar con identificador de fragmento; el
  formateador **no** cambia ese mapa. El Redactor deja de añadir fuentes propias
  fuera de `sources` (alineado con el contrato del framework §10).
- **Compuerta:** criterios `citation_support` y `retraction` en
  `platform/publication_gate/` (juez por la capacidad `llm`; Crossref por
  `safe_get` con `quien="publication_gate"`).
- **Datos:** `citation_links` (migración Alembic) y estado de confirmación manual.
- **Frontend:** vista de citas en la pestaña Fuentes de
  `ArticleTraceHistoryPage.jsx` y en el detalle del artículo.
- **Evaluación:** módulo `evals/agent_behavior/metrics/citation_support.py`
  registrado como el resto de métricas.
- **Cableado del mapa (AC9, T23.8).** El orquestador (o el nodo del Redactor, vía la
  capacidad correspondiente) llama a `to_citation_inputs` y `save_citation_map` con las
  citas que el Redactor ya extrae (`[F#]`). **Punto delicado:** la huella del texto cambia si
  el Formateador reescribe el texto, y el mapa es por huella; por eso el guardado debe
  hacerse (o repetirse, es idempotente por huella) sobre el **texto final** que lee la
  compuerta (`service.py`), y la tarea debe comprobar con un test que
  `current_citation_map` devuelve filas para el artículo tras una ejecución completa, con y
  sin Formateador que modifique el texto. La activación en `template.yaml` es en modo aviso
  (`CITATION_SUPPORT_ENFORCE`, apagado por defecto); pasar a bloqueo es una decisión
  posterior, con datos de falsos positivos. El juez (T23.4) opera sobre el mapa persistido,
  por lo que depende de esta tarea para ejercerse de punta a punta. El arreglo del enlace
  documento/página es mínimo: `DocumentsPage` lee `doc` y `page` de la URL y los usa para
  seleccionar y posicionar; no se rediseña la pantalla.

## 5. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| El juez de modelo se equivoca o es complaciente | Alto | Modelo distinto, temperatura 0, muestra humana obligatoria y métrica de acuerdo |
| Solo hay texto del PDF, sin página fiable | Medio | Guardar página en la indexación; degradar a «sección» si no se conoce |
| Coste de llamadas por cita | Medio | Evaluar solo afirmaciones citadas; caché por hash |
| Datasets `handwritten` dan falsa confianza | Medio | Declarar `provenance` y avisar en el informe (disciplina EDD) |
| Datos del manuscrito enviados a un juez externo | Medio | Respetar proveedor local; aviso de privacidad (SPEC-037) |

## 6. Plan de pruebas

Unitarias del mapa cita→fragmento y del solape; integración de la compuerta con un
juez simulado; prueba de retractación con respuesta grabada de Crossref; EDD
golden/regressions; manual: confirmar una cita desde la UI.

## 7. Impacto operativo / observabilidad

Métricas: citas por estado, tasa de «sin soporte», latencia del juez. Documentar
retención de `citation_links`. Flag `CITATION_SUPPORT_ENFORCE` con modo
`warning` inicial (como `edd-gate`) hasta medir falsos positivos.

## 8. Backlog (sincronización SDD)

```yaml
# sdd-sync v1
epic:
  id: E23
  title: "Soporte de cada cita y retractaciones"
  area: area/backend
tasks:
  - id: T23.1
    title: "Redactor con citas por identificador de fragmento y sin fuentes fuera de sources"
    sev: high
    depends_on: []
    acceptance: [AC1]
  - id: T23.2
    title: "Migración y persistencia del mapa cita→fragmento versionado con el texto"
    sev: high
    depends_on: []
    acceptance: [AC1, AC6]
  - id: T23.3
    title: "Criterio de compuerta de soporte con solape determinista y falla cerrada"
    sev: high
    depends_on: [T23.1, T23.2]
    acceptance: [AC2, AC4]
  - id: T23.4
    title: "Juez independiente de soporte con modelo distinto al redactor y muestra humana"
    sev: high
    depends_on: [T23.3, T23.8]
    acceptance: [AC3, AC7]
  - id: T23.5
    title: "Comprobación de retractaciones y expresiones de preocupación vía Crossref"
    sev: medium
    depends_on: []
    acceptance: [AC5]
  - id: T23.6
    title: "Frontend: estado de cada cita, extracto y confirmación manual en la pestaña Fuentes"
    sev: medium
    depends_on: [T23.3]
    acceptance: [AC6]
  - id: T23.7
    title: "Métrica EDD citation_support con datasets golden y regressions en modo live"
    sev: medium
    depends_on: [T23.3]
    acceptance: [AC8]
  - id: T23.8
    title: "Cablear el mapa de citas: guardarlo tras el Redactor sobre el texto final, activar el criterio en modo aviso y enlazar documento/página"
    sev: high
    depends_on: [T23.1, T23.2, T23.3, T23.6]
    acceptance: [AC1, AC6, AC9]
  - id: T23.9
    title: "Redactor: exigir citas [F#] en el cuerpo, rechazar autor-año inventadas, reintentar y diagnosticar el contexto"
    sev: high
    depends_on: [T23.1, T23.8]
    acceptance: [AC10]
```
