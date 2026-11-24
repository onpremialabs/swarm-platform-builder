"""Sección de referencias fuera del índice de recuperación (SPEC-034 AC15 / T22.14).

Observado en una ejecución real: los fragmentos que llegaban al mapa de citas eran
entradas de las listas de referencias de los PDF, no contenido. Estos tests
defienden:

* la detección es **determinista y conservadora**: ante duda, ``other``;
* ``section=references`` queda fuera de la búsqueda (Qdrant con ``must_not`` y
  respaldo local) pero **el texto se conserva** en el documento (AC4);
* con un PDF real de acceso abierto (SciPy 1.0, CC-BY 4.0, 160 referencias) ningún
  fragmento recuperado es una entrada bibliográfica;
* el aislamiento por proyecto (T8.5) y ``embed_vector_size()`` no se tocan.
"""
import asyncio
import uuid
import re
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.platform.capabilities import rag  # noqa: E402
from app.platform.capabilities.sections import parece_bibliografia, split_sections  # noqa: E402
from app.platform.project_context import ProjectContext  # noqa: E402

PDF = Path(__file__).parent / "fixtures" / "scipy-1.0-oa.pdf"

_ENTRADA_NUMERADA = re.compile(r"^\s*\d{1,3}\.\s+\S.*\b(?:19|20)\d\d\b", re.MULTILINE)
_REF = {"key": "section", "match": {"value": "references"}}


def _es_entrada_bibliografica(texto: str) -> bool:
    return bool(re.search(r"\bURL https?://", texto)) or len(_ENTRADA_NUMERADA.findall(texto)) >= 2


def _bibliografia_sintetica(n: int = 30) -> str:
    return "\n".join(
        f"{i}. Autor{i}, A. B. & Otro, C. Titulo del trabajo numero {i}. J. Ejemplo {i}, "
        f"{10 + i}-{20 + i} ({1990 + i % 30}). doi:10.1000/ejemplo.{i}"
        for i in range(1, n + 1))


# -- Detección ---------------------------------------------------------------

def test_texto_sin_encabezados_es_un_solo_tramo_other_y_chunk_igual_que_antes():
    texto = "Un parrafo.\n\nOtro parrafo con contenido.\n\n" * 30
    assert split_sections(texto) == [("other", texto)]
    chunks, secciones = rag.chunk_text_sections(texto, chunk_size=200, overlap=20)
    assert chunks == rag.chunk_text(texto, chunk_size=200, overlap=20)
    assert set(secciones) == {"other"}


def test_encabezado_references_sobre_bibliografia_se_marca():
    texto = "Introduction\nAlgo de contenido.\n\nReferences\n" + _bibliografia_sintetica()
    assert [s for s, _ in split_sections(texto)] == ["introduction", "references"]


def test_encabezado_references_sobre_prosa_se_conserva_como_other():
    prosa = "Esta seccion se llama References pero describe ideas. " * 20
    tramos = split_sections("Introduction\nHola.\nReferences\n" + prosa)
    assert "references" not in [s for s, _ in tramos]
    assert not parece_bibliografia(prosa)


def test_secciones_imrad_y_numeracion():
    texto = ("Title\nAbstract\nresumen del trabajo\n1. Introduction\nintro\n2 Methods\nse hizo asi\n"
             "3. Results\nlos datos muestran\nDiscussion\ndisc\nConclusions\nfin\n")
    assert [s for s, _ in split_sections(texto)] == [
        "other", "abstract", "introduction", "methods", "results", "discussion", "conclusion"]


def test_lo_posterior_a_la_bibliografia_no_se_excluye():
    texto = ("Discussion\nalgo\nReferences\n" + _bibliografia_sintetica()
             + "\nAcknowledgements\nGracias a todos.\nAppendix\nTabla extra.")
    assert [s for s, _ in split_sections(texto)] == ["discussion", "references", "other", "other"]


def test_el_split_no_pierde_texto():
    texto = "Intro\nIntroduction\nx\nReferences\n" + _bibliografia_sintetica() + "\nFunding\nf"
    assert "\n".join(t for _, t in split_sections(texto)) == texto


# -- PDF real de acceso abierto ----------------------------------------------

@pytest.fixture(scope="module")
def texto_pdf():
    texto = rag.extract_text(PDF.name, PDF.read_bytes())
    assert len(texto) > 50_000, "el PDF de prueba no se extrajo"
    return texto


def test_pdf_real_tiene_mas_de_100_referencias_y_se_etiquetan(texto_pdf):
    tramos = [t for s, t in split_sections(texto_pdf) if s == "references"]
    assert len(tramos) == 1
    entradas = len(re.findall(r"^\d{1,3}\. ", tramos[0], re.MULTILINE))
    assert entradas > 100
    chunks, secciones = rag.chunk_text_sections(texto_pdf)
    refs = [c for c, s in zip(chunks, secciones) if s == "references"]
    assert {"abstract", "introduction", "discussion"} <= set(secciones)
    assert any("Oliphant" in c for c in refs)  # se conservan, no se descartan


