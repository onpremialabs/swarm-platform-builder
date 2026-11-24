// Panel «Por qué este resultado» — SPEC-014 / T9.2 / AC2.
//
// T9.1 dejó la traza escrita: un registro por paso de agente con su modelo, sus
// parámetros, lo que recuperó del RAG, lo que decidió y lo que costó. Este panel
// es el único sitio donde eso se lee, y de él depende que la traza sirva para
// algo: un dato persistido que nadie puede ver no explica nada.
//
// Vive en `platform/` y no en el proyecto porque la explicabilidad es del motor:
// cualquier proyecto que ejecute un pipeline tiene pasos, fuentes y decisiones.
// Lo único del proyecto —cómo se llama y de qué color es cada agente— se
// pregunta al registro (`agentCatalog`), que es lo que invierte la dependencia.
//
// Dos escalas distintas conviven aquí y **no se pintan igual a propósito**: el
// score del revisor es una aprobación de 0 a 100, y el de una fuente es una
// similitud coseno de 0 a 1. Enseñar «0.91» y «91» con el mismo formato invitaría
// a leerlos como lo mismo.
import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle, ChevronDown, ChevronRight, Clock, FileSearch, Hash, Layers, Sparkles,
} from 'lucide-react';
import { agentMeta } from '../../agentCatalog';
import { agentsApi } from '../../api/agents';
import { mensajeDeCarga } from '../../api/errors';
import { AsyncState, EmptyState } from '../ui/states';
import { Trans, translate, useTranslation } from '../../i18n';

/** Milisegundos → algo legible. 8452.7 no dice nada; «8,5 s» sí. */
function formatoDuracion(ms, t, formatNumber) {
  if (!ms) return '—';
  if (ms < 1000) return t('explain.duration.ms', { value: Math.round(ms) });
  const segundos = ms / 1000;
  if (segundos < 60) {
    const decimales = { minimumFractionDigits: 1, maximumFractionDigits: 1 };
    return t('explain.duration.seconds', { value: formatNumber(segundos, decimales) });
  }
  return t('explain.duration.minutes', { minutes: Math.floor(segundos / 60), seconds: Math.round(segundos % 60) });
}

/** Número con el formato del idioma activo (`Intl`). */
function formatoNumero(n, formatNumber) {
  return formatNumber(n ?? 0);
}

/** Similitud coseno (0–1) como porcentaje. Es otra escala que el score del revisor. */
function porcentajeSimilitud(score, formatNumber) {
  return formatNumber(Math.round((Number(score) || 0) * 100) / 100, { style: 'percent', maximumFractionDigits: 0 });
}

const ESTADO_PASO = {
  completed: { labelKey: 'explain.status.completed', color: 'var(--status-success)' },
  failed: { labelKey: 'explain.status.failed', color: 'var(--status-error)' },
  error: { labelKey: 'explain.status.failed', color: 'var(--status-error)' },
};

function Metrica({ icon, label, valor }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ color: 'var(--text-muted)', display: 'flex' }} aria-hidden="true">{icon}</span>
      <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
        {label}: <strong style={{ color: 'var(--text-primary)' }}>{valor}</strong>
      </span>
    </div>
  );
}

/**
 * Una fuente recuperada. La barra es una ayuda, no el dato: el porcentaje va
 * escrito al lado porque el color por sí solo no comunica (T7.2).
 */
function Fuente({ fuente }) {
  const { t, formatNumber } = useTranslation();
  return (
    <li style={{
      display: 'flex', flexDirection: 'column', gap: 4,
      padding: 'var(--space-2) 0',
      borderBottom: '1px solid var(--border-subtle)',
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)' }}>
        <span style={{ flex: 1, fontSize: 'var(--font-size-sm)', color: 'var(--text-primary)' }}>
          {fuente.title || fuente.doc_id}
        </span>
        <span style={{
          fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)',
          fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap',
        }}>
          {t('explain.source.similarity', { percent: porcentajeSimilitud(fuente.score, formatNumber) })}
        </span>
      </div>
      <div
        style={{ height: 4, background: 'var(--bg-inset)', borderRadius: 'var(--radius-pill)' }}
        aria-hidden="true"
      >
        <div style={{
          width: `${Math.min(100, Math.round((Number(fuente.score) || 0) * 100))}%`,
          height: '100%', background: 'var(--brand)', borderRadius: 'var(--radius-pill)',
        }} />
      </div>
      <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
        {fuente.authors && <span>{fuente.authors} · </span>}
        {(fuente.chunk_ids || []).length > 0 && (
          <span>{t('explain.source.fragments', { count: fuente.chunk_ids.length })} · </span>
        )}
        <span>{t('explain.source.retrievedBy', { agents: (fuente.used_by || []).join(', ') || '—' })}</span>
      </div>
    </li>
  );
}

