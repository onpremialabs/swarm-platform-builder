import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { agentMeta } from '../catalog';
import { dashboardApi } from '../../../platform/api/dashboard';
import { useArticleStore } from '../store/articleStore';
import { EmptyState, LoadingState } from '../../../platform/components/ui/states';
import {
  Activity, BarChart2, Clock, FileText, RefreshCw,
  TrendingUp, XCircle, CheckCircle, Zap, ChevronDown, ChevronRight,
  AlertTriangle,
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

const STATUS_LABEL = {
  draft: 'Borrador', published: 'Publicado', failed: 'Fallido',
  generating: 'Generando', review: 'En revisión',
};

const STATUS_CLS = {
  published: 'badge-approved', failed: 'badge-error',
  generating: 'badge-running', review: 'badge-pending',
  draft: 'badge-draft',
};

/** Color del agente según el catálogo del proyecto; gris si no está. */
const agentColor = (name) => agentMeta(name)?.color || 'var(--text-muted)';

// ─── Tile global ──────────────────────────────────────────────────────────────

function StatTile({ icon, label, value, sub, color }) {
  return (
    <div className="metrics-stat-tile">
      <span className="metrics-stat-icon" style={{ color: color || 'var(--brand)' }}>{icon}</span>
      <div>
        <div className="metrics-stat-value">{value}</div>
        <div className="metrics-stat-label">{label}</div>
        {sub && <div className="metrics-stat-sub">{sub}</div>}
      </div>
    </div>
  );
}

// ─── Barra proporcional ───────────────────────────────────────────────────────

function Bar({ value, max, color }) {
  const pct = max > 0 ? Math.min(100, Math.round(value / max * 100)) : 0;
  return (
    <div style={{ height: 5, background: 'var(--bg-inset)', borderRadius: 'var(--radius-pill)', width: '100%', minWidth: 60 }}>
      <div style={{
        width: `${pct}%`, height: '100%',
        background: color || 'var(--brand)',
        borderRadius: 'var(--radius-pill)',
        transition: 'width .3s',
      }} />
    </div>
  );
}

// ─── Tarjeta de agente ────────────────────────────────────────────────────────

function AgentCard({ data }) {
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
          ? <span className="badge badge-error" style={{ fontSize: 10 }}>{data.errors} error{data.errors !== 1 ? 'es' : ''}</span>
          : <CheckCircle size={14} style={{ color: 'var(--success)' }} />}
      </div>

      <div className="metrics-agent-card-stats">
        <div className="metrics-agent-stat">
          <span className="metrics-agent-stat-label">Ejecuciones</span>
          <span className="metrics-agent-stat-val">{fmtNum(data.runs)}</span>
        </div>
        <div className="metrics-agent-stat">
          <span className="metrics-agent-stat-label">Tokens totales</span>
          <span className="metrics-agent-stat-val">{fmtNum(data.tokens)}</span>
        </div>
        <div className="metrics-agent-stat">
          <span className="metrics-agent-stat-label">Latencia media</span>
          <span className="metrics-agent-stat-val">{fmtSeg(avgLat)}</span>
        </div>
        <div className="metrics-agent-stat">
          <span className="metrics-agent-stat-label">Latencia total</span>
          <span className="metrics-agent-stat-val">{fmtSeg(data.latencyMs)}</span>
        </div>
      </div>
    </div>
  );
}

// ─── Página ───────────────────────────────────────────────────────────────────

