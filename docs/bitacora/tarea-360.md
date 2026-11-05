# Tarea #360 — T17.3: Verificación que localiza el paso alterado, borrado o insertado

## 2026-11-05 — Completada ✅

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **Spec:** SPEC-029 · Épica E17 · AC5, AC7

### Qué se hizo y dónde

- `backend/app/platform/explainability.py` — `verify_chain()`.
- `backend/app/routers/agents.py` — `GET /api/v1/agents/{id}/integrity`.

### El informe dice cuál, no solo que algo falla

`verify_chain` recorre los pasos de **una** ejecución y distingue dos problemas:

- `contenido_alterado` — el paso no produce el hash que tiene guardado.
- `enlace_roto` — su `prev_hash` no es el hash del paso anterior: falta uno por
  medio, se insertó, o se reordenaron.

Cada hallazgo lleva posición, `step_index` y agente. Un informe que solo dijera «la
cadena está rota» obligaría a revisar la ejecución entera a mano, que es tanto como
no decir nada.

### Falta de prueba no es prueba de manipulación

Las filas anteriores a T17.2 no tienen hash. Se cuentan aparte, como `unchained`.
Presentarlas como íntegras sería mentir; presentarlas como rotas, alarmismo. Lo que
hay es ausencia de prueba, y tanto la respuesta como la interfaz lo dicen con esas
palabras.

### AC7: cada ejecución se verifica por separado

El endpoint agrupa con `group_executions` antes de verificar. Un artículo
reejecutado tiene varias cadenas en la misma tabla, y verificarlas juntas las
leería como una sola rota: falsas alarmas que entrenan a ignorar la alarma, que es
el riesgo que la spec señala. Una reanudación no reinicia `step_index`, así que
continúa su cadena y tampoco produce falso positivo.

### De camino: el control de acceso, una vez

`/explain`, `/integrity` y `/export.jsonl` necesitan la misma comprobación
—artículo existe, es de quien pregunta, y si viene `X-Project-Id` es de ese
proyecto—. Se extrajo a `_articulo_y_pasos()`. Tenerla escrita una vez y no tres es
lo que evita que una copia se quede sin la comprobación de proyecto cuando alguien
toque otra.

### Tests

Los dos que pide el AC explícitamente —alterar una fila y borrar una del medio—
más inserción, cadena intacta, pasos sin hash, reejecución y reanudación. Y en
integración contra la base real: editar `output_text` de un paso directamente en la
tabla hace que el endpoint devuelva `intact: false` señalando al redactor.

### Tres estados, no dos — corregido al probar con datos reales

La primera versión devolvía `intact: true|false`. Contra la base de desarrollo,
cuyos 65 pasos son todos anteriores a T17.2, el informe salía `intact: false` y la
pestaña lo pintaba como **«cadena rota»**.

No había nada roto: no había nada que comprobar. Era exactamente el alarmismo que
esta tarea dice evitar, y de los que entrenan a ignorar la alarma cuando alguna vez
sea de verdad. El fallo no lo cazó ningún test porque el que cubría pasos sin hash
usaba una ejecución **mixta** —dos encadenados y uno sin— y ahí sí quedaba algo
verificado.

`verify_chain` devuelve ahora `status`: `intacta`, `rota` o `sin_cadena`. El
endpoint agrega con el mismo criterio —«rota» manda; si no hay ni una cadena que
comprobar se dice eso— y la interfaz pinta los tres distintos: escudo verde, escudo
de aviso, o icono informativo con el texto de que no hay con qué comprobarlo.

`intact` se mantiene y vale solo para `intacta`: una ejecución sin cadena tampoco
puede afirmarse íntegra.

Dos tests nuevos: una ejecución entera sin cadena no es una cadena rota, y los tres
estados se distinguen.

### Definition of Done

- [x] AC5: detecta modificado, borrado e insertado, y dice cuál y en qué posición.
- [x] AC5: test que altera una fila y test que borra una del medio.
- [x] AC7: reejecución y reanudación no dan falso positivo.
- [x] El endpoint hereda el control de acceso de `/explain`.
- [x] «Sin cadena» no se presenta como «rota».
