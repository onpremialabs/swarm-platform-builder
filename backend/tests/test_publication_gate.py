"""SPEC-032 AC5 y AC11 / T20.4 — módulo de la compuerta, V03 y `gate:` en template.yaml."""
import asyncio
import copy

import pytest
import yaml

from app.platform.projects import loader
from app.platform.projects.loader import TemplateError, load
from app.platform.publication_gate import CriterionStatus
from app.platform.publication_gate.config import GateConfigError, parse_gate
from app.platform.publication_gate.gate import evaluate_gate
from app.platform.publication_gate.placeholders import DEFAULT_PLACEHOLDERS
from app.platform.publication_gate.structure import check_structure

GATE = load("alejandria-magazine").gate

IMRAD_ES = """# Título

## Resumen
Algo.

## Introducción
Texto.

## Metodología
Texto.

## Resultados
Texto.

## Discusión
Texto.

## Referencias
Lista.
"""

IMRAD_EN = (
    IMRAD_ES.replace("Introducción", "Introduction").replace("Metodología", "Methods")
    .replace("Resultados", "Results").replace("Discusión", "Discussion")
    .replace("Referencias", "References")
)


def estructura(texto):
    return check_structure(texto, GATE.sections, GATE.titles)


# ── V03 ─────────────────────────────────────────────────────────────────────


def test_imrad_completo_pasa_en_espanol_y_en_ingles():
    assert estructura(IMRAD_ES).status is CriterionStatus.PASSED
    assert estructura(IMRAD_EN).status is CriterionStatus.PASSED


@pytest.mark.parametrize("titulo", ["Métodos", "Metodología"])
def test_acepta_los_titulos_del_diccionario(titulo):
    assert estructura(IMRAD_ES.replace("Metodología", titulo)).status is CriterionStatus.PASSED


def test_encabezados_numerados_y_de_cualquier_nivel():
    texto = IMRAD_ES.replace("## Introducción", "### 1. Introducción")
    assert estructura(texto).status is CriterionStatus.PASSED


def test_seccion_ausente_se_nombra():
    r = estructura(IMRAD_ES.replace("## Discusión\nTexto.\n\n", ""))
    assert r.status is CriterionStatus.FAILED and r.blocking
    assert {"section": "discussion", "problem": "missing", "language": "es"} in r.evidence


def test_resultados_y_discusion_fundidos_fallan():
    texto = IMRAD_ES.replace("## Resultados\nTexto.\n\n## Discusión", "## Resultados y Discusión")
    r = estructura(texto)
    assert r.status is CriterionStatus.FAILED
    assert any(e["problem"] == "fused" for e in r.evidence)


def test_secciones_desordenadas_fallan():
    texto = IMRAD_ES.replace("## Resultados\nTexto.\n\n## Discusión\nTexto.\n\n",
                             "## Discusión\nTexto.\n\n## Resultados\nTexto.\n\n")
    r = estructura(texto)
    assert r.status is CriterionStatus.FAILED
    assert any(e["problem"] == "out_of_order" for e in r.evidence)


def test_texto_sin_encabezados_falla_y_sin_diccionario_no_se_verifica():
    assert estructura("Solo un párrafo.").status is CriterionStatus.FAILED
    assert check_structure(IMRAD_ES, GATE.sections, {}).status is CriterionStatus.NOT_VERIFIED


# ── Configuración y validación al cargar ────────────────────────────────────


def test_la_plantilla_de_alejandria_declara_la_compuerta():
    assert GATE is not None
    # AC1: los literales son la lista cerrada, sin deriva; los `regex:` los añade SPEC-037/AC2.
    literales = tuple(m for m in GATE.placeholders if not m.startswith("regex:"))
    assert literales == DEFAULT_PLACEHOLDERS
    assert any(m.startswith("regex:") for m in GATE.placeholders)
    assert GATE.references.title_similarity == 0.90
    assert {p.id for p in GATE.pending} == {"V01", "V05", "V06", "V07", "V08", "V12", "V13", "V14", "V16"}
    assert all(p.phase for p in GATE.pending)


