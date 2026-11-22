# SPEC-037: Autoría, declaraciones y metadatos del manuscrito

- **Estado:** Ready
- **Autor:** Equipo de plataforma (borrador asistido)
- **Fecha:** 2026-11-22
- **Épica:** E25 (GitHub Project)
- **ADR relacionado:** [SPEC-032](SPEC-032-publication-gate-framework.md) / [ADR-0011](../adr/0011-publication-gate-fail-closed.md) · [SPEC-029](SPEC-029-traceability-view-and-integrity.md)
- **Severidad:** 🟠

> **Origen.** Análisis del 2026-11-22 y Framework v0.1 §9 (V12, V13, V14, V16) y
> §10 (el Formateador compone las declaraciones desde registros) · plan SPEC-032
> Fase 5 (5.1–5.4). Pasa a `Ready` por instrucción del equipo;
> `/speckit-clarify` y `/speckit-checklist` pendientes (no bloqueantes).

## 1. Problema

- **Metadatos inventados por el modelo.** Un artículo publicado en la instancia de
  desarrollo conserva «Autor: [Su Nombre/Autoría]» y «Fecha: Octubre 2023
  (Borrador)» cuando se creó el 15-sep-2026. La lista de marcadores de la compuerta
  (`gate.placeholders` en `template.yaml`) es de literales y no cubre ese patrón.
- **Declaración de uso de IA ausente (V12 parcial).** `agent_run_steps` guarda
  agente, modelo, parámetros y tokens por paso (SPEC-014/T9.1), pero no la
  *versión* del modelo, la sección afectada ni existe un párrafo generado para el
  manuscrito.
- **V13 parcial:** SPEC-032 (T20.6/T20.10) añade autor responsable y aprobación;
  falta comprobar que ningún agente figure como autor en el texto final.
- **V14 ausente:** no hay `credit`, `conflict` ni `funding` en el backend.
- **V16 parcial:** el Publicador fija `license: CC-BY-4.0` y `publisher` como
  constantes y no hay declaración de datos y código.
- **Etiqueta engañosa:** `FlowsPage.jsx` muestra «Auto-publica» para cualquier
  flujo que contenga un Publicador (`hasPublicador`). Tras SPEC-032 publicar exige
  compuerta y aprobación humana, así que la etiqueta describe algo que ya no es
  cierto y puede llevar a un equipo a creer que se publica sin control.
- **Artículos anteriores a SPEC-032** (p. ej. «Compuerta de publicación: Sin
  informe») siguen figurando como publicados sin haber pasado la compuerta.

## 2. Objetivos / No-objetivos

- **Objetivos:** (a) autor, filiación y fecha **los pone el sistema**, no el LLM;
  (b) **declaración de uso de IA** generada desde la traza; (c) declaraciones de
  contribuciones (CRediT), conflictos y financiamiento por persona; (d)
  declaración de datos y código y metadatos de publicación configurables; (e)
  política de **qué datos pueden ir a un proveedor externo**; (f) etiqueta de flujo
  veraz; (g) reevaluar lo publicado antes de la compuerta.
- **No-objetivos:** asignar DOI propios; certificar cumplimiento legal de una
  revista concreta; colaboración multiusuario completa (SPEC-038).

## 3. Criterios de aceptación (Given/When/Then)

- [ ] **AC1** — *Given* un artículo con autores registrados *When* se compone el
  manuscrito *Then* autor, filiación y fecha se inyectan desde la base y cualquier
  valor escrito por el LLM en esos campos se descarta.
- [ ] **AC2** — *Given* los marcadores configurados del proyecto *When* se evalúa la
  compuerta *Then* admite **expresiones regulares** además de literales, y un texto
  con «[Su Nombre/Autoría]» o una fecha fuera del rango de creación queda `blocking`.
- [ ] **AC3** — *Given* una ejecución con trazas *When* se compone el manuscrito
  *Then* se genera un párrafo con herramienta, **versión del modelo**, fechas,
  tarea y sección afectada por agente, y V12 bloquea si falta o no coincide con el
  registro.
- [ ] **AC4** — *Given* el texto final *When* se evalúa V13 *Then* bloquea si un
  agente o modelo figura como autor.
- [ ] **AC5** — *Given* un artículo con varias personas *When* cada una registra
  contribuciones (taxonomía CRediT), conflictos de interés y financiamiento *Then*
  el manuscrito incorpora las declaraciones compuestas y V14 bloquea si faltan.
