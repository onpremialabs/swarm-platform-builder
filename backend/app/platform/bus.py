"""Bus de coordinación entre workers (SPEC-018 / T4.3 / AC3).

Con **un** worker basta con diccionarios en memoria: el proceso que ejecuta el
pipeline es el mismo que atiende el SSE y el que recibe la decisión humana. Con
**varios**, esas tres cosas caen en procesos distintos y el estado en memoria deja
de servir: el navegador se conecta al worker B mientras el pipeline corre en el A,
así que no ve un solo evento; y la decisión HITL llega al C, que no tiene el
`Future` que espera nadie.

Este módulo esconde esa diferencia detrás de una interfaz y ofrece dos
implementaciones:

* **`InProcessBus`** — lo que había, palabra por palabra en comportamiento. Es el
  valor por defecto: desarrollar no debe exigir levantar Redis.
* **`RedisBus`** — pub/sub para los eventos y para las señales de control. Se activa
  con `REDIS_ENABLED`.

**Lo que no se puede mover, y por qué.** El registro de tareas guarda objetos
`asyncio.Task`: manejadores de corrutinas vivas, no datos. No hay forma de
serializarlos, así que la tarea **sigue siendo local al worker que la lanzó**. Lo
que viaja por Redis es la *señal*: cancelar publica un mensaje de control y el
worker dueño de la tarea la cancela. Igual con la decisión humana: el `Future` vive
donde espera el pipeline, y por el bus solo va el valor.

De ahí que existan `mark_running`/`is_running`: sin ellos, un `409 No active
pipeline` sería mentira en cuanto el pipeline corriese en otro worker.
"""
from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

#: Segundos que sobrevive la marca de «pipeline en curso» sin refrescarse. Si un
#: worker muere a mitad, la clave caduca sola en vez de bloquear el artículo.
RUNNING_TTL_SECONDS = 3600

#: Igual para la marca de «esperando decisión»: acota el 409 al tiempo real de espera.
AWAITING_TTL_SECONDS = 1800

_EVENTS = "agents:events:{article_id}"
#: Canal del log en vivo por proyecto (T17.5). Separado del de artículo a
#: propósito: así un worker que solo sirve el log del proyecto no recibe —ni
#: puede filtrar mal— los eventos de artículos de otros proyectos.
_PROJECT_EVENTS = "agents:project-events:{project_id}"
#: El vínculo artículo→proyecto vive en Redis para que lo vea el worker que
#: atiende el log aunque la ejecución corra en otro.
_ARTICLE_PROJECT = "agents:article-project:{article_id}"
_CONTROL = "agents:control:{article_id}"
_RUNNING = "agents:running:{article_id}"
_AWAITING = "agents:awaiting:{article_id}"
_TICKET = "sse:ticket:{ticket}"


