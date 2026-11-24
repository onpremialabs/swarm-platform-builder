#!/usr/bin/env python3
"""Reclasifica por `section` los fragmentos indexados antes de AC15 (SPEC-034 / T22.16 / AC17).

Antes de T22.14 los fragmentos no llevaban `section`, asi que las listas de
referencias seguian recuperandose como evidencia. Este script les pone la etiqueta
(solo el campo `section` del payload): no crea, borra ni re-embebe puntos, no toca
`doc_id`, DOI ni el estado de curacion, y no reescribe los mapas de citas de las
ejecuciones guardadas. Es idempotente (solo toca fragmentos sin `section`).

Aislamiento: se procesa proyecto a proyecto y las colecciones se enumeran con el
`ProjectContext` del proyecto; el nombre nunca se compone a mano.

Uso:
    python scripts/reindex_library.py                       # simulacro, todos los proyectos
    python scripts/reindex_library.py --apply
    python scripts/reindex_library.py --project <uuid> --apply
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models import ProjectModel  # noqa: E402
from app.platform.capabilities.reindex import reindexar_proyecto  # noqa: E402
from app.platform.project_context import ProjectContext  # noqa: E402


async def _proyectos(solo: UUID | None) -> list[ProjectContext]:
    try:
        async with AsyncSessionLocal() as session:
            filas = (await session.execute(select(ProjectModel))).scalars().all()
    except Exception as error:
        raise SystemExit(
            f"No se pudo leer la base de datos ({error.__class__.__name__}). "
            "Comprueba DATABASE_URL y que la aplicacion haya arrancado al menos una vez."
        ) from error
    return [
        ProjectContext(project_id=p.id, name=p.name, is_system=bool(p.is_system))
        for p in filas if solo is None or p.id == solo
    ]


async def reindexar(aplicar: bool, solo: UUID | None) -> int:
    proyectos = await _proyectos(solo)
    if not proyectos:
        print("No hay proyectos que reindexar.")
        return 1 if solo else 0
    print(f"Modo: {'APLICAR' if aplicar else 'simulacro'}\n")
    for ctx in proyectos:
        print(f"Proyecto {ctx.name} ({ctx.project_id})")
        try:
            resumenes = await reindexar_proyecto(
                ctx, settings.QDRANT_URL, aplicar, settings.QDRANT_API_KEY or None)
        except Exception as error:
            print(f"  [error] {error.__class__.__name__}: {error}")
            return 1
        for r in resumenes:
            detalle = ", ".join(f"{k}={v}" for k, v in sorted(r.reclasificados.items())) or "nada que hacer"
            print(f"  [{r.backend}] {r.coleccion}: {r.fragmentos} fragmento(s), "
                  f"{r.sin_seccion} sin section -> {detalle}")
    if not aplicar:
        print("\nSimulacro (no se escribio nada). Repite con --apply para escribir.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="Escribe (por defecto: simulacro)")
    parser.add_argument("--project", type=UUID, default=None, help="Solo este proyecto")
    args = parser.parse_args()
    return asyncio.run(reindexar(args.apply, args.project))


if __name__ == "__main__":
    sys.exit(main())
