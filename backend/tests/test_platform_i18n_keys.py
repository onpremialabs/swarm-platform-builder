"""Las cadenas del builder viven en el catálogo (SPEC-041 / T29.7 / AC6).

No hay tests de componente, así que una clave mal escrita solo se vería en el
navegador: `t('flows.titel')` devuelve la propia clave y la pantalla enseña
«flows.titel». Estos tests lo comprueban sobre el código fuente de
`frontend/src/platform/`:

* toda clave que el código pide existe en `es.json`;
* toda variable `{x}` del mensaje se pasa en la llamada (y al revés no sobra);
* el builder ya no deja literales en la línea base de `check_i18n.py`.

El control de paridad es/en y de claves sin usar es `scripts/check_i18n.py`
(`test_i18n_checks.py`); aquí se mira el otro sentido: código -> catálogo.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PLATFORM = REPO / "frontend" / "src" / "platform"
I18N = PLATFORM / "i18n"
SUFIJOS = ("zero", "one", "two", "few", "many", "other")


def _aplanar(obj, prefijo=""):
    out = {}
    for k, v in obj.items():
        clave = f"{prefijo}.{k}" if prefijo else k
        if isinstance(v, dict):
            out.update(_aplanar(v, clave))
        else:
            out[clave] = str(v)
    return out


@pytest.fixture(scope="module")
def catalogo():
    return _aplanar(json.loads((I18N / "es.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def espacios(catalogo):
    return {k.split(".", 1)[0] for k in catalogo}


def _fuentes():
    for f in sorted(PLATFORM.rglob("*")):
        if f.suffix in (".js", ".jsx") and ".test." not in f.name and I18N not in f.parents:
            yield f, f.read_text(encoding="utf-8")


def _formas(catalogo, clave):
    """Mensajes que puede dar `clave`: la propia o sus formas plurales."""
    if clave in catalogo:
        return [catalogo[clave]]
    return [catalogo[f"{clave}_{s}"] for s in SUFIJOS if f"{clave}_{s}" in catalogo]


def _variables(mensajes):
    return {v for m in mensajes for v in re.findall(r"\{(\w+)\}", m)}


# ── 1. Toda clave pedida existe ──────────────────────────────────────────────

LLAMADA = re.compile(r"""(?<![\w.])(?:t|translate)\(\s*(['"])([^'"]+)\1""")
I18NKEY = re.compile(r"""i18nKey=(?:"([^"]+)"|\{'([^']+)'\})""")
PROPIEDAD_KEY = re.compile(r"""\b\w*Key\s*[:=]\s*(?:'([^']+)'|"([^"]+)")""")


def _claves_pedidas(texto, espacios):
    """(clave, línea) de cada clave literal que el código pide al catálogo."""
    vistas = []
    for rx in (LLAMADA, I18NKEY, PROPIEDAD_KEY):
        for m in rx.finditer(texto):
            clave = next(g for g in m.groups() if g and g not in ("'", '"'))
            vistas.append((clave, texto.count("\n", 0, m.start()) + 1))
    # Claves guardadas en datos (`USE_CASE_LABEL = { x: 'dashboard.useCase.x' }`):
    # cualquier cadena que empiece por un espacio de nombres del catálogo.
    patron = r"""['"]((?:%s)\.[\w.]+)['"]""" % "|".join(sorted(espacios))
    for m in re.finditer(patron, texto):
        vistas.append((m.group(1), texto.count("\n", 0, m.start()) + 1))
    return vistas


def test_toda_clave_que_el_builder_pide_existe_en_es_json(catalogo, espacios):
    faltan = []
    total = 0
    for f, texto in _fuentes():
        for clave, linea in _claves_pedidas(texto, espacios):
            total += 1
            if not _formas(catalogo, clave):
                faltan.append(f"{f.relative_to(REPO).as_posix()}:{linea}  '{clave}'")
    assert total > 100, "el escaneo no encuentra claves: ¿cambió la forma de llamar a t()?"
    assert not faltan, "claves que no existen en es.json:\n  " + "\n  ".join(faltan)


# ── 2. Las variables del mensaje se pasan ────────────────────────────────────

def _objeto_literal(texto, desde):
    """Texto del `{...}` que empieza en `desde` (equilibrando llaves), o None."""
    if desde >= len(texto) or texto[desde] != "{":
        return None
    profundidad, i, comilla = 0, desde, None
    while i < len(texto):
        c = texto[i]
        if comilla:
            if c == "\\":
                i += 1
            elif c == comilla:
                comilla = None
        elif c in "'\"`":
            comilla = c
        elif c in "{([":
            profundidad += 1
        elif c in "})]":
            profundidad -= 1
            if profundidad == 0:
                return texto[desde + 1:i]
        i += 1
    return None


def _claves_del_objeto(cuerpo):
    """Nombres de propiedad de un objeto literal (`a`, `b: x`, `'c': y`)."""
    nombres, profundidad, actual, comilla = [], 0, "", None
    for c in cuerpo + ",":
        if comilla:
            actual += c
            if c == comilla:
                comilla = None
            continue
        if c in "'\"`":
            comilla = c
        elif c in "{([":
            profundidad += 1
        elif c in "})]":
            profundidad -= 1
        if c == "," and profundidad == 0:
            m = re.match(r"\s*['\"]?(\w+)['\"]?\s*(?::|$)", actual)
            if m:
                nombres.append(m.group(1))
            actual = ""
        else:
            actual += c
    return set(nombres)


LLAMADA_CON_VARS = re.compile(r"""(?<![\w.])(?:t|translate)\(\s*(['"])([^'"]+)\1\s*,\s*(?=\{)""")
TRANS_CON_VALORES = re.compile(r"""<Trans\b(?P<cuerpo>.*?)/>""", re.S)


def _llamadas_con_vars(texto):
    for m in LLAMADA_CON_VARS.finditer(texto):
        cuerpo = _objeto_literal(texto, m.end())
        if cuerpo is not None:
            yield m.group(2), cuerpo, texto.count("\n", 0, m.start()) + 1
    for m in TRANS_CON_VALORES.finditer(texto):
        k = I18NKEY.search(m.group("cuerpo"))
        v = re.search(r"values=\{\{", m.group("cuerpo"))
        if k and v:
            inicio = m.start("cuerpo") + v.end() - 1
            cuerpo = _objeto_literal(texto, inicio)
            if cuerpo is not None:
                yield next(g for g in k.groups() if g), cuerpo, texto.count("\n", 0, m.start()) + 1


def test_las_variables_de_cada_mensaje_se_pasan_en_la_llamada(catalogo):
    problemas = []
    revisadas = 0
    for f, texto in _fuentes():
        for clave, cuerpo, linea in _llamadas_con_vars(texto):
            mensajes = _formas(catalogo, clave)
            if not mensajes:
                continue  # lo cubre el test de claves
            revisadas += 1
            pasadas = _claves_del_objeto(cuerpo)
            pedidas = _variables(mensajes)
            donde = f"{f.relative_to(REPO).as_posix()}:{linea}  '{clave}'"
            if pedidas - pasadas:
                problemas.append(f"{donde}: el mensaje usa {sorted(pedidas - pasadas)} y no se pasa")
            # `count` también elige la forma plural: puede sobrar respecto al texto
            sobran = pasadas - pedidas - {"count"}
            if sobran:
                problemas.append(f"{donde}: se pasa {sorted(sobran)} y el mensaje no lo usa")
    assert revisadas > 50, "el escaneo no revisa llamadas: ¿cambió la forma de llamar a t()?"
    assert not problemas, "\n".join(problemas)


# ── 3. Plurales ──────────────────────────────────────────────────────────────

def test_las_formas_plurales_son_completas_en_es(catalogo):
    """`x_one` sin `x_other` deja a los números que no son 1 sin texto."""
    bases = {}
    for clave in catalogo:
        m = re.fullmatch(r"(.+)_(%s)" % "|".join(SUFIJOS), clave)
        if m:
            bases.setdefault(m.group(1), set()).add(m.group(2))
    assert bases, "no hay plurales: ¿se perdió el catálogo?"
    for base, formas in bases.items():
        assert "other" in formas, f"'{base}' tiene {sorted(formas)} y le falta _other"


# ── 4. Deuda de literales del builder ────────────────────────────────────────

def test_el_builder_no_deja_literales_en_la_linea_base():
    base = json.loads((REPO / "scripts" / "i18n_literals_baseline.json").read_text(encoding="utf-8"))
    pendientes = [f for f in base["ficheros"] if f.startswith("platform/")]
    assert not pendientes, f"literales sin extraer en platform/: {pendientes}"


def test_el_builder_no_importa_del_proyecto_al_traducir():
    for f, texto in _fuentes():
        assert not re.search(r"""from\s+['"][^'"]*projects/""", texto), f


# ── 5. Marcas simples de `Trans` ─────────────────────────────────────────────

@pytest.mark.skipif(shutil.which("node") is None, reason="node no disponible")
def test_parser_de_marcas_con_node():
    r = subprocess.run(
        ["node", "--test", str(I18N / "rich.test.mjs")], capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_los_mensajes_con_marcas_estan_bien_formados(catalogo):
    """Cada `<x>` del catálogo se cierra: una marca rota se pintaría como texto."""
    for clave, texto in catalogo.items():
        abiertas = re.findall(r"<(\w+)>", texto)
        cerradas = re.findall(r"</(\w+)>", texto)
        assert sorted(abiertas) == sorted(cerradas), f"{clave}: marcas sin cerrar en {texto!r}"
