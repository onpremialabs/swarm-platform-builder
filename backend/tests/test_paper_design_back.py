"""BUG-005 — «Volver» en el diseño del paper sale con un solo clic.

Sin runner de frontend, se fija por estructura el contrato que lo arregla. La
vista previa es un `<iframe srcDoc>` que se repinta con cada edición; cambiar el
`srcdoc` de un iframe ya cargado añade una entrada al historial de sesión, y
`navigate(-1)` se la comía en el primer clic: solo el segundo salía de la página.
"""
import re
from pathlib import Path

PAGINA = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "projects" / "alejandria-magazine" / "pages" / "PaperDesignPage.jsx"
).read_text(encoding="utf-8")


def test_volver_no_depende_del_historial():
    assert "navigate(-1)" not in re.sub(r"//.*", "", PAGINA)  # el comentario lo menciona
    assert "navigate(`/dashboard/articles/${id}`)" in PAGINA


def test_el_boton_volver_usa_el_manejador_con_aviso_de_cambios_sin_guardar():
    assert re.search(r"onClick=\{handleBack\}\s+aria-label=\{t\('common\.back'\)\}", PAGINA)
    assert "if (dirty && !globalThis.confirm(" in PAGINA


def test_cada_previa_es_un_iframe_nuevo_y_no_un_srcdoc_cambiado():
    assert "key={previewKey}" in PAGINA
    assert "setPreviewKey(" in PAGINA
