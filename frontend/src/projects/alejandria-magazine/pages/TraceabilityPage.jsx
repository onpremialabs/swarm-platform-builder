import React, { useCallback, useEffect, useRef, useState } from 'react';
import { agentMeta } from '../catalog';
import { EmptyState } from '../../../platform/components/ui/states';
import { Navigate, useParams, useLocation, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import {
  CheckCircle, XCircle, Clock, Loader, ArrowLeft, FileText, UserPlus,
  Square, Upload, Play, AlertTriangle, BarChart2, GitBranch, Activity,
  ShieldCheck, ShieldAlert, Download, Info,
} from 'lucide-react';
import { agentsApi } from '../../../platform/api/agents';
import { useArticleStore } from '../store/articleStore';
import toast from 'react-hot-toast';
import { agentLabel, CRITERION_LABELS } from '../gate';
import ExplainPanel from '../../../platform/components/explain/ExplainPanel';

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatDuration(ms) {
  if (!ms || ms <= 0) return '—';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1).replace('.', ',')} s`;
  return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
}

function formatDurationLive(ms) {
  if (!ms || ms <= 0) return '0 s';
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s} s`;
  return `${Math.floor(s / 60)} min ${s % 60} s`;
}

const STATUS_LABEL = { waiting: 'Pendiente', running: 'En ejecución', completed: 'Completado', failed: 'Error' };

/** Color del agente según el catálogo del proyecto; el de marca si no está. */
const agentColor = (name) => agentMeta(name)?.color || 'var(--brand)';

// ─── Gráfico de barras SVG ───────────────────────────────────────────────────