- [ ] **AC6** — *Given* el Publicador *When* publica *Then* licencia, editor y
  declaración de datos/código salen de la configuración del proyecto y del artículo
  y no de constantes (V16 como advertencia).
- [ ] **AC7** — *Given* un proyecto *When* se define su política de datos *Then* el
  proveedor activo (local o externo) se muestra en el modal de ejecución y se
  exige confirmación explícita antes de enviar datos del brief a un proveedor externo.
- [ ] **AC8** — *Given* la página de Flujos *When* se lista un flujo con Publicador
  *Then* la etiqueta indica «Pasa por compuerta y aprobación humana» (no «Auto-publica»)
  y hay un test que verifica que ningún flujo guardado alcanza `published` sin la
  puerta única.
- [ ] **AC9** — *Given* artículos publicados sin informe de compuerta *When* un
  administrador ejecuta la reevaluación *Then* cada uno recibe informe y, si
  bloquea, queda marcado para revisión humana sin despublicarse automáticamente.

## 4. Diseño propuesto

- **Compuerta:** `platform/publication_gate/placeholders.py` pasa a aceptar
  patrones (`regex:`) con validación al cargar `template.yaml`.
- **Composición:** `adapters/publicador.py` y `formateador.py` componen las
  declaraciones desde registros; el Formateador no toca el cuerpo científico.
- **Datos:** `article_authors` con rol CRediT, conflictos y financiamiento
  (Alembic); `project.data_policy`.
- **Traza:** guardar versión del modelo en `agent_run_steps` si el proveedor la
  devuelve.
- **Frontend:** `FlowsPage.jsx` (etiqueta) y formulario de autoría en el detalle.
- **Reevaluación:** extender `scripts/gate_rollout_report.py` o un endpoint admin.

## 5. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Regex mal escritas bloquean publicaciones válidas | Medio | Validar al cargar; modo `warning` inicial; tests con textos reales |
| El proveedor no devuelve versión de modelo | Medio | Registrar el identificador configurado y marcar «versión no informada» |
| Declaraciones erróneas de conflicto o financiamiento | Alto | Las firma cada persona; el sistema no las infiere |
| Reevaluación masiva despublica por error | Alto | **No** despublica: solo marca para revisión humana |
| Etiqueta nueva confunde a usuarios | Bajo | Texto claro con enlace al informe de compuerta |

## 6. Plan de pruebas

Unitarias de patrones y composición; prueba de V12 contra un registro simulado;
integración de reevaluación en una base con artículos previos; test estructural de
la puerta única; manual: formulario de autoría y etiqueta de Flujos.

## 7. Impacto operativo / observabilidad

Migración aditiva. Documentar retención de las nuevas tablas en
`data-retention.md`. Reevaluación en lotes con informe (patrón de
`gate_rollout_report.py`). Flag por criterio para pasar de `warning` a `blocking`.

## 8. Backlog (sincronización SDD)

```yaml
# sdd-sync v1
epic:
  id: E25
  title: "Autoría, declaraciones y metadatos del manuscrito"
  area: area/backend
tasks:
  - id: T25.1
    title: "Autor, filiación y fecha inyectados por el sistema y descarte de lo escrito por el LLM"
    sev: high
    depends_on: []
    acceptance: [AC1]
  - id: T25.2
    title: "Marcadores de la compuerta con expresiones regulares y validación al cargar"
    sev: high
    depends_on: []
    acceptance: [AC2]
  - id: T25.3
    title: "Declaración de uso de IA desde la traza con versión de modelo y criterio V12"
    sev: high
    depends_on: []
    acceptance: [AC3]
  - id: T25.4
    title: "Criterio V13: ningún agente figura como autor"
    sev: medium
    depends_on: []
    acceptance: [AC4]
  - id: T25.5
    title: "Modelos y API de contribuciones CRediT, conflictos y financiamiento con criterio V14"
    sev: medium
    depends_on: []
    acceptance: [AC5]
  - id: T25.6
    title: "Metadatos del Publicador desde configuración y declaración de datos y código (V16)"
    sev: medium
    depends_on: []
    acceptance: [AC6]
  - id: T25.7
    title: "Política de datos por proyecto y confirmación al usar un proveedor externo"
    sev: medium
    depends_on: []
    acceptance: [AC7]
  - id: T25.8
    title: "Etiqueta veraz en Flujos y test de la puerta única a published"
    sev: low
    depends_on: []
    acceptance: [AC8]
  - id: T25.9
    title: "Reevaluación de artículos publicados sin informe de compuerta"
    sev: medium
    depends_on: []
    acceptance: [AC9]
```
