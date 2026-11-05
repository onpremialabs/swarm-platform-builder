# Tarea #362 — T17.5: Log en vivo por proyecto, filtrado en servidor

## 2026-11-05 — Completada ✅

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **Spec:** SPEC-029 · Épica E17 · AC2

### El riesgo que marca la spec

«El punto con más riesgo de fuga». El SSE existente es por artículo y hereda su
autorización; un flujo «del proyecto» puede entregar de más si filtra en el
cliente, y lo haría justo en la vista pensada para auditar.

### Qué se hizo y dónde

- `backend/app/platform/bus.py` — `bind_project()`, `unbind_project()`,
  `subscribe_project()` y el reparto `_fanout_project()`, en `InProcessBus`; el
  canal equivalente en `RedisBus`.
- `backend/app/core/stream_auth.py` — `issue_project_ticket()` y
  `consume_project_ticket()`.
- `backend/app/routers/dashboard.py` — `POST /api/v1/dashboard/log-ticket` y
  `GET /api/v1/dashboard/log-stream`.
- `use_cases.py` — vincula artículo y proyecto al arrancar el pipeline.

### El filtro es de servidor, y falla cerrado

El bus guarda a qué proyecto pertenece cada artículo y entrega el evento **solo** a
quien escucha ese proyecto. Un evento de otro proyecto no sale del servidor: no
llega al cliente ni siquiera para descartarse en el navegador, porque filtrar en el
cliente significa habérselo mandado primero.

Un artículo **sin vincular no emite en ningún flujo de proyecto**. Es deliberado:
ante la duda, no entregar. Perder una línea del log molesta; entregarla al proyecto
ajeno rompe el aislamiento de T8.5.

El vínculo se declara donde se conoce el proyecto de verdad —al arrancar el
pipeline, desde `initial_state`— y no en el endpoint, que solo sabe quién pregunta.

### Ticket propio, no un modo del existente

`issue_project_ticket` es hermano de `issue_ticket`, no un parámetro suyo: uno ata
a un artículo y el otro a un proyecto, y mezclarlos abriría la puerta a canjear uno
donde vale el otro. Dos funciones con dos comprobaciones distintas son más difíciles
de confundir que una con un modo.

### Redis: mismo patrón, canal aparte

`RedisBus` publica también en `agents:project-events:{project_id}` y
`subscribe_project` puentea ese canal igual que `subscribe` hace con el del
artículo. El vínculo artículo→proyecto se guarda además en Redis, porque el worker
que atiende el log puede no ser el que ejecuta.

### El camino de Redis, probado

`tests/test_project_log_stream_redis.py` ejercita `RedisBus` con `fakeredis`, una
implementación del protocolo con la que `redis-py` habla de verdad: se recorren los
`publish`/`subscribe` reales, los nombres de canal y el buzón de salida, no un
doble escrito por nosotros. Cinco casos: el evento llega por el canal del proyecto,
**no se filtra entre proyectos**, un artículo sin vincular no llega a ninguno, el
vínculo se resuelve desde Redis aunque el proceso no lo tenga en memoria —el caso
de otro worker—, y el canal por artículo sigue funcionando.

Se comprobó que el test **tiene dientes**: apuntando todos los proyectos al mismo
canal, `test_no_se_filtra_entre_proyectos_sobre_redis` falla. Un test de
aislamiento que pasa pase lo que pase es peor que no tenerlo.

Lo que esto **no** cubre: el comportamiento de un servidor Redis concreto y su
versión, y la entrega entre procesos de sistema distintos. Para eso hace falta un
Redis de verdad, y en esta máquina no hay ni Docker ni WSL. `fakeredis` va en
`requirements-dev.txt`, que la CI no instala, así que allí el fichero se salta.

### Tests

`tests/test_project_log_stream.py`, seis casos. El que importa: dos proyectos, un
oyente en uno, y se comprueba que el evento del otro **no llega**. Más: el evento
lleva `article_id` (el flujo mezcla ejecuciones y sin él no se podrían separar), un
artículo sin vincular no emite, desvincular corta la entrega, dos oyentes del mismo
proyecto reciben los dos, y el stream por artículo sigue funcionando sin
enriquecerse.

### Definition of Done

- [x] AC2: eventos del proyecto activo, filtrados en servidor.
- [x] AC2: test que suscribe a un proyecto y comprueba que no recibe del otro.
- [x] Autenticado por ticket de un solo uso atado al proyecto.
- [x] El stream por artículo no se rompe.
- [x] El camino de `RedisBus` ejercitado contra una implementación del protocolo,
      con prueba de que el test de aislamiento detecta la fuga.
- [ ] Verificación contra un servidor Redis real y entre procesos — hace falta un
      entorno con Docker o WSL, que esta máquina no tiene.
