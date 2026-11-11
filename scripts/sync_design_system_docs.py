"""Copia a la web de documentación lo que necesita la referencia del sistema de diseño.

La página `docs/public/design-system/index.html` no define ningún valor: carga
`colors_and_type.css` y los logos con rutas relativas. Su fuente de verdad sigue en
`frontend/ds/` (la importa la aplicación), así que aquí solo se copia, sin editar.

    python scripts/sync_design_system_docs.py          # copia lo que haya cambiado
    python scripts/sync_design_system_docs.py --check  # sale con 1 si la copia va atrás

Ejecútalo después de tocar un token o un logo en `frontend/ds/`. Si no, el test
`backend/tests/test_design_system_docs.py` falla.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGEN = ROOT / "frontend" / "ds"
DESTINO = ROOT / "docs" / "public" / "design-system"

# Lo que la página referencia con rutas relativas. Si la página empieza a cargar algo
# más de frontend/ds/, se añade aquí.
FICHEROS = (
    "colors_and_type.css",
    "assets/logomark.svg",
    "assets/wordmark.svg",
)


def _contenido(path: Path) -> bytes:
    # Git puede dejar CRLF en Windows y LF en la CI: se compara sin saltos de línea.
    return path.read_bytes().replace(b"\r\n", b"\n")


def desfasados() -> list[str]:
    """Ficheros cuya copia en docs falta o no coincide con frontend/ds."""
    return [
        rel for rel in FICHEROS
        if not (DESTINO / rel).exists() or _contenido(DESTINO / rel) != _contenido(ORIGEN / rel)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="no copia; falla si la copia va atrás")
    args = parser.parse_args(argv)

    pendientes = desfasados()
    if args.check:
        if pendientes:
            print("[ERROR] la copia de docs/public/design-system/ va atrás de frontend/ds/:")
            for rel in pendientes:
                print(f"  - {rel}")
            print("Ejecuta: python scripts/sync_design_system_docs.py")
            return 1
        print(f"[OK] docs/public/design-system/ al día ({len(FICHEROS)} ficheros).")
        return 0

    for rel in pendientes:
        destino = DESTINO / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(_contenido(ORIGEN / rel))
        print(f"copiado {rel}")
    if not pendientes:
        print("Nada que copiar: ya estaba al día.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
