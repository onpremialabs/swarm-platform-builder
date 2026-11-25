import asyncio
import logging
from typing import Dict, Any

from app.core.config import settings
from app.platform.capabilities.binding import provider
from app.platform.project_context import collection_for_state
from app.platform.capabilities.rag import semantic_search_results, LIBRARY_AGENT
from app.platform import citations as citas
from app.platform.capabilities import subqueries as citas_cobertura
from app.platform import draft_integrity, explainability
from app.platform.llm import (
    call_llm, call_llm_stream, enlarge_output_budget, last_stop_reason,
    reset_stop_reason, resolve_agent_max_output_tokens, resolve_agent_model,
    resolve_agent_num_ctx, resolve_agent_temperature,
)

logger = logging.getLogger(__name__)

# Default prompt templates per language
_DEFAULT_TEMPLATE_ES = (
    "Eres un escritor científico experto. Redacta un borrador de artículo científico en Markdown.\n"
    "{word_count_header}"
    "\nTítulo: {title}\n"
    "Palabras clave: {keywords}\n"
    "{context_section}"
    "### Contexto de investigación (incorpora estos datos; cita SOLO las fuentes listadas como citables, el resto es contexto y no se cita):\n"
    "{research_data}\n"
    "{feedback_section}\n"
    "Escribe un manuscrito científico estructurado que contenga:\n"
    "- Resumen (Abstract)\n- Introducción\n- Metodología\n- Resultados\n- Discusión\n\n"
    "Resultados y Discusión son DOS secciones separadas, cada una con su propio encabezado: en "
    "Resultados expón los hallazgos sin interpretarlos; la interpretación va en Discusión.\n\n"
    "Si el contexto declara «EVIDENCIA SIN COBERTURA» para una sección, no la rellenes con tu "
    "propio conocimiento: indica que las fuentes no aportan evidencia.\n\n"
    "FORMATO DE CITA (obligatorio): cita cada afirmación sustantiva con el marcador del fragmento "
    "citable que la respalda, entre corchetes, p. ej. «La HbA1c bajó un 1,1 % [F1].» o «... [F1, F3].». "
    "NO uses citas autor-año como (Autor, 2024) ni pongas el título de una obra como autor: no son "
    "válidas. Si no hay fragmento que respalde una frase, no la cites.\n\n"
    "Redacta el borrador en español, con lenguaje académico y profesional."
    "{word_count_footer}"
)

_DEFAULT_TEMPLATE_EN = (
    "You are an expert scientific writer. Write a scientific paper draft in Markdown.\n"
    "{word_count_header}"
    "\nTitle: {title}\n"
    "Keywords: {keywords}\n"
    "{context_section}"
    "### Research Context (incorporate this data; cite ONLY the sources listed as citable, with the [F#] marker of their fragment; anything else is context and must not be cited):\n"
    "{research_data}\n"
    "{feedback_section}\n"
    "Write a structured scientific manuscript containing:\n"
    "- Abstract\n- Introduction\n- Methodology\n- Results\n- Discussion\n\n"
    "Results and Discussion are TWO separate sections, each with its own heading: report "
    "findings in Results without interpreting them; interpretation belongs in Discussion.\n\n"
    "If the context declares «EVIDENCE WITHOUT COVERAGE» for a section, do not fill it with your "
    "own knowledge: state that the sources provide no evidence.\n\n"
    "CITATION FORMAT (mandatory): cite every substantive claim with the marker of the citable fragment "
    "that supports it, in square brackets, e.g. \"HbA1c fell by 1.1% [F1].\" or \"... [F1, F3].\". "
    "Do NOT use author-year citations like (Author, 2024) or put a work's title as author: they are "
    "not valid. If no fragment supports a sentence, do not cite it.\n\n"
    "Write the draft in English, in professional, academic language."
    "{word_count_footer}"
)

_FEEDBACK_HEADER_ES = (
    "\n### Feedback del Revisor:\n"
    "El revisor rechazó el borrador anterior con los siguientes comentarios. "
    "DEBES resolver estos problemas en el nuevo borrador:\n"
)

