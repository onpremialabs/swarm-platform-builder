# ADR-0013: fuentes aportadas por el autor y verificación de DOI diferida

## 2026-11-23 — Éxito ✅

- **Rama:** `docs/adr-0013-fuentes-del-autor`
- **PR:** la de esta rama → `develop` (sin issue: decisión previa a implementar)
- **Origen:** prueba manual del 2026-11-23. El Investigador se abstuvo con 0/3 fuentes
  verificadas teniendo documentos relevantes subidos por la persona. El mantenedor pidió:
  (1) que el Investigador pueda **generar ágilmente un paper desde los borradores y PDFs que
  aporta la persona**; (2) que el DOI se compruebe **después** de generar y formatear el
  contenido; (3) que **quien lanzó el pipeline pueda publicar** su propio artículo.

### Esto cambia decisiones que estaban tomadas

- ADR-0011 descartó expresamente «excepción para documentos aportados por el autor» y fijó
  que aprueba **una persona distinta**. SPEC-034 lo confirmó en la aclaración del 2026-11-22
  (pregunta 1, opción A, que respondió el mantenedor). Aquí se revisa con una **vía intermedia**
  y queda registrado como un cambio de criterio, no como un ajuste.

### Qué se hizo y dónde

- `docs/adr/0013-author-supplied-sources-and-deferred-verification.md` (nuevo, Propuesto): dos
  clases de fuente citable (identificada / aportada por el autor, declarada por una persona); un
  DOI declarado que no resuelve **sigue bloqueando**; el DOI se comprueba en la compuerta tras el
  Formateador y no frena la generación; `min_sources` cuenta fuentes citables; severidad por
  proyecto `gate.references.author_supplied` (`block` por defecto, AlejandrIA `warn`);
  autoaprobación por proyecto `approval.allow_self_approval` con registro `self_approved`.
- `docs/adr/0011-…md`: puntero de cabecera y sección «Enmienda 2026-11-23».
  `docs/adr/README.md`: fila de ADR-0013.
- `docs/specs/SPEC-032-…md`: enmienda en la decisión de V09, AC8 matizado, nuevos **AC17**
  (clase «aportada por el autor») y **AC18** (autoaprobación por proyecto), y tareas **T20.16** y
  **T20.17**.
- `docs/specs/SPEC-034-…md`: hallazgo en el Problema, no-objetivo reformulado, pregunta 1 de la
  aclaración marcada como sustituida y sesión 2026-11-23, AC4/AC5/AC7 reescritos, nuevo **AC14**,
  nota de diseño y tarea **T22.13**.
- `python scripts/validate_specs.py` pasa.

### Qué NO se hizo

- **No hay issues:** `/sdd-sync --apply` los crea tras el merge (T20.16, T20.17, T22.13). SPEC-032 está
  `In progress` y SPEC-034 `Ready`; se comprobará que el sync las procese.
- **No se tocó código ni se verificó el estado actual** de `library_documents.verification_method`
  (enum o texto) ni qué sella la cadena de integridad: queda como comprobación previa de T22.13.
- **No se edita SPEC-035:** el soporte de cada cita se comprueba contra el fragmento, que no
  depende del DOI, así que aplica igual a las dos clases. Se citó en el ADR.
- **Los datasets EDD de T22.9** afirman «un documento interno sin verificar no se cita»: dejarán de
  ser ciertos; la actualización está en T22.13.
- **Los metadatos del manuscrito** (autor, filiación, fecha) que el mantenedor dice no ver en la
  última pantalla son de SPEC-037 (E25) y **no** forman parte de este cambio: se investigan aparte.
- **Autoaprobación:** elimina el principio de dos personas donde se active. El ADR lo recoge como
  coste; requiere que una persona revise esta decisión en la PR.
