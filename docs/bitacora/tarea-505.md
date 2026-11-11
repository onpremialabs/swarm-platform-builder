# Tarea #505 — Servir la referencia del sistema de diseño desde la web de docs

## 2026-11-11 — Éxito ✅

- **Rama:** `docs/ds-referencia-en-docs`
- **PR:** la de esta rama → `develop` (`Closes #505`)
- **Spec:** SPEC-003 (E7), sin cambios en sus criterios.

### Por qué

#503 dejó la referencia visual del sistema de diseño en `frontend/ds/design-system.html`.
Esa ubicación tenía tres problemas:

- **Nada la servía.** GitHub muestra los `.html` como código, no como página.
- **No se veía bien fuera del repo**, porque carga `colors_and_type.css` y los logos con
  rutas relativas. Copiar solo el `.html` la dejaba sin estilos.
- **Nadie la enlazaba:** ni el README, ni `frontend/ds/README.md`, ni la web de docs.

### Qué se hizo y dónde

- **`docs/public/design-system/index.html`**: la página, movida con `git mv` desde
  `frontend/ds/design-system.html`. VitePress copia `docs/public/` tal cual, así que la
  web de docs la sirve en `/design-system/index.html`. Junto a ella están
  `colors_and_type.css` y `assets/{logomark,wordmark}.svg`, de modo que la carpeta funciona
  también con doble clic o copiada a otro sitio. Se sigue el mismo patrón que
  `docs/public/onboarding/`.
- **`scripts/sync_design_system_docs.py`**: copia esos tres ficheros desde
  `frontend/ds/`, que **sigue siendo la fuente de verdad** porque la aplicación lo importa
  desde `src/index.css`. Con `--check` sale con 1 si la copia va atrás. Compara sin tener
  en cuenta CRLF/LF.
- **`backend/tests/test_design_system_docs.py`**: falla si la copia se desfasa, si la
  página empieza a cargar en local un fichero que el script no sincroniza, o si la página
  redefine algún token en su `<style>`.
- **`docs/guide/design-system.md`**: página de la guía que explica cómo abrir la
  referencia, de dónde salen los valores y cómo resincronizarlos.
- **`docs/.vitepress/config.js`**: entrada «Sistema de diseño» en la navegación superior
  (con `target: '_self'`, para que el router de VitePress no intercepte una página
  estática) y en la barra lateral de la guía.
- **`README.md`**: fila en la tabla de documentación y en el árbol de carpetas. **`frontend/ds/README.md`**: fila en el índice.
- **La página**: los textos que hablaban de su ubicación ahora explican la copia y cómo
  resincronizarla.

### Qué NO se hizo

- **No se copió el resto de `frontend/ds/`** (`preview/`, `ui_kits/`, las guías `.md`).
  Siguen junto a sus tokens; la guía de docs los enlaza.
- **La build completa de la web de docs (`vitepress build`) ya fallaba en `develop`**
  por `docs/specs/TEMPLATE.md` (Vue: «Element is missing end tag», línea 7) y avisos en
  `bitacora/tarea-166.md`. Esta PR no los arregla. La web se verificó con
  `vitepress dev`. Ningún workflow de CI construye `docs/`.
- No se publicó la web de docs en ningún hosting.

### Verificación

- `npm run dev` en `docs/`: `/guide/design-system` muestra la página de la guía. Su
  enlace abre `/design-system/index.html`, donde los tokens cargan (`--brand` =
  `#0176d3`), el logo y todos los iconos se renderizan y el contraste calculado
  coincide con `ACCESSIBILITY.md` (11.48:1).
- `python scripts/sync_design_system_docs.py --check` → OK (3 ficheros).
- `pytest tests/test_design_system_docs.py tests/test_design_tokens.py tests/test_frontend_layers.py`
  → 26 passed. El test detectó un falso positivo (un ejemplo de código escapado en la
  página), y se corrigió para mirar solo etiquetas reales.
- `scripts/validate_specs.py` y `scripts/check_design_tokens.py` → OK.

### Definition of Done

- [x] La página se ve completa en la web de docs y con doble clic.
- [x] Un test falla si la copia de tokens se desfasa.
- [x] Enlazada desde la navegación de docs, la guía, el README raíz y `frontend/ds/README.md`.
- [x] Sin secretos en el diff.
