# Fix — T16.4: pasos que quedaban abiertos y falseaban el estado «incierto»

## 2026-11-05 — Corregido

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **Spec:** SPEC-028 · AC4 (corrige lo entregado en [tarea-355](tarea-355.md))

## Síntoma

Agentes en estado **«incierto»** sin que hubiera nada ejecutándose.

El estado en sí es correcto: significa que hay un paso abierto desde hace más del
umbral y, por tanto, que no se sabe si el agente trabaja. El problema era que se
llegaba a él por dos caminos en los que no había ninguna incertidumbre real —solo
una fila mal cerrada—.

## Causa 1: cancelar una ejecución (reproducible)

`asyncio.CancelledError` hereda de `BaseException`, **no de `Exception`**, desde
Python 3.8. El wrapper del nodo cerraba la fila de `agent_runs` en dos sitios: el
camino de éxito y un `except Exception`. La cancelación no pasa por ninguno de los
dos, así que `log_run_end` no llegaba a ejecutarse y la fila se quedaba en
`running` para siempre.

Cancelar es un botón de la interfaz, no un caso extremo: **cada cancelación dejaba
un agente en «incierto» de forma permanente**.

Se añade una rama `except asyncio.CancelledError` que cierra el run como
`cancelled`, deja su paso en la traza —T9.1/AC1 pide el paso «cuando termina **o
se cancela**», y saber dónde se cortó es justo lo que se pregunta después— y
**vuelve a lanzar**: tragarse una cancelación deja la tarea viva, que es peor que
el problema que arregla.

**Nicolás llegó a esto por su cuenta** en `8b60ee2`, y su versión es mejor que la
primera que escribí: envuelve el cierre en `asyncio.shield`. El detalle importa y
se me había escapado — estamos **dentro** de una tarea ya cancelada, así que un
`await` sin proteger se cancelaría a su vez y dejaría la fila abierta, que es
exactamente el fallo que la rama pretende arreglar. Se conserva su implementación
y se le añade el comentario que explica por qué `CancelledError` necesita rama
propia; sin esa nota, el siguiente que lea el `except Exception` de debajo pensará
que ya cubre todo.

## Causa 2: el proceso muere de golpe

Un `SIGKILL`, un corte de luz o cerrar la ventana no dan oportunidad de cerrar
nada desde dentro. Para eso, `close_orphan_runs()` barre al arrancar: si este
proceso acaba de empezar, nada de lo que dejó abierto el anterior sigue vivo.

Pasó en esta misma sesión: varios `pkill` al backend mientras había ejecuciones en
vuelo.

**Con varios workers la premisa no se sostiene**, así que solo se cierran las filas
más antiguas que `SWARM_STALE_AFTER_S`. Es el mismo umbral con el que la portada ya
deja de llamarlas «ejecutando», y es el mismo a propósito: dos criterios distintos
para la misma pregunta acabarían discrepando, y habría una ventana en la que la
portada dice una cosa y el registro otra. Se marcan como `interrupted` con el
motivo escrito, no como `completed`: no terminaron.

## Lo que no cambia

El estado «incierto» se queda. Sigue siendo la respuesta correcta cuando un paso
lleva abierto más del umbral en un proceso vivo —por ejemplo, un agente colgado
esperando a un LLM que no responde—. Lo que se han quitado son las dos formas de
llegar a él sin que hubiera nada que dudar.

## Tests

`tests/test_orphan_runs.py`, 9 casos. Los tres primeros fijan la rama de
cancelación —que existe, que cierra y traza, y que vuelve a lanzar—, de modo que
quitarla rompa la suite. Los demás cubren la barrida: cierra lo viejo, **no toca lo
recién abierto** —que puede estar ejecutándose de verdad—, usa el mismo umbral que
la portada, y no toca lo que ya estaba cerrado.

## Definition of Done

- [x] Cancelar una ejecución cierra su paso y lo deja en la traza.
- [x] Un proceso que muere de golpe no deja agentes en «incierto» tras reiniciar.
- [x] La barrida usa el mismo umbral que el estado del enjambre.
- [x] «Incierto» se conserva para el caso en que de verdad no se sabe.
