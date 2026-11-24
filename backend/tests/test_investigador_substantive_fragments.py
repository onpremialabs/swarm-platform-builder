"""Investigador: abstención por falta de fragmentos sustantivos (SPEC-034 / T22.15 / AC16).

Reutiliza el mundo y los dobles de `test_investigador_verified_only` (sin red).
"""
import pytest

from tests.test_investigador_verified_only import (  # noqa: F401
    _doc, _estado, _hit, entorno, mundo,
)
from app.modules.agents.adapters import investigador
from app.modules.agents.domain import alejandria
from app.platform import explainability, library
from app.platform.capabilities.literature.research import (
    DEFAULT_MIN_SUBSTANTIVE_FRAGMENTS, ResearchConfig, ResearchConfigError, parse_research,
)
from app.platform.projects import loader

import shutil
from app.core.database import AsyncSessionLocal


def _ref(n):
    h = _hit(n, text="Smith J. (2019) Deep learning for things. Nature 12, 1-10.")
    h["section"] = "references"
    return h


async def _solo_resumen(project, n):
    doc = await _doc(project, n)
    async with AsyncSessionLocal() as session:
        await library.set_text_status(session, project, doc.id, library.TextStatus.ABSTRACT_ONLY)


# ── K: plantilla, validación, no reducible ──────────────────────────────────

def test_k_por_defecto_es_3_y_la_plantilla_lo_declara():
    assert DEFAULT_MIN_SUBSTANTIVE_FRAGMENTS == 3
    assert ResearchConfig().min_substantive_fragments == 3
    assert parse_research(None).min_substantive_fragments == 3
    assert alejandria.package().research.min_substantive_fragments == 3


@pytest.mark.parametrize("valor", [0, -1, 2.5, "3", True, []])
def test_k_invalido_se_rechaza_al_cargar(valor):
    with pytest.raises(ResearchConfigError, match="min_substantive_fragments"):
        parse_research({"min_substantive_fragments": valor})


def test_k_valido_se_respeta():
    assert parse_research({"min_substantive_fragments": 5}).min_substantive_fragments == 5
    assert parse_research({"sources": ["crossref"], "min_substantive_fragments": 1}
                          ).min_substantive_fragments == 1


def test_una_plantilla_con_k_invalido_no_carga(tmp_path):
    origen = alejandria.package().root if hasattr(alejandria.package(), "root") else None
    if origen is None:
        pytest.skip("el paquete no expone su raíz")
    destino = tmp_path / "p"
    shutil.copytree(origen, destino)
    plantilla = destino / "template.yaml"
    texto = plantilla.read_text(encoding="utf-8")
    assert "min_substantive_fragments: 3" in texto
    plantilla.write_text(texto.replace("min_substantive_fragments: 3",
                                       "min_substantive_fragments: 0"), encoding="utf-8")
    with pytest.raises(Exception, match="min_substantive_fragments"):
        loader.load_from(destino)


@pytest.mark.asyncio
async def test_el_autor_no_puede_bajar_k_desde_los_ajustes(mundo, entorno):
    p = mundo["p1"]
    for n in (1, 2, 3):
        await _doc(p, n)
    entorno["resultados"]["hits"] = [_hit(1), _hit(2), _ref(3)]
    out = await investigador.run_investigador(_estado(
        p, agent_settings={"investigador": {"min_substantive_fragments": 1}}))
    assert out["abstained"] is True
    assert out["abstention"]["min_substantive_fragments"] == 3


# ── AC16 ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_n_fuentes_pero_pocos_fragmentos_sustantivos_se_abstiene(mundo, entorno):
    p = mundo["p1"]
    for n in (1, 2, 3):
        await _doc(p, n)
    # 3 fuentes citables (AC7 se cumple), pero 2 de sus 3 fragmentos son bibliografía.
    entorno["resultados"]["hits"] = [_hit(1), _ref(2), _ref(3)]
    out = await investigador.run_investigador(_estado(p))
    assert out["abstained"] is True and out["sources"] == [] and entorno["llm"] == []
    a = out["abstention"]
    assert a["reason"] == "insufficient_substantive_content"      # distinto del de AC7
    assert a["substantive_fragments"] == 1 and a["min_substantive_fragments"] == 3
    assert a["citable_sources"] == 3
    msg = a["message"]
    assert "PDF completo" in msg and "reindexa" in msg and "aporta el texto" in msg


