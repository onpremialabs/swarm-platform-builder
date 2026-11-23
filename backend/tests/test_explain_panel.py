"""Panel «Por qué este resultado» en un navegador (SPEC-014 / T9.2 / AC2).

AC2 pide dos cosas y esta es la segunda: que **la interfaz** muestre las fuentes,
el score y las decisiones por paso. La primera —que el endpoint devuelva la traza
completa— vive en `test_explain_endpoint.py`.

Se conduce el componente real con Chromium, como en T7.2 y T7.3, porque lo que
puede fallar aquí no se lee en el código:

* que el detalle de un paso **se abra y se cierre** de verdad — `hidden` lo aplica
  el navegador, y un `aria-expanded` que no corresponde con lo visible es peor que
  no tenerlo;
* que los **dos scores** que conviven en el panel no se lean como el mismo número:
  el del revisor es una aprobación sobre 100 y el de una fuente una similitud
  coseno sobre 1;
* y que un **fallo de carga no se disfrace de «no hay traza»**, que es exactamente
  la mentira que T7.3 fue a arreglar y que este panel podría repetir.

Sin Chromium los tests de navegador se saltan; los estructurales siguen corriendo.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = ROOT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

FRONT = REPO_DIR / "frontend"
FUENTE = FRONT / "src"
PANEL = FUENTE / "platform" / "components" / "explain" / "ExplainPanel.jsx"
BANCO = FRONT / "a11y"
PAGINA_DETALLE = FUENTE / "projects" / "alejandria-magazine" / "pages" / "ArticleDetailPage.jsx"
CLIENTE_API = FUENTE / "platform" / "api" / "agents.js"

CHROMIUM = os.environ.get("A11Y_CHROMIUM") or next(
    (
        str(p)
        for p in sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"))
    ),
    None,
)


# ── Capa estructural ─────────────────────────────────────────────────────────

def test_el_panel_vive_en_la_plataforma_y_no_en_el_proyecto():
    """La explicabilidad es del motor: cualquier proyecto que ejecute un pipeline
    tiene pasos, fuentes y decisiones. Si el panel viviera en el proyecto, el
    siguiente tendría que reescribirlo (T8.6)."""
    assert PANEL.is_file()
    fuente = PANEL.read_text(encoding="utf-8")
    assert "projects/" not in fuente, "el panel no puede importar de un proyecto"


def test_el_panel_pregunta_al_registro_como_se_llaman_los_agentes():
    """Lo único del proyecto que el panel necesita —nombre, color, icono— se
    pregunta; no se importa. Es la inversión de dependencia de T8.6."""
    assert "agentCatalog" in PANEL.read_text(encoding="utf-8")


def test_la_pagina_de_detalle_monta_el_panel():
    """AC2 dice «la UI muestra un panel»: existir no basta, tiene que estar puesto."""
    fuente = PAGINA_DETALLE.read_text(encoding="utf-8")
    assert "ExplainPanel" in fuente
    assert "articleId={id}" in fuente


def test_el_cliente_pide_la_traza_al_endpoint_de_la_spec():
    fuente = CLIENTE_API.read_text(encoding="utf-8")
    assert "/explain" in fuente and "getExplain" in fuente


# ── Capa de navegador ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def pagina():
    playwright = pytest.importorskip("playwright.sync_api", reason="playwright no instalado")
    if not CHROMIUM or not Path(CHROMIUM).exists():
        pytest.skip("no hay Chromium; exporta A11Y_CHROMIUM con la ruta del binario")
    if not shutil.which("npx"):
        pytest.skip("no hay npx para construir el banco de pruebas")

    construccion = subprocess.run(
        ["npx", "vite", "build", "--config", "a11y/vite.config.js"],
        cwd=str(FRONT), capture_output=True, text=True,
    )
    assert construccion.returncode == 0, construccion.stdout + construccion.stderr

    servidor = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8909", "--bind", "127.0.0.1"],
        cwd=str(BANCO / "dist"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    with playwright.sync_playwright() as p:
        navegador = p.chromium.launch(executable_path=CHROMIUM)
        pg = navegador.new_page()
        for _ in range(50):
            try:
                pg.goto("http://127.0.0.1:8909/explain.html")
                break
            except Exception:
                pg.wait_for_timeout(100)
        yield pg
        navegador.close()
    servidor.terminate()
    servidor.wait(timeout=10)


@pytest.fixture
def banco(pagina):
    pagina.goto("http://127.0.0.1:8909/explain.html")
    pagina.wait_for_selector("#explain-titulo")
    return pagina


def test_navegador_se_pinta_un_paso_por_agente_con_su_nombre(banco):
    """Y con el nombre del catálogo, no con el identificador crudo."""
    banco.wait_for_selector("[aria-controls^=explain-paso-]")
    etiquetas = banco.eval_on_selector_all(
        "[aria-controls^=explain-paso-]", "els => els.map(e => e.textContent)"
    )
    assert len(etiquetas) == 2
    assert "Investigador" in etiquetas[0]
    assert "Revisor" in etiquetas[1]


def test_navegador_el_detalle_se_abre_y_se_cierra(banco):
    """`aria-expanded` y lo que se ve tienen que decir lo mismo."""
    boton = banco.query_selector("[aria-controls^=explain-paso-]")
    detalle = f"#{boton.get_attribute('aria-controls')}"

    assert boton.get_attribute("aria-expanded") == "false"
    assert not banco.is_visible(detalle)

    boton.click()
    banco.wait_for_selector(detalle, state="visible")
    assert boton.get_attribute("aria-expanded") == "true"

    boton.click()
    banco.wait_for_selector(detalle, state="hidden")
    assert boton.get_attribute("aria-expanded") == "false"


def test_navegador_el_detalle_ensena_modelo_parametros_y_lo_recuperado(banco):
    """Las tres cosas que AC1 persistió y AC2 tiene que dejar ver."""
    boton = banco.query_selector("[aria-controls^=explain-paso-]")
    detalle = f"#{boton.get_attribute('aria-controls')}"
    boton.click()
    banco.wait_for_selector(detalle, state="visible")

    texto = banco.text_content(detalle)
    assert "qwen2.5:3b" in texto
    assert "temperature" in texto
    assert "Blanqueamiento de corales" in texto
    assert "Con qué entró" in texto


def test_navegador_la_decision_del_revisor_se_lee_con_su_porque(banco):
    botones = banco.query_selector_all("[aria-controls^=explain-paso-]")
    revisor = botones[1]
    detalle = f"#{revisor.get_attribute('aria-controls')}"
    revisor.click()
    banco.wait_for_selector(detalle, state="visible")

    texto = banco.text_content(detalle)
    assert "Score de aprobación" in texto and "82/100" in texto
    assert "Coherencia" in texto
    # El rationale es lo que convierte un número en una explicación.
    assert "Falta metodología" in texto


def test_navegador_los_dos_scores_no_se_leen_como_el_mismo_numero(banco):
    """El del revisor es una aprobación sobre 100; el de una fuente, una similitud
    coseno sobre 1. Pintados igual, un 0,91 y un 91 se confunden."""
    # `Intl` separa el número del % con un espacio duro (U+00A0): se lee igual.
    pagina_texto = banco.text_content("#zona").replace(" ", " ")
    assert "82/100" in pagina_texto
    assert "91 %" in pagina_texto and "similitud" in pagina_texto
    assert "0.91" not in pagina_texto and "0,91" not in pagina_texto


def test_navegador_la_vuelta_del_bucle_se_indica(banco):
    """El mismo agente aparece varias veces cuando hay bucle de revisión: sin
    decir la vuelta, la línea de tiempo parece que se repite sin motivo."""
    botones = banco.eval_on_selector_all(
        "[aria-controls^=explain-paso-]", "els => els.map(e => e.textContent)"
    )
    assert any("vuelta 2" in t for t in botones)


def test_navegador_se_avisa_de_que_hay_mas_ejecuciones(banco):
    """Lo que se está leyendo lo produjo la última ejecución, no la suma."""
    texto = banco.text_content("#zona")
    assert "2 veces" in texto
    assert banco.query_selector("text=Ver las 2 ejecuciones") is not None


def test_navegador_el_error_de_carga_no_se_disfraza_de_vacio(banco):
    """El fallo de T7.3, que este panel podría repetir: decirle a alguien que no
    hay traza cuando lo que pasa es que no se ha podido preguntar."""
    banco.click("#modo-vacio")
    banco.wait_for_selector("#zona .empty-state")
    assert "Sin traza que explicar" in banco.text_content("#zona")
    assert banco.eval_on_selector_all("#zona [role=alert]", "e => e.length") == 0

    banco.click("#modo-error")
    banco.wait_for_selector("#zona [role=alert]")
    assert "Sin traza que explicar" not in banco.text_content("#zona")
    # Y con salida: sin reintento la única opción es recargar la página entera.
    assert banco.query_selector("#zona [role=alert] button") is not None


def test_navegador_un_cambio_de_alcance_que_falla_no_ensena_el_otro(banco):
    """`AsyncState` mantiene los datos cuando falla una recarga, y para un refresco
    está bien. Pero al cambiar de alcance lo que queda en pantalla es la respuesta
    a **otra** pregunta, y darla por buena es justo la mentira que un panel de
    explicabilidad no se puede permitir."""
    banco.wait_for_selector("[aria-controls^=explain-paso-]")
    assert banco.eval_on_selector_all("[aria-controls^=explain-paso-]", "e => e.length") == 2

    # Falla la recarga del mismo alcance: los datos siguen, que es lo correcto.
    banco.click("#modo-error")
    banco.wait_for_timeout(200)
    assert banco.eval_on_selector_all("#zona [role=alert]", "e => e.length") == 0
    assert banco.eval_on_selector_all("[aria-controls^=explain-paso-]", "e => e.length") == 2

    # Pero al pedir *otro* alcance y fallar, no se pueden seguir enseñando estos.
    banco.click("text=Ver las 2 ejecuciones")
    banco.wait_for_selector("#zona [role=alert]")
    assert banco.eval_on_selector_all("[aria-controls^=explain-paso-]", "e => e.length") == 0