def test_pdf_real_ningun_fragmento_recuperado_es_una_entrada_bibliografica(
        texto_pdf, tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "_local_rag_root", lambda: tmp_path)

    async def _no(*a, **k):
        return False
    monkeypatch.setattr(rag, "is_qdrant_available", _no)
    monkeypatch.setattr(rag, "_anotar_traza", lambda *a, **k: None)

    col = ProjectContext(project_id=uuid.uuid4()).collection("fuentes")
    chunks, secciones = rag.chunk_text_sections(texto_pdf)

    async def _flujo():
        await rag.upsert_chunks(
            "http://q", col, "doc-1", "__library__", "scipy.pdf", chunks,
            "http://o", "m", rag.embed_vector_size(), sections=secciones)
        return await rag.semantic_search_results(
            "scipy optimization algorithms", "http://q", col, ["__library__"],
            "http://o", "m", limit=10_000, score_threshold=0.0)

    recuperados = asyncio.run(_flujo())
    assert len(recuperados) > 100, "se recupera el contenido sustantivo"
    assert not [r for r in recuperados if r["section"] == "references"]
    malos = [r["text"][:80] for r in recuperados if _es_entrada_bibliografica(r["text"])]
    assert not malos, f"entradas bibliograficas recuperadas: {malos[:3]}"
    # Control: el detector sí ve las referencias que se guardaron.
    guardadas = [c for c, s in zip(chunks, secciones) if s == "references"]
    assert sum(_es_entrada_bibliografica(c) for c in guardadas) > 50
    # Y el texto de referencias sigue en el documento guardado.
    doc = rag._local_collection_dir(col) / "doc-1.json"
    assert "Oliphant" in doc.read_text(encoding="utf-8")


# -- Qdrant: filtro y payload --------------------------------------------------

class _Resp:
    status_code = 200
    text = ""

    def __init__(self, data=None):
        self._d = data or {}

    def json(self):
        return self._d


def _cliente(capturado, resultado=None):
    class _C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, *a, **k):
            return _Resp()

        async def post(self, url, json=None, **k):
            capturado.append((url, json))
            return _Resp({"result": resultado if resultado is not None else []})

        async def put(self, url, json=None, **k):
            capturado.append((url, json))
            return _Resp()
    return _C


@pytest.fixture
def qdrant_vivo(monkeypatch):
    async def _si(*a, **k):
        return True

    async def _vec(*a, **k):
        return [0.1, 0.2]

    monkeypatch.setattr(rag, "is_qdrant_available", _si)
    monkeypatch.setattr(rag, "get_embedding", _vec)
    monkeypatch.setattr(rag, "_anotar_traza", lambda *a, **k: None)


@pytest.mark.asyncio
async def test_upsert_escribe_section_en_el_payload(monkeypatch, qdrant_vivo):
    capturado = []
    monkeypatch.setattr(rag.httpx, "AsyncClient", _cliente(capturado))
    n = await rag.upsert_chunks("http://q", "c", "d", "a", "f.pdf", ["uno", "dos"],
                                "http://o", "m", 2, sections=["methods", "references"])
    assert n == 2
    assert [p["payload"]["section"] for p in capturado[0][1]["points"]] == ["methods", "references"]
    # Sin etiquetas (llamadores antiguos) -> other, nunca ausente.
    capturado.clear()
    await rag.upsert_chunks("http://q", "c", "d", "a", "f.pdf", ["uno"], "http://o", "m", 2)
    assert capturado[0][1]["points"][0]["payload"]["section"] == "other"


@pytest.mark.asyncio
async def test_busqueda_semantica_y_scroll_excluyen_references_en_qdrant(monkeypatch, qdrant_vivo):
    capturado = []
    punto_ref = {"id": "1", "score": 0.9, "payload": {"text": "1. X (2020)", "section": "references"}}
    punto_ok = {"id": "2", "score": 0.8, "payload": {"text": "contenido", "section": "results"}}
    monkeypatch.setattr(rag.httpx, "AsyncClient", _cliente(capturado, [punto_ref, punto_ok]))

    out = await rag.semantic_search_results("q", "http://q", "c", ["a"], "http://o", "m")
    assert [r["text"] for r in out] == ["contenido"]  # defensa en profundidad
    assert _REF in capturado[-1][1]["filter"]["must_not"]

    await rag._fetch_agent_results("http://q", "c", ["a"], 5)
    assert _REF in capturado[-1][1]["filter"]["must_not"]
    await rag.fetch_agent_context("http://q", "c", ["a"])
    assert _REF in capturado[-1][1]["filter"]["must_not"]
