# Designing for Accessibility

La accesibilidad en Alexandria Magazine no es una capa añadida al final — está integrada en los tokens, en los patrones de componentes y en las decisiones tipográficas. Diseñar con este sistema es diseñar accesiblemente por defecto.

---

## Los tokens ya cumplen AA

Los pares de color semántico están pre-verificados. Si usas los tokens documentados en las superficies documentadas, el contraste es correcto. No uses primitivos directamente en UI de producto — los semánticos están ahí precisamente para esto.

**Lo que el sistema garantiza:**
- `--text-body` sobre `--bg-surface`: 11.48:1 — AAA
- `--text-secondary` sobre `--bg-surface`: 5.44:1 — AA
- `--text-link` (brand) sobre blanco: 4.63:1 — AA
- Blanco sobre `--brand`: 4.63:1 — AA
- Dark theme: todos los valores han subido de tono para mantener AA en superficies oscuras

**Lo que debes verificar tú:**
- Pares de color custom o combinaciones no documentadas
- Texto sobre imágenes o fondos con gradiente
- Iconos en colores no estándar

---

## Color no es suficiente

El sistema tiene herramientas para no depender nunca del color solo:

**Iconos Lucide:** cada estado tiene un icono propio. El artículo Aprobado tiene `check-circle` verde. El Rechazado tiene `x-circle` rojo. Un usuario con daltonismo lee el ícono y la etiqueta de texto.

**Etiquetas de texto:** los badges de estado siempre muestran el nombre del estado. "Aprobado" no es solo un badge verde.

**Patrones de textura/forma (para charts):** la paleta de dataviz está ordenada para máximo contraste adyacente y es colorblind-aware, pero siempre se acompañan con etiquetas directas o leyenda.

---

## Focus ring — siempre visible

El `--focus-ring` (3px azul a 25% alpha) es visible en todos los modos. No suprimir `:focus-visible`. No reemplazar por un borde más fino.

```css
/* El sistema ya lo define — no sobreescribir */
:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}
```

Para controles IA/generativos, el `--focus-ring-accent` (violeta) diferencia el tipo de control sin comprometer la visibilidad.

---

## Labels en todos los inputs

Nunca placeholder-only. El placeholder desaparece cuando el usuario empieza a escribir — si era el label, el campo queda sin identificar.

```jsx
{/* ✅ Correcto */}
<label htmlFor="titulo">Título del artículo</label>
<input
  id="titulo"
  placeholder="Escribe el título aquí"
/>

{/* ❌ Incorrecto */}
<input placeholder="Título del artículo" />
```

---

## Iconos con texto o aria-label

Los iconos de Lucide en UI siempre tienen contexto:

```jsx
{/* Con texto — preferido */}
<button className="btn btn-primary btn-base">
  <Save size={16} aria-hidden="true" />
  Guardar
</button>

{/* Solo icono — necesita aria-label */}
<button
  className="btn btn-secondary btn-icon"
  aria-label="Guardar artículo"
>
  <Save size={16} />
</button>

{/* Icono decorativo — ocultar de screen readers */}
<CheckCircle size={14} aria-hidden="true" />
<span>Aprobado</span>
```

---

## Motion reducida

Las animaciones del Flow Designer (marching ants, step spinners, fade entrances) son decorativas. Bajo `prefers-reduced-motion: reduce`, se pausan o eliminan. El sistema incluye esta regla en su CSS base.

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

Al diseñar animaciones, preguntarse siempre: ¿esta animación comunica algo que sin ella se pierde? Si la respuesta es no, es decorativa y debe pausarse.

---

## Idioma correcto

Alexandria es una plataforma bilingüe. El chrome de UI está en español (`lang="es"`). El contenido científico puede estar en inglés u otro idioma.

```html
<!-- Root en español -->
<html lang="es">

<!-- Sección en inglés (artículo científico) -->
<article lang="en" class="prose">
  <h1>Deep Learning Approaches for Scientific Literature Mining</h1>
</article>
```

Esto permite a los lectores de pantalla pronunciar correctamente en cada idioma.

---

## Checklist de diseño antes de entregar

- [ ] ¿Usé tokens semánticos de color? ¿No primitivos ni hex hardcoded?
- [ ] ¿Todos los estados tienen color + texto + icono?
- [ ] ¿Los focus rings son visibles en los prototipos?
- [ ] ¿Los inputs tienen labels persistentes visibles?
- [ ] ¿Los iconos solos tienen `aria-label` en la especificación?
- [ ] ¿Las animaciones son descartables / pausables?
- [ ] ¿El contraste de combinaciones custom está verificado?
- [ ] ¿Los textos sobre imagen tienen scrim suficiente (ink scrim)?
