# Color

El sistema de color de Alexandria Magazine está construido sobre la arquitectura de tokens de **Salesforce Lightning Design System 2 (SLDS2)** — neutrales cloud, un azul de marca seguro, y color semántico sistemático — extendido con una paleta editorial de cinco agentes y estados de flujo de trabajo. El resultado es una UI limpia y espaciosa con color que comunica función, nunca decoración.

---

## Alexandria Blue — el color primario

**Alexandria Blue `#0176D3`** es el color de acción y confianza del sistema. Aparece en acciones primarias, enlaces, selecciones y anillos de foco. Procede del ramp azul de SLDS2 (brand blue family).

| Token CSS | Hex | Uso |
|---|---|---|
| `--blue-05` | `#EAF4FF` | Fondo de filas/estados seleccionados, nav activo |
| `--blue-10` | `#D6EAFF` | Tint secundario |
| `--blue-20` | `#AAD5FB` | Decoración ligera, underline de link en hover |
| `--blue-40` | `#4EA0EE` | Acento azure intermedio |
| `--blue-50` | `#1B96FF` | Azure / acento alternativo |
| `--blue-60` | `#0176D3` | **PRIMARY** — botón primario, enlace, focus |
| `--blue-70` | `#005FB2` | Hover del primario |
| `--blue-80` | `#014486` | Active / pressed / deep |
| `--blue-95` | `#022A52` | Navy profundo |

### Tokens semánticos de marca

| Token CSS | Apunta a | Uso |
|---|---|---|
| `--brand` | `--blue-60` | Color de acción principal |
| `--brand-hover` | `--blue-70` | Estado hover del botón primario |
| `--brand-active` | `--blue-80` | Estado active/pressed |
| `--brand-tint` | `--blue-05` | Fondo de selección, nav activo |
| `--brand-on` | `#FFFFFF` | Texto/icono sobre fondo de marca |

---

## Neutrales — cloud ramp SLDS

Las superficies de la app viven en una gama de grises azulados muy tenues. El canvas de la app es Link Water `#F4F6F9`; las cards son blancas; los bordes son Steam `#E0E5EE`. El texto oscuro nunca es negro puro — es ink navy `#0B1B33`.

| Token CSS | Hex | Nombre SLDS | Uso |
|---|---|---|---|
| `--neutral-00` | `#FFFFFF` | White | Surfaces — cards, modals, panels |
| `--neutral-05` | `#F8FAFC` | — | Sunken / background de código |
| `--neutral-10` | `#F4F6F9` | Link Water | Canvas de la app |
| `--neutral-15` | `#EEF1F6` | White Lilac | Inset, separadores muy suaves |
| `--neutral-20` | `#E0E5EE` | Steam | Bordes por defecto |
| `--neutral-30` | `#D8DDE6` | Geyser | Separadores fuertes, hover de cards |
| `--neutral-40` | `#C9CFDB` | — | Neutral medio |
| `--neutral-50` | `#AAB2C2` | — | Muted neutral |
| `--neutral-60` | `#8793A5` | — | Ejes de gráficos; no llega a AA como texto |
| `--neutral-65` | `#657286` | — | Placeholder, texto muted (mínimo AA) |
| `--neutral-70` | `#5C6B7E` | — | Texto secundario / labels |
| `--neutral-80` | `#44546A` | — | Secondary fuerte |
| `--neutral-90` | `#2E3A4D` | — | Body text (tema claro) |

### Ink — navy editorial

| Token CSS | Hex | Uso |
|---|---|---|
| `--ink-100` | `#0B1B33` | Headings — máximo contraste |
| `--ink-90` | `#16243D` | Texto primario en superficies oscuras |
| `--ink-80` | `#1F3A5F` | Acento de tinta profundo |

### Tokens semánticos de superficie y texto

| Token CSS | Apunta a | Uso |
|---|---|---|
| `--bg-canvas` | `--neutral-10` | Fondo de la app |
| `--bg-surface` | `--neutral-00` | Cards, paneles |
| `--bg-sunken` | `--neutral-05` | Áreas hundidas |
| `--bg-inset` | `--neutral-15` | Insets, background de código inline |
| `--bg-hover` | `--neutral-10` | Hover en filas interactivas |
| `--bg-active` | `--blue-05` | Fila/item seleccionado activo |
| `--text-heading` | `--ink-100` | Todos los headings |
| `--text-body` | `--neutral-90` | Texto de cuerpo por defecto |
| `--text-secondary` | `--neutral-70` | Metadatos, labels de campo |
| `--text-muted` | `--neutral-65` | Placeholder, hints, disabled |
| `--text-link` | `--blue-60` | Enlaces interactivos |
| `--border-control` | `#7B8CAA` | Contorno de inputs, botones secundarios y toggles |

---

## Intelligence Accent — violeta

**Violet `#6B4FE3`** es la continuidad del brand original (dark `#7c3aed`). Se usa **con moderación** — solo para momentos de IA y generatividad. Nunca como color decorativo.

| Token CSS | Hex | Uso |
|---|---|---|
| `--violet-05` | `#F1EEFE` | Tint de fondo para acciones IA |
| `--violet-40` | `#9A82F0` | Violeta claro |
| `--violet-60` | `#6B4FE3` | **Accent** — botón "Ask AI", estado generativo |
| `--violet-70` | `#5436C9` | Violet hover |
| `--accent` | `--violet-60` | Token semántico — accent principal |
| `--accent-tint` | `--violet-05` | Token semántico — tint de accent |

