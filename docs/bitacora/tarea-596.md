# Tarea #596 — T29.13 Controles de CI: paridad de claves es/en y bloqueo de literales nuevos en JSX

## 2026-11-23 — Completada

- **Rama:** `feat/596-controles-ci-i18n`
- **PR:** abierta contra `develop` (`Closes #596`)
- **Spec/ADR:** SPEC-041 (AC7, AC11)
- **Dependencias:** #589 (T29.6) mergeada

### Qué se hizo y por qué
- `scripts/check_i18n.py` (stdlib, mismo patrón que `check_design_tokens.py` / `check_async_states.py`):
  - **Paridad (AC7)**: por espacio de nombres compara `es.json` y `en.json` de cada `i18n/`; falla si una
    clave está en un idioma y no en el otro, si difieren las variables `{x}` y si hay claves sin usar (usada =
    cadena `'clave'` / `'ns:clave'` en el código o prefijo de plantilla dinámica). Las formas plurales
    (`_one`, `_other`...) cuentan como una sola clave porque cada idioma tiene las suyas. Un `en.json`
    ausente es un catálogo vacío. Con los catálogos de hoy (vacíos) pasa de forma vacía.
  - **Literales (AC11)**: detecta texto entre etiquetas, atributos visibles (`title`, `placeholder`,
    `aria-label`, `alt`, `label`...) y `{'texto'}` en `.jsx`, y falla con `archivo:línea`.
- Como hoy casi todo el texto es literal, el control usa una **línea base** de deuda
  (`scripts/i18n_literals_baseline.json`: 635 literales en 31 ficheros, por fichero + texto + recuento) y una
  lista de **excepciones permanentes con motivo** (`scripts/i18n_literals_exceptions.json`, solo marca
  «AlejandrIA»). Un literal que no esté en ninguna falla; una entrada de la línea base que ya no existe
  también falla hasta regenerar, así que la deuda **solo baja** y no puede esconder literales nuevos. La
  clave es el texto y no la línea, para que editar un fichero no desplace la línea base.
- `backend/tests/test_i18n_checks.py` (14 tests): catálogos de prueba que demuestran el fallo en cada caso
  (clave solo en un idioma, clave sin usar, variable ausente, plurales), `.jsx` de prueba para literal nuevo
  con archivo y línea, recuento repetido, excepciones y coherencia de la línea base; y ejecución del script
  sobre el repo. Enganche a CI: el job `Backend · pytest` ya corre `tests/`, así que **no se añade paso al
  workflow**.
- `CLAUDE.md`: párrafo breve con el control.

### Cómo se regenera y se reduce
- Tras extraer cadenas a los catálogos (T29.7/T29.8): `python scripts/check_i18n.py --update` reduce la línea
  base (se niega si hay literales nuevos; nunca la amplía). T29.7/T29.8 la irán vaciando hasta `{}`.
- `--init-baseline` regenera desde cero (solo bootstrap; revisar el diff en la PR).
- Heurística: puede dar falsos positivos (p. ej. un `>` de comparación seguido de `<`); si es un caso
  legítimo, va a la línea base en la PR que lo introduce o a las excepciones con motivo.

### Checklist DoD
- [x] **AC7** — paridad: clave en un solo idioma, claves sin usar y variable de interpolación ausente
  fallan (tests con catálogos de prueba).
- [x] **AC11** — literal nuevo en `.jsx` falla con archivo y línea; lista de excepciones revisable y versionada.

### Verificación
- `python -m pytest -q tests/test_i18n_checks.py` (desde `backend/`): 14 passed.
- `npm run build` y `npm run build:public` (frontend): OK.
- Suite completa de backend (una sola ejecución, 1:02:53): 1 failed, 1887 passed, 38 skipped. El único fallo es `test_no_tracked_databases::test_a_fresh_dev_database_is_created_and_migrated` (WinError 32, conocido en Windows).

### Notas
- No se extraen cadenas ni se crea `en.json` (T29.7-T29.9); no se toca el tema (T29.1).