export default function MetricsDashboardPage() {
  const navigate = useNavigate();
  const { articles, fetchArticles } = useArticleStore();

  // summary viene del endpoint /dashboard/summary (una sola petición, aislada por proyecto)
  const [summary, setSummary]     = useState(null);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState(null);
  const [expanded, setExpanded]   = useState({});
  const [sortField, setSortField] = useState('tokens');

  const loadSummary = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await dashboardApi.getSummary();
      setSummary(data);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Error al cargar métricas');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchArticles({ limit: 200 }); }, []); // eslint-disable-line
  useEffect(() => { loadSummary(); }, []); // eslint-disable-line

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

  // Filas de artículos desde summary.articles (AC5 — estado real del pipeline)
  const summaryArticles = summary?.articles ?? [];
  const articleRows = summaryArticles
    .map(sa => {
      const art = articleById[sa.article_id] || {};
      const tokens    = sa.tokens_total ?? 0;
      const latencyMs = sa.latency_ms ?? 0;
      const failed    = sa.failed ?? false;

      return {
        id: sa.article_id,
        title: art.title || `Artículo ${sa.article_id?.slice(0, 8)}`,
        status: art.status || 'draft',
        tokens, latencyMs, errors: failed ? 1 : 0,
        agentBreakdown: Object.fromEntries(
          (sa.agents || []).map(a => [a.name, {
            tokens: a.tokens_total, latencyMs: a.latency_ms, runs: a.runs,
          }])
        ),
        hasMetrics: true,
        last_run: sa.last_run,
      };
    })
    .sort((a, b) => {
      if (sortField === 'tokens')  return b.tokens    - a.tokens;
      if (sortField === 'latency') return b.latencyMs - a.latencyMs;
      if (sortField === 'errors')  return b.errors    - a.errors;
      return 0;
    });

  const maxTokens  = Math.max(...articleRows.map(r => r.tokens),    1);
  const maxLatency = Math.max(...articleRows.map(r => r.latencyMs), 1);

  // Ejecuciones del proyecto (SPEC-029 / T17.1 / AC1): una fila por pasada del
  // pipeline. La tabla por artículo agrega, y al agregar funde las reejecuciones:
  // una segunda pasada desaparecía sumada a la primera.
  const executionRows = (summary?.executions ?? []).map(ex => ({
    ...ex,
    title: articleById[ex.article_id]?.title
      || `Artículo ${String(ex.article_id).slice(0, 8)}`,
  }));

  // ── RENDER ───────────────────────────────────────────────────────────────────
  return (
    <div className="metrics-page">

      {/* CABECERA */}
      <div className="metrics-header">
        <div>
          <h2 className="metrics-title">Trazabilidad del proyecto</h2>
          <p className="metrics-subtitle">
            Consumo, latencia y trazas de todos los artículos generados.
          </p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={loadSummary} disabled={loading}
          style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <RefreshCw size={14} style={loading ? { animation: 'spin 1s linear infinite' } : undefined} />
          {loading ? 'Cargando…' : 'Actualizar métricas'}
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
        <StatTile icon={<Activity size={20} />}    label="Tokens totales (7 días)"
          value={fmtNum(globalTokensIn + globalTokensOut)}
          sub={`↑ ${fmtNum(globalTokensIn)} entrada  ·  ↓ ${fmtNum(globalTokensOut)} salida`}
          color="var(--brand)" />
        <StatTile icon={<Clock size={20} />}        label="Latencia p50 por paso de agente"
          value={fmt(latencyP50)}
          sub="Mediana de agent_run_steps (no HTTP)"
          color="var(--agent-write)" />
        <StatTile icon={<FileText size={20} />}     label="Artículos con ejecución"
          value={summary?.articles_analyzed ?? 0}
          sub={`en los últimos ${summary?.window_days ?? 7} días`}
          color="var(--agent-format)" />
        <StatTile icon={<Zap size={20} />}          label="Ejecuciones de pipeline"
          value={fmtNum(summary?.executions_total ?? 0)}
          sub="pasadas completas, no pasos"
          color="var(--agent-review)" />
        <StatTile icon={<XCircle size={20} />}      label="Pasos con error"
          value={globalErrors}
          color={globalErrors > 0 ? 'var(--error)' : 'var(--success)'} />
        <StatTile icon={<AlertTriangle size={20} />} label="Anomalías detectadas"
          value={anomalies.total ?? 0}
          sub={anomalies.total === 0 ? `${(anomalies.checks_applied || []).length} condiciones verificadas` : undefined}
          color={anomalies.total > 0 ? 'var(--warning)' : 'var(--success)'} />
      </div>

      {/* ANOMALÍAS (AC3 — el cero tiene semántica: se verificó y no se encontró) */}
      {anomalies.checks_applied && (
        <section>
          <h3 className="metrics-section-title">
            <AlertTriangle size={16} /> Anomalías — {anomalies.checks_applied.length} condiciones verificadas
          </h3>
          <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
            {[
              { key: 'failed_step',      label: 'Pasos fallidos',           desc: 'status ≠ completed' },
              { key: 'loop_exhausted',   label: 'Bucles agotados',          desc: `iteration ≥ ${summary?.budgets?.max_review_loops ?? 3}` },
              { key: 'latency_exceeded', label: 'Latencia excedida',        desc: `> ${((summary?.budgets?.latency_budget_ms ?? 60000)/1000).toFixed(0)} s por paso` },
              { key: 'rag_empty',        label: 'Pasos sin recuperación RAG', desc: 'rag_sources vacío' },
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
            Un contador en 0 significa «se comprobó esta condición en los últimos {summary?.window_days ?? 7} días y no se encontró ningún caso».
          </p>
        </section>
      )}

      {/* CONSUMO POR AGENTE — tarjetas */}
      {agentAgg.length > 0 && (
        <section>
          <h3 className="metrics-section-title">
            <BarChart2 size={16} /> Consumo acumulado por agente
          </h3>
          <div className="metrics-agent-cards">
            {agentAgg.map(a => <AgentCard key={a.name} data={a} />)}
          </div>
        </section>
      )}

      {/* EJECUCIONES DEL PROYECTO (T17.1 / AC1) — una fila por pasada */}
      <section>
        <h3 className="metrics-section-title">
          <Activity size={16} /> Ejecuciones del proyecto
        </h3>
        <div className="metrics-card">
          <div className="metrics-exec-thead">
            <span>Ejecución</span>
            <span>Cuándo</span>
            <span>Agentes</span>
            <span>Pasos</span>
            <span>Tokens</span>
            <span>Latencia</span>
            <span>Estado</span>
          </div>

          {executionRows.length === 0 ? (
            <div style={{ padding: 'var(--space-5)', textAlign: 'center',
              color: 'var(--text-muted)', fontSize: 'var(--font-size-sm)' }}>
              Sin ejecuciones en los últimos {summary?.window_days ?? 7} días.
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
                    pasada {ex.run_number} de {ex.runs_total}
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
                    ? <Icono key={n} size={13} style={{ color: agentColor(n) }} />
                    : <span key={n} style={{ fontSize: 'var(--font-size-xs)' }}>{n.slice(0, 3)}</span>;
                })}
              </span>

              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--font-size-xs)' }}>
                {ex.steps}
                {ex.loops > 0 && (
                  <span style={{ color: 'var(--agent-write)' }}> · {ex.loops} bucle{ex.loops !== 1 ? 's' : ''}</span>
                )}
              </span>

              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--font-size-xs)' }}>
                {fmtNum(ex.tokens_total)}
              </span>

              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--font-size-xs)' }}>
                {fmtSeg(ex.latency_ms)}
              </span>

              <span style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
                {ex.status === 'failed'
                  ? <span className="badge badge-error" style={{ fontSize: 10 }}>Fallida</span>
                  : ex.status === 'running'
                    ? <span className="badge badge-running" style={{ fontSize: 10 }}>En curso</span>
                    : <CheckCircle size={15} style={{ color: 'var(--success)' }} />}
                <button className="btn btn-ghost btn-sm"
                  style={{ fontSize: 'var(--font-size-xs)', padding: '3px 8px' }}
                  onClick={() => navigate(`/dashboard/execution/${ex.article_id}`, { state: {} })}>
                  Trazas
                </button>
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* TABLA DE ARTÍCULOS */}
      <section>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-3)' }}>
          <h3 className="metrics-section-title" style={{ margin: 0 }}>
            <FileText size={16} /> Métricas por artículo
          </h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>Ordenar:</span>
            {[
              { id: 'tokens',  label: 'Tokens' },
              { id: 'latency', label: 'Latencia' },
              { id: 'errors',  label: 'Errores' },
            ].map(opt => (
              <button key={opt.id}
                className="btn btn-ghost btn-sm"
                style={{
                  fontSize: 'var(--font-size-xs)', padding: '2px 10px',
                  background: sortField === opt.id ? 'var(--brand-tint)' : undefined,
                  color:      sortField === opt.id ? 'var(--brand)'      : undefined,
                }}
                onClick={() => setSortField(opt.id)}>
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {articles.length === 0 ? (
          <EmptyState icon={<FileText size={28} />} title="Sin artículos"
            description="Genera artículos desde el Flow Designer para ver sus métricas aquí." />
        ) : (
          <div className="metrics-card">
            {/* Cabecera de la tabla */}
            <div className="metrics-art-thead">
              <span>Artículo</span>
              <span>Tokens</span>
              <span>Latencia</span>
              <span>Errores</span>
              <span></span>
            </div>

            {articleRows.length === 0 && (
              <div style={{ padding: 'var(--space-5)', textAlign: 'center',
                color: 'var(--text-muted)', fontSize: 'var(--font-size-sm)' }}>
                No hay ejecuciones registradas en los últimos {summary?.window_days ?? 7} días.
                Ejecuta un artículo desde el Flow Designer para ver sus métricas aquí.
              </div>
            )}
            {articleRows.map(row => (
              <div key={row.id} className="metrics-art-item">

                {/* Fila principal */}
                <div
                  className="metrics-art-row"
                  onClick={() => row.hasMetrics && setExpanded(e => ({ ...e, [row.id]: !e[row.id] }))}
                  style={{ cursor: row.hasMetrics ? 'pointer' : 'default' }}
                >
                  {/* Título + estado */}
                  <div>
                    <div style={{ fontWeight: 500, fontSize: 'var(--font-size-sm)', color: 'var(--text-heading)',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 280 }}>
                      {row.title || `Artículo ${row.id.slice(0, 8)}`}
                    </div>
                    <span className={`badge ${STATUS_CLS[row.status] || 'badge-draft'}`} style={{ fontSize: 10, marginTop: 3 }}>
                      {STATUS_LABEL[row.status] || row.status || 'Borrador'}
                    </span>
                  </div>

                  {/* Tokens */}
                  <div>
                    {row.hasMetrics ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 'var(--font-size-sm)' }}>
                          {fmtNum(row.tokens)}
                        </span>
                        <Bar value={row.tokens} max={maxTokens} color="var(--brand)" />
                      </div>
                    ) : <span style={{ color: 'var(--text-muted)', fontSize: 'var(--font-size-xs)' }}>—</span>}
                  </div>

                  {/* Latencia */}
                  <div>
                    {row.hasMetrics ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 'var(--font-size-sm)' }}>
                          {fmt(row.latencyMs)}
                        </span>
                        <Bar value={row.latencyMs} max={maxLatency} color="var(--agent-research)" />
                      </div>
                    ) : <span style={{ color: 'var(--text-muted)', fontSize: 'var(--font-size-xs)' }}>—</span>}
                  </div>

                  {/* Errores */}
                  <div style={{ display: 'flex', justifyContent: 'center' }}>
                    {row.hasMetrics
                      ? (row.errors > 0
                        ? <span style={{ color: 'var(--error)', fontWeight: 700, fontSize: 'var(--font-size-sm)' }}>{row.errors}</span>
                        : <CheckCircle size={16} style={{ color: 'var(--success)' }} />)
                      : <span style={{ color: 'var(--text-muted)', fontSize: 'var(--font-size-xs)' }}>—</span>}
                  </div>

                  {/* Acciones */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
                    <button className="btn btn-ghost btn-sm"
                      style={{ fontSize: 'var(--font-size-xs)', padding: '3px 8px' }}
                      onClick={e => { e.stopPropagation(); navigate(`/dashboard/execution/${row.id}`, { state: {} }); }}>
                      <Activity size={12} /> Trazas
                    </button>
                    {row.hasMetrics && (
                      expanded[row.id]
                        ? <ChevronDown size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                        : <ChevronRight size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                    )}
                  </div>
                </div>

                {/* Desglose por agente (desplegable) */}
                {expanded[row.id] && Object.keys(row.agentBreakdown).length > 0 && (
                  <div className="metrics-art-breakdown">
                    <div className="metrics-art-breakdown-head">
                      <span>Agente</span><span>Tokens</span><span>Latencia</span><span>Pasos</span>
                    </div>
                    {Object.entries(row.agentBreakdown).map(([name, ag]) => {
                      const meta  = agentMeta(name) || {};
                      const Icono = meta.icon;
                      return (
                        <div key={name} className="metrics-art-breakdown-row">
                          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            {Icono && <Icono size={13} style={{ color: agentColor(name), flexShrink: 0 }} />}
                            <span style={{ fontSize: 'var(--font-size-xs)', fontWeight: 500 }}>{meta.label || name}</span>
                          </span>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                            {fmtNum(ag.tokens)}
                          </span>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                            {fmtSeg(ag.latencyMs)}
                          </span>
                          <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
                            {ag.runs}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}

              </div>
            ))}
          </div>
        )}
      </section>

      {loading && !summary && (
        <div style={{ display: 'grid', placeItems: 'center', padding: 'var(--space-8)' }}>
          <LoadingState label="Cargando métricas…" />
        </div>
      )}


    </div>
  );
}
