# Tarea #661 — T24.10: Redactor, tratar como truncado el borrador sin secciones obligatorias o sin cierre aunque la parada sea normal

## 2026-11-25 07:55 — Completada ✅

- **Rama:** `fix/661-heuristica-truncado-siempre`
- **PR:** pendiente de número → `develop` (`Closes #661`)
- **Spec/ADR:** SPEC-036 (AC10, AC11)
- **Dependencias:** #657 (T24.9) cerrada

### Dónde estaba el problema
`draft_integrity.detect_truncation` (T24.9) solo aplicaba la heurística si el proveedor no informaba
motivo de parada. En una prueba de punta a punta con `qwen3.5:9b` y `num_ctx=16384` el borrador acabó
en «(HarnessDev, 2024» sin Discusión, el proveedor dijo parada normal y el texto pasó al Revisor.

### Qué se hizo y por qué
- `backend/app/platform/draft_integrity.py`: la heurística (secciones obligatorias + frase sin cerrar)
  se aplica **siempre**. El motivo de parada solo añade la señal: el diagnóstico lleva `signals`
  (`stop_reason` y/o `heuristic`); `signal` es la principal (`stop_reason` si el proveedor cortó; si no,
  `heuristic`). Una parada normal con un texto entero devuelve `None` (sin reintento).
- Las secciones **salen de `gate.structure`** de la plantilla (`required_sections(gate)`), no de listas
  es/en en código: cada sección acepta los títulos de **todos** los idiomas declarados (sin falsos
  positivos por idioma ni por variante: Metodología/Métodos/Materials and Methods; numeración;
  negrita; un encabezado «Resultados y Discusión» cuenta para ambas, su fusión la juzga la compuerta).
  Se eliminó `SECCIONES_IMRAD` y el parámetro `language`/`require_sections`.
- `references` no se exige al Redactor (`SECCIONES_FUERA_DEL_REDACTOR`): el Formateador construye la
  lista en código y el prompt del Redactor no la pide.
- `adapters/redactor.py` (bloque de truncado únicamente): resuelve las secciones desde
  `alejandria.package().gate`; si el corte es solo heurístico y no hay más presupuesto que dar, igual se
  reintenta una vez con el mismo presupuesto (antes fallaba sin reintentar). Si persiste, el paso falla
  con motivo y no avanza al Revisor. No se tocó el prompt ni el manejo de citas.
- **Plantilla propia y esquema del autor (`article_outline`)**: decisión — no se exigen secciones
  (solo cuenta el cierre de frase y el motivo de corte), porque el autor define sus propios encabezados
  y no debe fallar por secciones que no pidió. **Vueltas del bucle del Revisor** (modo corrección): se
  exigen las secciones del proyecto igual que en la primera redacción, salvo que haya esquema del autor.
- Tests: `tests/test_redactor_truncation.py` (caso HarnessDev con parada normal sin pasar al Revisor,
  reintento y recuperación, borrador completo sin reintento, falsos positivos por idioma/título,
  esquema del autor, secciones desde la plantilla; los de AC10 siguen en verde).

### Definition of Done
- [x] Parada normal + faltan secciones o frase sin cerrar => truncado, señal `heuristic` en la traza, un reintento, falla con motivo, no pasa al Revisor.
- [x] Heurística siempre aplicada; el motivo de parada solo añade `stop_reason`.
- [x] Borrador que termina bien no se reintenta; sin falsos positivos por idioma/título.
- [x] Caso de prueba «(HarnessDev, 2024» sin Discusión con parada normal.

### Verificación
- `cd backend && DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q tests/test_redactor_truncation.py` → 32 passed.
- Suite completa (`DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q`, sin `-p no:logging`): 2062 passed; fallos: 7 de entorno (`test_language_selector`, `test_traceability_abstention`: falta `node_modules`/vite en el worktree nuevo) y 8 tests que usaban dobles con borradores minimos y parada «stop» (precisamente lo que AC11 deja de aceptar).
- Esos dobles se corrigieron (borrador entero): `test_redactor_citations`, `test_investigador_verified_only`, `test_investigador_subqueries`; en `test_published_single_gate` el caso «incompleto» pasa a ser un borrador entero con orden roto (`out_of_order`), porque uno incompleto ya no llega a la compuerta: lo para el Redactor. Tras ello los archivos relacionados con redactor/orquestador: verdes.

### Notas
`redactor.py` lo toca en paralelo T23.9 (citas [F#]); el cambio aquí es acotado al bloque de truncado.
