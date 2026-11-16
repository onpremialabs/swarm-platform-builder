"""«Ejecutar» en el Flow Designer no debe romper al navegar a la ejecución.

`navigate(url, { state })` acaba en `history.pushState`, que clona el estado con
*structured clone*: una función o un componente de React lo hacen lanzar
`DataCloneError`. El botón mandaba los nodos del lienzo enteros, y desde T8.6 cada
nodo lleva su icono —un componente de lucide— en `data.icon`. El artículo se
creaba, la navegación reventaba y el `catch` lo resumía en «Error al iniciar
pipeline».

Nadie leía esos nodos: la página de ejecución solo usa unas pocas claves del
estado. El test fija ese contrato: lo que manda el lienzo es un subconjunto de lo
que lee la ejecución, así que no puede volver a colarse nada de más.
"""
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[2] / "frontend" / "src"
DISEÑADOR = FRONT / "platform" / "pages" / "FlowDesignerPage.jsx"
#: Quien recibe la navegación. Era `ExecutionPage`; desde T17.1 el lienzo lleva a
#: la vista de trazabilidad, que es la que lee ese estado. El contrato es el
#: mismo —no mandar lo que nadie lee— pero el destino cambió.
EJECUCION = FRONT / "projects" / "alejandria-magazine" / "pages" / "TraceabilityPage.jsx"


def _claves_enviadas() -> set[str]:
    fuente = DISEÑADOR.read_text(encoding="utf-8")
    # El prefijo `/dashboard` es opcional: lo que fija el contrato es el estado
    # que se manda, no bajo qué ruta queda colgada la página.
    bloque = re.search(
        r"navigate\(`(?:/dashboard)?/execution/\$\{articleId\}`,"
        r"\s*\{\s*state:\s*\{(.*?)\}\s*\}\s*\)",
        fuente, re.S,
    )
    assert bloque, "no encuentro la navegación a la ejecución en el Flow Designer"
    return set(re.findall(r"^\s*(\w+)\s*[:,]", bloque.group(1), re.M))


def _claves_leidas() -> set[str]:
    fuente = EJECUCION.read_text(encoding="utf-8")
    return set(re.findall(r"location\.state\?\.(\w+)", fuente))


def test_el_lienzo_solo_manda_lo_que_lee_la_ejecucion():
    enviadas, leidas = _claves_enviadas(), _claves_leidas()
    assert enviadas, "la navegación no manda estado: el regex ya no casa"
    sobrantes = enviadas - leidas
    assert not sobrantes, (
        f"el Flow Designer manda {sorted(sobrantes)} en el estado de navegación y la "
        "ejecución no lo lee; si lleva nodos o componentes, pushState lanza DataCloneError"
    )


def test_no_manda_los_nodos_del_lienzo():
    """Los nodos llevan `data.icon` (un componente): no son clonables."""
    enviadas = _claves_enviadas()
    assert not enviadas & {"flowNodes", "flowEdges", "nodes", "edges"}