class InProcessBus:
    """Coordinación dentro de un solo proceso (comportamiento histórico)."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, list[asyncio.Queue]] = {}
        self._running: Dict[str, dict] = {}
        self._decisions: Dict[str, "asyncio.Future[str]"] = {}
        self._cancels: Dict[str, Any] = {}
        self._tickets: Dict[str, tuple[dict, float]] = {}
        #: Log en vivo por proyecto (SPEC-029 / T17.5 / AC2). Dos registros: a qué
        #: proyecto pertenece cada artículo, y quién escucha cada proyecto.
        self._article_project: Dict[str, str] = {}
        self._project_subscribers: Dict[str, list[asyncio.Queue]] = {}

    # -- eventos ----------------------------------------------------------- #

    def bind_project(self, article_id: uuid.UUID, project_id) -> None:
        """Declara a qué proyecto pertenece un artículo, para el log del proyecto.

        Sin esta marca los eventos del artículo **no** llegan a ningún flujo de
        proyecto. Es deliberado: ante la duda, no entregar. Perder un evento en
        el log en vivo es un inconveniente; entregarlo al proyecto equivocado
        rompe el aislamiento de T8.5 justo en la vista pensada para auditar.
        """
        if project_id is None:
            return
        self._article_project[str(article_id)] = str(project_id)

    def unbind_project(self, article_id: uuid.UUID) -> None:
        self._article_project.pop(str(article_id), None)

    async def publish(self, article_id: uuid.UUID, event: dict) -> None:
        self.publish_nowait(article_id, event)

    def publish_nowait(self, article_id: uuid.UUID, event: dict) -> None:
        """Publicar sin `await`.

        Los agentes emiten tokens y logs desde *callbacks síncronos*, así que la
        publicación tiene que poder hacerse sin await. Aquí es entrega directa.
        """
        for queue in list(self._subscribers.get(str(article_id), [])):
            with contextlib.suppress(Exception):
                queue.put_nowait(event)
        self._fanout_project(article_id, event)

    def _fanout_project(self, article_id: uuid.UUID, event: dict) -> None:
        """Entrega el evento a quien escucha **ese** proyecto, y a nadie más.

        El filtro es de servidor: un evento de otro proyecto no sale de aquí, ni
        siquiera para que el navegador lo descarte (AC2). Se añade `article_id`
        porque el flujo del proyecto mezcla varias ejecuciones y sin él no se
        podrían separar.
        """
        proyecto = self._article_project.get(str(article_id))
        if not proyecto:
            return
        oyentes = self._project_subscribers.get(proyecto)
        if not oyentes:
            return
        enriquecido = {**event, "article_id": str(article_id)}
        for queue in list(oyentes):
            with contextlib.suppress(Exception):
                queue.put_nowait(enriquecido)

    @contextlib.asynccontextmanager
    async def subscribe_project(self, project_id) -> AsyncIterator[asyncio.Queue]:
        """Flujo de eventos de un proyecto, ya filtrado en servidor (AC2)."""
        key = str(project_id)
        queue: asyncio.Queue = asyncio.Queue()
        self._project_subscribers.setdefault(key, []).append(queue)
        try:
            yield queue
        finally:
            colas = self._project_subscribers.get(key, [])
            if queue in colas:
                colas.remove(queue)
            if not colas:
                self._project_subscribers.pop(key, None)

    @contextlib.asynccontextmanager
    async def subscribe(self, article_id: uuid.UUID) -> AsyncIterator[asyncio.Queue]:
        key = str(article_id)
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(key, []).append(queue)
        try:
            yield queue
        finally:
            colas = self._subscribers.get(key, [])
            if queue in colas:
                colas.remove(queue)
            if not colas:
                self._subscribers.pop(key, None)

    # -- presencia --------------------------------------------------------- #

    async def mark_running(self, article_id: uuid.UUID, info: Optional[dict] = None) -> None:
        """Marca el artículo como en ejecución, con qué se está ejecutando.

        El `info` —la secuencia de agentes y cuál corre ahora— es lo que permite
        reconstruir la vista en vivo al volver a ella (SPEC-030 / T18.7). Antes
        solo vivía en `location.state` del navegador, así que navegar a otra
        pestaña la perdía aunque el pipeline siguiera corriendo: el servidor sabía
        que había algo en marcha pero no podía decir **qué**.
        """
        self._running[str(article_id)] = dict(info or {})

    async def clear_running(self, article_id: uuid.UUID) -> None:
        self._running.pop(str(article_id), None)

    async def is_running(self, article_id: uuid.UUID) -> bool:
        return str(article_id) in self._running

    async def update_run_info(self, article_id: uuid.UUID, **campos) -> None:
        """Actualiza parte del `info` sin pisar el resto (p. ej. el agente actual).

        Si el artículo ya no está en ejecución no se reabre: una carrera entre el
        cierre y un último evento no debe resucitar la marca.
        """
        actual = self._running.get(str(article_id))
        if actual is not None:
            actual.update(campos)

    async def get_run_info(self, article_id: uuid.UUID) -> Optional[dict]:
        info = self._running.get(str(article_id))
        # Copia **profunda**: `dict(info)` comparte las listas de dentro, así que
        # quien leyera la secuencia de agentes podía modificar el estado del bus
        # sin querer. En el camino de Redis esto sale gratis porque se
        # deserializa; aquí hay que hacerlo a mano.
        return copy.deepcopy(info) if info is not None else None

    async def running_articles(self) -> Dict[str, dict]:
        """Todo lo que está en ejecución, para el aviso persistente del shell."""
        return copy.deepcopy(self._running)

    # -- cancelación ------------------------------------------------------- #

    def register_cancel_handler(self, article_id: uuid.UUID, handler) -> None:
        self._cancels[str(article_id)] = handler

    def unregister_cancel_handler(self, article_id: uuid.UUID) -> None:
        self._cancels.pop(str(article_id), None)

    async def request_cancel(self, article_id: uuid.UUID) -> bool:
        handler = self._cancels.get(str(article_id))
        if handler is None:
            return False
        handler()
        return True

    # -- decisión humana --------------------------------------------------- #

    @contextlib.asynccontextmanager
    async def awaiting_decision(self, article_id: uuid.UUID) -> AsyncIterator["asyncio.Future[str]"]:
        key = str(article_id)
        future: "asyncio.Future[str]" = asyncio.get_event_loop().create_future()
        self._decisions[key] = future
        try:
            yield future
        finally:
            self._decisions.pop(key, None)

    async def submit_decision(self, article_id: uuid.UUID, decision: str) -> bool:
        future = self._decisions.get(str(article_id))
        if future is None or future.done():
            return False
        future.set_result(decision)
        return True

    # -- tickets de stream (SPEC-015/AC3, compartidos desde T4.3) ---------- #

    async def store_ticket(self, ticket: str, payload: dict, ttl_seconds: int) -> None:
        self._tickets[ticket] = (payload, time.monotonic() + max(1, ttl_seconds))

    async def take_ticket(self, ticket: str) -> Optional[dict]:
        """Devuelve el ticket y lo borra: es de un solo uso, válido o no."""
        entrada = self._tickets.pop(ticket, None)
        if entrada is None:
            return None
        payload, expira = entrada
        return payload if expira > time.monotonic() else None

    async def clear_tickets(self) -> None:
        self._tickets.clear()

    async def close(self) -> None:
        return None


class RedisBus(InProcessBus):
    """Coordinación entre varios workers.

    Hereda de `InProcessBus` a propósito: los `Future` y los manejadores de
    cancelación **siguen siendo locales** —no son serializables— y lo que se añade
    aquí es el transporte que los despierta desde otro proceso. Escribirlo como
    herencia deja explícito qué parte es local y cuál compartida.
    """

    def __init__(self, url: str) -> None:
        super().__init__()
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(url, decode_responses=True)
        self._control_subs: Dict[str, asyncio.Task] = {}
        # Buzón de salida: mantiene el orden de los eventos (ver `publish_nowait`).
        self._outbox: asyncio.Queue = asyncio.Queue()
        self._drain_task: Optional[asyncio.Task] = None

    # -- eventos ----------------------------------------------------------- #

    def bind_project(self, article_id: uuid.UUID, project_id) -> None:
        """Igual que en memoria, pero el vínculo también va a Redis.

        El log del proyecto lo puede atender un worker distinto del que ejecuta,
        y sin el vínculo compartido ese worker no sabría a qué canal encaminar.
        """
        super().bind_project(article_id, project_id)
        if project_id is None:
            return

        async def _escribir() -> None:
            with contextlib.suppress(Exception):
                await self._redis.set(
                    _ARTICLE_PROJECT.format(article_id=article_id),
                    str(project_id), ex=RUNNING_TTL_SECONDS,
                )

        # Fuera del buzón de eventos: ese preserva el orden de los tokens y
        # mezclarle otro tipo de mensaje lo volvería un protocolo.
        with contextlib.suppress(RuntimeError):  # sin bucle en marcha
            asyncio.create_task(_escribir())

    async def publish(self, article_id: uuid.UUID, event: dict) -> None:
        await self._redis.publish(
            _EVENTS.format(article_id=article_id), json.dumps(event, default=str)
        )
        # Y al canal del proyecto, si el artículo está vinculado. Se resuelve en
        # Redis y no solo en memoria para que valga entre workers.
        proyecto = self._article_project.get(str(article_id))
        if proyecto is None:
            with contextlib.suppress(Exception):
                proyecto = await self._redis.get(
                    _ARTICLE_PROJECT.format(article_id=article_id))
        if proyecto:
            with contextlib.suppress(Exception):
                await self._redis.publish(
                    _PROJECT_EVENTS.format(project_id=proyecto),
                    json.dumps({**event, "article_id": str(article_id)}, default=str),
                )

    @contextlib.asynccontextmanager
    async def subscribe_project(self, project_id) -> AsyncIterator[asyncio.Queue]:
        """Mismo puente que `subscribe`, sobre el canal del proyecto (AC2)."""
        queue: asyncio.Queue = asyncio.Queue()
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(_PROJECT_EVENTS.format(project_id=project_id))

        async def _bombear() -> None:
            async for mensaje in pubsub.listen():
                if mensaje.get("type") != "message":
                    continue
                with contextlib.suppress(Exception):
                    queue.put_nowait(json.loads(mensaje["data"]))

        bomba = asyncio.create_task(_bombear())
        try:
            yield queue
        finally:
            bomba.cancel()
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe()
                await pubsub.aclose()

    def publish_nowait(self, article_id: uuid.UUID, event: dict) -> None:
        """Encolar en el buzón; lo vacía **una sola** tarea, en orden.

        No se lanza una tarea por evento: `asyncio` no garantiza el orden entre
        tareas independientes y los `token` del streaming llegarían barajados, que
        es peor que llegar tarde. Un único consumidor secuencial preserva el orden
        de emisión, que es justo lo que el cliente necesita para ir componiendo el
        texto.
        """
        self._outbox.put_nowait((article_id, event))
        self._ensure_drain()

    def _ensure_drain(self) -> None:
        if self._drain_task is not None and not self._drain_task.done():
            return
        with contextlib.suppress(RuntimeError):  # sin bucle en marcha: nada que drenar
            self._drain_task = asyncio.create_task(self._drain())

    async def _drain(self) -> None:
        while True:
            article_id, event = await self._outbox.get()
            try:
                await self.publish(article_id, event)
            except Exception:
                logger.warning(
                    "No se pudo publicar un evento del pipeline",
                    exc_info=True,
                    extra={"event": "bus_publish_failed", "article_id": str(article_id)},
                )
            finally:
                self._outbox.task_done()

    @contextlib.asynccontextmanager
    async def subscribe(self, article_id: uuid.UUID) -> AsyncIterator[asyncio.Queue]:
        queue: asyncio.Queue = asyncio.Queue()
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(_EVENTS.format(article_id=article_id))

        async def _bombear() -> None:
            async for mensaje in pubsub.listen():
                if mensaje.get("type") != "message":
                    continue
                with contextlib.suppress(Exception):
                    queue.put_nowait(json.loads(mensaje["data"]))

        bomba = asyncio.create_task(_bombear())
        try:
            yield queue
        finally:
            bomba.cancel()
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe()
                await pubsub.aclose()

    # -- presencia --------------------------------------------------------- #

    async def mark_running(self, article_id: uuid.UUID, info: Optional[dict] = None) -> None:
        """La marca guarda el `info`, no un «1».

        Así `is_running` sigue siendo «¿existe la clave?» y de paso el contenido
        viaja con ella: un worker distinto del que ejecuta puede contestar qué se
        está ejecutando sin preguntarle a nadie.
        """
        await self._redis.set(
            _RUNNING.format(article_id=article_id),
            json.dumps(dict(info or {}), default=str),
            ex=RUNNING_TTL_SECONDS,
        )

    async def clear_running(self, article_id: uuid.UUID) -> None:
        await self._redis.delete(_RUNNING.format(article_id=article_id))

    async def is_running(self, article_id: uuid.UUID) -> bool:
        return bool(await self._redis.exists(_RUNNING.format(article_id=article_id)))

    async def update_run_info(self, article_id: uuid.UUID, **campos) -> None:
        actual = await self.get_run_info(article_id)
        if actual is None:
            return  # ya terminó: no se reabre la marca
        actual.update(campos)
        # Se conserva el TTL restante en vez de renovarlo: la marca caduca a la
        # hora de **empezar**, no a la hora del último evento, que con un agente
        # colgado la mantendría viva indefinidamente.
        ttl = await self._redis.ttl(_RUNNING.format(article_id=article_id))
        await self._redis.set(
            _RUNNING.format(article_id=article_id),
            json.dumps(actual, default=str),
            ex=ttl if ttl and ttl > 0 else RUNNING_TTL_SECONDS,
        )

    async def get_run_info(self, article_id: uuid.UUID) -> Optional[dict]:
        crudo = await self._redis.get(_RUNNING.format(article_id=article_id))
        if not crudo:
            return None
        try:
            return json.loads(crudo)
        except (TypeError, ValueError):
            # Marca de una versión anterior, que guardaba «1». Sigue significando
            # «está en ejecución»; simplemente no sabe decir con qué.
            return {}

    async def running_articles(self) -> Dict[str, dict]:
        fuera: Dict[str, dict] = {}
        async for clave in self._redis.scan_iter(match=_RUNNING.format(article_id="*")):
            aid = str(clave).rsplit(":", 1)[-1]
            crudo = await self._redis.get(clave)
            try:
                fuera[aid] = json.loads(crudo) if crudo else {}
            except (TypeError, ValueError):
                fuera[aid] = {}
        return fuera

    # -- control (cancelación y decisión) ---------------------------------- #

    def register_cancel_handler(self, article_id: uuid.UUID, handler) -> None:
        super().register_cancel_handler(article_id, handler)
        self._listen_control(article_id)

    def unregister_cancel_handler(self, article_id: uuid.UUID) -> None:
        super().unregister_cancel_handler(article_id)
        self._stop_control(article_id)

    def _listen_control(self, article_id: uuid.UUID) -> None:
        """Escucha el canal de control del artículo en el worker que lo ejecuta."""
        key = str(article_id)
        if key in self._control_subs:
            return

        async def _escuchar() -> None:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(_CONTROL.format(article_id=key))
            try:
                async for mensaje in pubsub.listen():
                    if mensaje.get("type") != "message":
                        continue
                    try:
                        datos = json.loads(mensaje["data"])
                    except Exception:
                        continue
                    if datos.get("type") == "cancel":
                        handler = self._cancels.get(key)
                        if handler is not None:
                            handler()
                    elif datos.get("type") == "decision":
                        await super(RedisBus, self).submit_decision(article_id, datos.get("value"))
            finally:
                with contextlib.suppress(Exception):
                    await pubsub.unsubscribe()
                    await pubsub.aclose()

        self._control_subs[key] = asyncio.create_task(_escuchar())

    def _stop_control(self, article_id: uuid.UUID) -> None:
        tarea = self._control_subs.pop(str(article_id), None)
        if tarea is not None:
            tarea.cancel()

    async def request_cancel(self, article_id: uuid.UUID) -> bool:
        """Publica la señal; la cancela el worker que tiene la tarea.

        Se apoya en `is_running` para responder si había algo que cancelar: quien
        atiende la petición HTTP puede no ser el dueño de la tarea.
        """
        if not await self.is_running(article_id):
            return False
        await self._redis.publish(
            _CONTROL.format(article_id=article_id), json.dumps({"type": "cancel"})
        )
        return True

    @contextlib.asynccontextmanager
    async def awaiting_decision(self, article_id: uuid.UUID) -> AsyncIterator["asyncio.Future[str]"]:
        await self._redis.set(
            _AWAITING.format(article_id=article_id), "1", ex=AWAITING_TTL_SECONDS
        )
        self._listen_control(article_id)
        try:
            async with super().awaiting_decision(article_id) as future:
                yield future
        finally:
            with contextlib.suppress(Exception):
                await self._redis.delete(_AWAITING.format(article_id=article_id))

    async def submit_decision(self, article_id: uuid.UUID, decision: str) -> bool:
        esperando = await self._redis.exists(_AWAITING.format(article_id=article_id))
        if not esperando:
            return False
        await self._redis.publish(
            _CONTROL.format(article_id=article_id),
            json.dumps({"type": "decision", "value": decision}),
        )
        return True

    # -- tickets de stream ------------------------------------------------- #

    async def store_ticket(self, ticket: str, payload: dict, ttl_seconds: int) -> None:
        await self._redis.set(_TICKET.format(ticket=ticket), json.dumps(payload), ex=max(1, ttl_seconds))

    async def take_ticket(self, ticket: str) -> Optional[dict]:
        """`GETDEL`: leer y borrar en una sola operación atómica.

        Es lo que hace que «un solo uso» siga siendo cierto con varios workers.
        Un `GET` seguido de `DELETE` deja una ventana en la que dos conexiones
        simultáneas podrían canjear el mismo ticket.
        """
        crudo = await self._redis.getdel(_TICKET.format(ticket=ticket))
        if crudo is None:
            return None
        with contextlib.suppress(Exception):
            return json.loads(crudo)
        return None

    async def clear_tickets(self) -> None:
        claves = [k async for k in self._redis.scan_iter(match=_TICKET.format(ticket="*"))]
        if claves:
            await self._redis.delete(*claves)

    async def close(self) -> None:
        for tarea in list(self._control_subs.values()):
            tarea.cancel()
        self._control_subs.clear()
        if self._drain_task is not None:
            self._drain_task.cancel()
            self._drain_task = None
        with contextlib.suppress(Exception):
            await self._redis.aclose()


_bus: Optional[InProcessBus] = None


def get_bus() -> InProcessBus:
    """Bus activo, creado la primera vez que se pide.

    Si Redis está activado pero no se puede construir el cliente, **se cae al bus en
    proceso con un aviso** en lugar de tumbar el arranque: perder la coordinación
    entre workers degrada el servicio, pero no arrancar lo deja fuera del todo.
    """
    global _bus
    if _bus is None:
        if settings.REDIS_ENABLED:
            try:
                _bus = RedisBus(settings.REDIS_URL)
                logger.info(
                    "Coordinación entre workers vía Redis",
                    extra={"event": "bus_backend", "backend": "redis"},
                )
            except Exception:
                logger.error(
                    "Redis activado pero no se pudo inicializar; se usa el bus en "
                    "proceso. Con más de un worker se perderán eventos SSE.",
                    exc_info=True,
                    extra={"event": "bus_backend_fallback", "backend": "memory"},
                )
                _bus = InProcessBus()
        else:
            _bus = InProcessBus()
    return _bus


async def reset_bus() -> None:
    """Suelta el bus activo (tests, y cierre ordenado de la aplicación)."""
    global _bus
    if _bus is not None:
        await _bus.close()
    _bus = None
