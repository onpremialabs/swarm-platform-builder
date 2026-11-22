# Tarea #525 — T22.2 Verificación de candidatos (DOI, duplicados, fecha futura) reutilizando el resolver de la compuerta

## 2026-11-22 13:35 — Completada ✅

- **Rama:** `feat/525-verificacion-candidatos`
- **PR:** ver PR de la rama → `develop` (`Closes #525`)
- **Spec/ADR:** SPEC-034 (AC2, AC10, §Clarifications); SPEC-032 (V09 nivel 2) y [ADR-0011](../adr/0011-publication-gate-fail-closed.md); SPEC-037/T25.2 (lógica de fechas parciales)
- **Dependencias:** #524 (T22.1, capacidad `literature`) cerrada, en `develop` desde la PR #608

### Dónde estaba el problema
`search_literature` devuelve `Candidate` con `verified=False` y nada los comprobaba: un
registro inventado, mal fechado o repetido por dos bases se habría ofrecido a la persona
autora. Verificar es V09 nivel 2, que ya hace `publication_gate/reference_resolver.py`, pero
su sesión estaba atada a `quien="publication_gate"`, a las métricas de la compuerta y a su
`User-Agent`, y devolvía solo un texto como causa.

### Qué se hizo y por qué
- `backend/app/platform/capabilities/literature/verification.py` (nuevo): `verify_candidates(
  candidates, searched_at, ...)` -> `VerificationResult` con `verified` (`VerifiedCandidate`:
  DOI verificado, proveedor, `verified_at`, `verification_method='doi_resolved'`, `found_in`,
  `already_in_library`, `doi_origin`) y `discarded` (`DiscardedCandidate` con motivo en
  `no_identifier | unresolved | metadata_mismatch | duplicate | future_date |
  resolver_unavailable`). Orden: fecha futura (sin red) -> duplicados por DOI -> resolución
  (concurrencia 4) -> duplicados que solo se ven tras resolver -> marca de biblioteca.
  `log_fields()` entrega `result_count`, `verified_count`, `discarded`, `status`, `searched_at`
  con los nombres de `search_logs`/`record_search` (T22.7 no rehace nada); `per_source` y
  `search_status()` completan. Helpers sin API: `library_dois_of`, `library_fields` y
  `add_candidate_to_library` (`curation_status='candidate'`, vía `library.add_document`).
- `publication_gate/reference_resolver.py` (refactor mínimo, sin cambio de comportamiento):
  `_Session` recibe `metrics` (`ResolverMetrics`; por defecto `GATE_METRICS`, que llama a
  `observe_gate_*` resueltos en la llamada) y `user_agent`; nuevos `fetch_for(quien)`,
  `open_session(...)` y `resolve_reference(...)`; `ReferenceOutcome.kind` (causa estructurada:
  `not_found`, `mismatch`, `unavailable`, `no_search_data`, `no_match`, `ambiguous`). Los
  llamadores de la compuerta no cambian: `check_reference_existence` sigue usando
  `_default_fetch` (`quien="publication_gate"`) y sus métricas. La alternativa de copiar el
  resolver o de pasar `quien` por parámetros sueltos se descartó: duplicaba umbrales y reglas
  de autores/año, justo lo que SPEC-034 pide no duplicar.
- `egress.py`: `api.datacite.org` añadido a `HOSTS_LITERATURA` (no estaba; la compuerta sí lo
  tenía). Hace falta para los DOI de arXiv. Con `EGRESS_ALLOWED_DOMAINS` definida sigue abierto
  solo para `literature_discovery` y `publication_gate`, no para `fetch_url`.
- `literature/__init__.py` exporta la verificación; `CLAUDE.md` y `data-retention.md` anotan que
  la verificación usa el resolver de la compuerta y qué sale a terceros (DOI o título y autores
  de metadatos ya publicados).
- `tests/test_literature_discovery.py`: el test de hosts ya no afirma que DataCite esté cerrado
  para la capacidad (ahora lo está abierto, y se comprueba que `egress` no lo gana).
- `tests/test_literature_verification.py`: 45 tests sin red.

