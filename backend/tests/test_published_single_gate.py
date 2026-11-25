"""SPEC-037 AC8 / T25.8 — ningún camino llega a `published` sin la puerta única.

SPEC-032/ADR-0011 centraliza la decisión en `platform/publication_gate/decision.py`
(`can_publish` decide, `assign_published` asigna). `test_can_publish.py` ya fija la
tabla de verdad y los dos endpoints; aquí se cierra lo que faltaba:

1. **Estructural**: nadie asigna PUBLISHED por otra vía (atributo, `setattr`,
   `status=` en un constructor o `.values()`, dict, SQL crudo) y cada llamada a
   `assign_published` lleva una decisión de `can_publish` o una de las dos
   excepciones declaradas (proyecto sin `gate:` y siembra de desarrollo).
2. **Los DTO de escritura no admiten `status`**: no se publica rellenando un campo.
3. **De extremo a extremo**: un flujo guardado (`SavedFlow`) con solo
   Redactor -> Revisor -> Publicador —el «Flujo rápido de publicación»— deja el
   artículo fuera de `published`, con informe de compuerta, sin aprobación ni fecha
   de publicación; solo `approve` lo publica.
"""
import ast
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from test_project_isolation import (  # noqa: F401  (fixtures y ayudas de ese módulo)
    _cabeceras, _proyecto, _token, _usuario, client, db,
)
from app.core.database import AsyncSessionLocal
from app.models import (
    ArticleModel, ArticleStatus, PublicationGateReportModel, SavedFlowModel, UserRole,
)
from app.platform.publication_gate import gate as gate_module
from app.platform.publication_gate.types import CriterionResult, CriterionStatus

APP = Path(__file__).resolve().parents[1] / "app"
DECISION = APP / "platform" / "publication_gate" / "decision.py"
DOMINIO_HUERFANO = APP / "modules" / "articles"  # lo vigila test_can_publish.py


def _fuentes():
    for ruta in sorted(APP.rglob("*.py")):
        if ruta == DECISION or DOMINIO_HUERFANO in ruta.parents:
            continue
        yield ruta, ruta.read_text(encoding="utf-8")


def _es_published(nodo) -> bool:
    """`ArticleStatus.PUBLISHED`, `X.PUBLISHED` o la cadena "published"."""
    if isinstance(nodo, ast.Attribute):
        return nodo.attr == "PUBLISHED"
    if isinstance(nodo, ast.Constant):
        return nodo.value == "published"
    return False


def _apunta_a_status(nodo) -> bool:
    return (isinstance(nodo, ast.Attribute) and nodo.attr == "status") or (
        isinstance(nodo, ast.Name) and nodo.id == "status")


def _nombre_llamada(nodo: ast.Call) -> str:
    f = nodo.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")


# ── 1. Estructural ──────────────────────────────────────────────────────────

