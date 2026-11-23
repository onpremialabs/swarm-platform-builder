# Tarea #532 — T22.9 Casos EDD de cobertura bibliográfica sobre papers de acceso abierto

## 2026-11-23 04:35 — Completada ✅

- **Rama:** `feat/532-cobertura-edd`
- **PR:** → `develop` (`Closes #532`)
- **Spec/ADR:** [SPEC-034](../specs/SPEC-034-verified-literature-discovery-and-library.md) (AC5, AC7) · [ADR-0011](../adr/0011-publication-gate-fail-closed.md) · SPEC-014 (EDD)
- **Dependencias:** #528, #617 (y T22.5) cerradas/mergeadas.

### Dónde estaba el problema
T22.5 dejó las métricas `source_verification` y `abstention` y dos casos por lado en `investigador-golden` / `investigador-regressions`, con un corpus ficticio. Faltaba cubrir los **bordes** de AC5/AC7 con papers de acceso abierto reales (DOI incluido).

### Qué se hizo y por qué
- `backend/evals/agent_behavior/datasets/investigador-cobertura.jsonl` (nuevo, pasa entero): exactamente N=3 verificadas (basta), documento interno sin verificar presente pero no citado (ADR-0011: sin excepción), DOI aportado por el autor cuenta, y tres abstenciones: N-1 con documento interno, fuente verificada bajo el umbral de similitud, biblioteca vacía. Papers: Vaswani 2017 (arXiv), Ioannidis 2005 (PLOS Med), Wilkinson 2016 (Sci Data, FAIR), Piwowar 2018 (PeerJ).
- `.../investigador-cobertura-regressions.jsonl` (nuevo, falla a propósito): cita el interno habiendo N verificadas, sintetiza con N-1, se abstiene con evidencia suficiente, declara abstención pero escribe texto.
- Datasets **separados** y sin sufijo `-golden`: no cambian la línea base ni `thresholds.yaml`, y `test_hay_umbrales_para_cada_agente_evaluable` no los exige. El gate sigue en `enforce: false` y no se marca como obligatorio.
- `backend/tests/test_edd_cobertura_bibliografica.py` (nuevo, 3 tests): el primero pasa entero con los 6 casos, el segundo comprueba que cada regresión falla por su métrica, el tercero que la procedencia es `handwritten`.
- `backend/evals/agent_behavior/README.md`: fila en la tabla de datasets.

### Definition of Done
- [x] **AC5** — `oa-exactamente-n-verificadas`, `oa-contexto-sin-verificar-no-se-cita`, `oa-doi-aportado-por-autor-cuenta` (source_verification 100) y la regresión `cita-interno-aunque-hay-suficientes` (falla por `source_verification`; sin excepción para «documento interno»).
- [x] **AC7** — `abstencion-n-menos-uno-con-interno`, `abstencion-fuente-bajo-umbral-de-similitud`, `abstencion-biblioteca-vacia` (abstention 100) y regresiones `sintetiza-con-n-menos-uno`, `se-abstiene-con-evidencia-suficiente`, `declara-abstencion-pero-escribe`.

### Verificación
- `python -m evals.agent_behavior.runner --dataset investigador-cobertura --mode replay` → exit 0.
- `... --dataset investigador-cobertura-regressions --mode replay` → exit 1 (esperado).
- `DEBUG=true SECRET_KEY=ci-secret-not-for-prod python -m pytest tests/test_edd_cobertura_bibliografica.py tests/test_edd_gate.py tests/test_investigador_verified_only.py -q` → 56 passed y 6 errores de fixture (Windows, ver notas).
- `... python -m pytest tests/test_investigador_verified_only.py tests/test_edd_cobertura_bibliografica.py -q` (por separado) → 38 passed. `test_edd_gate.py` pasó en la ejecución conjunta.

### Fuera de alcance / notas
- **Los golden son `handwritten`**: un verde dice que las métricas funcionan en los bordes, no que el modelo se comporte así. No se ejecutó `live`. Las salidas grabadas son texto escrito a mano (los DOI/títulos son de papers reales, el texto no es una salida del modelo).
- Los casos de abstención verifican la decisión **grabada**; que el adapter calcule `verified_sources`/umbral lo cubren `tests/test_investigador_verified_only.py`.
- Al correr en Windows junto con `test_edd_gate.py`, 6 tests de `test_investigador_verified_only.py` dieron error de fixture (en aislamiento pasan); repetidos por separado pasan los 38. No se ejecutó la suite completa (es larga en Windows; el cambio solo añade datasets, un test y una fila de README).
