# Tarea #635 — T23.8 Cablear el mapa de citas: guardarlo tras el Redactor sobre el texto final, activar el criterio en modo aviso y enlazar documento/página

## 2026-11-23 15:45 — Completada ✅

- **Rama:** `feat/635-cablear-mapa-citas`
- **PR:** ver la PR con `Closes #635` → `develop`
- **Spec/ADR:** SPEC-035 (AC1, AC6, AC9; §1 «Hallazgo» y §4 «Cableado del mapa»), ADR-0011 (falla cerrada)
- **Dependencias:** #534, #535, #536, #539 (cerradas)

### Dónde estaba el problema
`save_citation_map` y `to_citation_inputs` (`backend/app/platform/citations.py`) no tenían llamador:
el mapa de AC1 no se guardaba en ninguna ejecución, así que `citation_support` no se podía declarar
(bloquearía todo por `no_citations`), la pestaña Fuentes salía siempre vacía y el enlace
`/dashboard/documents?doc=…&page=…` no llevaba a ningún sitio porque `DocumentsPage` ignoraba los parámetros.

**Dónde se fija el texto final (investigado):** el Formateador devuelve `formatted_text` (y siempre añade la
bibliografía determinista, así que el texto casi nunca coincide con la salida del Redactor). El Publicador toma
`formatted_text or draft_text`, le quita los metadatos escritos por el LLM (`strip_llm_metadata`) y lo asigna a
`article.body` (`adapters/publicador.py`); `evaluate_and_store` evalúa y versiona el informe con la huella de ese
`article.body`, y `current_citation_map` busca por esa misma huella. Por tanto el único punto correcto para guardar el
mapa es el Publicador, justo antes de evaluar; hacerlo en el Redactor lo dejaría con la huella equivocada.

### Qué se hizo y por qué
- `adapters/publicador.py`: nueva `_save_citation_map` (llamada desde `_apply_gate`, solo si la plantilla declara
  `gate.citation_support`). Guarda el mapa con `save_citation_map(session, article.id, article.body,
  to_citation_inputs(state["citations"]), run_id=…)` dentro de un `begin_nested()` (un fallo no ensucia la transacción
  del artículo). Idempotente por huella (reejecutar no duplica ni pierde confirmaciones). Si falla, se avisa en el log y
  se pasa `citation_map_unavailable=True`. Además registra un aviso por cada criterio en modo aviso que no pasa.
- `publication_gate/service.py`: `evaluate_and_store(..., citation_map_unavailable=False)`; con `True` el criterio recibe
  `citations=None` → `map_unavailable` (not_verified), no se omite. Pasa `settings.CITATION_SUPPORT_ENFORCE` a la compuerta.
- `publication_gate/types.py` y `gate.py`: `CriterionResult.advisory` (por defecto `False`); un criterio `advisory` conserva
  su estado real (`not_verified`) y su evidencia pero **no bloquea**; el informe serializado lleva `advisory`. Sin
  `citation_support` declarado nada cambia (parámetro por defecto `True` = comportamiento anterior).
- `core/config.py`, `config.yaml` (raíz y `backend/`), `.env.example` y `backend/.env.example`: nuevo interruptor
  `CITATION_SUPPORT_ENFORCE` (apagado por defecto; yaml `publication.citation_support_enforce`). No existía antes.
- `projects/alejandria-magazine/template.yaml`: `gate.citation_support: {min_overlap: 0.25}` y
  `responsible.citation_support: redactor`.
- `docs/governance/publication-gate-rollout.md`: sección del despliegue en modo aviso y de cuándo pasar a bloqueo.
- Frontend: `platform/pages/DocumentsPage.jsx` lee `doc` y `page` (`useSearchParams`), desplaza el documento a la vista,
  le da el foco, `aria-current` y contorno, y muestra una línea `role="status"` con el documento y la página citados (o
  que no está). Textos nuevos en `platform/i18n/{es,en}.json` (`documents.citedTarget`, `citedTargetNoPage`,
  `citedNotFound`); sin literales nuevos en `.jsx`. No se tocó `main.jsx` ni el selector de idioma.
- La pestaña Fuentes (`ArticleCitations.jsx`, T23.6) no necesitó cambios: ahora recibe filas reales porque el mapa se guarda.
- `backend/tests/test_citation_map_wiring.py` (nuevo).