/** Un paso del pipeline: cabecera siempre visible, detalle desplegable. */
function Paso({ paso, abierto, onToggle }) {
  const { t, formatNumber } = useTranslation();
  const meta = agentMeta(paso.agent_name);
  const Icono = meta.icon;
  const estado = ESTADO_PASO[paso.status] || { label: paso.status, color: 'var(--text-muted)' };
  const detalleId = `explain-paso-${paso.id}`;
  const params = Object.entries(paso.params || {});
  const decision = paso.decision || null;

  return (
    <li style={{
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-md)',
      background: 'var(--bg-surface)',
      overflow: 'hidden',
    }}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={abierto}
        aria-controls={detalleId}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
          padding: 'var(--space-3) var(--space-4)', background: 'transparent',
          border: 'none', cursor: 'pointer', textAlign: 'left',
          color: 'var(--text-primary)', font: 'inherit',
        }}
      >
        <span aria-hidden="true" style={{ display: 'flex', color: 'var(--text-muted)' }}>
          {abierto ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        </span>
        <span
          aria-hidden="true"
          style={{ display: 'flex', color: meta.color || 'var(--text-secondary)' }}
        >
          {Icono ? <Icono size={16} /> : <Sparkles size={16} />}
        </span>
        <span style={{ flex: 1, fontWeight: 600, fontSize: 'var(--font-size-sm)' }}>
          {meta.label || paso.agent_name}
          {paso.iteration > 0 && (
            <span style={{
              marginLeft: 6, fontWeight: 400, fontSize: 'var(--font-size-xs)',
              color: 'var(--text-muted)',
            }}>
              {t('explain.step.round', { round: paso.iteration + 1 })}
            </span>
          )}
        </span>
        {decision?.score != null && (
          <span style={{
            fontSize: 'var(--font-size-xs)', fontVariantNumeric: 'tabular-nums',
            color: 'var(--text-secondary)',
          }}>
            {t('explain.step.score', { score: Math.round(decision.score) })}
          </span>
        )}
        <span style={{ fontSize: 'var(--font-size-xs)', color: estado.color }}>
          {estado.labelKey ? t(estado.labelKey) : estado.label}
        </span>
      </button>

      {/* El `display` sale de `abierto` y no solo del atributo `hidden`: el
          `display: none` que `hidden` trae de la hoja del navegador lo pisa
          cualquier `display` en línea, así que con las dos cosas el panel decía
          `aria-expanded="false"` y enseñaba el detalle igual. Lo encontró el test
          de navegador; leyendo el código no se ve. */}
      <div id={detalleId} hidden={!abierto} style={{
        padding: '0 var(--space-4) var(--space-4) var(--space-4)',
        display: abierto ? 'flex' : 'none',
        flexDirection: 'column', gap: 'var(--space-3)',
      }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-4)' }}>
          <Metrica icon={<Sparkles size={13} />} label={t('explain.metric.model')} valor={paso.model || '—'} />
          <Metrica
            icon={<Hash size={13} />}
            label={t('explain.metric.tokens')}
            valor={t('explain.tokensInOut', { in: formatoNumero(paso.tokens_in, formatNumber), out: formatoNumero(paso.tokens_out, formatNumber) })}
          />
          <Metrica icon={<Clock size={13} />} label={t('explain.metric.duration')} valor={formatoDuracion(paso.latency_ms, t, formatNumber)} />
        </div>

        {params.length > 0 && (
          <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
            {t('explain.params', { params: params.map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(' · ') })}
          </div>
        )}

        {paso.status !== 'completed' && paso.error_message && (
          <div role="alert" style={{
            display: 'flex', gap: 8, alignItems: 'flex-start',
            background: 'var(--status-error-bg)', borderRadius: 'var(--radius-sm)',
            padding: 'var(--space-3)', fontSize: 'var(--font-size-xs)',
            color: 'var(--text-secondary)',
          }}>
            <AlertTriangle size={14} style={{ color: 'var(--status-error)', flexShrink: 0 }} />
            <span>{paso.error_message}</span>
          </div>
        )}

        {paso.input_digest && (
          <div>
            <div style={{
              fontSize: 'var(--font-size-xs)', fontWeight: 600,
              color: 'var(--text-secondary)', marginBottom: 4,
            }}>
              {t('explain.input')}
            </div>
            <pre style={{
              margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)',
              fontFamily: 'var(--font-mono)', background: 'var(--bg-inset)',
              padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)',
            }}>{paso.input_digest}</pre>
          </div>
        )}

        {decision && (
          <div style={{
            background: 'var(--bg-inset)', borderRadius: 'var(--radius-sm)',
            padding: 'var(--space-3)', fontSize: 'var(--font-size-xs)',
            color: 'var(--text-secondary)',
          }}>
            <div style={{ fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>
              {t('explain.decision.title')}
            </div>
            {decision.score != null && (
              <div><Trans i18nKey="explain.decision.score" values={{ score: Math.round(decision.score) }} /></div>
            )}
            {decision.coherent != null && (
              <div><Trans i18nKey="explain.decision.coherent" values={{ value: decision.coherent ? t('explain.decision.yes') : t('explain.decision.no') }} /></div>
            )}
            {decision.hitl_outcome && (
              <div><Trans i18nKey="explain.decision.human" values={{ outcome: decision.hitl_outcome }} /></div>
            )}
            {decision.abstained && (
              <div>
                {decision.reason === 'insufficient_substantive_content' ? (
                  <Trans
                    i18nKey="explain.decision.abstainedContent"
                    values={{ found: decision.substantive_fragments ?? 0, min: decision.min_substantive_fragments ?? '?' }}
                  />
                ) : (
                  <Trans
                    i18nKey="explain.decision.abstained"
                    values={{ verified: decision.verified_sources ?? 0, min: decision.min_sources ?? '?' }}
                  />
                )}
              </div>
            )}
            {paso.rationale && (
              <div style={{ marginTop: 6, whiteSpace: 'pre-wrap' }}>{paso.rationale}</div>
            )}
          </div>
        )}

        {(paso.rag_sources || []).length > 0 && (
          <div>
            <div style={{
              fontSize: 'var(--font-size-xs)', fontWeight: 600,
              color: 'var(--text-secondary)', marginBottom: 4,
            }}>
              {t('explain.retrieved', { count: paso.rag_sources.length })}
            </div>
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {paso.rag_sources.map((fuente, i) => (
                <Fuente key={`${fuente.doc_id}-${i}`} fuente={{ ...fuente, used_by: [paso.agent_name] }} />
              ))}
            </ul>
          </div>
        )}
      </div>
    </li>
  );
}

