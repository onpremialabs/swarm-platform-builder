# Accessibility — WCAG 2.1 AA (AlejandrIA Magazine)

AlejandrIA targets **WCAG 2.1 Level AA** across product UI and the published reading
layer, with AAA where it's cheap (body text contrast, reading measure). These rules are
binding for anything built with this design system.

## 1 · Colour & contrast (1.4.3, 1.4.11, 1.4.1)
- **Text contrast** ≥ **4.5:1** (normal) / **3:1** (large ≥ 24px or 19px bold). The
  semantic text tokens are pre-checked against their intended surfaces — keep the
  documented pairings (`--text-body` on `--bg-surface` = 11.48:1 AAA; `--brand` link on
  white = 4.63:1 AA; `#fff` on `--brand` = 4.63:1 AA).
- **Non-text contrast** ≥ **3:1** for UI component boundaries, icons, focus rings, chart
  marks, and form borders. Interactive borders use `--border-control` (3.40:1 on white);
  `--border-strong` (1.36:1) is for decorative separators only.
- **Never rely on colour alone** (1.4.1). Article status = colour **+ label + Lucide
  icon**. Chart series carry labels/legend; the categorical palette is ordered for
  adjacent contrast and is colour-blind aware, but always pair with direct labels.
- **Dark theme** values are independently lifted to keep AA on dark ink — don't reuse
  light-theme hand-picked hex on dark surfaces; use the semantic tokens.

## 2 · Focus & keyboard (2.1.1, 2.4.7, 2.4.3)
- Everything operable is reachable and operable by **keyboard**; no traps.
- **Visible focus**: a 2px `--border-focus` outline with 2px offset on every focusable
  control; inputs add the 3px `--focus-ring`. Never `outline: none` without an equivalent. Don't suppress `:focus-visible`.
- **Logical tab order** follows reading/DOM order. Modals trap focus while open, restore
  it on close, and close on `Esc`.
- Drag interactions (Flow Designer node placement, palette drag) must have a
  keyboard/menu alternative (2.1.1, 2.5.7).

## 3 · Targets & spacing (2.5.5 / 2.5.8)
- Minimum hit target **44×44px** for primary touch controls; **24×24px** floor (AA 2.5.8)
  for dense toolbar/icon buttons, with adequate spacing. Studio `icon-btn` = 34px;
  `btn-sm` keeps a 44px-equivalent tap area via padding.

## 4 · Text & content (1.4.4, 1.4.12, 1.4.10, 3.1)
- Text resizes to **200%** without loss of content; layouts reflow (no fixed-px text
  walls). Reading body is `rem`-based; `--measure` caps line length at 68ch.
- Respect user **line-height/spacing** overrides (1.4.12) — don't lock them with
  `!important`.
- Set `lang` correctly: product chrome is `lang="es"`; switch `lang` on content authored
  in another language so screen readers pronounce it right (3.1.1 / 3.1.2).

## 5 · Forms & feedback (3.3.1, 3.3.2, 4.1.3, 1.3.1)
- Every input has a **persistent visible `<label>`** (not placeholder-only). Placeholders
  are hints, never labels.
- **Errors** are identified in text + icon and programmatically associated
  (`aria-describedby`, `aria-invalid`) — not colour-only.
- **Status messages** (toasts, "Flujo guardado", validation) use an appropriate live
  region (`role="status"` / `aria-live="polite"`; `role="alert"` for errors) so they're
  announced without moving focus (4.1.3).

## 6 · Structure & semantics (1.3.1, 2.4.6, 4.1.2)
- Use **native semantic elements** (`<button>`, `<nav>`, `<main>`, headings in order).
  Custom controls get correct `role` + state (`aria-pressed`, `aria-checked`,
  `aria-expanded`, `aria-selected`).
- One `<h1>` per view; don't skip heading levels. The `.prose` reading layer must keep a
  correct article heading hierarchy (h1 title → h2 sections → h3 subsections).
- All non-decorative images need `alt`; decorative SVG/icons get `aria-hidden="true"` or
  empty `alt`. Icon-only buttons need an `aria-label`.

## 7 · Motion & media (2.3.1, 2.2.2, 1.4.2)
- No content flashes more than **3×/second**. Marching-ant flow edges and step spinners
  are decorative and must pause under `prefers-reduced-motion: reduce`.
- Auto-updating content (execution log) can be paused; nothing essential is conveyed by
  animation alone.

## Quick checklist (per screen)
- [ ] Contrast AA on all text, icons, borders, chart marks
- [ ] Status/charts readable without colour
- [ ] Keyboard-operable, visible focus, logical order, Esc closes overlays
- [ ] Labels + associated errors + live-region feedback
- [ ] Headings ordered; landmarks present; icon buttons labelled
- [ ] 200% zoom reflows; reduced-motion respected; correct `lang`
