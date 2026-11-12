# Tarea #367 — T18.4: Evento SSE de progreso por unidades de trabajo reales

## 2026-11-05 — Completada ✅

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **Spec:** SPEC-030 · Épica E18 · AC5

### Qué se hizo y dónde

`backend/app/platform/progress.py` (nuevo) — `SectionTracker` y la detección de
sección. `use_cases.py` inyecta `_emit_progress` junto a `_log` y `_emit_token`.
El Redactor lo usa mientras transmite. `TraceabilityPage` lo pinta.

### El hallazgo: el Redactor no escribe por secciones

El diseño de la spec da por hecho que «el Redactor conoce sus secciones». Conocerlas
las conoce —están en su prompt—, pero **no itera sobre ellas**: genera el artículo
entero en una sola llamada con streaming de tokens. No hay cinco pasos que contar.

Lo que sí hay es un hecho observable: cuando en el flujo aparece el encabezado de
la cuarta sección, la cuarta ha empezado. Eso no se deriva de nada, se ve. Y es
exactamente el ejemplo que pone AC5 —«sección 2 de 5»—, sin violar su prohibición.

### Decisiones del detector

- **No retrocede.** El modelo puede abrir «## Discusión» y dentro escribir
  «## Introducción» al recapitular; quedarse con la última encontrada haría
  retroceder el contador, y una barra que va hacia atrás se lee como un fallo.
  Se conserva la más avanzada.
- **Normaliza el encabezado**: sin tildes, sin numeración, sin mayúsculas. El
  modelo escribe «## 3. METODOLOGÍA» o «## Metodologia y datos» según le da, y el
  progreso no puede depender de esa arbitrariedad.
- **Reconstruye encabezados partidos** entre tokens, que es lo normal al
  transmitir.
- **Avisa solo al cambiar** de sección: emitir por token convertiría el progreso
  en ruido y el cliente tendría que deduplicar.

La lista de secciones vive junto al detector con un aviso: son las que pide el
prompt del Redactor, y si el prompt cambia esta lista tiene que cambiar con él.

### Quien no sabe, no emite

`_emit_progress` solo lo llama quien conoce sus unidades. Los demás no mandan
nada y la interfaz los deja **indeterminados**, que es la respuesta honesta: una
barra indeterminada dice «no sé cuánto falta», y eso es cierto.

### Tests

`tests/test_progress_units.py`, 14 casos. Dos son la prohibición de AC5 hecha
test: mil tokens sin encabezado siguen dando «no sé en qué sección voy», y el
resultado no depende de en cuántos trozos llegue el texto. Si alguien sustituyera
esto por una cuenta de tokens o un reloj, esos dos fallarían.

### Definition of Done

- [x] AC5: progreso fraccional solo con unidades de trabajo reales.
- [x] AC5: sin unidades, estado indeterminado.
- [x] AC5: no se deriva de tokens emitidos ni de tiempo transcurrido.
- [x] El evento viaja por el SSE que ya existía, junto a los demás.