def _plantilla(tmp_path, cambio):
    raiz = tmp_path / "proyecto"
    origen = loader.PROJECTS_ROOT / "alejandria-magazine"
    import shutil

    shutil.copytree(origen, raiz)
    ruta = raiz / loader.PLANTILLA
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    cambio(datos)
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True), encoding="utf-8")
    return raiz


def test_proyecto_sin_gate_carga_sin_compuerta(tmp_path):
    raiz = _plantilla(tmp_path, lambda d: d.pop("gate"))
    assert loader.load_from(raiz).gate is None


@pytest.mark.parametrize(
    "cambio,fragmento",
    [
        (lambda g: g["references"].update(title_similarity=1.5), "title_similarity"),
        (lambda g: g["references"].update(desconocido=1), "desconocido"),
        (lambda g: g["references"].update(retries=True), "retries"),
        (lambda g: g.update(placeholders=[]), "placeholders"),
        (lambda g: g["structure"]["titles"]["es"].pop("results"), "results"),
        (lambda g: g.update(pending=[{"id": "V01"}]), "pending"),
        (lambda g: g.update(references="no es un mapa"), "references"),
    ],
)
def test_una_compuerta_mal_escrita_falla_al_cargar(tmp_path, cambio, fragmento):
    raiz = _plantilla(tmp_path, lambda d: cambio(d["gate"]))
    with pytest.raises(TemplateError) as exc:
        loader.load_from(raiz)
    assert fragmento in str(exc.value)


def test_parse_gate_con_valores_por_defecto():
    cfg = parse_gate({})
    assert cfg.placeholders == DEFAULT_PLACEHOLDERS and cfg.pending == ()
    with pytest.raises(GateConfigError):
        parse_gate([])


# ── La compuerta completa ───────────────────────────────────────────────────

FUENTE = {"title": "Deep learning", "authors": "LeCun, Bengio, Hinton", "year": "2015",
          "journal": "Nature", "doi": "10.1038/nature14539"}


class _Resp:
    status_code = 200

    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d


async def _fetch_ok(url, *, params=None, headers=None, timeout=10.0):
    return _Resp({"message": {
        "DOI": "10.1038/nature14539", "title": ["Deep learning"], "type": "journal-article",
        "author": [{"family": "LeCun"}, {"family": "Bengio"}, {"family": "Hinton"}],
        "issued": {"date-parts": [[2015]]}, "container-title": ["Nature"]}})


async def _nosleep(_):
    pass


def gate(texto, fuentes, fetch=_fetch_ok):
    return asyncio.run(evaluate_gate(texto, fuentes, GATE, fetch=fetch, sleep=_nosleep))


def test_manuscrito_valido_pasa_y_lista_lo_pendiente():
    r = gate(IMRAD_ES, [FUENTE])
    assert r.passed and r.blockers == []
    assert [c.criterion for c in r.criteria] == [
        "reference_existence", "reference_structure", "placeholders", "imrad_structure"]
    assert {p["id"] for p in r.pending} >= {"V01", "V12"}  # AC5: pendientes visibles
    assert r.as_dict()["passed"] is True


def test_cada_criterio_bloquea_por_separado():
    assert gate(IMRAD_ES + "\nTODO", [FUENTE]).blockers[0].criterion == "placeholders"
    assert gate("sin estructura", [FUENTE]).blockers[0].criterion == "imrad_structure"

    async def caido(*a, **k):
        raise TimeoutError("x")

    r = gate(IMRAD_ES, [FUENTE], fetch=caido)
    assert r.blockers[0].status is CriterionStatus.NOT_VERIFIED  # falla cerrada
    assert not r.passed


def test_resolver_antes_de_validar_la_estructura():
    # AC2/AC3: sin año ni revista en la fuente, la resolución la completa y la estructura pasa.
    incompleta = {**FUENTE, "year": "", "journal": ""}
    r = gate(IMRAD_ES, [incompleta])
    assert r.passed and r.sources[0]["year"] == "2015" and r.sources[0]["journal"] == "Nature"


def test_no_hay_estado_compartido_entre_evaluaciones():
    a = gate(IMRAD_ES, [FUENTE])
    b = gate(IMRAD_ES + "\nXXX", [copy.deepcopy(FUENTE)])
    assert a.passed and not b.passed
