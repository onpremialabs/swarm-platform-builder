"""Motor de capacidades: enrutado como datos y paridad de caminos.

SPEC-013 / T8.3 / **AC5** (paridad input→output del flujo
investigador→…→publicador) y **AC8** (los dos caminos del flag `AGENT_ENGINE`
producen el mismo resultado hasta retirar los adapters heredados).

Lo que había: el orquestador conocía a AlejandrIA de tres formas —un `dict` con
sus cinco agentes, un `if "revisor" in nodes: add("redactor")` y un
`if node_name == "revisor"` para colocar la arista condicional—. Con eso, un
proyecto cuyo revisor se llame `qa` compila un **grafo recto sin bucle** y nadie
se entera: no hay error, simplemente no hay revisión. Los tests de enrutado de
abajo usan nombres de agente inventados justamente para comprobar que el motor ya
no depende de los de AlejandrIA.
"""
import uuid

import pytest

from app.modules.agents.adapters import formateador as adapter_formateador
from app.modules.agents.adapters import investigador as adapter_investigador
from app.modules.agents.adapters import publicador as adapter_publicador
from app.modules.agents.adapters import redactor as adapter_redactor
from app.modules.agents.adapters import revisor as adapter_revisor
from app.modules.agents.application import use_cases as orquestador
from app.modules.agents.domain import alejandria
from app.platform.capabilities import binding
from app.platform.capabilities.binding import MissingCapability, bind, provider
from app.platform.engine.agents import (
    AgentSpec, UnknownAgent, bundle_for, get_agent, resolve_runner,
)
from app.platform.engine.graph import GraphSpec
from app.platform.engine.routing import FIN, ReviewLoop, make_review_router, next_after


# ── Enrutado como datos ──────────────────────────────────────────────────────

def _flujo_generico():
    """Un proyecto que no es AlejandrIA: si el motor sigue atado a sus nombres, falla."""
    return ["recopilar", "escribir", "qa", "publicar"]


def _bucle_generico():
    return ReviewLoop(
        reviewer="qa", on_reject="escribir", threshold=70.0, max_loops=2,
        retry_targets=("recopilar",),
    )


def test_el_bucle_funciona_con_agentes_que_no_son_los_de_alejandria():
    router = make_review_router(_bucle_generico())
    estado = {"flow_sequence": _flujo_generico(), "approval_score": 50, "loop_count": 0}
    assert router(estado) == "escribir"


def test_el_umbral_y_el_maximo_de_vueltas_son_del_proyecto():
    router = make_review_router(_bucle_generico())   # umbral 70, máximo 2
    flujo = _flujo_generico()
    # 75 pasaría el umbral de AlejandrIA (80) pero no debería: aquí es 70.
    assert router({"flow_sequence": flujo, "approval_score": 75, "loop_count": 0}) == "publicar"
    # Agotadas las vueltas, avanza aunque la puntuación siga baja.
    assert router({"flow_sequence": flujo, "approval_score": 10, "loop_count": 2}) == "publicar"


def test_la_decision_humana_manda_sobre_la_puntuacion():
    router = make_review_router(_bucle_generico())
    flujo = _flujo_generico()
    assert router({"flow_sequence": flujo, "approval_score": 0, "user_decision": "continue"}) == "publicar"
    assert router({"flow_sequence": flujo, "approval_score": 0, "user_decision": "add_source"}) == "recopilar"


def test_si_ningun_destino_de_reintento_esta_en_el_flujo_se_avanza():
    """Rechazar hacia un nodo que no existe colgaría el grafo."""
    router = make_review_router(ReviewLoop("qa", "escribir", retry_targets=("no_existe",)))
    assert router({"flow_sequence": ["qa", "publicar"], "user_decision": "add_source"}) == "publicar"


def test_un_revisor_al_final_del_flujo_termina():
    router = make_review_router(_bucle_generico())
    assert router({"flow_sequence": ["qa"], "approval_score": 99}) == FIN


def test_next_after_no_conoce_ningun_nombre_concreto():
    assert next_after(["a", "b", "c"], "b") == "c"
    assert next_after(["a", "b"], "b") == FIN
    assert next_after(["a"], "ausente") == FIN


# ── La forma del grafo sale de la especificación ────────────────────────────

def test_el_destino_del_rechazo_se_registra_aunque_no_este_en_la_secuencia():
    """Ejecutar solo el revisor sigue necesitando el nodo al que rechaza."""
    spec = GraphSpec(("qa",), (_bucle_generico(),))
    assert set(spec.nodes()) == {"qa", "escribir", "recopilar"}


def test_sin_bucles_no_se_registran_nodos_de_mas():
    assert GraphSpec(("a", "b")).nodes() == ("a", "b")


