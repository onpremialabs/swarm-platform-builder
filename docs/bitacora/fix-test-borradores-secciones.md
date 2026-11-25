# Bitácora — arreglo de tests tras combinar #662 y #663

- **Fecha:** 2026-11-25
- **Rama:** `fix/test-borradores-secciones-t2410`
- **Relacionadas:** #660 (T23.9, PR #662) y #661 (T24.10, PR #663)

## Qué se hizo
`backend/tests/test_redactor_citation_format.py` (de #662) usaba borradores de una sola sección
(`## Introducción`). Con #663 el Redactor exige las secciones de `gate.structure` y falla el paso
(«faltan secciones obligatorias: methods, results, discussion»), así que 9 tests de ese archivo
rompían en `develop` tras mergear ambas PR. Cada PR pasaba su CI por separado.

## Por qué
Las dos PR se desarrollaron en paralelo; la interacción solo aparece al combinarlas.
El cambio es solo de fixtures: `SIN_CITAS` y `CON_CITAS` ganan Metodología, Resultados y Discusión.
No se toca código de producción.

## Verificación
`pytest tests/test_redactor_citation_format.py tests/test_redactor_truncation.py`: 47 passed.
