# SPEC-029: Trazabilidad auditable — vista, exportación e integridad

- **Estado:** Ready
- **Autor:** Equipo de plataforma
- **Fecha:** 2026-09-13
- **Épica:** E17 (GitHub Project)
- **ADR relacionado:** se apoya en [SPEC-014](SPEC-014-explainability-and-edd.md) (T9.1) y [SPEC-019](SPEC-019-observability.md)
- **Severidad:** 🟠

## 1. Problema

**El sustrato existe; la vista no.** `agent_run_steps` (T9.1) guarda por paso el
modelo, los parámetros, el `input_digest`, la salida, las `rag_sources` con su
score, tokens, `latency_ms`, la decisión del revisor y el `correlation_id` que
enlaza con los logs. `GET /agents/{id}/explain` (T9.2) lo sirve para **un
artículo**, y el panel «Por qué este resultado» lo pinta.

Lo que no hay:

- **Ninguna vista de trazabilidad transversal.** No existe ruta ni página: para ver
  qué ha pasado hay que entrar artículo por artículo.
- **Ningún log en tiempo real que no sea de una ejecución concreta.** El SSE de
  `/agents/{id}/stream` sirve a quien está mirando *ese* artículo.
- **Ninguna exportación.** `grep -r jsonl backend/app frontend/src` no devuelve
  nada. Hoy la traza solo se puede leer por pantalla.
- **Ninguna verificación de integridad.** `SHA-256` solo aparece en
  `capabilities/rag.py`, para identificar documentos. No hay hash de la traza, ni
  nada que detecte que una fila se modificó después de escribirse.

Y hay una confusión que la maqueta invita a cometer: llama «spans» a los pasos del
pipeline. **Spans ya existen y son otra cosa**: `platform/tracing.py` emite spans
de OpenTelemetry, que están **apagados por defecto** y se exportan a un colector
externo. La vista de trazabilidad debe leer `agent_run_steps` —que siempre está y
vive en la base— y no OTel. Construirla sobre OTel la dejaría vacía en cualquier
despliegue que no haya encendido el tracing, que son todos.

### La parte delicada: «Integridad · hashes verificados · SHA-256»

Enseñar «38 hashes íntegros» es hacer una **afirmación de auditoría**. Merece
cuidado porque es fácil construir algo que lo parezca y no lo sea:

- Un hash por fila calculado y guardado en la misma fila no detecta nada: quien
  cambie la fila recalcula el hash.
- Una **cadena** —cada paso incluye el hash del anterior— sí detecta que alguien
  editó, borró o insertó un paso, porque romper la cadena exige recalcular todo lo
  posterior.
- Y aun así, **quien tenga escritura en la base puede recalcular la cadena entera**.
  Contra eso solo protege anclar la cabeza de la cadena fuera de la base: un
  export firmado, un registro externo, o al menos una copia append-only.

Esta spec implementa la cadena y **dice en la propia interfaz qué garantiza y qué
no**. Un sello de integridad que promete más de lo que da es peor que no tenerlo:
convierte una duda sana en una confianza infundada.

## 2. Objetivos / No-objetivos

- **Objetivos:** una vista de trazabilidad del proyecto con log en vivo, trazas por
  ejecución, exportación JSONL y verificación de integridad encadenada, honesta
  sobre su alcance.
- **No-objetivos:** sustituir OpenTelemetry ni el tablero de operación; firma
  criptográfica con claves gestionadas ni notarización externa (se deja el gancho,
  no se implementa); retención distinta de la que fija
  [data-retention.md](../governance/data-retention.md); edición o borrado manual de
  trazas desde la interfaz — una traza que se puede editar desde su propia vista no
  es una traza.

## 3. Criterios de aceptación (Given/When/Then)

- [ ] **AC1** — *Given* un proyecto activo, *When* se abre la vista de
  trazabilidad, *Then* lista las ejecuciones del **proyecto** con sus pasos, estado
  y coste, leyendo `agent_run_steps` (no OpenTelemetry, que está apagado por
  defecto); un usuario no ve ejecuciones de un proyecto que no le corresponde.
