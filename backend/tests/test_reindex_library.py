"""Reindexado de la biblioteca previa a AC15 (SPEC-034 AC17 / T22.16).

Defiende: reclasifica por ``section`` sin duplicar ni perder fragmentos ni tocar
doc_id/DOI/curacion; idempotente; simulacro sin escribir; aislamiento por proyecto.
"""
import copy
import json
import re
import sys
import uuid
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.platform.capabilities import rag, reindex  # noqa: E402
from app.platform.capabilities.rag import chunk_text  # noqa: E402
from app.platform.project_context import ProjectContext  # noqa: E402


def _bibliografia(n=40):
    return "\n".join(
        f"{i}. Autor{i}, A. B. & Otro, C. Titulo del trabajo numero {i}. J. Ejemplo {i}, "
        f"{10 + i}-{20 + i} ({1990 + i % 30}). doi:10.1000/ejemplo.{i}" for i in range(1, n + 1))


TEXTO = ("Introduction\n" + "Contenido sustantivo sobre el tema estudiado. " * 40
         + "\n\nResults\n" + "Los resultados muestran una mejora clara. " * 40
         + "\n\nReferences\n" + _bibliografia())


def _payloads(doc_id="d1", texto=TEXTO, **extra):
    chunks = chunk_text(texto, chunk_size=300, overlap=30)
    return [{"doc_id": doc_id, "chunk_index": i, "text": t, "doi": "10.1/x",
             "filename": "a.pdf", **extra} for i, t in enumerate(chunks)]


# -- Clasificacion ------------------------------------------------------------

def test_clasifica_con_encabezados_conservados():
    texto = ("Introduction\n\n" + "\n\n".join(f"Parrafo de contenido numero {i}." for i in range(30))
             + "\n\nResults\n\n" + "\n\n".join(f"Resultado {i} claro." for i in range(30))
             + "\n\nReferences\n" + _bibliografia(15).replace("\n", "\n\n"))
    secs = reindex.clasificar_fragmentos([p["text"] for p in _payloads(texto=texto)])
    assert secs[0] == "introduction"
    assert "results" in secs and "references" in secs
    primero = secs.index("references")
    assert set(secs[primero:]) == {"references"}  # una vez en referencias, no vuelve
    assert "references" not in secs[:primero]


def test_encabezado_perdido_por_el_troceado_antiguo_cola_bibliografica():
    # TEXTO tiene parrafos largos: chunk_text los parte por palabras y el encabezado se pierde.
    secs = reindex.clasificar_fragmentos([p["text"] for p in _payloads()])
    assert secs.count("references") >= 3
    primero = secs.index("references")
    assert set(secs[primero:]) == {"references"}
    assert set(secs[:primero]) == {"other"}  # el contenido nunca se esconde


def test_un_fragmento_aislado_con_muchas_fechas_no_es_referencia():
    citas = ("Estudios previos (Garcia 2010; Lopez 2011; Ruiz 2012; Diaz 2013; Mora 2014; "
             "Vega 2015; Sanz 2016) coinciden en este punto. ") * 3
    textos = ["Contenido normal " * 30, citas, "Mas contenido normal " * 30, "Cierre " * 30]
    assert set(reindex.clasificar_fragmentos(textos)) == {"other"}


def test_sin_encabezados_todo_es_other():
    secs = reindex.clasificar_fragmentos([p["text"] for p in _payloads(texto="Parrafo. " * 300)])
    assert set(secs) == {"other"}


# -- Qdrant simulado ----------------------------------------------------------

class _Resp:
    def __init__(self, data=None, status=200):
        self._d, self.status_code = data or {}, status

    def json(self):
        return self._d

    def raise_for_status(self):
        pass


class _Qdrant:
    def __init__(self, colecciones):
        self.cols = colecciones  # nombre -> {id: payload}
        self.escrituras = 0

    def cliente(self):
        q = self

        class C:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, **k):
                if url == "/collections":
                    return _Resp({"result": {"collections": [{"name": n} for n in q.cols]}})
                nombre = url.rsplit("/", 1)[1]
                return _Resp(status=200 if nombre in q.cols else 404)

            async def post(self, url, json=None, **k):
                nombre = url.split("/")[2]
                if url.endswith("/points/scroll"):
                    pts = [{"id": i, "payload": copy.deepcopy(p)} for i, p in q.cols[nombre].items()]
                    return _Resp({"result": {"points": pts, "next_page_offset": None}})
                assert url.split("?")[0].endswith("/points/payload")
                q.escrituras += 1
                for i in json["points"]:
                    q.cols[nombre][i].update(json["payload"])
                return _Resp()

        return C


def _coleccion(payloads):
    return {str(uuid.uuid4()): p for p in payloads}


@pytest.fixture
def qdrant(monkeypatch):
    ctx_a = ProjectContext(project_id=uuid.uuid4())
    ctx_b = ProjectContext(project_id=uuid.uuid4())
    q = _Qdrant({
        ctx_a.collection("__library__"): _coleccion(_payloads("d1")),
        ctx_b.collection("__library__"): _coleccion(_payloads("d2")),
        "rag_docs": _coleccion(_payloads("legado")),
    })
    monkeypatch.setattr(reindex.httpx, "AsyncClient", q.cliente())

    async def _si(*a, **k):
        return True
    monkeypatch.setattr(rag, "is_qdrant_available", _si)
    monkeypatch.setattr(rag, "_local_rag_root", lambda: Path("/no/existe/rag"))
    monkeypatch.setattr(reindex, "colecciones_locales_del_proyecto", lambda ctx: [])
    return q, ctx_a, ctx_b