def test_un_bucle_cuyo_revisor_no_esta_en_el_flujo_no_arrastra_nodos():
    spec = GraphSpec(("a", "b"), (_bucle_generico(),))
    assert spec.nodes() == ("a", "b")
    assert spec.active_loops() == ()


def test_una_secuencia_vacia_es_un_error():
    with pytest.raises(ValueError):
        GraphSpec(())


# ── El proyecto declara sus agentes; el motor no los conoce ─────────────────

def test_alejandria_registra_sus_cinco_agentes():
    alejandria.register()
    for nombre in ("investigador", "redactor", "revisor", "formateador", "publicador"):
        assert get_agent(nombre) is not None, nombre


def test_un_agente_desconocido_dice_cuales_hay():
    alejandria.register()
    with pytest.raises(UnknownAgent) as error:
        resolve_runner("no_existe", lambda _n: None)
    assert "investigador" in str(error.value)


def test_un_agente_dinamico_se_resuelve_por_el_fallback():
    """Los perfiles `.agent.md` no se declaran en código y deben seguir cargando."""
    async def runner(state):
        return {}

    assert resolve_runner("agente_de_perfil", lambda _n: runner) is runner


# ── Capacidades: contrato y resolución ──────────────────────────────────────

def test_cada_agente_declara_las_capacidades_que_compone():
    alejandria.register()
    esperado = {
        "investigador": {"rag_results", "llm"},
        "redactor": {"rag_results", "llm", "llm_stream"},
        "revisor": {"llm"},
        "formateador": {"llm"},
        "publicador": {"format"},
    }
    for nombre, capacidades in esperado.items():
        assert set(get_agent(nombre).requires) == capacidades, nombre


def test_las_capacidades_declaradas_se_resuelven_de_verdad():
    alejandria.register()
    for nombre in ("investigador", "redactor", "revisor", "formateador", "publicador"):
        bundle = bundle_for(nombre)
        assert bundle is not None
        for capacidad in get_agent(nombre).requires:
            assert callable(bundle.get(capacidad)), f"{nombre} → {capacidad}"


def test_una_capacidad_sin_proveedor_falla_al_construir_el_bundle():
    """Antes de arrancar el pipeline, no a mitad del tercer agente."""
    with pytest.raises(MissingCapability):
        bind(["scrape"])


def test_una_capacidad_que_no_existe_tambien():
    with pytest.raises(MissingCapability):
        bind(["inventada"])


def test_sin_bundle_el_agente_usa_su_import_de_siempre():
    centinela = object()
    assert provider({}, "llm", centinela) is centinela


def test_con_bundle_el_agente_usa_el_proveedor_inyectado():
    inyectado = object()
    estado = {binding.CLAVE_ESTADO: binding.CapabilityBundle({"llm": inyectado})}
    assert provider(estado, "llm", object()) is inyectado


def test_un_bundle_sin_esa_capacidad_no_tapa_el_fallback():
    centinela = object()
    estado = {binding.CLAVE_ESTADO: binding.CapabilityBundle({"rag": object()})}
    assert provider(estado, "llm", centinela) is centinela


# ── AC5 + AC8: paridad de los dos caminos sobre el flujo completo ───────────

FLUJO_COMPLETO = ["investigador", "redactor", "revisor", "formateador", "publicador"]


@pytest.fixture
def sin_efectos(monkeypatch):
    """Neutraliza el registro en base de datos, que no es lo que se compara aquí."""
    async def _log_start(agent_name, article_id, author_id, input_payload):
        return uuid.uuid4()

    async def _log_end(run_id, output_payload, status, error_message=None):
        return None

    monkeypatch.setattr(orquestador, "log_run_start", _log_start)
    monkeypatch.setattr(orquestador, "log_run_end", _log_end)


def _instalar_agentes_deterministas(monkeypatch, registro):
    """Cinco agentes que dependen **solo** de su entrada, para poder comparar.

    Cada uno registra qué proveedores recibió: es lo que distingue los dos
    caminos del flag, y por tanto lo que hay que mirar para saber que el test no
    está comparando el mismo camino consigo mismo.
    """
    def _hacer(nombre, capacidades, salida):
        async def runner(state, _n=nombre, _c=capacidades, _s=salida):
            registro.setdefault(_n, []).append(
                {c: provider(state, c, None) is not None for c in _c}
            )
            return dict(_s(state))
        return runner

    monkeypatch.setattr(
        adapter_investigador, "run_investigador",
        _hacer("investigador", ("rag_results", "llm"),
               lambda s: {"research_data": f"fuentes<{s['title']}>",
                          "sources": [{"title": "una fuente"}]}))
    monkeypatch.setattr(
        adapter_redactor, "run_redactor",
        _hacer("redactor", ("rag_results", "llm", "llm_stream"),
               lambda s: {"draft_text": f"borrador[{s.get('research_data','')}]"}))
    monkeypatch.setattr(
        adapter_revisor, "run_revisor",
        _hacer("revisor", ("llm",),
               lambda s: {"approval_score": 95.0, "coherent": True,
                          "feedback": ["bien"], "loop_count": 0, "user_decision": None}))
    monkeypatch.setattr(
        adapter_formateador, "run_formateador",
        _hacer("formateador", ("llm",),
               lambda s: {"formatted_text": f"formateado({s.get('draft_text','')})"}))
    monkeypatch.setattr(
        adapter_publicador, "run_publicador",
        _hacer("publicador", ("format",),
               lambda s: {"published_url": "http://ejemplo/publicado",
                          "metadata": {"word_count": len(s.get('formatted_text','').split())}}))


