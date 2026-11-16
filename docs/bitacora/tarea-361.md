# Tarea #361 — T17.4: Exportación JSONL con esquema versionado y respeto a la retención

## 2026-11-05 — Completada ✅

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **Spec:** SPEC-029 · Épica E17 · AC3

### Qué se hizo y dónde

- `backend/app/routers/agents.py` — `GET /api/v1/agents/{id}/export.jsonl`, con
  `EXPORT_SCHEMA` y `EXPORT_SCHEMA_VERSION`.
- `frontend/src/platform/api/agents.js` — `downloadExport()`.
- La pestaña de integridad (T17.6) ofrece el botón.

### Esquema versionado y explícito

La primera línea es una cabecera con el esquema, su versión, la de la
serialización canónica, el alcance y el número de pasos. Un fichero guardado tiene
que seguir diciendo de qué habla cuando la tabla gane columnas.

`EXPORT_SCHEMA` es una lista de campos y no «todas las columnas»: así añadir una al
modelo no cambia el formato de exportación sin que nadie lo decida.

### Los hashes van dentro

Es lo que hace la cadena verificable **fuera** de la plataforma, y lo que la vuelve
útil aunque no haya notarización: quien recibe el fichero puede recalcular la
cadena por su cuenta sin pedirnos permiso ni fiarse de nuestra interfaz.

### Retención: no se vuelca nada que la traza no guarde ya

`input_digest` es un resumen recortado a propósito (`MAX_TEXTO`, 4.000 caracteres)
y la exportación no lo convierte en un segundo almacén del artículo: el cuerpo
completo vive en `articles` y se rige por su propia ventana. La cabecera lo dice en
el campo `note`, para que quien reciba el fichero no lo confunda con un volcado.

`docs/governance/data-retention.md` queda actualizado: la exportación vuelca lo que
`agent_run_steps` guarda y nada más, y una vez descargado el fichero sale del
alcance de la política —lo custodia quien lo exportó—. También se anota que las
columnas de la cadena son metadatos derivados y caducan con su fila.

### Descarga autenticada

El cliente va por axios con `responseType: 'blob'` y no por un `<a href>`: el
endpoint pide `Bearer` y `X-Project-Id`, y la navegación directa no los lleva —
habría dado 401. Se guarda desde el cliente con un object URL.

### Tests

La cabecera trae esquema y versión, hay una línea por paso, todas llevan
`content_hash`, y el `input_digest` exportado sigue siendo el resumen.

### Definition of Done

- [x] AC3: JSONL con una línea por paso y esquema documentado y versionado.
- [x] AC3: no vuelca contenido que la retención no permita.
- [x] Incluye los hashes: verificable fuera de la plataforma.
- [x] `data-retention.md` actualizado.
