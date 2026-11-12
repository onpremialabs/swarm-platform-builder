# Tarea #364 — T18.1: Alcance de documento por ejecución

## 2026-11-05 — Completada ✅

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **Spec:** SPEC-030 · Épica E18 · AC1

### El problema

Toda subida iba al bucket del agente o a `__library__`, que leen **todos** los
agentes del proyecto. Subir ahí la plantilla de estilo de un paper concreto hace
que los siguientes recuperen ese estilo. Nadie lo ve hasta que los papers empiezan
a parecerse entre sí sin que nadie lo haya pedido: contaminación silenciosa.

### Qué se hizo y dónde

`backend/app/platform/capabilities/rag.py`:

- `upsert_chunks` acepta `article_id` y lo guarda en el payload de cada fragmento,
  en las dos rutas —Qdrant y almacén local—.
- `_article_scope_clause` / `_article_scope_matches`: un documento **sin**
  `article_id` es compartido y se ve siempre; uno acotado solo se recupera desde
  su propio paper.
- `_merge_filter` compone el filtro de agente con el de alcance.

No es un espacio nuevo sino un **filtro dentro del espacio del proyecto**: el
nombre de la colección se sigue derivando en `project_context.py` y esto no abre
ninguna vía para componerlo a mano.

### El detalle que lo haría inútil

En Qdrant un `should` junto a un `must` **no es obligatorio** salvo que se exija un
mínimo. Dejarlo al lado habría puesto el filtro sin que filtrara nada: la
referencia de un paper seguiría apareciendo en los demás, con el código escrito y
la impresión de estar resuelto. Por eso `_merge_filter` lo anida dentro del `must`,
y hay un test que comprueba justo eso.

### Retrocompatible por construcción

Lo indexado antes de T18.1 no lleva el campo, así que es compartido y sigue
visible. La biblioteca no se toca.

### Tests

`tests/test_reference_scope.py`, 11 casos, incluido el del plan de pruebas de la
spec: dos papers en un proyecto, y el B no recupera la referencia del A. También
que elegir el documento de otro paper por `doc_id` a mano tampoco se salta el
acotamiento — ese camino evita el filtro de bucket a propósito y habría sido la
puerta de atrás evidente.

### Definition of Done

- [x] AC1: la referencia queda acotada a su paper y no aparece en otros.
- [x] Verificado con dos papers en el mismo proyecto.
- [x] Las dos rutas de recuperación, Qdrant y local.
- [x] La colección se sigue derivando; no se compone a mano.
