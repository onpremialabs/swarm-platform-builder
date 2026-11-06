# Parches de vulnerabilidades en dependencias

## 2026-11-06 — Éxito ✅

- **Rama:** `sec/parches-vulnerabilidades-deps`
- **PR:** la de esta rama → `develop` (sin issue: petición directa del mantenedor)
- **Origen:** el job `deps-audit` fallaba en todas las PRs contra `develop` por CVE
  publicados después de compilar los locks (14 en el backend, 1 alta en el frontend).

### Qué se hizo y dónde

- `backend/requirements.txt`: subidas de parche con hashes nuevos —`pypdf` 6.21.2→6.21.4,
  `pyasn1` 0.6.4→0.6.5, `dnspython` 2.8.0→2.9.0, `langgraph-sdk` 0.4.4→0.4.6— y la familia
  OpenTelemetry 1.44.0→1.45.1, que arrastra `semantic-conventions` 0.66b1 y dos paquetes
  nuevos (`opentelemetry-exporter-http-transport`, `opentelemetry-exporter-otlp-common`)
  porque el SDK fija la API a la versión exacta. `requirements.in` no cambia.
- Recompilado con `pip-compile --upgrade-package <pkg>==<versión>` para no mover nada más.
  Compilar en Windows quita `uvloop` (marcador `sys_platform != "win32"`): se repuso su
  bloque tal cual estaba.
- `frontend/package-lock.json`: `follow-redirects` 1.16.1→1.16.2 (`npm audit fix`, sin
  cambios de rango).

### Verificación

- `pip install --require-hashes -r requirements.txt` y `pip-audit` con los mismos
  `--ignore-vuln` de la CI: sin vulnerabilidades.
- `npm audit --omit=dev --audit-level=high`: sale 0. `npm run build` y `npm run build:public` OK.
- `pytest` backend: 1430 passed. `test_a_fresh_dev_database_is_created_and_migrated` falla
  solo en Windows (el `dev.db` temporal sigue abierto al borrarlo); la CI es Linux.

### Qué NO se hizo

- `react-router` / `react-router-dom` tienen 2 avisos **moderados** cuyo arreglo es la
  versión mayor 7.18 (rompe compatibilidad). No bloquean el gate (`--audit-level=high`);
  quedan para una migración aparte.
