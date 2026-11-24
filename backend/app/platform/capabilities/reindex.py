"""Reindexado de la biblioteca ya indexada antes de AC15 (SPEC-034 AC17 / T22.16).

Los fragmentos indexados antes de T22.14 no llevan ``section`` y, por eso, las
listas bibliograficas siguen recuperandose como «evidencia». Aqui se reclasifican
**in situ**: solo se escribe el campo ``section`` del payload.

Garantias (las que pide AC17):

* **Sin duplicar ni perder**: no se crean, borran ni re-embeben puntos; el id, el
  vector y el resto del payload (``doc_id``, ``doc_title``, DOI/metadatos, texto)
  no se tocan. Excluir las referencias es solo etiquetarlas: el filtro de busqueda
  (``must_not section=references``) hace el resto, y el texto sigue en el documento.
* **Estado de curacion intacto**: la curacion vive en la BD relacional; este modulo
  no la importa ni la lee. Tampoco toca ``agent_runs``/``agent_run_steps``: los
  mapas de citas (SPEC-035) de ejecuciones guardadas no se reescriben.
* **Idempotente**: solo se reclasifican los fragmentos sin ``section``; una segunda
  pasada no encuentra nada que hacer.
* **Simulacion**: con ``aplicar=False`` no se escribe nada.
* **Aislamiento por proyecto**: las colecciones se enumeran con
  ``ProjectContext.owns_collection``; el nombre nunca se compone aqui.

Reclasificacion: el troceado antiguo no guardo limites de seccion, asi que se
reconstruye el documento uniendo sus fragmentos por ``chunk_index`` y se aplica el
mismo ``split_sections`` determinista de la indexacion. Un fragmento es
``references`` solo si **cae entero** dentro de un tramo de referencias; si cruza el
borde hacia contenido se queda con la seccion del contenido, para no perder nunca
texto sustantivo.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from app.platform.capabilities import rag
from app.platform.capabilities.sections import (
    OTHER, REFERENCES, parece_bibliografia, split_sections,
)
from app.platform.project_context import ProjectContext

logger = logging.getLogger(__name__)

_SEP = "\n\n"
LOTE = 256


@dataclass
class ResumenColeccion:
    coleccion: str
    backend: str  # "qdrant" | "local"
    fragmentos: int = 0
    sin_seccion: int = 0
    reclasificados: Dict[str, int] = field(default_factory=dict)

    @property
    def referencias(self) -> int:
        return self.reclasificados.get(REFERENCES, 0)


_MAX_SOLAPE = 400
_MIN_COLA = 3  # fragmentos seguidos con aspecto de bibliografia para etiquetar sin encabezado


def _quitar_solape(textos: Sequence[str]) -> List[str]:
    """Quita el prefijo de solape que ``chunk_text`` antepone a cada fragmento.

    ``chunk_text`` antepone al fragmento i los ultimos ``overlap`` caracteres del
    i-1 y un espacio; ese prefijo tapa el encabezado de seccion (ya no queda al
    principio de linea). Se busca el prefijo mas largo que coincide con la cola del
    anterior; si no hay (fragmentos sin solape) el texto se deja tal cual.
    """
    cuerpos = [textos[0]] if textos else []
    for i in range(1, len(textos)):
        previo, actual = textos[i - 1], textos[i]
        cuerpo = actual
        for k in range(min(_MAX_SOLAPE, len(previo), len(actual) - 1), 0, -1):
            if actual[k] == " " and actual[:k] == previo[-k:]:
                cuerpo = actual[k + 1:]
                break
        cuerpos.append(cuerpo)
    return cuerpos


def clasificar_fragmentos(textos: Sequence[str]) -> List[str]:
    """Seccion de cada fragmento de un documento, dado su texto en orden.

    1. Con encabezados reconocibles (mismo ``split_sections`` que la indexacion).
    2. Sin encabezado (el troceado antiguo lo pierde cuando parte un parrafo largo
       por palabras): una **cola** final de al menos ``_MIN_COLA`` fragmentos
       consecutivos, todos con aspecto de bibliografia, se marca ``references``.
       Un fragmento aislado con muchas fechas no basta: es lo que citaria un
       parrafo de resultados.
    """
    if not textos:
        return []
    cuerpos = _quitar_solape(textos)
    unido = _SEP.join(cuerpos)
    rangos: List[Tuple[int, int]] = []
    pos = 0
    for t in cuerpos:
        rangos.append((pos, pos + len(t)))
        pos += len(t) + len(_SEP)

    # split_sections conserva el texto y une los tramos con salto de linea.
    tramos: List[Tuple[str, int, int]] = []
    cursor = 0
    for etiqueta, cuerpo in split_sections(unido):
        inicio = unido.find(cuerpo, cursor)
        if inicio < 0:  # no deberia ocurrir; falla hacia el lado seguro
            return [OTHER] * len(textos)
        tramos.append((etiqueta, inicio, inicio + len(cuerpo)))
        cursor = inicio + len(cuerpo)

    def seccion_en(p: int) -> str:
        for etiqueta, a, b in tramos:
            if a <= p < b:
                return etiqueta
        return OTHER  # separadores entre tramos

    resultado: List[str] = []
    for (a, b), t in zip(rangos, cuerpos):
        if not t.strip():
            resultado.append(OTHER)
            continue
        s_ini, s_fin = seccion_en(a), seccion_en(max(a, b - 1))
        if s_ini == REFERENCES and s_fin == REFERENCES:
            resultado.append(REFERENCES)
        elif s_ini == REFERENCES:
            resultado.append(s_fin)  # cruza hacia contenido: nunca se esconde
        else:
            resultado.append(s_ini)

    if REFERENCES not in resultado:
        cola = 0
        for t, etiqueta in zip(reversed(cuerpos), reversed(resultado)):
            if etiqueta != OTHER or not parece_bibliografia(t):
                break
            cola += 1
        if cola >= _MIN_COLA:
            for i in range(len(resultado) - cola, len(resultado)):
                resultado[i] = REFERENCES
    return resultado


def _plan_documentos(puntos: Sequence[Tuple[Any, Dict[str, Any]]]) -> Dict[Any, str]:
    """``id_punto -> seccion`` solo para los puntos que no tienen ``section``."""
    por_doc: Dict[str, List[Tuple[int, Any, Dict[str, Any]]]] = {}
    for pid, pl in puntos:
        did = pl.get("doc_id")
        if not did:
            continue
        por_doc.setdefault(did, []).append((pl.get("chunk_index", 0), pid, pl))
    plan: Dict[Any, str] = {}
    for fragmentos in por_doc.values():
        if all(pl.get("section") for _, _, pl in fragmentos):
            continue
        fragmentos.sort(key=lambda f: f[0])
        etiquetas = clasificar_fragmentos([pl.get("text", "") for _, _, pl in fragmentos])
        for (_, pid, pl), etiqueta in zip(fragmentos, etiquetas):
            if not pl.get("section"):
                plan[pid] = etiqueta
    return plan


def _contar(resumen: ResumenColeccion, plan: Dict[Any, str]) -> None:
    for etiqueta in plan.values():
        resumen.reclasificados[etiqueta] = resumen.reclasificados.get(etiqueta, 0) + 1


async def reindexar_qdrant(
    qdrant_url: str, coleccion: str, aplicar: bool, api_key: Optional[str] = None,
) -> Optional[ResumenColeccion]:
    headers = {"api-key": api_key} if api_key else {}
    resumen = ResumenColeccion(coleccion, "qdrant")
    puntos: List[Tuple[Any, Dict[str, Any]]] = []
    async with httpx.AsyncClient(base_url=qdrant_url, timeout=30.0, headers=headers) as c:
        if (await c.get(f"/collections/{coleccion}")).status_code != 200:
            return None
        offset = None
        while True:
            cuerpo: Dict[str, Any] = {"limit": LOTE, "with_payload": True, "with_vector": False}
            if offset is not None:
                cuerpo["offset"] = offset
            r = await c.post(f"/collections/{coleccion}/points/scroll", json=cuerpo)
            r.raise_for_status()
            res = r.json().get("result", {})
            pagina = res.get("points", [])
            puntos.extend((p["id"], p.get("payload") or {}) for p in pagina)
            offset = res.get("next_page_offset")
            if not offset or not pagina:
                break
        resumen.fragmentos = len(puntos)
        resumen.sin_seccion = sum(1 for _, pl in puntos if not pl.get("section"))
        plan = _plan_documentos(puntos)
        _contar(resumen, plan)
        if aplicar:
            por_seccion: Dict[str, List[Any]] = {}
            for pid, etiqueta in plan.items():
                por_seccion.setdefault(etiqueta, []).append(pid)
            for etiqueta, ids in por_seccion.items():
                for i in range(0, len(ids), LOTE):
                    w = await c.post(
                        f"/collections/{coleccion}/points/payload?wait=true",
                        json={"payload": {"section": etiqueta}, "points": ids[i:i + LOTE]},
                    )
                    w.raise_for_status()
    return resumen


def reindexar_local(coleccion: str, aplicar: bool) -> Optional[ResumenColeccion]:
    directorio = rag._local_rag_root() / coleccion
    if not directorio.is_dir():
        return None
    resumen = ResumenColeccion(coleccion, "local")
    for fichero in sorted(directorio.glob("*.json")):
        doc = rag._load_local_document(fichero)
        if not doc or not isinstance(doc.get("chunks"), list):
            continue
        chunks = doc["chunks"]
        resumen.fragmentos += len(chunks)
        resumen.sin_seccion += sum(1 for ch in chunks if not ch.get("section"))
        did = doc.get("doc_id") or fichero.stem
        plan = _plan_documentos([
            (i, {"doc_id": did, "chunk_index": ch.get("chunk_index", i),
                 "text": ch.get("text", ""), "section": ch.get("section")})
            for i, ch in enumerate(chunks)
        ])
        if not plan:
            continue
        _contar(resumen, plan)
        if aplicar:
            for i, etiqueta in plan.items():
                chunks[i]["section"] = etiqueta
            fichero.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return resumen


def colecciones_locales_del_proyecto(contexto: ProjectContext) -> List[str]:
    raiz = rag._local_rag_root()
    return sorted(d.name for d in raiz.iterdir()
                  if d.is_dir() and contexto.owns_collection(d.name))


async def colecciones_qdrant_del_proyecto(
    qdrant_url: str, contexto: ProjectContext, api_key: Optional[str] = None,
) -> List[str]:
    headers = {"api-key": api_key} if api_key else {}
    async with httpx.AsyncClient(base_url=qdrant_url, timeout=30.0, headers=headers) as c:
        r = await c.get("/collections")
        r.raise_for_status()
        nombres = [x["name"] for x in r.json()["result"]["collections"]]
    return sorted(n for n in nombres if contexto.owns_collection(n))


async def reindexar_proyecto(
    contexto: ProjectContext, qdrant_url: str, aplicar: bool, api_key: Optional[str] = None,
) -> List[ResumenColeccion]:
    """Reclasifica todas las colecciones (respaldo local y Qdrant) de **un** proyecto."""
    resultados: List[ResumenColeccion] = []
    for nombre in colecciones_locales_del_proyecto(contexto):
        r = reindexar_local(nombre, aplicar)
        if r:
            resultados.append(r)
    if await rag.is_qdrant_available(qdrant_url, api_key):
        for nombre in await colecciones_qdrant_del_proyecto(qdrant_url, contexto, api_key):
            r = await reindexar_qdrant(qdrant_url, nombre, aplicar, api_key)
            if r:
                resultados.append(r)
    return resultados
