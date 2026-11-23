"""BUG-003 — las conexiones del Flow Designer se pueden eliminar.

No hay runner de tests de frontend en el repo (los contratos del lienzo se fijan
con tests estructurales, como `test_flow_designer_run_state.py`). Lo que se fija
aquí es lo que hacía que borrar una conexión no funcionara:

- `deleteKeyCode="Delete"` dejaba sin efecto Retroceso, que en muchos portátiles
  es la única tecla de borrar.
- La arista no tenía botón ni área de clic ancha, y no se anunciaba a un lector
  de pantalla.
"""
from pathlib import Path

FRONT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "platform"
PAGINA = (FRONT / "pages" / "FlowDesignerPage.jsx").read_text(encoding="utf-8")
ARISTA = (FRONT / "components" / "flow" / "DeletableEdge.jsx").read_text(encoding="utf-8")
ALMACEN = (FRONT / "store" / "flowStore.js").read_text(encoding="utf-8")


def test_retroceso_y_suprimir_borran_la_seleccion():
    assert "deleteKeyCode={['Backspace', 'Delete']}" in PAGINA


def test_el_lienzo_usa_la_arista_borrable_para_todas_las_aristas():
    assert "edgeTypes={edgeTypes}" in PAGINA
    # `default` es el tipo de las aristas sin `type`: las ya guardadas también.
    assert "{ default: DeletableEdge }" in ARISTA


def test_la_arista_tiene_area_de_clic_ancha_y_boton_accesible():
    assert "interactionWidth={interactionWidth ?? 28}" in ARISTA
    assert "deleteElements({ edges: [{ id }] })" in ARISTA  # solo la arista, no los nodos
    # El texto vive en el catálogo (T29.7): la arista pide la clave y el catálogo dice «Eliminar».
    import json
    from pathlib import Path
    catalogo = json.loads((Path(__file__).resolve().parents[2] / "frontend/src/platform/i18n/es.json").read_text(encoding="utf-8"))
    assert "aria-label=" in ARISTA and "edge.delete" in ARISTA
    assert catalogo["edge"]["delete"].startswith("Eliminar")
    assert catalogo["edge"]["deleteNamed"].startswith("Eliminar")


def test_el_guardado_persiste_las_aristas_que_quedan():
    # `handleSave` copia las aristas del lienzo al borrador antes de guardar.
    assert "setDraftEdges(edges)" in PAGINA
    assert "edges: draftEdges" in ALMACEN
