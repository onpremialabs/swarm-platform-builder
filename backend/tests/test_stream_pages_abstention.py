"""SPEC-034 / AC13 — toda pantalla que abre el stream del pipeline interpreta la abstención.

Regresión de T22.12 (#628): se arregló ExecutionPage y no TraceabilityPage, que tiene su
propio manejador SSE; esa pantalla mostraba «Pipeline completado» y «Ver artículo» para
una ejecución que el Investigador había detenido. El test es estructural y barre **todo**
el código del proyecto: si alguien añade una tercera pantalla con `new EventSource(...)`
sin tratar `abstained` y el `outcome` de `done`, falla aquí y no en producción.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"
PROYECTO = SRC / "projects" / "alejandria-magazine"


def _fuentes_con_stream() -> list[Path]:
    return sorted(
        p for p in SRC.rglob("*.jsx") if "new EventSource(" in p.read_text(encoding="utf-8")
    )


def test_se_detectan_las_pantallas_con_stream():
    nombres = {p.name for p in _fuentes_con_stream()}
    assert {"ExecutionPage.jsx", "TraceabilityPage.jsx"} <= nombres


@pytest.mark.parametrize("pagina", _fuentes_con_stream(), ids=lambda p: p.name)
def test_la_pantalla_con_stream_trata_la_abstencion(pagina: Path):
    texto = pagina.read_text(encoding="utf-8")
    # El evento `abstained` y el `outcome` del cierre `done`: por el módulo compartido o a mano.
    evento = "isAbstainedEvent(" in texto or re.search(r"type === 'abstained'", texto)
    cierre = "isAbstainedDone(" in texto or re.search(r"\.outcome\b", texto)
    assert evento, f"{pagina.name} abre un EventSource y no maneja el evento `abstained`"
    assert cierre, f"{pagina.name} abre un EventSource y su `done` ignora `outcome`"
    # Y lo refleja: pasos sin ejecutar, estado propio y nada de «completado» tras abstenerse.
    assert "not_run" in texto or "settleUnrunSteps" in texto, f"{pagina.name}: pasos sin ejecutar"
    assert re.search(r"setAbstained\(true\)", texto), f"{pagina.name}: sin estado de abstención"
    assert "!abstained" in texto, f"{pagina.name}: «Ver artículo»/«Completo» siguen activos tras abstenerse"
    assert "role=\"alert\"" in texto or "'alert'" in texto, f"{pagina.name}: el aviso no es un alert"


def test_el_proyecto_no_tiene_streams_fuera_de_las_paginas():
    for p in _fuentes_con_stream():
        assert PROYECTO in p.parents and p.parent.name == "pages", p


@pytest.mark.skipif(shutil.which("node") is None, reason="node no disponible")
def test_el_modulo_compartido_con_node():
    r = subprocess.run(
        ["node", "--test", str(PROYECTO / "pipelineEvents.test.mjs")],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr
