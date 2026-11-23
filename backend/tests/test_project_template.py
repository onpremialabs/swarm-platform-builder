"""Proyectos empaquetados en el filesystem (SPEC-013 / T8.4 / AC4 + AC5).

**AC4**: existe `projects/alejandria-magazine/` con `template.yaml` y
`agents/*.agent.md`, un *loader* lo carga, y `app/agents/` **ya no se referencia
por ruta relativa**.

**AC5**: un proyecto creado desde la plantilla produce el mismo pipeline que el
AlejandrIA de siempre.

Lo que había: cuatro sitios distintos con
`[Path("app/agents"), Path("../app/agents")]` —el runner genérico, la siembra, el
resolutor de modelos y el router—. Son rutas relativas al **directorio de
trabajo**, así que el mismo código encuentra los perfiles arrancando desde
`backend/` y no los encuentra desde la raíz del repo. Y no encontrarlos no
fallaba: se caía a un modelo por defecto y a un prompt genérico, con lo que el
síntoma aparecía lejos de la causa. Hay un test estructural más abajo que impide
que vuelvan.
"""
import ast
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.modules.agents.domain import alejandria  # noqa: E402
from app.platform.engine.agents import get_agent  # noqa: E402
from app.platform.engine.graph import GraphSpec  # noqa: E402
from app.platform.engine.routing import ReviewLoop  # noqa: E402
from app.platform.projects import loader, profiles  # noqa: E402

PLANTILLA_ALEJANDRIA = loader.PROJECTS_ROOT / "alejandria-magazine"

#: La forma que tenía AlejandrIA cuando estaba escrita en Python (T8.3). La
#: plantilla tiene que reproducirla exactamente: es la paridad que pide AC5.
GRAFO_ESPERADO = GraphSpec(
    sequence=("investigador", "redactor", "revisor", "formateador", "publicador"),
    loops=(ReviewLoop(
        reviewer="revisor", on_reject="redactor", threshold=80.0, max_loops=3,
        retry_targets=("investigador", "redactor"),
        # Único cambio deliberado respecto a la forma original: SPEC-032/AC7, agotadas
        # las vueltas sin aprobar el flujo se detiene para revisión humana.
        on_exhausted="stop",
    ),),
)

CAPACIDADES_ESPERADAS = {
    "investigador": ("rag_results", "llm"),
    "redactor": ("rag_results", "llm", "llm_stream"),
    "revisor": ("llm",),
    "formateador": ("llm",),
    "publicador": ("format",),
}


# ── AC4: el proyecto existe como paquete en el filesystem ───────────────────

def test_el_proyecto_esta_empaquetado():
    assert (PLANTILLA_ALEJANDRIA / "template.yaml").is_file()
    perfiles = list((PLANTILLA_ALEJANDRIA / "agents").glob("*.agent.md"))
    assert perfiles, "el proyecto no trae ningún perfil de agente"


def test_ya_no_existe_el_directorio_suelto_de_agentes():
    assert not (ROOT_DIR / "app" / "agents").exists(), (
        "app/agents/ sigue ahí: los perfiles viven en el paquete del proyecto"
    )


