"""Infraestructura i18n del frontend (SPEC-041 / T29.6 / AC6, AC8)."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[2] / "frontend"
I18N = FRONT / "src" / "platform" / "i18n"


@pytest.mark.skipif(shutil.which("node") is None, reason="node no disponible")
def test_nucleo_i18n_con_node():
    r = subprocess.run(["node", "--test", str(I18N / "i18n.test.mjs")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr


def test_el_proyecto_se_registra_desde_main_sin_que_el_builder_lo_importe():
    main = (FRONT / "src" / "main.jsx").read_text(encoding="utf-8")
    assert "registerMessages(MAGAZINE_NS" in main
    for f in I18N.rglob("*"):
        if f.suffix in (".js", ".jsx"):
            assert not re.search(r"""from\s+['"][^'"]*projects/""", f.read_text(encoding="utf-8")), f
