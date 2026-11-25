# SPEC-036: Revisión científica por criterios, independiente y con regla de reversión

- **Estado:** Ready
- **Autor:** Equipo de plataforma (borrador asistido)
- **Fecha:** 2026-11-22
- **Épica:** E24 (GitHub Project)
- **ADR relacionado:** [SPEC-032](SPEC-032-publication-gate-framework.md) (T20.7 Revisor que no aprueba por defecto) · [SPEC-025](SPEC-025-model-benchmark-scientific-writing.md) (modelos por agente)
- **Severidad:** 🟠

> **Origen.** Análisis del 2026-11-22; PaperOrchestra (Google Research,
> arXiv 2604.05018: refinamiento que acepta un cambio solo si la puntuación sube
> y lo revierte si no) · Framework v0.1 §3 etapa 6 y §10 (JSON por criterio, V15)
> · plan SPEC-032 Fase 3. Pasa a `Ready` por instrucción del equipo;
> `/speckit-clarify` y `/speckit-checklist` pendientes (no bloqueantes).

## 1. Problema

- El Revisor emite **tres campos** (`approval_score`, `coherent`, `feedback[]`) sin
  desglose por criterio (`adapters/revisor.py`, matriz 0.2). SPEC-032 T20.7 corrige
  que apruebe por defecto, pero no el desglose.
- Con Ollama el Revisor usa `llama3.2:1b` por defecto; la propia nota de SPEC-025
  recuerda que `llama3.2:3b` falló el esquema JSON.
- Revisor y Redactor pueden ser **el mismo modelo**: los autores de PaperOrchestra
  reportan sesgo de autoevaluación de los LLM.
- Tras un cambio del Redactor, nada comprueba que el borrador **mejoró**: el bucle
  vuelve al Redactor y el siguiente texto sustituye al anterior aunque sea peor.
- V15 (conclusiones que no afirman más que los resultados; limitaciones en la
  Discusión) está **ausente** y el prompt del Redactor no pide limitaciones.
- Una instancia de desarrollo mostró un artículo avanzando con 65/100 y coherencia
  «No» por decisión humana de continuar; la decisión quedó registrada pero el
  Revisor no explicó por qué criterio falló.

## 2. Objetivos / No-objetivos

- **Objetivos:** (a) rúbrica **por ejes** con JSON validado y reintento; (b) el
  modelo del Revisor **distinto** del del Redactor, verificado al cargar la
  plantilla; (c) **regla de aceptación/reversión** entre vueltas; (d) criterio V15
  como advertencia con evidencia; (e) guía de **modelos recomendados** por agente;
  (f) evaluar el Revisor con EDD.
- **No-objetivos:** sustituir la revisión por pares humana; entrenar un modelo
  revisor propio; cambiar el umbral 80 ni el máximo de 3 vueltas (siguen siendo
  datos de `template.yaml`).

## 3. Criterios de aceptación (Given/When/Then)

- [ ] **AC1** — *Given* un borrador *When* corre el Revisor *Then* devuelve un JSON
  con `score` y estado por eje (rigor metodológico, soporte de afirmaciones,
  claridad, estructura, limitaciones) con **una cita textual** que justifica cada
  eje; la respuesta se valida con esquema.
- [ ] **AC2** — *Given* una respuesta no válida *When* se reintenta una vez *Then*
  si sigue sin cumplir el esquema el resultado es `not_verified` y **no aprueba**
  (falla cerrada, coherente con T20.7).
- [ ] **AC3** — *Given* una plantilla de proyecto *When* se carga *Then* falla si el
  modelo resuelto del Revisor coincide con el del Redactor, salvo `allow_same_model`
  explícito que queda registrado en la traza.
- [ ] **AC4** — *Given* una vuelta *n* y una vuelta *n+1* *When* termina la
  revisión *Then* el texto nuevo solo sustituye al anterior si el score global
  **sube**, o empata sin perder en ningún eje; si no, se **conserva la versión
  previa** y se registra por qué.
- [ ] **AC5** — *Given* conclusiones que afirman más que los resultados o una
  Discusión sin limitaciones *When* revisa *Then* emite V15 como advertencia con la
  frase concreta y el Redactor recibe ese comentario en la siguiente vuelta.
- [ ] **AC6** — *Given* el Redactor *When* genera la Discusión *Then* su prompt exige
  una subsección de limitaciones y amenazas a la validez.
- [ ] **AC7** — *Given* los perfiles de agentes *When* se documenta la guía de
  modelos *Then* indica un mínimo recomendado por agente y avisa en la UI de
  Agentes cuando un modelo está por debajo (p. ej. parámetros muy pequeños en
  Revisor o Redactor).
- [ ] **AC8** — *Given* el harness EDD *When* se añaden casos *Then* hay golden
  (borrador sólido aprobado) y regressions (borrador con defecto conocido
  rechazado) por eje, y el informe declara su `provenance`.
- [ ] **AC9** — *Given* un borrador cuyo score queda por debajo del umbral y una
  pausa de decisión humana (`await_decision`) *When* **nadie la responde** (no hay
  oyente SSE o vence el tiempo de espera) *Then* el valor por defecto **no es
  «continuar»**: el bucle vuelve al Redactor mientras queden vueltas, y agotadas pasa
  a `requires_human_review` (SPEC-032/AC7). *And* solo una decisión **explícita de una
  persona** salta la revisión, y la traza distingue «decidió una persona» de «sin
  respuesta», con quién y cuándo. *And* hay un caso de prueba de una ejecución sin
  oyente con score < umbral que no llega al Formateador.
- [ ] **AC10** — *Given* el borrador del Redactor *When* su salida **se trunca** (la
  generación corta por límite de tokens o de ventana, sin cierre del texto) *Then* el
  adapter lo **detecta** (motivo de parada del proveedor y, de no haberlo, ausencia de
  secciones obligatorias o frase final sin cerrar), lo registra en la traza y no lo
  entrega como borrador completo: reintenta con más presupuesto de salida o devuelve el
  paso como fallido con motivo, nunca avanza en silencio. *And* el límite de salida del
  Redactor deja de estar fijo en el código y se resuelve con la misma cascada que el
  modelo (ajustes de la ejecución → `.agent.md` → defecto), validado al cargar y
  acotado por la ventana del modelo. *And* hay un caso de prueba con una respuesta
  cortada a mitad de frase que no pasa al Revisor.

## 4. Diseño propuesto

- **Revisor:** esquema Pydantic de salida por criterio y un único reintento; la
  traza (T9.1) guarda la rúbrica completa por vuelta.
- **Motor:** `platform/engine/routing.py` (`make_review_router`) aplica la regla de
  reversión; el estado guarda `best_draft` y su score.
- **Decisión por omisión y truncado (AC9, AC10):** la decisión por defecto de
  `await_decision` pasa de «continuar» a «sin respuesta» y `make_review_router` solo
  salta la revisión ante una decisión explícita; el Redactor lee el motivo de parada
  del proveedor (`done_reason` en Ollama) y resuelve `num_ctx`/`num_predict` por la
  cascada de `resolve_agent_model`. Observado en una prueba de punta a punta con
  `qwen3.5:9b` (2026-11-25): borrador cortado a mitad de frase, sin Discusión, score
  72 y `coherent: false` que aun así llegó al Formateador y al Publicador.
- **Plantilla:** `review_loops[].require_distinct_model` (por defecto `true` en
  proyectos de paper); validación en `platform/projects/`.
- **Frontend:** `AgentsPage.jsx` muestra el aviso de modelo; el historial muestra la
  rúbrica por vuelta.

## 5. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Rúbrica demasiado estricta bloquea todo | Medio | Umbrales por eje como datos; arrancar en modo `warning` |
| Dos modelos distintos suben el coste | Medio | Permitir un modelo barato pero no el mismo; medir con SPEC-025 |
| Regla de reversión estanca el borrador | Medio | Tope de vueltas existente; mostrar el motivo al autor |
| El score sigue siendo juicio de un modelo | Alto | Se presenta como ayuda, no como garantía; la aprobación humana permanece |

## 6. Plan de pruebas

Unitarias de esquema/reintento y de la regla de reversión; test de carga de
plantilla con modelos iguales; paridad `adapters`/`capabilities` (hay test);
datasets EDD por eje en `live`; manual: vuelta que empeora y se revierte.

## 7. Impacto operativo / observabilidad

La traza crece (rúbrica por vuelta): revisar retención. Métricas: reversiones por
artículo, ejes más fallados. Flag `REVIEW_RUBRIC_ENABLED` para desplegar por
etapas; el modo anterior sigue disponible durante la transición.

## 8. Backlog (sincronización SDD)

```yaml
# sdd-sync v1
epic:
  id: E24
  title: "Revisión científica por criterios y regla de reversión"
  area: area/backend
tasks:
  - id: T24.1
    title: "Revisor con rúbrica por ejes, JSON validado, cita justificativa y reintento con falla cerrada"
    sev: high
    depends_on: []
    acceptance: [AC1, AC2]
  - id: T24.2
    title: "Validación al cargar: modelo del Revisor distinto del Redactor con excepción registrada"
    sev: medium
    depends_on: []
    acceptance: [AC3]
  - id: T24.3
    title: "Regla de aceptación y reversión entre vueltas en el motor"
    sev: high
    depends_on: [T24.1]
    acceptance: [AC4]
  - id: T24.4
    title: "Criterio V15 y subsección de limitaciones en el prompt del Redactor"
    sev: medium
    depends_on: [T24.1]
    acceptance: [AC5, AC6]
  - id: T24.5
    title: "Guía de modelos recomendados y aviso en la pantalla de Agentes"
    sev: low
    depends_on: []
    acceptance: [AC7]
  - id: T24.6
    title: "Mostrar la rúbrica por vuelta en el historial de generación"
    sev: medium
    depends_on: [T24.1]
    acceptance: [AC1]
  - id: T24.7
    title: "Datasets EDD del Revisor por eje con provenance declarada"
    sev: medium
    depends_on: [T24.1]
    acceptance: [AC8]
  - id: T24.8
    title: "Decisión humana por omisión: sin respuesta no es «continuar»; el bucle vuelve al Redactor y distingue persona de omisión en la traza"
    sev: high
    depends_on: [T24.3]
    acceptance: [AC9]
  - id: T24.9
    title: "Redactor: detectar salida truncada, no entregarla como borrador y resolver el límite de salida por la cascada de ajustes"
    sev: high
    depends_on: []
    acceptance: [AC10]
```
