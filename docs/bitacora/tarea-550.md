# Tarea #550 — T25.1 Autor, filiación y fecha inyectados por el sistema y descarte de lo escrito por el LLM

## 2026-11-22 — Completada ✅

- **Rama:** `feat/550-metadatos-del-sistema`
- **PR:** ver PR de la rama → `develop` (`Closes #550`)
- **Spec/ADR:** SPEC-037 §1, §4 (AC1); relacionado SPEC-032 / ADR-0011
- **Dependencias:** ninguna

### Dónde estaba el problema
El texto que sale del Formateador (`state["formatted_text"]`) conservaba el encabezado
que inventa el LLM («Autor: [Su Nombre/Autoría]», «Fecha: Octubre 2023 (Borrador)»), y
el Publicador (`adapters/publicador.py::run_publicador`) lo guardaba tal cual en
`article.body`. La maquetación (`paper_layout.build_paper_html`) ya pintaba los autores
de `article.authors`, pero no tenía fecha, así que el texto del modelo era la única fecha.

### Qué se hizo y por qué
- `backend/app/platform/manuscript_metadata.py` (nuevo): `strip_llm_metadata` descarta
  del **encabezado** (antes del primer `##`, máx. 30 líneas) las líneas «Autor/Autores/
  Author, Afiliación/Affiliation, Institución, Fecha/Date, Correo/Email: ...» (con
  decoración Markdown); el cuerpo científico no se toca. `system_authors` (solo autores
  registrados con nombre; nunca inventa uno) y `system_date` (fecha de creación ISO).
- `adapters/publicador.py`: aplica el descarte antes de persistir y evaluar la compuerta
  (punto más estrecho: el Formateador sigue sin alterar el contenido y el motor no
  menciona agentes), pasa `system_authors(article.authors)` y `date=system_date(created_at)`.
- `adapters/paper_layout.py`: parámetro opcional `date`; sin él la salida es idéntica.
- `routers/articles.py`: la maquetación de respaldo (`paper_html` vacío) también inyecta la fecha.
- Sin migraciones ni cambios de esquema; sin tocar prompts ni perfiles de agente.

### Definition of Done
- [x] **AC1** — con autores registrados, el `paper_html` lleva autor/filiación de la base
  y la fecha de creación; lo escrito por el LLM se descarta de `body` y `paper_html`
  (`test_publicador_inyecta_autor_y_fecha_del_sistema`). Artículo sin autores: no se
  inventa ninguno (`test_articulo_sin_autores_no_inventa_ninguno`).

### Verificación
- `DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest -q tests/test_manuscript_metadata.py` → 5 passed.
- Suite completa (backend/) → 1482 passed, 38 skipped, 2 failed: uno era mi test (corregido, 5 passed
  ahora); el otro, `test_no_tracked_databases.py::test_a_fresh_dev_database_is_created_and_migrated`
  (`PermissionError` WinError 32 al borrar `dev.db` temporal en Windows), **falla igual sin mis cambios**.
- No se reejecutó la suite completa tras corregir el test propio; sí los 5 tests del archivo.
- EDD: no se tocan agentes ni prompts, no aplica el gate de evaluación; el comportamiento que podría
  romperse (Publicador) lo cubre `test_publicador_compuerta.py` (verde).

### Fuera de alcance / notas
- Riesgo: una línea legítima del encabezado que empiece por «Fecha:»/«Autor:» se descarta; es el comportamiento buscado.
- AC2–AC9 (regex en la compuerta, declaración de IA, CRediT, etc.) pertenecen a T25.2+.
- El texto de `body` ya no incluye autor/fecha; el lector los ve en el bloque de título de `paper_html`.
