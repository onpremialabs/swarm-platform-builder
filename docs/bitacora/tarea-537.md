# Tarea #537 — T23.4 Juez independiente de soporte con modelo distinto al redactor y muestra humana

## 2026-11-24 05:55 — Completada ✅

- **Rama:** `feat/537-juez-independiente-soporte`
- **PR:** ver la PR con `Closes #537` → `develop`
- **Spec/ADR:** SPEC-035 (AC3, AC7; §5 riesgo «juez complaciente»), ADR-0011 (falla cerrada)
- **Dependencias:** #536 (T23.3) y #635 (T23.8), cerradas

### Qué se hizo y por qué
- `backend/app/platform/publication_gate/citation_judge.py` (nuevo): `resolve_judge` resuelve modelo y
  temperatura del perfil `citation_judge` con `resolve_agent_model`/`resolve_agent_temperature` y los compara con
  el modelo que resuelve `redactor`; si coinciden lanza `JudgeConfigError` y no se juzga. `judge_citation` llama al
  dispatcher `llm.call_llm` (temperatura 0, `keep_alive=0`) con la afirmación y el extracto delimitados como dato;
  `parse_verdict` solo acepta `supported|partial|unsupported` (+ justificación recortada a 300 caracteres); sin
  veredicto válido o con error del proveedor, la cita sigue `not_verified` (falla cerrada). `judge_links` solo juzga
  filas `not_verified` con fragmento y solape suficiente (AC2/AC4 siguen sin esperar al juez) y escribe
  `status`/`rationale` en `citation_links` (sin migración: las columnas ya existían), así que reevaluar no repite llamadas.
  `citation_report` da el recuento por estado y la muestra determinista (AC7).
- `citation_support.py`: `check_citation_support(..., judge_required)`; con juez, `unsupported` -> `failed`,
  `partial` -> `not_verified` + revisión humana, sin veredicto -> `judge_unavailable`. La confirmación manual rescata.
  Sin juez declarado nada cambia.
- `config.py`: `gate.citation_support.judge` (bool) y `sample_size` (0..100, por defecto 5), validados al cargar.
- `gate.py`: el resumen del criterio en el informe añade `counts`, `sample`, `sample_size` y `judge`.
- `service.py`: `evaluate_and_store` ejecuta el juez antes de evaluar (`agent_settings`/`judge_call` opcionales);
  un juez no independiente o caído no tumba la compuerta, deja las citas sin verificar.
- `projects/alejandria-magazine/agents/citation_judge.agent.md` (nuevo): temperatura 0 y modelos distintos al
  Redactor para anthropic (`claude-opus-5` vs `claude-sonnet-5`), ollama (`llama3.1:8b` vs `llama3.2:3b`) y openai (`gpt-4o` vs `gpt-4o-mini`).
  `template.yaml`: `judge: true`, `sample_size: 5` (sigue en modo aviso por `CITATION_SUPPORT_ENFORCE=false`).
- `docs/governance/publication-gate-rollout.md`: sección del juez y la muestra.
- Tests: `tests/test_citation_judge.py` (nuevo, 31) y ajuste de `tests/test_citation_map_wiring.py` (la plantilla ahora declara el juez; se simula `call_llm`).

### Definition of Done
- [x] **AC3** — el juez emite `supported|partial|unsupported` con justificación breve y su modelo es distinto del de redacción,
  verificado por configuración (test por proveedor de que los perfiles difieren; con el mismo modelo no se juzga y la compuerta no aprueba).
- [x] **AC7** — el informe de compuerta incluye el recuento por estado y una muestra para verificación humana de tamaño configurable.

### Verificación
- `cd backend && DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q tests/test_citation_judge.py tests/test_citation_map_wiring.py` -> verde.
- Suite completa (`python -m pytest -q`, 11 min) -> 1986 passed, 38 skipped, 1 failed: `test_no_tracked_databases::test_a_fresh_dev_database_is_created_and_migrated` (WinError 32 al borrar `dev.db` temporal en Windows; fallo conocido del entorno, ajeno al cambio).

### Notas
- No se tocó el frontend: la pestaña Fuentes y la vista del informe no muestran aún `counts`/`sample` (el dato ya viaja en la API del informe); queda como seguimiento de UI.
- `llama3.1:8b` debe estar descargado en Ollama; si no, el juez falla cerrado (citas `not_verified`, modo aviso).
- Los datos del manuscrito salen al proveedor activo (SPEC-037).
