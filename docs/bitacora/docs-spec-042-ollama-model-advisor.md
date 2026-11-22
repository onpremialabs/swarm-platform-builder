# SPEC-042: recomendación de modelos Ollama por agente según hardware

## 2026-11-22 — Éxito ✅

- **Rama:** `docs/spec-042-ollama-model-advisor`
- **PR:** la de esta rama → `develop` (sin issue: petición directa del mantenedor)
- **Origen:** el mantenedor pidió que el sistema elija, entre los modelos Ollama
  instalados, los mejores para cada agente según la VRAM y la RAM disponibles.

### Qué se hizo y dónde

- `docs/specs/SPEC-042-ollama-model-advisor.md` (nueva, estado **Draft**): 12 AC,
  épica E30 y 7 tareas (T30.1–T30.7) en el bloque `sdd-sync`. Pasó por
  `/speckit-clarify` (5 preguntas) y `/speckit-analyze` (9 hallazgos, todos aplicados):
  - El perfil de rol (`model_profile`) vive en el `.agent.md` y es opcional.
  - El hardware solo se mide si Ollama está en `localhost`/`127.0.0.1`; si no, «sin
    datos» o capacidad declarada (`OLLAMA_VRAM_GB`, `OLLAMA_RAM_GB`).
  - Estimador de encaje con constantes conservadoras (`k = 1.2`, margen por `num_ctx`).
  - Aceptar una sugerencia escribe `AgentProfileModel.model` del proyecto activo, con
    confirmación. El origen va en `params` del paso y en la auditoría, sin migración.
- `docs/specs/README.md`: fila de SPEC-042 en el índice.
- `python scripts/validate_specs.py` pasa.

### Qué NO se hizo

- **La spec sigue en Draft:** `/sdd-sync` no la sembrará en el Project hasta que pase a
  `Ready`. Cuando lo haga, ejecutar `/sdd-sync --apply`.
- **El campo `Epic` del Project no tiene la opción E30** (igual que E21–E29): hay que
  crearla a mano en la UI.
- No hay checklist de SPEC-042 en `docs/specs/checklists/`.
- No hay código de producto en esta PR. La estimación de VRAM/RAM, la detección de GPU y el
  comportamiento con Ollama real quedan sin probar hasta implementar.
- Abierto con impacto bajo: la regla de desempate entre modelos de tamaño parecido y los
  estados vacío/error de la pantalla (se definen al implementar T30.6).
- El origen de la elección es una etiqueta de procedencia, no una prueba: si se fija a mano
  el mismo modelo tras aceptar, se sigue etiquetando como aceptado. Mostrarlo sin consultar
  la auditoría exigiría una columna y su migración (descartado por ahora).
