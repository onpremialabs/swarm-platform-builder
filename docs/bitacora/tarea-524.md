# Tarea #524 — T22.1 Capacidad `literature` con clientes OpenAlex, Crossref, Semantic Scholar, arXiv y PubMed por `safe_get`

## 2026-11-22 12:55 — Completada ✅

- **Rama:** `feat/524-capacidad-literature`
- **PR:** ver PR de la rama → `develop` (`Closes #524`)
- **Spec/ADR:** SPEC-034 (AC1, AC10, §Clarifications); relacionado SPEC-024 (egress), SPEC-032 / ADR-0011
- **Dependencias:** ninguna (T22.3, #607, ya mergeada: se alinean nombres con `library_documents`)

### Dónde estaba el problema
No existía ninguna capacidad de descubrimiento: el Investigador solo consulta el RAG local
(`adapters/investigador.py`) y la única búsqueda externa era `ddg_search_with_urls`
(arXiv/Wikipedia) en `capabilities/tools.py`. Tampoco había forma de decir en la plantilla
qué bases bibliográficas usa un proyecto.

### Qué se hizo y por qué
- `backend/app/platform/capabilities/literature/` (paquete nuevo):
  - `models.py`: `Candidate` (campos = columnas de `library_documents`; `verified` es
    `init=False` y siempre `False`), `build_candidate` (falla cerrada: sin título o sin
    DOI/id de la base no hay candidato), `BaseReport`/`LiteratureResult`.
  - `transport.py`: `ApiSession.request`, único punto que llama a `egress.safe_get(quien=
    "literature_discovery")`. Reintenta con espera exponencial timeout, red, 429
    (respetando `Retry-After` con tope), 5xx y respuesta inválida (JSON o XML que no se
    interpreta, incluida una forma inesperada); no reintenta 4xx ni un bloqueo de egress.
  - `openalex.py`, `crossref.py`, `semantic_scholar.py`, `arxiv.py`, `pubmed.py`: una
    función `parse` pura y una `search` por base. PubMed hace `esearch` + `efetch`.
  - `discovery.py`: `search_literature(query, sources)` consulta las bases en paralelo;
    una que falla queda como `BaseReport(status="failed")` con causa e intentos y no tumba
    a las demás; Semantic Scholar sin clave queda `skipped`. Rechaza la consulta vacía o de
    más de 300 caracteres (privacidad: solo sale la cadena de búsqueda).
  - `research.py`: `parse_research` del bloque `research:`.
- `capabilities/registry.py`: `CapabilityKind.LITERATURE` y capacidad `literature`.
  `binding.py` no necesita cambios (resuelve por nombre).
- `platform/egress.py`: `HOSTS_LITERATURA` y `QUIEN_LITERATURA`; se generaliza el patrón
  de la compuerta a un mapa `quien -> hosts` (`_HOSTS_POR_QUIEN`). Con
  `EGRESS_ALLOWED_DOMAINS` definida los hosts solo se suman para ese `quien`; la
  compuerta conserva los suyos y `fetch_url` no gana ninguno.
- `projects/loader.py` + `projects/alejandria-magazine/template.yaml`: bloque
  `research.sources` (por defecto `[openalex, crossref]`), validado al cargar; base
  desconocida, lista vacía/repetida o clave desconocida -> `TemplateError`. No se añade
  `research.min_sources` (T22.5): hasta entonces se rechaza como clave desconocida.
- `core/config.py`, `.env.example`, `backend/.env.example`: `LITERATURE_CONTACT_EMAIL`,
  `SEMANTIC_SCHOLAR_API_KEY`, `NCBI_API_KEY` (solo por entorno, sin valor),
  `LITERATURE_TIMEOUT_S/RETRIES/BACKOFF_S/MAX_BACKOFF_S/MAX_RESULTS` (configurables).
- Docs: `CLAUDE.md` (capacidad y egress) y `docs/governance/data-retention.md` (qué sale
  a las bases bibliográficas).
- `tests/test_literature_discovery.py`: 56 tests sin red.

### Decisiones
- **Semantic Scholar sin clave**: ni falla al cargar ni se desactiva en silencio. La
  plantilla es un dato del proyecto y no debe ser válida o inválida según el entorno donde
  se cargue; por eso la base es válida en `sources` y, al consultar, se omite con
  `BaseReport(status="skipped", error_kind="missing_api_key")`, mensaje explícito y
  `logger.warning`. `result.complete` es `False` mientras haya una omitida.
- **Reintentos**: 2 reintentos (3 intentos), espera `1 s * 2^n`, tope 30 s, timeout 10 s;
  todo configurable por entorno (`LITERATURE_*`).
- **Reutilización del resolver de la compuerta: no se reutiliza.** `reference_resolver`
  parsea Crossref/OpenAlex a `Canonical` (título, apellidos, año, revista), sin resumen,
  URL, fecha completa ni acceso abierto, y su `_Session` está atada a `quien="publication_gate"`
  y a las métricas de la compuerta. Importarlo acoplaría la capacidad a la compuerta. Solo
  se repite `normalize_doi` (3 líneas), y un test comprueba que coincide con el de la
  compuerta y con el de `library_document`. La reutilización para verificar es T22.2.
- **XML**: sin `defusedxml` en el lock, `xml_root` rechaza respuestas con `<!ENTITY`;
  el `DOCTYPE` de `efetch` (sin entidades) es válido.
- El mismo mapa de hosts incluye `export.arxiv.org` y `eutils.ncbi.nlm.nih.gov`; la
  descarga de PDFs de acceso abierto (T22.10) quedará fuera de esta lista y deberá
  resolverse allí.

### Definition of Done
- [x] **AC1** — se consultan las bases de `research.sources` (por defecto OpenAlex y Crossref; Semantic Scholar solo con clave; arXiv y PubMed si el proyecto las activa; base desconocida falla al cargar la plantilla) solo por `safe_get(quien="literature_discovery")`; con `EGRESS_ALLOWED_DOMAINS` los hosts se añaden solo para esta capacidad. Tests: `test_consulta_por_defecto…`, `test_con_allowlist_los_hosts…`, `test_una_base_mal_escrita_falla_al_cargar…`, `test_el_paquete_no_abre_clientes_http…`.
- [x] **AC10** — fallo o límite de API: reintentos con espera exponencial y error claro por base, resultado parcial explícito, sin candidatos incompletos ni «verificados». Tests: `test_reintenta_…`, `test_429_…`, `test_agotados_los_reintentos…`, `test_el_fallo_de_una_base_no_tumba…`, `test_ningun_candidato…`.

### Verificación
- `DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q tests/test_literature_discovery.py` -> 56 passed.
- Suite completa desde `backend/` (`python -m pytest -q`) -> 1648 passed, 38 skipped, 1 failed: `test_a_fresh_dev_database_is_created_and_migrated` (WinError 32 en Windows, conocido y ajeno).
- `PYTHONIOENCODING=utf-8 python -m evals.agent_behavior.gate` -> sin métricas por debajo del umbral. Ningún agente usa aún la capacidad, así que no hay efecto EDD.
- No se llamó a ninguna API real (los tests inyectan `safe_get`).

### Fuera de alcance / notas
- Verificación, deduplicación y fecha futura (T22.2); registro en `search_logs` (T22.7);
  UI; Investigador y `research.min_sources` (T22.5); descarga de PDFs (T22.10).
- Las formas de respuesta de las APIs se tomaron de su documentación y se fijaron en
  fixtures reducidos; no se contrastaron en vivo, así que un cambio de formato real se
  vería como `invalid_response` (falla cerrada), no como datos erróneos.