> **Regla de uso:** `--accent` aparece en: botón `btn-accent`, ring de foco en controles IA (`--focus-ring-accent`), el agente Redactor, y estados de generación activa. Nunca en navegación ni elementos de estado genérico.

---

## Paleta de agentes

Los cinco agentes del pipeline editorial tienen un color propio. El **full value** se usa para el mark/icono del agente; el **tint 05** respalda chips de agente e icon tiles.

| Agente | Token CSS | Hex | Lucide icon |
|---|---|---|---|
| Investigador | `--agent-research` | `#0D9DDA` | `search` |
| Redactor | `--agent-write` | `#6B4FE3` | `pen-line` |
| Revisor | `--agent-review` | `#C47D04` | `eye` |
| Formateador | `--agent-format` | `#2E844A` | `file-text` |
| Publicador | `--agent-publish` | `#CB4B3F` | `send` |

### Cómo usar los tints de agente

```css
/* Icon tile de agente — tint como fondo, full value como glyph */
.agent-tile {
  background-color: color-mix(in srgb, var(--agent-research) 8%, transparent);
  color: var(--agent-research);
  border-radius: var(--radius-md);
  padding: var(--space-xs);
}
```

En React con Lucide:
```jsx
import { Search } from 'lucide-react';

<div
  className="agent-tile"
  style={{ '--agent-color': 'var(--agent-research)' }}
>
  <Search size={16} />
</div>
```

---

## Colores semánticos

Los colores de estado siempre se usan en pares: **valor pleno** para el texto/icono + **tint pálido** para el fondo. Nunca solo color para comunicar estado — siempre acompañado de texto e icono Lucide.

| Estado | Token valor | Hex | Token tint | Hex tint |
|---|---|---|---|---|
| Success | `--success` | `#1F6135` | `--success-bg` | `#EBF7EE` |
| Warning | `--warning` | `#946004` | `--warning-bg` | `#FDF3E3` |
| Error | `--error` | `#BA0517` | `--error-bg` | `#FEEEEC` |
| Info | `--info` | `#005FB2` | `--info-bg` | `#EAF4FF` |

```css
/* Alerta de error — siempre: tint bg + color fg + icono */
.alert-error {
  background: var(--error-bg);
  border: 1px solid var(--error);
  border-left: 3px solid var(--error);
  color: var(--text-heading);
  /* Acompañar con <AlertCircle /> de Lucide */
}
```

---

## Estados editoriales del artículo

El ciclo de vida del artículo (`borrador → en_revisión → aprobado → publicado`) se representa con tokens de estado. Cada estado tiene su color + badge + etiqueta de texto.

| Estado | Token CSS | Hex | Label |
|---|---|---|---|
| Borrador | `--status-draft` | `#5C6B7E` | Borrador |
| En revisión | `--status-review` | `#946004` | En revisión |
| Aprobado | `--status-approved` | `#1F6135` | Aprobado |
| Publicado | `--status-published` | `#005FB2` | Publicado |
| Rechazado | `--status-rejected` | `#BA0517` | Rechazado |

```jsx
// Badge de estado — siempre: color + icono + label
const statusConfig = {
  draft:     { color: 'var(--status-draft)',     icon: Clock,       label: 'Borrador'     },
  review:    { color: 'var(--status-review)',    icon: Eye,         label: 'En revisión'  },
  approved:  { color: 'var(--status-approved)',  icon: CheckCircle, label: 'Aprobado'     },
  published: { color: 'var(--status-published)', icon: Send,        label: 'Publicado'    },
  rejected:  { color: 'var(--status-rejected)',  icon: XCircle,     label: 'Rechazado'    },
};
```

---

## Tema oscuro

El tema oscuro se activa con `data-theme="dark"` o la clase `.dark` en cualquier ancestro. Solo los tokens semánticos cambian — los primitivos son compartidos. Los colores de marca suben de tono para mantener contraste AA sobre superficies oscuras.

| Token | Light | Dark |
|---|---|---|
| `--brand` | `#0176D3` | `#2F9BFF` |
| `--bg-canvas` | `#F4F6F9` | `#0A1120` |
| `--bg-surface` | `#FFFFFF` | `#111C2F` |
| `--text-heading` | `#0B1B33` | `#F3F6FC` |
| `--text-body` | `#2E3A4D` | `#D2DCEA` |
| `--border-default` | `#E0E5EE` | `rgba(255,255,255,0.11)` |

```html
<!-- Sección completa en dark -->
<section data-theme="dark">
  <!-- Todos los componentes dentro heredan el tema oscuro automáticamente -->
</section>
```

---

## Accesibilidad de color

Todos los tokens semánticos están pre-verificados contra sus superficies documentadas:

| Par | Ratio | Nivel |
|---|---|---|
| `--text-body` sobre `--bg-surface` | 11.48:1 | AAA |
| `--text-heading` sobre `--bg-surface` | 17.23:1 | AAA |
| `--brand` (link) sobre blanco | 4.63:1 | AA |
| Blanco sobre `--brand` (btn-primary) | 4.63:1 | AA |
| `--text-secondary` sobre `--bg-surface` | 5.44:1 | AA |
| `--status-draft` sobre `--bg-surface` | 5.44:1 | AA |

> Nunca usar solo color para comunicar estado. Siempre: color + etiqueta de texto + icono Lucide.
