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

/** Milisegundos → algo legible. 8452.7 no dice nada; «8,5 s» sí. */
function formatoDuracion(ms) {
  if (!ms) return '—';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const segundos = ms / 1000;
  if (segundos < 60) return `${segundos.toFixed(1).replace('.', ',')} s`;
  return `${Math.floor(segundos / 60)} min ${Math.round(segundos % 60)} s`;
}

function formatoNumero(n) {
  return (n ?? 0).toLocaleString('es-ES');
}

/** Similitud coseno (0–1) como porcentaje. Es otra escala que el score del revisor. */
function porcentajeSimilitud(score) {
  return `${Math.round((Number(score) || 0) * 100)} %`;
}

const ESTADO_PASO = {
  completed: { label: 'Completado', color: 'var(--status-success)' },
  failed: { label: 'Falló', color: 'var(--status-error)' },
  error: { label: 'Falló', color: 'var(--status-error)' },
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
          {porcentajeSimilitud(fuente.score)} de similitud
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
          <span>{fuente.chunk_ids.length} fragmento(s) · </span>
        )}
        <span>Recuperada por {(fuente.used_by || []).join(', ') || '—'}</span>
      </div>
    </li>
  );
}

/** Un paso del pipeline: cabecera siempre visible, detalle desplegable. */
function Paso({ paso, abierto, onToggle }) {
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
              · vuelta {paso.iteration + 1}
            </span>
          )}
        </span>
        {decision?.score != null && (
          <span style={{
            fontSize: 'var(--font-size-xs)', fontVariantNumeric: 'tabular-nums',
            color: 'var(--text-secondary)',
          }}>
            score {Math.round(decision.score)}/100
          </span>
        )}
        <span style={{ fontSize: 'var(--font-size-xs)', color: estado.color }}>
          {estado.label}
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
          <Metrica icon={<Sparkles size={13} />} label="Modelo" valor={paso.model || '—'} />
          <Metrica
            icon={<Hash size={13} />}
            label="Tokens"
            valor={`${formatoNumero(paso.tokens_in)} ent. / ${formatoNumero(paso.tokens_out)} sal.`}
          />
          <Metrica icon={<Clock size={13} />} label="Duración" valor={formatoDuracion(paso.latency_ms)} />
        </div>

        {params.length > 0 && (
          <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
            Parámetros: {params.map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(' · ')}
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
              Con qué entró
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
              Qué decidió
            </div>
            {decision.score != null && (
              <div>Score de aprobación: <strong>{Math.round(decision.score)}/100</strong></div>
            )}
            {decision.coherent != null && (
              <div>Coherencia: <strong>{decision.coherent ? 'sí' : 'no'}</strong></div>
            )}
            {decision.hitl_outcome && (
              <div>Decisión humana: <strong>{decision.hitl_outcome}</strong></div>
            )}
            {decision.abstained && (
              <div>
                Se abstuvo: <strong>{decision.verified_sources ?? 0} de {decision.min_sources ?? '?'}</strong> fuentes
                verificadas necesarias
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
              Qué recuperó ({paso.rag_sources.length})
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
      setError(mensajeDeCarga(e, 'No se pudo cargar la traza de la ejecución'));
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
          Por qué este resultado
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
              ? `Ver las ${traza.executions} ejecuciones`
              : 'Ver solo la última ejecución'}
          >
            <Layers size={13} />
            {scope === 'last' ? `Ver las ${traza.executions} ejecuciones` : 'Ver solo la última'}
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
          Este artículo se ha ejecutado {vigente.executions} veces. Se explica la última,
          que es la que produjo el texto actual.
        </p>
      )}

      <AsyncState
        loading={cargando}
        error={error}
        isEmpty={pasos.length === 0}
        onRetry={cargar}
        loadingLabel="Cargando la traza de la ejecución…"
        empty={(
          <EmptyState
            icon={<FileSearch size={28} />}
            title="Sin traza que explicar"
            description={
              "Este artículo no tiene una ejecución registrada. La traza se guarda "
              + "al ejecutar el pipeline, y se conserva 90 días."
            }
          />
        )}
      >
        <>
          <div style={{
            display: 'flex', flexWrap: 'wrap', gap: 'var(--space-5)',
            paddingBottom: 'var(--space-4)', marginBottom: 'var(--space-4)',
            borderBottom: '1px solid var(--border-subtle)',
          }}>
            <Metrica icon={<Layers size={13} />} label="Pasos" valor={totales.steps ?? 0} />
            <Metrica
              icon={<Hash size={13} />}
              label="Tokens"
              valor={`${formatoNumero(totales.tokens_in)} / ${formatoNumero(totales.tokens_out)}`}
            />
            <Metrica icon={<Clock size={13} />} label="Duración" valor={formatoDuracion(totales.latency_ms)} />
            {totales.loops > 0 && (
              <Metrica
                icon={<Sparkles size={13} />}
                label="Vueltas de revisión"
                valor={totales.loops}
              />
            )}
            {totales.failed_steps > 0 && (
              <Metrica
                icon={<AlertTriangle size={13} />}
                label="Pasos fallidos"
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
                En qué se apoya ({vigente.sources.length})
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
