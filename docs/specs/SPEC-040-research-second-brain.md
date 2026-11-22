# SPEC-040: Second brain de investigación (fichas de afirmación y notas enlazadas)

- **Estado:** Ready
- **Autor:** Equipo de plataforma (borrador asistido)
- **Fecha:** 2026-11-22
- **Épica:** E28 (GitHub Project)
- **ADR relacionado:** complementa [SPEC-021](SPEC-021-agent-memory-context-budget.md) (memoria episódica de los agentes, Draft) · depende de [SPEC-034](SPEC-034-verified-literature-discovery-and-library.md) y [SPEC-035](SPEC-035-citation-support-and-retractions.md)
- **Severidad:** 🟡

> **Origen.** Análisis del 2026-11-22: ¿second brain en lugar de RAG? Conclusión:
> **capa curada sobre el RAG**, no sustituto. **Hipótesis sin medir:** que las
> fichas mejoren el soporte de citas es un razonamiento, no un resultado; por eso
> la spec incluye su evaluación (AC8). Pasa a `Ready` por instrucción del equipo;
> `/speckit-clarify` y `/speckit-checklist` pendientes (no bloqueantes).
> Distinción con SPEC-021: aquella es memoria **de los agentes** entre ejecuciones;
> esta es conocimiento **del equipo**, escrito o aprobado por personas.

## 1. Problema

- Todo el conocimiento del proyecto vive en la **Biblioteca vectorial**: PDFs
  troceados (302 fragmentos para un único paper en la instancia de desarrollo). El
  Investigador recupera 6 fragmentos y sintetiza con tope de 1024 tokens.
- El RAG recupera **fragmentos sueltos**: no sabe qué afirma cada paper ni cómo se
  relacionan entre sí; cada artículo parte de cero.
- Las decisiones del equipo (hipótesis descartadas, glosario, criterios de
  inclusión, notas de lectura) no tienen dónde vivir; se pierden entre papers.
- Para citar con rigor hace falta un **libro de pruebas**: afirmación, evidencia,
  cita textual, página y confianza, curado por una persona.

## 2. Objetivos / No-objetivos

- **Objetivos:** (a) **fichas de afirmación** por fuente (afirmación, evidencia,
  cita textual, página, confianza, estado de validación); (b) **notas** del
  equipo (decisiones, glosario, protocolo) con enlaces entre notas y a fuentes;
  (c) la IA **propone borradores de ficha** y la persona valida; (d) el
  Investigador/Redactor recuperan sobre **fuentes + fichas + notas** (RAG híbrido
  con re-ranking), citando siempre una ficha validada; (e) **exportación a
  Markdown** (compatible con Obsidian); (f) medir el efecto con EDD.
- **No-objetivos:** reemplazar el RAG; editor de notas colaborativo en tiempo real;
  grafo de conocimiento automático sin revisión; memoria conversacional (SPEC-021).

## 3. Criterios de aceptación (Given/When/Then)

- [ ] **AC1** — *Given* un documento de la biblioteca *When* el autor pide fichas
  *Then* el sistema genera **borradores** con afirmación, cita textual y página,
  marcados «sin validar» hasta que una persona los confirme o edite.
- [ ] **AC2** — *Given* una ficha *When* la edita o valida una persona *Then* se
  registra quién y cuándo, y solo las **validadas** pueden respaldar una cita
  en un manuscrito.
- [ ] **AC3** — *Given* notas del equipo *When* se crean *Then* admiten enlaces a
  otras notas, fichas y documentos, y se muestran los enlaces entrantes.
- [ ] **AC4** — *Given* fichas y notas *When* se indexan *Then* viven en el
  espacio del proyecto (`p_<project_id>__<bucket>`, derivado con
  `project_context.py`) y un perfil no puede leer las de otro proyecto.
- [ ] **AC5** — *Given* una consulta del Investigador *When* recupera *Then* mezcla
  fuentes, fichas y notas con re-ranking y devuelve para cada resultado su tipo,
  documento y página.
