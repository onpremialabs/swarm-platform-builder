import React, { useState } from 'react';
import { ShieldCheck, RefreshCw, ArrowRight } from 'lucide-react';
import {
  ACTION_LABELS, agentLabel, BLOCKING, CRITERION_LABELS, CRITERION_STATUS, evidenceLines,
  nextStep, PENDING_REASONS, summaryLines,
} from '../gate';
import { useT } from '../i18n/useT';

/**
 * Informe de la compuerta de publicación (SPEC-032/AC6). Cada criterio se despliega:
 * si se supera, dice qué se comprobó; si bloquea, qué falta, a quién corresponde y
 * qué se puede hacer; lo que aún no se comprueba dice por qué. Sin informe lo dice,
 * en vez de callarlo: los artículos anteriores a la compuerta no tienen.
 *
 * Las acciones las ejecuta quien monta el panel (`onAction`): el panel solo las
 * ofrece. `onProvideDoi(index, doi)` devuelve una promesa que rechaza si falla.
 */
export default function GateReportPanel({
  data, loading, error, onRetry, onReevaluate, busy, onAction, onProvideDoi,
}) {
  const { t, formatDate } = useT();
  const report = data?.report;
  const criteria = report?.criteria?.criteria || [];
  const pending = report?.criteria?.pending || [];
  const next = report ? nextStep(data) : nextStep(null);
  const [dois, setDois] = useState({});
  const [doiError, setDoiError] = useState(null);

  const act = (action, criterion) => {
    if (action.action === 'reevaluate') onReevaluate?.();
    else onAction?.(action, criterion);
  };

  const sendDoi = async (index) => {
    setDoiError(null);
    try {
      await onProvideDoi(index, dois[index] || '');
      setDois((d) => ({ ...d, [index]: '' }));
    } catch (err) {
      setDoiError(err?.response?.data?.detail || t('gate.doiFailed'));
    }
  };

  const renderAction = (a, c) => {
    if (a.action === 'provide_doi') return null; // lo resuelve el formulario de DOI
    const label = ACTION_LABELS[a.action]?.(a.agent);
    if (!label || (!onAction && a.action !== 'reevaluate')) return null;
    return (
      <button key={a.action + (a.agent || '')} className="btn btn-secondary btn-sm"
        onClick={() => act(a, c.criterion)} disabled={busy}>
        {label}
      </button>
    );
  };

  return (
    <div className="card" aria-label={t('gate.reportAria')}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 'var(--space-3)' }}>
        <ShieldCheck size={14} />
        <strong style={{ fontSize: 'var(--font-size-sm)', flex: 1 }}>{t('gate.title')}</strong>
        {onReevaluate && (
          <button className="btn btn-ghost btn-sm" onClick={onReevaluate} disabled={busy}
            aria-label={t('gate.reevaluateAria')}>
            <RefreshCw size={12} /> {t('gate.reevaluate')}
          </button>
        )}
      </div>

      {loading && <div style={{ color: 'var(--text-muted)' }}>{t('gate.loading')}</div>}

      {!loading && error && (
        <div role="alert" style={{ fontSize: 'var(--font-size-xs)', color: 'var(--error)' }}>
          {error}{' '}
          {onRetry && <button className="btn btn-ghost btn-sm" onClick={onRetry}>{t('common.retry')}</button>}
        </div>
      )}

      {!loading && !error && !report && (
        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
          {t('gate.noReport')}
        </div>
      )}

      {!loading && !error && (onReevaluate || onAction) && (
        <div role="status" style={{
          fontSize: 'var(--font-size-xs)', marginBottom: 'var(--space-3)', padding: 'var(--space-2)',
          border: '1px solid var(--border)', borderRadius: 'var(--radius-md)',
        }}>
          <strong>{t('gate.nextStep')}</strong> {next.text}
          {next.action && next.action.action !== 'provide_doi'
            && (next.action.action === 'reevaluate' ? onReevaluate : onAction) && (
            <div style={{ marginTop: 6 }}>
              <button className="btn btn-primary btn-sm" disabled={busy}
                onClick={() => act(next.action, next.action.criterion)}>
                {next.action.action === 'reevaluate' ? t('gate.reevaluate') : ACTION_LABELS[next.action.action]?.(next.action.agent)}
                {' '}<ArrowRight size={12} />
              </button>
            </div>
          )}
        </div>
      )}

      {report && (
        <>
          <div style={{ marginBottom: 'var(--space-3)' }}>
            <span className={`badge ${report.criteria.passed ? 'badge-approved' : 'badge-error'}`}>
              {report.criteria.passed ? t('gate.noBlockers') : t('gate.withBlockers')}
            </span>
            {!data.current && (
              <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--warning)', marginTop: 6 }}>
                {t('gate.textChanged')}
              </div>
            )}
            <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', marginTop: 4 }}>
              {t('gate.evaluatedOn', { when: formatDate(report.created_at, { dateStyle: 'short', timeStyle: 'medium' }) })}
            </div>
          </div>

          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {criteria.map((c) => {
              const st = CRITERION_STATUS[c.status] || CRITERION_STATUS.not_verified;
              const blocks = BLOCKING.has(c.status);
              const lines = blocks ? evidenceLines(c) : summaryLines(c);
              const items = !blocks ? (c.summary?.items || []) : [];
              const doiTargets = blocks
                ? (c.actions || []).filter((a) => a.action === 'provide_doi').flatMap((a) => a.targets || [])
                : [];
              return (
                <li key={c.criterion}>
                  <details open={blocks}>
                    <summary style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span className={`badge ${st.cls}`}>{st.label}</span>
                      <span style={{ fontSize: 'var(--font-size-sm)' }}>
                        {CRITERION_LABELS[c.criterion] || c.criterion}
                      </span>
                    </summary>
                    <div style={{ fontSize: 'var(--font-size-xs)', marginTop: 4, color: 'var(--text-secondary)' }}>
                      {lines.slice(0, 5).map((l, i) => <div key={i}>{l}</div>)}
                      {lines.length > 5 && <div>{t('gate.andMore', { count: lines.length - 5 })}</div>}
                      {items.length > 0 && (
                        <ul style={{ paddingLeft: 18, margin: '4px 0 0' }}>
                          {items.map((it, i) => (
                            <li key={i}>«{it.title || t('gate.untitled')}»{it.doi ? ` · ${it.doi}` : ''}</li>
                          ))}
                        </ul>
                      )}
                      {blocks && c.responsible_agent && (
                        <div style={{ marginTop: 2 }}>
                          {t('gate.responsible')} <strong>{agentLabel(c.responsible_agent)}</strong>
                        </div>
                      )}
                      {onProvideDoi && doiTargets.length > 0 && (
                        <div style={{ marginTop: 6 }}>
                          <div>{t('gate.doiPrompt')}</div>
                          {doiTargets.map((index) => (
                            <div key={index} style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                              <input className="input" style={{ flex: 1 }} placeholder={t('gate.doiOfRef', { index })}
                                aria-label={t('gate.doiOfRef', { index })}
                                value={dois[index] || ''} onChange={(e) => setDois((d) => ({ ...d, [index]: e.target.value }))} />
                              <button className="btn btn-secondary btn-sm" disabled={busy || !(dois[index] || '').trim()}
                                onClick={() => sendDoi(index)}>
                                {t('gate.provide')}
                              </button>
                            </div>
                          ))}
                          {doiError && <div role="alert" style={{ color: 'var(--error)', marginTop: 4 }}>{doiError}</div>}
                        </div>
                      )}
                      {blocks && (c.actions || []).length > 0 && (
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                          {c.actions.map((a) => renderAction(a, c))}
                        </div>
                      )}
                    </div>
                  </details>
                </li>
              );
            })}
          </ul>

          {pending.length > 0 && (
            <details style={{ marginTop: 'var(--space-3)' }}>
              <summary style={{ cursor: 'pointer', fontSize: 'var(--font-size-xs)' }}>
                {t('gate.pending', { count: pending.length })}
              </summary>
              <ul style={{ fontSize: 'var(--font-size-xs)', paddingLeft: 18, margin: '6px 0 0' }}>
                {pending.map((p) => (
                  <li key={p.id}>
                    <strong>{p.id}</strong> — {p.phase}
                    {PENDING_REASONS[p.id] && <div style={{ color: 'var(--text-muted)' }}>{PENDING_REASONS[p.id]}</div>}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </div>
  );
}
