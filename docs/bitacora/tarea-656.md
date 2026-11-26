# Tarea #656 — T24.8: la decisión humana sin respuesta no es «continuar»

## 2026-11-26 18:56 — Completada (AC9)

- **Rama:** `fix/656-hitl-sin-respuesta-no-continua`
- **PR:** pendiente de número → `develop` (`Closes #656`)
- **Spec/ADR:** SPEC-036 (AC9, «Decisión por omisión y truncado»); SPEC-032/AC7 (`requires_human_review`)
- **Dependencias:** el issue dice «Bloqueada por #544» (T24.3), **aún abierta**. **Se salta por orden expresa de la persona usuaria**: se implementa solo AC9 sobre el router actual (`make_review_router`) y **no** se toca la regla de reversión / `best_draft` de T24.3.

### Dónde estaba el problema
Prueba real del 2026-11-26: un borrador con score 45 y `coherent: false` llegó al Formateador sin que nadie decidiera. `request_user_decision` devolvía `"continue"` al vencer `_DECISION_TIMEOUT` (900 s) y `revisor.py` fijaba `user_decision="continue"` al llegar a `MAX_SOURCE_RETRIES`; el enrutador da prioridad a `continue`, y la traza lo registraba como `hitl_outcome: continue`, indistinguible de una persona.

### Qué se hizo y por qué
- `platform/engine/routing.py`: `EXPLICIT_DECISIONS = (add_source, continue)` y `NO_RESPONSE`. El router ignora cualquier `user_decision` que no sea explícita y sigue por umbral y vueltas; agotadas, `on_exhausted: stop` → `requires_human_review`.
- `application/use_cases.py`: `request_user_decision` devuelve `{decision, by, at}`; al vencer el tiempo `decision = no_response` (no «continue») y el SSE `decision_resolved` lleva `timed_out: true`. `submit_user_decision(..., by)` anota quién y cuándo y los emite en `decision_resolved`.
- `platform/bus.py` (memoria y Redis): `submit_decision(..., by, at)` los lleva hasta el `Future` aunque lo resuelva otro worker; sin `by` conserva la cadena de siempre (compatibilidad).
- `adapters/revisor.py`: sin canal de decisión, tope de fuentes alcanzado o sin respuesta → `user_decision = None` y `hitl = {origin, outcome: no_response, by: None, at}`; decisión explícita → `hitl.origin = person` con `by`/`at`. Acepta también el canal antiguo que devolvía una cadena. `hitl` se reinicia en cada pasada.
- `platform/explainability.py`: `decision.hitl` y `hitl_outcome = no_response` en `agent_run_steps.decision`. Sin esquema nuevo (columna JSON existente).
- `routers/agents.py`: `POST /agents/{id}/decision` pasa el usuario autenticado (`by`); sigue aceptando solo `continue` y `add_source`.
- Frontend: `ExecutionPage.jsx` ya no rotula como «continuar» un `decision_resolved` con `timed_out`; clave `execution.log.decisionNoResponse` en es/en.
- Docs: `docs/api/agents.md` y nota de implementación en SPEC-036 (sin marcar el estado de issues).
- `data-retention.md`: sin cambios; el rastro (`hitl.by` = id de usuario) va en `agent_run_steps.decision`, ya cubierto por su ventana de retención y no añade tablas.

### Definition of Done
- [x] Sin respuesta (sin oyente / tiempo vencido / sin canal) no es «continuar»: vuelve al Redactor mientras quedan vueltas y, agotadas, `requires_human_review` — `test_ejecucion_sin_oyente_con_score_bajo_no_llega_al_formateador`, `test_no_response_no_salta_la_revision`.
- [x] Solo una decisión explícita de una persona salta la revisión; la traza distingue persona de «sin respuesta», con quién y cuándo — `test_una_decision_explicita_de_una_persona_*`, `test_vencer_el_tiempo_*`, `test_la_decision_de_una_persona_lleva_quien_y_cuando`.
- [x] Caso de ejecución sin oyente con score < umbral que no llega al Formateador — `tests/test_hitl_no_response.py` (revisor real, score 45, tiempo vencido: 3 vueltas, sin Formateador/Publicador, `REQUIRES_HUMAN_REVIEW`, evento `timed_out`).

### Verificación
- `DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q tests/test_hitl_no_response.py tests/test_review_exhausted.py tests/test_bus_multiworker.py tests/test_revisor_budget.py tests/test_revisor_fail_closed.py tests/test_explainability_trace.py` → 89 passed, 15 skipped (los skipped son los de Redis).
- `tests/test_hitl_no_response.py` → 9 passed.
- `cd frontend && npm run build` → OK.
- Suite completa de `backend/`: 2121 passed, 38 skipped, 1 failed (`test_no_tracked_databases`, WinError 32 al borrar un `dev.db` temporal en Windows; conocido y ajeno).

### Notas y trabajo para T24.3
- T24.3 (reversión a `best_draft`) deberá reconciliar: en los casos «sin respuesta» el router recibe `user_decision = None`, así que su regla de reversión actuará sobre un estado sin decisión humana. El ajuste de `review_exhausted` ante `continue` sigue siendo válido.
- No se verificó contra un Ollama real ni con un oyente SSE real; el tiempo de espera se probó acortando `_DECISION_TIMEOUT`.
