# Tarea #365 — T18.2: Agentes participantes como variante validada del GraphSpec

## 2026-11-05 — Completada ✅

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **Spec:** SPEC-030 · Épica E18 · AC2

### Qué se hizo y dónde

`backend/app/platform/engine/graph.py` — `restrict_to()` y `InvalidVariant`.
`backend/app/routers/agents.py` — se valida al lanzar, antes de arrancar nada.

Elegir agentes no es marcar casillas: es construir otra forma de pipeline. La
variante se construye **a partir del `GraphSpec` del proyecto**, así que el
resultado pasa por las mismas comprobaciones y la validación no puede divergir.

### El caso que da nombre al AC, y por qué es traicionero

Si conservas el revisor pero quitas el redactor, el bucle Revisor→Redactor apunta
a un nodo que no está en la secuencia. Lo que pasa entonces **no es un fallo
ruidoso**: `GraphSpec.nodes()` vuelve a añadir el destino del bucle a propósito
—la arista condicional lo necesita para no apuntar al vacío—, así que el redactor
se ejecutaría igual y la exclusión que pidió la persona se ignoraría en silencio.

Por eso se rechaza con un motivo que dice **qué hacer**: «o incluyes el redactor,
o quitas también el revisor». Un error que solo dice que algo está mal obliga a
adivinar.

### Qué no es un error

Quitar el revisor se lleva su bucle y ya está: es lo que significa quitar al
revisor. Los destinos de reintento se filtran a los que participan, porque la
plantilla ya documenta que cae al siguiente si uno no está en el flujo.

### El orden lo pone el proyecto

La secuencia resultante conserva el orden del `template.yaml`, no el de la
petición. Dejar que el cliente lo reordene convertiría un selector de
participantes en un editor de pipeline paralelo, con su propia forma de
equivocarse; eso es trabajo del Flow Designer.

### Tests

`tests/test_graph_variant.py`, 9 casos: lo que debe funcionar —quitar el
investigador, quitar el revisor, un solo agente, el orden— y lo que debe
rechazarse, con el caso del AC a la cabeza. También que la variante no muta el
spec del proyecto.

### Definition of Done

- [x] AC2: la selección se valida como variante del `GraphSpec`.
- [x] Mismas comprobaciones que al cargar el proyecto; no duplicadas.
- [x] Se rechaza **antes de empezar**, con el motivo.
- [x] El bucle cuyo nodo se ha quitado es el caso cubierto.