### Decisiones
- **Sin DOI (regla 1, ADR-0011):** arXiv -> el DOI se deriva del identificador
  (`10.48550/arxiv.<id>`; el cliente ya lo hace y aquí es red de seguridad) y se resuelve por
  DataCite, que es el registrador. PubMed -> solo vale el DOI que informe la base; no hay
  conversión PMID->DOI propia (habría que llamar a otro servicio). Para el resto y PubMed sin DOI
  se busca por título y autores con las reglas del resolver: un único candidato fiable fija el
  DOI (`doi_origin='resolved_by_title'`); ninguno o varios -> `unresolved`; sin título y autores
  con los que buscar -> `no_identifier`.
- **Mismas reglas que la compuerta (título >= `gate.references.title_similarity`, primer autor
  y resto, año con tolerancia de preprint).** Así lo que pasa aquí no falla luego al citarlo. Es
  estricto: un candidato sin autores o con año de impresión distinto del en línea se descarta
  como `metadata_mismatch`. La revista **no** se compara (cada base la nombra a su modo, y es la
  señal más débil). El llamador pasa `resolver=` con `gate.references` del proyecto.
- **Duplicados:** por DOI normalizado, antes de consultar (ahorra peticiones; la caché solo guarda
  positivos); gana el de más campos informados (autores, año, fecha, revista, resumen, URL, OA),
  a igualdad el primero; `found_in` lista todas las bases. Si el ganador no resuelve, los
  repetidos no se reintentan (mismo DOI, mismo veredicto de existencia). Los DOI hallados por
  título se deduplican otra vez tras resolver. Los que ya están en la biblioteca no se descartan:
  `already_in_library=True` (el llamador pasa `library_dois_of(...)`).
- **Fecha futura:** solo si **todo** el intervalo de publicación es posterior al día de
  `searched_at` (misma `_tramo` que `publication_gate/dates.py`); sin fecha ni año, no se juzga;
  una fecha imposible tampoco. Se evalúa primero, sin red.
- **Falla cerrada:** caída, 429/5xx tras los reintentos, tiempo máximo agotado o excepción
  inesperada -> `resolver_unavailable` (`not_verified=True`), nunca verificado. Un 404 de un
  proveedor con el otro caído no se toma por «no existe».
- **Métricas:** la verificación usa `NO_METRICS` para no contaminar las de la compuerta; unas
  métricas propias del descubrimiento (SPEC-034 §7) quedan para T22.7.

### Definition of Done
- [x] **AC2** — se descartan los que no resuelven por DOI/ID (`unresolved`, `no_identifier`,
  `metadata_mismatch`), los duplicados (`duplicate`) y los de fecha posterior a la de la
  búsqueda (`future_date`); los no verificados, incluidos los que el resolver no pudo comprobar,
  no se ofrecen (`resolver_unavailable`). `VerificationResult.searched_at` conserva la fecha de
  corte y `log_fields()` la entrega para el registro (AC6, T22.7).
- [x] **AC10 (parte de verificación)** — resolver caído o limitado: reintentos del resolver y
  descarte `not_verified`; nunca verificado por defecto.

### Verificación
- `DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q tests/test_literature_verification.py` -> 45 passed.
- Suite completa desde `backend/` (`DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q`) -> 1694 passed, 38 skipped, 1 failed: `test_a_fresh_dev_database_is_created_and_migrated` (WinError 32 en Windows, conocido y ajeno). Incluye intactos `test_gate_*`, `test_reference_measurement` y `test_publicador_compuerta`.
- `PYTHONIOENCODING=utf-8 python -m evals.agent_behavior.gate` -> sin métricas por debajo del umbral (ningún agente usa aún la capacidad; el refactor de la compuerta no cambia su comportamiento).
- Dos tests de T22.1 se ajustaron a propósito: hosts de la capacidad (+ DataCite) y «el paquete no depende de la compuerta» (excepción: `verification.py`).
- No se llamó a ninguna API real: los tests inyectan `fetch`/`egress.safe_get`.

### Fuera de alcance / notas
- `search_logs` (T22.7), API y UI de curación (T22.8), Investigador (T22.5), descarga de PDFs
  (T22.10), resolución de DOI de PDFs subidos (T22.4; `resolve_reference` ya sirve para ello).
- Las respuestas simuladas siguen la forma que el resolver ya parsea (Crossref, OpenAlex,
  DataCite); no se contrastaron en vivo en esta tarea.
