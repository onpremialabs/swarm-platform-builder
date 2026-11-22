# Tarea #551 — T25.2 — Marcadores de la compuerta con expresiones regulares y validación al cargar

## 2026-11-22 10:50 — Completada ✅

- **Rama:** `feat/551-marcadores-regex`
- **PR:** ver la PR que cierra #551 → `develop` (relacionada con #600 / T25.1, pero independiente: no comparten archivos ni se bloquean)
- **Spec/ADR:** SPEC-037 (AC2, §1 y §4) · SPEC-032 / ADR-0011 (falla cerrada)
- **Dependencias:** ninguna

### Dónde estaba el problema
`gate.placeholders` (`backend/projects/alejandria-magazine/template.yaml`) solo admitía
literales y `platform/publication_gate/placeholders.py::_pattern` los escapaba todos. No
había forma de cubrir «[Su Nombre/Autoría]» ni de detectar «Fecha: Octubre 2023
(Borrador)» en un artículo creado el 15-sep-2026.

### Qué se hizo y por qué
- `placeholders.py`: un marcador con prefijo `regex:` se compila como expresión regular
  (distingue mayúsculas; `(?i)` al principio para lo contrario). `validate_marker` /
  `compile_regex_marker` rechazan al cargar: regex no compilable, vacía, de más de 200
  caracteres, que casa con la cadena vacía (marcaría todo), con referencias hacia atrás,
  repeticiones acotadas > 1000, **repeticiones multiplicativas anidadas** (`(a+)+`) y
  **alternativas dentro de una repetición** (`(a|a)*`). Es una auditoría estática del
  árbol de `re._parser`: conservadora (un patrón legítimo que caiga ahí se reescribe sin
  anidar) pero determinista, sin hilos ni temporizadores. Los literales funcionan igual.
  El código delimitado se sigue ignorando también para las regex.
- `config.py::parse_gate`: valida cada marcador al cargar y traduce el error a
  `GateConfigError` (el loader lo convierte en `TemplateError`, como el resto de
  validaciones de `platform/projects/`). Nuevo bloque `gate.dates` (`labels`,
  `tolerance_days`) validado igual.
- `dates.py` (nuevo) y `check_placeholders(..., dates, created_at, now)`: **decisión sobre
  la fecha fuera de rango.** El mínimo determinista que no da falsos positivos es examinar
  solo las líneas de metadatos que empiezan por una etiqueta declarada por el proyecto
  (`Fecha:`, `Date:`…), no el cuerpo. Una fecha está fuera si termina antes de la creación
  del artículo (menos 1 día de tolerancia por zona horaria) o empieza después del día de la
  evaluación (más tolerancia). Con granularidad de mes/año se compara el intervalo entero
  («2026» y «septiembre 2026» no se marcan en un artículo de septiembre de 2026). Entiende
  ISO, d/m/aaaa, «15 de septiembre de 2026», «September 15, 2026», «Octubre 2023» y año
  suelto; fechas imposibles (31 de febrero) no se juzgan. Un hallazgo se registra en la
  evidencia de `placeholders` con `pattern: date_out_of_range`, así el informe mantiene su
  forma (4 criterios) y bloquea por el criterio existente. Sin etiquetas configuradas o sin
  `created_at` no se comprueba nada.
- `gate.py::evaluate_gate` acepta `created_at`/`now`; `service.py::evaluate_and_store` pasa
  `article.created_at`. La compuerta no nombra agentes: el dato llega por el servicio.
- `template.yaml`: regex de autoría sin rellenar (`[Su Nombre/Autoría]`, `[Your Name]`,
  `[Autor]`; no casa con enlaces `[Autor](url)`) y `gate.dates` con las etiquetas de
  AlejandrIA.
- `tests/test_gate_marker_regex_dates.py` (nuevo).

### Definition of Done
- [x] **AC2** — La compuerta admite `regex:` además de literales; «[Su Nombre/Autoría]» y
  «Fecha: Octubre 2023» en un artículo creado en sept-2026 dan `placeholders` `failed`
  (bloqueante), probado con la plantilla real de AlejandrIA y por `evaluate_gate`.
- [x] Regex inválida o catastrófica → error al cargar (`TemplateError`), no en ejecución.
- [x] Compatibilidad: la lista de literales actual funciona igual (test de regresión).
- [x] Falsos positivos: citas «(García, 2019)», años en el cuerpo y fechas válidas no bloquean.
- [x] Falla cerrada (ADR-0011): sin cambios en la semántica; un marcador inaceptable
  impide cargar el proyecto en vez de ignorarse.

### Verificación
Desde `backend/`, con `DEBUG=true SECRET_KEY=ci-secret-not-for-prod`:
- `python -m pytest -q tests/test_gate_marker_regex_dates.py tests/test_gate_placeholders.py
  tests/test_publication_gate.py` → 86 passed (una primera pasada dio 1 fallo en
  `gate.dates: []`, que `or {}` tragaba; corregido).
- `tests/test_publication_gate.py::test_la_plantilla_de_alejandria_declara_la_compuerta`
  comparaba la lista entera con los literales; ahora compara los literales y exige que
  haya `regex:`.
- Suite completa (`python -m pytest -q`, tras los últimos cambios) → 1542 passed,
  38 skipped, 1 failed: `tests/test_no_tracked_databases.py::
  test_a_fresh_dev_database_is_created_and_migrated`, el fallo conocido de Windows
  (PermissionError WinError 32), sin relación con este cambio.

### Fuera de alcance / notas
- No toca prompts ni perfiles de agentes: la DoR/DoD de evaluación (EDD) no aplica.
- El detector de fechas no mira el cuerpo: «Octubre 2023» en un párrafo no se marca a
  propósito. Ampliarlo exigiría criterio semántico (¿es la fecha del manuscrito o una cita?).
- Los literales no cambian; solo los `regex:` se auditan con la heurística estática. La
  auditoría puede rechazar patrones inocuos con alternativas bajo `*`/`+`.