@pytest.mark.asyncio
async def test_simulacro_no_escribe(qdrant):
    q, a, _ = qdrant
    antes = copy.deepcopy(q.cols)
    res = await reindex.reindexar_proyecto(a, "http://q", aplicar=False)
    assert q.cols == antes and q.escrituras == 0
    assert res[0].referencias > 0 and res[0].sin_seccion == res[0].fragmentos


@pytest.mark.asyncio
async def test_aplicar_etiqueta_sin_perder_ni_alterar_y_es_idempotente(qdrant):
    q, a, b = qdrant
    nombre = a.collection("__library__")
    antes = copy.deepcopy(q.cols[nombre])
    res = await reindex.reindexar_proyecto(a, "http://q", aplicar=True)

    despues = q.cols[nombre]
    assert despues.keys() == antes.keys()  # mismos puntos: ni duplicados ni perdidos
    for pid, pl in despues.items():
        resto = {k: v for k, v in pl.items() if k != "section"}
        assert resto == antes[pid]  # doc_id, doi, texto... intactos
        assert pl["section"]
    assert sum(1 for p in despues.values() if p["section"] == "references") == res[0].referencias > 0

    # Idempotente: segunda pasada no escribe nada.
    escrituras, estado = q.escrituras, copy.deepcopy(q.cols)
    res2 = await reindex.reindexar_proyecto(a, "http://q", aplicar=True)
    assert q.escrituras == escrituras and q.cols == estado
    assert res2[0].sin_seccion == 0 and res2[0].reclasificados == {}


@pytest.mark.asyncio
async def test_aislamiento_otro_proyecto_y_legado_no_se_tocan(qdrant):
    q, a, b = qdrant
    antes_b = copy.deepcopy(q.cols[b.collection("__library__")])
    antes_legado = copy.deepcopy(q.cols["rag_docs"])
    await reindex.reindexar_proyecto(a, "http://q", aplicar=True)
    assert q.cols[b.collection("__library__")] == antes_b
    assert q.cols["rag_docs"] == antes_legado


@pytest.mark.asyncio
async def test_no_pisa_section_ya_existente(qdrant):
    q, a, _ = qdrant
    nombre = a.collection("__library__")
    pid = next(iter(q.cols[nombre]))
    q.cols[nombre][pid]["section"] = "methods"
    await reindex.reindexar_proyecto(a, "http://q", aplicar=True)
    assert q.cols[nombre][pid]["section"] == "methods"


# -- Respaldo local -----------------------------------------------------------

def test_respaldo_local(monkeypatch, tmp_path):
    ctx = ProjectContext(project_id=uuid.uuid4())
    otro = ProjectContext(project_id=uuid.uuid4())
    monkeypatch.setattr(rag, "_local_rag_root", lambda: tmp_path)
    for c, did in ((ctx, "d1"), (otro, "d2")):
        d = tmp_path / c.collection("__library__")
        d.mkdir()
        doc = {"doc_id": did, "doc_title": "T", "filename": "a.pdf",
               "chunks": [{"chunk_index": p["chunk_index"], "text": p["text"]} for p in _payloads(did)]}
        (d / f"{did}.json").write_text(json.dumps(doc), encoding="utf-8")
    ajeno = tmp_path / otro.collection("__library__") / "d2.json"
    ajeno_antes = ajeno.read_text(encoding="utf-8")
    propio = tmp_path / ctx.collection("__library__") / "d1.json"
    n = len(json.loads(propio.read_text(encoding="utf-8"))["chunks"])

    nombres = reindex.colecciones_locales_del_proyecto(ctx)
    assert nombres == [ctx.collection("__library__")]

    r = reindex.reindexar_local(nombres[0], aplicar=False)
    assert "section" not in json.loads(propio.read_text(encoding="utf-8"))["chunks"][0]
    assert r.referencias > 0

    reindex.reindexar_local(nombres[0], aplicar=True)
    doc = json.loads(propio.read_text(encoding="utf-8"))
    assert len(doc["chunks"]) == n and doc["doc_title"] == "T" and doc["doc_id"] == "d1"
    assert all(c["section"] for c in doc["chunks"])
    assert any(c["section"] == "references" for c in doc["chunks"])
    assert reindex.reindexar_local(nombres[0], aplicar=True).reclasificados == {}
    assert ajeno.read_text(encoding="utf-8") == ajeno_antes


# -- Estructurales ------------------------------------------------------------

def test_modulo_no_toca_curacion_ni_mapas_de_citas_ni_compone_colecciones():
    src = (ROOT_DIR / "app/platform/capabilities/reindex.py").read_text(encoding="utf-8")
    codigo = src.split('"""', 2)[2]
    assert not re.search(r"agent_run|AgentRun|curat|ProjectModel|AsyncSessionLocal", codigo)
    assert not re.search(r"f\"p_|PREFIJO_PROYECTO|\.collection\(", codigo)
    assert "upsert" not in codigo and "/points/delete" not in codigo