- [ ] **AC2** — *Given* ejecuciones en curso, *When* se mira el log en vivo,
  *Then* muestra los eventos del proyecto activo filtrables por nivel, y **el flujo
  está acotado al proyecto**: un evento de otro proyecto no llega al cliente ni
  siquiera para ser filtrado en el navegador.
- [ ] **AC3** — *Given* una ejecución, *When* se exporta, *Then* se obtiene JSONL
  con una línea por paso, esquema documentado y versionado, y **sin volcar
  contenido que la política de retención no permita** — el `input_digest` es un
  resumen a propósito y la exportación no lo convierte en un segundo almacén del
  artículo.
- [ ] **AC4** — *Given* un paso que se escribe, *Then* se calcula su hash SHA-256
  sobre una serialización **canónica** de su contenido, encadenado al hash del paso
  anterior de la misma ejecución; el primer paso ancla en un valor conocido.
- [ ] **AC5** — *Given* una ejecución con su cadena, *When* se verifica, *Then* se
  detecta cualquier paso modificado, borrado o insertado, y el informe dice **cuál**
  y en qué posición; verificable con un test que altere una fila y otro que borre
  una del medio.
- [ ] **AC6** — *Given* la vista de integridad, *Then* dice explícitamente qué
  garantiza la cadena y **qué no** (que no protege frente a quien pueda reescribir
  la base entera), en la interfaz y no solo en la documentación.
- [ ] **AC7** — *Given* una ejecución reanudada o un artículo reejecutado, *When*
  se verifica la integridad, *Then* la cadena no da falso positivo: la agrupación
  por ejecución sigue el mismo criterio que ya usa `/explain` —`step_index` que
  vuelve a 0 abre ejecución, una reanudación no—.

## 4. Diseño propuesto

**La cadena (AC4).** Al cerrar un paso, `platform/explainability.py` —que ya es
quien recoge tokens y fuentes y cierra la fila— calcula
`sha256(canónico(paso) || hash_anterior)`. «Canónico» significa un orden de claves
y un formato de números fijados y **versionados**: si mañana cambia la
serialización, las cadenas viejas deben seguir verificándose con su versión, así que
el número de versión va en la fila. Dos columnas nuevas —`content_hash` y
`prev_hash`— y una migración.

**Por qué en el cierre del paso y no en un trabajo aparte:** el mismo argumento de
T9.1. Quien conoce el dato lo anota; un proceso posterior que recorriera la tabla
para hashearla sería un segundo sitio que puede quedarse atrás, y una cadena que se
calcula tarde no distingue «nadie lo ha tocado» de «aún no lo he mirado».

**Qué entra en el canónico, y qué no.** Entran los campos de contenido del paso.
Quedan fuera `id` y `run_id` —claves sustitutas, no contenido—, `correlation_id`
—sirve para cruzar logs y puede faltar— y `created_at`, que no sobrevive de forma
fiable al viaje de ida y vuelta por SQLite: precisión y zona horaria varían, y una
cadena que da falsos positivos por eso entrena a ignorar la alarma, que es el peor
resultado posible de un sello de integridad. La **posición** de cada paso sigue
protegida, pero por el encadenado (`prev_hash`): es lo que detecta borrados e
inserciones, y no depende de ninguna marca de tiempo. La lista de campos es
explícita y no «todas las columnas», de modo que añadir una a la tabla no invalide
en silencio las cadenas ya escritas; ampliarla obliga a subir `CANON_VERSION`.

**Las filas anteriores a T17.2 no tienen hash, y eso no es manipulación.** La
verificación las cuenta aparte, como «sin cadena». Presentarlas como íntegras sería
mentir y presentarlas como rotas, alarmismo: lo que hay es ausencia de prueba, y la
interfaz lo dice con esas palabras.

**La agrupación (AC7)** reutiliza `group_executions` de T9.2 en vez de inventar
otra: un artículo reejecutado tiene sus ejecuciones en la misma tabla y se separan
porque `step_index` vuelve a 0. Si la verificación usara otro criterio, dos
ejecuciones del mismo artículo parecerían una cadena rota.

