# Tarea #649 — T22.16 Reindexado idempotente de la biblioteca existente con modo de simulación y aislamiento por proyecto

## 2026-11-24 14:55 — Completada

- **Rama:** `feat/649-reindexado-biblioteca`
- **PR:** ver PR de la rama -> `develop` (`Closes #649`)
- **Spec/ADR:** SPEC-034 (AC17, «Evidencia sustantiva»); SPEC-035 (mapas de citas, no tocados)
- **Dependencias:** #647 (cerrada, PR #651)

### Dónde estaba el problema
T22.14 etiqueta `section` al indexar y excluye `references` de la búsqueda con `must_not`, pero
los puntos indexados antes no llevan `section` y siguen recuperándose, listas bibliográficas
incluidas.

### Qué se hizo y por qué
- `backend/app/platform/capabilities/reindex.py` (nuevo): reclasifica **solo el campo `section`**
  del payload (Qdrant: `POST /points/payload`; respaldo local: JSON). No crea, borra ni
  re-embebe puntos, así que no hay duplicados ni pérdidas, y `doc_id`, DOI, título y texto
  quedan intactos. No importa la BD: curación y `agent_runs` (mapas de citas SPEC-035) no se
  tocan.
  - Reconstruye cada documento por `chunk_index`, quita el solape que `chunk_text` antepone (tapa
    los encabezados) y aplica el mismo `split_sections` de T22.14 (reutilizado). Un fragmento es
    `references` solo si cae entero en un tramo de referencias; si cruza hacia contenido se queda
    con la sección del contenido.
  - Si el troceado antiguo perdió el encabezado (párrafos largos partidos por palabras), solo se
    marca como referencias una **cola final de >=3 fragmentos consecutivos** con aspecto
    bibliográfico (`parece_bibliografia`); un fragmento aislado con muchas fechas no basta.
  - Idempotente: solo se escriben fragmentos sin `section`; no pisa etiquetas existentes.
  - Aislamiento: las colecciones se enumeran con `ProjectContext.owns_collection`; el nombre no se
    compone a mano y las heredadas/otros proyectos no se tocan. No se crean colecciones
    (no aplica `embed_vector_size()`).
- `scripts/reindex_library.py` (nuevo): CLI al estilo de `migrate_rag_namespaces.py`; simulacro
  por defecto, `--apply` escribe, `--project <uuid>` limita a un proyecto.
- `backend/tests/test_reindex_library.py` (nuevo, 10 tests) y README (sección RAG).

### Definition of Done
- [x] Fragmentos previos reclasificados por `section` y referencias excluidas sin duplicar ni
  perder contenido, ni alterar doc_id/DOI/curación — tests de claves de punto y payload idénticos
  salvo `section`; test estructural (sin upsert/delete, sin BD).
- [x] Idempotente — segunda pasada: 0 escrituras y estado idéntico.
- [x] Modo de simulación sin escribir — `test_simulacro_no_escribe` (y respaldo local).
- [x] Aislamiento por proyecto vía `project_context` — otro proyecto y colección heredada intactos.
- [x] Mapas de citas de ejecuciones guardadas no se reescriben — el módulo no toca la BD.

### Verificación
- `cd backend && DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest tests/test_reindex_library.py -q` -> 10 passed.
- Suite completa: `python -m pytest -q` -> 2023 passed, 38 skipped, 1 failed (`test_no_tracked_databases`, WinError 32, fallo conocido de Windows ajeno a la tarea).

### Fuera de alcance / notas
- No se probó contra un Qdrant real (cliente HTTP simulado en memoria con la misma API).
- Limitación: un documento sin encabezado conservado y con bibliografía de menos de 3 fragmentos
  seguidos queda `other` (conservador, nunca esconde contenido).
- AC16 (T22.15) y AC18 son tareas aparte.
