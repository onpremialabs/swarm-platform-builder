# Tarea #355 — T16.4: Estado del enjambre derivado de los pasos abiertos

## 2026-11-05 — Completada ✅

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **Spec:** SPEC-028 · Épica E16 · AC4

### Qué se hizo y dónde

`backend/app/platform/summary.py` — nueva `project_swarm_state()`. Devuelve cada
agente del proyecto con su estado, el momento desde el que lo está y **el criterio
que lo decide**, escrito en la propia respuesta.

`MetricsDashboardPage.jsx` — sección «Estado del enjambre»: una tarjeta por agente,
con punto pulsante solo cuando de verdad ejecuta y el criterio en el `title`.

### El dato no está donde decía la spec

SPEC-028 §4 dice que «un paso abierto es una fila en `agent_run_steps` sin cerrar».
No lo es: el orquestador escribe esa traza **al cerrar** el nodo —lo dice la propia
docstring del modelo—, así que mientras un agente trabaja todavía no tiene fila
ahí. Derivarlo de esa tabla habría dado «ninguno ejecutando» siempre, que es justo
el momento que AC4 quiere ver.

El hecho vivo está en `agent_runs`: `log_run_start` abre la fila con
`status='running'` y `log_run_end` la cierra. Un paso abierto es una fila que nadie
cerró. El principio de la spec —derivar, no almacenar— se respeta igual; lo que
cambia es de qué tabla.

`agent_runs` no lleva `project_id`, así que se acota por `articles.project_id`.
**No** sirve cruzarlo por `agent_run_steps` como hacía la consulta anterior: un run
recién abierto aún no tiene paso en la traza, que es precisamente el que hay que ver.

### Los cuatro estados

| Estado | Criterio |
|---|---|
| `ejecutando` | Paso abierto empezado hace menos de 15 min |
| `incierto` | Paso abierto desde hace más de 15 min |
| `disponible` | Tiene perfil y ningún paso abierto |
| `no_configurado` | Sale en la traza pero ya no tiene perfil |

**El umbral es el punto de la tarea, no un detalle.** Un proceso que muere deja su
fila en `running` para siempre; sin umbral la portada afirmaría que el agente
trabaja justo cuando no lo hace. Pasado `SWARM_STALE_AFTER_S` (900 s) el estado
pasa a `incierto`, que es lo que de verdad se sabe: ni se afirma que ejecuta ni se
afirma que esté libre.

Son 15 min y no los 60 s de `LATENCY_BUDGET_MS` a propósito: pasarse del
presupuesto de latencia es una anomalía (AC3), no indicio de que el proceso murió.
Un paso lento sigue siendo un paso vivo.

`no_configurado` existe para no esconder un descuadre: un agente que ejecutó y
luego perdió su perfil —borrado o renombrado— sigue siendo parte de lo que el
proyecto hizo. Callarlo dejaría tokens y latencia sin dueño en la portada.

Los criterios viajan en la respuesta (`swarm.criteria` y `criterion` por agente),
no solo en el código: AC4 pide que estén escritos, y uno que viva únicamente en el
backend se desincroniza del rótulo que lee quien mira la portada.

### Tests

- `test_estado_del_enjambre_distingue_ejecutando_de_colgado`: dos pasos abiertos,
  uno de hace 30 s y otro de hace más del umbral. El primero sale `ejecutando`, el
  segundo `incierto`. Si alguien quita el umbral, el test falla.
- `test_agente_sin_perfil_aparece_como_no_configurado`: un agente con traza y sin
  perfil no desaparece de la portada.

### Definition of Done

- [x] AC4: cada agente con estado derivado de hechos, no de un registro aparte.
- [x] El criterio de cada estado está escrito, y viaja en la respuesta.
- [x] Un paso colgado deja de mostrarse como «ejecutando» pasado el umbral.
- [x] Aislamiento por proyecto: se acota por `articles.project_id`.
