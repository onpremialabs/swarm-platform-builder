"""SPEC-037 AC2 / T25.2 — marcadores `regex:` validados al cargar y fechas de metadatos."""
import time
from datetime import datetime

import pytest

from app.platform.projects import loader
from app.platform.publication_gate import CriterionStatus
from app.platform.publication_gate.config import GateConfigError, parse_gate
from app.platform.publication_gate.dates import DateRules
from app.platform.publication_gate.gate import evaluate_gate
from app.platform.publication_gate.placeholders import (
    DEFAULT_PLACEHOLDERS,
    MarkerError,
    check_placeholders,
    validate_marker,
)

CREADO = datetime(2026, 9, 15, 10, 0)
AHORA = datetime(2026, 11, 22, 12, 0)
REGLAS = DateRules(labels=("Fecha", "Date"), tolerance_days=1)


def _alejandria():
    from app.platform.projects.loader import load_from
    from pathlib import Path
    import app

    raiz = Path(app.__file__).resolve().parent.parent / "projects" / "alejandria-magazine"
    return load_from(raiz).gate


# --- regex: marcadores -------------------------------------------------------------

def test_regex_bloquea_y_se_nombra_con_su_prefijo():
    m = r"regex:\[Su Nombre/Autor[ií]a\]"
    r = check_placeholders("Autor: [Su Nombre/Autoría]", [m])
    assert r.status is CriterionStatus.FAILED and r.blocking
    assert r.evidence[0]["pattern"] == m and r.evidence[0]["line"] == 1


def test_regex_y_literales_conviven_en_orden_de_posicion():
    r = check_placeholders("TODO y luego [?] y [Autor]", ["TODO", "[?]", r"regex:\[Autor\]"])
    assert [e["offset"] for e in r.evidence] == sorted(e["offset"] for e in r.evidence)
    assert len(r.evidence) == 3


def test_regex_ignora_codigo_delimitado():
    r = check_placeholders("Mira `[Autor]` y ```\n[Autor]\n```", [r"regex:\[Autor\]"])
    assert r.status is CriterionStatus.PASSED


def test_regex_distingue_mayusculas_salvo_flag_inline():
    assert check_placeholders("[autor]", [r"regex:\[Autor\]"]).status is CriterionStatus.PASSED
    assert check_placeholders("[autor]", [r"regex:(?i)\[Autor\]"]).blocking


def test_un_literal_con_prefijo_parecido_sigue_siendo_literal():
    # Sin el prefijo exacto no es una regex: "regex" a secas es un literal.
    assert check_placeholders("a.b", ["a.b"]).blocking
    assert check_placeholders("axb", ["a.b"]).status is CriterionStatus.PASSED


# --- validación al cargar ------------------------------------------------------------

@pytest.mark.parametrize("marker,fragmento", [
    ("regex:(", "no válida"),
    ("regex:[a-", "no válida"),
    ("regex:", "vacía"),
    ("regex:   ", "vacía"),
    ("regex:a*", "vacío"),            # casa con "" => marcaría todo
    ("regex:(a+)+$", "anidadas"),     # catastrófica clásica
    ("regex:(a*)*b", "anidadas"),
    ("regex:(a|a)*b", "alternativas"),
    ("regex:(x+x+)+y", "anidadas"),
    ("regex:(a)\\1", "referencias"),
    ("regex:a{1,100000}", "demasiado grande"),
    ("regex:" + "a" * 300, "supera"),
])
def test_regex_invalida_o_peligrosa_se_rechaza(marker, fragmento):
    with pytest.raises(MarkerError, match=fragmento):
        validate_marker(marker)


@pytest.mark.parametrize("marker", [
    "TODO", "(Author, Year)", r"regex:\bTODO\b", r"regex:\[\s?Autor\s?\](?!\()",
    r"regex:(?:Su|Tu) nombre", r"regex:\d{4}-\d{2}",
])
def test_regex_sana_se_acepta(marker):
    validate_marker(marker)


def test_parse_gate_traduce_el_error_con_el_marcador():
    with pytest.raises(GateConfigError, match=r"gate\.placeholders.*\(a\+\)\+"):
        parse_gate({"placeholders": ["TODO", "regex:(a+)+$"]})


def test_la_plantilla_con_regex_rota_falla_al_cargar(tmp_path):
    import shutil
    from pathlib import Path
    import app

    origen = Path(app.__file__).resolve().parent.parent / "projects" / "alejandria-magazine"
    destino = tmp_path / "alejandria-magazine"
    shutil.copytree(origen, destino)
    plantilla = destino / "template.yaml"
    texto = plantilla.read_text(encoding="utf-8")
    plantilla.write_text(texto.replace('    - "XXX"\n', '    - "XXX"\n    - "regex:(a+)+$"\n', 1), encoding="utf-8")
    with pytest.raises(loader.TemplateError, match="anidadas"):
        loader.load_from(destino)


def test_regresion_la_lista_de_literales_actual_sigue_igual():
    cfg = parse_gate({"placeholders": list(DEFAULT_PLACEHOLDERS)})
    assert cfg.placeholders == DEFAULT_PLACEHOLDERS and cfg.dates.labels == ()
    for marker in DEFAULT_PLACEHOLDERS:
        assert check_placeholders(f"x {marker} y", cfg.placeholders).blocking
    # y sin `gate.dates` ni creación no se examinan fechas: mismo resultado que antes
    assert check_placeholders("Fecha: Octubre 2023", cfg.placeholders, created_at=CREADO).status \
        is CriterionStatus.PASSED


def test_la_regex_de_alejandria_no_es_lenta():
    cfg = _alejandria()
    texto = "[" + "su " * 20000 + "x"
    t0 = time.perf_counter()
    check_placeholders(texto, cfg.placeholders)
    assert time.perf_counter() - t0 < 1.0


