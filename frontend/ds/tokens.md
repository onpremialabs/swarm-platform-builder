# Tokens & Design Patterns — AlejandrIA Magazine

The single source of truth is **`colors_and_type.css`**. Everything below documents how
those CSS custom properties are organised and how to use them. The structure mirrors
**Salesforce Lightning Design System 2** (primitive → alias → semantic), reframed for a
content-creation & publishing product.

## Token architecture (three tiers)

```
PRIMITIVE            ALIAS / SCALE              SEMANTIC (use these)
--blue-60: #0176d3   --text-2xl, --space-lg     --brand, --bg-surface,
--neutral-10         --radius-md, --shadow-2     --text-heading, --border-default
--ink-100            (font/space/radius scales)  --success, --status-published
```

- **Primitives** — raw palette stops (`--blue-*`, `--neutral-*`, `--ink-*`, `--violet-*`,
  agent + status hues). Never reference these directly in product UI; they exist so the
  semantic layer and themes can point at them.
- **Scales / aliases** — type (`--text-*`, `--weight-*`, `--leading-*`, `--tracking-*`),
  spacing (`--space-*`, 4px base), radius (`--radius-*`), elevation (`--shadow-*`),
  motion (`--dur-*`, `--ease-*`). Shared across **both** themes.
- **Semantic** — the layer you build with: `--brand`, `--bg-canvas`, `--bg-surface`,
  `--text-heading/primary/body/secondary/muted`, `--border-subtle/default/strong`,
  `--success/warning/error/info` (+ `-bg` tints), and the editorial
  `--status-draft/review/approved/published/rejected`.

### Theming
Only the **semantic** tier is overridden under `[data-theme="dark"]` / `.dark`.
Components that reference semantic vars switch automatically — no per-component dark CSS.

```html
<html data-theme="dark">          <!-- whole document -->
<section class="dark">…</section>  <!-- a single subtree -->
```

## Token groups & reference

| Group | Prefix | Notes |
|---|---|---|
| Brand / accent | `--brand`, `--accent`, `--brand-tint` | Blue `#0176D3`; accent violet for AI moments only |
| Surfaces | `--bg-canvas/surface/raised/sunken/inset/shell` | Canvas = faint blue-grey; surfaces = white (light) |
| Text | `--text-heading/primary/body/secondary/muted/link` | Ink navy heads, never pure black |
| Borders | `--border-subtle/default/strong/control/brand/focus` | Hairline 1px default; `control` outlines inputs, secondary buttons and toggles (3:1) |
| Status | `--success/warning/error/info` + `-bg` | Always value + pale tint pair |
| Editorial status | `--status-*` | draft/review/approved/published/rejected |
| Agents | `--agent-research/write/review/format/publish` | One hue per editorial agent |
| Type | `--font-serif/sans/mono`, `--text-*`, `--weight-*`, `--leading-*`, `--tracking-*`, `--measure` | Serif=content, Sans=UI, Mono=code |
| Spacing | `--space-3xs … --space-4xl` | 4px base, SLDS rem aliases |
| Radius | `--radius-sm/md/lg/xl/pill/circle` | Controls 8, cards 12, modals 16 |
| Elevation | `--shadow-1…4`, `--shadow-brand`, `--focus-ring` | Soft, ink-tinted; brand glow on CTA only |
| Motion | `--dur-fast/base/slow`, `--ease-standard/out` | 120/200/320ms |
| Dataviz | `--viz-1…8`, `--viz-seq-*`, `--viz-div-*`, `--viz-positive/negative`, `--viz-grid/axis/track` | Categorical ordered for adjacent contrast; CB-aware |

## Core design patterns

**Surface hierarchy** — `bg-canvas` (app) → `bg-surface` card (1px `border-default`,
`radius-lg`, `shadow-1`) → nested content uses `bg-sunken`/`bg-inset`. Raise to
`shadow-2` + `border` on hover. Don't stack more than two elevation steps.

**Spacing rhythm** — Compose layouts from the 4px scale only. Card padding `lg` (24) or
`md` (16); section gaps `lg`/`xl`; inline control gaps `xs`/`sm`. Reading column is a
single `--measure` (68ch) centered block.

**Actions** — One primary (`btn-primary`, brand fill + `shadow-brand`) per view.
Secondary = white + `border-control`. Ghost for tertiary. `btn-accent` (violet) is
reserved for AI/generative actions. Destructive = `btn-danger` (red tint → solid on
hover). Hover darkens one step; active darkens two + `translateY(1px)`.

**Status as a system** — Every article state maps to a `--status-*` colour and a `badge`
(pale tint bg + deep-ink text + Lucide glyph). Never communicate state by colour alone —
always pair with the label and icon (see ACCESSIBILITY.md).

**Two registers** — Product UI uses `--font-sans` and the `.ax`/UI classes; published
content uses `--font-serif` via `.prose`. Keep them visually distinct: chrome is compact
and sans; content is airy and serif at a generous measure.

**Iconography** — Lucide, 1.5px stroke, `currentColor`. Tinted icon *tiles* use the 05
tint as background with the full hue as the glyph. No emoji in product UI.

**Motion** — Entrances = fade + 8–16px rise on `--ease-out`, `--dur-base`. Flow edges
animate (marching ants); steps spin while running. No bounce/parallax. Honour
`prefers-reduced-motion`.

See **`colors_and_type.css`** for the authoritative values and the `.prose` content
system, and **`ACCESSIBILITY.md`** for WCAG 2.1 rules governing how these tokens combine.
