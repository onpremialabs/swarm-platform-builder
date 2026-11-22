# Specs, épicas y tareas para el flujo de paper científico

## 2026-11-22 — Éxito ✅

- **Rama:** `docs/specs-paper-cientifico`
- **PR:** la de esta rama → `develop` (sin issue que cerrar: petición directa del mantenedor)
- **Origen:** análisis de AlejandrIA Magazine como asistente para escribir un paper
  científico (informe `docs/reports/analisis-alejandria-paper-cientifico.html`), con
  capturas de la app local, lectura del código y del repositorio PaperOrchestra
  (Google Research, arXiv 2604.05018).

### Qué se hizo y dónde

- **9 specs nuevas** en `docs/specs/` (SPEC-033 a SPEC-041), todas en estado `Ready`
  y con su bloque `sdd-sync`, y su fila en el índice de `docs/specs/README.md`:
  | Spec | Épica | Tema |
  |---|---|---|
  | SPEC-033 | E21 | Brief del paper y datos del autor |
  | SPEC-034 | E22 | Descubrimiento de literatura verificado y biblioteca |
  | SPEC-035 | E23 | Soporte de cada cita y retractaciones |
  | SPEC-036 | E24 | Revisión científica por criterios y regla de reversión |
  | SPEC-037 | E25 | Autoría, declaraciones y metadatos del manuscrito |
  | SPEC-038 | E26 | Colaboración de equipo sobre un manuscrito |
  | SPEC-039 | E27 | Exportación del manuscrito y plantilla «Paper científico» |
  | SPEC-040 | E28 | Second brain de investigación |
  | SPEC-041 | E29 | Tema claro/oscuro e idioma de la interfaz (es/en) |
- **Informe de análisis** (`docs/reports/analisis-alejandria-paper-cientifico.html`):
  HTML autocontenido con las capturas incrustadas.
- **Backlog sembrado con `/sdd-sync --apply`** en el Project «Roadmap: calidad,
  evaluación y vistas agénticas»: 9 épicas (#515, #523, #533, #541, #549, #559,
  #567, #575, #583) y 75 tareas (#516–#522, #524–#532, #534–#540, #542–#548,
  #550–#558, #560–#566, #568–#574, #576–#582, #584–#598). Cada épica lleva en su
  cuerpo la relación con la épica cerrada de la que continúa (#432, #246, #351, #191).
- `python scripts/validate_specs.py` pasa.

### Qué NO se hizo / decisiones abiertas

- **Las specs pasaron a `Ready` por instrucción del mantenedor, sin
  `/speckit-clarify` ni `/speckit-checklist`** (recomendados por la DoR, no
  bloqueantes). Cada spec lo declara en su cabecera.
- **El campo `Epic` del Project no tiene las opciones E21–E29.** Añadir una opción
  regenera las demás y borra los valores ya puestos, así que no se creó; hay que
  hacerlo a mano en la UI y asignar el campo a los 84 issues.
- **Los issues enlazan a las specs en `develop`**, que no existían hasta esta PR:
  los enlaces dan 404 hasta el merge.
- **No hay código de producto en esta PR.** Las specs describen trabajo futuro; el
  informe es un análisis, no una verificación de comportamiento: no se ejecutó un
  pipeline nuevo y los datos de las capturas son de prueba (modelo local de 4B).
- Las filas de SPEC-026 a SPEC-032 siguen sin aparecer en el índice de specs (ya
  faltaban antes); queda fuera de esta PR.
- Pendiente de decidir entre épicas cerradas e épicas nuevas: se mantuvieron
  abiertas (ver el cuerpo de cada épica).
