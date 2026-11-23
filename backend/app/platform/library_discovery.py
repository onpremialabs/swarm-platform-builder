"""Descubrimiento lanzado por la persona autora: busca, verifica y guarda candidatos
(SPEC-034 / T22.11 / AC12).

Lo dispara la **persona autora** desde Documentos, no el Investigador (que sigue usando solo
la biblioteca ya verificada, T22.5). Este módulo une las piezas que ya existen:
`run_literature_search` (descubrimiento + verificación + registro de la búsqueda, AC6) y
`verification.add_candidate_to_library` (guardar como `candidate`).

Reglas, todas de falla cerrada:

* Solo se guarda un candidato **verificado** (DOI resuelto y coincidente); un resolver caído
  nunca verifica, y lo no verificado no se guarda ni se ofrece.
* Un DOI que el proyecto ya tiene, **en cualquier estado** (candidato, aceptado, descartado),
  no se vuelve a crear: un descartado no reaparece por cada búsqueda. La comprobación mira
  solo `library_documents` del proyecto activo, así que no hay fuga entre proyectos.
* Una base caída, limitada u omitida no oculta a las demás: la respuesta lleva el estado de
  cada una. El mensaje de error de la base **no** se devuelve (puede llevar la URL con la
  clave o el correo de contacto): solo una etiqueta cerrada con su explicación.
* Con `LITERATURE_DISCOVERY_ENABLED` apagado no se hace ninguna petición de red.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional
from uuid import UUID

from app.core.config import settings
from app.platform import library, library_upload
from app.platform.capabilities.literature.run import run_literature_search
from app.platform.capabilities.literature.verification import add_candidate_to_library

logger = logging.getLogger(__name__)

DISABLED_MESSAGE = (
    "Descubrimiento desactivado: un administrador debe activar LITERATURE_DISCOVERY_ENABLED."
)

#: Explicación en claro por `error_kind` (cerrado); nunca el mensaje crudo de la base.
_ERROR_TEXT = {
    "timeout": "la base no respondió a tiempo",
    "rate_limited": "la base limitó las peticiones; reintenta más tarde",
    "http_error": "la base devolvió un error",
    "invalid_response": "la base devolvió una respuesta no válida",
    "network": "no se pudo conectar con la base",
    "blocked": "el destino está bloqueado por la política de salida",
    "missing_api_key": "se omite: falta la clave de API de la base",
    "unexpected": "error inesperado",
}


def is_enabled() -> bool:
    return bool(settings.LITERATURE_DISCOVERY_ENABLED)


def _base_view(report: Any, extra: Dict[str, int]) -> Dict[str, Any]:
    kind = report.error_kind or None
    return {
        "db": report.db, "status": report.status, "returned": report.count,
        "verified": extra.get("verified", 0), "error_kind": kind,
        "message": _ERROR_TEXT.get(kind or "", "error") if report.status != "ok" else None,
    }


async def discover_and_store(
    session: Any, project_id: UUID, query: str, sources: Iterable[str], *,
    user_id: Optional[UUID] = None, **inject: Any,
) -> Dict[str, Any]:
    """Ejecuta la búsqueda y guarda los candidatos verificados nuevos. `inject` es para tests."""
    if not is_enabled():
        return {"enabled": False, "message": DISABLED_MESSAGE, "new_candidates": 0,
                "already_in_library": 0, "sources": [], "candidates": [], "status": "disabled"}

    outcome = await run_literature_search(
        session, project_id, query, list(sources), user_id=user_id, **inject)
    verificacion, literatura = outcome.verification, outcome.literature

    nuevos, ya_estaban, vistos = [], 0, set()
    for v in verificacion.verified:
        # `already_in_library` viene de `library_dois_of` (este proyecto, cualquier estado).
        if v.already_in_library or v.doi in vistos:
            ya_estaban += 1
            continue
        vistos.add(v.doi)
        try:
            doc = await add_candidate_to_library(session, project_id, v, added_by=user_id)
        except library.DuplicateDocumentError:
            # Carrera con otra petición: el DOI apareció entre la comprobación y la escritura.
            await session.rollback()
            ya_estaban += 1
            continue
        nuevos.append(library_upload.document_view(doc))

    cuentas = verificacion.per_source
    if literatura.all_failed:
        mensaje = "Ninguna base respondió: no se guardó ningún candidato."
    elif nuevos:
        mensaje = f"{len(nuevos)} candidato(s) nuevo(s) verificado(s)."
    else:
        mensaje = "No hay candidatos verificados nuevos."
    return {
        "enabled": True, "status": outcome.status, "message": mensaje, "query": literatura.query,
        "new_candidates": len(nuevos), "already_in_library": ya_estaban,
        "unverified_discarded": len(verificacion.discarded),
        "sources": [_base_view(r, cuentas.get(r.db, {})) for r in literatura.reports],
        "candidates": nuevos, "search_id": str(outcome.log.id),
    }
