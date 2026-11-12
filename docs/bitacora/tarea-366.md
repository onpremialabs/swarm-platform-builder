# Tarea #366 — T18.3: Notas acotadas, tratadas como dato y registradas

## 2026-11-05 — Completada ✅

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **Spec:** SPEC-030 · Épica E18 · AC3, AC7

### Qué se hizo y dónde

`backend/app/platform/run_config.py` (nuevo) — `MAX_SWARM_NOTES`,
`sanitize_notes()`, `notes_as_data()`, `run_params()` y `FORMAT_MODES`.
`explainability.params_of()` incorpora los parámetros de ejecución.
El Redactor usa las notas; `AgentState` las transporta.

### Dato, no instrucción

El campo que ya existía, `context_description`, se inserta en el prompt bajo el
rótulo «Instrucciones adicionales del autor»: le está diciendo al modelo que lo
trate como órdenes. Las notas no van así. Van delimitadas entre marcas y
precedidas de una línea que declara qué son y qué no pueden hacer.

No es defensa perfecta —ninguna lo es contra un prompt adversario— y no se vende
como tal. Lo que consigue es que el caso corriente, el de alguien que escribe
«ignora lo anterior» sin mala intención, quede como contenido de una nota.

### Longitud declarada, y el recorte se avisa

`MAX_SWARM_NOTES = 2000`: unos párrafos, suficiente para orientar una ejecución y
corto para que no quepa un prompt entero. `sanitize_notes` devuelve **si recortó**
en vez de hacerlo en silencio: quien escribió 2.500 caracteres tiene derecho a
saber que el agente vio 2.000. También se quitan los caracteres de control, que no
aportan a una nota y sí sirven para disimular texto.

### AC7: dos pasadas se distinguen

`params_of` junta los ajustes del agente con los parámetros de la ejecución
—notas, referencia, agentes, modo— y todo acaba en `agent_run_steps.params`. La
pregunta al leer la traza es una sola: «¿con qué corrió esto?».

De las notas se guarda **el texto**, no un resumen: AC3 pide poder atribuirles un
cambio de resultado, y para eso hay que poder leer cuáles eran. Están acotadas, así
que no convierten la traza en un almacén.

### Tests

`tests/test_run_config.py`, 14 casos: el tope y su aviso, los caracteres de
control, el delimitado como dato, un intento de inyección que queda dentro del
bloque —con la advertencia **antes**, no después—, y que dos pasadas con notas
distintas producen trazas distintas.

### Definition of Done

- [x] AC3: longitud máxima declarada.
- [x] AC3: se tratan como dato, nunca como instrucción de sistema.
- [x] AC3: quedan en la traza del paso que las usó.
- [x] AC7: los parámetros de ejecución distinguen dos pasadas.
