# Tarea #507 — Publicar la referencia del sistema de diseño en GitHub Pages

## 2026-11-11 — Éxito ✅ (pendiente de activar Pages)

- **Rama:** `chore/ds-github-pages`
- **PR:** la de esta rama → `develop` (`Closes #507`)
- **Spec:** SPEC-003 (E7), sin cambios en sus criterios.

### Por qué

Desde #505, la referencia visual del sistema de diseño vive en `docs/public/design-system/`
y se ve completa, pero solo si se clona el repo o se levanta la web de docs. No había una
URL permanente que se pudiera pasar a cualquiera.

### Qué se hizo y dónde

- **`.github/workflows/ds-pages.yml`** (nuevo). Se dispara con cada push a `develop` que toque
  `docs/public/design-system/**`, los tokens o logos de `frontend/ds/`, el script de
  sincronización o el propio workflow, y también a mano (`workflow_dispatch`).
  - **build**: ejecuta `sync_design_system_docs.py --check`, para que no se publique una
    página con tokens desfasados; monta `_site/design-system/` copiando **solo** esa
    carpeta, con un `index.html` raíz que redirige a `design-system/`; y lo sube con
    `actions/upload-pages-artifact@v3`.
  - **deploy**: `actions/deploy-pages@v4` al entorno `github-pages`.
  - **Permisos mínimos**: `contents: read` global; `pages: write` e `id-token: write`
    solo en `deploy`. Sin secretos.
  - **`concurrency`** sin cancelar, para que un despliegue a medias no deje el sitio roto.
- **`docs/guide/design-system.md`, `README.md`**: la URL pública.
- **`CLAUDE.md`**: el workflow aparece en la sección de CI, aclarando que **no es un gate**.

URL resultante: <https://onpremialabs.github.io/swarm-platform-builder/design-system/>

### Qué NO se hizo

- **No se activó Pages.** Es un ajuste del repositorio que necesita permisos de admin:
  **Settings → Pages → Source: GitHub Actions**. Hasta que se haga, el job `deploy`
  fallará.
- No se publicó el resto de la web de docs: su `vitepress build` ya fallaba en
  `develop` por `docs/specs/TEMPLATE.md`.

### Verificación

- Se parseó el YAML con PyYAML: disparadores `push` y `workflow_dispatch`, 5 rutas, y
  `deploy` con `needs: build` y solo sus dos permisos.
- Se ejecutó en local el script del paso «Montar el sitio», tal como sale del YAML. Genera
  `_site/index.html` y `_site/design-system/{index.html, colors_and_type.css, assets/*}`.
- Se sirvió `_site` bajo el prefijo `/swarm-platform-builder/`, como hará Pages. La raíz
  redirige a `/design-system/`, la ruta sin barra final resuelve, y la página carga
  tokens (`--brand` `#0176d3`), logo y los 116 iconos, con contraste 11.48:1.
- **No se ha ejecutado en GitHub Actions**: el primer despliegue real será tras el merge.

### Definition of Done

- [x] Workflow que publica solo `docs/public/design-system/`.
- [x] No publica si la copia de tokens va atrás.
- [x] URL documentada en la guía, el README y CLAUDE.md.
- [ ] Pages activado en el repo (manual, admin).
- [x] Sin secretos en el diff.
