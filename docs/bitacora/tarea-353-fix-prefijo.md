# Fix — T16.2: el endpoint del dashboard quedó fuera del proxy de Vite

## 2026-11-04 — Corregido

- **Rama:** `feat/358-369-trazabilidad-ui-metricas`
- **Spec:** SPEC-028 · Épica E16 (corrige lo entregado en [tarea-353](tarea-353.md))

### Síntoma

`/dashboard/traceability` renderizaba la portada entera con **todas las magnitudes
en cero** y la tabla de artículos vacía, sin mostrar ningún error. El backend
tenía 9 artículos, 65 ejecuciones y 86.923 tokens para ese proyecto.

### Causa

`backend/app/routers/dashboard.py` se registró con `prefix="/dashboard"`. Es el
**único** router del backend fuera de `/api/v1`; los otros doce usan
`/api/v1/<nombre>`.

`frontend/vite.config.js` solo reenvía `/api` al backend, así que en desarrollo
`GET /dashboard/summary` nunca llegaba a FastAPI: lo atendía el propio servidor de
Vite, que para una ruta desconocida devuelve `index.html` (el fallback de SPA).

El fallo es silencioso por cómo encaja con el código de la página: axios recibe
200 con HTML, `summary` pasa a ser un string, y cada lectura `summary?.campo ?? 0`
cae al valor por defecto. Cero no se distingue de «no se pudo preguntar» — que es
exactamente lo que `scripts/check_async_states.py` persigue en el frontend, aquí
reproducido por una ruta mal puesta.

Comprobación directa del contraste:

```
GET http://localhost:5173/api/v1/dashboard/summary  →  {"tokens_total":86923,...}
GET http://localhost:5173/dashboard/summary         →  <!doctype html>...
```

### Qué se hizo y dónde

- `backend/app/routers/dashboard.py`: prefijo a `/api/v1/dashboard`, que es la
  convención del resto de routers. No se tocó `vite.config.js`: añadir `/dashboard`
  al proxy arreglaría el síntoma dejando el router como la excepción del backend.
- `frontend/src/platform/api/dashboard.js`: la llamada apunta a la ruta nueva.
- `backend/tests/test_dashboard_summary.py`: rutas actualizadas.

### Por qué los tests no lo detectaron

Los cinco tests de T16.2 **nunca llegaron a ejecutar el endpoint**. Autenticaban
contra `/auth/token` con form-data, y esa ruta no existe: la real es
`/api/v1/auth/login` con JSON `{email, password}`. Los tests fallaban en el
`assert` del login, antes de pedir la portada, así que el aislamiento por proyecto
(AC6) estaba sin verificar pese a figurar como cumplido.

Al corregir el login apareció un segundo fallo, solo visible al correr el fichero
entero: `PermissionError [WinError 32]`. El fixture `setup_db` borra el fichero
SQLite al empezar cada test, pero el pool de conexiones lo mantiene abierto y
Windows no deja borrar un fichero en uso — el primer test pasaba y los cuatro
siguientes daban ERROR en el setup. Se añade `await engine.dispose()` antes del
`unlink` y al cerrar, en vez del `drop_all` anterior, que además chocaba con el
ciclo de FKs `users` ↔ `projects`.

Los cinco tests pasan ahora de verdad, y con ellos AC6 queda realmente cubierto.

### Definition of Done

- [x] La portada muestra los datos del proyecto en desarrollo.
- [x] El router sigue la convención `/api/v1` del resto del backend.
- [x] Los 5 tests de T16.2 pasan ejecutando el endpoint, no solo importándolo.
- [x] `scripts/check_async_states.py` y `npm run build` en verde.
