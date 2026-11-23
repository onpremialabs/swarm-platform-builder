# SPEC-035: tarea T23.8 — cablear el mapa de citas

## 2026-11-23 — Éxito ✅

- **Rama:** `docs/spec-035-t23-8-cableado`
- **PR:** la de esta rama → `develop` (sin issue: edición de spec previa a implementar)
- **Origen:** al cerrar T23.1 a T23.7 se comprobó en `develop` que `save_citation_map` y
  `to_citation_inputs` (`platform/citations.py`) no tienen ningún llamador fuera de ese
  módulo: el mapa de AC1 no se guarda en ninguna ejecución. El criterio de soporte (T23.3)
  no se puede activar sin bloquear toda publicación, la pestaña Fuentes (T23.6) sale vacía
  y el juez (T23.4) no tendría datos. Ninguna tarea de SPEC-035 cubría el cableado.

### Qué se hizo y dónde

- `docs/specs/SPEC-035-citation-support-and-retractions.md`:
  - §1: hallazgo (incluye que el enlace documento/página de la pestaña no coloca al usuario:
    `DocumentsPage` no lee `doc` y `page`).
  - §3: nuevo **AC9** (mapa guardado con la huella del texto **final**, criterio declarado
    en `template.yaml` en **modo aviso**, `CITATION_SUPPORT_ENFORCE`, enlace que coloca,
    falla cerrada si no hay citas o no se pudo guardar, sin regresión si no está declarado).
  - §4: «Cableado del mapa (AC9, T23.8)». Punto delicado: si el Formateador reescribe el
    texto, la huella cambia y `current_citation_map` quedaría vacío; el guardado debe
    hacerse sobre el texto que lee la compuerta, con test.
  - §8: nueva tarea **T23.8** (sev high, depende de T23.1, T23.2, T23.3 y T23.6; acepta AC1,
    AC6 y AC9) y **T23.4 pasa a depender también de T23.8**.
- `python scripts/validate_specs.py` pasa.

### Qué NO se hizo

- **El issue de T23.8 no existe aún:** `/sdd-sync --apply` lo crea tras el merge.
- **#537 (T23.4) conserva en su cuerpo `Bloqueada por: #536`:** el sync solo compara
  títulos de tareas ya creadas, no dependencias. Hay que actualizar a mano el cuerpo de
  #537 para añadir `#<nuevo>` (T23.8) antes de lanzarla.
- No se ha comprobado en código si existe ya `CITATION_SUPPORT_ENFORCE` (la spec lo
  menciona en §7); la tarea debe verificarlo y crearlo si falta.
- No se ha verificado dónde exactamente fijar el texto final en `use_cases.py`/`service.py`;
  queda como análisis de la tarea.