/**
 * @param {string} articleId  artículo cuya traza se explica
 * @param {Function} load     cómo se pide la traza: `(articleId, scope) => Promise`.
 *   Por defecto la API real. Se inyecta para poder conducir el panel en un
 *   navegador de verdad (`frontend/a11y/explain.jsx`), que es la única forma de
 *   comprobar lo que este componente promete: que el detalle de un paso se abre,
 *   que los dos scores no se leen como el mismo número y que un fallo de carga no
 *   se confunde con «no hay traza».
 */
export default function ExplainPanel({ articleId, load = agentsApi.getExplain }) {
  const { t, formatNumber } = useTranslation();
  const [traza, setTraza] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(null);
  const [scope, setScope] = useState('last');
  const [abiertos, setAbiertos] = useState(() => new Set());

  const cargar = useCallback(async () => {
    if (!articleId) return;
    setCargando(true);
    setError(null);
    try {
      setTraza(await load(articleId, scope));
    } catch (e) {
      // No se traga: sin esto el panel se quedaría en el estado vacío
      // diciendo «no hay traza» cuando lo que pasa es que no pudo preguntarla.
      setError(mensajeDeCarga(e, translate('explain.loadError')));
    } finally {
      setCargando(false);
    }
  }, [articleId, scope, load]);

  useEffect(() => { cargar(); }, [cargar]);

  const alternar = (id) => setAbiertos((previos) => {
    const siguiente = new Set(previos);
    if (siguiente.has(id)) siguiente.delete(id); else siguiente.add(id);
    return siguiente;
  });

  // La traza que se está enseñando tiene que ser **la del alcance pedido**.
  // `AsyncState` mantiene los datos en pantalla cuando falla una recarga, y eso
  // está bien para un refresco: tirar una lista legible para enseñar un error
  // sería peor. Pero al cambiar de alcance los datos que quedan son de *otra*
  // pregunta, y enseñarlos como respuesta a esta es justo el tipo de mentira que
  // un panel de explicabilidad no se puede permitir.
  const vigente = traza && traza.scope === scope ? traza : null;
  const pasos = vigente?.steps || [];
  const totales = vigente?.totals || {};

  return (
    <section
      className="card"
      aria-labelledby="explain-titulo"
      style={{ padding: 'var(--space-6)' }}
    >
      <div style={{
        display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
        flexWrap: 'wrap', marginBottom: 'var(--space-4)',
      }}>
        <FileSearch size={16} style={{ color: 'var(--brand)' }} aria-hidden="true" />
        <h3 id="explain-titulo" style={{ margin: 0, fontSize: 'var(--font-size-md)', flex: 1 }}>
          {t('explain.title')}
        </h3>
        {/* El control se decide con lo último que se sabe del artículo, no con
            lo que hay en pantalla: cuántas ejecuciones tiene no depende del
            alcance, y esconder el botón cuando la carga falla deja a quien lo
            pulsó sin manera de volver. */}
        {traza?.executions > 1 && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setScope(scope === 'last' ? 'all' : 'last')}
            aria-label={scope === 'last'
              ? t('explain.viewAll', { count: traza.executions })
              : t('explain.viewLastOnly')}
          >
            <Layers size={13} />
            {scope === 'last' ? t('explain.viewAll', { count: traza.executions }) : t('explain.viewLast')}
          </button>
        )}
      </div>

      {/* Un artículo reejecutado se lee mal sin esto: lo que hay en pantalla lo
          produjo la última ejecución, no la suma de todas. */}
      {vigente?.executions > 1 && scope === 'last' && (
        <p style={{
          margin: '0 0 var(--space-4)', fontSize: 'var(--font-size-xs)',
          color: 'var(--text-muted)',
        }}>
          {t('explain.multipleRuns', { count: vigente.executions })}
        </p>
      )}

      <AsyncState
        loading={cargando}
        error={error}
        isEmpty={pasos.length === 0}
        onRetry={cargar}
        loadingLabel={t('explain.loading')}
        empty={(
          <EmptyState
            icon={<FileSearch size={28} />}
            title={t('explain.emptyTitle')}
            description={t('explain.emptyDescription')}
          />
        )}
      >
        <>
          <div style={{
            display: 'flex', flexWrap: 'wrap', gap: 'var(--space-5)',
            paddingBottom: 'var(--space-4)', marginBottom: 'var(--space-4)',
            borderBottom: '1px solid var(--border-subtle)',
          }}>
            <Metrica icon={<Layers size={13} />} label={t('explain.metric.steps')} valor={totales.steps ?? 0} />
            <Metrica
              icon={<Hash size={13} />}
              label={t('explain.metric.tokens')}
              valor={`${formatoNumero(totales.tokens_in, formatNumber)} / ${formatoNumero(totales.tokens_out, formatNumber)}`}
            />
            <Metrica icon={<Clock size={13} />} label={t('explain.metric.duration')} valor={formatoDuracion(totales.latency_ms, t, formatNumber)} />
            {totales.loops > 0 && (
              <Metrica
                icon={<Sparkles size={13} />}
                label={t('explain.metric.loops')}
                valor={totales.loops}
              />
            )}
            {totales.failed_steps > 0 && (
              <Metrica
                icon={<AlertTriangle size={13} />}
                label={t('explain.metric.failedSteps')}
                valor={totales.failed_steps}
              />
            )}
          </div>

          <ul style={{
            listStyle: 'none', margin: 0, padding: 0,
            display: 'flex', flexDirection: 'column', gap: 'var(--space-2)',
          }}>
            {pasos.map((paso) => (
              <Paso
                key={paso.id}
                paso={paso}
                abierto={abiertos.has(paso.id)}
                onToggle={() => alternar(paso.id)}
              />
            ))}
          </ul>

          {(vigente?.sources || []).length > 0 && (
            <div style={{ marginTop: 'var(--space-5)' }}>
              <h4 style={{
                margin: '0 0 var(--space-2)', fontSize: 'var(--font-size-sm)',
              }}>
                {t('explain.supports', { count: vigente.sources.length })}
              </h4>
              <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                {vigente.sources.map((fuente) => (
                  <Fuente key={fuente.doc_id} fuente={fuente} />
                ))}
              </ul>
            </div>
          )}
        </>
      </AsyncState>
    </section>
  );
}
