"""La referencia del sistema de diseño en la web de docs no se separa de los tokens reales.

`docs/public/design-system/index.html` carga `colors_and_type.css` y los logos con
rutas relativas. Son copias de `frontend/ds/` (la fuente de verdad, que importa la
aplicación), hechas por `scripts/sync_design_system_docs.py`. Si alguien cambia un
token y no resincroniza, la página documentaría valores que la app ya no usa.
"""
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "sync_design_system_docs.py"
PAGINA = ROOT / "docs" / "public" / "design-system" / "index.html"


def _modulo():
    spec = importlib.util.spec_from_file_location("sync_design_system_docs", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_la_copia_de_docs_coincide_con_frontend_ds():
    pendientes = _modulo().desfasados()
    assert not pendientes, (
        f"docs/public/design-system/ va atrás de frontend/ds/ en {pendientes}. "
        "Ejecuta: python scripts/sync_design_system_docs.py"
    )


def test_todo_lo_local_que_carga_la_pagina_esta_sincronizado():
    """Si la página empieza a cargar otro fichero local, el script debe copiarlo."""
    html = PAGINA.read_text(encoding="utf-8")
    # Solo etiquetas reales: los ejemplos de código de la página van escapados (&lt;link…).
    locales = {
        ref for ref in re.findall(r'<(?:link|script|img)\b[^>]*?\b(?:href|src)="([^"#:]+)"', html)
        if not ref.startswith(("/", "http"))
    }
    assert locales, "la página debería cargar al menos colors_and_type.css"
    faltan = locales - set(_modulo().FICHEROS)
    assert not faltan, f"la página carga {faltan} pero el script no lo sincroniza"
    for ref in locales:
        assert (PAGINA.parent / ref).exists(), f"falta {ref} junto a la página"


def test_la_pagina_no_redefine_tokens():
    """Los valores vienen del CSS copiado; la página solo los consume."""
    html = PAGINA.read_text(encoding="utf-8")
    estilos = "".join(re.findall(r"<style>(.*?)</style>", html, flags=re.S))
    redefinidos = re.findall(r"^\s*(--[a-z0-9-]+)\s*:", estilos, flags=re.M)
    assert not redefinidos, f"la página redefine tokens: {redefinidos}"
