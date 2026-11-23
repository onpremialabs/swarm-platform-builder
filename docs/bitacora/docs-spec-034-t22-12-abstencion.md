# SPEC-034: tarea T22.12 — la abstención se muestra como detenida, no completada

## 2026-11-23 — Éxito ✅

- **Rama:** `docs/spec-034-t22-12-abstencion-estado`
- **PR:** la de esta rama → `develop` (sin issue: edición de spec previa a implementar)
- **Origen:** prueba manual de T22.5. Con 0 fuentes verificadas el Investigador se abstuvo
  (correcto, AC7), pero la pantalla de ejecución mostró «Pipeline completado», la insignia
  COMPLETADO y «Ver artículo» activo, con los otros cuatro agentes en «PENDIENTE».

### Qué se hizo y dónde

- `docs/specs/SPEC-034-verified-literature-discovery-and-library.md`:
  - §1: hallazgo (el paso se registra `completed` en `use_cases.py`, se emite `done` y la
    pantalla no distingue «terminó» de «se detuvo por abstención»).
  - §3: nuevo **AC13** (estado propio, aviso destacado `k/N`, pasos «No ejecutado», sin
    «Ver artículo», artículo en borrador, sin regresión en ejecuciones completas).
  - §4: «Estado de la abstención (AC13, T22.12)» con dos comprobaciones previas: si
    `agent_runs`/`agent_run_steps` usan enum nativo (migración Alembic, nunca SQL a mano) y
    si el estado entra en el canon de integridad (`CANON_VERSION`).
  - §8: nueva tarea **T22.12** (sev high, depende de T22.5, acepta AC7 y AC13).

### Qué NO se hizo

- **El issue no existe aún.** Tras mergear, `/sdd-sync --apply` lo crea (solo procesa specs
  que no estén en Draft).
- No se ha comprobado en código si el estado de las ejecuciones es un enum nativo ni si
  entra en el canon de integridad: se deja como comprobación previa de la tarea.
- No se ha verificado cómo queda el artículo en BD tras la abstención; el log del frontend
  dice «sigue en borrador» y AC13 lo exige, pero no se ha leído la base.
