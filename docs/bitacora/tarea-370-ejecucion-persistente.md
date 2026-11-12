# T18.7 — No perder de vista una ejecución al cambiar de pestaña

## 2026-11-06 — Completada ✅

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **Spec:** SPEC-030 · Épica E18 (hallazgo de uso, sin issue propia todavía)

## Síntoma

Con el pipeline corriendo, si salías a otra pestaña y volvías, la pantalla
enseñaba la traza histórica en vez de la ejecución en curso — **aunque siguiera
ejecutándose**. No había forma de volver a mirarla.

## Causa

La vista en vivo se construía con `location.state.flowSequence`, que le pasa el
Flow Designer al navegar. React Router descarta ese estado al cambiar de ruta, así
que al volver llegaba vacío y la página caía en modo histórico, que es lo correcto
**cuando de verdad no hay nada corriendo**. El problema es que no sabía
distinguir los dos casos.

Y no podía: **el servidor tampoco lo decía.** `is_running` existía en el bus pero
no estaba expuesto, y además solo guardaba un booleano — sabía que algo corría,
no con qué.

## Qué se hizo

### El servidor como fuente (A)

La marca de ejecución del bus pasa de guardar `"1"` a guardar la información:
secuencia de agentes, agente en curso, inicio y proyecto. `is_running` sigue
siendo «¿existe la clave?», así que nada de lo que había cambia.

- `mark_running(article_id, info)` — al arrancar el pipeline.
- `update_run_info(...)` — en cada `agent_start`, para saber quién corre **ahora**.
  No reabre una marca ya cerrada: una carrera entre el cierre y un último evento
  no debe resucitarla.
- `GET /api/v1/agents/{id}/status` — por artículo.
- `GET /api/v1/dashboard/running` — por proyecto, ligero, para la barra.

En Redis el TTL **no se renueva** al actualizar: la marca caduca a la hora de
empezar, no a la del último evento. Renovarla haría que un agente colgado la
mantuviera viva indefinidamente, que es justo lo que el umbral de «incierto»
intenta detectar.

El listado por proyecto descarta las marcas **sin** `project_id` —de una versión
anterior— en vez de enseñarlas: no se puede comprobar a quién pertenecen, y el
aislamiento de T8.5 no admite suposiciones.

### La pantalla se reconstruye sola

`TraceabilityPage`, al montar sin estado de navegación, pregunta al servidor en
vez de asumir. Si hay ejecución viva rehace las tarjetas, marca el agente en curso
y deja que el SSE —que se suscribe igual— siga pintando. Si no, modo histórico
como antes.

No relanza nada: el pipeline ya corre en el servidor, aquí solo se escucha.

### La barra persistente (C)

`RunningBar` vive en el shell, **por encima del `<Outlet/>`**, así que cambiar de
pestaña no la desmonta. Enseña qué corre, en qué agente va —«3 de 5»— y un enlace
para volver. Se oculta sola si ya estás mirando esa ejecución: ofrecer «volver» a
donde ya estás es ruido.

Sondea cada 5 s en lugar de abrir un SSE: es una barra de estado, no un log, y una
conexión viva por pestaña cuesta más que un GET ligero. Si una vuelta falla
conserva lo último que supo, porque vaciarla diría «ya no corre nada», que sería
falso.

## Un defecto que el test cazó

`get_run_info` devolvía `dict(info)` —copia superficial—, así que quien leyera la
secuencia de agentes podía modificar el estado del bus sin querer. Se pasa a
copia profunda. En el camino de Redis sale gratis porque se deserializa; en
memoria había que hacerlo a mano.

## Tests

`tests/test_run_status.py`, 9 casos: la marca guarda con qué se ejecuta, el agente
actual se actualiza sin pisar el resto, actualizar algo ya terminado no lo
resucita, al terminar deja de aparecer, lo devuelto es una copia, y el listado por
proyecto filtra por proyecto.

## Definition of Done

- [x] Volver a una ejecución en curso la muestra en vivo, no el histórico.
- [x] Funciona tras recargar, en otra pestaña y en otro equipo.
- [x] Hay aviso persistente desde cualquier pantalla del dashboard.
- [x] Acotado al proyecto activo.