def test_ninguna_via_asigna_published_fuera_de_la_puerta():
    culpables = []
    for ruta, texto in _fuentes():
        rel = ruta.relative_to(APP)
        for nodo in ast.walk(ast.parse(texto)):
            if isinstance(nodo, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                objetivos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
                if nodo.value is not None and _es_published(nodo.value) \
                        and any(_apunta_a_status(t) for t in objetivos):
                    culpables.append(f"{rel}:{nodo.lineno}: asignación directa")
            elif isinstance(nodo, ast.Call):
                nombre = _nombre_llamada(nodo)
                # status=PUBLISHED en constructores (ArticleModel(...)) y en .values(...)
                for kw in nodo.keywords:
                    if kw.arg == "status" and _es_published(kw.value):
                        culpables.append(f"{rel}:{nodo.lineno}: status= en {nombre}(...)")
                if nombre == "setattr" and len(nodo.args) == 3:
                    a = nodo.args[1]
                    if isinstance(a, ast.Constant) and a.value == "status" and _es_published(nodo.args[2]):
                        culpables.append(f"{rel}:{nodo.lineno}: setattr(..., 'status', PUBLISHED)")
            elif isinstance(nodo, ast.Dict):
                for k, v in zip(nodo.keys, nodo.values):
                    if isinstance(k, ast.Constant) and k.value == "status" and _es_published(v):
                        culpables.append(f"{rel}:{nodo.lineno}: dict con status PUBLISHED")
        # SQL crudo: UPDATE articles SET status = 'published'
        if re.search(r"(?is)\bupdate\b[^;]*\bset\b[^;]*\bstatus\b\s*=\s*.?published", texto):
            culpables.append(f"{rel}: SQL crudo que fija status = published")
    assert culpables == [], "PUBLISHED se asigna fuera de decision.py:\n" + "\n".join(culpables)


# Quién puede llamar a `assign_published`, y de dónde sale la decisión que le pasa.
LLAMADORES = {
    "main.py": {"dev_seed_decision"},                               # siembra, tras ENABLE_DEV_SEED
    "modules/agents/adapters/publicador.py": {"legacy_decision"},    # solo si el proyecto no declara gate:
    "routers/articles.py": {"decision"},                             # sale de can_publish o legacy_decision
}


def test_assign_published_solo_lo_llaman_los_sitios_conocidos():
    encontrados: dict[str, list] = {}
    for ruta, texto in _fuentes():
        for nodo in ast.walk(ast.parse(texto)):
            if isinstance(nodo, ast.Call) and _nombre_llamada(nodo) == "assign_published":
                encontrados.setdefault(ruta.relative_to(APP).as_posix(), []).append(nodo)
    assert set(encontrados) == set(LLAMADORES), (
        "Cambió quién llama a assign_published: un camino nuevo a `published` debe pasar "
        f"por can_publish y declararse aquí. Hoy: {sorted(encontrados)}")
    for rel, llamadas in encontrados.items():
        for llamada in llamadas:
            arg = llamada.args[1] if len(llamada.args) > 1 else None
            visto = _nombre_llamada(arg) if isinstance(arg, ast.Call) else getattr(arg, "id", None)
            assert visto in LLAMADORES[rel], f"{rel}:{llamada.lineno} pasa una decisión no prevista ({visto})"


def test_la_decision_de_articles_sale_de_can_publish():
    """En `articles.py` la decisión es `legacy_decision()` (proyecto sin `gate:`) o el
    resultado de `can_publish`, con 409 si no está permitida, antes de asignar."""
    texto = (APP / "routers" / "articles.py").read_text(encoding="utf-8")
    cuerpo = texto[texto.index("async def _publish_through_the_gate"):]
    antes = cuerpo[:cuerpo.index("assign_published(article, decision)")]
    assert "decision = can_publish(" in antes
    assert "if not decision.allowed" in antes and "status_code=409" in antes
    assert "decision = legacy_decision()" in antes


def test_los_endpoints_que_publican_pasan_por_la_funcion_con_la_puerta():
    """`approve` y `publish` delegan en `_publish_through_the_gate`; ninguna otra
    ruta de `routers/` llama a `assign_published`."""
    tree = ast.parse((APP / "routers" / "articles.py").read_text(encoding="utf-8"))
    delegan = {
        f.name for f in ast.walk(tree)
        if isinstance(f, ast.AsyncFunctionDef)
        and any(isinstance(n, ast.Call) and _nombre_llamada(n) == "_publish_through_the_gate"
                for n in ast.walk(f))
    }
    assert len(delegan) == 2 and any("approve" in n for n in delegan) and any("publish" in n for n in delegan), delegan
    for ruta, texto in _fuentes():
        if ruta.parent.name == "routers" and ruta.name != "articles.py":
            assert "assign_published" not in texto, ruta


# ── 2. Los DTO de escritura no traen `status` ───────────────────────────────

def test_ningun_dto_de_escritura_de_articulos_admite_status():
    from app.models import article as modelo

    revisados = []
    for nombre, cls in vars(modelo).items():
        campos = getattr(cls, "model_fields", None)
        if campos is None or not nombre.endswith(("DTO", "Request", "Create", "Update")):
            continue
        revisados.append(nombre)
        assert "status" not in campos, f"{nombre} permite fijar `status` desde el cliente"
    assert revisados, "no se encontró ningún DTO de escritura: el test dejó de medir"


# ── 3. El «Flujo rápido de publicación» de punta a punta ─────────────────────

FUENTE = {"title": "Deep learning", "authors": "LeCun, Bengio, Hinton", "year": "2015",
          "journal": "Nature", "doi": "10.1038/nature14539"}
RAPIDO = ["redactor", "revisor", "publicador"]
IMRAD = "\n\n".join(f"## {t}\nTexto." for t in
                    ("Introducción", "Metodología", "Resultados", "Discusión", "Referencias")) + "\n"
# Entero para el Redactor (T24.10: uno incompleto ya no llega aqui) pero con el orden roto: la
# compuerta lo bloquea (`out_of_order`).
INCOMPLETO = "\n\n".join(f"## {t}\nTexto." for t in
                         ("Metodología", "Introducción", "Resultados", "Discusión", "Referencias")) + "\n"


@pytest.fixture
def _sin_red(monkeypatch):
    async def ok(sources, cfg, **kw):
        return CriterionResult("reference_existence", CriterionStatus.PASSED, []), list(sources)

    monkeypatch.setattr(gate_module, "check_reference_existence", ok)


def _llm_falso(monkeypatch, cuerpo):
    import app.modules.agents.adapters.redactor as redactor_adapter
    import app.modules.agents.adapters.revisor as revisor_adapter
    from app.modules.agents.application import use_cases as orquestador

    async def noop_start(*a, **k):
        return uuid.uuid4()

    async def noop_end(*a, **k):
        return None

    async def llm(prompt, **kwargs):
        return '{"approval_score": 95, "feedback": []}'

    async def llm_stream(prompt, **kwargs):
        __import__("app.platform.llm", fromlist=["x"])._anotar_motivo_parada("stop")  # el proveedor declara fin natural
        for t in cuerpo.splitlines(keepends=True):
            yield t

    monkeypatch.setattr(orquestador, "log_run_start", noop_start)
    monkeypatch.setattr(orquestador, "log_run_end", noop_end)
    monkeypatch.setattr(redactor_adapter, "call_llm_stream", llm_stream)
    monkeypatch.setattr(redactor_adapter, "call_llm", llm)
    monkeypatch.setattr(revisor_adapter, "call_llm", llm)
    return orquestador


async def _leer(art_id):
    async with AsyncSessionLocal() as s:
        art = (await s.execute(select(ArticleModel).where(ArticleModel.id == art_id))).scalars().first()
        informes = (await s.execute(select(PublicationGateReportModel).where(
            PublicationGateReportModel.article_id == art_id))).scalars().all()
    return art, informes


@pytest.mark.asyncio
@pytest.mark.parametrize("cuerpo, fuentes, esperado", [
    (IMRAD, [FUENTE], ArticleStatus.IN_REVIEW),   # compuerta superada: espera aprobación humana
    (INCOMPLETO, [FUENTE], ArticleStatus.DRAFT),  # bloqueante (IMRAD): vuelve a borrador
    (IMRAD, [], ArticleStatus.DRAFT),             # sin Investigador no hay fuentes: no se aprueba por ausencia
])
async def test_flujo_guardado_redactor_revisor_publicador_no_publica_solo(
        db, client, monkeypatch, _sin_red, cuerpo, fuentes, esperado):
    from app.modules.agents.adapters import publicador

    aplicar = publicador._apply_gate

    async def con_fuentes(session, article, state, log):
        # El flujo rápido no trae Investigador; se simulan las fuentes que él aportaría.
        return await aplicar(session, article, {**state, "sources": fuentes}, log)

    monkeypatch.setattr(publicador, "_apply_gate", con_fuentes)
    orquestador = _llm_falso(monkeypatch, cuerpo)
    autora = await _usuario("autora@ejemplo.com", UserRole.REDACTOR)
    admin = await _usuario("admin@ejemplo.com", UserRole.ADMIN)
    proyecto = await _proyecto("P", owner_id=autora.id)

    # El flujo se guarda por la API, como lo hace la página de Flujos.
    async with client as ac:
        token = await _token(ac, autora.email)
        r = await ac.post("/api/v1/flows", headers=_cabeceras(token, proyecto.id), json={
            "name": "Flujo rápido de publicación", "project_id": str(proyecto.id),
            "nodes": [], "edges": [], "flow_sequence": RAPIDO})
        assert r.status_code == 201, r.text
    async with AsyncSessionLocal() as s:
        guardado = (await s.execute(select(SavedFlowModel))).scalars().one()
    assert list(guardado.flow_sequence) == RAPIDO

    async with AsyncSessionLocal() as s:
        art = ArticleModel(title="T", body="", author_id=autora.id, project_id=proyecto.id,
                           status=ArticleStatus.DRAFT, responsible_author_id=autora.id)
        s.add(art)
        await s.commit()
        await s.refresh(art)

    await orquestador.Orchestrator.run(
        article_id=art.id, author_id=autora.id, title="T", keywords=["k"],
        scientific_format="apa", flow_sequence=list(guardado.flow_sequence),
    )

    tras_el_flujo, informes = await _leer(art.id)
    assert tras_el_flujo.status == esperado, f"el flujo dejó el artículo en {tras_el_flujo.status}"
    assert tras_el_flujo.published_at is None
    assert tras_el_flujo.approved_by is None and tras_el_flujo.approved_text_sha256 is None
    assert len(informes) >= 1, "el Publicador no dejó informe de compuerta"

    # Solo la aprobación humana, por la puerta única, publica; con bloqueantes, ni así.
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        tok = await _token(ac, admin.email)
        r = await ac.post(f"/api/v1/articles/{art.id}/approve", headers=_cabeceras(tok, proyecto.id))
    final, _ = await _leer(art.id)
    if esperado == ArticleStatus.IN_REVIEW:
        assert r.status_code == 200, r.text
        assert final.status == ArticleStatus.PUBLISHED
        assert final.approved_by == admin.id and final.approved_text_sha256
    else:
        assert r.status_code >= 400, r.text
        assert final.status != ArticleStatus.PUBLISHED
