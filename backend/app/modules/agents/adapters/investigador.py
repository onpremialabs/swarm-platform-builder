import logging
import re
from typing import Dict, Any, List

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.platform import library
from app.platform.capabilities import subqueries as subq
from app.platform.capabilities.binding import provider
from app.platform.capabilities.sections import REFERENCES
from app.platform.project_context import collection_for_state
from app.platform.capabilities.rag import (
    semantic_search_results, get_rag_backend, resolve_score_threshold, LIBRARY_AGENT,
)

logger = logging.getLogger(__name__)


def _clean_doc_title(filename: str) -> str:
    """Derive a human-readable document title from a stored filename.

    Strips the scraper prefix, file extension and arXiv id, and normalises
    separators — e.g. '[Scrape] [2404.00027v1] LLMs as Writing Assistants.txt'
    becomes 'LLMs as Writing Assistants'.
    """
    name = (filename or "").strip()
    name = re.sub(r"^\[Scrape\]\s*", "", name, flags=re.I)
    name = re.sub(r"\.(pdf|txt|md|docx?)$", "", name, flags=re.I)
    name = re.sub(r"^\[\d{4}\.\d{4,5}(v\d+)?\]\s*", "", name)  # arXiv id prefix
    name = re.sub(r"[_\-]+", " ", name).strip(" —|")
    name = re.sub(r"\s{2,}", " ", name)
    # Title-case slug-style names ("bienvenida alejandria magazine" -> "Bienvenida ...")
    if name and name == name.lower():
        name = name.title()
    return name


def _min_sources() -> int:
    """N de la abstención: de `research.min_sources` en `template.yaml`, y de ningún otro sitio.

    Deliberadamente **no** se lee de `agent_settings` ni del artículo: el autor no puede
    bajar el listón de evidencia que el proyecto exige (SPEC-034 AC7).
    """
    from app.modules.agents.domain import alejandria  # perezoso: evita un ciclo de imports

    return alejandria.package().research.min_sources


def _min_substantive_fragments() -> int:
    """K de la abstención por contenido: de `research.min_substantive_fragments`, y de ningún otro sitio."""
    from app.modules.agents.domain import alejandria  # perezoso: evita un ciclo de imports

    return alejandria.package().research.min_substantive_fragments


def _max_subqueries() -> int:
    """Tope de sub-preguntas: de `research.max_subqueries` en `template.yaml`, y de ningún otro sitio."""
    from app.modules.agents.domain import alejandria  # perezoso: evita un ciclo de imports

    return alejandria.package().research.max_subqueries


async def _proponer_subpreguntas(state: Dict[str, Any], maximo: int, log) -> List[Dict[str, str]]:
    """Sub-preguntas de sección (AC18) a partir **solo** del título y el enfoque del autor.

    Nunca recibe el manuscrito ni texto de las fuentes. Si el modelo falla o no devuelve nada
    utilizable, quedan las deterministas derivadas del título: la recuperación por sección no
    depende de que el modelo responda bien.
    """
    titulo = state.get("title") or ""
    enfoque = state.get("context_description") or ""
    respuesta = None
    try:
        from app.platform.llm import call_llm, resolve_agent_model, resolve_agent_temperature

        model = resolve_agent_model("investigador", state.get("agent_settings"))
        temperature = resolve_agent_temperature("investigador", state.get("agent_settings"))
        proponer = provider(state, "llm", call_llm)
        respuesta = await proponer(
            subq.build_prompt(titulo, enfoque, maximo),
            model=model,
            timeout=120.0,
            num_ctx=4096,
            temperature=temperature,
            max_tokens=512,
        )
    except Exception as exc:
        logger.warning("Sub-question proposal failed (non-critical): %s", exc)
        log(f"⚠️ No se pudieron proponer sub-preguntas con el modelo ({exc}); se usan las derivadas del título.", "warning")
    return subq.plan(titulo, respuesta, maximo)


