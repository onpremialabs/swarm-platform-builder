# Button

Los botones de Alexandria Magazine son la principal interfaz de acción. Se definen por cuatro variantes, tres tamaños, y un sistema estricto de un solo primario por vista. La jerarquía de botones comunica prioridad de acción — no decoración.

---

## Variantes

### btn-primary — acción principal

Fondo azul `--brand` (#0176D3), texto blanco, shadow de marca. Es el botón de mayor jerarquía visual. **Solo uno por vista.**

```css
.btn-primary {
  background: var(--brand);
  color: var(--text-on-brand);
  border: none;
  box-shadow: var(--shadow-brand);
}
.btn-primary:hover  { background: var(--brand-hover);  }
.btn-primary:active { background: var(--brand-active); transform: translateY(1px); }
```

**Usos correctos:** "Guardar", "Publicar", "Ejecutar pipeline", "Crear artículo"

---

### btn-secondary — acción secundaria

Fondo blanco, borde `--border-control` (#7B8CAA), texto `--text-body`. La alternativa al primario cuando hay dos acciones de igual importancia, pero una es la preferida.

```css
.btn-secondary {
  background: var(--bg-surface);
  color: var(--text-body);
  border: 1px solid var(--border-control);
}
.btn-secondary:hover  { background: var(--bg-hover); border-color: var(--border-brand); }
.btn-secondary:active { background: var(--bg-active); }
```

**Usos correctos:** "Cancelar", "Exportar", "Ver historial", acción alternativa junto a un primario

---

### btn-ghost — acción terciaria

Sin fondo ni borde. Solo texto en color de enlace. Para acciones de menor prioridad en contextos donde agregar un borde visual sería demasiado ruido.

```css
.btn-ghost {
  background: transparent;
  color: var(--text-link);
  border: none;
}
.btn-ghost:hover  { background: var(--brand-tint); }
.btn-ghost:active { background: var(--bg-active); }
```

**Usos correctos:** "Más información", links de navegación secundaria, acciones inline en tablas

---

### btn-accent — acción de IA / generativa

Violeta `--accent` (#6B4FE3). **Reservado exclusivamente para acciones de inteligencia artificial y generación.** Visualmente llama la atención sin competir con el primario.

```css
.btn-accent {
  background: var(--accent);
  color: #ffffff;
  border: none;
  box-shadow: var(--focus-ring-accent);
}
.btn-accent:hover  { background: var(--violet-70); }
.btn-accent:active { background: var(--violet-70); transform: translateY(1px); }
.btn-accent:focus-visible { box-shadow: var(--focus-ring-accent); }
```

**Usos correctos:** "Preguntar al agente", "Generar borrador", "Sugerir mejoras", "Ejecutar con IA"

> **Regla de oro:** `btn-accent` nunca coexiste con `btn-primary` en la misma llamada a la acción principal. Uno u otro, no ambos.

---

### btn-danger — acción destructiva

Rojo `--error` (#BA0517). Para acciones irreversibles. Muestra tint suave en reposo y solid en hover — la progresión de severidad es intencional.

```css
.btn-danger {
  background: var(--error-bg);
  color: var(--error);
  border: 1px solid var(--error);
}
.btn-danger:hover  { background: var(--error); color: #ffffff; }
.btn-danger:active { background: var(--red-70); color: #ffffff; transform: translateY(1px); }
```

**Usos correctos:** "Eliminar artículo", "Rechazar", "Borrar flujo"

---

## Tamaños

| Variante | Token | Padding H | Padding V | Font | Min-height | Uso |
|---|---|---|---|---|---|---|
| `btn-sm` | `--text-sm` | `--space-sm` (12px) | `--space-2xs` (4px) | 13px semibold | 32px | Acciones en tablas, toolbars densas |
| `btn-base` | `--text-base` | `--space-md` (16px) | `--space-xs` (8px) | 14px semibold | 40px | **Default** — formularios, modals |
| `btn-lg` | `--text-md` | `--space-lg` (24px) | `--space-sm` (12px) | 16px semibold | 48px | CTAs prominentes, onboarding |
| `btn-icon` | — | `--space-xs` (8px) | `--space-xs` (8px) | — | 40px (34px toolbar) | Solo icono — necesita `aria-label` |

---

## Estados

### Hover
Oscurece el fill un paso (primario: blue-70; danger: rojo sólido). Ghost y secondary añaden tint de fondo. Transición `--dur-fast` (120ms).

### Active / pressed
Oscurece dos pasos + `translateY(1px)` para sensación táctil. Duración `--dur-fast`.

### Disabled
```css
.btn:disabled,
.btn[aria-disabled="true"] {
  opacity: 0.45;
  cursor: not-allowed;
  pointer-events: none;
}
```
No cambiar colores — solo opacity al 45%. Mantener la forma del botón visible.

### Focus visible
```css
.btn:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);  /* 3px anillo azul a 25% alpha */
}
.btn-accent:focus-visible {
  box-shadow: var(--focus-ring-accent);  /* 3px anillo violeta a 25% alpha */
}
```

---

## Implementación en React

```jsx
import { Save, Trash2, Sparkles } from 'lucide-react';

// Primario
<button className="btn btn-primary btn-base">
  <Save size={16} />
  Guardar artículo
</button>

// Secundario
<button className="btn btn-secondary btn-base">
  Cancelar
</button>

// Acción de IA
<button className="btn btn-accent btn-base">
  <Sparkles size={16} />
  Generar borrador
</button>

// Destructivo
<button className="btn btn-danger btn-base">
  <Trash2 size={16} />
  Eliminar artículo
</button>

// Solo icono — requiere aria-label
<button className="btn btn-secondary btn-icon" aria-label="Configuración">
  <Settings size={16} />
</button>
```

---

## Tokens completos de botón

```css
.btn {
  /* Base */
  font-family: var(--font-sans);
  font-weight: var(--weight-semibold);
  border-radius: var(--radius-md);      /* 8px */
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);                 /* gap icono-texto: 8px */
  transition:
    background var(--dur-fast) var(--ease-standard),
    box-shadow var(--dur-fast) var(--ease-standard),
    transform var(--dur-fast) var(--ease-standard);
  white-space: nowrap;
  text-decoration: none;
  outline: none;

  /* Accessibility */
  min-height: 40px;                     /* target mínimo */
}
```

---

## Reglas de composición

- **Un solo `btn-primary` por vista.** Si hay múltiples acciones, usar secondary o ghost para las secundarias.
- **Verb-first en sentence case:** "Guardar", "Ejecutar", "Aprobar", "Rechazar" — no "Guardar el artículo".
- **Iconos opcionales** a la izquierda del label. Nunca a la derecha (excepto "siguiente" / flechas de navegación).
- **`btn-accent` y `btn-primary` nunca juntos** en el mismo grupo de acciones primarias.
- **Grupos de botones:** primario a la derecha, secundario/ghost a la izquierda.
- **Botones de solo icono** siempre con `aria-label` descriptivo.

---

## Grupos de acción — ejemplos

```jsx
{/* Modal footer — patrón estándar */}
<div className="btn-group">
  <button className="btn btn-ghost btn-base">Cancelar</button>
  <button className="btn btn-primary btn-base">
    <Save size={16} />
    Guardar cambios
  </button>
</div>

{/* Confirmación de borrado — danger pattern */}
<div className="btn-group">
  <button className="btn btn-secondary btn-base">Cancelar</button>
  <button className="btn btn-danger btn-base">
    <Trash2 size={16} />
    Eliminar artículo
  </button>
</div>
```

---

## Accesibilidad

- Todos los botones son `<button>` nativos — nunca `<div>` o `<span>` como botón
- Contraste mínimo: blanco sobre `--brand` = 4.63:1 (AA)
- Focus ring siempre visible — `--focus-ring` de 3px
- `aria-disabled="true"` + `pointer-events: none` para botones deshabilitados semánticos
- Botones de solo icono: `aria-label` obligatorio
- Target mínimo `btn-sm`: compensar con padding o espacio circundante para alcanzar 44×44px táctil