- [ ] **AC6** — *Given* una cita del Redactor *When* se compone el mapa cita→fragmento
  (SPEC-035) *Then* puede apuntar a una ficha validada además de a un fragmento.
- [ ] **AC7** — *Given* un proyecto *When* se exporta *Then* se descarga un `.zip`
  con una nota Markdown por ficha/nota, enlaces tipo wikilink y metadatos en
  cabecera; reimportarlo reconstruye el mismo contenido.
- [ ] **AC8** — *Given* un conjunto de papers de acceso abierto *When* se generan
  con y sin fichas *Then* el informe EDD compara `citation_support` (SPEC-035) y
  declara su `provenance`; la decisión de seguir invirtiendo se toma con ese dato.

## 4. Diseño propuesto

- **Capa 2 sobre la biblioteca (SPEC-034):** tablas `claim_cards` y `notes`
  (Alembic) con enlaces en `note_links`; colección Qdrant por proyecto para fichas
  y notas.
- **Generación de borradores:** capacidad `llm` con el modelo del agente, salida
  JSON validada, **nunca** publicada sin validación humana.
- **Recuperación híbrida:** reutilizar `capabilities/rag.py` añadiendo filtros por
  tipo; búsqueda léxica + semántica y re-ranking.
- **Presupuesto de contexto:** coordinar con SPEC-021 para no duplicar la
  compactación.
- **Frontend:** vistas «Fichas» y «Notas» dentro del proyecto, y revisión por
  lotes de borradores.

## 5. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Coste de curación humana | Alto | Borradores por IA y revisión por lotes; empezar solo con fuentes citadas |
| Fichas incorrectas que se asumen ciertas | Alto | Solo las validadas respaldan citas; estado y autoría visibles |
| Solape con SPEC-021 | Medio | Revisión conjunta de contratos antes de implementar; separar «agente» de «equipo» |
| Fuga entre proyectos | Alto | Colecciones derivadas por proyecto y test de aislamiento |
| El beneficio no se confirma | Medio | AC8 decide con datos si se continúa |

## 6. Plan de pruebas

Unitarias de enlaces y de la validación; test de aislamiento de proyecto;
ida y vuelta de la exportación Markdown; evaluación A/B (AC8); manual: validar un
lote de fichas y usarlas en un borrador.

## 7. Impacto operativo / observabilidad

Tablas nuevas: documentar retención en `data-retention.md`. Métricas: fichas
validadas, citas respaldadas por ficha, coste de generación de borradores. Flag
`SECOND_BRAIN_ENABLED`.

## 8. Backlog (sincronización SDD)

```yaml
# sdd-sync v1
epic:
  id: E28
  title: "Second brain de investigación"
  area: area/backend
tasks:
  - id: T28.1
    title: "Migración y modelos: claim_cards, notes y note_links con retención documentada"
    sev: medium
    depends_on: []
    acceptance: [AC2, AC3]
  - id: T28.2
    title: "Generación de borradores de ficha por documento con salida validada y estado sin validar"
    sev: medium
    depends_on: [T28.1]
    acceptance: [AC1, AC2]
  - id: T28.3
    title: "Indexación de fichas y notas por proyecto y recuperación híbrida con re-ranking"
    sev: medium
    depends_on: [T28.1]
    acceptance: [AC4, AC5]
  - id: T28.4
    title: "Integración con el mapa cita→fragmento: citas respaldadas por ficha validada"
    sev: medium
    depends_on: [T28.2, T28.3]
    acceptance: [AC6]
  - id: T28.5
    title: "Frontend: vistas de fichas y notas con revisión por lotes de borradores"
    sev: medium
    depends_on: [T28.1, T28.2]
    acceptance: [AC1, AC3]
  - id: T28.6
    title: "Exportación e importación Markdown compatible con Obsidian"
    sev: low
    depends_on: [T28.1]
    acceptance: [AC7]
  - id: T28.7
    title: "Evaluación A/B con y sin fichas sobre papers abiertos y decisión de continuidad"
    sev: medium
    depends_on: [T28.4]
    acceptance: [AC8]
```
