import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle, CircleAlert, FileText, Info, UserCheck } from 'lucide-react';
import { articlesApi } from '../api/articles';
import { useT } from '../i18n/useT';

// Estado automático de cada cita (SPEC-035). El texto lleva el significado: el color solo acompaña.
const STATUS = {
  supported: { label: 'citations.status.supported', cls: 'ath-completed', Icon: CheckCircle },
  partial: { label: 'citations.status.partial', cls: 'ath-badge', Icon: Info },
  unsupported: { label: 'citations.status.unsupported', cls: 'ath-error', Icon: CircleAlert },
  not_verified: { label: 'citations.status.not_verified', cls: 'ath-badge', Icon: Info },
};
const when = v => v ? new Date(/Z$|[+-]\d\d:\d\d$/.test(v) ? v : `${v}Z`).toLocaleString('es-CL') : '';

function Row({ link, onConfirm, pending }) {
  const { t } = useT();
  const st = STATUS[link.status] || STATUS.not_verified;
  const { Icon } = st;
  const place = link.doc_id
    ? t(link.page ? 'citations.place.page' : link.section ? 'citations.place.section' : 'citations.place.unknown',
      { doc: link.doc_id, page: link.page, section: link.section })
    : null;
  return (
    <li className="ath-source ath-citation">
      <p>
        <strong>[{link.citation_key}]</strong>{' '}
        <span className={`ath-badge ${st.cls}`}><Icon size={14} strokeWidth={1.5} aria-hidden="true" />{t(st.label)}</span>
      </p>
      {link.claim && <p>{t('citations.claim', { claim: link.claim })}</p>}
      {link.excerpt
        ? <blockquote className="ath-muted">{link.excerpt}</blockquote>
        : <p className="ath-muted">{t('citations.noExcerpt')}</p>}
      {link.rationale && <p className="ath-muted">{link.rationale}</p>}
      {place && (
        <p>
          <FileText size={14} aria-hidden="true" />{' '}
          <Link to={`/dashboard/documents?doc=${encodeURIComponent(link.doc_id)}${link.page ? `&page=${link.page}` : ''}`}>
            {place}
          </Link>
        </p>
      )}
      {link.confirmed_at
        ? <p><span className="ath-badge ath-completed"><UserCheck size={14} aria-hidden="true" />{t('citations.confirmedOn', { when: when(link.confirmed_at) })}</span></p>
        : (
          <button className="btn btn-secondary btn-sm" disabled={pending}
            aria-label={t('citations.confirmAria', { key: link.citation_key })}
            onClick={() => onConfirm(link.id)}>
            {pending ? t('citations.confirming') : t('citations.confirm')}
          </button>
        )}
    </li>
  );
}

export default function ArticleCitations({ articleId, projectId }) {
  const { t } = useT();
  const [links, setLinks] = useState(null);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [pending, setPending] = useState(null);
  const headingRef = useRef(null);

  const load = useCallback(() => {
    setLinks(null); setError('');
    let live = true;
    articlesApi.citations(articleId)
      .then(r => { if (live) setLinks(r.citations || []); })
      .catch(e => { if (live) setError(e.response?.status === 403 ? 'citations.errorForbidden' : 'citations.errorLoad'); });
    return () => { live = false; };
  }, [articleId, projectId]);
  useEffect(() => load(), [load]);

  async function confirm(linkId) {
    setPending(linkId); setActionError('');
    try {
      const updated = await articlesApi.confirmCitation(articleId, linkId);
      setLinks(ls => ls.map(l => l.id === linkId ? updated : l));
    } catch (e) {
      setActionError(e.response?.status === 403
        ? 'citations.confirmForbidden'
        : 'citations.confirmFailed');
    } finally {
      setPending(null);
    }
  }

  return (
    <section className="ath-card" aria-labelledby="ath-citations-title" aria-busy={links === null && !error}>
      <h2 id="ath-citations-title" ref={headingRef} tabIndex={-1}>{links ? t('citations.titleCount', { count: links.length }) : t('citations.title')}</h2>
      <p className="ath-muted">{t('citations.intro')}</p>
      {error && (
        <div role="alert" className="ath-alert">
          <CircleAlert size={16} aria-hidden="true" /><span>{t(error)}</span>
          <button className="btn btn-secondary btn-sm" onClick={load}>{t('common.retry')}</button>
        </div>
      )}
      {actionError && <div role="alert" className="ath-alert"><CircleAlert size={16} aria-hidden="true" /><span>{t(actionError)}</span></div>}
      {links === null && !error && <p role="status">{t('citations.loading')}</p>}
      {links && links.length === 0 && (
        <p role="status">{t('citations.empty')}</p>
      )}
      {links && links.length > 0 && (
        <ul className="ath-citation-list" style={{ listStyle: 'none', padding: 0 }}>
          {links.map(l => <Row key={l.id} link={l} onConfirm={confirm} pending={pending === l.id} />)}
        </ul>
      )}
    </section>
  );
}