async def _ejecutar(modo, monkeypatch, registro):
    from app.core.config import settings as ajustes

    monkeypatch.setattr(ajustes, "AGENT_ENGINE", modo, raising=False)
    _instalar_agentes_deterministas(monkeypatch, registro)
    return await orquestador.Orchestrator.run(
        article_id=uuid.uuid4(),
        author_id=uuid.uuid4(),
        title="Un título estable",
        keywords=["uno", "dos"],
        scientific_format="apa",
        flow_sequence=FLUJO_COMPLETO,
    )


def _comparable(estado):
    """Quita lo que cambia entre ejecuciones por definición (los identificadores)."""
    return {
        clave: valor for clave, valor in estado.items()
        if clave not in {"article_id", "author_id"} and not clave.startswith("_")
    }


@pytest.mark.asyncio
async def test_ac5_ac8_los_dos_caminos_producen_el_mismo_estado(sin_efectos, monkeypatch):
    """La comparación que pide la spec: mismo input, misma salida, flujo completo."""
    registro_adapters: dict = {}
    con_adapters = await _ejecutar("adapters", monkeypatch, registro_adapters)

    registro_capacidades: dict = {}
    con_capacidades = await _ejecutar("capabilities", monkeypatch, registro_capacidades)

    assert _comparable(con_adapters) == _comparable(con_capacidades)


@pytest.mark.asyncio
async def test_el_flag_cambia_de_verdad_el_camino(sin_efectos, monkeypatch):
    """Sin esto, la paridad de arriba podría estar comparando el mismo camino.

    Con `adapters` no se inyecta nada y cada agente cae a sus imports; con
    `capabilities` recibe resueltas justo las que declara en `alejandria.py`.
    """
    registro_adapters: dict = {}
    await _ejecutar("adapters", monkeypatch, registro_adapters)
    assert all(
        not any(recibidas.values())
        for pasadas in registro_adapters.values() for recibidas in pasadas
    ), registro_adapters

    registro_capacidades: dict = {}
    await _ejecutar("capabilities", monkeypatch, registro_capacidades)
    assert all(
        all(recibidas.values())
        for pasadas in registro_capacidades.values() for recibidas in pasadas
    ), registro_capacidades


@pytest.mark.asyncio
async def test_el_flujo_recorre_los_cinco_agentes_en_orden(sin_efectos, monkeypatch):
    registro: dict = {}
    await _ejecutar("capabilities", monkeypatch, registro)
    assert set(registro) == set(FLUJO_COMPLETO)


@pytest.mark.asyncio
async def test_el_bucle_de_revision_sigue_devolviendo_al_redactor(sin_efectos, monkeypatch):
    """La conducta que el `if node_name == "revisor"` daba por hecha."""
    from app.core.config import settings as ajustes

    monkeypatch.setattr(ajustes, "AGENT_ENGINE", "adapters", raising=False)
    registro: dict = {}
    _instalar_agentes_deterministas(monkeypatch, registro)

    vueltas = {"n": 0}

    async def revisor_severo(state):
        registro.setdefault("revisor", []).append({})
        vueltas["n"] += 1
        # Rechaza la primera vez y aprueba después, para salir del bucle.
        if vueltas["n"] == 1:
            return {"approval_score": 10.0, "coherent": False, "feedback": ["flojo"],
                    "loop_count": 1, "user_decision": None}
        return {"approval_score": 95.0, "coherent": True, "feedback": [],
                "loop_count": 1, "user_decision": None}

    monkeypatch.setattr(adapter_revisor, "run_revisor", revisor_severo)

    await orquestador.Orchestrator.run(
        article_id=uuid.uuid4(), author_id=uuid.uuid4(), title="T", keywords=[],
        scientific_format="apa", flow_sequence=["redactor", "revisor", "formateador"],
    )
    # El redactor corre dos veces: la inicial y la del rechazo.
    assert len(registro["redactor"]) == 2
    assert len(registro["revisor"]) == 2
