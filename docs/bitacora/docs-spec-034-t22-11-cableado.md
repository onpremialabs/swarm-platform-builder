# SPEC-034: tarea T22.11 para cablear la búsqueda de literatura

## 2026-11-22 — Éxito ✅

- **Rama:** `docs/spec-034-t22-11-cableado-busqueda`
- **PR:** la de esta rama → `develop` (sin issue: hallazgo de T22.10, petición del mantenedor)
- **Origen:** al resolver T22.10 (#606) se comprobó que `run_literature_search` y
  `add_candidate_to_library` solo los llaman los tests: ningún endpoint, nodo ni pantalla
  los invoca. El panel de candidatos (T22.8) queda vacío y AC1/AC3 no se pueden ejercer
  de punta a punta.

### Qué se hizo y dónde

- `docs/specs/SPEC-034-verified-literature-discovery-and-library.md`:
  - Apartado 1: el hallazgo, y que `LITERATURE_DISCOVERY_ENABLED` (apartado 7) no existe.
  - Nuevo **AC12**: la persona autora lanza la búsqueda; los verificados nuevos entran como
    `candidate`; los no verificados y los DOI ya presentes no se crean; el estado por base
    se informa; con el flag apagado no hay red.
  - Apartado 4: el cableado es un endpoint `POST /agents/rag/library/search` más un
    formulario en el panel, disparado por la persona autora y no por el Investigador.
  - Nueva tarea **T22.11** (sev alta) en el bloque `sdd-sync`. **T22.9** pasa a depender de
    ella, porque medir la cobertura sin búsqueda conectada mediría un flujo inalcanzable.
- `python scripts/validate_specs.py` pasa.

### Qué NO se hizo

- **Los issues no están reconciliados.** T22.11 aún no existe como issue y #532 (T22.9) no
  refleja su nueva dependencia. Hay que ejecutar `/sdd-sync --apply` **después de mergear
  esta PR**.
- **Decisión de diseño no consultada:** que lo dispare la persona autora y no el
  Investigador lo propuso el asistente; queda a revisión en la PR.
- No hay código de producto en esta PR.
