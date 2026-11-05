"""Tickets efímeros y de un solo uso para autenticar el stream SSE (T1.4).

La API `EventSource` del navegador no puede mandar cabecera `Authorization`, así
que el stream aceptaba el JWT en el query string (`/stream?token=<JWT>`), lo que
filtra una credencial de larga vida a los logs del servidor, al historial del
navegador y a los del proxy. En su lugar, un cliente ya autenticado cambia su JWT
—enviado como Bearer en un POST normal— por un **ticket** opaco, y se conecta con
`?ticket=<ticket>`. Un ticket filtrado no sirve de gran cosa: caduca en segundos y
se consume al primer uso.

**El almacén vive en el bus de coordinación** (SPEC-018/T4.3), no en un diccionario
de proceso. Con varios workers, el POST que emite el ticket y la conexión SSE que
lo canjea caen casi siempre en procesos distintos: con el almacén local, el segundo
no reconocería el ticket del primero y el stream respondería `403` sin motivo
aparente.
"""

from __future__ import annotations

import secrets

from app.platform.bus import get_bus

DEFAULT_TTL_SECONDS = 30


async def issue_ticket(user_id: str, article_id: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """Emitir un ticket de un solo uso que ata *user_id* a *article_id*."""
    ticket = secrets.token_urlsafe(32)
    await get_bus().store_ticket(
        ticket,
        {"user_id": str(user_id), "article_id": str(article_id)},
        ttl_seconds,
    )
    return ticket


async def consume_ticket(ticket: str, article_id: str) -> str | None:
    """Devolver el `user_id` atado si el ticket vale para *article_id*; si no, `None`.

    El ticket se retira **en cualquier intento**, válido o no, para que no pueda
    reproducirse.
    """
    if not ticket:
        return None
    datos = await get_bus().take_ticket(ticket)
    if datos is None:
        return None
    if datos.get("article_id") != str(article_id):
        return None
    return datos.get("user_id")


async def issue_project_ticket(user_id: str, project_id: str,
                               ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """Ticket para el log en vivo de un proyecto (SPEC-029 / T17.5 / AC2).

    Hermano de `issue_ticket` y no un parámetro suyo: el ticket de artículo ata
    a un artículo y este a un proyecto, y mezclarlos abriría la puerta a canjear
    uno donde vale el otro. Dos funciones con dos comprobaciones distintas es más
    difícil de confundir que una con un modo.
    """
    ticket = secrets.token_urlsafe(32)
    await get_bus().store_ticket(
        ticket,
        {"user_id": str(user_id), "project_id": str(project_id)},
        ttl_seconds,
    )
    return ticket


async def consume_project_ticket(ticket: str, project_id: str) -> str | None:
    """Devolver el `user_id` atado si el ticket vale para *project_id*.

    Un ticket de artículo no sirve aquí: no lleva `project_id`, así que la
    comparación falla y se rechaza.
    """
    if not ticket:
        return None
    datos = await get_bus().take_ticket(ticket)
    if datos is None:
        return None
    if datos.get("project_id") != str(project_id):
        return None
    return datos.get("user_id")


async def reset_stream_tickets() -> None:
    """Vaciar los tickets pendientes (lo usan los tests para aislar casos)."""
    await get_bus().clear_tickets()
