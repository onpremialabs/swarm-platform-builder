# SPEC-028: Portada de plataforma — métricas del proyecto y estado del enjambre

- **Estado:** Ready
- **Autor:** Equipo de plataforma
- **Fecha:** 2026-09-13
- **Épica:** E16 (GitHub Project)
- **ADR relacionado:** complementa [ADR-0004](../adr/0004-observability-and-ci.md)
- **Severidad:** 🟠

## 1. Problema

**La portada no existe.** `frontend/src/App.jsx:162` hace
`<Route index element={<Navigate to="articles" replace />} />`: entrar en
`/dashboard` te deja en el listado de artículos. No hay ningún sitio donde ver de
un vistazo qué está haciendo la plataforma.

Lo que sí hay, y **no sirve para esto**:

- `GET /metrics` (`backend/app/routers/health.py:112`) devuelve formato Prometheus,
  **sin autenticación y sin proyecto**, porque su consumidor es el recolector. No
  se puede colgar de ella una vista de producto.
- `agent_runs` y `agent_run_steps` tienen los datos —`status`, `latency_ms`,
  `tokens_in/out`, `iteration`, `rag_sources`— pero nadie los agrega.
- **El estado del enjambre no existe como dato.** No hay registro de qué agente
  está ejecutándose ahora; el pipeline lo emite por SSE a quien mire *una*
  ejecución concreta (`/agents/{id}/stream`), y ahí se pierde.

Y hay dos trampas en la maqueta que conviene resolver **antes** de implementarla,
no después:

1. **«MÉTRICAS GLOBALES» en una plataforma multi-tenant.** El aislamiento por
   proyecto (T8.5) es una propiedad que costó construir: la colección de Qdrant se
   deriva, no se recibe, y `project_access.py` autoriza cada petición. Una portada
   que cuente «38 papers generados» sin filtrar por proyecto **filtra información
   entre proyectos** por la puerta de atrás — y lo hace con aspecto de resumen
   inocente.
2. **«Anomalías detectadas: 0» sin definir qué es una anomalía.** Un contador que
   siempre marca cero no informa: tranquiliza. Es peor que no tenerlo, porque
   parece que algo está vigilando.

Y una tercera menor pero que envejece mal: «Latencia promedio 1.2s». Un paso de
agente tarda entre segundos y minutos; 1,2 s solo puede ser latencia HTTP. Si la
tarjeta no dice de qué, cada persona leerá una cosa distinta.

## 2. Objetivos / No-objetivos

- **Objetivos:** una portada por proyecto con magnitudes **definidas**; un estado
  del enjambre derivado de las ejecuciones en curso; anomalías definidas sobre la
  traza que ya existe; y aislamiento por proyecto demostrado con test.
- **No-objetivos:** sustituir `/metrics` ni el tablero de Prometheus/Grafana —la
  portada es producto, no operación; métricas entre proyectos para administración
  (sería otra vista, con su autorización); alertado o notificación por anomalía
  (esta spec las **cuenta y enseña**, no las envía).

## 3. Criterios de aceptación (Given/When/Then)

- [ ] **AC1** — *Given* una sesión con proyecto activo, *When* se pide
  `GET /api/v1/dashboard/summary` con `X-Project-Id`, *Then* devuelve las magnitudes de la
  portada **solo de ese proyecto**, autenticado y resuelto por
  `get_project_context`; no reutiliza `/metrics`, que es anónima y sin proyecto.
- [ ] **AC2** — *Given* cada tarjeta de la portada, *Then* su magnitud está
  **definida y documentada**: qué cuenta, sobre qué ventana temporal y de qué tabla
  sale; en particular la latencia dice **de qué** es (paso de agente, no petición
  HTTP) y con qué estadístico.
- [ ] **AC3** — *Given* la traza de T9.1, *Then* «anomalía» está definida como un
  conjunto **enumerado y verificable** de condiciones sobre `agent_run_steps`
  —al menos: paso con `status` de fallo, bucle de revisión agotado
  (`iteration` en el máximo), latencia por encima del presupuesto declarado, y
  paso con RAG que no recuperó nada—, cada una con su cuenta propia; *When* no hay
  ninguna, *Then* el cero significa «se han comprobado estas condiciones», no
  «no se comprueba nada».
- [ ] **AC4** — *Given* ejecuciones en curso, *When* se consulta el estado del
  enjambre, *Then* cada agente del proyecto aparece con un estado derivado de
  hechos —ejecutando un paso ahora / disponible / no configurado— y el criterio de
  cada uno está escrito; un agente que lleva más de un umbral sin cerrar paso no
  se muestra como «ejecutando» indefinidamente.
- [ ] **AC5** — *Given* la lista de papers recientes, *Then* cada uno muestra su
  estado real del pipeline y su coste en tokens tomados de `agent_runs`, no un
  estado de artículo que pueda haber quedado desfasado.
- [ ] **AC6** — *Given* dos proyectos con datos, *When* se pide la portada de uno,
  *Then* ninguna magnitud incluye datos del otro; verificable con un test que cree
  ejecuciones en ambos y compare.
- [ ] **AC7** — *Given* una fuente de datos caída (base, Qdrant), *When* se carga
  la portada, *Then* las tarjetas que dependen de ella se muestran como
  indisponibles y el resto funciona; la portada **no** se queda en blanco ni
  bloquea la navegación.

## 4. Diseño propuesto

