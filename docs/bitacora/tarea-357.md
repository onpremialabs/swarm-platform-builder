# Tarea #357 — T16.6: Degradación por tarjeta cuando una fuente no responde

## 2026-11-05 — Completada ✅

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **Spec:** SPEC-028 · Épica E16 · AC7

### El problema, que ya habíamos sufrido

`GET /api/v1/dashboard/summary` componía la respuesta con varios `await` seguidos.
Si uno fallaba, la petición entera devolvía 500 y la portada se quedaba a cero.

Y un cero no se distingue de «no se pudo preguntar». Es exactamente el error que
esta misma spec persigue en AC3 —donde el cero tiene semántica porque se enumera
qué se comprobó— reproducido en el transporte. Durante la depuración de esta misma
rama costó bastante: la portada enseñaba ceros perfectamente plausibles mientras el
backend tenía 86.923 tokens, porque el cliente recibía HTML en vez de JSON y cada
`summary?.campo ?? 0` caía al valor por defecto.

### Qué se hizo y dónde

`backend/app/routers/dashboard.py` — cada agregación va en su propio intento
(`_seccion`) y la respuesta declara en `sections` qué se pudo calcular:

```json
"sections": {
  "metrics":    {"available": true,  "source": "database"},
  "executions": {"available": false, "source": "database", "reason": "RuntimeError"}
}
```

El `rollback` dentro de `_seccion` no es decorativo: tras un error la sesión de
SQLAlchemy queda inutilizable, y sin él la primera sección rota tumbaría también
las siguientes — la degradación en cascada que AC7 prohíbe.

Una sección caída devuelve su forma vacía, no ceros: la UI lo distingue mirando
`sections[...].available`, nunca el valor.

`MetricsDashboardPage.jsx`:

- `StatTile` acepta `unavailable`: pinta «No disponible» con borde discontinuo e
  icono de nube tachada, en vez de un cero que se leería como dato.
- Las secciones de enjambre, ejecuciones y métricas por artículo distinguen tres
  casos, no dos: **no disponible** (no se pudo preguntar), **vacío** (se preguntó y
  no hay nada) y **con datos**.

### Sobre Qdrant

El AC nombra «(base, Qdrant)». Hoy **todas** las secciones de la portada salen de
la base: ninguna tarjeta lee Qdrant, ni siquiera la anomalía `rag_empty`, que
cuenta `rag_sources` ya guardadas en `agent_run_steps`.

Por eso no se añade un sondeo a Qdrant: probar una fuente de la que no depende
ninguna tarjeta sería ruido que además puede fallar por su cuenta. El mecanismo es
genérico —cada sección declara su `source`—, así que la tarjeta que mañana lea
Qdrant declara `"source": "qdrant"` y queda cubierta sin tocar el router.

Se deja escrito aquí para que la decisión sea revisable y no parezca un olvido.

### Test

`test_una_seccion_caida_no_tumba_la_portada` hace reventar una agregación y
comprueba las dos mitades del AC: la sección queda marcada como no disponible con
su motivo **y** el resto sigue devolviendo datos reales —no ceros—.

### Definition of Done

- [x] AC7: una fuente caída no deja la portada en blanco ni bloquea la navegación.
- [x] Las secciones afectadas se muestran indisponibles; las demás funcionan.
- [x] «No disponible» y «cero» se ven distinto, y el motivo se enseña.
- [x] Cubierto por test que simula el fallo.