# --- plantilla de AlejandrIA ----------------------------------------------------------

@pytest.mark.parametrize("texto", [
    "Autor: [Su Nombre/Autoría]",
    "Autor: [Su Nombre]",
    "Author: [Your Name]",
    "Autor: [Autor]",
    "[su nombre/autoria]",
])
def test_alejandria_bloquea_autoria_sin_rellenar(texto):
    r = check_placeholders(texto, _alejandria().placeholders)
    assert r.status is CriterionStatus.FAILED, texto


@pytest.mark.parametrize("texto", [
    "Véase [el autor](https://ejemplo.org) y [Autor](https://x.org).",
    "Según [1] el nombre del método es robusto.",
    "Autor: Ana García Ruiz",
])
def test_alejandria_no_bloquea_texto_legitimo(texto):
    assert check_placeholders(texto, _alejandria().placeholders).status is CriterionStatus.PASSED


# --- fechas fuera de rango -------------------------------------------------------------

def _fechas(texto, **kw):
    return check_placeholders(
        texto, [], dates=kw.pop("dates", REGLAS), created_at=kw.pop("created_at", CREADO),
        now=kw.pop("now", AHORA),
    )


def test_caso_real_fecha_octubre_2023_bloquea():
    r = _fechas("Autor: [Su Nombre/Autoría]\nFecha: Octubre 2023 (Borrador)\n\nTexto.")
    assert r.status is CriterionStatus.FAILED and r.blocking
    e = r.evidence[0]
    assert e["pattern"] == "date_out_of_range" and e["reason"] == "before_creation"
    assert e["line"] == 2 and e["text"] == "Octubre 2023"


def test_caso_real_completo_con_la_plantilla_de_alejandria_ambos_hallazgos():
    cfg = _alejandria()
    r = check_placeholders(
        "Autor: [Su Nombre/Autoría]\nFecha: Octubre 2023 (Borrador)", cfg.placeholders,
        dates=cfg.dates, created_at=CREADO, now=AHORA,
    )
    assert {e["pattern"] for e in r.evidence} >= {"date_out_of_range"} and len(r.evidence) == 2


@pytest.mark.parametrize("linea", [
    "Fecha: 15 de septiembre de 2026",
    "Fecha: septiembre 2026",
    "Fecha: 2026",
    "**Fecha:** 2026-09-15",
    "> Fecha: 14/09/2026",           # tolerancia de un día
    "Date: September 15, 2026",
    "Fecha: 22 de noviembre de 2026",
    "Fecha: pendiente",               # sin fecha reconocible, nada que juzgar
    "Fecha: 31 de febrero de 2020",   # no es una fecha válida: no se juzga
])
def test_fechas_dentro_de_rango_pasan(linea):
    assert _fechas(linea).status is CriterionStatus.PASSED, linea


@pytest.mark.parametrize("linea,motivo", [
    ("Fecha: 2023", "before_creation"),
    ("Fecha: 2023-10-01", "before_creation"),
    ("Fecha: 1 de enero de 2020", "before_creation"),
    ("Date: October 2023", "before_creation"),
    ("Fecha: 10/09/2026", "before_creation"),
    ("Fecha: diciembre de 2026", "after_evaluation"),
    ("Fecha: 2027", "after_evaluation"),
])
def test_fechas_fuera_de_rango_bloquean(linea, motivo):
    r = _fechas(linea)
    assert r.blocking and r.evidence[0]["reason"] == motivo, linea


def test_falso_positivo_citas_y_fechas_en_el_cuerpo_no_bloquean():
    texto = (
        "Fecha: 15 de septiembre de 2026\n\n"
        "Como mostraron García (2019) y Smith et al. (2015), el efecto persiste.\n"
        "El estudio de 2019 (Fecha: no aplica) se repitió en 2021.\n"
        "Referencias\nPérez, J. (2018). Título. Revista, 3(2), 1-10. https://doi.org/10.1000/x\n"
    )
    assert _fechas(texto).status is CriterionStatus.PASSED


def test_la_etiqueta_debe_abrir_la_linea():
    # «Fecha:» en mitad de una frase no es metadato.
    assert _fechas("El informe tiene Fecha: 2019 en su portada.").status is CriterionStatus.PASSED


def test_codigo_delimitado_no_cuenta_para_fechas():
    assert _fechas("```\nFecha: 2019\n```").status is CriterionStatus.PASSED


def test_sin_creacion_o_sin_etiquetas_no_se_comprueba_nada():
    assert _fechas("Fecha: 2019", created_at=None).status is CriterionStatus.PASSED
    assert _fechas("Fecha: 2019", dates=DateRules()).status is CriterionStatus.PASSED


@pytest.mark.parametrize("datos", [
    {"dates": []}, {"dates": {"labels": "Fecha"}}, {"dates": {"labels": [""]}},
    {"dates": {"tolerance_days": -1}}, {"dates": {"tolerance_days": True}},
    {"dates": {"otro": 1}},
])
def test_gate_dates_invalido_falla_al_cargar(datos):
    with pytest.raises(GateConfigError):
        parse_gate(datos)


# --- por la compuerta completa -----------------------------------------------------------

@pytest.mark.asyncio
async def test_evaluate_gate_pasa_la_creacion_y_bloquea():
    cfg = _alejandria()
    informe = await evaluate_gate(
        "Autor: [Su Nombre/Autoría]\nFecha: Octubre 2023 (Borrador)", [], cfg,
        created_at=CREADO, now=AHORA,
    )
    ph = next(c for c in informe.criteria if c.criterion == "placeholders")
    assert ph.blocking and not informe.passed and len(ph.evidence) == 2
