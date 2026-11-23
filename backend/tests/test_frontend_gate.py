"""SPEC-032 AC6, AC7, AC8, AC14 / T20.14 — la interfaz muestra la compuerta.

No hay test runner de frontend (ver `test_frontend_layers.py`): estas comprobaciones
son estructurales, leen el JSX y los módulos y los cruzan con lo que dice el backend.
Prueban que la interfaz **cubre** cada código, estado y evento; no que se vea bien,
eso es una comprobación manual en el navegador.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "frontend" / "src" / "projects" / "alejandria-magazine"
BACKEND = REPO / "backend" / "app"


def _leer(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8")


def _catalogo_es() -> str:
    """Valores del catálogo español del proyecto (T29.8): los textos ya no están en el JSX."""
    return _leer(SRC / "i18n" / "es.json")


def _con_textos(texto: str) -> str:
    """El JSX más los textos de su catálogo: lo que la pantalla acaba mostrando."""
    return texto + "\n" + _catalogo_es()


def _sin_comentarios_js(texto: str) -> str:
    return re.sub(r"(?m)^\s*//.*$", "", texto)


# ── Estados ─────────────────────────────────────────────────────────────────


def test_el_estado_nuevo_se_muestra_en_el_detalle_y_en_el_listado():
    from app.models import ArticleStatus

    detalle = _leer(SRC / "pages" / "ArticleDetailPage.jsx")
    listado = _leer(SRC / "pages" / "ArticlesPage.jsx")
    for estado in ArticleStatus:
        assert re.search(rf"\b{estado.value}\s*:", detalle), f"el detalle no mapea {estado.value}"
        assert re.search(rf"\b{estado.value}\s*:", listado), f"el listado no mapea {estado.value}"
    assert "human_review: 'requires_human_review'" in listado  # y se puede filtrar
    assert "Revisión humana" in _catalogo_es()


def test_requires_human_review_explica_que_hacer_y_muestra_los_comentarios():
    detalle = _leer(SRC / "pages" / "ArticleDetailPage.jsx")
    assert "article.status === 'requires_human_review'" in detalle
    assert "article.rejection_comment" in detalle
    assert "vuelve a ejecutar el pipeline" in _con_textos(detalle)


# ── Códigos de error de la API ──────────────────────────────────────────────


def _codigos_del_backend() -> set:
    codigos = set()
    texto = _leer(BACKEND / "platform" / "publication_gate" / "approval.py")
    codigos |= set(re.findall(r'Denial\(\s*\d+,\s*"([a-z_]+)"', texto))
    from app.platform.publication_gate.review import judgment_blockers

    codigos |= set(judgment_blockers({"review_status": "not_run"}))
    codigos |= set(judgment_blockers({"review_status": "not_verified"}))
    codigos |= set(judgment_blockers({"review_status": "ok", "approval_score": 1, "coherent": False}))
    texto = _leer(BACKEND / "platform" / "publication_gate" / "decision.py")
    codigos |= set(re.findall(r'"(no_gate_report|gate_stale|gate_blockers|no_approval|approval_stale)"', texto))
    return codigos


def test_cada_codigo_de_409_tiene_un_mensaje_accionable():
    mensajes = _leer(SRC / "gate.js")
    faltan = [c for c in sorted(_codigos_del_backend()) if not re.search(rf"\b{c}\s*:", mensajes)]
    # `gate_stale` se traduce a `text_changed` antes de salir por la API.
    faltan = [c for c in faltan if c != "gate_stale"]
    assert faltan == [], f"códigos del backend sin mensaje en gate.js: {faltan}"


def test_las_acciones_traducen_el_error_en_lugar_de_mostrar_un_generico():
    detalle = _con_textos(_sin_comentarios_js(_leer(SRC / "pages" / "ArticleDetailPage.jsx")))
    for accion in ("aprobar", "publicar", "rechazar", "reevaluar la compuerta"):
        assert accion in detalle.lower()
    assert detalle.count("describeApiError(") >= 5
    assert "toast.error('Error al aprobar')" not in detalle
    assert "toast.error(t('detail.approveError'))" not in detalle  # tampoco sin pasar por describeApiError


# ── Informe de la compuerta ─────────────────────────────────────────────────


def test_el_panel_cubre_los_cuatro_estados_de_criterio_y_los_nombres_de_cada_uno():
    gate = _leer(SRC / "gate.js")
    for estado in ("passed", "failed", "not_verified", "not_implemented"):
        assert re.search(rf"\b{estado}\s*:", gate), estado
    for criterio in ("reference_existence", "reference_structure", "placeholders", "imrad_structure"):
        assert re.search(rf"\b{criterio}\s*:", gate), criterio
    # Los que el backend declara no pueden quedar sin etiqueta.
    for criterio in re.findall(r'^CRITERION = "([a-z_]+)"', _leer(BACKEND / "platform" / "publication_gate" / "structure.py"), re.M):
        assert criterio in gate


def test_el_panel_dice_cuando_no_hay_informe_y_cuando_esta_caducado():
    panel = _con_textos(_leer(SRC / "components" / "GateReportPanel.jsx"))
    assert "Sin informe" in panel
    assert "data.current" in panel and "reevalúa antes de aprobar" in panel
    assert "responsible_agent" in panel and "pending" in panel


def test_el_detalle_usa_el_panel_y_declara_al_autor_responsable():
    detalle = _leer(SRC / "pages" / "ArticleDetailPage.jsx")
    assert "<GateReportPanel" in detalle
    assert "Declararme autor responsable" in _con_textos(detalle)
    assert "handleDeclareResponsible" in detalle
    api = _leer(SRC / "api" / "articles.js")
    assert "/gate-report" in api and "/responsible-author" in api


def test_la_api_de_rechazo_manda_el_comentario_como_parametro_de_consulta():
    # El backend declara `comment: str` suelto: es un parámetro de consulta. Mandarlo en el
    # cuerpo JSON daba 422 y el rechazo desde requires_human_review no funcionaba.
    api = _sin_comentarios_js(_leer(SRC / "api" / "articles.js"))
    assert re.search(r"reject:.*\n?.*params:\s*\{\s*comment\s*\}", api)
    assert "reject_article" in _leer(BACKEND / "routers" / "articles.py")
    assert re.search(r"async def reject_article\(\s*article_id: UUID,\s*comment: str,",
                     _leer(BACKEND / "routers" / "articles.py"))


# ── Eventos SSE ─────────────────────────────────────────────────────────────


def test_la_pagina_de_ejecucion_atiende_los_eventos_de_la_compuerta():
    ejecucion = _leer(SRC / "pages" / "ExecutionPage.jsx")
    uso = _leer(BACKEND / "modules" / "agents" / "application" / "use_cases.py")
    for evento in ("gate_failed", "requires_human_review"):
        assert f'"type": "{evento}"' in uso, f"el backend ya no emite {evento}"
        assert f"data.type === '{evento}'" in ejecucion, f"la interfaz no atiende {evento}"
    assert "gateNotice" in ejecucion and "responsible_agent" in ejecucion


# ── Capas ───────────────────────────────────────────────────────────────────


def test_lo_nuevo_vive_en_el_proyecto_y_la_plataforma_no_lo_importa():
    plataforma = REPO / "frontend" / "src" / "platform"
    for ruta in plataforma.rglob("*.js*"):
        texto = _leer(ruta)
        assert "alejandria-magazine/gate" not in texto and "GateReportPanel" not in texto, ruta
