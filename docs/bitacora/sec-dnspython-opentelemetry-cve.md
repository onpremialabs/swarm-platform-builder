# Actualizar dnspython y OpenTelemetry por dos CVE

## 2026-11-22 — Éxito ✅

- **Rama:** `sec/dnspython-opentelemetry-cve`
- **PR:** la de esta rama → `develop` (sin issue: lo bloqueaba todo el CI, petición directa del mantenedor)
- **Origen:** el check obligatorio «Cadena de suministro · pip-audit + npm audit»
  fallaba en `develop` y en todas las PRs (#599, #600, #601), con lo que ninguna
  podía mergearse. `pip-audit` encontró dos vulnerabilidades nuevas sin ignorar:
  - `dnspython` 2.9.0 — CVE-2026-128089, arreglada en 2.9.2.
  - `opentelemetry-api` 1.45.1 — CVE-2026-126360, arreglada en 1.45.2.

### Qué se hizo y dónde

- `backend/requirements.txt` (el lock con hashes), recompilado con `pip-compile
  --generate-hashes --no-strip-extras` en Python 3.12.10 subiendo solo lo necesario:
  - `dnspython` 2.9.0 → 2.9.2
  - `opentelemetry-api` 1.45.1 → 1.45.2
  - `opentelemetry-sdk` 1.45.1 → 1.45.2 (va acoplado al `api`)
  - `opentelemetry-semantic-conventions` 0.66b1 → 0.66b2 (acoplado)
- `requirements.in` no cambia: sus rangos ya admiten estas versiones.
- **Dos retoques manuales sobre el lock recompilado** (el diff final son solo las 4
  versiones y sus hashes, 12 líneas):
  - Se restauró el bloque de `uvloop==0.22.1 ; sys_platform != "win32"`. Compilar el
    lock en Windows evalúa ese marcador como falso y lo elimina, y el lock se
    despliega en Linux.
  - Se mantuvo la línea de cabecera original (`--no-index`).

### Verificación

- `pip-audit 2.10.1 --require-hashes -r requirements.txt` con las mismas excepciones
  que la CI (`PYSEC-2026-1325`, `PYSEC-2026-4298`): **«No known vulnerabilities
  found»**. El lock anterior, usado como control, reproduce las dos CVE.
- `pip install --require-hashes -r requirements.txt` en un entorno limpio: instala y
  quedan `dnspython 2.9.2`, `opentelemetry-api 1.45.2` y `opentelemetry-sdk 1.45.2`.
- Suite completa del backend con ese entorno: **1547 passed, 38 skipped, 1 failed**.
  El fallo es `tests/test_no_tracked_databases.py::test_a_fresh_dev_database_is_created_and_migrated`
  (`PermissionError` WinError 32 al borrar `dev.db` temporal en Windows), conocido y
  sin relación con las dependencias.

### Qué NO se hizo

- No se ejecutó `npm audit`: no se tocó el frontend.
- **No se probó el despliegue en Linux ni el build de Docker.** El lock se compiló y
  se instaló en Windows; la CI (Ubuntu) es la que confirma que resuelve igual allí.
- No se ejecutó la ruta de tracing con un colector OTLP real (`OTEL_ENABLED`
  está apagado por defecto); solo la suite de tests.
- El lock debería recompilarse en Linux en cuanto sea posible para evitar el
  retoque manual de `uvloop`.
