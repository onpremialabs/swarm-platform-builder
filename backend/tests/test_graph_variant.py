"""Agentes participantes como variante validada del GraphSpec (SPEC-030 / T18.2 / AC2).

Elegir un subconjunto de agentes no es marcar casillas: es construir otra forma de
pipeline. Si esa forma no pasa por la misma validación que el grafo del proyecto,
quitar un agente puede dejar un bucle apuntando a un nodo que no está, y eso
reventaría en mitad de la ejecución — justo lo que T8.4 se construyó para evitar.
"""
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.platform.engine.graph import GraphSpec, InvalidVariant, restrict_to  # noqa: E402
from app.platform.engine.routing import ReviewLoop  # noqa: E402


def _spec_alejandria() -> GraphSpec:
    """La forma real del proyecto de referencia."""
    return GraphSpec(
        sequence=("investigador", "redactor", "revisor", "formateador", "publicador"),
        loops=(ReviewLoop(
            reviewer="revisor", on_reject="redactor",
            threshold=80.0, max_loops=3,
            retry_targets=("investigador", "redactor"),
            on_exhausted="stop",
        ),),
    )


# ── Lo que debe funcionar ───────────────────────────────────────────────────

def test_quitar_el_investigador_deja_un_flujo_valido():
    """El caso corriente: generar sin fase de investigación."""
    variante = restrict_to(_spec_alejandria(),
                           ["redactor", "revisor", "formateador", "publicador"])

    assert variante.sequence == ("redactor", "revisor", "formateador", "publicador")
    assert len(variante.loops) == 1
    # El destino de reintento que ya no participa se filtra; queda el que sí.
    assert variante.loops[0].retry_targets == ("redactor",)


def test_quitar_el_revisor_se_lleva_su_bucle():
    """Sin revisor no hay revisión. No es un error: es lo que se pidió."""
    variante = restrict_to(_spec_alejandria(),
                           ["investigador", "redactor", "formateador", "publicador"])

    assert "revisor" not in variante.sequence
    assert variante.loops == (), "el bucle debe irse con su revisor"


def test_la_secuencia_la_ordena_el_proyecto_no_la_peticion():
    """Un selector de participantes no es un editor de pipeline.

    Si el orden lo pusiera el cliente, esta pantalla se convertiría en un Flow
    Designer paralelo, con su propia forma de equivocarse.
    """
    variante = restrict_to(_spec_alejandria(),
                           ["publicador", "redactor", "investigador"])

    assert variante.sequence == ("investigador", "redactor", "publicador")


def test_un_solo_agente_es_una_variante_valida():
    variante = restrict_to(_spec_alejandria(), ["redactor"])
    assert variante.sequence == ("redactor",)
    assert variante.loops == ()


# ── Lo que debe rechazarse, antes de empezar y con motivo ───────────────────

def test_quitar_el_destino_del_bucle_dejando_al_revisor_se_rechaza():
    """AC2, el caso que le da nombre.

    `GraphSpec.nodes()` vuelve a añadir el destino del bucle aunque no esté en la
    secuencia, porque la arista condicional lo necesita. Es decir: sin esta
    comprobación el redactor se ejecutaría igual y la exclusión no serviría de
    nada, en silencio.
    """
    with pytest.raises(InvalidVariant) as error:
        restrict_to(_spec_alejandria(),
                    ["investigador", "revisor", "formateador", "publicador"])

    mensaje = str(error.value)
    assert "revisor" in mensaje and "redactor" in mensaje
    # El motivo tiene que decir qué hacer, no solo que está mal.
    assert "incluyes" in mensaje or "quitas" in mensaje


def test_un_agente_que_el_proyecto_no_declara_se_rechaza():
    with pytest.raises(InvalidVariant) as error:
        restrict_to(_spec_alejandria(), ["redactor", "traductor"])
    assert "traductor" in str(error.value)


def test_una_seleccion_vacia_se_rechaza():
    with pytest.raises(InvalidVariant):
        restrict_to(_spec_alejandria(), [])
    with pytest.raises(InvalidVariant):
        restrict_to(_spec_alejandria(), ["", "  "])


def test_se_rechaza_antes_de_construir_el_grafo():
    """El error llega al pedirlo, no al ejecutarlo: esa es la diferencia."""
    spec = _spec_alejandria()
    with pytest.raises(InvalidVariant):
        restrict_to(spec, ["revisor"])  # sin su destino de rechazo

    # Y el spec del proyecto no se toca: la variante es un objeto nuevo.
    assert spec.sequence == ("investigador", "redactor", "revisor",
                             "formateador", "publicador")


def test_la_variante_no_muta_el_spec_del_proyecto():
    spec = _spec_alejandria()
    original_loops = spec.loops
    restrict_to(spec, ["redactor", "revisor"])
    assert spec.loops is original_loops
    assert spec.loops[0].retry_targets == ("investigador", "redactor")
