import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle, CircleAlert, FileText, Info, UserCheck } from 'lucide-react';
import { articlesApi } from '../api/articles';

// Estado automático de cada cita (SPEC-035). El texto lleva el significado: el color solo acompaña.
const STATUS = {
  supported: { label: 'Respaldada', cls: 'ath-completed', Icon: CheckCircle },
  partial: { label: 'Parcialmente respaldada', cls: 'ath-badge', Icon: Info },
  unsupported: { label: 'No respaldada', cls: 'ath-error', Icon: CircleAlert },
  not_verified: { label: 'No verificada', cls: 'ath-badge', Icon: Info },
};
const when = v => v ? new Date(/Z$|[+-]\d\d:\d\d$/.test(v) ? v : `${v}Z`).toLocaleString('es-CL') : '';

function Row({ link, onConfirm, pending }) {
  const st = STATUS[link.status] || STATUS.not_verified;
  const { Icon } = st;
  const place = link.doc_id
    ? `Documento ${link.doc_id}${link.page ? `, página ${link.page}` : link.section ? `, sección ${link.section}` : ', página desconocida'}`
    : null;
  return (
    <li className="ath-source ath-citation">
      <p>
        <strong>[{link.citation_key}]</strong>{' '}
        <span className={`ath-badge ${st.cls}`}><Icon size={14} strokeWidth={1.5} aria-hidden="true" />{st.label}</span>
      </p>
      {link.claim && <p>Afirmación: «{link.claim}»</p>}
      {link.excerpt
        ? <blockquote className="ath-muted">{link.excerpt}</blockquote>
        : <p className="ath-muted">Sin extracto: la cita no apunta a un fragmento de la biblioteca.</p>}
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
        ? <p><span className="ath-badge ath-completed"><UserCheck size={14} aria-hidden="true" />Confirmada manualmente el {when(link.confirmed_at)}</span></p>
        : (
          <button className="btn btn-secondary btn-sm" disabled={pending}
            aria-label={`Confirmar manualmente la cita ${link.citation_key}`}
            onClick={() => onConfirm(link.id)}>
            {pending ? 'Confirmando…' : 'Confirmar manualmente'}
          </button>
        )}
    </li>
  );
}

export default function ArticleCitations({ articleId, projectId }) {
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
      .catch(e => { if (live) setError(e.response?.status === 403 ? 'No tienes permiso para consultar las citas de este artículo.' : 'No se pudieron cargar las citas.'); });
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
        ? 'Solo la persona autora puede confirmar una cita.'
        : 'No se pudo confirmar la cita. Inténtalo de nuevo.');
    } finally {
      setPending(null);
    }
  }

  return (
    <section className="ath-card" aria-labelledby="ath-citations-title" aria-busy={links === null && !error}>
      <h2 id="ath-citations-title" ref={headingRef} tabIndex={-1}>Citas del artículo{links ? ` (${links.length})` : ''}</h2>
      <p className="ath-muted">Cada cita del texto actual con su estado, el extracto en que se apoya y el documento. La confirmación manual queda registrada con quién y cuándo, y no cambia el veredicto automático.</p>
      {error && (
        <div role="alert" className="ath-alert">
          <CircleAlert size={16} aria-hidden="true" /><span>{error}</span>
          <button className="btn btn-secondary btn-sm" onClick={load}>Reintentar</button>
        </div>
      )}
      {actionError && <div role="alert" className="ath-alert"><CircleAlert size={16} aria-hidden="true" /><span>{actionError}</span></div>}
      {links === null && !error && <p role="status">Cargando citas…</p>}
      {links && links.length === 0 && (
        <p role="status">No hay citas evaluadas para la versión actual del texto. Aparecerán aquí cuando se evalúen las citas de esta versión.</p>
      )}
      {links && links.length > 0 && (
        <ul className="ath-citation-list" style={{ listStyle: 'none', padding: 0 }}>
          {links.map(l => <Row key={l.id} link={l} onConfirm={confirm} pending={pending === l.id} />)}
        </ul>
      )}
    </section>
  );
}
