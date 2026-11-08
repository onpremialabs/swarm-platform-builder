# Accessibility Standards

Alexandria Magazine cumple **WCAG 2.1 Level AA** en toda la interfaz de producto y en la capa de lectura editorial. Estas normas son vinculantes para todo lo que se construya con este sistema.

---

## 1. Color y contraste

**Texto normal (< 24px o < 19px bold): mínimo 4.5:1**

| Par de colores | Ratio | Nivel |
|---|---|---|
| `--text-body` (#2E3A4D) sobre `--bg-surface` (#FFF) | 11.48:1 | AAA |
| `--text-heading` (#0B1B33) sobre `--bg-surface` (#FFF) | 17.23:1 | AAA |
| `--text-secondary` (#5C6B7E) sobre `--bg-surface` (#FFF) | 5.44:1 | AA |
| `--text-link` (#0176D3) sobre `--bg-surface` (#FFF) | 4.63:1 | AA |
| Blanco sobre `--brand` (#0176D3) | 4.63:1 | AA |

**Texto grande (≥ 24px o ≥ 19px bold): mínimo 3:1**

**UI no-texto (bordes, iconos, marks de chart): mínimo 3:1**
- `--border-control` (#7B8CAA) sobre blanco: 3.40:1 — contorno de inputs, botones secundarios y toggles
- `--border-strong` (#D8DDE6) sobre blanco: 1.36:1 — solo separadores decorativos, nunca el contorno de un control
- Los iconos Lucide heredan `currentColor` — siempre tiene contraste suficiente con el texto del contexto

**Nunca confiar solo en el color (WCAG 1.4.1).** Todo estado visual tiene además: etiqueta de texto + icono Lucide.

---

## 2. Focus y teclado

**Toda la interfaz es operable con teclado.**

- **Focus ring visible en todos los controles:** `--focus-ring` — anillo azul de 3px a 25% alpha
- **Nunca** `outline: none` sin reemplazo equivalente o visible
- **No suprimir** `:focus-visible` — los navegadores ya distinguen mouse/teclado
- **Orden lógico de tab:** sigue el orden del DOM y la lectura visual
- **Modales:** atrapan foco mientras están abiertos, lo devuelven al elemento trigger al cerrar, se cierran con `Esc`
- **Flow Designer:** las interacciones de drag tienen alternativa de teclado (menú contextual o atajos de teclado)

```css
/* Focus ring estándar — obligatorio en todos los controles */
:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

/* Controles IA — ring violeta */
.ai-control:focus-visible {
  box-shadow: var(--focus-ring-accent);
}
```

---

## 3. Targets táctiles

| Control | Tamaño mínimo | Nota |
|---|---|---|
| btn-primary / btn-secondary / btn-base | 40px alto | Padding estándar |
| btn-lg | 48px alto | CTA prominente |
| btn-sm | 32px alto + padding táctil | Compensar con espacio circundante a 44px |
| btn-icon toolbar | 34px (área táctil 44px) | Padding invisible de 5px |
| Input, select, textarea | 40px alto mínimo | |
| Nav items | 40px alto | padding: 8px 16px |
| Checkbox / radio | 20px mark + area de 44px | |

---

## 4. Texto y contenido

- Texto en **rem** — escala al 200% de zoom sin pérdida de contenido
- **No fijar line-height con `!important`** — respetar overrides del usuario (WCAG 1.4.12)
- `--measure: 68ch` — límite de línea para lectura `.prose` (WCAG 1.4.10 reflow)
- `lang="es"` en el root del documento; cambiar `lang` en secciones en otro idioma
- **Texto de lectura mínimo:** `--text-md` (16px) en `.prose`, `--text-base` (14px) en UI

---

## 5. Formularios y feedback

- **`<label>` visible y persistente** en cada `<input>` — nunca placeholder como única etiqueta
- Errores en **texto + icono**, programáticamente asociados:
  ```html
  <input aria-invalid="true" aria-describedby="error-id" />
  <div id="error-id" role="alert">Mensaje de error</div>
  ```
- **Mensajes de estado** (toasts, notificaciones) en live regions:
  - `role="status"` + `aria-live="polite"` para success/info
  - `role="alert"` + `aria-live="assertive"` para errores

---

## 6. Estructura y semántica

- **`<button>` nativo** para acciones — nunca `<div onClick>`
- **`<nav>`, `<main>`, `<header>`, `<footer>`** como landmarks
- **Un solo `<h1>`** por vista; no saltar niveles de heading
- **Imagen no decorativa:** `alt` descriptivo
- **SVG decorativo / icono:** `aria-hidden="true"` o `alt=""`
- **Icon-only button:** `aria-label` obligatorio
- **Custom controls:** `role` correcto + estado ARIA:
  - Toggle: `role="switch"` + `aria-checked`
  - Dropdown: `aria-expanded` + `aria-haspopup`
  - Tabs: `role="tablist"` / `role="tab"` / `role="tabpanel"` + `aria-selected`

---

## 7. Motion

- **No más de 3 flashes/segundo** en ningún elemento
- Animaciones de nodos del Flow Designer pausan bajo `prefers-reduced-motion: reduce`
- Spinners de agente pausan bajo motion reducida
- Nada esencial se comunica solo mediante animación

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## Quick checklist por pantalla

- [ ] Contraste AA en todo texto, iconos, bordes, marks de chart
- [ ] Estado/charts legibles sin color (etiqueta + icono)
- [ ] Teclado operativo, focus ring visible, orden lógico, Esc cierra overlays
- [ ] Labels + errores asociados + live-region feedback
- [ ] Headings ordenados, landmarks presentes, icon buttons con `aria-label`
- [ ] 200% zoom refleja sin pérdida; motion reducida respetada; `lang` correcto