**El log en vivo (AC2)** es el punto con más riesgo de fuga. El SSE actual es por
artículo y hereda su autorización; un flujo «del proyecto» necesita filtrar en
**servidor** por el `project_id` resuelto, nunca en cliente. Se implementa como una
suscripción por proyecto sobre los mismos eventos que ya emite el pipeline.

**La exportación (AC3)** sale del mismo modelo de respuesta que `/explain`, serializado
línea a línea. Incluye los hashes, de modo que un export es verificable fuera de la
plataforma — que es lo que hace útil la cadena aunque no haya notarización.

**Ficheros afectados:** `backend/app/models/agent_run_step.py` (dos columnas),
`backend/alembic/versions/` (migración), `backend/app/platform/explainability.py`
(cálculo y verificación), `backend/app/routers/agents.py` (export y verificación),
un flujo SSE por proyecto, y una página nueva en `frontend/src/platform/`.

## 5. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| La cadena promete más de lo que da | Confianza infundada: el peor resultado posible de un sello de integridad | AC6: el alcance se dice en la interfaz. La documentación sola no basta, porque quien lee la pestaña no lee la documentación |
| El log en vivo filtra eventos entre proyectos | Rompe T8.5 en la vista pensada para auditar | AC2: el filtro es de servidor; test que suscribe a un proyecto y comprueba que no recibe del otro |
| El export se convierte en un segundo almacén del artículo | Contradice la retención y duplica datos personales | AC3: se exporta lo que la traza guarda, `input_digest` incluido — resumen, no prompt |
| El hash en el camino caliente encarece cada paso | Pipeline más lento | Se hashea el contenido que ya está en memoria al cerrar la fila; el coste es una serialización por paso, frente a segundos de LLM |
| Reejecuciones leídas como cadena rota | Falsas alarmas que entrenan a ignorar la alarma | AC7: misma agrupación que `/explain`, con test de reejecución y de reanudación |

## 6. Plan de pruebas

AC4 y AC5 son el núcleo y se prueban por **mutación de datos**: una cadena válida,
otra con una fila alterada, otra con una fila borrada del medio y otra con una
insertada; cada caso debe señalar la posición. AC7 con una reejecución y una
reanudación sembradas. AC2 con dos suscripciones de proyectos distintos. AC3
comparando el JSONL con su esquema declarado. AC1 y AC6 por test de API y de
contenido de la vista.

## 7. Impacto operativo / observabilidad

Una migración que añade dos columnas. **Las trazas anteriores no tienen cadena**:
la verificación debe distinguir «sin cadena» de «cadena rota», que es una
diferencia que importa y un falso positivo garantizado si se olvida. La retención
no cambia; el documento de retención sí debe mencionar las columnas nuevas.

## 8. Backlog (sincronización SDD)

```yaml
# sdd-sync v1
epic:
  id: E17
  title: "Trazabilidad auditable: vista, exportación e integridad"
  area: area/observability
tasks:
  - id: T17.1
    title: "Vista de trazabilidad del proyecto sobre agent_run_steps"
    sev: high
    depends_on: []
    acceptance: [AC1]
  - id: T17.2
    title: "Cadena de hashes SHA-256 por paso, con serialización canónica versionada"
    sev: high
    depends_on: []
    acceptance: [AC4]
  - id: T17.3
    title: "Verificación de integridad que localiza el paso alterado, borrado o insertado"
    sev: high
    depends_on: [T17.2]
    acceptance: [AC5, AC7]
  - id: T17.4
    title: "Exportación JSONL con esquema versionado y respeto a la retención"
    sev: medium
    depends_on: [T17.1, T17.2]
    acceptance: [AC3]
  - id: T17.5
    title: "Log en vivo por proyecto, filtrado en servidor"
    sev: high
    depends_on: [T17.1]
    acceptance: [AC2]
  - id: T17.6
    title: "Pestaña de integridad que declara su alcance y sus límites"
    sev: medium
    depends_on: [T17.3]
    acceptance: [AC6]
```