@pytest.mark.asyncio
async def test_el_motivo_de_ac7_sigue_siendo_el_suyo(mundo, entorno):
    p = mundo["p1"]
    await _doc(p, 1)
    entorno["resultados"]["hits"] = [_hit(1)]
    out = await investigador.run_investigador(_estado(p))
    assert out["abstention"]["reason"] == "insufficient_verified_sources"


@pytest.mark.asyncio
async def test_un_fragmento_sin_texto_utilizable_no_cuenta(mundo, entorno):
    p = mundo["p1"]
    for n in (1, 2, 3):
        await _doc(p, n)
    entorno["resultados"]["hits"] = [_hit(1), _hit(2), _hit(3, text="  12 ...  ")]
    out = await investigador.run_investigador(_estado(p))
    assert out["abstained"] is True
    assert out["abstention"]["substantive_fragments"] == 2


@pytest.mark.asyncio
async def test_con_k_fragmentos_sustantivos_investiga_y_no_cita_la_bibliografia(mundo, entorno):
    p = mundo["p1"]
    for n in (1, 2, 3):
        await _doc(p, n)
    entorno["resultados"]["hits"] = [_hit(1), _hit(2), _hit(3), _ref(3)]
    out = await investigador.run_investigador(_estado(p))
    assert not out.get("abstained") and len(out["sources"]) == 3
    assert "Deep learning for things" not in entorno["llm"][0]


@pytest.mark.asyncio
async def test_abstract_only_cuenta_como_un_fragmento_como_maximo(mundo, entorno):
    p = mundo["p1"]
    await _solo_resumen(p, 1)
    await _solo_resumen(p, 2)
    await _doc(p, 3)
    # Dos «solo resumen» con 3 fragmentos recuperados cada uno aportan 1 + 1; el completo, 1.
    entorno["resultados"]["hits"] = [_hit(1)] * 3 + [_hit(2)] * 3 + [_hit(3)]
    out = await investigador.run_investigador(_estado(p))
    assert not out.get("abstained") and len(out["sources"]) == 3

    # Sin el fragmento del completo son 2 (no 6): se abstiene por contenido, no por fuentes.
    entorno["resultados"]["hits"] = [_hit(1)] * 3 + [_hit(2)] * 3 + [_ref(3)]
    out = await investigador.run_investigador(_estado(p))
    assert out["abstention"]["reason"] == "insufficient_substantive_content"
    assert out["abstention"]["substantive_fragments"] == 2


@pytest.mark.asyncio
async def test_abstract_only_con_muchos_fragmentos_no_suple_la_falta(mundo, entorno):
    p = mundo["p1"]
    for n in (1, 2, 3):
        await _solo_resumen(p, n)
    entorno["resultados"]["hits"] = [_hit(1), _hit(2), _ref(3), _ref(3)]
    out = await investigador.run_investigador(_estado(p))
    assert out["abstained"] is True
    assert out["abstention"]["abstract_only_documents"] == 3
    assert out["abstention"]["substantive_fragments"] == 2


def test_la_traza_declara_el_motivo_y_los_fragmentos():
    decision = explainability.decision_of({"abstained": True, "abstention": {
        "reason": "insufficient_substantive_content", "substantive_fragments": 1,
        "min_substantive_fragments": 3, "verified_sources": 3, "min_sources": 3}})
    assert decision["reason"] == "insufficient_substantive_content"
    assert decision["substantive_fragments"] == 1 and decision["min_substantive_fragments"] == 3
