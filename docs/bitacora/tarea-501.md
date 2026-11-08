# Tarea #501 — Alinear la documentación del sistema de diseño con los tokens reales

## 2026-11-08 — Éxito ✅

- **Rama:** `docs/ds-valores-reales`
- **PR:** la de esta rama → `develop` (`Closes #501`)
- **Spec:** SPEC-003 (E7), sin cambios en sus criterios.

### Por qué

T7.2 (#193) corrigió el contraste **en los tokens** de `colors_and_type.css`, pero la
documentación de `frontend/ds/` y `tokens.dtcg.json` no se actualizaron. Quien la leía
recibía colores y ratios que la aplicación ya no usa, y una regla equivocada: daba
`--border-strong` (1.36:1) como contorno mínimo de un control, cuando WCAG 1.4.11 pide
3:1 y por eso existe `--border-control`. Además, el README raíz no enlazaba el sistema
de diseño, así que era difícil de encontrar.

### Qué se hizo y dónde

- **`frontend/ds/README.md`, `tokens.md`, `ACCESSIBILITY.md`:** texto atenuado, colores
  de estado, `--border-control`, ratios medidos y foco visible real (contorno de 2px
  con separación de 2px; `--focus-ring` solo se añade en inputs).
- **`frontend/ds/zeroheight/pages/`** (`Accessibility_standards`,
  `Designing_for_accessibility`, `Button`, `Code`, `Color`, `Confirmation_success`,
  `Foundations`, `Components`, `Tokens`): los mismos valores.
- **`frontend/ds/preview/`** (`colors-semantic`, `comp-buttons`, `comp-inputs`,
  `comp-selection`): colores de estado y contorno de los controles.
- **`frontend/ds/zeroheight/tokens.dtcg.json`:** alias de `text.muted`, estados y
  estados editoriales; tokens nuevos `neutral.65`, `border.control`, `brand.on-tint` y
  `text.on-error`.
- **`README.md`:** fila en la tabla de documentación y `ds/` en la estructura de carpetas.

No se tocó ningún token, estilo ni componente: solo documentación.

### Qué NO se hizo

- **No se publicó en zeroheight.** El styleguide seguirá con los valores antiguos hasta
  que alguien con la API key ejecute `upload_tokens.sh` y actualice las páginas.
- **El tema oscuro sigue sin activarse:** los tokens existen, pero nada en `frontend/src`
  ni en los HTML pone `data-theme`. Tampoco se cambió la documentación que lo describe.
- **`tokens.dtcg.json` sigue sin tema oscuro**, y sigue sin haber un paso que lo genere
  desde el CSS, así que puede volver a desviarse.
- `Release_notes.md` conserva sus valores por ser histórico. La mención a `DESIGN.md` en
  las fuentes del README de `ds/` también se mantiene, aunque ese fichero ya no exista.

### Verificación

Los ratios proceden de `python scripts/check_contrast.py --table`. Se comprobó, con un
script local, que cada alias semántico del JSON resuelve al mismo valor que su token del
tema claro en el CSS, y que no quedan los ratios antiguos en `frontend/ds/`.

En verde: `check_design_tokens.py`, `check_contrast.py`, `validate_specs.py` y
`tests/test_design_tokens.py`. No se ejecutó la suite completa ni las builds, porque
ningún fichero cambiado lo carga la aplicación; las corre la CI de esta PR.

No se abrieron en navegador las fichas de `preview/` modificadas.

### Definition of Done

- [x] Valores documentados coinciden con `colors_and_type.css` y `check_contrast.py`.
- [x] `tokens.dtcg.json` refleja alias y tokens actuales del tema claro.
- [x] El README raíz enlaza el sistema de diseño.
- [x] Sin secretos en el diff.
