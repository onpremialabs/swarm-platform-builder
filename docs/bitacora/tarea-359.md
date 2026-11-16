# Tarea #359 — T17.2: Cadena de hashes SHA-256 por paso

## 2026-11-05 — Completada ✅

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **Spec:** SPEC-029 · Épica E17 · AC4

### Qué se hizo y dónde

- `backend/app/platform/explainability.py` — `canonical_form()`, `compute_hash()`
  y las constantes `CANON_VERSION` y `ANCLA_GENESIS`.
- `backend/app/models/agent_run_step.py` — tres columnas: `content_hash`,
  `prev_hash` y `hash_version`.
- `backend/alembic/versions/0007_integrity_chain.py` — la migración, generada con
  `--autogenerate` y revisada: solo esas tres columnas, anulables, con su
  `downgrade`. No toca el ciclo de FKs `users` ↔ `projects`.
- `backend/app/modules/agents/application/use_cases.py` — `log_run_step` sella la
  cadena al escribir el paso.

### Dónde se calcula, y por qué ahí

En `log_run_step`, que es el **único** punto por el que se escribe una fila de
`agent_run_steps`. Es el mismo argumento de T9.1: quien conoce el dato lo anota.
Un proceso posterior que recorriera la tabla para hashearla sería un segundo sitio
que puede quedarse atrás, y una cadena calculada tarde no distingue «nadie lo ha
tocado» de «aún no lo he mirado».

El anterior se busca con la misma regla que `group_executions`: `step_index == 0`
abre ejecución y por tanto ancla; cualquier otro enlaza con el último paso escrito
del artículo. Una reanudación no reinicia el índice, así que continúa la cadena —
que es lo que AC7 necesita para no dar falso positivo.

### Qué entra en el hash

Los campos de contenido, en una lista **explícita**: así añadir una columna a la
tabla no cambia el formato sin que nadie lo decida. Ampliarla obliga a subir
`CANON_VERSION`, que viaja en la fila para que un cambio futuro no convierta la
traza vieja en «manipulada».

Quedan fuera `id` y `run_id` (claves sustitutas), `correlation_id` (puede faltar)
y **`created_at`**. Esta última es una decisión con coste: no sobrevive de forma
fiable al viaje de ida y vuelta por SQLite —precisión y zona horaria varían— y una
cadena que da falsos positivos por eso entrena a ignorar la alarma, que es el peor
resultado posible de un sello de integridad. La posición de cada paso sigue
protegida por el encadenado, que es lo que detecta borrados e inserciones y no
depende de ninguna marca de tiempo. Queda escrito en la spec y se declara en la
pestaña de integridad (T17.6).

El hash anterior entra **dentro** del digest y no al lado: así cada eslabón depende
de todos los previos y un paso no se puede recolocar sin que el resto deje de cuadrar.

### Tests

`tests/test_integrity_chain.py` — el canónico no depende del orden de las claves ni
de si el paso viene como `dict` o como fila del ORM (escribir y verificar usan el
mismo código, porque dos implementaciones que «deberían coincidir» acaban no
coincidiendo); el primero ancla; cambiar un campo cambia el hash; el mismo paso en
distinta posición da distinto hash. Y en integración: `log_run_step` sella de
verdad, y los tres pasos quedan encadenados.

### Definition of Done

- [x] AC4: `sha256(canónico || anterior)` por paso, anclado el primero.
- [x] Serialización canónica versionada, con la versión en la fila.
- [x] Migración revisada; `test_migrations` en verde.
- [x] Se calcula al cerrar el paso, en el único punto de escritura.
