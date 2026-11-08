# Tokens

El sistema de tokens de Alexandria Magazine sigue la arquitectura de **tres capas** de SLDS2: Primitivo → Escala/Alias → Semántico. Esta separación permite theming sin reescribir estilos de componentes.

---

## Arquitectura de tres capas

```
PRIMITIVO                  ESCALA / ALIAS              SEMÁNTICO (usa estos)
──────────────────────────────────────────────────────────────────────────────
--blue-60: #0176d3         --text-2xl: 1.5rem          --brand
--neutral-10: #f4f6f9      --space-lg: 1.5rem          --bg-surface
--ink-100: #0b1b33         --radius-md: 0.5rem         --text-heading
--violet-60: #6b4fe3       --shadow-2: …               --border-default
--green-70: #1f6135        --dur-base: 200ms           --success
```

### Capa 1 — Primitivos

Los valores brutos de la paleta. Nunca los referencias directamente en componentes UI. Existen para que la capa semántica y los temas puedan apuntar a ellos.

**Grupos de primitivos:**
- `--blue-05` → `--blue-95` — Ramp Alexandria Blue
- `--ink-100`, `--ink-90`, `--ink-80` — Navy editorial
- `--neutral-00` → `--neutral-90` — Cloud ramp SLDS
- `--violet-05`, `--violet-40`, `--violet-60`, `--violet-70` — Accent violeta
- `--agent-research/write/review/format/publish` — Cinco agentes
- `--green-*`, `--amber-*`, `--red-*`, `--teal-*` — Feedback hues

### Capa 2 — Escala / Alias

Escalas compartidas entre temas. No cambian en dark mode.

| Grupo | Tokens |
|---|---|
| Tipografía | `--text-2xs` … `--text-6xl`, `--weight-*`, `--leading-*`, `--tracking-*`, `--measure` |
| Espaciado | `--space-3xs` … `--space-4xl` |
| Radius | `--radius-sm` … `--radius-circle` |
| Motion | `--dur-fast/base/slow`, `--ease-standard/out` |
| Layout | `--sidebar-w`, `--topbar-h` |

### Capa 3 — Semánticos

Los tokens con los que construyes UI. Solo estos cambian entre temas. Si usas `var(--bg-surface)` en un componente, ese componente soporta dark mode automáticamente.

---

## Referencia completa de grupos semánticos

| Grupo | Tokens | Descripción |
|---|---|---|
| **Marca** | `--brand`, `--brand-hover`, `--brand-active`, `--brand-tint`, `--brand-on` | Azul de acción principal |
| **Accent IA** | `--accent`, `--accent-tint` | Violeta para momentos de IA — uso restringido |
| **Superficies** | `--bg-canvas`, `--bg-surface`, `--bg-raised`, `--bg-sunken`, `--bg-inset`, `--bg-hover`, `--bg-active`, `--bg-shell` | Jerarquía de superficies |
| **Texto** | `--text-heading`, `--text-primary`, `--text-body`, `--text-secondary`, `--text-muted`, `--text-link`, `--text-on-brand`, `--text-inverse` | Jerarquía tipográfica |
| **Bordes** | `--border-subtle`, `--border-default`, `--border-strong`, `--border-control`, `--border-brand`, `--border-focus` | Separadores y contorno de controles |
| **Status feedback** | `--success`, `--success-bg`, `--warning`, `--warning-bg`, `--error`, `--error-bg`, `--info`, `--info-bg` | Feedback de estado |
| **Estado editorial** | `--status-draft`, `--status-review`, `--status-approved`, `--status-published`, `--status-rejected` | Ciclo de vida del artículo |
| **Elevation** | `--shadow-1`, `--shadow-2`, `--shadow-3`, `--shadow-4`, `--shadow-brand`, `--focus-ring`, `--focus-ring-accent` | Capas de profundidad |

---

## Cómo funciona el theming

Solo los tokens semánticos se redefinen en `[data-theme="dark"]`. Los primitivos y las escalas son idénticos en ambos temas.

```css
/* Componente que soporta ambos temas sin modificación */
.card {
  background: var(--bg-surface);          /* blanco en light, #111C2F en dark */
  border: 1px solid var(--border-default); /* #E0E5EE en light, rgba(255,255,255,0.11) en dark */
  color: var(--text-body);                /* #2E3A4D en light, #D2DCEA en dark */
}
```

### Activar el tema oscuro

```html
<!-- Documento completo -->
<html data-theme="dark">

<!-- Una sección -->
<section data-theme="dark">…</section>

<!-- Clase alternativa -->
<div class="dark">…</div>
```

---

## Cuándo usar cada capa

| Situación | Usa | Ejemplo |
|---|---|---|
| Componente UI de producto | **Semántico** | `var(--brand)`, `var(--bg-surface)` |
| Variante de color de agente | **Primitivo de agente** | `var(--agent-research)` |
| Valor de tamaño/espaciado | **Escala** | `var(--space-lg)`, `var(--radius-md)` |
| Tint de estado en badge | **Semántico** | `var(--success-bg)` + `var(--success)` |
| Apuntar desde un semántico | **Primitivo** | `--brand: var(--blue-60)` |
| Hardcodear hex | **Nunca** | — |

---

## Jerarquía de superficies

```
Canvas (#F4F6F9)           ← bg-canvas: fondo de toda la app
  └── Surface (#FFFFFF)    ← bg-surface: cards, paneles, sidebar
        └── Raised (#FFFFFF) ← bg-raised: tooltips, dropdowns
              └── Inset (#EEF1F6) ← bg-inset: áreas hundidas, code
```

No apilar más de dos pasos de elevación. Card sobre canvas = shadow-1; dropdown sobre card = shadow-3.

---

## Formato W3C DTCG

Los tokens también están disponibles en formato W3C Design Token Community Group en `tokens.dtcg.json`, para importar en herramientas de diseño (Figma Variables, Style Dictionary, Tokens Studio).

```json
{
  "color": {
    "semantic": {
      "brand": {
        "default": {
          "$value": "#0176d3",
          "$type": "color",
          "$description": "Primary brand action color — Alexandria Blue"
        }
      }
    }
  }
}
```
