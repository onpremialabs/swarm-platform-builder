import React, { useEffect, useRef, useState } from 'react';
import { agentMeta } from '../catalog';
import { EmptyState } from '../../../platform/components/ui/states';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { CheckCircle, XCircle, Clock, Loader, ArrowRight, ArrowLeft, FileText, UserPlus, Square, Upload, Play, AlertTriangle } from 'lucide-react';
import { agentsApi } from '../../../platform/api/agents';
import { useArticleStore } from '../store/articleStore';
import toast from 'react-hot-toast';
import { agentLabel, CRITERION_LABELS } from '../gate';


const STATUS_ICON = {
  waiting:   <Clock size={16} style={{ color: 'var(--text-muted)' }} />,
  running:   <Loader size={16} style={{ color: 'var(--status-info)', animation: 'spin 1s linear infinite' }} />,
  completed: <CheckCircle size={16} style={{ color: 'var(--status-success)' }} />,
  failed:    <XCircle size={16} style={{ color: 'var(--status-error)' }} />,
};

export default function ExecutionPage() {
  const { articleId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { fetchArticle, assignReviewer } = useArticleStore();

  const flowSequence = location.state?.flowSequence || [];
  const agentSettings = location.state?.agentSettings || {};
  const runKeywords = location.state?.keywords || [];
  const contextDescription = location.state?.contextDescription || '';
  const articleOutline = location.state?.articleOutline || '';
  const [steps, setSteps] = useState(
    flowSequence.map(id => ({ id, status: 'waiting', output: '' }))
  );
  const [logs, setLogs] = useState([]);
  const [preview, setPreview] = useState('');
  const [done, setDone] = useState(false);
  const [pipelineFailed, setPipelineFailed] = useState(false);
  const [canResume, setCanResume] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [runCount, setRunCount] = useState(0);
  const [hasPublicador] = useState(flowSequence.includes('publicador'));
  const [reviewerEmail, setReviewerEmail] = useState('');
  const [assigning, setAssigning] = useState(false);
  // Human-in-the-loop coherence gate
  const [pendingDecision, setPendingDecision] = useState(null);
  const [gateNotice, setGateNotice] = useState(null);
  const [decisionBusy, setDecisionBusy] = useState(false);
  const sourceInputRef = useRef(null);
  const logsEndRef = useRef(null);
  const evtSourceRef = useRef(null);
  const hasFailedSteps = steps.some((step) => step.status === 'failed');
  const isGeneratingPreview = !done && steps.some((step) => step.status === 'running');

  const getStepStatusLabel = (status) => {
    if (status === 'waiting') return 'Esperando...';
    if (status === 'running') return 'Ejecutando...';
    if (status === 'completed') return 'Completado';
    return 'Error';
  };

  const markStepStatus = (agentId, status, output = undefined) => {
    setSteps((current) => current.map((step) => {
      if (step.id !== agentId) {
        return step;
      }
      return output === undefined ? { ...step, status } : { ...step, status, output };
    }));
  };

  useEffect(() => { logsEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [logs]);

  // When pipeline finishes but preview is still empty (e.g. no publicador or SSE missed),
  // fetch the article body as a last-resort fallback.
  useEffect(() => {
    if (done && !preview) {
      // mejor-esfuerzo: es el último recurso cuando el SSE no trajo el cuerpo;
      // si también falla, la vista se queda con lo que el SSE sí dio.
      fetchArticle(articleId).then(art => {
        if (art?.body) setPreview(art.body);
      }).catch(() => {});
    }
  }, [done]);

  // Connect SSE
  useEffect(() => {
    if (!articleId) return;
    let cancelled = false;
    let evtSource;

    // Exchange the JWT for a single-use stream ticket, then open the SSE
    // connection with it — the token is never placed in the URL (T1.4).
    (async () => {
      let ticket;
      try {
        const res = await agentsApi.getStreamTicket(articleId);
        ticket = res?.ticket;
      } catch {
        addLog('No se pudo autenticar el stream en tiempo real', 'error');
        return;
      }
      if (cancelled || !ticket) return;

      evtSource = new EventSource(agentsApi.getStreamUrl(articleId, ticket));
      evtSourceRef.current = evtSource;

    evtSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === 'agent_start') {
          markStepStatus(data.agent, 'running');
          addLog(`▶ ${data.agent} iniciado`, 'info');
          if (data.agent === 'redactor' || data.agent === 'formateador') {
            setPreview('');
          }
        } else if (data.type === 'token') {
          setPreview((current) => current + data.token);
        } else if (data.type === 'agent_end') {
          markStepStatus(data.agent, 'completed', data.output);
          addLog(`✓ ${data.agent} completado`, 'success');
          const draftText = data.draft_text || data.output?.draft_text;
          const fmtText = data.formatted_text || data.output?.formatted_text;
          if (draftText) setPreview(draftText);
          if (fmtText) setPreview(fmtText);
        } else if (data.type === 'agent_error') {
          markStepStatus(data.agent, 'failed');
          addLog(`✗ ${data.agent}: ${data.error}`, 'error');
          setPreview((current) => current || `Error: ${data.error}`);
        } else if (data.type === 'await_decision') {
          setPendingDecision(data);
          addLog('⏸️ El pipeline espera tu decisión (coherencia)', 'warn');
        } else if (data.type === 'decision_resolved') {
          setPendingDecision(null);
          setDecisionBusy(false);
          addLog(`▶️ Decisión: ${data.decision === 'add_source' ? 'nueva fuente añadida' : 'continuar'}`, 'info');
        } else if (data.type === 'gate_failed') {
          // SPEC-032/AC14: la compuerta bloqueó el texto final; el artículo vuelve a borrador.
          const lista = (data.blockers || []).map((b) => b.criterion).join(', ');
          setGateNotice({ kind: 'gate_failed', blockers: data.blockers || [] });
          addLog(`⛔ La compuerta bloquea la publicación (${lista}). El artículo vuelve a borrador.`, 'error');
        } else if (data.type === 'requires_human_review') {
          // SPEC-032/AC7: se agotaron las vueltas sin aprobar; solo una persona decide.
          setGateNotice({ kind: 'requires_human_review', score: data.score, feedback: data.feedback || [] });
          addLog('⏸️ El Revisor no aprobó tras agotar las vueltas: el artículo requiere revisión humana', 'warn');
        } else if (data.type === 'log') {
          addLog(data.message, data.level || '');
        } else if (data.type === 'done') {
          setDone(true);
          setPipelineFailed(false);
          addLog('Pipeline completado', 'success');
          // Always fetch the final article body from the server — this is the
          // authoritative source after publicador commits, and acts as a fallback
          // when SSE draft_text/formatted_text events were missed or empty.
          // mejor-esfuerzo: refresco autoritativo tras publicar; el preview del
          // SSE ya está en pantalla si esto no llega.
          fetchArticle(articleId).then(art => {
            if (art?.body) setPreview(art.body);
          }).catch(() => {});
          evtSource.close();
        } else if (data.type === 'done_error') {
          setDone(true);
          setPipelineFailed(true);
          setCanResume(data.can_resume !== false);
          addLog(`Pipeline fallido: ${data.error || 'error desconocido'}`, 'error');
          evtSource.close();
        } else if (data.type === 'cancelled') {
          setDone(true);
          setCancelled(true);
          addLog('Pipeline cancelado por el usuario — artículo en borrador', 'warn');
          evtSource.close();
        }
      // mejor-esfuerzo: un evento SSE ilegible se descarta; el siguiente
      // llega en milisegundos y cortar el flujo por uno sería peor.
      } catch { /* ignore parse errors */ }
    };

    evtSource.onerror = () => {
      // onerror fires both on real errors and when the server closes the connection
      // normally after sending `done`. In either case, try to show the article body.
      evtSource.close();
      setDone(true);
      // mejor-esfuerzo: mismo refresco al cerrarse la conexión.
      fetchArticle(articleId).then(art => {
        if (art?.body) setPreview(p => p || art.body);
      }).catch(() => {});
    };
    })();

    return () => {
      cancelled = true;
      if (evtSource) evtSource.close();
      else if (evtSourceRef.current) evtSourceRef.current.close();
    };
  }, [articleId, runCount]);

  // Trigger the actual pipeline run — ref guard prevents double-fire in React StrictMode
  const pipelineStarted = useRef(false);
  // When true, the next trigger resumes from the last checkpoint instead of restarting
  const resumeRef = useRef(false);
  useEffect(() => {
    if (flowSequence.length > 0 && !pipelineStarted.current) {
      pipelineStarted.current = true;
      const isResume = resumeRef.current;
      resumeRef.current = false;
      const payload = {
        flow_sequence: flowSequence,
        agent_settings: agentSettings,
        keywords: runKeywords,
        context_description: contextDescription,
        article_outline: articleOutline,
      };
      const request = isResume
        ? agentsApi.resume(articleId, payload)
        : agentsApi.run(articleId, payload);
      request.catch(() => {
        toast.error(isResume ? 'Error al reanudar el pipeline' : 'Error al iniciar el pipeline');
      });
    }
  }, [runCount]);

  const addLog = (msg, type = '') => {
    setLogs(l => [...l, { msg, type, ts: new Date().toLocaleTimeString() }]);
  };

  const handleCancel = async () => {
    setCancelling(true);
    try {
      await agentsApi.cancel(articleId);
    } catch (err) {
      if (err?.response?.status !== 409) {
        toast.error('No se pudo cancelar el pipeline');
      }
    } finally {
      setCancelling(false);
    }
  };

  const handleRerun = () => {
    setSteps(flowSequence.map(id => ({ id, status: 'waiting', output: '' })));
    setLogs([]);
    setPreview('');
    setDone(false);
    setPipelineFailed(false);
    setCanResume(false);
    setCancelled(false);
    setCancelling(false);
    resumeRef.current = false;
    pipelineStarted.current = false;
    setRunCount(c => c + 1);
  };

  // Resume from the last checkpoint: keep the work done by completed agents and
  // only re-run the failed step onward.
  const handleResume = () => {
    setSteps((current) => current.map((step) => (
      step.status === 'completed' ? step : { ...step, status: 'waiting', output: '' }
    )));
    setPreview((current) => (current.startsWith('Error:') ? '' : current));
    setDone(false);
    setPipelineFailed(false);
    setCanResume(false);
    setCancelled(false);
    setCancelling(false);
    resumeRef.current = true;
    pipelineStarted.current = false;
    setRunCount(c => c + 1);
  };

  const handleContinueDecision = async () => {
    setDecisionBusy(true);
    try {
      await agentsApi.submitDecision(articleId, 'continue');
      setPendingDecision(null);
    } catch {
      toast.error('No se pudo enviar la decisión');
      setDecisionBusy(false);
    }
  };

  const handleUploadSourceClick = () => sourceInputRef.current?.click();

  const onSourceFileSelected = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';  // allow re-selecting the same file later
    if (!file) return;
    setDecisionBusy(true);
    try {
      // Upload to the investigador bucket so the re-run finds it as a source
      await agentsApi.uploadRagDocument('investigador', file);
      toast.success(`Fuente añadida: ${file.name}`);
      await agentsApi.submitDecision(articleId, 'add_source');
      setPendingDecision(null);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'No se pudo subir la fuente');
      setDecisionBusy(false);
    }
  };

  const handleAssignReviewer = async () => {
    if (!reviewerEmail.trim()) { toast.error('Escribe el email del revisor'); return; }
    setAssigning(true);
    try {
      await assignReviewer(articleId, reviewerEmail);
      toast.success(`Revisor asignado: ${reviewerEmail}`);
      setReviewerEmail('');
    } catch { toast.error('Error al asignar revisor'); }
    finally { setAssigning(false); }
  };

  return (
    <div className="execution-layout">
      {/* Left panel */}
      <div className="execution-sidebar">
        <div className="execution-header">
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => navigate('/dashboard/flow-designer')}
            style={{ alignSelf: 'flex-start', marginBottom: 'var(--space-2)', display: 'flex', alignItems: 'center', gap: 4, fontSize: 'var(--font-size-xs)' }}
            aria-label="Volver al Flow Designer"
          >
            <ArrowLeft size={13} /> Volver al diseñador
          </button>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 4 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {done && cancelled
                ? <Square size={16} style={{ color: 'var(--status-warning)' }} />
                : done && !pipelineFailed
                ? <CheckCircle size={16} style={{ color: 'var(--status-success)' }} />
                : done && pipelineFailed
                ? <XCircle size={16} style={{ color: 'var(--status-error)' }} />
                : <Loader size={16} style={{ color: 'var(--brand-primary)', animation: 'spin 1s linear infinite' }} />
              }
              <span style={{ fontWeight: 600, fontSize: 'var(--font-size-sm)' }}>
                {done && cancelled ? 'Pipeline cancelado' : done && pipelineFailed ? 'Pipeline fallido' : done ? 'Pipeline completado' : 'Ejecutando pipeline…'}
              </span>
            </div>
            {!done && (
              <button
                className="btn btn-sm"
                style={{ color: 'var(--status-error)', border: '1px solid var(--status-error)', background: 'transparent', display: 'flex', alignItems: 'center', gap: 4, padding: '2px 8px', fontSize: 'var(--font-size-xs)', cursor: 'pointer' }}
                onClick={handleCancel}
                disabled={cancelling}
                aria-label="Cancelar ejecución del pipeline"
              >
                <Square size={11} /> {cancelling ? 'Cancelando…' : 'Cancelar'}
              </button>
            )}
          </div>
          <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            ID: {articleId?.slice(0, 8)}…
          </div>
        </div>

        {/* Resultado de la compuerta de publicación (SPEC-032): el artículo no se publica solo */}
        {gateNotice && (
          <div role="status" style={{
            margin: '0 0 var(--space-3)', padding: 'var(--space-4)',
            background: 'var(--status-warning-bg)', border: '1px solid var(--status-warning)',
            borderRadius: 'var(--radius-md)', fontSize: 'var(--font-size-sm)',
          }}>
            {gateNotice.kind === 'gate_failed' ? (
              <>
                <strong>La compuerta bloquea la publicación.</strong> El artículo vuelve a borrador.
                <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                  {gateNotice.blockers.map((b) => (
                    <li key={b.criterion}>
                      {CRITERION_LABELS[b.criterion] || b.criterion}
                      {b.responsible_agent && <> — corresponde a <strong>{agentLabel(b.responsible_agent)}</strong></>}
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <>
                <strong>Requiere revisión humana.</strong> El Revisor no aprobó el texto tras agotar las vueltas
                {typeof gateNotice.score === 'number' && <> (puntuación {gateNotice.score}/100)</>}; no se ha formateado ni publicado.
                {gateNotice.feedback.length > 0 && (
                  <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                    {gateNotice.feedback.slice(0, 4).map((f, i) => <li key={i}>{f}</li>)}
                  </ul>
                )}
              </>
            )}
          </div>
        )}

        {/* Human-in-the-loop decision panel */}
        {pendingDecision && !done && (
          <div style={{
            margin: '0 0 var(--space-3)', padding: 'var(--space-4)',
            background: 'var(--status-warning-bg)', border: '1px solid var(--status-warning)',
            borderRadius: 'var(--radius-md)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <AlertTriangle size={16} style={{ color: 'var(--status-warning)' }} />
              <span style={{ fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--status-warning)' }}>
                Coherencia insuficiente
              </span>
            </div>
            <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)', marginBottom: 8 }}>
              {pendingDecision.message || 'El revisor considera que la redacción no es suficientemente coherente.'}
              {typeof pendingDecision.approval_score === 'number' && (
                <span> (puntuación: {pendingDecision.approval_score}/100)</span>
              )}
            </div>
            {Array.isArray(pendingDecision.feedback) && pendingDecision.feedback.length > 0 && (
              <ul style={{ margin: '0 0 10px 16px', padding: 0, fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
                {pendingDecision.feedback.slice(0, 4).map((f, i) => <li key={i}>{f}</li>)}
              </ul>
            )}
            <input
              ref={sourceInputRef}
              type="file"
              accept=".txt,.md,.pdf,.docx"
              style={{ display: 'none' }}
              onChange={onSourceFileSelected}
            />
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

        {/* Steps */}
        <div className="execution-steps">
          {steps.map((step, i) => {
            const meta = agentMeta(step.id) || { emoji: '🤖', label: step.id, color: 'var(--neutral-60)' };
            return (
              <div key={step.id} className={`step-card ${step.status}`}>
                <span style={{ fontSize: 18 }}>{meta.emoji}</span>
                <div className="step-info">
                  <div className="step-name">{meta.label}</div>
                  <div className="step-status">
                    {getStepStatusLabel(step.status)}
                  </div>
                </div>
                {STATUS_ICON[step.status]}
                {i < steps.length - 1 && step.status === 'completed' && (
                  <ArrowRight size={12} style={{ position: 'absolute', right: -8, color: 'var(--status-success)' }} />
                )}
              </div>
            );
          })}

          {/* Post-completion actions */}
          {done && !hasPublicador && (
            <div style={{ marginTop: 'var(--space-4)', padding: 'var(--space-4)', background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-default)' }}>
              <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                <UserPlus size={14} /> Asignar revisor
              </div>
              <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', marginBottom: 10 }}>
                El pipeline no incluye un publicador. Asigna un revisor para validar el artículo.
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <input className="input" style={{ flex: 1, padding: '6px 10px', fontSize: 'var(--font-size-xs)' }}
                  placeholder="@email del revisor"
                  value={reviewerEmail}
                  onChange={e => setReviewerEmail(e.target.value.replace('@', ''))}
                  onKeyDown={e => e.key === 'Enter' && handleAssignReviewer()}
                />
                <button className="btn btn-primary btn-sm" onClick={handleAssignReviewer} disabled={assigning}>
                  {assigning ? '…' : 'Asignar'}
                </button>
              </div>
            </div>
          )}

          {done && cancelled && (
            <div style={{ marginTop: 'var(--space-4)', padding: 'var(--space-4)', background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', border: '1px solid var(--status-warning)' }}>
              <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', marginBottom: 10 }}>
                Artículo guardado como borrador. Puedes re-ejecutar el pipeline desde aquí o revisarlo en el editor.
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                <button
                  className="btn btn-primary btn-sm w-full"
                  onClick={handleRerun}
                  aria-label="Re-ejecutar el pipeline desde el principio"
                >
                  ▶ Re-ejecutar pipeline
                </button>
                <button className="btn btn-secondary btn-sm w-full"
                  onClick={() => navigate(`/dashboard/articles/${articleId}`)}>
                  <FileText size={13} /> Ver borrador
                </button>
              </div>
            </div>
          )}

          {done && !cancelled && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', marginTop: 'var(--space-3)' }}>
              <button className="btn btn-secondary w-full"
                onClick={() => navigate(`/dashboard/articles/${articleId}`)}>
                <FileText size={14} /> Ver artículo
              </button>
              {pipelineFailed && canResume && (
                <button className="btn btn-primary w-full"
                  onClick={handleResume}
                  aria-label="Reanudar el pipeline desde el último checkpoint">
                  <Play size={14} /> Reanudar desde el último checkpoint
                </button>
              )}
              {pipelineFailed && (
                <button className="btn btn-ghost w-full"
                  onClick={() => navigate('/dashboard/flow-designer')}>
                  <ArrowLeft size={14} /> Reintentar en el diseñador
                </button>
              )}
            </div>
          )}
        </div>

        {/* Log terminal */}
        <div className="execution-log">
          {logs.map((l, i) => (
            <div key={`${l.ts}-${i}-${l.msg}`} className={`log-line ${l.type}`}>
              <span style={{ opacity: 0.5 }}>{l.ts} </span>{l.msg}
            </div>
          ))}
          <div ref={logsEndRef} />
        </div>
      </div>

      {/* Right preview */}
      <div className="execution-preview">
        <div className="execution-preview-header">
          <span style={{ fontWeight: 600, fontSize: 'var(--font-size-sm)' }}>Vista previa del artículo</span>
          {hasFailedSteps && <span className="badge badge-rejected">Error</span>}
          {!hasFailedSteps && isGeneratingPreview && <span className="badge badge-running animate-pulse">Generando…</span>}
          {!hasFailedSteps && done && preview && <span className="badge badge-approved">Completo</span>}
        </div>
        <div className="execution-preview-body">
          {preview ? (
            <div className="markdown-body">
              <ReactMarkdown>{preview}</ReactMarkdown>
            </div>
          ) : (
            <EmptyState
              icon={<FileText size={28} />}
              title="Esperando contenido"
              description="El artículo aparecerá aquí conforme los agentes generen contenido."
            />
          )}
        </div>
      </div>
    </div>
  );
}
