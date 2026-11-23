import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { agentMeta } from '../catalog';
import { dashboardApi } from '../../../platform/api/dashboard';
import { useArticleStore } from '../store/articleStore';
import { LoadingState } from '../../../platform/components/ui/states';
import { tr, useT } from '../i18n/useT';
import {
  Activity, BarChart2, Clock, FileText, RefreshCw,
  XCircle, CheckCircle, Zap,
  AlertTriangle, CloudOff, Bot,
} from 'lucide-react';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmt(ms) {
  if (!ms || ms <= 0) return '—';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1).replace('.', ',')} s`;
  return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
}

// Latencia de agente, siempre en segundos. `fmt` cambia de unidad según la
// magnitud, y eso rompe la comparación entre agentes: el publicador, que no
// llama al LLM, salía en ms al lado de agentes medidos en minutos.
function fmtSeg(ms) {
  if (!ms || ms <= 0) return '—';
  const s = (ms / 1000).toLocaleString('es-ES', {
    minimumFractionDigits: 1, maximumFractionDigits: 1,
  });
  return `${s} s`;
}

function fmtNum(n) {
  return (n ?? 0).toLocaleString('es-ES');
}

function fmtFecha(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('es-ES', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

/** Color del agente según el catálogo del proyecto; gris si no está. */
const agentColor = (name) => agentMeta(name)?.color || 'var(--text-muted)';

// ─── Tile global ──────────────────────────────────────────────────────────────

/**
 * Tile de magnitud. Con `unavailable` no pinta un cero: pinta que no se pudo
 * preguntar (AC7). Un cero y un «no lo sé» no pueden verse igual — es el mismo
 * principio que el «0 de 4 comprobaciones» de las anomalías.
 */
function StatTile({ icon, label, value, sub, color, unavailable, reason }) {
  const { t } = useT();
  return (
    <div className="metrics-stat-tile" data-unavailable={unavailable || undefined}>
      <span className="metrics-stat-icon"
        style={{ color: unavailable ? 'var(--text-muted)' : (color || 'var(--brand)') }}>
        {unavailable ? <CloudOff size={20} /> : icon}
      </span>
      <div>
        <div className="metrics-stat-value"
          style={unavailable ? { color: 'var(--text-muted)' } : undefined}>
          {unavailable ? t('metrics.unavailable') : value}
        </div>
        <div className="metrics-stat-label">{label}</div>
        {unavailable
          ? <div className="metrics-stat-sub">{reason ? t('metrics.queryFailedReason', { reason }) : t('metrics.queryFailed')}</div>
          : sub && <div className="metrics-stat-sub">{sub}</div>}
      </div>
    </div>
  );
}

/** Estado del enjambre (AC4): cada agente, su estado y el criterio que lo decide. */
const SWARM_STYLE = {
  ejecutando:     { label: 'metrics.swarm.state.ejecutando',     color: 'var(--info)' },
  incierto:       { label: 'metrics.swarm.state.incierto',       color: 'var(--warning)' },
  disponible:     { label: 'metrics.swarm.state.disponible',     color: 'var(--success)' },
  no_configurado: { label: 'metrics.swarm.state.no_configurado', color: 'var(--text-muted)' },
};

function SwarmAgent({ agent }) {
  const { t } = useT();
  const meta  = agentMeta(agent.name) || {};
  const Icono = meta.icon;
  const estilo = SWARM_STYLE[agent.state] || SWARM_STYLE.no_configurado;
  return (
    <div className="metrics-swarm-agent" title={agent.criterion}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        {Icono
          ? <Icono size={16} style={{ color: agentColor(agent.name), flexShrink: 0 }} />
          : <span style={{ width: 16, height: 16, borderRadius: '50%',
              background: agentColor(agent.name), flexShrink: 0 }} />}
        <span style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500,
          color: 'var(--text-heading)', overflow: 'hidden',
          textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {meta.label || agent.label || agent.name}
        </span>
      </span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
        {agent.state === 'ejecutando' && (
          <span className="metrics-swarm-pulse" style={{ background: estilo.color }} />
        )}
        <span style={{ fontSize: 'var(--font-size-xs)', fontWeight: 600, color: estilo.color }}>
          {t(estilo.label)}
        </span>
      </span>
    </div>
  );
}

// ─── Tarjeta de agente ────────────────────────────────────────────────────────

function AgentCard({ data }) {
  const { t } = useT();
  const meta   = agentMeta(data.name) || {};
  const Icono  = meta.icon;
  const color  = agentColor(data.name);
  const avgLat = data.runs > 0 ? Math.round(data.latencyMs / data.runs) : 0;

  return (
    <div className="metrics-agent-card" style={{ borderTopColor: color }}>
      <div className="metrics-agent-card-header">
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {Icono
            ? <Icono size={18} style={{ color }} />
            : <span style={{ width: 18, height: 18, borderRadius: '50%', background: color, display: 'inline-block' }} />}
          <span style={{ fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--text-heading)' }}>
            {meta.label || data.name}
          </span>
        </span>
        {data.errors > 0
          ? <span className="badge badge-error" style={{ fontSize: 10 }}>{t('metrics.errors', { count: data.errors })}</span>
          : <CheckCircle size={14} style={{ color: 'var(--success)' }} />}
      </div>

      <div className="metrics-agent-card-stats">
        <div className="metrics-agent-stat">
          <span className="metrics-agent-stat-label">{t('metrics.agent.runs')}</span>
          <span className="metrics-agent-stat-val">{fmtNum(data.runs)}</span>
        </div>
        <div className="metrics-agent-stat">
          <span className="metrics-agent-stat-label">{t('metrics.agent.tokens')}</span>
          <span className="metrics-agent-stat-val">{fmtNum(data.tokens)}</span>
        </div>
        <div className="metrics-agent-stat">
          <span className="metrics-agent-stat-label">{t('metrics.agent.avgLatency')}</span>
          <span className="metrics-agent-stat-val">{fmtSeg(avgLat)}</span>
        </div>
        <div className="metrics-agent-stat">
          <span className="metrics-agent-stat-label">{t('metrics.agent.totalLatency')}</span>
          <span className="metrics-agent-stat-val">{fmtSeg(data.latencyMs)}</span>
        </div>
      </div>
    </div>
  );
}

// ─── Página ───────────────────────────────────────────────────────────────────

export default function MetricsDashboardPage() {
  const { t } = useT();
  const navigate = useNavigate();
  const { articles, fetchArticles } = useArticleStore();

  // summary viene del endpoint /dashboard/summary (una sola petición, aislada por proyecto)
  const [summary, setSummary]     = useState(null);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState(null);

  const loadSummary = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await dashboardApi.getSummary();
      setSummary(data);
    } catch (e) {
      setError(e?.response?.data?.detail || tr('metrics.loadError'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchArticles({ limit: 200 }); }, []); // eslint-disable-line
  useEffect(() => { loadSummary(); }, []); // eslint-disable-line

  // Disponibilidad por sección (AC7). Si el backend no la declara —respuesta de
  // una versión anterior— se asume disponible: lo contrario pintaría «no
  // disponible» sobre datos que sí llegaron.
  const sections = summary?.sections ?? {};
  const seccion  = (n) => sections[n] ?? { available: true };

  // ── Agregados desde /dashboard/summary ──────────────────────────────────────
  const globalTokensIn  = summary?.tokens_in       ?? 0;
  const globalTokensOut = summary?.tokens_out      ?? 0;
  const latencyP50      = summary?.latency_p50_ms  ?? 0;
  const anomalies       = summary?.anomalies       ?? {};
  const globalErrors    = anomalies.failed_step    ?? 0;

  // Consumo por agente: lo agrega el backend desde agent_run_steps (una sola petición).
  const AGENT_ORDER = ['investigador', 'redactor', 'revisor', 'formateador', 'publicador'];
  const agentAgg = (summary?.by_agent ?? [])
    .map(a => ({
      name: a.name, runs: a.runs, tokens: a.tokens_total,
      latencyMs: a.latency_ms, errors: a.errors,
    }))
    .sort((a, b) => (AGENT_ORDER.indexOf(a.name) + 99) - (AGENT_ORDER.indexOf(b.name) + 99));

  // Mapa de artículo para enriquecer la tabla con títulos del store
  const articleById = Object.fromEntries(articles.map(a => [String(a.id), a]));

  // Ejecuciones del proyecto (SPEC-029 / T17.1 / AC1): una fila por pasada del
  // pipeline. La tabla por artículo agrega, y al agregar funde las reejecuciones:
  // una segunda pasada desaparecía sumada a la primera.
  const executionRows = (summary?.executions ?? []).map(ex => ({
    ...ex,
    title: articleById[ex.article_id]?.title
      || t('metrics.articleFallback', { id: String(ex.article_id).slice(0, 8) }),
  }));

  // ── RENDER ───────────────────────────────────────────────────────────────────
  return (
    <div className="metrics-page">

      {/* CABECERA */}
      <div className="metrics-header">
        <div>
          <h2 className="metrics-title">{t('metrics.title')}</h2>
          <p className="metrics-subtitle">
            {t('metrics.subtitle')}
          </p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={loadSummary} disabled={loading}
          style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <RefreshCw size={14} style={loading ? { animation: 'spin 1s linear infinite' } : undefined} />
          {loading ? t('metrics.loading') : t('metrics.refresh')}
        </button>
      </div>

      {/* ERROR — arriba para que sea imposible ignorarlo */}
      {error && (
        <div style={{ padding: 'var(--space-4)', background: 'var(--error-tint)',
          border: '1px solid var(--error)', borderRadius: 'var(--radius-md)',
          color: 'var(--error)', fontSize: 'var(--font-size-sm)',
          display: 'flex', alignItems: 'center', gap: 8 }}>
          <XCircle size={16} style={{ flexShrink: 0 }} />
          {error}
        </div>
      )}

      {/* TILES GLOBALES (AC2 — cada tile dice qué cuenta y de dónde sale) */}
      <div className="metrics-tiles-grid">
        <StatTile icon={<Activity size={20} />}    label={t('metrics.tiles.tokens')}
          value={fmtNum(globalTokensIn + globalTokensOut)}
          sub={t('metrics.tiles.tokensSub', { in: fmtNum(globalTokensIn), out: fmtNum(globalTokensOut) })}
          color="var(--brand)"
          unavailable={!seccion('metrics').available} reason={seccion('metrics').reason} />
        <StatTile icon={<Clock size={20} />}        label={t('metrics.tiles.latency')}
          value={fmt(latencyP50)}
          sub={t('metrics.tiles.latencySub')}
          color="var(--agent-write)"
          unavailable={!seccion('metrics').available} reason={seccion('metrics').reason} />
        <StatTile icon={<FileText size={20} />}     label={t('metrics.tiles.articles')}
          value={summary?.articles_analyzed ?? 0}
          sub={t('metrics.tiles.articlesSub', { count: summary?.window_days ?? 7 })}
          color="var(--agent-format)"
          unavailable={!seccion('metrics').available} reason={seccion('metrics').reason} />
        <StatTile icon={<Zap size={20} />}          label={t('metrics.tiles.executions')}
          value={fmtNum(summary?.executions_total ?? 0)}
          sub={t('metrics.tiles.executionsSub')}
          color="var(--agent-review)"
          unavailable={!seccion('metrics').available} reason={seccion('metrics').reason} />
        <StatTile icon={<XCircle size={20} />}      label={t('metrics.tiles.failedSteps')}
          value={globalErrors}
          color={globalErrors > 0 ? 'var(--error)' : 'var(--success)'}
          unavailable={!seccion('metrics').available} reason={seccion('metrics').reason} />
        <StatTile icon={<AlertTriangle size={20} />} label={t('metrics.tiles.anomalies')}
          value={anomalies.total ?? 0}
          sub={anomalies.total === 0 ? t('metrics.conditionsChecked', { count: (anomalies.checks_applied || []).length }) : undefined}
          color={anomalies.total > 0 ? 'var(--warning)' : 'var(--success)'}
          unavailable={!seccion('metrics').available} reason={seccion('metrics').reason} />
      </div>

      {/* ESTADO DEL ENJAMBRE (AC4 — derivado de los pasos abiertos, no almacenado) */}
      <section>
        <h3 className="metrics-section-title">
          <Bot size={16} /> {t('metrics.swarm.title')}
        </h3>
        {!seccion('swarm').available ? (
          <div className="metrics-card" style={{ padding: 'var(--space-5)', textAlign: 'center',
            color: 'var(--text-muted)', fontSize: 'var(--font-size-sm)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
            <CloudOff size={16} />
            {seccion('swarm').reason
              ? t('metrics.swarm.unavailableReason', { reason: seccion('swarm').reason })
              : t('metrics.swarm.unavailable')}
          </div>
        ) : (
          <>
            <div className="metrics-swarm-grid">
              {(summary?.swarm?.agents ?? []).map(a => <SwarmAgent key={a.name} agent={a} />)}
            </div>
            <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)',
              marginTop: 'var(--space-2)' }}>
              {t('metrics.swarm.noteBefore')} <code>agent_runs</code>{t('metrics.swarm.noteAfter', { min: Math.round((summary?.swarm?.stale_after_s ?? 900) / 60) })}
            </p>
          </>
        )}
      </section>

      {/* ANOMALÍAS (AC3 — el cero tiene semántica: se verificó y no se encontró) */}
      {anomalies.checks_applied && (
        <section>
          <h3 className="metrics-section-title">
            <AlertTriangle size={16} /> {t('metrics.anomaliesTitle', { count: anomalies.checks_applied.length })}
          </h3>
          <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
            {[
              { key: 'failed_step',      label: t('metrics.anomaly.failed_step'),    desc: t('metrics.anomaly.failed_step_desc') },
              { key: 'loop_exhausted',   label: t('metrics.anomaly.loop_exhausted'), desc: t('metrics.anomaly.loop_exhausted_desc', { max: summary?.budgets?.max_review_loops ?? 3 }) },
              { key: 'latency_exceeded', label: t('metrics.anomaly.latency_exceeded'), desc: t('metrics.anomaly.latency_exceeded_desc', { seconds: ((summary?.budgets?.latency_budget_ms ?? 60000)/1000).toFixed(0) }) },
              { key: 'rag_empty',        label: t('metrics.anomaly.rag_empty'),      desc: t('metrics.anomaly.rag_empty_desc') },
            ].map(({ key, label, desc }) => (
              <div key={key} style={{
                padding: 'var(--space-3) var(--space-4)',
                background: 'var(--bg-card)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                minWidth: 160,
              }}>
                <div style={{ fontSize: 'var(--font-size-xl)', fontWeight: 700,
                  color: (anomalies[key] ?? 0) > 0 ? 'var(--error)' : 'var(--success)' }}>
                  {anomalies[key] ?? 0}
                </div>
                <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--text-heading)' }}>{label}</div>
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>{desc}</div>
              </div>
            ))}
          </div>
          <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', marginTop: 'var(--space-2)' }}>
            {t('metrics.zeroMeaning', { count: summary?.window_days ?? 7 })}
          </p>
        </section>
      )}

      {/* CONSUMO POR AGENTE — tarjetas */}
      {agentAgg.length > 0 && (
        <section>
          <h3 className="metrics-section-title">
            <BarChart2 size={16} /> {t('metrics.consumption')}
          </h3>
          <div className="metrics-agent-cards">
            {agentAgg.map(a => <AgentCard key={a.name} data={a} />)}
          </div>
        </section>
      )}

      {/* EJECUCIONES DEL PROYECTO (T17.1 / AC1) — una fila por pasada */}
      <section>
        <h3 className="metrics-section-title">
          <Activity size={16} /> {t('metrics.perArticle')}
        </h3>
        <div className="metrics-card">
          <div className="metrics-exec-thead">
            <span>{t('metrics.col.execution')}</span>
            <span>{t('metrics.col.when')}</span>
            <span>{t('metrics.col.agents')}</span>
            <span>{t('metrics.col.steps')}</span>
            <span>{t('metrics.col.tokens')}</span>
            <span>{t('metrics.col.latency')}</span>
            <span className="metrics-exec-state-heading">{t('metrics.col.state')}</span>
            <span aria-hidden="true" />
          </div>

          {!seccion('executions').available ? (
            <div style={{ padding: 'var(--space-5)', textAlign: 'center',
              color: 'var(--text-muted)', fontSize: 'var(--font-size-sm)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              <CloudOff size={16} />
              {seccion('executions').reason
                ? t('metrics.executionsUnavailableReason', { reason: seccion('executions').reason })
                : t('metrics.executionsUnavailable')}
            </div>
          ) : executionRows.length === 0 ? (
            <div style={{ padding: 'var(--space-5)', textAlign: 'center',
              color: 'var(--text-muted)', fontSize: 'var(--font-size-sm)' }}>
              {t('metrics.noExecutions', { count: summary?.window_days ?? 7 })}
            </div>
          ) : executionRows.map(ex => (
            <div key={ex.execution_id} className="metrics-exec-row">
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 500, fontSize: 'var(--font-size-sm)',
                  color: 'var(--text-heading)', overflow: 'hidden',
                  textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {ex.title}
                </div>
                {/* «2 de 3» distingue una reejecución de un retroceso inexplicado */}
                {ex.runs_total > 1 && (
                  <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--agent-write)' }}>
                    {t('metrics.passOf', { n: ex.run_number, total: ex.runs_total })}
                  </span>
                )}
              </div>

              <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                {fmtFecha(ex.started_at)}
              </span>

              <span style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                {(ex.agents_run || []).map(n => {
                  const Icono = agentMeta(n)?.icon;
                  return Icono
                    ? <span key={n} role="img" aria-label={agentMeta(n)?.label || n} title={agentMeta(n)?.label || n}>
                      <Icono size={14} strokeWidth={1.5} style={{ color: agentColor(n) }} aria-hidden="true" />
                    </span>
                    : <span key={n} style={{ fontSize: 'var(--font-size-xs)' }}>{n.slice(0, 3)}</span>;
                })}
              </span>

              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--font-size-xs)' }}>
                {ex.steps}
                {ex.loops > 0 && (
                  <span style={{ color: 'var(--agent-write)' }}> · {t('metrics.loops', { count: ex.loops })}</span>
                )}
              </span>

              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--font-size-xs)' }}>
                {fmtNum(ex.tokens_total)}
              </span>

              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--font-size-xs)' }}>
                {fmtSeg(ex.latency_ms)}
              </span>

              <div className="metrics-exec-state">
                {ex.status === 'failed' ? (
                  <span className="metrics-exec-status metrics-exec-status-failed"
                    role="img" aria-label={t('metrics.status.failed')} title={t('metrics.status.failed')}>
                    <XCircle size={16} strokeWidth={1.5} aria-hidden="true" />
                  </span>
                ) : ex.status === 'running' ? (
                  <span className="metrics-exec-status metrics-exec-status-running" title={t('metrics.status.running')}>
                    <Clock size={15} strokeWidth={1.5} aria-hidden="true" />
                    <span>{t('metrics.status.running')}</span>
                  </span>
                ) : (
                  <>
                    <span className="metrics-exec-status metrics-exec-status-complete"
                      role="img" aria-label={t('metrics.status.completed')} title={t('metrics.status.completed')}>
                      <CheckCircle size={16} strokeWidth={1.5} aria-hidden="true" />
                    </span>
                    {ex.recovered_failures > 0 && (
                      <small className="metrics-exec-recovered">
                        {t('metrics.recovered', { count: ex.recovered_failures })}
                      </small>
                    )}
                  </>
                )}
              </div>
              <span className="metrics-exec-actions">
                <button className="btn btn-secondary btn-sm"
                  aria-label={t('metrics.viewTracesAria', { title: ex.title, n: ex.run_number })}
                  onClick={() => navigate(`/dashboard/articles/${ex.article_id}/observability${ex.trace_id ? `?execution=${ex.trace_id}` : ''}`)}>
                  {t('metrics.traces')}
                </button>
              </span>
            </div>
          ))}
        </div>
      </section>

      {loading && !summary && (
        <div style={{ display: 'grid', placeItems: 'center', padding: 'var(--space-8)' }}>
          <LoadingState label={t('metrics.loadingMetrics')} />
        </div>
      )}


    </div>
  );
}
