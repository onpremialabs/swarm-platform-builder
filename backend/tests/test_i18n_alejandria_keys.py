"""Las claves de i18n que usa AlejandrIA Magazine existen en su catálogo (SPEC-041 / T29.8).

No hay tests de componente en el frontend: una clave mal escrita en un `.jsx` no
rompe nada, solo pinta la clave en pantalla. `check_i18n.py` detecta la clave
**sin usar** (catálogo -> código); este test cubre el sentido contrario, la clave
**inexistente** (código -> catálogo), y que cada `{variable}` del mensaje se pase.

Reconoce tres formas de uso en `frontend/src/projects/alejandria-magazine/`:
  * llamadas `t('clave', {...})` / `tr('clave', {...})`;
  * llamadas con plantilla `t(`grupo.${x}`)`: el prefijo debe existir;
  * claves guardadas como dato (`label: 'citations.status.supported'`, que luego
    se pinta con `t(st.label)`): toda cadena con forma de clave cuyo primer
    segmento sea un grupo del catálogo debe existir.
"""
import json
import re
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]
PROYECTO = REPO_DIR / "frontend" / "src" / "projects" / "alejandria-magazine"
I18N = PROYECTO / "i18n"

SUFIJOS_PLURAL = ("zero", "one", "two", "few", "many", "other")
LLAMADA = re.compile(r"(?<![\w.])(?:t|tr)\(\s*(['\"`])([^'\"`]*)\1")
PLANTILLA = re.compile(r"(?<![\w.])(?:t|tr)\(\s*`([^`]*)`")
FORMA_DE_CLAVE = re.compile(r"^[a-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")
VARIABLE = re.compile(r"\{(\w+)\}")


def _aplanar(obj, prefijo=""):
    for k, v in obj.items():
        clave = f"{prefijo}.{k}" if prefijo else k
        if isinstance(v, dict):
            yield from _aplanar(v, clave)
        else:
            yield clave, str(v)


def _catalogo(idioma="es"):
    return dict(_aplanar(json.loads((I18N / f"{idioma}.json").read_text(encoding="utf-8"))))


def _base(clave):
    m = re.fullmatch(r"(.+)_(" + "|".join(SUFIJOS_PLURAL) + ")", clave)
    return m.group(1) if m else clave


def _fuentes():
    return [
        f for f in sorted(PROYECTO.rglob("*"))
        if f.suffix in (".js", ".jsx") and I18N not in f.parents and ".test." not in f.name
    ]


def _argumentos(texto, inicio):
    """Texto de los argumentos de la llamada cuyo `(` está justo antes de `inicio`."""
    nivel, i = 1, inicio
    while i < len(texto) and nivel:
        nivel += {"(": 1, ")": -1}.get(texto[i], 0)
        i += 1
    return texto[inicio:i]


def test_el_catalogo_existe_y_no_esta_vacio():
    assert len(_catalogo()) > 300


def test_toda_clave_usada_en_las_llamadas_existe():
    es = _catalogo()
    bases = {_base(k) for k in es}
    faltan = []
    for f in _fuentes():
        for m in LLAMADA.finditer(f.read_text(encoding="utf-8")):
            clave = m.group(2)
            if "${" in clave:
                continue  # plantilla dinamica: la cubre el test del prefijo
            if clave not in es and clave not in bases:
                faltan.append(f"{f.relative_to(PROYECTO).as_posix()}: t('{clave}')")
    assert not faltan, "claves usadas que no están en es.json:\n  " + "\n  ".join(faltan)


def test_toda_plantilla_dinamica_tiene_prefijo_en_el_catalogo():
    es = _catalogo()
    faltan = []
    for f in _fuentes():
        for m in PLANTILLA.finditer(f.read_text(encoding="utf-8")):
            prefijo = m.group(1).split("${", 1)[0]
            if "${" in m.group(1) and not any(k.startswith(prefijo) for k in es):
                faltan.append(f"{f.relative_to(PROYECTO).as_posix()}: t(`{m.group(1)}`)")
    assert not faltan, "plantillas sin claves en es.json:\n  " + "\n  ".join(faltan)


def test_las_claves_guardadas_como_dato_existen():
    es = _catalogo()
    bases = {_base(k) for k in es}
    grupos = {k.split(".", 1)[0] for k in es}
    cadena = re.compile(r"(['\"])([^'\"\n]+)\1")
    faltan = []
    for f in _fuentes():
        for m in cadena.finditer(f.read_text(encoding="utf-8")):
            texto = m.group(2)
            if FORMA_DE_CLAVE.match(texto) and texto.split(".", 1)[0] in grupos:
                if texto not in es and texto not in bases:
                    faltan.append(f"{f.relative_to(PROYECTO).as_posix()}: '{texto}'")
    assert not faltan, "claves guardadas como dato que no existen:\n  " + "\n  ".join(faltan)


def test_cada_variable_del_mensaje_se_pasa_en_la_llamada():
    """`t('citations.claim')` sin `{ claim }` pintaría «{claim}» tal cual."""
    es = _catalogo()
    por_base = {}
    for k, v in es.items():
        por_base.setdefault(_base(k), set()).update(VARIABLE.findall(v))
    fallos = []
    for f in _fuentes():
        texto = f.read_text(encoding="utf-8")
        for m in LLAMADA.finditer(texto):
            clave = m.group(2)
            esperadas = por_base.get(clave, set()) - {"count"}
            if not esperadas:
                continue
            args = _argumentos(texto, m.end())
            palabras = set(re.findall(r"\w+", args))
            if esperadas - palabras:
                fallos.append(
                    f"{f.relative_to(PROYECTO).as_posix()}: t('{clave}') no pasa {sorted(esperadas - palabras)}"
                )
    assert not fallos, "\n  ".join(["variables sin pasar:"] + fallos)


def test_los_plurales_traen_la_forma_other():
    """Sin `_other`, un recuento que no sea 1 no encontraría su texto."""
    es = _catalogo()
    for clave in es:
        m = re.fullmatch(r"(.+)_one", clave)
        if m:
            assert f"{m.group(1)}_other" in es, f"{clave} sin {m.group(1)}_other"


def test_el_catalogo_en_provisional_tiene_las_mismas_claves():
    """Hasta T29.9, `en.json` copia `es.json` para que la paridad de T29.13 siga activa."""
    assert set(_catalogo("en")) == set(_catalogo("es"))


def test_la_revista_publica_monta_el_proveedor_y_registra_los_mensajes():
    """index.public.html tiene su propio punto de entrada: sin esto la revista saldría en blanco de textos."""
    main = (PROYECTO / "public" / "main.jsx").read_text(encoding="utf-8")
    assert "I18nProvider" in main
    assert "registerMessages(NAMESPACE, MESSAGES)" in main
    assert "registerMessages('platform'" in main


def test_el_proyecto_no_importa_de_otro_proyecto_ni_toca_el_catalogo_de_la_plataforma():
    """El catálogo de la plataforma es de T29.7; aquí solo se lee su proveedor."""
    for f in _fuentes():
        texto = f.read_text(encoding="utf-8")
        assert "platform/i18n/es.json" not in texto or f.name == "main.jsx", f.name