def _ordenar_por_subpregunta(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Intercala los fragmentos por sub-pregunta (reparto en turnos), para que un tope de
    material (p. ej. el de la síntesis) no se lo lleve una sola sección."""
    grupos: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        clave = (item.get("subqueries") or [subq.TITULO])[0]
        grupos.setdefault(clave, []).append(item)
    colas = list(grupos.values())
    salida: List[Dict[str, Any]] = []
    while any(colas):
        for cola in colas:
            if cola:
                salida.append(cola.pop(0))
    return salida


_PALABRA = re.compile(r"[^\W\d_]{2,}")
#: Palabras mínimas para que un fragmento tenga «texto utilizable» (AC16).
_MIN_PALABRAS_SUSTANTIVO = 3


def _es_sustantivo(item: Dict[str, Any]) -> bool:
    """¿El fragmento aporta contenido? No es bibliografía y tiene texto utilizable (AC16)."""
    if item.get("section") == REFERENCES:
        return False
    return len(_PALABRA.findall(item.get("text") or "")) >= _MIN_PALABRAS_SUSTANTIVO


def _supera_umbral(item: Dict[str, Any], umbral: float, seleccion_explicita: bool) -> bool:
    """¿El fragmento está **demostrablemente** por encima del umbral de similitud?

    La capacidad de RAG ya filtra, pero aquí se decide quién cuenta como evidencia, así que
    no se confía solo en ella (defensa en profundidad, como hace la propia capacidad). Un
    fragmento sin puntuación solo vale si la persona eligió documentos concretos: esa
    elección es la señal de relevancia, el mismo criterio que `_fallback_sin_ranking` (T22.6).
    """
    if umbral <= 0.0:
        return True
    score = item.get("score")
    if score is None:
        return seleccion_explicita
    return score >= umbral


def _autores(doc: Any) -> str:
    nombres = [str(a).strip() for a in (doc.authors or []) if str(a).strip()]
    return ", ".join(nombres)


def _mensaje_abstencion(*, verificadas: int, minimo: int, solo_contexto: List[str],
                        umbral: float, rag_fallo: bool, hubo_resultados: bool) -> str:
    """Qué pasó, qué falta y cómo resolverlo, para la persona que lanzó la ejecución."""
    partes = [
        f"El Investigador se ha abstenido: hay {verificadas} fuente(s) citable(s) y relevante(s) "
        f"para este tema y el proyecto exige al menos {minimo}. No se ha generado ningún texto "
        "desde el conocimiento del modelo."
    ]
    if rag_fallo:
        partes.append("La base de conocimiento no estuvo disponible en esta ejecución (consulta el registro).")
    elif not hubo_resultados:
        partes.append(
            f"No se recuperó ningún fragmento por encima del umbral de similitud ({umbral:g})."
        )
    if solo_contexto:
        muestra = "; ".join(solo_contexto[:5]) + ("…" if len(solo_contexto) > 5 else "")
        partes.append(
            f"{len(solo_contexto)} documento(s) relevante(s) solo pueden usarse como contexto porque "
            f"no son citables (no están aceptados, o no tienen DOI verificado ni están declarados "
            f"«aportados por el autor»): {muestra}."
        )
    partes.append(
        "Qué hacer: acepta en la biblioteca los documentos que quieras usar y, para cada uno sin "
        "identificador, verifica su DOI o decláralo «aportado por el autor» en la pantalla "
        "Documentos; también puedes añadir más documentos (candidatos verificados o PDFs). "
        "Después vuelve a ejecutar el artículo."
    )
    return " ".join(partes)


def _mensaje_sin_contenido(*, sustantivos: int, minimo: int, fuentes: int,
                           solo_resumen: List[str]) -> str:
    """Hay fuentes citables, pero no aportan contenido recuperable (AC16)."""
    partes = [
        f"El Investigador se ha abstenido: hay {fuentes} fuente(s) citable(s), pero solo "
        f"{sustantivos} fragmento(s) con contenido recuperable (sin contar la bibliografía) y el "
        f"proyecto exige al menos {minimo}. No se ha generado ningún texto desde el conocimiento "
        "del modelo."
    ]
    if solo_resumen:
        muestra = "; ".join(solo_resumen[:5]) + ("…" if len(solo_resumen) > 5 else "")
        partes.append(
            f"{len(solo_resumen)} documento(s) solo tienen el resumen, que cuenta como un único "
            f"fragmento: {muestra}."
        )
    partes.append(
        "Qué hacer: sube el PDF completo de las fuentes (o súbelo de nuevo si solo se indexó la "
        "bibliografía), reindexa los documentos ya guardados o aporta el texto de las fuentes. "
        "Después vuelve a ejecutar el artículo."
    )
    return " ".join(partes)


# Generated by GitHub Copilot
async def run_investigador(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Investigador Agent — investigación **solo con la biblioteca verificada** (SPEC-034 AC5, AC7).

    1. RAG local (Qdrant) — búsqueda semántica con el umbral de similitud activo.
    2. Clasificación contra la biblioteca (`library_documents`, del proyecto):
         * **citable**: aceptado y, o bien con DOI verificado (resuelto por el sistema o
           aportado por el autor), o bien declarado «aportado por el autor» por una persona
           (AC14, ADR-0013). Es lo único que entra en `sources` y, por tanto, en Referencias,
           cada fuente con su clase en `source_class`.
         * **solo contexto**: sin verificar y sin declarar, o sin fila en la biblioteca
           (documentos subidos antes de que existiera). Alimenta la síntesis pero **nunca** se
           cita. No existe excepción implícita para un «documento interno».
         * **descartado** por el autor: no se usa ni como contexto.
    3. Abstención: con menos de `research.min_sources` documentos citables, no se sintetiza
       —ni desde el conocimiento paramétrico del modelo— y se devuelve `abstained`, que
       detiene el pipeline y se declara en la traza y al autor.
    4. Síntesis con LLM del material citable más el contexto no citable.
    """
    article_id = state.get("article_id")
    title = state.get("title") or ""
    keywords = state.get("keywords") or []
    log = state.get("_log") or (lambda msg, level="info": None)

    logger.info("Running Investigador for article %s with keywords %s", article_id, keywords)
    log(f"🔑 Keywords: {', '.join(keywords) if keywords else '(ninguna)'}")

    # Build query: title words + unique keywords (deduped, title takes priority)
    title_words = [w.strip(".,;:?!()[]") for w in title.split() if len(w) > 3] if title else []
    kw_words = [k for k in keywords if k.lower() not in {w.lower() for w in title_words}]
    combined_terms = title_words + kw_words
    query_str = " ".join(combined_terms) if combined_terms else "scientific research"
    log(f"🔍 Query de búsqueda: \"{query_str[:100]}\"")

    agent_cfg = (state.get("agent_settings") or {}).get("investigador", {})
    context_hint = (agent_cfg.get("context_hint") or "").strip()
    if "min_sources" in agent_cfg:
        # El listón de evidencia es del proyecto (template.yaml); un ajuste de la ejecución
        # no lo mueve, y se dice para que no parezca que sí.
        log("ℹ️ Se ignora 'min_sources' en los ajustes de la ejecución: lo fija la plantilla del proyecto.", "warning")
    if "max_subqueries" in agent_cfg:
        log("ℹ️ Se ignora 'max_subqueries' en los ajustes de la ejecución: lo fija la plantilla del proyecto.", "warning")
    if context_hint:
        query_str = f"{context_hint} {query_str}"
        logger.info("Investigador context hint: '%s'", context_hint[:80])
        log(f"💡 Context hint aplicado: \"{context_hint[:80]}\"")

    # Resolve RAG collection
    # El perfil aporta un *bucket*; el proyecto de la ejecución compone la
    # colección real, y así dos proyectos con el mismo perfil no se leen
    # (SPEC-013 / T8.5 / AC6).
    rag_bucket = (agent_cfg.get("rag_collection") or "").strip() or settings.QDRANT_COLLECTION
    rag_collection = collection_for_state(state, rag_bucket)
    rag_top_k = int(agent_cfg.get("rag_top_k") or 0) or settings.RAG_TOP_K
    rag_doc_ids = agent_cfg.get("rag_doc_ids") or None
    if isinstance(rag_doc_ids, list) and len(rag_doc_ids) == 0:
        rag_doc_ids = None
    minimo = _min_sources()
    minimo_fragmentos = _min_substantive_fragments()
    umbral = resolve_score_threshold()

    # ── Etapa 1: RAG local ───────────────────────────────────────────────────
    # Search the investigador's own bucket AND the shared library, so documents
    # uploaded to either are found. Explicit doc_ids (selected by the user) take
    # precedence and bypass the agent-bucket filter entirely.
    search_agents = ["investigador", LIBRARY_AGENT]
    backend = await get_rag_backend(settings.QDRANT_URL, settings.QDRANT_API_KEY)
    if rag_doc_ids:
        log(f"🔎 Etapa 1/3 — Buscando en documentos seleccionados ({len(rag_doc_ids)}) "
            f"[backend: {backend}, colección: {rag_collection}]...")
    else:
        log(f"🔎 Etapa 1/3 — Buscando fuentes [backend: {backend}, colección: {rag_collection}, "
            f"buckets: {', '.join(search_agents)}]...")
    rag_results: List[Dict[str, Any]] = []
    rag_fallo = False
    # La búsqueda sale de la capacidad `rag_results` cuando el motor la
    # inyecta, y del import de siempre cuando no (SPEC-013/T8.3/AC8).
    buscar = provider(state, "rag_results", semantic_search_results)

    async def _consultar(consulta: str) -> List[Dict[str, Any]]:
        return await buscar(
            query=consulta,
            qdrant_url=settings.QDRANT_URL,
            collection=rag_collection,
            agent_name=search_agents,
            ollama_base_url=settings.OLLAMA_BASE_URL,
            embedding_model=settings.OLLAMA_EMBED_MODEL,
            limit=rag_top_k,
            api_key=settings.QDRANT_API_KEY,
            doc_ids=rag_doc_ids,
        ) or []

    # Sub-preguntas de sección (AC18): el modelo las propone solo con título y enfoque.
    subpreguntas = await _proponer_subpreguntas(state, _max_subqueries(), log)
    log(f"🧭 {len(subpreguntas)} sub-pregunta(s) de sección: "
        + "; ".join(f"[{q['id']}] {subq.ETIQUETAS[q['section']]}" for q in subpreguntas))

    # Cada fragmento declara qué consultas lo recuperaron: `title` o ids `q#` (dedup por chunk).
    por_fragmento: Dict[Any, Dict[str, Any]] = {}

    def _fusionar(consulta_id: str, resultados: List[Dict[str, Any]]) -> None:
        for r in resultados:
            if r.get("chunk_id") is not None:
                clave = (r.get("doc_id"), r.get("chunk_id"))
            else:
                clave = (r.get("doc_id"), (r.get("text") or "")[:120])
            previo = por_fragmento.get(clave)
            if previo is None:
                previo = dict(r)
                previo["subqueries"] = []
                por_fragmento[clave] = previo
            if consulta_id not in previo["subqueries"]:
                previo["subqueries"].append(consulta_id)

    try:
        _fusionar(subq.TITULO, await _consultar(query_str))
    except Exception as exc:
        rag_fallo = True
        logger.warning("Could not search Qdrant: %s", exc)
        log(f"⚠️ RAG local no disponible: {exc}", "warning")
    if not rag_fallo:
        for q in subpreguntas:
            try:
                _fusionar(q["id"], await _consultar(q["question"]))
            except Exception as exc:
                logger.warning("Sub-question search %s failed: %s", q["id"], exc)
                log(f"⚠️ La sub-pregunta {q['id']} no se pudo recuperar: {exc}", "warning")
    # Lo recuperado por sub-preguntas va antes que lo que solo trajo el título.
    rag_results = list(por_fragmento.values())
    for r in rag_results:
        r["subqueries"].sort(key=lambda i: (i == subq.TITULO, i))

    # Guard: when the user selected specific documents, never build citations
    # from anything else — even if an upstream fallback ignored the filter.
    if rag_doc_ids:
        allowed = set(rag_doc_ids)
        before = len(rag_results)
        rag_results = [r for r in rag_results if r.get("doc_id") in allowed]
        dropped = before - len(rag_results)
        if dropped:
            log(f"🛡️ Descartados {dropped} fragmento(s) de documentos no seleccionados.")
    # Solo cuenta como evidencia lo que supera el umbral de similitud (AC7).
    antes = len(rag_results)
    rag_results = [r for r in rag_results if _supera_umbral(r, umbral, bool(rag_doc_ids))]
    if antes != len(rag_results):
        log(f"🛡️ Descartados {antes - len(rag_results)} fragmento(s) por debajo del umbral de similitud ({umbral:g}).")

    # ── Etapa 2: clasificar contra la biblioteca del proyecto ────────────────
    por_doc: Dict[str, Dict[str, Any]] = {}
    for index, item in enumerate(rag_results):
        doc_id = item.get("doc_id") or f"local-{index}"
        grupo = por_doc.setdefault(doc_id, {
            "items": [], "filename": item.get("filename", ""),
            "doc_title": (item.get("doc_title") or "").strip(),
        })
        grupo["items"].append(item)

    project_id = state.get("project_id")
    filas: Dict[str, Any] = {}
    if project_id is not None and por_doc:
        # Si la biblioteca no se puede leer, la ejecución falla (y se puede reanudar): no se
        # abstiene diciendo «faltan documentos» por un fallo que no es del autor.
        async with AsyncSessionLocal() as session:
            filas = await library.documents_by_rag_id(session, project_id, list(por_doc))

    citables: Dict[str, Any] = {}
    solo_contexto: Dict[str, Dict[str, Any]] = {}
    descartados = 0
    for doc_id, grupo in por_doc.items():
        fila = filas.get(doc_id)
        if fila is not None and fila.curation_status == library.CurationStatus.DISCARDED.value:
            descartados += 1
            continue
        if fila is not None and library.is_citable(fila):
            citables[doc_id] = fila
        else:
            # Sin fila (documento anterior a la biblioteca) o sin DOI verificado: contexto.
            solo_contexto[doc_id] = grupo
    log(
        f"📚 Etapa 2/3 — {len(citables)} documento(s) citable(s) (DOI verificado o aportado por el "
        f"autor), {len(solo_contexto)} solo contexto (ni verificado ni declarado)"
        + (f", {descartados} descartado(s) por el autor." if descartados else ".")
    )

    # ── Abstención (AC7) ─────────────────────────────────────────────────────
    if len(citables) < minimo:
        nombres = [
            (g["doc_title"] or _clean_doc_title(g["filename"]) or g["filename"] or "Documento")
            for g in solo_contexto.values()
        ]
        mensaje = _mensaje_abstencion(
            verificadas=len(citables), minimo=minimo, solo_contexto=nombres,
            umbral=umbral, rag_fallo=rag_fallo, hubo_resultados=bool(rag_results),
        )
        log(f"⛔ {mensaje}", "warning")
        logger.warning("Investigador se abstiene en el artículo %s: %s/%s fuentes verificadas",
                       article_id, len(citables), minimo)
        return {
            "research_data": "",
            "sources": [],
            "abstained": True,
            "abstention": {
                "reason": "insufficient_verified_sources",
                "message": mensaje,
                "verified_sources": len(citables),
                "citable_sources": len(citables),
                "min_sources": minimo,
                "similarity_threshold": umbral,
                "context_only_documents": len(solo_contexto),
                "rag_unavailable": rag_fallo,
                "subqueries": subpreguntas,
            },
        }

    # ── Abstención por contenido (AC16) ──────────────────────────────────────
    # Solo cuentan los fragmentos sustantivos de las fuentes citables; un documento
    # `abstract_only` (AC11) aporta uno como máximo, por mucho que se recupere.
    sustantivos: Dict[str, List[Dict[str, Any]]] = {
        doc_id: [i for i in por_doc[doc_id]["items"] if _es_sustantivo(i)] for doc_id in citables
    }
    solo_resumen = {
        doc_id for doc_id, fila in citables.items()
        if getattr(fila, "text_status", None) == library.TextStatus.ABSTRACT_ONLY.value
    }
    total_sustantivos = sum(
        min(len(items), 1) if doc_id in solo_resumen else len(items)
        for doc_id, items in sustantivos.items()
    )
    if total_sustantivos < minimo_fragmentos:
        nombres = [citables[d].title for d in citables if d in solo_resumen]
        mensaje = _mensaje_sin_contenido(
            sustantivos=total_sustantivos, minimo=minimo_fragmentos, fuentes=len(citables),
            solo_resumen=nombres,
        )
        log(f"⛔ {mensaje}", "warning")
        logger.warning("Investigador se abstiene en el artículo %s: %s/%s fragmentos sustantivos",
                       article_id, total_sustantivos, minimo_fragmentos)
        return {
            "research_data": "",
            "sources": [],
            "abstained": True,
            "abstention": {
                "reason": "insufficient_substantive_content",
                "message": mensaje,
                "verified_sources": len(citables),
                "citable_sources": len(citables),
                "min_sources": minimo,
                "substantive_fragments": total_sustantivos,
                "min_substantive_fragments": minimo_fragmentos,
                "abstract_only_documents": len(solo_resumen),
                "similarity_threshold": umbral,
                "context_only_documents": len(solo_contexto),
                "rag_unavailable": rag_fallo,
                "subqueries": subpreguntas,
            },
        }

    # ── Cobertura por sección (AC18) ──────────────────────────────────────────
    # Una sección sin fragmento sustantivo de una fuente citable queda «sin cobertura»: se
    # declara en la traza y el Redactor la recibe como hueco, no como invitación a rellenar.
    sustantivos_citables = [
        {**i, "_doc_id": doc_id} for doc_id, items in sustantivos.items() for i in items
    ]
    cobertura = subq.coverage(subpreguntas, sustantivos_citables)
    sin_cobertura = [c["label"] for c in cobertura if not c["covered"]]
    por_pregunta = []
    for q in subpreguntas:
        por_pregunta.append({
            **q,
            "fragments": sum(1 for i in rag_results if q["id"] in i["subqueries"]),
            "substantive_fragments": sum(1 for i in sustantivos_citables if q["id"] in i["subqueries"]),
        })
    research_coverage = {
        "subqueries": por_pregunta,
        "coverage": cobertura,
        "uncovered_sections": [c["section"] for c in cobertura if not c["covered"]],
    }
    if sin_cobertura:
        log(f"⚠️ Sin cobertura (sin evidencia sustantiva): {', '.join(sin_cobertura)}.", "warning")
    else:
        log("✅ Todas las secciones tienen evidencia sustantiva.")

    # ── Fuentes citables y material ──────────────────────────────────────────
    sources: List[Dict[str, Any]] = []
    research_chunks: List[str] = []
    # Material por sub-pregunta, intercalado; cada fragmento declara de cuál viene.
    etiquetas_q = {q["id"]: subq.ETIQUETAS[q["section"]] for q in subpreguntas}
    for item in _ordenar_por_subpregunta(sustantivos_citables):
        origen = (item.get("subqueries") or [subq.TITULO])[0]
        marca = f"[Sub-pregunta {origen}: {etiquetas_q[origen]}]" if origen in etiquetas_q else "[Sub-pregunta: título]"
        research_chunks.append(f"[Fuente: {citables[item['_doc_id']].title}] {marca} {item.get('text', '')}")
    for doc_id, fila in citables.items():
        grupo = por_doc[doc_id]
        declarado = getattr(fila, "author_provided_at", None)
        sources.append({
            "doc_id": doc_id,
            "title": fila.title,
            "authors": _autores(fila),
            "journal": (fila.journal or "").strip(),
            "year": str(fila.year or "").strip(),
            "doi": fila.doi,
            "url": (fila.url or "").strip(),
            "filename": grupo["filename"],
            "snippet": ((sustantivos[doc_id] or grupo["items"])[0].get("text", "") or "")[:200],
            "doi_verification": fila.verification_method,
            # Clase citable (ADR-0013): «identified» o «author_provided». La compuerta decide su
            # severidad y Referencias la etiqueta; sin DOI no se inventa un identificador.
            "source_class": library.source_class(fila),
            "author_provided_at": declarado.isoformat() + "Z" if declarado else None,
        })
    # Lo no verificado alimenta la síntesis y nada más: ni `sources` ni `[Fuente: …]`.
    contexto_no_citable = [
        f"- {item.get('text', '')}"
        for grupo in solo_contexto.values() for item in grupo["items"]
    ]
    log(f"✅ RAG: {len(rag_results)} fragmento(s) de {len(por_doc)} documento(s) en '{rag_collection}'; "
        f"{len(sources)} fuente(s) citable(s).")

    # ── Etapa 3: síntesis con LLM ────────────────────────────────────────────
    # Solo se llega aquí con evidencia suficiente: nunca se sintetiza desde el
    # conocimiento paramétrico del modelo (AC7).
    try:
        from app.platform.llm import (
            call_llm, resolve_agent_model, resolve_agent_temperature,
        )
        model = resolve_agent_model("investigador", state.get("agent_settings"))
        # Temperatura del agente (perfil o ajustes de la ejecución). Hasta ahora
        # se guardaba y no llegaba a ningún proveedor.
        temperature = resolve_agent_temperature("investigador", state.get("agent_settings"))
        # Tope de salida de la síntesis. Es un resumen: ~1000 tokens sobran. Sin
        # tope, Ollama no para nunca por su cuenta, y un modelo pequeño que entra
        # en bucle repitiendo frases llenaba el timeout de 600 s en cada intento.
        _SYNTHESIS_MAX_TOKENS = 1024

        log(f"🧠 Etapa 3/3 — Síntesis con LLM ({model}) de {len(research_chunks)} fragmento(s) citable(s)...")
        combined = "\n\n---\n\n".join(research_chunks[:8])
        contexto_extra = ""
        if contexto_no_citable:
            contexto_extra = (
                "\n\nCONTEXTO NO CITABLE (documentos sin DOI verificado: úsalo para entender el "
                "tema, pero NO lo cites ni menciones sus títulos ni autores):\n"
                + "\n".join(contexto_no_citable[:6])[:2000]
            )
        synthesis_prompt = (
            "Eres un investigador científico. Lee el siguiente material de investigación y "
            "elabora un resumen estructurado en español con los hallazgos más relevantes. "
            "Cita solo las fuentes marcadas como [Fuente: …]; no añadas información que no "
            "esté en el material. Sé conciso pero completo.\n\n"
            f"MATERIAL RECOPILADO:\n{combined[:6000]}{contexto_extra}\n\n"
            "RESUMEN DE INVESTIGACIÓN:"
        )
        sintetizar = provider(state, "llm", call_llm)
        synthesis = await sintetizar(
            synthesis_prompt,
            model=model,
            timeout=600.0,
            keep_alive=0,   # unload after synthesis — frees VRAM before redactor loads its model
            num_ctx=8192,   # more context for multi-source synthesis
            temperature=temperature,
            max_tokens=_SYNTHESIS_MAX_TOKENS,
        )
        if synthesis and len(synthesis.split()) > 30:
            # La síntesis es material para el Redactor, no una fuente: no entra en `sources`.
            research_chunks.append(f"[Síntesis] {synthesis}")
            log(f"✅ Síntesis generada — {len(synthesis.split())} palabras.")
        else:
            log("⚠️ Síntesis LLM vacía o muy corta.", "warning")
    except Exception as exc:
        logger.warning("LLM synthesis failed (non-critical): %s", exc)
        log(f"⚠️ Síntesis LLM no disponible: {exc}", "warning")

    # Lista explícita de lo citable al frente: lo único que el Redactor puede referenciar.
    citables_txt = "\n".join(
        f"- {s['title']}" + (f" ({s['authors']}, {s['year']})" if s["authors"] or s["year"] else "")
        + (f" — DOI {s['doi']}" if s.get("doi") else " — documento aportado por el autor, sin identificador")
        for s in sources
    )
    research_data = (
        "FUENTES CITABLES (únicas que pueden citarse; DOI verificado o aportadas por el autor):\n" + citables_txt
        + "\n\n---\n\n" + "\n\n---\n\n".join(research_chunks)
    )
    log(f"📦 Investigación completada: {len(sources)} fuente(s), {len(research_chunks)} fragmento(s).")
    return {"research_data": research_data, "sources": sources, "research_coverage": research_coverage}