def test_ningun_modulo_busca_los_perfiles_con_rutas_relativas():
    """La guardia de AC4. Es un fallo que no se ve: no falla, cae a los defaults.

    Se analiza el **AST** y no el texto: los módulos que arreglaron el problema
    lo explican en sus docstrings, y un `grep` los señalaría a ellos.
    """
    culpables = []
    for fichero in sorted((ROOT_DIR / "app").rglob("*.py")):
        arbol = ast.parse(fichero.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            nombre = getattr(nodo.func, "id", None) or getattr(nodo.func, "attr", None)
            if nombre != "Path":
                continue
            for argumento in nodo.args:
                if isinstance(argumento, ast.Constant) and "app/agents" in str(argumento.value):
                    culpables.append(f"{fichero.relative_to(ROOT_DIR)}:{nodo.lineno}")
    assert culpables == [], f"vuelven a resolverse perfiles por ruta relativa: {culpables}"


def test_el_loader_encuentra_el_proyecto():
    assert "alejandria-magazine" in loader.available_slugs()


def test_la_raiz_de_proyectos_no_depende_del_directorio_de_trabajo():
    """Sale del paquete, no de `os.getcwd()`."""
    assert loader.PROJECTS_ROOT.is_absolute()
    assert loader.PROJECTS_ROOT == ROOT_DIR / "projects"


# ── AC5: la plantilla reproduce el AlejandrIA de siempre ────────────────────

def test_el_grafo_de_la_plantilla_es_el_de_alejandria():
    assert alejandria.graph_spec() == GRAFO_ESPERADO


def test_los_agentes_declaran_las_mismas_capacidades_que_antes():
    paquete = loader.load("alejandria-magazine")
    declarado = {a.name: a.requires for a in paquete.agents}
    assert declarado == CAPACIDADES_ESPERADAS


def test_registrar_la_plantilla_da_de_alta_los_cinco_agentes():
    alejandria.register()
    for nombre, capacidades in CAPACIDADES_ESPERADAS.items():
        spec = get_agent(nombre)
        assert spec is not None, nombre
        assert spec.requires == capacidades
        assert spec.resolve() is not None, f"el entrypoint de '{nombre}' no importa"


def test_cada_agente_declarado_trae_su_perfil():
    paquete = loader.load("alejandria-magazine")
    for spec in paquete.agents:
        ruta = paquete.profile_path(spec.name)
        assert ruta is not None and ruta.is_file(), spec.name


# ── La siembra clona lo que la plantilla declara ────────────────────────────

def test_la_siembra_clona_los_agentes_de_la_plantilla():
    from app.shared.agents_seed import _alejandria_magazine_agents

    sembrados = _alejandria_magazine_agents()
    assert [a["slug"] for a in sembrados] == list(GRAFO_ESPERADO.sequence)


def test_la_siembra_toma_el_modelo_del_perfil_y_no_un_defecto():
    """Si volviera a caer al fallback escrito a mano, todos serían llama3.2:1b."""
    from app.shared.agents_seed import _alejandria_magazine_agents

    frontmatter = yaml.safe_load(
        (PLANTILLA_ALEJANDRIA / "agents" / "investigador.agent.md")
        .read_text(encoding="utf-8").split("---")[1]
    )
    sembrado = next(a for a in _alejandria_magazine_agents() if a["slug"] == "investigador")
    assert sembrado["model"] == frontmatter["model"]
    assert sembrado["temperature"] == pytest.approx(float(frontmatter["temperature"]))


def test_la_siembra_ya_no_arrastra_los_perfiles_que_la_plantilla_no_declara():
    """`pepe.agent.md` dice de sí mismo `flow-designer-persist-test`.

    El `glob("*.agent.md")` de antes lo sembraba como agente de serie en **cada**
    proyecto nuevo, junto con `flowskill`. Siguen siendo cargables como agentes
    dinámicos; lo que ya no son es parte del producto.
    """
    from app.shared.agents_seed import _alejandria_magazine_agents

    sembrados = {a["slug"] for a in _alejandria_magazine_agents()}
    assert "pepe" not in sembrados
    assert "flowskill" not in sembrados
    assert profiles.find("pepe") is not None, "debe seguir siendo cargable"


# ── Validación: una plantilla rota se rechaza al cargarla ───────────────────

def _escribir_proyecto(directorio: Path, plantilla: dict, con_perfil: bool = True) -> Path:
    raiz = directorio / "proyecto-de-prueba"
    (raiz / "agents").mkdir(parents=True)
    if con_perfil:
        (raiz / "agents" / "uno.agent.md").write_text("---\nname: uno\n---\n# Uno\n", encoding="utf-8")
    (raiz / "template.yaml").write_text(yaml.safe_dump(plantilla), encoding="utf-8")
    return raiz


def _plantilla_minima() -> dict:
    return {
        "version": 1,
        "slug": "proyecto-de-prueba",
        "name": "Proyecto de prueba",
        "agents": [{
            "name": "uno",
            "entrypoint": "app.modules.agents.adapters.revisor:run_revisor",
            "requires": ["llm"],
            "profile": "agents/uno.agent.md",
        }],
        "graph": {"sequence": ["uno"]},
    }


def test_un_proyecto_minimo_se_carga(tmp_path):
    """Copiar un directorio y editar un YAML: eso es crear un proyecto."""
    raiz = _escribir_proyecto(tmp_path, _plantilla_minima())
    paquete = loader.load_from(raiz)
    assert paquete.slug == "proyecto-de-prueba"
    assert [a.name for a in paquete.agents] == ["uno"]
    assert paquete.graph.sequence == ("uno",)


@pytest.mark.parametrize(
    "romper, fragmento_del_error",
    [
        (lambda p: p.update(version=99), "no soportada"),
        (lambda p: p.update(agents=[]), "ningún agente"),
        (lambda p: p["agents"][0].update(requires=["inventada"]), "inventada"),
        (lambda p: p["agents"][0].update(entrypoint="sin_dos_puntos"), "entrypoint"),
        (lambda p: p["agents"][0].update(profile="agents/no_esta.agent.md"), "no existe"),
        (lambda p: p["graph"].update(sequence=["fantasma"]), "no está declarado"),
        (lambda p: p["graph"].update(sequence=[]), "vacía"),
        (lambda p: p["graph"].update(review_loops=[{"reviewer": "uno", "on_reject": "nadie"}]),
         "rechaza hacia"),
        (lambda p: p["graph"].update(review_loops=[{"reviewer": "nadie", "on_reject": "uno"}]),
         "revisor desconocido"),
        (lambda p: p["graph"].update(
            review_loops=[{"reviewer": "uno", "on_reject": "uno", "retry_targets": ["nadie"]}]),
         "reintenta hacia"),
        (lambda p: p["agents"].append(dict(p["agents"][0])), "dos veces"),
    ],
)
def test_una_plantilla_rota_se_rechaza_al_cargarla(tmp_path, romper, fragmento_del_error):
    """Y el mensaje dice qué está mal: es lo único que hace un YAML depurable."""
    plantilla = _plantilla_minima()
    romper(plantilla)
    raiz = _escribir_proyecto(tmp_path, plantilla)
    with pytest.raises(loader.TemplateError) as error:
        loader.load_from(raiz)
    assert fragmento_del_error in str(error.value)


def test_un_perfil_que_apunta_fuera_del_proyecto_se_rechaza(tmp_path):
    """`profile: ../../otro/secreto.md` leería ficheros ajenos al proyecto."""
    plantilla = _plantilla_minima()
    plantilla["agents"][0]["profile"] = "../../app/main.py"
    raiz = _escribir_proyecto(tmp_path, plantilla)
    with pytest.raises(loader.TemplateError):
        loader.load_from(raiz)


def test_un_directorio_sin_plantilla_no_es_un_proyecto(tmp_path):
    (tmp_path / "vacio").mkdir()
    with pytest.raises(loader.TemplateError) as error:
        loader.load_from(tmp_path / "vacio")
    assert "template.yaml" in str(error.value)


def test_un_yaml_invalido_se_rechaza(tmp_path):
    raiz = tmp_path / "roto"
    raiz.mkdir()
    (raiz / "template.yaml").write_text("no: [cierro\n", encoding="utf-8")
    with pytest.raises(loader.TemplateError) as error:
        loader.load_from(raiz)
    assert "YAML" in str(error.value)
