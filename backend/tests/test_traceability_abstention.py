"""Fix de T22.12 (#628) — TraceabilityPage en vivo muestra la abstención como detenida.

Banco de navegador (se salta si no hay Chromium, como `test_language_selector.py`): monta la
pantalla real «Trazabilidad y observabilidad» con un `EventSource` guionizado, le inyecta la
secuencia que emite el backend cuando el Investigador se abstiene
(`agent_start, log, agent_end, abstained, done{outcome:'abstained'}`) y comprueba que no
dice «Completado» / «Pipeline completado» ni ofrece «Ver artículo», que sí muestra el aviso
con k/N y los pasos «No ejecutado». También cubre el corte del stream tras `abstained` sin
`done`, y que una ejecución normal sigue terminando como completada.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FRONT = REPO / "frontend"
BANCO = FRONT / "a11y"
PUERTO = 8911

CHROMIUM = os.environ.get("A11Y_CHROMIUM") or next(
    (
        str(p)
        for base in (Path("/opt/pw-browsers"), Path.home() / "AppData" / "Local" / "ms-playwright")
        for p in sorted(base.glob("chromium-*/chrome-*/chrome*"))
        if p.name in ("chrome", "chrome.exe")
    ),
    None,
)

# EventSource guionizado: el test lo empuja con window.__emitir(evento) / window.__cortar().
FALSO_EVENTSOURCE = """
window.EventSource = class {
  constructor(url) { this.url = url; this.closed = false; window.__es = this; }
  close() { this.closed = true; }
};
window.__emitir = (ev) => window.__es.onmessage({ data: JSON.stringify(ev) });
window.__cortar = () => window.__es.onerror(new Event('error'));
"""

ABSTENCION = {
    "message": "Sube documentos o amplía la búsqueda para llegar a 3 fuentes verificadas.",
    "verified_sources": 1,
    "min_sources": 3,
}


@pytest.fixture(scope="module")
def navegador():
    playwright = pytest.importorskip("playwright.sync_api", reason="playwright no instalado")
    if not CHROMIUM or not Path(CHROMIUM).exists():
        pytest.skip("no hay Chromium; exporta A11Y_CHROMIUM con la ruta del binario")
    npx = shutil.which("npx")
    if not npx:
        pytest.skip("no hay npx para construir el banco de pruebas")
    construccion = subprocess.run(
        [npx, "vite", "build", "--config", "a11y/vite.config.js"],
        cwd=str(FRONT), capture_output=True, text=True,
    )
    assert construccion.returncode == 0, construccion.stdout + construccion.stderr
    servidor = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PUERTO), "--bind", "127.0.0.1"],
        cwd=str(BANCO / "dist"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    with playwright.sync_playwright() as p:
        nav = p.chromium.launch(executable_path=CHROMIUM)
        yield nav
        nav.close()
    servidor.terminate()
    servidor.wait(timeout=10)


def _abrir(navegador):
    ctx = navegador.new_context(locale="es-CL")
    ctx.add_init_script(FALSO_EVENTSOURCE)

    def api(route):
        url = route.request.url
        cuerpo = {"ticket": "t-1"} if "stream-ticket" in url else {}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(cuerpo))

    ctx.route("**/api/**", api)
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{PUERTO}/trace.html")
    pg.wait_for_function("!!window.__es")
    return ctx, pg


def _emitir(pg, *eventos):
    for ev in eventos:
        pg.evaluate("(e) => window.__emitir(e)", ev)


def _tramo_abstencion(pg):
    _emitir(
        pg,
        {"type": "agent_start", "agent": "investigador"},
        {"type": "log", "message": "Buscando fuentes", "level": "info"},
        {"type": "agent_end", "agent": "investigador", "output": ""},
        {"type": "abstained", "agent": "investigador", **ABSTENCION},
    )


def _texto(pg):
    return pg.inner_text("body")


def test_la_abstencion_no_se_presenta_como_completada(navegador):
    ctx, pg = _abrir(navegador)
    _tramo_abstencion(pg)
    _emitir(pg, {"type": "done", "outcome": "abstained", **ABSTENCION})
    pg.wait_for_selector("[role=alert]")

    texto = _texto(pg)
    for prohibido in ("Pipeline completado", "Ver artículo"):
        assert prohibido not in texto, prohibido
    # Ninguna insignia (paso, cabecera, métricas) dice «Completado».
    assert pg.locator(".badge", has_text="Completado").count() == 0

    aviso = pg.inner_text("[role=alert]")
    assert "El Investigador se abstuvo" in aviso and "1/3" in aviso
    assert ABSTENCION["message"] in aviso
    assert "Detenida por abstención" in pg.text_content("body")
    assert pg.text_content(".trace-step-card:first-child .badge") == "Se abstuvo"
    otros = pg.locator(".trace-step-card:not(:first-child) .badge").all_text_contents()
    assert otros == ["No ejecutado"] * 4
    assert pg.locator(".trace-step-card .badge", has_text="Pendiente").count() == 0
    assert pg.locator("button", has_text="Ver borrador").count() == 1
    assert pg.locator("button", has_text="Volver al diseñador").count() == 2  # cabecera + acciones
    ctx.close()


def test_si_el_stream_se_corta_tras_abstained_sin_done(navegador):
    ctx, pg = _abrir(navegador)
    _tramo_abstencion(pg)
    pg.evaluate("window.__cortar()")
    pg.wait_for_selector("[role=alert]")
    pg.wait_for_function("document.querySelectorAll('.trace-step-card .badge').length === 5")
    pg.wait_for_function("[...document.querySelectorAll('.trace-step-card .badge')].slice(1).every(b => b.textContent === 'No ejecutado')")
    texto = _texto(pg)
    assert "Pipeline completado" not in texto and "Ver artículo" not in texto
    assert pg.locator("button", has_text="Ver borrador").count() == 1
    ctx.close()


def test_una_ejecucion_normal_sigue_completandose(navegador):
    ctx, pg = _abrir(navegador)
    _emitir(
        pg,
        {"type": "agent_start", "agent": "investigador"},
        {"type": "agent_end", "agent": "investigador", "output": ""},
        {"type": "done"},
    )
    pg.wait_for_selector("button:has-text('Ver artículo')")
    assert pg.locator("[role=alert]").count() == 0
    assert "Completado" in pg.text_content(".trace-step-card:first-child")
    ctx.close()
