"""Referencia acotada a un paper (SPEC-030 / T18.1 / AC1).

Hoy toda subida va al bucket del agente o a `__library__`, que leen **todos** los
agentes del proyecto. Subir ahí la plantilla de estilo de un paper concreto hace
que los siguientes recuperen ese estilo: contaminación silenciosa, que nadie ve
hasta que los papers empiezan a parecerse entre sí sin que nadie lo pidiera.

El plan de pruebas de la spec lo dice tal cual: dos papers en un proyecto y una
recuperación que debe ver uno y no el otro. Eso es lo que se comprueba aquí, por
las dos rutas —Qdrant y el almacén local—, porque el acotamiento sirve de poco si
solo funciona en una.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.platform.capabilities import rag  # noqa: E402

PAPER_A = "11111111-1111-1111-1111-111111111111"
PAPER_B = "22222222-2222-2222-2222-222222222222"


# ── La cláusula y su equivalente local ──────────────────────────────────────

def test_lo_compartido_se_ve_siempre():
    """Sin `article_id` el documento es de todos: es lo que ya hacían los que había."""
    assert rag._article_scope_matches(None, None) is True
    assert rag._article_scope_matches(None, PAPER_A) is True
    assert rag._article_scope_matches("", PAPER_A) is True


def test_lo_acotado_no_se_ve_desde_otro_paper():
    """AC1, en una línea."""
    assert rag._article_scope_matches(PAPER_A, PAPER_B) is False


def test_lo_acotado_se_ve_desde_su_paper():
    assert rag._article_scope_matches(PAPER_A, PAPER_A) is True


def test_lo_acotado_no_se_ve_sin_paper_en_curso():
    """Una búsqueda que no declara artículo no puede arrastrar referencias ajenas."""
    assert rag._article_scope_matches(PAPER_A, None) is False


def test_la_clausula_de_qdrant_exige_lo_compartido_si_no_hay_articulo():
    clausula = rag._article_scope_clause(None)
    assert clausula == {"must": [{"is_empty": {"key": "article_id"}}]}


def test_la_clausula_de_qdrant_admite_ambos_con_articulo():
    clausula = rag._article_scope_clause(PAPER_A)
    assert {"is_empty": {"key": "article_id"}} in clausula["should"]
    assert {"key": "article_id", "match": {"value": PAPER_A}} in clausula["should"]


def test_el_should_se_anida_dentro_del_must():
    """En Qdrant un `should` junto a un `must` no es obligatorio.

    Si se dejara al lado, el filtro de alcance no filtraría nada y la referencia
    de un paper aparecería en los demás: el fallo exacto que AC1 persigue, con el
    filtro puesto y sin efecto.
    """
    filtro = rag._merge_filter(
        [rag._agent_name_clause("redactor")], rag._article_scope_clause(PAPER_A))

    assert "should" not in filtro, "el should no puede quedar en la raíz"
    anidados = [c for c in filtro["must"] if "should" in c]
    assert len(anidados) == 1


# ── El caso del plan de pruebas: dos papers en un proyecto ──────────────────

@pytest.fixture
def coleccion(tmp_path, monkeypatch):
    """Una colección local con tres documentos: uno de A, uno de B y uno común."""
    monkeypatch.setattr(rag, "_local_rag_root", lambda: tmp_path)
    nombre = "p_proyecto__investigador"
    destino = tmp_path / nombre
    destino.mkdir(parents=True)

    documentos = [
        ("ref-a", "plantilla-a.pdf", PAPER_A, "El estilo del paper A"),
        ("ref-b", "plantilla-b.pdf", PAPER_B, "El estilo del paper B"),
        ("comun", "manual.pdf", None, "Guia de estilo compartida"),
    ]
    for doc_id, fichero, articulo, texto in documentos:
        (destino / f"{doc_id}.json").write_text(json.dumps({
            "doc_id": doc_id,
            "agent_name": "investigador",
            "filename": fichero,
            "doc_title": fichero,
            "doc_authors": "",
            "article_id": articulo,
            "chunks": [{"chunk_index": 0, "text": texto}],
        }), encoding="utf-8")
    return nombre


@pytest.mark.asyncio
async def test_el_paper_b_no_recupera_la_referencia_del_paper_a(coleccion, monkeypatch):
    """El caso que hoy fallaría, tal y como lo pide el plan de pruebas."""
    monkeypatch.setattr(rag, "is_qdrant_available", lambda *a, **k: _falso())

    resultados = await rag._fetch_agent_results(
        "http://qdrant", coleccion, "investigador", limit=10, article_id=PAPER_B)

    textos = " ".join(r["text"] for r in resultados)
    assert "paper B" in textos, "debe ver su propia referencia"
    assert "compartida" in textos, "y lo compartido"
    assert "paper A" not in textos, "NO puede ver la referencia del otro paper"


@pytest.mark.asyncio
async def test_el_paper_a_recupera_la_suya(coleccion, monkeypatch):
    monkeypatch.setattr(rag, "is_qdrant_available", lambda *a, **k: _falso())

    resultados = await rag._fetch_agent_results(
        "http://qdrant", coleccion, "investigador", limit=10, article_id=PAPER_A)

    textos = " ".join(r["text"] for r in resultados)
    assert "paper A" in textos
    assert "paper B" not in textos


@pytest.mark.asyncio
async def test_sin_paper_solo_se_recupera_lo_compartido(coleccion, monkeypatch):
    """Una ejecución sin referencia declarada no arrastra las de nadie."""
    monkeypatch.setattr(rag, "is_qdrant_available", lambda *a, **k: _falso())

    resultados = await rag._fetch_agent_results(
        "http://qdrant", coleccion, "investigador", limit=10)

    textos = " ".join(r["text"] for r in resultados)
    assert "compartida" in textos
    assert "paper A" not in textos and "paper B" not in textos


@pytest.mark.asyncio
async def test_elegir_un_doc_a_mano_no_salta_el_acotamiento(coleccion, monkeypatch):
    """Seleccionar el documento de otro paper por `doc_id` tampoco vale.

    El camino de `doc_ids` explícitos se salta el filtro de bucket a propósito,
    y sería la puerta de atrás evidente para el acotamiento si no se comprobara
    también aquí.
    """
    monkeypatch.setattr(rag, "is_qdrant_available", lambda *a, **k: _falso())

    resultados = await rag._fetch_agent_results(
        "http://qdrant", coleccion, "investigador", limit=10,
        doc_ids=["ref-a"], article_id=PAPER_B)

    assert resultados == [], "la referencia del paper A no es recuperable desde el B"


async def _falso() -> bool:
    return False


# ── La subida acotada no puede plantar en otro proyecto ────────────────────

def test_el_endpoint_de_subida_acepta_article_id():
    """La vía de un solo paso existe: subir y acotar en la misma petición."""
    import inspect
    from app.routers.agents import upload_to_rag_library

    assert "article_id" in inspect.signature(upload_to_rag_library).parameters


def test_la_subida_valida_que_el_articulo_sea_del_proyecto():
    """Acotar a un artículo ajeno sería plantar un documento en su espacio.

    El aislamiento de T8.5 no puede depender de lo que mande el cliente, así que
    el `article_id` se comprueba contra el proyecto resuelto por la cabecera.
    """
    import inspect
    from app.routers import agents

    fuente = inspect.getsource(agents.upload_to_rag_library)
    assert "destino.project_id != project.project_id" in fuente, (
        "la subida debe comprobar que el artículo es del proyecto activo"
    )
    # 404 y no 403: la respuesta no distingue «existe pero no es tuyo» de «no existe».
    assert "404" in fuente
