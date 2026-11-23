// Estados de datos remotos: cargando / vacío / error — SPEC-003 / T7.3 / AC4.
//
// Los tres van juntos en un fichero porque son **un solo** contrato: toda vista
// que pida datos a la red tiene exactamente estos tres desenlaces, y lo que la
// aplicación hacía mal era tratarlos como dos.
//
// El fallo que motiva la tarea: al fallar la carga, las páginas hacían
// `catch { setLoading(false) }` y un `toast`. El toast se va a los pocos
// segundos y lo que queda en pantalla es el estado **vacío**: «Sin artículos —
// ejecuta un pipeline para generar tu primero». Es decir, la aplicación le dice a
// alguien que no tiene datos cuando lo que pasa es que no ha podido preguntarlo,
// y no le ofrece reintentar. Un error silencioso que además miente.
//
// Accesibilidad (viene de T7.2): cargar y fallar son cambios que ocurren sin que
// nadie los provoque, así que se anuncian. `role="status"` para lo que puede
// esperar, `role="alert"` para lo que interrumpe.
import React from 'react';
import { AlertTriangle, RotateCw } from 'lucide-react';
import { useTranslation } from '../../i18n';

/**
 * Cargando. `label` describe qué se está cargando: un lector de pantalla que
 * solo oye «cargando» no sabe si es la página o un panel dentro de ella.
 */
export function LoadingState({ label, compact = false }) {
  const { t } = useTranslation();
  return (
    <div
      className="empty-state"
      role="status"
      aria-live="polite"
      style={compact ? { padding: 'var(--space-6)' } : undefined}
    >
      <div className={compact ? 'spinner' : 'spinner spinner-lg'} aria-hidden="true" />
      <span className="sr-only">{label ?? t('states.loading')}</span>
    </div>
  );
}

/**
 * Sin datos. Es un estado **legítimo**: no lleva reintento ni tono de aviso,
 * porque no ha fallado nada. `action` es el siguiente paso natural (crear el
 * primero), no un «reintentar» disfrazado.
 */
export function EmptyState({ icon, title, description, action }) {
  return (
    <div className="empty-state">
      {icon && <div className="empty-state-icon">{icon}</div>}
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}

/**
 * La carga falló. Lo importante no es el icono: es que **no se confunda con el
 * vacío** y que ofrezca `onRetry`. Sin reintento, la única salida es recargar la
 * página entera y perder el resto del estado.
 */
export function ErrorState({
  title,
  description,
  onRetry,
  retryLabel,
}) {
  const { t } = useTranslation();
  return (
    <div className="empty-state state-error" role="alert">
      <div className="empty-state-icon state-error-icon">
        <AlertTriangle size={28} />
      </div>
      <h3>{title ?? t('states.loadError')}</h3>
      {description && <p>{description}</p>}
      {onRetry && (
        <button className="btn btn-secondary" onClick={onRetry}>
          <RotateCw size={14} /> {retryLabel ?? t('states.retry')}
        </button>
      )}
    </div>
  );
}

/**
 * Los tres estados en el orden correcto, que es el que casi siempre se escribe
 * mal: **error antes que vacío**. Al revés, una lista vacía por un fallo de red
 * se pinta como «no hay nada» y el error no llega a verse nunca.
 *
 * Una sola regla por encima de todo: **si hay datos, se enseñan los datos.** Ni
 * el spinner ni el error tapan una lista que ya se puede leer. Eso cubre dos
 * casos reales: recargar una lista ya cargada (sin parpadeo a spinner) y fallar
 * al refrescar cuando `flowStore` tiene flujos cacheados en `localStorage` —
 * tirar esa lista a la basura para enseñar un error sería peor que el error.
 *
 * @param {boolean} loading  hay una petición en curso
 * @param {?string} error    mensaje del último fallo de carga, o null
 * @param {boolean} isEmpty  no hay nada que renderizar
 * @param {Function} onRetry vuelve a lanzar la carga
 * @param {React.ReactNode} empty  el <EmptyState/> propio de esta vista
 */
export function AsyncState({
  loading,
  error,
  isEmpty,
  onRetry,
  loadingLabel,
  empty = null,
  children,
}) {
  if (!isEmpty) return children;
  if (loading) return <LoadingState label={loadingLabel} />;
  if (error) {
    return (
      <ErrorState
        description={typeof error === 'string' ? error : undefined}
        onRetry={onRetry}
      />
    );
  }
  return empty;
}