_FEEDBACK_HEADER_EN = (
    "\n### Feedback from Reviewer:\n"
    "The reviewer rejected the previous draft with the following comments. "
    "You MUST address these issues in the new draft:\n"
)

_CORRECTION_TEMPLATE_ES = (
    "Identidad: Eres un Ingeniero Senior de Software Experto en LLMOps y sistemas multi-agente.\n"
    "Stack tecnológico exacto: Python, FastAPI, LangGraph (v2), Qdrant y un motor de inferencia local (como Ollama/vLLM).\n\n"
    "MODO: Edición y Corrección de Manuscrito Científico.\n"
    "Ignora el prompt inicial genérico de creación. Tu única prioridad es revisar el borrador actual "
    "y corregir de forma estricta los puntos críticos señalados por el Revisor.\n\n"
    "Borrador actual:\n{draft_text}\n\n"
    "Feedback del Revisor:\n{feedback_section}\n\n"
    "{context_section}\n"
    "Conserva las citas con marcador [F#]; no uses citas autor-año como (Autor, 2024).\n"
    "Escribe el borrador científico corregido y mejorado completo en Markdown:"
)

_CORRECTION_TEMPLATE_EN = (
    "Identity: You are a Senior Software Engineer Expert in LLMOps and multi-agent systems.\n"
    "Exact technology stack: Python, FastAPI, LangGraph (v2), Qdrant and a local inference engine (like Ollama/vLLM).\n\n"
    "MODE: Scientific Manuscript Editing and Correction.\n"
    "Ignore the generic initial creation prompt. Your sole priority is to review the current draft "
    "and strictly address the review comments provided by the Reviewer.\n\n"
    "Current draft:\n{draft_text}\n\n"
    "Reviewer Feedback:\n{feedback_section}\n\n"
    "{context_section}\n"
    "Keep the [F#] marker citations; do not use author-year citations like (Author, 2024).\n"
    "Write the complete corrected and improved scientific draft in Markdown:"
)


def _fusionar_fragmentos(del_investigador, de_rag, permitidos):
    """Fragmentos del Investigador (con su origen) + los del RAG, sin duplicar el mismo fragmento."""
    vistos, fusion = set(), []
    for f in list(del_investigador or []) + list(de_rag or []):
        if not isinstance(f, dict) or str(f.get("doc_id")) not in permitidos:
            continue
        fid = citas.fragment_id(f) or (str(f.get("doc_id")), (f.get("text") or "")[:80])
        if fid in vistos:
            continue
        vistos.add(fid)
        fusion.append(f)
    return fusion


