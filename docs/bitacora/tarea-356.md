# Tarea #356 — T16.5: Portada en el frontend y fin de la redirección del index

## 2026-11-05 — Completada ✅ (con dependencias abiertas — ver notas)

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **Spec:** SPEC-028 · Épica E16

### Qué se hizo y dónde

`frontend/src/App.jsx`: el `index` de `/dashboard` deja de redirigir.

```diff
-<Route index element={<Navigate to="articles" replace />} />
+<Route index element={<MetricsDashboardPage />} />
```

Es el problema con el que abre SPEC-028 §1: entrar en `/dashboard` te dejaba en el
listado de artículos y no había ningún sitio donde ver de un vistazo qué está
haciendo la plataforma.

`/dashboard/traceability` sigue sirviendo la misma página, así que el enlace del
menú lateral y cualquier marcador guardado siguen valiendo.

### Dónde vive la portada, y por qué no donde decía la spec

SPEC-028 §4 la situaba en `frontend/src/platform/pages/OverviewPage.jsx`, es decir
en el **builder**. Está en `projects/alejandria-magazine/pages/MetricsDashboardPage.jsx`,
en el proyecto, porque lee dos cosas que son del proyecto: el catálogo de agentes
(`agentMeta`, para el color y la etiqueta de cada tarjeta) y el store de artículos
(para los títulos). `platform/` no puede importar de `projects/` —T8.6, con test
que lo comprueba—, así que moverla exige antes sacar esas dos dependencias a
registros, como ya se hizo con `setAgentCatalog` y `setProjectNavItems`.

Se deja donde está y se corrige la spec, que es lo que describía mal.

### AC cumplidos y lo que sigue abierto

Los dos AC de la tarea estaban cubiertos por T16.1 y T16.2:

- **AC2** — cada tile dice qué cuenta, sobre qué ventana y de qué tabla sale, y la
  latencia declara ser p50 de paso de agente y no de petición HTTP.
- **AC5** — los artículos muestran estado y tokens reales desde `agent_run_steps`.

La tarea figura bloqueada por **#355 (T16.4)** y la épica tiene además **#357
(T16.6)** abierta, así que la portada se entrega **sin** el estado del enjambre en
tiempo real (AC4) y **sin** la degradación por tarjeta cuando una fuente cae (AC7).
Lo que sí hay de AC7 es que la página ya no se queda en blanco: si la petición
falla, se pintan los tiles a cero y un aviso en rojo **arriba**, no al pie donde
nadie lo veía.

Revertir es una línea en `App.jsx` si se prefiere esperar a que #355 cierre.

### Definition of Done

- [x] AC2: magnitudes definidas y documentadas en código y UI.
- [x] AC5: estado y coste reales por artículo.
- [x] El `index` de `/dashboard` ya no redirige.
- [x] `npm run build` y `npm run build:public` en verde.
- [ ] AC4 (estado del enjambre) — #355, abierta.
- [ ] AC7 (degradación por tarjeta) — #357, abierta.
