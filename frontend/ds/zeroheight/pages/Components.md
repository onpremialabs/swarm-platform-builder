# Components

Los componentes de Alexandria Magazine son bloques reutilizables construidos sobre los fundamentos del sistema. Cada componente referencia exclusivamente variables semánticas CSS para garantizar compatibilidad con light y dark mode automáticamente.

---

## Inventario de componentes

### Button
4 variantes (primary, secondary, ghost, danger) + btn-accent para acciones IA. 3 tamaños (sm, base, lg) + icon-only. → Ver página **Button**.

### Badge / Chip
Etiquetas de estado compactas. Siempre: tint de color como fondo + full value como texto + icono Lucide. Radius pill. Usado para estados de artículo (Borrador, Aprobado, etc.) y etiquetas de agente.

```css
.badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2xs);
  padding: var(--space-3xs) var(--space-xs);
  border-radius: var(--radius-pill);
  font-size: var(--text-2xs);
  font-weight: var(--weight-semibold);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
}

.badge-success {
  background: var(--success-bg);
  color: var(--success);
}

.badge-draft {
  background: var(--bg-inset);
  color: var(--status-draft);
}
```

### Input / Field
Label persistente visible + input con border `--border-control` + estado de error con border `--error` + mensaje de error debajo. Nunca placeholder-only como label.

```css
.input {
  border: 1px solid var(--border-control);
  border-radius: var(--radius-md);
  padding: var(--space-xs) var(--space-sm);
  font-family: var(--font-sans);
  font-size: var(--text-base);
  background: var(--bg-surface);
  color: var(--text-body);
  width: 100%;
  transition: border-color var(--dur-fast) var(--ease-standard),
              box-shadow var(--dur-fast) var(--ease-standard);
}

.input:focus {
  outline: none;
  border-color: var(--border-focus);
  box-shadow: var(--focus-ring);
}

.input[aria-invalid="true"] {
  border-color: var(--error);
}
```

### Card
Blanca, radius 12px, border `--border-default`, shadow-1 en reposo → shadow-2 en hover. Padding 24px (16px en compacta). Las cards de artículo tienen título en serif como protagonista.

### Modal
Overlay `rgba(0,0,0,0.45)` con blur(2px). Surface blanca, radius 16px, shadow-4. Atrapa foco al abrirse, lo devuelve al cierre, cierra con Esc.

### Avatar
Circular, radio 50%. Iniciales en `--font-sans` semibold cuando no hay imagen. Fondo `--brand-tint` con texto `--brand` para avatares por defecto.

### Spinner / Loader
Spinner circular animado en `--brand`. Duración `--dur-slow` (320ms), ease-linear. Pausa con `prefers-reduced-motion`.

```css
.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border-default);
  border-top-color: var(--brand);
  border-radius: var(--radius-circle);
  animation: spin var(--dur-slow) linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

@media (prefers-reduced-motion: reduce) {
  .spinner { animation: none; border-top-color: var(--brand); }
}
```

### Tabs
Tabs horizontales: borde inferior `--border-default`; tab activo = borde inferior 2px `--brand` + texto `--brand`. Transition `--dur-fast`.

### Toggle / Switch
Toggle binario. Off = fondo `--neutral-30` con borde `--border-control`. On = `--brand`. Handle blanco. 44px de target mínimo.

### Divider
`<hr>` con `border-top: 1px solid var(--border-default)`. Sin margin propio — controlado por el contexto.

### Empty State
→ Ver página **Empty states**.

---

## Principios de composición

### Jerarquía de contenido en cards
```
Card
├── Header (eyebrow opcional, título, badge de estado)
│   └── Acciones rápidas (icon buttons)
├── Body (metadatos, resumen, content)
└── Footer (acciones principales, timestamps)
```

### Espaciado en componentes

- Gap icono → texto: `--space-xs` (8px)
- Padding interno de control: `--space-xs` (8px) vertical, `--space-sm` (12px) horizontal
- Gap entre controles en un form: `--space-md` (16px)

### Theming automático

Todos los componentes usan variables semánticas — no hay variantes específicas de dark mode. Basta con `data-theme="dark"` en el ancestro.

```jsx
{/* Ambos themes funcionan sin cambiar el componente */}
<Card>
  <Badge variant="success">Aprobado</Badge>
  <h2>Título del artículo</h2>
</Card>
```

---

## Accesibilidad en componentes

- `<button>` nativo para acciones — nunca `<div onClick>`
- `<label>` vinculado a cada `<input>` con `htmlFor`
- `role="dialog"` + `aria-modal="true"` en modales
- `aria-expanded` en dropdowns y accordions
- `aria-selected` en tabs activas
- `aria-live="polite"` en zonas de actualización dinámica
- `aria-label` en icon-only buttons