**Un endpoint, no cuatro.** `GET /api/v1/dashboard/summary` compone la respuesta en una
consulta por magnitud y la sirve junta: la portada hace una petición y no seis en
cascada. Depende de `get_project_context` —igual que el resto de rutas que leen
datos del proyecto— y por tanto hereda la autorización de `project_access.py`.

**El prefijo `/api/v1` no es decorativo.** El router nació con `prefix="/dashboard"`,
el único del backend fuera de `/api/v1`, y `vite.config.js` solo reenvía `/api`: en
desarrollo la petición la atendía el propio Vite, que para una ruta desconocida
devuelve `index.html`. El cliente recibía **200 con HTML**, `summary` pasaba a ser
un string y cada `summary?.campo ?? 0` caía al cero, así que la portada enseñaba
ceros sin un solo error. Un endpoint nuevo va bajo `/api/v1` o no llega.

**Las anomalías salen de lo que ya se registra (AC3).** `agent_run_steps` guarda
`status`, `error_message`, `iteration`, `latency_ms`, `tokens_in/out` y
`rag_sources` con su score. Las cuatro condiciones del AC3 se calculan sobre esas
columnas sin añadir ni una tabla. La ventaja de enumerarlas es doble: el número
deja de ser opaco y la tarjeta puede **desglosarlo** — «0 de 4 comprobaciones» dice
mucho más que «0».

**El estado del enjambre se deriva, no se almacena (AC4).** Un registro de estado
vivo sería un segundo sitio donde la verdad puede quedar desincronizada —y este
repo ya ha pagado eso—. Un paso abierto es una fila en `agent_run_steps` sin cerrar;
eso basta. El umbral del AC4 existe porque un proceso que muere deja el paso
abierto para siempre, y sin él la portada mentiría en el caso justo en que más
importa.

**Presupuestos declarados, no incrustados.** El umbral de latencia del AC3 vive en
configuración junto a los demás, no dentro de la consulta: es el mismo patrón que
`thresholds.yaml` en evaluación y `budgets.yaml` en carga (SPEC-026).

**Ficheros afectados:** `backend/app/routers/dashboard.py` (nuevo),
`backend/app/platform/summary.py` (nuevo, las consultas),
`frontend/src/projects/alejandria-magazine/pages/MetricsDashboardPage.jsx` (nuevo),
`App.jsx` (el `index` deja de redirigir), `frontend/src/platform/api/dashboard.js`.

La portada quedó en `projects/`, no en `platform/pages/OverviewPage.jsx` como se
planteó aquí: lee el catálogo de agentes del proyecto y su store de artículos, y
`platform/` no puede importar de `projects/` (T8.6, con test que lo comprueba).
Moverla al builder exige antes sacar esas dos dependencias a registros, que es
trabajo de otra tarea.

## 5. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Una portada «global» filtra datos entre proyectos | Rompe el aislamiento de T8.5 por una vista de resumen | AC1 y AC6: dependencia `get_project_context` obligatoria y test con dos proyectos |
| Las agregaciones se vuelven lentas al crecer `agent_run_steps` | La portada tarda y se percibe como que la plataforma va lenta | Las consultas se apoyan en los índices existentes (`article_id, step_index`, `created_at`); ventana temporal acotada por defecto |
| «Anomalías» crece hasta ser un cajón de sastre | Nadie sabe qué significa el número | El conjunto es **enumerado** en la spec; añadir una condición es cambiar el AC3 |
| El estado del enjambre se queda pegado en «ejecutando» | La portada miente justo cuando algo se ha roto | Umbral de AC4: pasado ese tiempo, el paso abierto se muestra como incierto, no como activo |

## 6. Plan de pruebas

AC1, AC5 y AC6 por test de API con `httpx`/`ASGITransport` y dos proyectos
sembrados. AC3 y AC4 con trazas construidas a mano que disparen cada condición por
separado — una por una, para que el test diga **cuál** dejó de detectarse. AC2 con
un test de gobernanza que cruce el documento de magnitudes con el código que las
calcula. AC7 simulando la caída con dobles.

## 7. Impacto operativo / observabilidad

Sin migraciones: todo sale de tablas existentes. La portada añade carga de lectura
en cada visita; la ventana por defecto la acota. `/metrics` no se toca.

## 8. Backlog (sincronización SDD)

```yaml
# sdd-sync v1
epic:
  id: E16
  title: "Portada de plataforma: métricas del proyecto y estado del enjambre"
  area: area/observability
tasks:
  - id: T16.1
    title: "Definir las magnitudes de la portada (qué cuenta cada tarjeta y de dónde sale)"
    sev: medium
    depends_on: []
    acceptance: [AC2]
  - id: T16.2
    title: "Endpoint GET /api/v1/dashboard/summary por proyecto, con aislamiento probado"
    sev: high
    depends_on: [T16.1]
    acceptance: [AC1, AC5, AC6]
  - id: T16.3
    title: "Definir y calcular las anomalías sobre la traza de explicabilidad"
    sev: high
    depends_on: [T16.1]
    acceptance: [AC3]
  - id: T16.4
    title: "Estado del enjambre derivado de los pasos abiertos, con umbral de incertidumbre"
    sev: medium
    depends_on: [T16.2]
    acceptance: [AC4]
  - id: T16.5
    title: "Portada en el frontend y fin de la redirección del index"
    sev: medium
    depends_on: [T16.2, T16.3, T16.4]
    acceptance: [AC2, AC5]
  - id: T16.6
    title: "Degradación por tarjeta cuando una fuente de datos no responde"
    sev: low
    depends_on: [T16.5]
    acceptance: [AC7]
```
