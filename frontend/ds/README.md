# AlejandrIA Magazine — Design System

> *Where rigorous science meets calm, modern publishing.*

**AlejandrIA Magazine** (AlejandrIA Magazine) is an agentic editorial platform for
researchers and editors: a personal workspace where authors design multi-agent AI
flows (the **Flow Designer**) to research, draft, review, format, and publish
technical and scientific articles, with a controlled `draft → in_review → approved →
published` lifecycle and human-in-the-loop approval. The backend orchestrates a graph
of agents (LangGraph) with private RAG (Qdrant + Ollama); the frontend is React + Vite.

This design system reframes the product's visual language on the foundations of
**Salesforce Lightning Design System 2 (SLDS2)** — clean cloud neutrals, a confident
brand blue, systematic spacing/radius tokens — pushed toward a **more modern,
content-publishing aesthetic**. It adds two things the product needs but a generic UI
kit doesn't: a **Content System** for authoring technical & scientific long-form, and a
**reading layer** for technology readers consuming published work.

---

## Sources (for whoever builds on this)

These were the inputs used to construct this system. You may not have access; they are
recorded so you can explore further and improve fidelity.

| Source | Location | What it gave us |
|---|---|---|
| **AlejandrIA codebase** | `alejandria-magazine/` (local mount) | Product domain, page structure, the existing `index.css` token set, agent metadata, editorial workflow |
| ↳ key files | `frontend/src/index.css`, `pages/*.jsx`, `components/flow/AgentNode.jsx`, `DESIGN.md`, `README.md` | Foundations & component behaviour |
| **Salesforce Lightning Design System** | https://github.com/salesforce-ux/design-system | Token *structure* + values: `design-tokens/aliases/{colors,spacing,font-size,border-radius,font-family}.yml`. Explore this repo to deepen any SLDS-aligned work. |
| **SLDS reference** | https://www.lightningdesignsystem.com | Live component patterns & SLDS2 guidance |

