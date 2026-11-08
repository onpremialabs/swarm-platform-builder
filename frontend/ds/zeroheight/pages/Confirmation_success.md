# Confirmation & Success

Alexandria Magazine confirma el éxito con calma y precisión. Sin celebración exagerada, sin confeti, sin signos de exclamación. El éxito es el estado esperado — reconocerlo brevemente y continuar.

---

## Patrones de confirmación

### Toast de éxito — la confirmación principal

Para acciones completadas (guardado, publicación, ejecución de pipeline). Verde, auto-dismiss a los 4 segundos.

```css
.toast-success {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  background: var(--success);
  color: #ffffff;
  border-radius: var(--radius-md);
  padding: var(--space-sm) var(--space-md);
  box-shadow: var(--shadow-3);
  min-width: 280px;
  max-width: 400px;
}
```

```jsx
<div aria-live="polite" aria-atomic="true">
  <div className="toast-success" role="status">
    <CheckCircle size={18} />
    <span>Flujo guardado</span>
  </div>
</div>
```

**Ejemplos de copy correcto:**
- "Flujo guardado" — no "¡Tu flujo se guardó exitosamente! 🎉"
- "Artículo publicado" — no "¡Publicación exitosa! 🚀"
- "Cambios guardados" — no "Todo perfecto ✅"
- "Pipeline ejecutado" — no "¡El pipeline terminó! ¡Qué rápido!"

### Badge de estado — Aprobado

Cuando un artículo pasa a estado Aprobado, el badge refleja el cambio de estado sin animación especial.

```jsx
<span className="badge badge-approved">
  <CheckCircle size={12} />
  Aprobado
</span>
```

```css
.badge-approved {
  background: var(--success-bg);
  color: var(--success);
  /* --success = #1F6135 sobre --success-bg = #EBF7EE */
}
```

### Alerta de éxito en línea — para flujos con confirmación explícita

En flujos donde el usuario espera una confirmación larga (ejecución de pipeline, publicación con revisión), se muestra una alerta verde inline.

```css
.alert-success {
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
  background: var(--success-bg);
  border: 1px solid var(--success);
  border-left: 3px solid var(--success);
  border-radius: var(--radius-md);
  padding: var(--space-sm) var(--space-md);
  color: var(--text-heading);
}
```

```jsx
<div className="alert-success" role="status">
  <CheckCircle size={18} style={{ color: 'var(--success)', flexShrink: 0 }} />
  <div>
    <strong>Pipeline completado.</strong>
    <p>El artículo está listo para revisión. Score de aprobación: 87/100.</p>
  </div>
</div>
```

---

## Estados de confirmación en el flujo de trabajo

### Paso completado en pipeline

Cuando un agente completa su trabajo en el Flow Designer, su nodo muestra:
- Borde izquierdo `--success` 
- Icono `check-circle` en el header
- Badge verde "Completado"
- Sin animación de celebración — solo el cambio de estado

### Publicación confirmada

Después de publicar un artículo, el badge de estado cambia de "Aprobado" a "Publicado" (azul brand). La notificación es un toast estándar. No hay pantalla de felicitación.

```jsx
// Estado post-publicación
<ArticleCard
  status="published"    // badge azul
  publishedAt={date}   // timestamp visible
/>
```

---

## Reglas de tono en confirmaciones

| Correcto | Incorrecto |
|---|---|
| "Flujo guardado" | "¡Tu flujo se guardó con éxito! 🎉" |
| "Artículo publicado" | "¡Publicación exitosa! ¡Buen trabajo!" |
| "Cambios guardados" | "Todo salió perfecto ✅" |
| "Pipeline completado" | "¡El pipeline terminó en tiempo récord! 🚀" |
| "Revisor asignado" | "¡Genial! Asignaste un revisor 👍" |

**La voz es precisa y calmada.** El estado completado es lo esperado, no una hazaña. El usuario sabe lo que pidió — solo necesita confirmación de que ocurrió.

---

## Duración de toasts

| Tipo | Duración | Motivo |
|---|---|---|
| Success | 4s | Acción completada, baja urgencia |
| Info | 5s | Informativo, puede necesitar leerse |
| Warning | 6s | Requiere atención |
| Error | 6s | Requiere acción del usuario |

Todos los toasts son descartables manualmente con `×`. El timer pausa en hover.

---

## Accesibilidad en confirmaciones

- `role="status"` + `aria-live="polite"` para toasts de éxito — anuncio no interrumpido
- `role="alert"` + `aria-live="assertive"` solo para errores — anuncio inmediato
- El foco no se mueve al aparecer un toast — el usuario continúa donde estaba
- El toast debe ser descartable con teclado (`Esc` o button con `aria-label="Cerrar"`)
