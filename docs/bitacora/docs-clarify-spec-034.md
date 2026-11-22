# Aclaración de SPEC-034 (`/speckit-clarify`)

## 2026-11-22 — Éxito ✅

- **Rama:** `docs/clarify-spec-034`
- **PR:** la de esta rama → `develop` (sin issue: paso de autoría previo a implementar E22)
- **Origen:** `/speckit-clarify SPEC-034` antes de lanzar T22.3 y el resto de E22.
  5 preguntas, todas respondidas por el mantenedor.

### Qué se hizo y dónde

- `docs/specs/SPEC-034-verified-literature-discovery-and-library.md`: sección
  `## Clarifications` (sesión 2026-11-22) con las 5 respuestas, aplicadas a los AC:
  1. **Documentos sin DOI:** sin excepción para «documento interno» (opción A). Se
     corrigió el AC5, que contradecía a ADR-0011 y a SPEC-032 (defecto introducido al
     redactar la spec el mismo día).
  2. **Candidatos sin texto completo:** descarga del PDF solo si hay URL de acceso
     abierto, por `safe_get`; si no, `text_status=abstract_only` («solo resumen»).
     Nuevo **AC11** y nueva tarea **T22.10**.
  3. **Fecha de corte:** la fecha de la búsqueda; solo se descartan candidatos con
     fecha futura (AC2). T22.2 renombrada («fecha futura»).
  4. **Abstención:** `research.min_sources` en `template.yaml`, por defecto 3,
     validado al cargar y no editable por el autor (AC7).
  5. **Bases por defecto:** OpenAlex y Crossref; el resto en `research.sources` por
     proyecto; Semantic Scholar solo con clave en el entorno (AC1).
- `python scripts/validate_specs.py` pasa.

### Qué NO se hizo

- **Los issues no están reconciliados.** T22.10 aún no existe como issue y el título
  de T22.2 (#525) sigue con el texto anterior. Hay que ejecutar `/sdd-sync --apply`
  **después de mergear esta PR**.
- No existe checklist de SPEC-034 en `docs/specs/checklists/`, así que no hubo
  revalidación de checklist.
- Quedan abiertos, con impacto bajo: reglas de unicidad por DOI dentro del proyecto,
  dos personas aceptando el mismo candidato a la vez y los estados vacío/error del
  panel de candidatos (se definen al implementar T22.8).
- Las demás specs de la serie (SPEC-033, 035 a 041) siguen sin pasar por
  `/speckit-clarify`.