> ⚠️ The original product ships a **dark** theme (purple `#7c3aed` + cyan `#06b6d4`).
> Per the brief ("estilo más moderno y orientado a la creación y publicación de
> contenido", based on SLDS2) this system **pivots to a light, editorial SLDS-blue
> direction**. The original brand violet is retained as a *sparing intelligence accent*
> for AI/agent moments, and the five agent hues carry over. **If you want to keep the
> dark theme instead, flag it** — see the caveats at the end.

---

## Content fundamentals — how AlejandrIA writes

The product and its content are **bilingual, Spanish-first**. Product chrome (nav,
buttons, toasts, empty states) is written in **Spanish**; scientific content itself is
authored in whatever language the researcher works in (often English). When in doubt,
follow the codebase: UI copy is Spanish.

**Voice & tone**
- **Precise, calm, and credible.** This is a tool for scientists — copy is direct and
  unembellished. No hype, no exclamation marks in product UI. "Flujo guardado", not
  "¡Tu flujo se guardó con éxito! 🎉".
- **Second person, informal "tú"** for the user: *"Diseña tu pipeline"*, *"Arrastra
  agentes…"*, *"¿No tienes cuenta?"*. Warm but not chatty.
- **Imperatives for actions**: *Guardar, Ejecutar, Aprobar, Rechazar, Asignar revisor*.
  Short verb-first button labels.
- **Domain vocabulary is exact**: *artículo, borrador, revisión, pipeline, flujo,
  agente, formato (APA/IEEE/Vancouver), score de aprobación, RAG*. Don't soften
  technical terms.
- **Casing**: Sentence case for headings and buttons (*"Iniciar sesión"*,
  *"Ejecutar pipeline"*). UPPERCASE only for small eyebrows/overlines and badge labels
  (with letter-spacing). Title Case is avoided.
- **Numbers & status** are factual: *"3 artículos en total"*, *"score 0–100"*,
  *"Mínimo 6 caracteres"*. State machine words are nouns: *Borrador, Pendiente,
  Aprobado, Publicado, Rechazado*.

**Emoji** — The *legacy* app used emoji liberally (📚 favicon; 🔍✍️👁️📄🚀 for agents;
section emoji in docs). The **modernized system removes emoji from the product UI** in
favour of Lucide line icons (see Iconography). Emoji may still appear in internal docs/
READMEs, never in shipped interface or published content.

**Content register (the reading layer)** — Published articles read like a serious
journal: an abstract, keywords, a clear section hierarchy, figures with numbered
captions ("Fig. 1"), tables, code, equations, callouts (Note / Methodology / Key
finding), and a formatted reference list (APA/IEEE/Vancouver). Tone there is the
author's scholarly voice — third person, measured, evidence-led.

*Examples lifted from the product:*
> "Plataforma inteligente para crear, revisar y publicar artículos científicos con
> agentes IA." · "Arrastra agentes desde el panel izquierdo al canvas para crear tu
> flujo de trabajo." · "Usa @ para mencionar al revisor." · "Se creará un nuevo
> artículo y se ejecutará el pipeline sobre él."

---

## Visual foundations

**Overall vibe** — Light, spacious, and editorial. A productivity app that feels like a
modern science publication's back office: white surfaces on a faint blue-grey canvas,
ink-navy type, one confident blue for action, restraint everywhere else. The reading
layer is generous and typographic — serif body at a comfortable measure, lots of air.

**Color** (see `colors_and_type.css`, `preview/colors-*`)
- **Primary — AlejandrIA Blue `#0176D3`** (SLDS2 brand blue). Hover `#005FB2`, active
  `#014486`. Used for primary actions, links, selection, focus rings. Tint `#EAF4FF`
  backs selected/active states.
- **Neutrals — SLDS "cloud" ramp.** Canvas `#F4F6F9` (Link Water), surfaces `#FFFFFF`,
  borders `#E0E5EE` (Steam) / `#D8DDE6` (Geyser). Text: headings `#0B1B33` (ink navy),
  body `#2E3A4D`, secondary `#5C6B7E`, muted `#657286`.
- **Intelligence accent — violet `#6B4FE3`** (continuity with the original brand). Used
  *sparingly*: "Ask AI" actions, generative states, the Redactor agent.
- **Agent palette**: Investigador `#0D9DDA`, Redactor `#6B4FE3`, Revisor `#C47D04`,
  Formateador `#2E844A`, Publicador `#CB4B3F`. Full value for the mark; the 05 tint
  backs chips & icon tiles.
- **Semantic**: success `#1F6135`, warning `#946004`, error `#BA0517`, info `#005FB2` —
  always paired with a pale tinted surface and deep-ink text.
- **Imagery vibe**: cool, clean, document/diagram-forward. No warm filters; cover
  imagery (when present) sits behind a subtle ink scrim. Use real images — never
  generate or hand-draw illustrations.

**Type** (see `preview/type-*`)
- **Source Serif 4** — editorial display & long-form reading body (the Content System).
- **Source Sans 3** — all product UI, labels, controls, sans body.
- **JetBrains Mono** — code, payloads, tokens, metadata.
- All three are open-source (OFL) and loaded from **Google Fonts via `@import`** at the
  top of `colors_and_type.css`. Scale follows SLDS rem font-size aliases
  (0.625 → 2.625rem) extended with a 56px editorial hero. UI body = 14px; reading
  body = 16px min at a `68ch` measure with 1.7 leading.

**Spacing & layout** — 4px base, SLDS rem aliases: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64.
App shell = fixed 248px sidebar + 56px top bar, white chrome on the cloud canvas;
content scrolls in the centre. Reading layer is a single centered column. Layouts are
calm and grid-aligned; generous whitespace over density.

**Radius** — SLDS2-rounded: `sm 4` · `md 8` · `lg 12` · `xl 16` · `pill 999`. Controls
and inputs use 8px; cards/panels 12px; modals 16px.

**Borders** — Hairline `1px` in `#E0E5EE` is the default separator. Inputs & secondary
buttons get a `1px` control border (`--border-control`, `#7B8CAA`); focus replaces it with the blue ring.
Color-coded left accents appear only on flow nodes / callouts, never as generic card
decoration.

**Elevation / shadows** — Soft, low, ink-tinted (`rgba(11,27,51,…)`):
`shadow-1` (rest/card hairline lift) → `shadow-2` (cards) → `shadow-3` (popovers/menus)
→ `shadow-4` (modals). `shadow-brand` is a blue glow reserved for the primary CTA. No
neon glows (a departure from the dark legacy theme).

**Animation** — Quick and unobtrusive. Durations 120 / 200 / 320ms on
`cubic-bezier(0.4,0,0.2,1)`. Fades + small (8–16px) upward slides for entrances;
spinners for loading; flow edges animate. **No bounces, no parallax.** Respect
`prefers-reduced-motion`.

**Hover / press states**
- *Buttons*: hover darkens the fill one step (or tints ghost); active darkens two and/or
  nudges `translateY(1px)`. Disabled = 45% opacity.
- *Cards / list rows*: hover raises border to `default`, adds `shadow-2`, optional
  `-1px` lift.
- *Nav items*: hover = `bg-hover`; active = blue tint fill + blue text + faint blue
  left border.
- *Focus*: a 2px `--border-focus` outline with 2px offset on keyboard focus; inputs add the 3px `--focus-ring`.

**Transparency & blur** — Used only for overlays: modal backdrop = `rgba(0,0,0,.45)`
with a light `blur(2px)`; sticky toolbars/headers may use `backdrop-filter: blur(12px)`
over a translucent white. Otherwise surfaces are solid.

**Cards** — White, `12px` radius, `1px #E0E5EE` border, `shadow-1` at rest → `shadow-2`
on hover. Padding `16–24px`. Article cards lead with a serif title; metadata row uses
sans + Lucide icons. No gradient fills, no colored left-border-only cards.

---

## Iconography

- **Lucide** is the icon system (the product already depends on `lucide-react`). Use it
  everywhere in UI kits and mocks.
  - **CDN**: `<script src="https://unpkg.com/lucide@0.544.0/dist/umd/lucide.min.js"></script>`
    then `lucide.createIcons()`; markup `<i data-lucide="search"></i>`. In React, use
    `lucide-react`.
  - **Style**: 1.5px stroke, rounded caps/joins, no fill. Sizes 14–18px inline UI,
    11–13px in badges, 24–28px in empty states. Icon color inherits text color
    (`currentColor`); tinted icon *tiles* use the 05 brand/agent tint as background.
  - **Common glyphs** (from the codebase): `book-open`, `git-branch`, `bot`, `zap`,
    `shield`, `play`, `save`, `trash-2`, `plus`, `search`, `filter`, `arrow-left`,
    `check-circle`, `x-circle`, `clock`, `alert-circle`, `user-plus`, `file-text`,
    `settings`, `sparkles` (AI), `flask-conical` (methodology), `lightbulb` (finding).
- **Agent icons** replace the legacy emoji: Investigador `search`, Redactor `pen-line`,
  Revisor `eye`, Formateador `file-text`, Publicador `send` / `rocket`.
- **No emoji** in shipped UI or content. **No Unicode dingbats** as icons. Arrows in
  flows use Lucide `arrow-right`, not `→` glyphs (except in code/payload samples).
- **Logo**: `assets/logomark.svg` (pediment "A" monogram in a blue tile) and
  `assets/wordmark.svg` (mark + "Alexandria" serif + "MAGAZINE" eyebrow). The monogram
  reads as the classical façade of the Library of Alexandria. Min mark size 24px; keep
  ½-tile clear space. On dark/photo backgrounds use the white-on-blue tile.

---

## Index — what's in this system

| Path | What it is |
|---|---|
| `README.md` | This file — context, content & visual foundations, iconography, index |
| `colors_and_type.css` | **The token source of truth.** Primitive + semantic CSS vars, **light + dark themes**, dataviz palette, the `.prose` Content System, base element styles. Link this in every artifact. |
| `tokens.md` | Token architecture (primitive → alias → semantic), full token reference, and core design patterns |
| `ACCESSIBILITY.md` | **WCAG 2.1 AA** rules governing how the system's tokens & components combine (contrast, focus, targets, forms, semantics, motion) |
| `SKILL.md` | Agent-Skill entry point (Claude Code compatible) |
| `assets/` | `logomark.svg`, `wordmark.svg` |
| `preview/` | 30+ Design-System cards (foundations + components) shown in the DS tab |
| `ui_kits/studio/` | **Studio** UI kit — the authoring app (auth, Flow Designer, execution, articles, review). `index.html` is an interactive click-through. |
| `ui_kits/magazine/` | **Magazine** UI kit — the public reading layer (home grid + long-form reader). The Content System in action. |

**Theming:** every artifact supports **light & dark** — add `data-theme="dark"` (or
class `.dark`) to any ancestor and the semantic tokens flip. See `tokens.md`.

**Products / surfaces covered:** (1) **Studio** — the agentic authoring workspace;
(2) **Magazine** — the reader-facing publication. No slide template was provided, so no
sample slides are included.
