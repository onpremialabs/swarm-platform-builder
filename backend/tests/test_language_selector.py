"""Selector de idioma accesible (SPEC-041 / T29.10 / AC1, AC6, AC12).

Dos capas, como en T7.2/T7.3:

* **Estructural** (siempre corre): el selector está en la interfaz principal y en la
  revista pública, las dos entradas registran el catálogo `en`, las cadenas del
  selector están en es y en, y el lienzo vuelve a leer el catálogo al cambiar de
  idioma. La detección y la persistencia las cubre `i18n.test.mjs` (node).
* **De navegador** (se salta si no hay Chromium): conduce las pantallas reales con
  `frontend/a11y/language.jsx` — teclado, `<html lang>`, región `role=status`,
  persistencia tras recargar y repintado de menú, catálogo de agentes y botón
  Ejecutar sin recargar. Ahí `en` lleva el prefijo «[en] » (hoy es copia en español).
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FRONT = REPO / "frontend"
SRC = FRONT / "src"
I18N = SRC / "platform" / "i18n"
SELECTOR = SRC / "platform" / "components" / "ui" / "LanguageSelector.jsx"
BANCO = FRONT / "a11y"
PUERTO = 8909

CHROMIUM = os.environ.get("A11Y_CHROMIUM") or next(
    (
        str(p)
        for base in (Path("/opt/pw-browsers"), Path.home() / "AppData" / "Local" / "ms-playwright")
        for p in sorted(base.glob("chromium-*/chrome-*/chrome*"))
        if p.name in ("chrome", "chrome.exe")
    ),
    None,
)


# ── Capa estructural ─────────────────────────────────────────────────────────

def test_el_nucleo_i18n_pasa_con_node():
    if not shutil.which("node"):
        pytest.skip("no hay node")
    r = subprocess.run(["node", "--test", str(I18N / "i18n.test.mjs")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr


def test_selector_en_la_interfaz_principal_y_en_la_revista_publica():
    assert "<LanguageSelector />" in (SRC / "platform" / "pages" / "DashboardPage.jsx").read_text(encoding="utf-8")
    revista = SRC / "projects" / "alejandria-magazine" / "pages" / "MagazinePage.jsx"
    assert "<LanguageSelector />" in revista.read_text(encoding="utf-8")


@pytest.mark.parametrize("entrada", [
    SRC / "main.jsx",
    SRC / "projects" / "alejandria-magazine" / "public" / "main.jsx",
])
def test_las_dos_entradas_registran_el_catalogo_en(entrada):
    fuente = entrada.read_text(encoding="utf-8")
    assert "en: platformEn" in fuente
    assert "I18nProvider" in fuente
    assert "en" in (SRC / "projects" / "alejandria-magazine" / "i18n" / "index.js").read_text(encoding="utf-8")


def test_cadenas_del_selector_en_es_y_en():
    for idioma in ("es", "en"):
        bloque = json.loads((I18N / f"{idioma}.json").read_text(encoding="utf-8"))["language"]
        assert set(bloque) == {"label", "es", "en", "changed"}
    assert "{language}" in json.loads((I18N / "es.json").read_text(encoding="utf-8"))["language"]["changed"]


def test_el_selector_es_accesible():
    fuente = SELECTOR.read_text(encoding="utf-8")
    assert 'role="group"' in fuente and "aria-label={t('language.label')}" in fuente
    assert "aria-pressed" in fuente and 'role="status"' in fuente and 'aria-live="polite"' in fuente
    assert "<button" in fuente  # nativo: Tab / Enter / Espacio sin código extra
    assert re.search(r"lang=\{code\}", fuente)  # cada idioma se pronuncia en el suyo


def test_el_lienzo_relee_el_catalogo_al_cambiar_de_idioma():
    fuente = (SRC / "platform" / "pages" / "FlowDesignerPage.jsx").read_text(encoding="utf-8")
    assert "const { t, locale } = useTranslation();" in fuente
    assert "[locale]" in fuente


# ── Capa de navegador ────────────────────────────────────────────────────────

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


DEFS = [{"id": "uuid-1", "slug": "investigador", "name": "Investigador", "model": "m", "content": ""}]


def _abrir(navegador, ruta, locale="es-CL"):
    ctx = navegador.new_context(locale=locale)

    def api(route):
        url = route.request.url
        cuerpo = DEFS if "claude-defs" in url else ({"models": []} if "models" in url else [])
        route.fulfill(status=200, content_type="application/json", body=json.dumps(cuerpo))

    ctx.route("**/api/**", api)
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{PUERTO}/language.html?ruta={ruta}")
    pg.wait_for_selector(".lang-switch")
    return ctx, pg


def test_ac1_idioma_inicial_segun_el_navegador(navegador):
    esperado = {"en-US": "en", "es-CL": "es", "fr-FR": "es", "de-DE": "es"}
    for locale, lang in esperado.items():
        ctx, pg = _abrir(navegador, "/magazine", locale)
        assert pg.get_attribute("html", "lang") == lang, locale
        assert pg.get_attribute(f".lang-switch-btn[lang={lang}]", "aria-pressed") == "true"
        ctx.close()


def test_ac12_teclado_nombre_accesible_y_anuncio(navegador):
    ctx, pg = _abrir(navegador, "/magazine", "es-CL")
    assert pg.get_attribute(".lang-switch", "aria-label") == "Idioma"
    assert pg.text_content("[role=status]") == ""
    pg.focus(".lang-switch-btn[lang=es]")
    pg.keyboard.press("Tab")
    assert pg.evaluate("document.activeElement.getAttribute('lang')") == "en"
    # El foco es visible: el anillo global de `:focus-visible` se dibuja.
    assert pg.evaluate("getComputedStyle(document.activeElement).outlineStyle") == "solid"
    pg.keyboard.press("Enter")
    assert pg.get_attribute("html", "lang") == "en"
    assert pg.get_attribute(".lang-switch", "aria-label") == "[en] Idioma"
    assert "[en] Idioma cambiado a [en] English" in pg.text_content("[role=status]")
    assert pg.get_attribute("[role=status]", "aria-live") == "polite"
    # Espacio también activa y el foco no se pierde.
    pg.keyboard.press("Shift+Tab")
    pg.keyboard.press("Space")
    assert pg.get_attribute("html", "lang") == "es"
    assert pg.evaluate("document.activeElement.getAttribute('lang')") == "es"
    ctx.close()


def test_ac6_la_preferencia_persiste_al_recargar(navegador):
    ctx, pg = _abrir(navegador, "/magazine", "es-CL")
    pg.click(".lang-switch-btn[lang=en]")
    assert pg.evaluate("localStorage.getItem('ui.locale')") == "en"
    pg.reload()
    pg.wait_for_selector(".lang-switch")
    assert pg.get_attribute("html", "lang") == "en"
    ctx.close()


def test_ac6_el_cambio_repinta_menu_catalogo_y_ejecutar_sin_recargar(navegador):
    ctx, pg = _abrir(navegador, "/dashboard/flow-designer", "es-CL")
    pg.wait_for_selector(".palette-node")
    pg.evaluate("window.__sin_recarga = 1")
    antes = pg.inner_text("body")
    assert "Artículos" in antes and "Ejecutar" in antes and "[en]" not in antes
    nodo = pg.inner_text(".react-flow__node")
    pg.click(".lang-switch-btn[lang=en]")
    pg.wait_for_function("document.documentElement.lang === 'en'")
    assert pg.evaluate("window.__sin_recarga") == 1  # no hubo recarga
    despues = pg.inner_text("body")
    assert "[en] Artículos" in despues                     # menú del proyecto
    assert "[en] Ejecutar" in despues                      # botón Ejecutar
    # La paleta y los nodos se releen en un efecto: se espera al siguiente render.
    pg.wait_for_function("document.querySelector('.palette-node').innerText.includes('[en] Investigador')")
    pg.wait_for_function("document.querySelector('.react-flow__node').innerText.includes('[en] ')")
    assert nodo != pg.inner_text(".react-flow__node")
    pg.click(".lang-switch-btn[lang=es]")
    pg.wait_for_function("!document.querySelector('.react-flow__node').innerText.includes('[en]')")
    assert pg.inner_text(".react-flow__node") == nodo      # vuelta completa
    ctx.close()
