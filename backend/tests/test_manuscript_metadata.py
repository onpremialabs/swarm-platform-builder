"""SPEC-037 AC1 / T25.1 — autor, filiación y fecha los inyecta el sistema."""
import pytest
from sqlalchemy import select

from test_project_isolation import _proyecto, _usuario, db  # noqa: F401
from test_publicador_compuerta import FUENTE, _referencias_resueltas  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.models import ArticleModel, UserRole
from app.modules.agents.adapters import publicador
from app.platform.manuscript_metadata import strip_llm_metadata, system_authors, system_date

LLM = """# Un título
**Autor:** [Su Nombre/Autoría]
**Fecha:** Octubre 2023 (Borrador)
Afiliación: Universidad Inventada

## Introducción
La fecha: 2020 fue clave. Autor: Smith dijo algo.

## Metodología
x

## Resultados
x

## Discusión
x

## Referencias
Lista.
"""


def test_descarta_lo_que_escribe_el_llm_en_el_encabezado_y_respeta_el_cuerpo():
    limpio, quitadas = strip_llm_metadata(LLM)
    assert len(quitadas) == 3
    assert "Su Nombre" not in limpio and "Octubre 2023" not in limpio and "Inventada" not in limpio
    assert "Autor: Smith dijo algo." in limpio  # el cuerpo no se toca
    assert "# Un título" in limpio and "## Introducción" in limpio


def test_sin_campos_el_texto_queda_identico():
    t = "## Introducción\nTexto.\n"
    assert strip_llm_metadata(t) == (t, [])


def test_autores_del_sistema_no_inventa():
    assert system_authors([]) == [] and system_authors(None) == []
    assert system_authors([{"name": " "}, {"name": "Ana"}]) == [{"name": "Ana"}]
    assert system_date(None) == ""


async def _articulo(authors):
    u = await _usuario("a@ejemplo.com", UserRole.REDACTOR)
    p = await _proyecto("P", owner_id=u.id)
    async with AsyncSessionLocal() as s:
        art = ArticleModel(title="T", body="", author_id=u.id, project_id=p.id, authors=authors)
        s.add(art)
        await s.commit()
        await s.refresh(art)
    return art


async def _publicar(art):
    await publicador.run_publicador(
        {"article_id": art.id, "formatted_text": LLM, "sources": [FUENTE]})
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(ArticleModel).where(ArticleModel.id == art.id))).scalars().first()


@pytest.mark.asyncio
async def test_publicador_inyecta_autor_y_fecha_del_sistema(db):
    art = await _articulo([{"name": "Ana Pérez", "affiliation": "Univ. Real", "email": ""}])
    a = await _publicar(art)
    assert "Su Nombre" not in a.body and "Octubre 2023" not in a.body
    assert "Su Nombre" not in a.paper_html and "Octubre 2023" not in a.paper_html
    assert "Ana Pérez" in a.paper_html and "Univ. Real" in a.paper_html
    assert f'<div class="paper-date">{a.created_at.strftime("%Y-%m-%d")}</div>' in a.paper_html


@pytest.mark.asyncio
async def test_articulo_sin_autores_no_inventa_ninguno(db):
    a = await _publicar(await _articulo([]))
    assert "Su Nombre" not in a.paper_html and 'class="authors"' not in a.paper_html
    assert "Autor:** [Su" not in a.body