# Generated by GitHub Copilot
async def run_redactor(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Redactor Agent.
    Generates a scientific draft in Markdown using Ollama. Supports custom
    prompt templates and configurable output language (es/en). Incorporates
    reviewer feedback when in a correction loop.
    """
    title = state.get("title") or "Artículo Científico"
    keywords = state.get("keywords") or []
    research_data = state.get("research_data") or "No se proporcionó contexto de investigación."
    feedback = state.get("feedback") or []
    context_description = (state.get("context_description") or "").strip()
    article_outline = (state.get("article_outline") or "").strip()
    log = state.get("_log") or (lambda msg, level="info": None)

    # Resolve per-agent config; model is provider-aware (SPEC-023/T12.3)
    agent_cfg = (state.get("agent_settings") or {}).get("redactor", {})
    model = resolve_agent_model("redactor", state.get("agent_settings"))
    # Temperatura del agente (perfil o ajustes de la ejecución). Hasta ahora se
    # guardaba y no llegaba a ningún proveedor: era un control de la interfaz
    # que no hacía nada.
    temperature = resolve_agent_temperature("redactor", state.get("agent_settings"))
    # Ventana y tope de salida (T24.9): ya no están fijos en el código. Misma cascada que el
    # modelo y la temperatura, acotados por la ventana del modelo.
    num_ctx = resolve_agent_num_ctx("redactor", state.get("agent_settings"), model)
    max_output = resolve_agent_max_output_tokens("redactor", state.get("agent_settings"), model)
    language = (agent_cfg.get("output_language") or "es").lower()
    custom_template = (agent_cfg.get("prompt_template") or "").strip()
    target_word_count = int(agent_cfg.get("target_word_count") or 0)

    logger.info(f"Running Redactor — title: '{title}', model: {model}, language: {language}, words: {target_word_count or 'unlimited'}")
    log(f"✍️ Modelo: {model} | idioma: {language} | palabras objetivo: {target_word_count or 'sin límite'}")
    if feedback:
        log(f"🔄 Iteración con feedback del revisor ({len(feedback)} comentario(s))")
        for item in feedback:
            log(f"  → {item}")

    # ── RAG lookup: más fragmentos, pero solo de las fuentes citables ─────────
    # El Redactor **no añade fuentes propias** (SPEC-034/AC5): lo citable es exactamente
    # `state["sources"]`, que el Investigador construyó con documentos de DOI verificado. Antes
    # hacía su propia consulta sobre todo el RAG y pegaba esos fragmentos en `research_data`,
    # así que podía citar documentos que nunca pasaron por `sources` ni por la verificación
    # (hallazgo 0.6 de la matriz). Ahora solo amplía con fragmentos de los mismos documentos.
    #   * Citable: las fuentes de `state["sources"]` (y sus fragmentos).
    #   * Contexto: `research_data` (incluida la síntesis, que puede apoyarse en documentos sin
    #     verificar, y el feedback del revisor). Orienta; no se cita.
    #   * Sin fuentes (p. ej. un flujo sin Investigador): no hay búsqueda ni material citable.
    rag_bucket = (agent_cfg.get("rag_collection") or "").strip() or settings.QDRANT_COLLECTION
    rag_collection = collection_for_state(state, rag_bucket)
    source_doc_ids = [
        str(src["doc_id"]) for src in (state.get("sources") or [])
        if isinstance(src, dict) and src.get("doc_id")
    ]
    rag_doc_ids = agent_cfg.get("rag_doc_ids") or None
    if isinstance(rag_doc_ids, list) and len(rag_doc_ids) == 0:
        rag_doc_ids = None
    if rag_doc_ids:
        # La selección del autor solo puede restringir, nunca ampliar más allá de `sources`.
        source_doc_ids = [d for d in source_doc_ids if d in set(rag_doc_ids)]

    # Secciones sin evidencia sustantiva (SPEC-034/AC18): se declaran al modelo como hueco, también
    # con plantilla propia del autor, y se le prohíbe rellenarlas con conocimiento propio.
    aviso_cobertura = citas_cobertura.render_gaps(
        (state.get("research_coverage") or {}).get("coverage"), language,
    )
    if aviso_cobertura:
        research_data = research_data + "\n\n---\n\n" + aviso_cobertura
        log("⚠️ Hay secciones sin cobertura de evidencia: el Redactor no las rellena con conocimiento propio.", "warning")

    citation_map: Dict[str, Any] = dict(state.get("citation_map") or {})
    bloque_fragmentos = ""
    fragmentos_rag: list = []
    permitidos = set(source_doc_ids)
    if not source_doc_ids:
        log("ℹ️ Sin fuentes citables con documento en la base: el Redactor no consulta el RAG por su cuenta.")
    else:
        log(f"🔎 Ampliando desde las {len(source_doc_ids)} fuente(s) citable(s) (colección: {rag_collection}, límite: 10)...")
        try:
            rag_query = f"{title} {' '.join(keywords[:6])}"
            buscar = provider(state, "rag_results", semantic_search_results)
            fragmentos_rag = await asyncio.wait_for(
                buscar(
                    query=rag_query,
                    qdrant_url=settings.QDRANT_URL,
                    collection=rag_collection,
                    agent_name=["investigador", LIBRARY_AGENT],
                    ollama_base_url=settings.OLLAMA_BASE_URL,
                    embedding_model=settings.OLLAMA_EMBED_MODEL,
                    limit=10,
                    api_key=settings.QDRANT_API_KEY,
                    # Solo documentos de `sources`: lo que el filtro deja pasar es lo citable.
                    doc_ids=source_doc_ids,
                ),
                timeout=25.0,
            ) or []
        except asyncio.TimeoutError:
            logger.warning("Redactor RAG lookup timed out after 25s — skipping")
            log("ℹ️ RAG omitido (timeout 25s) — continuando sin contexto adicional.")
        except Exception as exc:
            logger.warning("Redactor RAG lookup failed: %s", exc)
            log(f"⚠️ RAG no disponible: {exc}", "warning")
        # Defensa en profundidad: nada fuera de `sources` llega a ser citable.
        fragmentos_rag = [f for f in fragmentos_rag if str(f.get("doc_id")) in permitidos]
        # T23.9: los fragmentos por sub-pregunta del Investigador son el material que el prompt pide
        # incorporar; sin marcador solo se podían citar como autor-año. Se marcan aunque el RAG
        # propio falle o no devuelva nada.
        fragmentos = _fusionar_fragmentos(state.get("research_fragments"), fragmentos_rag, permitidos)
        # T23.1: cada fragmento lleva un marcador [F#] estable (platform/citations.py).
        citation_map = citas.assign_cite_ids(fragmentos, state.get("citation_map"))
        bloque_fragmentos = citas.render_fragments(fragmentos, citation_map, language)
        if bloque_fragmentos:
            research_data = research_data + "\n\n---\n\n" + bloque_fragmentos
            log(f"✅ {len(fragmentos)} fragmento(s) citable(s) con marcador.")
        else:
            log("ℹ️ Sin fragmentos citables con marcador.")

    # Build context section from user-provided description and outline
    context_parts = []
    if context_description:
        if language == "es":
            context_parts.append(f"### Enfoque / Instrucciones adicionales del autor:\n{context_description}")
        else:
            context_parts.append(f"### Focus / Additional author instructions:\n{context_description}")

    if article_outline:
        if language == "es":
            context_parts.append(
                f"### ESTRUCTURA Y SECCIONES REQUERIDAS DEL ARTÍCULO:\n"
                f"Usa ESTA estructura y nombres de sección creativos provistos por el autor en lugar de los estándar:\n"
                f"{article_outline}"
            )
        else:
            context_parts.append(
                f"### REQUIRED ARTICLE STRUCTURE AND SECTIONS:\n"
                f"Use THIS structure and creative section names provided by the author instead of the default ones:\n"
                f"{article_outline}"
            )

    if context_parts:
        context_section = "\n" + "\n\n".join(context_parts) + "\n\n"
    else:
        context_section = "\n"
    feedback_section = ""
    if feedback:
        items = "\n".join(f"- {f}" for f in feedback)
        header = _FEEDBACK_HEADER_ES if language == "es" else _FEEDBACK_HEADER_EN
        feedback_section = header + items

    # Build word-count guidance blocks
    if target_word_count > 0:
        # Distribute words proportionally across sections
        abstract_w  = max(50,  int(target_word_count * 0.10))
        intro_w     = max(100, int(target_word_count * 0.25))
        method_w    = max(100, int(target_word_count * 0.25))
        results_w   = max(100, int(target_word_count * 0.25))
        discussion_w = max(60, int(target_word_count * 0.15))
        if language == "es":
            word_count_header = (
                f"\nREQUISITO DE LONGITUD: El borrador DEBE tener exactamente {target_word_count} palabras en total.\n"
                f"Distribuci\u00f3n obligatoria por secci\u00f3n:\n"
                f"  - Resumen: ~{abstract_w} palabras\n"
                f"  - Introducci\u00f3n: ~{intro_w} palabras\n"
                f"  - Metodolog\u00eda: ~{method_w} palabras\n"
                f"  - Resultados: ~{results_w} palabras\n"
                f"  - Discusi\u00f3n: ~{discussion_w} palabras\n\n"
            )
            word_count_footer = (
                f"\n\nRECORDATORIO FINAL: el manuscrito completo debe tener {target_word_count} palabras. "
                f"Escribe cada secci\u00f3n hasta alcanzar el n\u00famero indicado."
            )
        else:
            word_count_header = (
                f"\nLENGTH REQUIREMENT: The draft MUST be exactly {target_word_count} words total.\n"
                f"Mandatory per-section distribution:\n"
                f"  - Abstract: ~{abstract_w} words\n"
                f"  - Introduction: ~{intro_w} words\n"
                f"  - Methodology: ~{method_w} words\n"
                f"  - Results: ~{results_w} words\n"
                f"  - Discussion: ~{discussion_w} words\n\n"
            )
            word_count_footer = (
                f"\n\nFINAL REMINDER: the complete manuscript must be {target_word_count} words. "
                f"Write each section until you reach the word count shown above."
            )
    else:
        word_count_header = "\n"
        word_count_footer = ""

    # Render prompt: custom template takes priority over built-in
    if custom_template:
        prompt = custom_template.format(
            title=title,
            keywords=", ".join(keywords),
            research_data=research_data,
            feedback_section=feedback_section,
            context_section=context_section,
            language=language,
            word_count_header=word_count_header,
            word_count_footer=word_count_footer,
        )
    elif feedback:
        # MODO Edición y Corrección: el prompt no lleva `research_data`, así que los
        # fragmentos citables se añaden aquí para que pueda seguir citando con [F#].
        if bloque_fragmentos:
            context_section = context_section + bloque_fragmentos + "\n\n"
        # MODO Edición y Corrección
        base = _CORRECTION_TEMPLATE_ES if language == "es" else _CORRECTION_TEMPLATE_EN
        prompt = base.format(
            draft_text=state.get("draft_text") or "",
            feedback_section=feedback_section,
            context_section=context_section,
        )
    else:
        base = _DEFAULT_TEMPLATE_ES if language == "es" else _DEFAULT_TEMPLATE_EN
        prompt = base.format(
            title=title,
            keywords=", ".join(keywords),
            research_data=research_data,
            feedback_section=feedback_section,
            context_section=context_section,
            word_count_header=word_count_header,
            word_count_footer=word_count_footer,
        )

    # Scale timeout: base 300s + 1.2s per expected word (minimum 1200s for slow local models)
    timeout = max(1200.0, 300.0 + target_word_count * 1.2) if target_word_count > 0 else 1200.0
    logger.info(f"Redactor timeout: {timeout:.0f}s")
    log(f"⏳ Generando borrador (timeout: {timeout:.0f}s)...")

    emit_token = state.get("_emit_token") or (lambda t: None)

    # Secciones obligatorias: las de `gate.structure` del proyecto (T24.10). Una plantilla propia
    # o el esquema del autor (`article_outline`) piden otra estructura: no se le exigen secciones
    # que no pidió y solo cuenta el cierre de frase.
    from app.modules.agents.domain import alejandria
    secciones = [] if (custom_template or article_outline) else draft_integrity.required_sections(
        alejandria.package().gate
    )

    async def _generar(texto_prompt: str, ctx: int, tope):
        """Una generación por streaming y su veredicto de truncado (T24.9 / AC10)."""
        reset_stop_reason()
        trozos = []
        stream = provider(state, "llm_stream", call_llm_stream)
        async for token in stream(
            texto_prompt, model=model, timeout=timeout, num_ctx=ctx, keep_alive=0,
            temperature=temperature, max_tokens=tope,
        ):
            emit_token(token)
            trozos.append(token)
        resultado = "".join(trozos)
        diagnostico = draft_integrity.detect_truncation(
            resultado, last_stop_reason(), sections=secciones,
        ) if resultado else None
        if diagnostico is not None:
            diagnostico.update({"num_ctx": ctx, "max_output_tokens": tope, "model": model})
            explainability.record_truncation(diagnostico)
        return resultado, diagnostico

    try:
        draft_text, truncado = await _generar(prompt, num_ctx, max_output)

        if not draft_text:
            raise RuntimeError("LLM devolvió una respuesta vacía al generar el borrador")

        if truncado is not None:
            # La salida se cortó: no es un borrador. Un reintento con más presupuesto, y si
            # tampoco, el paso falla con motivo. Lo que no se hace es seguir al Revisor.
            motivo = draft_integrity.describe(truncado)
            nuevo_ctx, nuevo_tope = enlarge_output_budget(num_ctx, max_output, model)
            log(f"⚠️ Borrador truncado: {motivo}.", "warning")
            # Sin más presupuesto que dar solo se renuncia si el corte fue de presupuesto; un
            # texto sin cerrar con parada normal se reintenta igual, una vez (AC11).
            if (nuevo_ctx, nuevo_tope) == (num_ctx, max_output) and "stop_reason" in truncado["signals"]:
                raise RuntimeError(
                    f"Borrador truncado ({motivo}) y no hay más presupuesto de salida que dar: "
                    f"num_ctx={num_ctx} ya está en el límite de la ventana de {model}. "
                    "Sube 'max_output_tokens'/'num_ctx' del Redactor o usa un modelo con más ventana."
                )
            log(f"🔁 Reintentando con más presupuesto (num_ctx {num_ctx}→{nuevo_ctx}, "
                f"salida {max_output or 'defecto'}→{nuevo_tope or 'defecto'}).", "warning")
            draft_text, segundo = await _generar(prompt, nuevo_ctx, nuevo_tope)
            if segundo is not None or not draft_text:
                raise RuntimeError(
                    "Borrador truncado tras reintentar con más presupuesto "
                    f"(num_ctx={nuevo_ctx}): {draft_integrity.describe(segundo or {'reasons': ['empty']})}. "
                    "El paso falla en vez de pasar un texto cortado al Revisor."
                )
            # Lo que sigue (ampliación de palabras) parte del presupuesto que sí bastó.
            num_ctx, max_output = nuevo_ctx, nuevo_tope
            log("✅ El reintento produjo un borrador completo.")

        actual_words = len(draft_text.split())
        log(f"✅ Borrador generado — {actual_words} palabras.")

        # ── Word-count enforcement: retry once if significantly below target ──
        if target_word_count > 0 and actual_words < int(target_word_count * 0.85):
            shortfall = target_word_count - actual_words
            log(
                f"⚠️ Borrador corto ({actual_words}/{target_word_count} palabras). "
                f"Expandiendo {shortfall} palabras...",
                "warning",
            )
            if language == "es":
                expand_prompt = (
                    f"El siguiente borrador científico tiene solo {actual_words} palabras, "
                    f"pero DEBE tener exactamente {target_word_count} palabras.\n\n"
                    f"INSTRUCCIÓN OBLIGATORIA: Reescribe y expande el borrador añadiendo "
                    f"al menos {shortfall} palabras más. Amplía TODAS las secciones "
                    f"(Resumen, Introducción, Metodología, Resultados, Discusión). "
                    f"Añade más detalles técnicos, ejemplos concretos, análisis y referencias. "
                    f"Mantén el formato Markdown y el estilo académico.\n\n"
                    f"BORRADOR ACTUAL:\n{draft_text}\n\n"
                    f"BORRADOR EXPANDIDO ({target_word_count} palabras):"
                )
            else:
                expand_prompt = (
                    f"The following scientific draft has only {actual_words} words, "
                    f"but MUST have exactly {target_word_count} words.\n\n"
                    f"MANDATORY INSTRUCTION: Rewrite and expand the draft by adding at least "
                    f"{shortfall} more words. Expand ALL sections (Abstract, Introduction, "
                    f"Methodology, Results, Discussion). Add more technical details, "
                    f"concrete examples, analysis and references. "
                    f"Maintain Markdown format and academic style.\n\n"
                    f"CURRENT DRAFT:\n{draft_text}\n\n"
                    f"EXPANDED DRAFT ({target_word_count} words):"
                )
            try:
                expanded, expansion_truncada = await _generar(expand_prompt, num_ctx, max_output)
                if expansion_truncada is not None:
                    # Una ampliación cortada no sustituye al borrador, que ya estaba entero.
                    log("⚠️ La ampliación salió truncada; se conserva el borrador original.", "warning")
                elif expanded:
                    expanded_words = len(expanded.split())
                    if expanded_words > actual_words:
                        draft_text = expanded
                        log(f"✅ Borrador expandido — {expanded_words} palabras.")
                    else:
                        log("ℹ️ La expansión no incrementó el conteo; usando borrador original.")
            except Exception as expand_err:
                logger.warning("Word-count expansion attempt failed: %s", expand_err)
                log(f"⚠️ No se pudo expandir: {expand_err}", "warning")

        # T23.1: lee las citas [F#] del borrador contra el mapa. No persiste (T23.2) ni
        # juzga (T23.3): deja en el estado el contrato que esos pasos consumen.
        leidas = citas.extract_citations(draft_text, citation_map)

        # T23.9 / AC10: habiendo fragmentos citables, un borrador sin ninguna cita [F#] válida
        # (p. ej. solo «(Título, 2024)») se reintenta UNA vez con el formato recordado. Es otro
        # mecanismo que el de truncado (T24.9): aquel falla el paso, este solo avisa.
        citables = len(citation_map) if bloque_fragmentos else 0
        comprobacion: Dict[str, Any] = {
            "citable_fragments": citables, "retried": False, "no_citations": False,
            "author_year": list(leidas["author_year"]),
        }
        if citables and not leidas["valid_citations"]:
            log("⚠️ El borrador no cita ningún fragmento con [F#]"
                + (f" (citas autor-año no válidas: {', '.join(leidas['author_year'][:3])})" if leidas["author_year"] else "")
                + ". Reintentando una vez con el formato recordado.", "warning")
            comprobacion["retried"] = True
            try:
                segundo, trunc2 = await _generar(prompt + citas.format_reminder(language), num_ctx, max_output)
                if segundo and trunc2 is None:
                    leidas2 = citas.extract_citations(segundo, citation_map)
                    # Se queda con el reintento solo si mejora: cita con [F#] o al menos no inventa autor-año.
                    if leidas2["valid_citations"] or len(leidas2["author_year"]) < len(leidas["author_year"]):
                        draft_text, leidas = segundo, leidas2
                        comprobacion["author_year"] = list(leidas["author_year"])
                else:
                    log("⚠️ El reintento de citas salió vacío o truncado; se conserva el borrador.", "warning")
            except Exception as retry_err:  # no falla el paso: la compuerta sigue en modo aviso
                logger.warning("Citation-format retry failed: %s", retry_err)
                log(f"⚠️ No se pudo reintentar el formato de citas: {retry_err}", "warning")
            if leidas["valid_citations"]:
                log("✅ El reintento citó con [F#].")
            else:
                comprobacion["no_citations"] = True
                log("⚠️ Sin citas [F#] válidas tras reintentar: se registra `no_citations` en la traza y se "
                    "avisa al Revisor y al autor. El paso no falla.", "warning")
        if leidas["unresolved"]:
            log(f"⚠️ Marcadores de cita sin fragmento: {', '.join(leidas['unresolved'])}", "warning")
        log(f"🔗 {leidas['valid_citations']} cita(s) vinculada(s) a fragmentos.")
        return {
            "draft_text": draft_text,
            "citation_map": citation_map,
            "citations": leidas["citations"],
            "citations_unresolved": leidas["unresolved"],
            "citations_text_hash": leidas["text_hash"],
            "citation_check": comprobacion,
        }
    except RuntimeError:
        raise
    except Exception as e:
        logger.exception("Error calling LLM in Redactor")
        raise RuntimeError(f"Failed to call LLM: {type(e).__name__}: {e}") from e
