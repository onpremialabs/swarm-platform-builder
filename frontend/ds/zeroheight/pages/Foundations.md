# Foundations

Los fundamentos visuales de Alexandria Magazine son el vocabulario compartido del que parten todos los componentes y patrones. Están definidos exclusivamente en `colors_and_type.css` como custom properties CSS — la fuente única de verdad.

---

## Los seis pilares

### Color
Una paleta editorial construida sobre SLDS2: Alexandria Blue `#0176D3` como color de acción confiado, cloud neutrals para superficies limpias, violet `#6B4FE3` restringido a momentos IA, y una paleta de cinco agentes con identidad propia. El color siempre comunica función, nunca decoración.

→ Ver página **Color** para la paleta completa y tablas de tokens.

### Tipografía
Tres tipografías open-source, dos registros: **Source Sans 3** para el chrome de producto (14px, compacto, funcional) y **Source Serif 4** para el contenido editorial (16px, 68ch, 1.7 leading). **JetBrains Mono** para código y metadatos. La distinción de registro es deliberada y vinculante.

→ Ver página **Typography** para la escala completa y reglas de uso.

### Espaciado
Base de 4px, escala rem alineada a SLDS: de `--space-3xs` (2px) a `--space-4xl` (80px). Todos los márgenes, paddings y gaps se componen de estos tokens. Sin valores arbitrarios.

→ Ver página **Spacing** para la escala y patrones de layout.

### Radius
SLDS2 — ligeramente más redondeado que SLDS1. Controles e inputs: `--radius-md` (8px). Cards y paneles: `--radius-lg` (12px). Modales: `--radius-xl` (16px). Badges y chips: `--radius-pill` (999px).

| Token | Valor | Uso |
|---|---|---|
| `--radius-sm` | 4px | Badges, código inline, chips pequeños |
| `--radius-md` | 8px | Inputs, botones, controles interactivos |
| `--radius-lg` | 12px | Cards, panels, dropdowns |
| `--radius-xl` | 16px | Modales, drawers grandes |
| `--radius-pill` | 999px | Badges de estado, tag chips |
| `--radius-circle` | 50% | Avatares, icon tiles circulares |

### Elevation

Sombras suaves, ink-tinted (`rgba(11,27,51,…)`). Sin neón glows — el sistema parte del legado dark para llegar a un editorial claro.

| Token | Uso |
|---|---|
| `--shadow-1` | Cards en reposo, hairline lift |
| `--shadow-2` | Cards en hover, dropdowns |
| `--shadow-3` | Popovers, menus contextuales, tooltips |
| `--shadow-4` | Modales, drawers |
| `--shadow-brand` | Glow azul — exclusivo del btn-primary |
| `--focus-ring` | Anillo de foco 3px azul — todos los controles |
| `--focus-ring-accent` | Anillo de foco 3px violeta — controles IA |

### Motion

Rápido y utilitario. Duración 120–320ms en `cubic-bezier(0.4,0,0.2,1)`. Fades y pequeñas subidas (8–16px) para entradas. Sin bounces, sin parallax. Pausar bajo `prefers-reduced-motion`.

| Token | Valor | Uso |
|---|---|---|
| `--dur-fast` | 120ms | Micro-interacciones, hover reveals |
| `--dur-base` | 200ms | Transiciones estándar — panel open, fade in |
| `--dur-slow` | 320ms | Transiciones de página, modal entrance |
| `--ease-standard` | cubic-bezier(0.4,0,0.2,1) | Mayoría de transiciones |
| `--ease-out` | cubic-bezier(0,0,0.2,1) | Animaciones de entrada |

```css
/* Entrada estándar — fade + rise */
@keyframes fade-up {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

.component-enter {
  animation: fade-up var(--dur-base) var(--ease-out);
}

/* Respetar prefers-reduced-motion */
@media (prefers-reduced-motion: reduce) {
  .component-enter { animation: none; }
}
```

---

## Bordes

Hairline `1px` en `--border-default` (#E0E5EE) es el separador estándar. Inputs y botones secundarios usan `--border-control` (#7B8CAA). Focus sustituye el borde por el anillo azul. Los acentos de color izquierdo aparecen solo en nodos del Flow Designer y callouts de contenido — nunca como decoración genérica de card.

```css
/* Card estándar */
.card {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-1);
}

.card:hover {
  border-color: var(--border-strong);
  box-shadow: var(--shadow-2);
}
```

---

## Transparencia y blur

Solo en overlays:
- **Modal backdrop:** `rgba(0,0,0,0.45)` con `blur(2px)`
- **Toolbars sticky:** `backdrop-filter: blur(12px)` sobre blanco translúcido
- Superficies normales son siempre sólidas — sin glassmorphism en la UI funcional
