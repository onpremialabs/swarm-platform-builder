# Sistema de diseño

El lenguaje visual compartido de la plataforma: el **Studio** (el builder donde se
diseñan, ejecutan y revisan flujos de agentes) y la **Magazine** (la capa de lectura
donde se publica el resultado).

<a href="/design-system/index.html" target="_self"><strong>Abrir la referencia visual del sistema de diseño →</strong></a>

La referencia está organizada en 21 secciones: principios, arquitectura de tokens,
color, tipografía, espaciado, radio, elevación, movimiento, iconografía, botones,
formularios, estado y feedback, cards y modales, Flow Designer y ejecución, Content
System (`.prose`), visualización de datos, voz y tono, accesibilidad, tema claro/oscuro
y uso. Tiene un selector de tema, y los valores y ratios de contraste se calculan en
vivo desde los tokens.

## Cómo abrirla

| Dónde | Cómo |
|---|---|
| **Web pública** | <https://onpremialabs.github.io/swarm-platform-builder/design-system/>. La publica `.github/workflows/ds-pages.yml` en cada cambio que llega a `develop`. |
| Web de documentación | `cd docs && npm run dev` → <http://localhost:5174/design-system/index.html> |
| Sin servidor | Abre `docs/public/design-system/index.html` con doble clic. Carga el CSS y los logos de su carpeta, así que se ve completa. Las fuentes y los iconos necesitan conexión. |
| En otro sitio | Copia la carpeta `docs/public/design-system/` entera: la página, `colors_and_type.css` y `assets/`. |

## De dónde salen los valores

La fuente de verdad **no** está en `docs/`: es
[`frontend/ds/colors_and_type.css`](https://github.com/onpremialabs/swarm-platform-builder/blob/develop/frontend/ds/colors_and_type.css),
el archivo que importa la aplicación. Esta página usa una **copia idéntica** que deja
junto a ella:

```bash
python scripts/sync_design_system_docs.py          # copia tokens y logos desde frontend/ds/
python scripts/sync_design_system_docs.py --check  # comprueba que la copia está al día
```

Ejecuta el script cada vez que cambies un token o un logo en `frontend/ds/`. Si no, falla
`backend/tests/test_design_system_docs.py`. El mismo test comprueba que la página no
redefine ningún token y que todo lo que carga en local tiene su copia.

## Resto del sistema de diseño

Viven en `frontend/ds/`, junto a los tokens:

- `README.md`: fundamentos visuales, voz e iconografía.
- `tokens.md`: arquitectura de tokens y patrones.
- `ACCESSIBILITY.md`: reglas WCAG 2.1 AA.
- `preview/` y `ui_kits/`: fichas por componente y prototipos de Studio y Magazine.
