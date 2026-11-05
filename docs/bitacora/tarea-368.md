# Tarea #368 — T18.5: Pantalla de subida de referencia y configuración de la ejecución

## 2026-11-05 — Completada ✅

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **Spec:** SPEC-030 · Épica E18 · AC6, AC7

### Qué se hizo y dónde

- `backend/app/models/agent_run.py` — `AgentRunRequest` acepta `swarm_notes`,
  `reference_doc_id` y `format_mode`.
- `backend/app/routers/agents.py` — valida la variante del grafo (T18.2) y el
  modo de formato **antes** de lanzar, y pasa los parámetros al orquestador.
- `Orchestrator.run` los acepta y los mete en el estado; de ahí van a la traza.
- `frontend/src/platform/runConfig.js` (nuevo) — tope de notas y modos.
- `FlowDesignerPage` — campo de notas con contador, y selector de modo.

### AC6: la opción que no está, se enseña

`finetune` aparece **deshabilitada con su motivo visible** —«Pendiente de decidir
en SPEC-031»— en vez de ocultarse. Una opción que no aparece parece no existir, y
esta existe: se está decidiendo. El backend la rechaza con 422 y el mismo motivo,
así que el cliente no es quien decide qué vale.

### Los modos duplicados, a sabiendas

`FORMAT_MODES` está en el backend y espejado en el frontend. El módulo del cliente
lo dice en su cabecera: la autoridad es el servidor, que valida. Lo del cliente es
la afordancia —que el contador avance y la opción no disponible se vea antes de
pulsar—.

Si divergen, la interfaz enseñaría un tope o una opción que el servidor no acepta y
el error llegaría al ejecutar en vez de al escribir: molesto, no peligroso. Lo
contrario —que el cliente decidiera qué es válido— sí lo sería.

### Qué no se hizo

- **La subida de la referencia desde esta pantalla.** El acotamiento por documento
  funciona y está probado (T18.1), y el endpoint acepta `reference_doc_id`, pero el
  selector que sube un fichero y lo ata a este paper en un paso no está: hoy se
  sube por la pantalla de documentos y se pasa el identificador. Queda como trabajo
  de interfaz, no de mecanismo.

### Definition of Done

- [x] AC6: RAG funciona; fine-tune no disponible con el motivo visible.
- [x] AC6: el modo elegido queda registrado en la ejecución.
- [x] AC7: referencia, agentes, notas y modo quedan en la traza.
- [x] La selección de agentes se valida antes de arrancar (vía T18.2).
- [ ] Subida de la referencia en un paso desde esta pantalla.