function BarChart({ data, unit }) {
  if (!data || data.length === 0) return (
    <div style={{ color: 'var(--text-muted)', fontSize: 'var(--font-size-xs)', padding: '12px 0' }}>Sin datos</div>
  );
  const max = Math.max(...data.map(d => d.value), 1);
  const barH = 22, gap = 10, labelW = 90, chartW = 180;
  const totalH = data.length * (barH + gap);
  return (
    <svg width="100%" viewBox={`0 0 ${labelW + chartW + 80} ${totalH}`} style={{ overflow: 'visible' }}>
      {data.map((d, i) => {
        const y = i * (barH + gap);
        const barW = Math.max(2, (d.value / max) * chartW);
        const displayVal = unit === 'ms' ? formatDuration(d.value) : d.value.toLocaleString('es-ES');
        return (
          <g key={d.name}>
            <text x={labelW - 6} y={y + barH * 0.72} textAnchor="end"
              fontSize="11" fill="var(--text-secondary)" fontFamily="var(--font-sans)">
              {d.label || d.name}
            </text>
            <rect x={labelW} y={y} width={barW} height={barH}
              fill={agentColor(d.name)} rx="4" opacity="0.9" />
            <text x={labelW + barW + 6} y={y + barH * 0.72}
              fontSize="11" fill="var(--text-muted)" fontFamily="var(--font-sans)">
              {displayVal}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function MetricTile({ icon, label, value, color }) {
  return (
    <div className="trace-metric-tile">
      <span className="trace-metric-icon" style={{ color: color || 'var(--brand)' }}>{icon}</span>
      <div>
        <div className="trace-metric-label">{label}</div>
        <div className="trace-metric-value">{value}</div>
      </div>
    </div>
  );
}

// ─── Componente principal ────────────────────────────────────────────────────

export default function TraceabilityPage() {
  const { articleId } = useParams();
  const location = useLocation();
  return location.state?.flowSequence?.length
    ? <LiveTraceabilityPage />
    : <Navigate to={`/dashboard/articles/${articleId}/observability`} replace />;
}

function LiveTraceabilityPage() {
  const { articleId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { fetchArticle, assignReviewer } = useArticleStore();

  const flowSequence       = location.state?.flowSequence || [];
  const returnToTraceability = location.state?.returnTo === '/dashboard/traceability' || flowSequence.length === 0;
  const agentSettings      = location.state?.agentSettings || {};
  const runKeywords        = location.state?.keywords || [];
  const contextDescription = location.state?.contextDescription || '';
  const articleOutline     = location.state?.articleOutline || '';
  // Parámetros de esta ejecución (SPEC-030 / T18.5). Viajan en el estado de
  // navegación como el resto: el lienzo los recoge y la ejecución los usa.
  const swarmNotes       = location.state?.swarmNotes || '';
  const referenceDocId   = location.state?.referenceDocId || null;
  const formatMode       = location.state?.formatMode || 'rag';

  // ── Estado de ejecución ──
  const [steps, setSteps] = useState(
    flowSequence.map(id => ({ id, status: 'waiting', output: '' }))
  );
  // iterationCount: cuántas veces ha arrancado cada agente — detecta el bucle revisor→redactor.
  const [iterationCount, setIterationCount] = useState({});
  // Progreso fraccional por agente, solo para quien lo emite (T18.4 / AC5).
  const [agentProgress, setAgentProgress] = useState({});
  // Llegamos a una ejecución ya en marcha, sin haberla lanzado desde el lienzo.
  const [recuperada, setRecuperada] = useState(false);
  const [logs, setLogs]         = useState([]);
  const [preview, setPreview]   = useState('');
  const [done, setDone]         = useState(false);
  const [pipelineFailed, setPipelineFailed] = useState(false);
  const [canResume, setCanResume]           = useState(false);
  const [cancelled, setCancelled]           = useState(false);
  const [cancelling, setCancelling]         = useState(false);
  const [runCount, setRunCount]             = useState(0);
  const [hasPublicador]                     = useState(flowSequence.includes('publicador'));
  const [reviewerEmail, setReviewerEmail]   = useState('');
  const [assigning, setAssigning]           = useState(false);
  const [pendingDecision, setPendingDecision] = useState(null);
  const [gateNotice, setGateNotice]           = useState(null);
  const [decisionBusy, setDecisionBusy]       = useState(false);
  const [agentTimings, setAgentTimings]       = useState({});
  const [elapsed, setElapsed]                 = useState('—');
  const [startTimeMs, setStartTimeMs]         = useState(null);
  const [executionDate, setExecutionDate]     = useState(null);

  // ── Estado de trazabilidad ──
  const [activeTab, setActiveTab]       = useState('realtime');
  const [traceData, setTraceData]       = useState(null);
  const [traceLoading, setTraceLoading] = useState(false);
  const [traceRefreshKey, setTraceRefreshKey] = useState(0);

  // ── Integridad (SPEC-029 / T17.3, T17.6) ──
  const [integrity, setIntegrity]           = useState(null);
  const [integrityLoading, setIntegrityLoading] = useState(false);
  const [integrityError, setIntegrityError] = useState(null);
  const [exporting, setExporting]           = useState(false);

  // ── Refs ──
  const sourceInputRef  = useRef(null);
  const logsEndRef      = useRef(null);
  const evtSourceRef    = useRef(null);
  const pipelineStarted = useRef(false);
  const resumeRef       = useRef(false);
  const currentAgentRef = useRef(null);
  const startTimeMsRef  = useRef(null);

  const hasFailedSteps      = steps.some(s => s.status === 'failed');
  const isGeneratingPreview = !done && steps.some(s => s.status === 'running');

  const markStepStatus = (agentId, status, output = undefined) =>
    setSteps(cur => cur.map(s =>
      s.id !== agentId ? s : (output === undefined ? { ...s, status } : { ...s, status, output })
    ));

  const addLog = (msg, type = '', agent = null) =>
    setLogs(l => [...l, { msg, type, agent, ts: new Date().toLocaleTimeString(), tsMs: Date.now() }]);

  // ── Timer de duración ──
  useEffect(() => {
    if (!startTimeMs || done) return;
    const id = setInterval(() => setElapsed(formatDurationLive(Date.now() - startTimeMs)), 1000);
    return () => clearInterval(id);
  }, [startTimeMs, done]);

  useEffect(() => { logsEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [logs]);

  // ── Carga de trazas ──
  const loadTrace = useCallback(async () => {
    if (!articleId) return;
    setTraceLoading(true);
    try {
      const data = await agentsApi.getExplain(articleId);
      setTraceData(data);
    } catch { /* mejor-esfuerzo: traza en modo degradado, la vista queda vacía */ }
    finally { setTraceLoading(false); }
  }, [articleId]);

  // Al montar sin estado de navegación hay **dos** situaciones distintas, y
  // antes se trataban como una sola: puede que el artículo no esté ejecutando
  // nada —modo histórico, correcto— o puede que sí lo esté y simplemente
  // hayamos perdido la secuencia al cambiar de pestaña. Esa segunda caía en
  // histórico y no había forma de volver a mirar la ejecución en curso.
  //
  // Se le pregunta al servidor, que es quien lo sabe (SPEC-030 / T18.7).
  useEffect(() => {
    if (flowSequence.length > 0) return;   // venimos del lienzo: ya hay estado

    let cancelado = false;
    (async () => {
      try {
        const estado = await agentsApi.getRunStatus(articleId);
        if (cancelado) return;
        if (estado?.running && (estado.flow_sequence || []).length > 0) {
          // Se reconstruyen las tarjetas y el SSE engancha solo: los eventos
          // siguen llegando desde que se suscribe.
          setSteps(estado.flow_sequence.map(id => ({
            id,
            status: id === estado.current_agent ? 'running' : 'waiting',
            output: '',
          })));
          setRecuperada(true);
          if (estado.started_at) {
            const inicio = new Date(estado.started_at).getTime();
            if (!Number.isNaN(inicio)) startTimeMsRef.current = inicio;
          }
          addLog('Reconectado a una ejecución en curso', 'info', null);
          return;
        }
      // mejor-esfuerzo: si no se puede preguntar, se cae al modo histórico, que
      // es lo que había antes de esto y sigue siendo útil.
      } catch { }
      if (!cancelado) loadTrace();
    })();

    return () => { cancelado = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Recargar al finalizar + incrementar key de ExplainPanel
  useEffect(() => {
    if (done) {
      setTraceRefreshKey(k => k + 1);
      loadTrace();
    }
  }, [done, loadTrace]);

  const loadIntegrity = useCallback(async () => {
    if (!articleId) return;
    setIntegrityLoading(true);
    setIntegrityError(null);
    try {
      setIntegrity(await agentsApi.getIntegrity(articleId));
    } catch (e) {
      // No es mejor-esfuerzo: si la verificación no se pudo hacer hay que
      // decirlo. Enseñar «sin problemas» cuando no se comprobó nada sería la
      // confianza infundada que T17.6 existe para evitar.
      setIntegrityError(e?.response?.data?.detail || 'No se pudo verificar la cadena');
    } finally {
      setIntegrityLoading(false);
    }
  }, [articleId]);

  const handleExport = async () => {
    setExporting(true);
    try { await agentsApi.downloadExport(articleId, 'last'); }
    catch { toast.error('No se pudo exportar la traza'); }
    finally { setExporting(false); }
  };

  // Cargar al entrar a métricas si aún no hay datos
  useEffect(() => {
    if (activeTab === 'metrics' && !traceData && !traceLoading) loadTrace();
    if (activeTab === 'integrity' && !integrity && !integrityLoading) loadIntegrity();
  }, [activeTab, traceData, traceLoading, loadTrace]);

  // Fallback preview
  useEffect(() => {
    // mejor-esfuerzo: preview al completar; si falla, el texto se carga al reabrir el artículo
    if (done && !preview)
      fetchArticle(articleId).then(art => { if (art?.body) setPreview(art.body); }).catch(() => {});
  }, [done]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── SSE ──
  useEffect(() => {
    if (!articleId) return;
    let isCancelled = false;
    let evtSource;

    (async () => {
      let ticket;
      try { const res = await agentsApi.getStreamTicket(articleId); ticket = res?.ticket; }
      catch { addLog('No se pudo autenticar el stream', 'error'); return; }
      if (isCancelled || !ticket) return;

      evtSource = new EventSource(agentsApi.getStreamUrl(articleId, ticket));
      evtSourceRef.current = evtSource;

      evtSource.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);

          if (data.type === 'agent_start') {
            if (!startTimeMsRef.current) {
              const now = Date.now();
              startTimeMsRef.current = now;
              setStartTimeMs(now);
              setExecutionDate(new Date().toLocaleString('es-ES', {
                day: '2-digit', month: 'short', year: 'numeric',
                hour: '2-digit', minute: '2-digit',
              }));
            }
            currentAgentRef.current = data.agent;
            // Rastrear iteraciones del bucle revisor→redactor (T18.6 AC4)
            setIterationCount(prev => {
              const count = (prev[data.agent] || 0) + 1;
              if (data.agent === 'redactor' && count > 1) {
                // Segunda vuelta o más: informar explícitamente al usuario (AC4)
                addLog(`Redactor: pasada ${count} del bucle revisor→redactor`, 'warn', data.agent);
              } else {
                addLog(`${data.agent} iniciado`, 'info', data.agent);
              }
              return { ...prev, [data.agent]: count };
            });
            setAgentTimings(prev => ({ ...prev, [data.agent]: { startMs: Date.now(), durationMs: null } }));
            markStepStatus(data.agent, 'running');
            if (data.agent === 'redactor' || data.agent === 'formateador') setPreview('');

          } else if (data.type === 'token') {
            setPreview(cur => cur + data.token);

          } else if (data.type === 'progress') {
            // Progreso fraccional (T18.4 / AC5). Solo lo emite quien conoce sus
            // unidades reales; los demás no mandan nada y se quedan
            // indeterminados, que es la respuesta honesta.
            setAgentProgress(prev => ({
              ...prev,
              [data.agent]: { current: data.current, total: data.total, unit: data.unit || '' },
            }));

          } else if (data.type === 'agent_end') {
            setAgentTimings(prev => {
              const ag = prev[data.agent] || {};
              return { ...prev, [data.agent]: { ...ag, durationMs: ag.startMs ? Date.now() - ag.startMs : null } };
            });
            currentAgentRef.current = null;
            markStepStatus(data.agent, 'completed', data.output);
            addLog(`${data.agent} completado`, 'success', data.agent);
            const draftText = data.draft_text || data.output?.draft_text;
            const fmtText   = data.formatted_text || data.output?.formatted_text;
            if (draftText) setPreview(draftText);
            if (fmtText)   setPreview(fmtText);

          } else if (data.type === 'agent_error') {
            setAgentTimings(prev => {
              const ag = prev[data.agent] || {};
              return { ...prev, [data.agent]: { ...ag, durationMs: ag.startMs ? Date.now() - ag.startMs : null } };
            });
            currentAgentRef.current = null;
            markStepStatus(data.agent, 'failed');
            addLog(`${data.agent}: ${data.error}`, 'error', data.agent);

          } else if (data.type === 'await_decision') {
            setPendingDecision(data);
            addLog('El pipeline espera tu decisión (coherencia)', 'warn', currentAgentRef.current);

          } else if (data.type === 'decision_resolved') {
            setPendingDecision(null);
            setDecisionBusy(false);
            addLog('Decisión enviada — reanudando pipeline', 'info', null);

          } else if (data.type === 'gate_failed') {
            setGateNotice({ kind: 'gate_failed', blockers: data.blockers || [] });
            addLog(`Compuerta bloquea la publicación`, 'error', null);

          } else if (data.type === 'requires_human_review') {
            setGateNotice({ kind: 'requires_human_review', score: data.score, feedback: data.feedback || [] });
            addLog('Revisor no aprobó: requiere revisión humana', 'warn', null);

          } else if (data.type === 'log') {
            addLog(data.message, data.level || 'info', currentAgentRef.current);

          } else if (data.type === 'done') {
            setDone(true);
            setPipelineFailed(false);
            setElapsed(formatDurationLive(Date.now() - (startTimeMsRef.current || Date.now())));
            addLog('Pipeline completado', 'success', null);
            // mejor-esfuerzo: preview post-ejecución; si falla, el texto se carga al reabrir el artículo
            fetchArticle(articleId).then(art => { if (art?.body) setPreview(art.body); }).catch(() => {});
            evtSource.close();

          } else if (data.type === 'done_error') {
            setDone(true);
            setPipelineFailed(true);
            setCanResume(data.can_resume !== false);
            setElapsed(formatDurationLive(Date.now() - (startTimeMsRef.current || Date.now())));
            addLog(`Pipeline fallido: ${data.error || 'error desconocido'}`, 'error', null);
            evtSource.close();

          } else if (data.type === 'cancelled') {
            setDone(true);
            setCancelled(true);
            addLog('Pipeline cancelado — artículo guardado como borrador', 'warn', null);
            evtSource.close();
          }
        // mejor-esfuerzo: evento SSE malformado, descartado sin interrumpir el stream
        } catch { }
      };

      evtSource.onerror = () => {
        evtSource.close();
        setDone(true);
        // mejor-esfuerzo: preview en error de SSE; si falla, el texto se carga al reabrir el artículo
        fetchArticle(articleId).then(art => { if (art?.body) setPreview(p => p || art.body); }).catch(() => {});
      };
    })();

    return () => {
      isCancelled = true;
      if (evtSource) evtSource.close();
      else if (evtSourceRef.current) evtSourceRef.current.close();
    };
  }, [articleId, runCount]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Disparar pipeline ──
  useEffect(() => {
    // Al recuperar una ejecución en curso **no** se relanza nada: el pipeline
    // ya corre en el servidor. Solo se escucha.
    if (recuperada) { pipelineStarted.current = true; return; }
    if (flowSequence.length > 0 && !pipelineStarted.current) {
      pipelineStarted.current = true;
      const isResume = resumeRef.current;
      resumeRef.current = false;
      const payload = {
        flow_sequence: flowSequence, agent_settings: agentSettings,
        keywords: runKeywords, context_description: contextDescription,
        article_outline: articleOutline,
        swarm_notes: swarmNotes,
        reference_doc_id: referenceDocId,
        format_mode: formatMode,
      };
      const request = isResume ? agentsApi.resume(articleId, payload) : agentsApi.run(articleId, payload);
      request.catch(() => toast.error(isResume ? 'Error al reanudar' : 'Error al iniciar el pipeline'));
    }
  }, [runCount]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Acciones ──
  const handleCancel = async () => {
    setCancelling(true);
    try { await agentsApi.cancel(articleId); }
    catch (err) { if (err?.response?.status !== 409) toast.error('No se pudo cancelar'); }
    finally { setCancelling(false); }
  };

  const handleRerun = () => {
    setSteps(flowSequence.map(id => ({ id, status: 'waiting', output: '' })));
    setLogs([]); setPreview(''); setDone(false); setPipelineFailed(false);
    setCanResume(false); setCancelled(false); setCancelling(false);
    setAgentTimings({}); setAgentProgress({}); setStartTimeMs(null); setElapsed('—');
    setTraceData(null); startTimeMsRef.current = null;
    resumeRef.current = false; pipelineStarted.current = false;
    setRunCount(c => c + 1);
  };

  const handleResume = () => {
    setSteps(cur => cur.map(s => s.status === 'completed' ? s : { ...s, status: 'waiting', output: '' }));
    setPreview(cur => cur.startsWith('Error:') ? '' : cur);
    setDone(false); setPipelineFailed(false); setCanResume(false);
    setCancelled(false); setCancelling(false);
    resumeRef.current = true; pipelineStarted.current = false;
    setRunCount(c => c + 1);
  };

  const handleContinueDecision = async () => {
    setDecisionBusy(true);
    try { await agentsApi.submitDecision(articleId, 'continue'); setPendingDecision(null); }
    catch { toast.error('No se pudo enviar la decisión'); setDecisionBusy(false); }
  };

  const handleUploadSourceClick = () => sourceInputRef.current?.click();

  const onSourceFileSelected = async (e) => {
    const file = e.target.files?.[0]; e.target.value = '';
    if (!file) return;
    setDecisionBusy(true);
    try {
      await agentsApi.uploadRagDocument('investigador', file);
      toast.success(`Fuente añadida: ${file.name}`);
      await agentsApi.submitDecision(articleId, 'add_source');
      setPendingDecision(null);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'No se pudo subir la fuente');
      setDecisionBusy(false);
    }
  };

  // ── Métricas derivadas ──
  const metricsAgents = (() => {
    if (traceData?.steps?.length) {
      const map = {};
      for (const s of traceData.steps) {
        if (!map[s.agent_name]) map[s.agent_name] = {
          name: s.agent_name, label: agentMeta(s.agent_name)?.label || s.agent_name,
          latencyMs: 0, tokens: 0, status: 'completed',
        };
        map[s.agent_name].latencyMs += s.latency_ms || 0;
        map[s.agent_name].tokens += (s.tokens_in || 0) + (s.tokens_out || 0);
        if (s.status !== 'completed') map[s.agent_name].status = s.status;
      }
      return Object.values(map);
    }
    return Object.entries(agentTimings).map(([name, t]) => ({
      name, label: agentMeta(name)?.label || name,
      latencyMs: t.durationMs || 0, tokens: 0,
      status: steps.find(s => s.id === name)?.status || 'waiting',
    }));
  })();

  const totalMs     = traceData?.totals?.latency_ms || metricsAgents.reduce((s, a) => s + a.latencyMs, 0);
  const totalTokens = traceData?.totals
    ? traceData.totals.tokens_in + traceData.totals.tokens_out
    : metricsAgents.reduce((s, a) => s + a.tokens, 0);
  const totalErrors   = traceData?.totals?.failed_steps ?? steps.filter(s => s.status === 'failed').length;
  const completedCnt  = metricsAgents.filter(a => a.status === 'completed').length;
  // AC5: no derivar porcentaje de tokens ni de tiempo — mostrar agentes completados / total (hechos reales).
  const progressLabel = done
    ? `${completedCnt} de ${metricsAgents.length || flowSequence.length} agentes`
    : metricsAgents.length > 0
      ? `${completedCnt} / ${metricsAgents.length} agentes`
      : 'Indeterminado';
  const latencyChart  = metricsAgents.map(a => ({ name: a.name, label: a.label, value: a.latencyMs }));
  const tokensChart   = metricsAgents.map(a => ({ name: a.name, label: a.label, value: a.tokens }));
  const hasMetrics    = metricsAgents.length > 0 || traceData?.available;

  const statusBadge = done && cancelled ? { label: 'Cancelado',    cls: 'badge-pending' }
    : done && pipelineFailed            ? { label: 'Fallido',      cls: 'badge-error' }
    : done                              ? { label: 'Completado',   cls: 'badge-approved' }
    : flowSequence.length > 0           ? { label: 'En ejecución', cls: 'badge-running' }
    : { label: 'Sin ejecutar', cls: 'badge-draft' };

  // ════════════════════════════════════════════════════════════════════════════
  // RENDER — todos los paneles siempre montados, visibles con display:none/block
  // ════════════════════════════════════════════════════════════════════════════
  return (
    <div className="trace-page">

      {/* CABECERA */}
      <div className="trace-header">
        <button className="btn btn-ghost btn-sm"
          onClick={() => navigate(returnToTraceability ? '/dashboard/traceability' : '/dashboard/flow-designer')}
          style={{ alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: 4 }}>
          <ArrowLeft size={13} /> {returnToTraceability ? 'Volver a trazabilidad' : 'Volver al diseñador'}
        </button>
        <div style={{ flex: 1 }}>
          <h2 className="trace-title">Trazabilidad y observabilidad</h2>
          <p className="trace-subtitle">
            Sigue la ejecución en tiempo real con trazas, métricas y eventos de los agentes.
          </p>
        </div>
        <div className="trace-meta-row">
          <span className="trace-meta-item">
            <FileText size={12} /> <code style={{ fontSize: 11 }}>{articleId?.slice(0, 8)}…</code>
          </span>
          {executionDate && <span className="trace-meta-item"><Clock size={12} /> {executionDate}</span>}
          <span className="trace-meta-item"><Clock size={12} /> {elapsed}</span>
        </div>
        <span className={`badge ${statusBadge.cls}`}>{statusBadge.label}</span>
      </div>

      {/* PESTAÑAS — 3 en lugar de 4, sin Logs */}
      <div className="trace-tabs" role="tablist">
        {[
          { id: 'realtime', icon: <Play size={13} />,        label: 'Ejecución en tiempo real' },
          { id: 'traces',   icon: <GitBranch size={13} />,   label: 'Trazas por agente' },
          { id: 'metrics',  icon: <BarChart2 size={13} />,   label: 'Métricas' },
          { id: 'integrity', icon: <ShieldCheck size={13} />, label: 'Integridad' },
        ].map(tab => (
          <button key={tab.id} role="tab" aria-selected={activeTab === tab.id}
            className={`trace-tab${activeTab === tab.id ? ' active' : ''}`}
            onClick={() => setActiveTab(tab.id)}>
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      {/* CUERPO */}
      <div className="trace-body">

        {/* ─── PANEL IZQUIERDO (siempre montado, mostrado con CSS) ─── */}
        <div className="trace-left-panel">

          {/* ══ TAB 1: EJECUCIÓN EN TIEMPO REAL ══ */}
          <div style={{ display: activeTab === 'realtime' ? undefined : 'none' }}>
            <div className="trace-section-header">
              <div>
                <div className="trace-section-title">Estado de ejecución del flujo</div>
                <div className="trace-section-sub">Sigue el progreso de cada agente en tiempo real.</div>
              </div>
              {!done && (
                <button className="btn btn-sm btn-secondary" onClick={handleCancel} disabled={cancelling}
                  style={{ color: 'var(--status-error)', borderColor: 'var(--status-error)' }}>
                  <Square size={12} /> {cancelling ? 'Cancelando…' : 'Detener ejecución'}
                </button>
              )}
            </div>

            {/* Aviso compuerta */}
            {gateNotice && (
              <div className="trace-notice trace-notice-warning">
                {gateNotice.kind === 'gate_failed' ? (
                  <>
                    <strong>La compuerta bloquea la publicación.</strong> El artículo vuelve a borrador.
                    <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                      {gateNotice.blockers.map(b => (
                        <li key={b.criterion}>
                          {CRITERION_LABELS[b.criterion] || b.criterion}
                          {b.responsible_agent && <> — <strong>{agentLabel(b.responsible_agent)}</strong></>}
                        </li>
                      ))}
                    </ul>
                  </>
                ) : (
                  <>
                    <strong>Requiere revisión humana.</strong>
                    {typeof gateNotice.score === 'number' && ` Puntuación: ${gateNotice.score}/100.`}
                    {gateNotice.feedback.length > 0 && (
                      <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                        {gateNotice.feedback.slice(0, 4).map((f, i) => <li key={i}>{f}</li>)}
                      </ul>
                    )}
                  </>
                )}
              </div>
            )}

            {/* Panel HITL */}
            {pendingDecision && !done && (
              <div className="trace-notice trace-notice-warning">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <AlertTriangle size={15} style={{ color: 'var(--status-warning)' }} />
                  <span style={{ fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--status-warning)' }}>
                    Coherencia insuficiente
                  </span>
                </div>
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginBottom: 8 }}>
                  {pendingDecision.message || 'El revisor solicita más contexto o fuentes.'}
                  {typeof pendingDecision.approval_score === 'number' && ` (${pendingDecision.approval_score}/100)`}
                </div>
                {Array.isArray(pendingDecision.feedback) && pendingDecision.feedback.length > 0 && (
                  <ul style={{ margin: '0 0 10px 16px', padding: 0, fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
                    {pendingDecision.feedback.slice(0, 4).map((f, i) => <li key={i}>{f}</li>)}
                  </ul>
                )}
                <input ref={sourceInputRef} type="file" accept=".txt,.md,.pdf,.docx" style={{ display: 'none' }} onChange={onSourceFileSelected} />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <button className="btn btn-primary btn-sm w-full" onClick={handleUploadSourceClick} disabled={decisionBusy}>
                    <Upload size={13} /> {decisionBusy ? 'Procesando…' : 'Subir otra fuente y reintentar'}
                  </button>
                  <button className="btn btn-ghost btn-sm w-full" onClick={handleContinueDecision} disabled={decisionBusy}>
                    <Play size={13} /> Continuar con el borrador actual
                  </button>
                </div>
              </div>
            )}

            {/* Tarjetas de agentes */}
            <div className="trace-steps-list">
              {steps.map(step => {
                const meta   = agentMeta(step.id) || {};
                const timing = agentTimings[step.id];
                const Icono  = meta.icon;
                // T18.6 AC4: mostrar iteración del bucle cuando un agente se repite
                const loopIter = iterationCount[step.id] || 0;
                const showLoop = loopIter > 1 && (step.id === 'redactor' || step.id === 'revisor');
                return (
                  <div key={step.id} className={`trace-step-card trace-step-${step.status}`}>
                    <div className="trace-step-left">
                      <span className="trace-step-emoji" aria-hidden="true">
                        {Icono
                          ? <Icono size={18} style={{ color: meta.color || 'var(--text-muted)' }} />
                          : (meta.emoji || '🤖')}
                      </span>
                      <div>
                        <div className="trace-step-name">{meta.label || step.id}</div>
                        {showLoop
                          ? <div className="trace-step-desc" style={{ color: 'var(--warning)', fontWeight: 500 }}>
                              Pasada {loopIter} del bucle revisor→redactor
                            </div>
                          : <div className="trace-step-desc">{meta.desc || ''}</div>
                        }
                      </div>
                    </div>
                    <div className="trace-step-right">
                      {timing?.durationMs && (
                        <span className="trace-step-duration">
                          <Clock size={11} /> {formatDuration(timing.durationMs)}
                        </span>
                      )}
                      <span className={`badge ${step.status === 'completed' ? 'badge-approved' : step.status === 'failed' ? 'badge-error' : step.status === 'running' ? 'badge-running' : 'badge-draft'}`}>
                        {STATUS_LABEL[step.status] || step.status}
                      </span>
                    </div>
                    {/* AC5: fraccional **solo** si el agente emite unidades reales.
                        Si no las emite, indeterminado — nunca un % de tokens ni de tiempo. */}
                    {step.status === 'running' && (() => {
                      const avance = agentProgress[step.id];
                      if (!avance || !avance.total) {
                        return (
                          <div className="trace-step-progress-bar">
                            <div className="trace-step-progress-fill animate-pulse" />
                          </div>
                        );
                      }
                      const pct = Math.round((avance.current / avance.total) * 100);
                      return (
                        <>
                          <div className="trace-step-progress-bar">
                            <div className="trace-step-progress-fill"
                              style={{ width: `${pct}%`, transition: 'width .3s' }} />
                          </div>
                          <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', marginTop: 3 }}>
                            {avance.unit === 'secciones'
                              ? `sección ${avance.current} de ${avance.total}`
                              : `${avance.current} de ${avance.total} ${avance.unit}`.trim()}
                          </div>
                        </>
                      );
                    })()}
                  </div>
                );
              })}
            </div>

            {/* Asignar revisor */}
            {done && !hasPublicador && (
              <div className="trace-notice trace-notice-info" style={{ marginTop: 'var(--space-4)' }}>
                <div style={{ fontWeight: 600, fontSize: 'var(--font-size-sm)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <UserPlus size={14} /> Asignar revisor
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <input className="input" style={{ flex: 1, padding: '6px 10px', fontSize: 'var(--font-size-xs)' }}
                    placeholder="@email del revisor" value={reviewerEmail}
                    onChange={e => setReviewerEmail(e.target.value.replace('@', ''))}
                    onKeyDown={e => e.key === 'Enter' && handleAssignReviewer()} />
                  <button className="btn btn-primary btn-sm" onClick={handleAssignReviewer} disabled={assigning}>
                    {assigning ? '…' : 'Asignar'}
                  </button>
                </div>
              </div>
            )}

            {/* Acciones post-ejecución */}
            {done && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', marginTop: 'var(--space-4)' }}>
                <button className="btn btn-secondary w-full" onClick={() => navigate(`/dashboard/articles/${articleId}`)}>
                  <FileText size={14} /> Ver artículo
                </button>
                {pipelineFailed && canResume && (
                  <button className="btn btn-primary w-full" onClick={handleResume}>
                    <Play size={14} /> Reanudar desde el último checkpoint
                  </button>
                )}
                {cancelled && (
                  <button className="btn btn-primary w-full" onClick={handleRerun}>
                    <Play size={14} /> Re-ejecutar pipeline
                  </button>
                )}
              </div>
            )}

            {/* Terminal de eventos en tiempo real */}
            <div className="trace-section-header" style={{ marginTop: 'var(--space-5)' }}>
              <div className="trace-section-title">Eventos en tiempo real</div>
              <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
                {logs.length} eventos
              </span>
            </div>
            <div className="trace-terminal">
              {logs.length === 0 && <span style={{ opacity: 0.5 }}>Esperando eventos del pipeline…</span>}
              {logs.slice(-60).map((l, i) => (
                <div key={`${l.tsMs}-${i}`} className={`log-line ${l.type}`}>
                  <span style={{ opacity: 0.5 }}>{l.ts} </span>
                  {l.agent && <span style={{ opacity: 0.7, marginRight: 4 }}>[{l.agent}]</span>}
                  {l.msg}
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          </div>

          {/* ══ TAB 2: TRAZAS POR AGENTE ══
              Siempre montado para que ExplainPanel no pierda su estado interno */}
          <div style={{ display: activeTab === 'traces' ? undefined : 'none' }}>
            <div className="trace-section-header">
              <div>
                <div className="trace-section-title">Trazas por agente</div>
                <div className="trace-section-sub">Detalle de cada paso: modelo, tokens, fuentes RAG y decisiones.</div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setTraceRefreshKey(k => k + 1)}
                style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <Loader size={13} /> Actualizar
              </button>
            </div>
            <ExplainPanel key={traceRefreshKey} articleId={articleId} />
          </div>

          {/* ══ TAB 3: MÉTRICAS ══ */}
          <div style={{ display: activeTab === 'metrics' ? undefined : 'none' }}>
            <div className="trace-section-header">
              <div className="trace-section-title">Métricas de ejecución</div>
              {traceLoading && (
                <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
                  <Loader size={12} style={{ animation: 'spin 1s linear infinite' }} /> Cargando…
                </span>
              )}
            </div>

            {!hasMetrics && !traceLoading ? (
              <EmptyState icon={<BarChart2 size={28} />}
                title="Sin datos de métricas"
                description={done ? "No se encontró traza para este artículo." : "Las métricas se irán completando durante la ejecución."} />
            ) : (
              <>
                <div className="trace-metric-row">
                  <MetricTile icon={<Clock size={18} />}        label="Duración total"   value={formatDuration(totalMs)}                 color="var(--brand)" />
                  <MetricTile icon={<Activity size={18} />}     label="Tokens totales"   value={totalTokens.toLocaleString('es-ES')}     color="var(--agent-write)" />
                  <MetricTile icon={<XCircle size={18} />}      label="Errores"          value={totalErrors}
                    color={totalErrors > 0 ? 'var(--error)' : 'var(--success)'} />
                  <MetricTile icon={<CheckCircle size={18} />}  label="Agentes completados"  value={progressLabel}  color="var(--success)" />
                </div>

                <div className="trace-charts-grid">
                  <div className="trace-chart-card">
                    <div className="trace-chart-title"><Clock size={14} /> Latencia por agente</div>
                    <BarChart data={latencyChart} unit="ms" />
                  </div>
                  <div className="trace-chart-card">
                    <div className="trace-chart-title"><Activity size={14} /> Tokens por agente</div>
                    <BarChart data={tokensChart} unit="tokens" />
                  </div>
                </div>

                <div className="trace-section-title" style={{ marginBottom: 'var(--space-3)' }}>
                  Métricas por agente
                </div>
                <table className="trace-log-table">
                  <thead>
                    <tr><th>Agente</th><th>Duración</th><th>Tokens</th><th>Estado</th></tr>
                  </thead>
                  <tbody>
                    {metricsAgents.map(a => (
                      <tr key={a.name} className="trace-log-row">
                        <td>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            {(() => { const m = agentMeta(a.name); const I = m?.icon; return I ? <I size={14} style={{ color: m.color }} /> : null; })()}
                            <span style={{ fontWeight: 500 }}>{a.label}</span>
                          </span>
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                          {formatDuration(a.latencyMs)}
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                          {a.tokens.toLocaleString('es-ES')}
                        </td>
                        <td>
                          <span className={`badge ${a.status === 'completed' ? 'badge-approved' : a.status === 'failed' || a.status === 'error' ? 'badge-error' : a.status === 'running' ? 'badge-running' : 'badge-pending'}`}>
                            {a.status === 'completed' ? 'Completado' : a.status === 'failed' ? 'Error' : a.status === 'running' ? 'En ejecución' : 'Pendiente'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>

          {/* ══ TAB 4: INTEGRIDAD (T17.6 / AC6) ══ */}
          <div style={{ display: activeTab === 'integrity' ? undefined : 'none' }}>
            <div className="trace-section-header">
              <div>
                <div className="trace-section-title">Integridad de la traza</div>
                <div className="trace-section-sub">
                  Cada paso lleva un SHA-256 encadenado al anterior de su ejecución.
                </div>
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <button className="btn btn-ghost btn-sm" onClick={handleExport} disabled={exporting}
                  style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Download size={13} /> {exporting ? 'Exportando…' : 'Exportar JSONL'}
                </button>
                <button className="btn btn-secondary btn-sm" onClick={loadIntegrity}
                  disabled={integrityLoading}
                  style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Loader size={13} style={integrityLoading ? { animation: 'spin 1s linear infinite' } : undefined} />
                  {integrityLoading ? 'Verificando…' : 'Verificar'}
                </button>
              </div>
            </div>

            {integrityError && (
              <div className="trace-notice trace-notice-warning">
                <strong>No se pudo verificar.</strong> {integrityError}
                <div style={{ marginTop: 4, fontSize: 'var(--font-size-xs)' }}>
                  Que no se haya podido comprobar no significa que la traza esté bien
                  ni que esté mal: significa que no se sabe.
                </div>
              </div>
            )}

            {!integrity && !integrityLoading && !integrityError && (
              <EmptyState icon={<ShieldCheck size={28} />}
                title="Sin verificar"
                description="Pulsa «Verificar» para comprobar la cadena de esta traza." />
            )}

            {integrity && !integrity.available && (
              <EmptyState icon={<ShieldAlert size={28} />}
                title="Sin traza que verificar"
                description="Este artículo no tiene pasos registrados: puede no haberse ejecutado nunca, o su traza haberse purgado por retención." />
            )}

            {integrity?.available && (
              <>
                {(integrity.executions || []).map(ej => {
                  // Tres estados, no dos: una ejecución sin un solo hash no está
                  // rota, está sin comprobar. Pintarla de rojo sería alarmismo.
                  const rota    = ej.status === 'rota';
                  const sinCadena = ej.status === 'sin_cadena';
                  return (
                  <div key={ej.run_number}
                    className={`trace-notice ${rota ? 'trace-notice-warning' : 'trace-notice-info'}`}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      {rota
                        ? <ShieldAlert size={16} style={{ color: 'var(--status-warning)' }} />
                        : sinCadena
                          ? <Info size={16} style={{ color: 'var(--text-muted)' }} />
                          : <ShieldCheck size={16} style={{ color: 'var(--status-success)' }} />}
                      <strong>
                        {ej.runs_total > 1 ? `Pasada ${ej.run_number} de ${ej.runs_total}` : 'Ejecución'}
                        {' — '}
                        {rota ? 'cadena rota' : sinCadena ? 'sin cadena que verificar' : 'cadena íntegra'}
                      </strong>
                    </div>
                    <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
                      {sinCadena ? (
                        <>
                          Sus {ej.steps} paso{ej.steps !== 1 ? 's son anteriores' : ' es anterior'} a la
                          cadena de integridad, así que no llevan hash. Eso no dice que la traza esté bien
                          ni que esté mal: dice que no hay con qué comprobarlo. Las ejecuciones nuevas sí
                          se sellan.
                        </>
                      ) : (
                        <>
                          {ej.verified} de {ej.steps} paso{ej.steps !== 1 ? 's' : ''} verificado{ej.verified !== 1 ? 's' : ''}
                          {ej.unchained > 0 && (
                            <> · {ej.unchained} sin cadena (anteriores a esta función; no es señal de manipulación)</>
                          )}
                        </>
                      )}
                    </div>
                    {(ej.issues || []).length > 0 && (
                      <ul style={{ margin: '8px 0 0 16px', padding: 0, fontSize: 'var(--font-size-xs)' }}>
                        {ej.issues.map((p, i) => (
                          <li key={i} style={{ marginBottom: 2 }}>
                            <strong>Paso {p.position}</strong>
                            {p.agent_name ? ` (${agentLabel(p.agent_name)})` : ''}:{' '}
                            {p.problem === 'contenido_alterado' ? 'contenido alterado' : 'enlace roto'}
                            {' — '}{p.detail}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  );
                })}

                {/* AC6: el alcance se dice en la interfaz, no solo en la documentación.
                    Viene del servidor para que no puedan divergir. */}
                <div className="trace-notice trace-notice-info" style={{ marginTop: 12 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <Info size={15} />
                    <strong>Qué garantiza esto, y qué no</strong>
                  </div>
                  <div style={{ fontSize: 'var(--font-size-xs)', lineHeight: 1.7 }}>
                    <p style={{ margin: '0 0 6px' }}>
                      <strong style={{ color: 'var(--status-success)' }}>Garantiza: </strong>
                      {integrity.scope?.guarantees}
                    </p>
                    <p style={{ margin: 0 }}>
                      <strong style={{ color: 'var(--status-warning)' }}>No garantiza: </strong>
                      {integrity.scope?.does_not_guarantee}
                    </p>
                  </div>
                </div>
              </>
            )}
          </div>

        </div>{/* /trace-left-panel */}

        {/* ─── PREVIEW DEL ARTÍCULO ─── */}
        <div className="trace-right-panel">
          <div className="trace-preview-header">
            <span style={{ fontWeight: 600, fontSize: 'var(--font-size-sm)' }}>
              Vista previa del artículo en tiempo real
            </span>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              {hasFailedSteps && <span className="badge badge-rejected">Error</span>}
              {!hasFailedSteps && isGeneratingPreview && <span className="badge badge-running animate-pulse">Generando…</span>}
              {!hasFailedSteps && done && preview && <span className="badge badge-approved">Borrador</span>}
            </div>
          </div>
          <div className="trace-preview-body">
            {preview ? (
              <div className="markdown-body"><ReactMarkdown>{preview}</ReactMarkdown></div>
            ) : (
              <EmptyState icon={<FileText size={28} />}
                title="Esperando contenido"
                description="El artículo aparecerá aquí conforme los agentes generen contenido." />
            )}
          </div>
        </div>

      </div>{/* /trace-body */}
    </div>
  );
}
