# Code

Cómo instalar y usar el Design System de Alexandria Magazine en código. El sistema es un archivo CSS + convenciones de uso, no un paquete npm.

---

## Stack del proyecto

| Tecnología | Versión | Rol |
|---|---|---|
| React | 18 | UI framework |
| Vite | 5+ | Build tool |
| `@xyflow/react` | latest | Flow Designer canvas |
| `lucide-react` | 0.544.0+ | Sistema de iconos |
| CSS Custom Properties | — | Tokens del sistema de diseño |

---

## Instalación del Design System

### Paso 1 — Importar el CSS de tokens

```css
/* En tu archivo de estilos global (index.css o App.css) */
@import '../ds/colors_and_type.css';

/* O con alias de Vite */
@import '@ds/colors_and_type.css';
```

Configurar el alias en `vite.config.js`:

```js
// vite.config.js
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@ds': path.resolve(__dirname, '../ds'),
    },
  },
});
```

### Paso 2 — Aplicar la clase raíz

```jsx
// main.jsx
import './index.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <div className="ax-root">
      <App />
    </div>
  </React.StrictMode>
);
```

O directamente en el body:

```html
<!-- index.html -->
<body class="ax">
  <div id="root"></div>
</body>
```

### Paso 3 — Lucide React

```bash
# Ya incluido en el proyecto
npm install lucide-react
```

```jsx
import { Search, BookOpen, Bot, Zap, CheckCircle, AlertCircle } from 'lucide-react';

// Uso estándar
<Search size={16} />           // UI inline
<BookOpen size={24} />         // Empty state icon tile
<CheckCircle size={14} />      // Badge de estado aprobado
```

---

## Variables CSS — referencia rápida

```css
/* Color de acción principal */
var(--brand)                /* #0176D3 */
var(--brand-hover)          /* #005FB2 */
var(--brand-tint)           /* #EAF4FF */

/* Superficies */
var(--bg-canvas)            /* #F4F6F9 — fondo app */
var(--bg-surface)           /* #FFFFFF — cards, modales */
var(--bg-inset)             /* #EEF1F6 — áreas hundidas */

/* Texto */
var(--text-heading)         /* #0B1B33 */
var(--text-body)            /* #2E3A4D */
var(--text-secondary)       /* #5C6B7E */
var(--text-muted)           /* #657286 */

/* Bordes */
var(--border-default)       /* #E0E5EE */
var(--border-strong)        /* #D8DDE6 — separadores */
var(--border-control)       /* #7B8CAA — contorno de controles */

/* Espaciado */
var(--space-xs)             /* 8px */
var(--space-sm)             /* 12px */
var(--space-md)             /* 16px */
var(--space-lg)             /* 24px */

/* Radius */
var(--radius-md)            /* 8px — controles */
var(--radius-lg)            /* 12px — cards */
var(--radius-xl)            /* 16px — modales */

/* Sombras */
var(--shadow-1)             /* card en reposo */
var(--shadow-2)             /* card en hover */
var(--shadow-3)             /* popovers */
var(--focus-ring)           /* anillo de foco 3px */
```

---

## Componente de ejemplo — Card de artículo

```jsx
import { Clock, CheckCircle, Eye, Send } from 'lucide-react';

const statusConfig = {
  draft:     { label: 'Borrador',     icon: Clock,        color: 'var(--status-draft)'     },
  review:    { label: 'En revisión',  icon: Eye,          color: 'var(--status-review)'    },
  approved:  { label: 'Aprobado',     icon: CheckCircle,  color: 'var(--status-approved)'  },
  published: { label: 'Publicado',    icon: Send,         color: 'var(--status-published)' },
};

function ArticleCard({ title, author, status, updatedAt }) {
  const { label, icon: StatusIcon, color } = statusConfig[status];

  return (
    <div className="article-card">
      <div className="article-card-header">
        <h2 className="article-card-title">{title}</h2>
        <span
          className="badge"
          style={{ color, backgroundColor: `color-mix(in srgb, ${color} 12%, transparent)` }}
        >
          <StatusIcon size={12} aria-hidden="true" />
          {label}
        </span>
      </div>
      <p className="article-card-meta">
        {author} · {updatedAt}
      </p>
    </div>
  );
}
```

```css
.article-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-1);
  padding: var(--space-lg);
  transition:
    box-shadow var(--dur-fast) var(--ease-standard),
    border-color var(--dur-fast) var(--ease-standard);
}

.article-card:hover {
  box-shadow: var(--shadow-2);
  border-color: var(--border-strong);
}

.article-card-title {
  font-family: var(--font-serif);         /* serif para títulos editoriales */
  font-size: var(--text-xl);
  font-weight: var(--weight-semibold);
  color: var(--text-heading);
  margin: 0;
}

.article-card-meta {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--space-xs) 0 0;
}
```

---

## Tema oscuro en React

```jsx
// Hook para gestionar el tema
function useTheme() {
  const [theme, setTheme] = useState(
    localStorage.getItem('ax-theme') || 'light'
  );

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('ax-theme', theme);
  }, [theme]);

  const toggle = () => setTheme(t => t === 'light' ? 'dark' : 'light');
  return { theme, toggle };
}

// En el componente raíz
function App() {
  const { theme, toggle } = useTheme();
  return (
    <div className="ax-root">
      {/* El tema se aplica vía data-theme en <html> */}
      <Router />
    </div>
  );
}
```

---

## Flow Designer — tokens de nodo de agente

```jsx
// AgentNode.jsx — usa colores del sistema por agente
const agentColors = {
  research:  'var(--agent-research)',
  write:     'var(--agent-write)',
  review:    'var(--agent-review)',
  format:    'var(--agent-format)',
  publish:   'var(--agent-publish)',
};

function AgentNode({ data }) {
  const color = agentColors[data.agentType];
  return (
    <div
      className="agent-node"
      style={{ '--node-color': color }}
    >
      <div className="agent-node-header">
        <div className="agent-icon-tile">
          {/* Icono del agente */}
        </div>
        <span>{data.label}</span>
      </div>
    </div>
  );
}
```

```css
.agent-node {
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-left: 3px solid var(--node-color);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-1);
}

.agent-icon-tile {
  background: color-mix(in srgb, var(--node-color) 12%, transparent);
  color: var(--node-color);
  border-radius: var(--radius-sm);
  padding: var(--space-2xs);
}
```

---

## Importar artículo en registro `.prose`

```jsx
function ArticleReader({ content }) {
  return (
    <main className="reading-column">
      <article
        className="prose"
        lang={content.lang || 'es'}
        dangerouslySetInnerHTML={{ __html: content.html }}
      />
    </main>
  );
}
```

```css
.reading-column {
  max-width: var(--measure);   /* 68ch */
  margin: 0 auto;
  padding: var(--space-3xl) var(--space-lg);
}
```