### Definition of Done
- [x] **AC1** — con un borrador con citas, el mapa `cita → {doc_id, página, extracto, hash}` se guarda por cada afirmación
  citada, versionado con la huella del texto evaluado (`test_current_citation_map_devuelve_filas…`: doc-1, página 7, extracto, `excerpt_sha256`).
- [x] **AC6** — la pestaña Fuentes muestra citas reales (estado, extracto, enlace a documento/página, confirmación con quién/cuándo, ya
  existentes en T23.6) y el enlace coloca al usuario en el documento (`DocumentsPage`).
- [x] **AC9** — mapa versionado con la huella del texto final tras Formateador (probado con y sin Formateador que reescribe; no
  existe ninguna fila con la huella de la salida del Redactor); `citation_support` declarado y evaluado en modo aviso con
  `CITATION_SUPPORT_ENFORCE` documentado; sin citas / mapa no guardado → `not_verified` visible y no silencioso, sin bloquear
  en aviso (y bloqueando con `CITATION_SUPPORT_ENFORCE=true`); sin `gate.citation_support` declarado, no se evalúa ni se guarda nada.

### Verificación
- Suite completa de backend (`DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q`, una vez, 12 min) → 1909 passed, 38 skipped, 5 failed:
  `test_no_tracked_databases` (WinError 32, fallo conocido de Windows) y 4 míos por el cambio de plantilla, corregidos y repetidos:
  `test_publication_gate.py` (3: la plantilla ahora declara `citation_support`, la lista esperada de criterios ganó ese criterio y el modo aviso
  se hace efectivo también al llamar a `evaluate_gate` directamente, leyendo `CITATION_SUPPORT_ENFORCE`) y `test_gate_citation_support.py` (1: prueba el
  bloqueo, ahora fija `CITATION_SUPPORT_ENFORCE=True`).
- Repetición de los afectados (publication_gate, gate_citation_support, explain, deployment, publicador_compuerta, project_template) → 92 passed.
- Repetición ampliada (citation_map_wiring [10 tests], engine_capability_parity, investigador_verified_only, i18n_checks, frontend_gate,
  edd_citation_support, approval, published_single_gate, gate_report_api, gate_rollout_report, no_tracked_databases) → 150 passed, 1 failed
  (`test_no_tracked_databases`, WinError 32 conocido).
- `npm run build` y `npm run build:public` → OK. `python scripts/check_i18n.py` → OK (línea base sin ampliar).

### Pantallas a revisar a mano
1. **Artículo → historial/trazabilidad → pestaña Fuentes**: lista de citas con estado «sin verificar», extracto, enlace
   «documento/página» y botón «Confirmar».
2. **Pulsar el enlace**: abre Documentos con el documento contorneado, el foco en él y la línea «Documento citado: …
   Página citada: N…». Con un documento borrado, el aviso «no está en esta biblioteca».
3. **Informe de la compuerta** del artículo: el criterio `citation_support` aparece con su estado y motivos, marcado `advisory`.

### Fuera de alcance / notas — qué se ve en una instalación real
- No se implementó el juez de modelo (T23.4) ni retractaciones: las citas quedan `not_verified` en el mapa (estado automático
  del juez) y solo el solape determinista puede marcarlas para revisión humana.
- `page` es `None` hasta que la indexación guarde la página (SPEC-035 §5): en una instalación real el enlace puede no llevar
  página y la línea de estado dice solo «Documento citado». La biblioteca no tiene visor por páginas: la página se **informa**, no se abre.
- Si el Formateador reescribe `[F#]` a otro estilo, las filas del mapa siguen existiendo (se guardan desde las citas del
  Redactor), pero el texto final ya no contiene marcadores; la compuerta no las marca como huérfanas.
- Un artículo editado a mano tras la ejecución cambia la huella: `current_citation_map` queda vacío hasta reejecutar (comportamiento previo, deliberado).
- Supuesto no verificado contra una instalación real: que el `doc_id` del mapa (payload de Qdrant) coincida con el `doc_id` que lista la biblioteca.
- Pasar a bloqueo (`CITATION_SUPPORT_ENFORCE=true`) es una decisión posterior con datos de falsos positivos.
