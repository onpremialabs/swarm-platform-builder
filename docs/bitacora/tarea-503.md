# Tarea #503 — Referencia HTML del sistema de diseño y contorno de controles del UI kit Studio

## 2026-11-11 — Éxito ✅

- **Rama:** `docs/ds-valores-reales` (la misma de #501; su PR #502 ya estaba mergeada)
- **PR:** la de esta rama → `develop` (`Closes #503`)
- **Spec:** SPEC-003 (E7), sin cambios en sus criterios.

### Por qué

El sistema de diseño de `frontend/ds/` estaba repartido entre `README.md`, `tokens.md`,
`ACCESSIBILITY.md`, las páginas de zeroheight y unas 30 fichas de `preview/`. No había una
única página donde verlo entero. Al montarla aparecieron dos desajustes con lo que #501
dejó documentado:

- `ui_kits/studio/studio.css` aún daba a `.inp`, `.search` y `.btn-secondary` un contorno
  `--border-strong` (#d8dde6, **1.36:1** sobre blanco). WCAG 2.1 SC 1.4.11 pide 3:1 para el
  contorno de un control, y para eso existe `--border-control` (#7b8caa, **3.40:1**).
- El hover del botón secundario **aclaraba** el contorno (`--neutral-40`), así que bajaba
  todavía más de 3:1. Además contradecía la regla del DS: el hover oscurece un escalón.

### Qué se hizo y dónde

- **`frontend/ds/design-system.html`** (nuevo): referencia en 21 secciones con índice
  lateral (principios, arquitectura de tokens, color, tipografía, espaciado, radio,
  elevación, movimiento, iconografía, botones, formularios, estado, cards y modales,
  Flow Designer y ejecución, Content System `.prose`, dataviz, voz y tono, accesibilidad,
  tema claro/oscuro, uso). **No redefine ningún valor**: enlaza `colors_and_type.css` y lee
  hex y ratios de contraste en vivo del CSS calculado, así que no puede quedarse atrás si
  cambia un token. Tiene un selector de tema que aplica `data-theme="dark"`.
- **`frontend/ds/ui_kits/studio/studio.css`**: `.inp`, `.search` y `.btn-secondary` pasan
  a `--border-control`. El hover del secundario usa `--neutral-80`, con un comentario que
  explica por qué no puede ser un tono más claro.

### Qué NO se hizo

- No se cambió ningún token ni nada de `frontend/src`. Los otros usos de
  `--border-strong` (hover de cards, separadores, nodos de flujo, tags de formato) son
  decorativos y se dejaron como estaban.
- **`preview/a11y-contrast.html` sigue con ratios fijos desactualizados** (12.6, 4.8, 4.6,
  5.4 frente a los 11.48, 4.63… de `ACCESSIBILITY.md`). Queda anotado en la sección 20 de
  la página nueva.
- Al abrirla con doble clic (`file://`), la página no carga los tokens. Hay que servirla
  por HTTP, por ejemplo con `python -m http.server --directory frontend/ds`.

### Verificación

- Se comprobó en el navegador, servida por HTTP, en tema claro, oscuro y ancho de móvil.
  No hubo errores de consola, se renderizaron todos los iconos y no apareció scroll
  horizontal.
- Los ratios que calcula la página en tema claro coinciden con los de `ACCESSIBILITY.md`:
  cuerpo 11.48, enlace 4.63, `--border-control` 3.40 y `--border-strong` 1.36.
- En el UI kit Studio, `.inp`, `.search` y `.btn-secondary` resuelven a `rgb(123,140,170)`
  (`#7b8caa`).
- En verde: `scripts/check_design_tokens.py`, `scripts/check_contrast.py` (68 pares AA) y
  `tests/test_design_tokens.py` (12 passed). No se ejecutaron la suite completa ni las
  builds, porque la aplicación no carga ninguno de los ficheros cambiados; las corre la CI
  de esta PR.

### Definition of Done

- [x] La página toma los tokens de `colors_and_type.css` sin redefinir valores.
- [x] Los controles del UI kit Studio tienen un contorno ≥ 3:1.
- [x] Checks de tokens y contraste en verde.
- [x] Sin secretos en el diff.
