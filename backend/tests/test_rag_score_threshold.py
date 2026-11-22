"""`RAG_SCORE_THRESHOLD` se aplica de verdad (SPEC-034 AC8 / T22.6).

El ajuste existía y ningún llamador lo pasaba: la búsqueda corría con 0.0 y una
fuente con similitud 0,00 llegó a figurar en un artículo. Se arregla en la
capacidad (`score_threshold=None` => ajuste global) para que **no pueda
olvidarse**, y estos tests fallan si alguien lo desmonta:

* un llamador que fija el umbral a un literal 0 / 0.0 (lo apaga a escondidas);
* una firma cuyo default vuelva a ser un número en lugar de «el ajuste»;
* una búsqueda que no mande `score_threshold` a Qdrant;
* un respaldo sin ranking que devuelva fragmentos con el umbral activo.
"""
import ast
import inspect
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.core import config  # noqa: E402
from app.platform.capabilities import rag  # noqa: E402

APP_DIR = ROOT_DIR / "app"
RAG_PY = APP_DIR / "platform" / "capabilities" / "rag.py"
BUSCADORES = {"semantic_search_results", "semantic_search_context", "graph_rag_search_context"}


# ── Estructural: ningún llamador lo omite ni lo apaga ───────────────────────

@pytest.mark.parametrize("funcion", [
    rag.semantic_search_results, rag.semantic_search_context,
])
def test_el_default_es_el_ajuste_y_no_un_numero(funcion):
    por_defecto = inspect.signature(funcion).parameters["score_threshold"].default
    assert por_defecto is None, (
        f"{funcion.__name__}: el default de score_threshold debe ser None "
        "(= RAG_SCORE_THRESHOLD), no un número que desactive el umbral")


def _llamadas_a_buscadores():
    """Llamadas con score_threshold y llamadas directas a los buscadores.

    Los adapters con motor de capacidades llaman a `buscar = provider(...)`, no al
    nombre del buscador; por eso el umbral se vigila en **cualquier** llamada de
    `app/` que lo reciba, y no solo en las que nombran la función.
    """
    for ruta in APP_DIR.rglob("*.py"):
        if ruta == RAG_PY:
            continue
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            f = nodo.func
            nombre = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
            if nombre in BUSCADORES or any(k.arg == "score_threshold" for k in nodo.keywords):
                yield ruta, nodo


def _adapters_que_referencian_buscadores():
    for ruta in APP_DIR.rglob("*.py"):
        if ruta == RAG_PY:
            continue
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            nombre = nodo.id if isinstance(nodo, ast.Name) else (
                nodo.attr if isinstance(nodo, ast.Attribute) else
                nodo.name if isinstance(nodo, ast.alias) else None)
            if nombre in BUSCADORES:
                yield ruta.name
                break


def test_hay_llamadores_y_ninguno_apaga_el_umbral():
    llamadas = list(_llamadas_a_buscadores())
    assert llamadas, "el test estructural no encuentra llamadores: ¿cambió el patrón?"
    for ruta, nodo in llamadas:
        for kw in nodo.keywords:
            if kw.arg != "score_threshold":
                continue
            es_cero = isinstance(kw.value, ast.Constant) and kw.value.value in (0, 0.0)
            assert not es_cero, (
                f"{ruta.relative_to(ROOT_DIR)}:{nodo.lineno} fija score_threshold=0; "
                "deja que lo resuelva la capacidad (RAG_SCORE_THRESHOLD)")


def test_ningun_llamador_busca_en_qdrant_por_su_cuenta():
    """Una búsqueda vectorial propia esquivaría el umbral."""
    for ruta in APP_DIR.rglob("*.py"):
        if ruta == RAG_PY:
            continue
        assert "/points/search" not in ruta.read_text(encoding="utf-8"), (
            f"{ruta.relative_to(ROOT_DIR)} busca en Qdrant sin pasar por rag.py "
            "y por tanto sin RAG_SCORE_THRESHOLD")


def test_los_adapters_que_buscan_no_fijan_el_umbral():
    """Los tres llamadores conocidos (investigador, redactor, generic) heredan el ajuste."""
    rutas = set(_adapters_que_referencian_buscadores())
    assert {"investigador.py", "redactor.py", "generic.py"} <= rutas
    for ruta, nodo in _llamadas_a_buscadores():
        if ruta.name in {"investigador.py", "redactor.py", "generic.py"}:
            assert all(k.arg != "score_threshold" for k in nodo.keywords), (
                f"{ruta.name}:{nodo.lineno} fija el umbral; debe heredarlo")


# ── Comportamiento ──────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._data = data or {}
        self.text = ""

    def json(self):
        return self._data


def _cliente_falso(capturado, puntos):
    class _Cliente:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, *a, **k):
            return _Resp(200)

        async def post(self, url, json=None, **k):
            capturado.append(json)
            return _Resp(200, {"result": puntos})
    return _Cliente


