"""Controles de CI de i18n (SPEC-041 / T29.13 / AC7 + AC11).

`scripts/check_i18n.py` corre aquí, dentro del job de pytest de la CI. Los tests
de abajo lo ejecutan contra catálogos y `.jsx` de prueba: un control que solo se
ve pasar con los catálogos vacíos de hoy no demuestra que sepa fallar.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parents[2]
SCRIPT = REPO_DIR / "scripts" / "check_i18n.py"


@pytest.fixture(scope="module")
def chk():
    spec = importlib.util.spec_from_file_location("check_i18n", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_i18n"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_el_repo_pasa_los_controles():
    r = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True,
        encoding="utf-8", cwd=str(REPO_DIR),
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_solo_stdlib():
    import re
    fuente = SCRIPT.read_text(encoding="utf-8")
    mods = set(re.findall(r"^\s*(?:import|from)\s+([a-zA-Z_]\w*)", fuente, re.M))
    assert not (mods - set(sys.stdlib_module_names) - {"__future__"})


def test_los_catalogos_vacios_pasan_de_forma_vacia(chk):
    cats = {"platform": {"es": {}, "en": {}}}
    assert chk.comprobar_paridad(cats, set(), []) == []


def test_clave_solo_en_un_idioma_falla(chk):
    cats = {"platform": {"es": {"a.b": "Hola"}, "en": {}}}
    fallos = chk.comprobar_paridad(cats, {"a.b"}, [])
    assert any("a.b" in f and "falta en 'en'" in f for f in fallos)


def test_clave_sin_usar_falla(chk):
    cats = {"platform": {"es": {"a": "x"}, "en": {"a": "x"}}}
    assert any("no se usa" in f for f in chk.comprobar_paridad(cats, set(), []))
    assert chk.comprobar_paridad(cats, {"platform:a"}, []) == []
    assert chk.comprobar_paridad(cats, set(), ["a"]) == []  # prefijo dinamico


def test_variable_de_interpolacion_ausente_falla(chk):
    cats = {"platform": {"es": {"a": "Hola {nombre}"}, "en": {"a": "Hello"}}}
    fallos = chk.comprobar_paridad(cats, {"a"}, [])
    assert any("variables" in f and "nombre" in f for f in fallos)


def test_plurales_distintos_por_idioma_son_la_misma_clave(chk):
    cats = {"platform": {
        "es": {"n_one": "{count} cosa", "n_many": "{count} cosas", "n_other": "{count} cosas"},
        "en": {"n_one": "{count} thing", "n_other": "{count} things"},
    }}
    assert chk.comprobar_paridad(cats, {"n"}, []) == []


def test_cargar_catalogos_lee_es_y_en(chk, tmp_path):
    d = tmp_path / "x" / "i18n"
    d.mkdir(parents=True)
    (d / "es.json").write_text(json.dumps({"a": {"b": "hola"}}), encoding="utf-8")
    cats = chk.cargar_catalogos(tmp_path)
    assert cats["platform"]["es"] == {"a.b": "hola"} and cats["platform"]["en"] == {}


# ── Literales ────────────────────────────────────────────────────────────────

JSX = """\
export default function X() {
  // <p>comentario ignorado</p>
  return (
    <div title="Titulo fijo" data-x="no">
      <h1>
        Hola mundo
      </h1>
      <p>{t('a.b')}</p>
      <span>{'Otro texto'}</span>
      <b>{count}</b>
    </div>
  );
}
"""


def test_detecta_literales_con_su_linea(chk):
    lits = dict((t, n) for n, t in chk.literales_de(JSX))
    assert lits == {"Titulo fijo": 4, "Hola mundo": 6, "Otro texto": 9}


def test_literal_nuevo_falla_con_archivo_y_linea(chk, tmp_path):
    (tmp_path / "Pantalla.jsx").write_text(JSX, encoding="utf-8")
    exc = {"textos": {}, "ficheros": {}}
    actuales = chk.literales_actuales(tmp_path, exc)
    base = chk._baseline_de(actuales)
    assert chk.comparar_literales(actuales, base) == ([], [])

    (tmp_path / "Pantalla.jsx").write_text(
        JSX.replace("<b>{count}</b>", "<b>{count}</b>\n      <i>Texto nuevo</i>"), encoding="utf-8"
    )
    nuevos, obsoletos = chk.comparar_literales(chk.literales_actuales(tmp_path, exc), base)
    assert obsoletos == []
    assert len(nuevos) == 1 and "Pantalla.jsx:11" in nuevos[0] and "Texto nuevo" in nuevos[0]


def test_la_linea_base_solo_baja(chk, tmp_path):
    (tmp_path / "P.jsx").write_text(JSX, encoding="utf-8")
    exc = {"textos": {}, "ficheros": {}}
    base = chk._baseline_de(chk.literales_actuales(tmp_path, exc))
    (tmp_path / "P.jsx").write_text(JSX.replace("Hola mundo", "{t('x')}"), encoding="utf-8")
    nuevos, obsoletos = chk.comparar_literales(chk.literales_actuales(tmp_path, exc), base)
    assert nuevos == [] and len(obsoletos) == 1  # hay que regenerar para bajar


def test_un_literal_repetido_cuenta_cada_vez(chk, tmp_path):
    (tmp_path / "P.jsx").write_text("<a>Guardar</a>\n", encoding="utf-8")
    exc = {"textos": {}, "ficheros": {}}
    base = chk._baseline_de(chk.literales_actuales(tmp_path, exc))
    (tmp_path / "P.jsx").write_text("<a>Guardar</a>\n<b>Guardar</b>\n", encoding="utf-8")
    nuevos, _ = chk.comparar_literales(chk.literales_actuales(tmp_path, exc), base)
    assert len(nuevos) == 1 and "P.jsx:2" in nuevos[0]


def test_excepciones_por_texto_y_por_fichero(chk, tmp_path):
    (tmp_path / "P.jsx").write_text("<a>Marca</a>\n", encoding="utf-8")
    (tmp_path / "Q.jsx").write_text("<a>Otra cosa</a>\n", encoding="utf-8")
    exc = {"textos": {"Marca": "marca"}, "ficheros": {"Q.jsx": "motivo"}}
    assert chk.literales_actuales(tmp_path, exc) == {}


def test_la_linea_base_del_repo_es_coherente(chk):
    base = chk.cargar_baseline()
    datos = json.loads(chk.BASELINE.read_text(encoding="utf-8"))
    assert datos["total"] == sum(sum(v.values()) for v in base.values())
    assert chk.comparar_literales(chk.literales_actuales(), base) == ([], [])