@pytest.fixture
def qdrant_vivo(monkeypatch):
    async def _si(*a, **k):
        return True

    async def _vector(*a, **k):
        return [0.1, 0.2]

    monkeypatch.setattr(rag, "is_qdrant_available", _si)
    monkeypatch.setattr(rag, "get_embedding", _vector)
    monkeypatch.setattr(rag, "_anotar_traza", lambda *a, **k: None)


def _buscar(**extra):
    return rag.semantic_search_results(
        query="q", qdrant_url="http://q", collection="c", agent_name=["investigador"],
        ollama_base_url="http://o", embedding_model="m", **extra)


def _punto(texto, score):
    return {"id": texto, "score": score, "payload": {"text": texto, "doc_id": "d"}}


@pytest.mark.asyncio
async def test_sin_decir_nada_se_manda_el_umbral_de_la_configuracion(monkeypatch, qdrant_vivo):
    monkeypatch.setattr(config.settings, "RAG_SCORE_THRESHOLD", 0.42, raising=False)
    enviados = []
    monkeypatch.setattr(rag.httpx, "AsyncClient", _cliente_falso(enviados, []))
    await _buscar()
    assert enviados[0]["score_threshold"] == pytest.approx(0.42)


@pytest.mark.asyncio
async def test_un_resultado_bajo_el_umbral_no_pasa_aunque_qdrant_lo_devuelva(monkeypatch, qdrant_vivo):
    monkeypatch.setattr(config.settings, "RAG_SCORE_THRESHOLD", 0.3, raising=False)
    puntos = [_punto("bueno", 0.8), _punto("cero", 0.0), _punto("justo-debajo", 0.29)]
    monkeypatch.setattr(rag.httpx, "AsyncClient", _cliente_falso([], puntos))
    out = await _buscar()
    assert [r["text"] for r in out] == ["bueno"]


@pytest.mark.asyncio
async def test_umbral_explicito_gana_y_cero_lo_desactiva(monkeypatch, qdrant_vivo):
    monkeypatch.setattr(config.settings, "RAG_SCORE_THRESHOLD", 0.3, raising=False)
    enviados = []
    monkeypatch.setattr(rag.httpx, "AsyncClient", _cliente_falso(enviados, [_punto("cero", 0.0)]))
    out = await _buscar(score_threshold=0.0)
    assert "score_threshold" not in enviados[0] and len(out) == 1
    await _buscar(score_threshold=0.7)
    assert enviados[1]["score_threshold"] == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_el_wrapper_de_contexto_tambien_aplica_el_umbral(monkeypatch, qdrant_vivo):
    monkeypatch.setattr(config.settings, "RAG_SCORE_THRESHOLD", 0.3, raising=False)
    enviados = []
    monkeypatch.setattr(rag.httpx, "AsyncClient", _cliente_falso(enviados, [_punto("cero", 0.0)]))
    ctx = await rag.semantic_search_context(
        query="q", qdrant_url="http://q", collection="c", agent_name=["x"],
        ollama_base_url="http://o", embedding_model="m")
    assert enviados[0]["score_threshold"] == pytest.approx(0.3) and ctx == ""


# ── Respaldo sin ranking ────────────────────────────────────────────────────

@pytest.fixture
def respaldo_con_fragmentos(monkeypatch):
    llamadas = []

    async def _scroll(*a, **k):
        llamadas.append(a)
        return [{"text": "sin ranking", "doc_id": "d"}]
    monkeypatch.setattr(rag, "_fetch_agent_results", _scroll)
    return llamadas


@pytest.mark.asyncio
@pytest.mark.parametrize("fallo", ["qdrant_caido", "embedding_roto"])
async def test_con_umbral_activo_el_respaldo_no_reintroduce_fragmentos(
        monkeypatch, respaldo_con_fragmentos, fallo):
    monkeypatch.setattr(config.settings, "RAG_SCORE_THRESHOLD", 0.3, raising=False)

    async def _disponible(*a, **k):
        return fallo != "qdrant_caido"

    async def _sin_vector(*a, **k):
        return None
    monkeypatch.setattr(rag, "is_qdrant_available", _disponible)
    monkeypatch.setattr(rag, "get_embedding", _sin_vector)
    assert await _buscar() == []
    assert respaldo_con_fragmentos == []


@pytest.mark.asyncio
async def test_el_respaldo_sigue_con_umbral_cero_o_documentos_elegidos(monkeypatch, respaldo_con_fragmentos):
    async def _caido(*a, **k):
        return False
    monkeypatch.setattr(rag, "is_qdrant_available", _caido)
    monkeypatch.setattr(config.settings, "RAG_SCORE_THRESHOLD", 0.3, raising=False)
    # La persona eligió documentos concretos: esa elección es la señal.
    assert len(await _buscar(doc_ids=["d"])) == 1
    # Filtro desactivado a propósito: comportamiento anterior.
    assert len(await _buscar(score_threshold=0.0)) == 1


def test_el_valor_por_defecto_no_es_cero():
    assert config.Settings.model_fields["RAG_SCORE_THRESHOLD"].default > 0.0
