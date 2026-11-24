// Panel de candidatos y biblioteca bibliográfica — SPEC-034 / T22.8 (AC3, AC9).
//
// Muestra las fichas de `library_documents` con DOI, año, revista y estado de
// verificación; deja aceptar, descartar o marcar «imprescindible» a los candidatos,
// editar metadatos (aportar el DOI es lo que verifica una ficha, con quién y cuándo) e
// importar BibTeX o una lista de DOI. Una ficha «sin verificar» se puede consultar como
// contexto pero no entra en Referencias (ADR-0011): el panel lo dice, no lo esconde.
//
// Estados de datos: cargando / vacío por pestaña / error con reintento (`AsyncState`).
// El estado vacío y el error no se confunden: fallar al preguntar no es «no hay fichas».
import React, { useCallback, useEffect, useId, useMemo, useState } from 'react';
import { BookOpen, Check, Pencil, Search, Star, Upload, X } from 'lucide-react';
import toast from 'react-hot-toast';
import { agentsApi } from '../../api/agents';
import { mensajeDeCarga } from '../../api/errors';
import { AsyncState, EmptyState } from '../ui/states';
import Modal from '../ui/Modal';
import { translate, useTranslation } from '../../i18n';

const PESTANAS = [
  { id: 'candidate', labelKey: 'library.tabs.candidate' },
  { id: 'accepted', labelKey: 'library.tabs.accepted' },
  { id: 'discarded', labelKey: 'library.tabs.discarded' },
];

const VACIOS = {
  candidate: {
    titleKey: 'library.empty.candidate.title',
    descriptionKey: 'library.empty.candidate.description',
  },
  accepted: {
    titleKey: 'library.empty.accepted.title',
    descriptionKey: 'library.empty.accepted.description',
  },
  discarded: {
    titleKey: 'library.empty.discarded.title',
    descriptionKey: 'library.empty.discarded.description',
  },
};

const METODO = { doi_resolved: 'library.method.doi_resolved', author_supplied: 'library.method.author_supplied' };

function errorDe(err, fallback) {
  const detail = err?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

/** Estado de verificación: texto siempre (no solo color) para que no dependa de verlo. */
export function VerificationBadge({ record }) {
  const { t } = useTranslation();
  if (record.author_provided) {
    return (
      <span className="badge badge-approved" title={record.author_provided_at
        ? t('library.authorProvidedAt', { date: record.author_provided_at }) : t('library.authorProvidedTitle')}>
        {t('library.authorProvided')}
      </span>
    );
  }
  if (!record.verified) {
    return <span className="badge badge-pending" title={t('library.unverifiedTitle')}>{t('library.unverified')}</span>;
  }
  return (
    <span className="badge badge-approved" title={record.verified_at ? t('library.verifiedAt', { date: record.verified_at }) : undefined}>
      {METODO[record.verification_method] ? t(METODO[record.verification_method]) : t('library.verified')}
    </span>
  );
}

function EditRecordModal({ record, onClose, onSaved }) {
  const { t } = useTranslation();
  const uid = useId();
  const [form, setForm] = useState({
    title: record.title || '',
    authors: (record.authors || []).join('; '),
    year: record.year ?? '',
    journal: record.journal || '',
    doi: record.doi || '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    const year = String(form.year).trim();
    try {
      const saved = await agentsApi.updateLibraryRecord(record.id, {
        title: form.title,
        authors: form.authors,
        year: year ? Number(year) : null,
        journal: form.journal,
        doi: form.doi,
      });
      toast.success(t('library.edit.saved'));
      onSaved(saved);
    } catch (err) {
      setError(errorDe(err, t('library.edit.saveError')));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal onClose={onClose} title={t('library.edit.title')} panelStyle={{ maxWidth: 560 }}>
      <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <div className="input-group">
          <label className="input-label" htmlFor={`${uid}-title`}>{t('library.edit.titleField')}</label>
          <input id={`${uid}-title`} className="input" value={form.title} onChange={set('title')} required />
        </div>
        <div className="input-group">
          <label className="input-label" htmlFor={`${uid}-authors`}>{t('library.edit.authors')}</label>
          <input id={`${uid}-authors`} className="input" value={form.authors} onChange={set('authors')} />
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
          <div className="input-group" style={{ width: 110 }}>
            <label className="input-label" htmlFor={`${uid}-year`}>{t('library.edit.year')}</label>
            <input id={`${uid}-year`} className="input" type="number" min="1000" max="2100" value={form.year} onChange={set('year')} />
          </div>
          <div className="input-group" style={{ flex: 1 }}>
            <label className="input-label" htmlFor={`${uid}-journal`}>{t('library.edit.journal')}</label>
            <input id={`${uid}-journal`} className="input" value={form.journal} onChange={set('journal')} />
          </div>
        </div>
        <div className="input-group">
          <label className="input-label" htmlFor={`${uid}-doi`}>{t('library.edit.doi')}</label>
          <input id={`${uid}-doi`} className="input" value={form.doi} onChange={set('doi')} placeholder={t('library.edit.doiPlaceholder')} aria-describedby={`${uid}-doi-help`} />
          <span id={`${uid}-doi-help`} style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
            {t('library.edit.doiHelp')}
          </span>
        </div>
        {error && <div role="alert" style={{ color: 'var(--error)', fontSize: 'var(--font-size-sm)' }}>{error}</div>}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>{t('library.cancel')}</button>
          <button type="submit" className="btn btn-primary btn-sm" disabled={saving}>{saving ? t('library.saving') : t('library.save')}</button>
        </div>
      </form>
    </Modal>
  );
}

function ImportModal({ onClose, onDone }) {
  const { t } = useTranslation();
  const uid = useId();
  const [mode, setMode] = useState('bibtex');
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [results, setResults] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const res = await agentsApi.importLibraryRecords(mode === 'bibtex' ? { bibtex: text } : { dois: text });
      setResults(res.results || []);
      onDone();
    } catch (err) {
      setError(errorDe(err, t('library.import.error')));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal onClose={onClose} title={t('library.import.title')} panelStyle={{ maxWidth: 620 }}>
      {results ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <p role="status">{t('library.import.summary', { imported: results.filter((r) => r.status === 'imported').length, total: results.length })}</p>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', maxHeight: 280, overflow: 'auto' }}>
            {results.map((r) => (
              <li key={`${r.ref}-${r.document_id || r.status}`} style={{ fontSize: 'var(--font-size-sm)' }}>
                <strong>{r.ref}</strong>
                {' — '}
                {r.status === 'imported' ? (r.verified ? t('library.import.importedVerified') : t('library.import.importedUnverified')) : r.status === 'duplicate' ? t('library.import.duplicate') : t('library.import.notImported')}
                {r.detail ? <span style={{ color: 'var(--text-muted)' }}> ({r.detail})</span> : null}
              </li>
            ))}
          </ul>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button type="button" className="btn btn-primary btn-sm" onClick={onClose}>{t('library.close')}</button>
          </div>
        </div>
      ) : (
        <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <div role="group" aria-label={t('library.import.formatAria')} style={{ display: 'flex', gap: 'var(--space-2)' }}>
            {[['bibtex', t('library.import.modeBibtex')], ['dois', t('library.import.modeDois')]].map(([id, label]) => (
              <button key={id} type="button" aria-pressed={mode === id}
                className={`btn btn-sm ${mode === id ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => { setMode(id); setError(''); }}>
                {label}
              </button>
            ))}
          </div>
          <div className="input-group">
            <label className="input-label" htmlFor={`${uid}-text`}>
              {mode === 'bibtex' ? t('library.import.contentBibtex') : t('library.import.contentDois')}
            </label>
            <textarea id={`${uid}-text`} className="input" rows={10} value={text} required
              onChange={(e) => setText(e.target.value)}
              placeholder={mode === 'bibtex' ? t('library.import.placeholderBibtex') : t('library.import.placeholderDois')} />
          </div>
          <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', margin: 0 }}>
            {t('library.import.help')}
          </p>
          {error && <div role="alert" style={{ color: 'var(--error)', fontSize: 'var(--font-size-sm)' }}>{error}</div>}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>{t('library.cancel')}</button>
            <button type="submit" className="btn btn-primary btn-sm" disabled={busy || !text.trim()}>{busy ? t('library.import.importing') : t('library.import.import')}</button>
          </div>
        </form>
      )}
    </Modal>
  );
}

const BASES = {
  openalex: 'OpenAlex', crossref: 'Crossref', semantic_scholar: 'Semantic Scholar',
  arxiv: 'arXiv', pubmed: 'PubMed',
};
const ESTADO_BASE = { ok: 'library.dbStatus.ok', failed: 'library.dbStatus.failed', skipped: 'library.dbStatus.skipped' };

/** Búsqueda de literatura (T22.11 / AC12): la lanza la persona autora y solo crea candidatos verificados. */
function SearchForm({ onFound }) {
  const { t } = useTranslation();
  const uid = useId();
  const [config, setConfig] = useState(null);
  const [configError, setConfigError] = useState(null);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const loadConfig = useCallback(async () => {
    setConfigError(null);
    try {
      const cfg = await agentsApi.getLibrarySearchConfig();
      setConfig(cfg);
      setActive(cfg.sources || []);
    } catch (err) {
      setConfigError(mensajeDeCarga(err, translate('library.search.configError')));
    }
  }, []);
  useEffect(() => { loadConfig(); }, [loadConfig]);

  if (configError) {
    return (
      <div role="alert" style={{ fontSize: 'var(--font-size-sm)', color: 'var(--error)' }}>
        {configError} <button type="button" className="btn btn-ghost btn-sm" onClick={loadConfig}>{t('library.search.retry')}</button>
      </div>
    );
  }
  if (!config) return <p role="status" style={{ margin: 0, fontSize: 'var(--font-size-sm)' }}>{t('library.search.checking')}</p>;
  if (!config.enabled) {
    return (
      <p role="status" style={{ margin: 0, fontSize: 'var(--font-size-sm)', color: 'var(--text-muted)' }}>
        {t('library.search.disabled', { reason: config.message || t('library.search.disabledDefault') })}
      </p>
    );
  }

  const toggle = (db) => setActive((a) => (a.includes(db) ? a.filter((x) => x !== db) : [...a, db]));
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const res = await agentsApi.searchLibrary(query.trim(), active);
      setResult(res);
      if (res.new_candidates > 0) onFound();
    } catch (err) {
      setError(errorDe(err, t('library.search.error')));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} aria-labelledby={`${uid}-title`}
      style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
      <strong id={`${uid}-title`} style={{ fontSize: 'var(--font-size-sm)' }}>{t('library.search.title')}</strong>
      <div className="input-group">
        <label className="input-label" htmlFor={`${uid}-q`}>{t('library.search.query')}</label>
        <input id={`${uid}-q`} className="input" value={query} maxLength={300} required
          aria-describedby={`${uid}-help`} onChange={(e) => setQuery(e.target.value)}
          placeholder={t('library.search.placeholder')} />
        <span id={`${uid}-help`} style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
          {t('library.search.help')}
        </span>
      </div>
      <fieldset style={{ border: 0, padding: 0, margin: 0, display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
        <legend style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>{t('library.search.databases')}</legend>
        {(config.sources || []).map((db) => (
          <label key={db} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 'var(--font-size-sm)' }}>
            <input type="checkbox" checked={active.includes(db)} onChange={() => toggle(db)} />
            {BASES[db] || db}
          </label>
        ))}
      </fieldset>
      <div>
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy || !query.trim() || active.length === 0}>
          <Search size={14} /> {busy ? t('library.search.searching') : t('library.search.search')}
        </button>
      </div>
      <div aria-live="polite">
        {busy && <p role="status" style={{ margin: 0 }}>{t('library.search.searchingVerifying')}</p>}
        {error && <div role="alert" style={{ color: 'var(--error)', fontSize: 'var(--font-size-sm)' }}>{error}</div>}
        {result && (
          <div style={{ fontSize: 'var(--font-size-sm)', display: 'flex', flexDirection: 'column', gap: 4 }}>
            <p style={{ margin: 0 }}>
              {result.new_candidates === 0 ? t('library.search.noNew') : t('library.search.newCandidates', { count: result.new_candidates })}
              {result.already_in_library > 0 && (' ' + t('library.search.alreadyIn', { count: result.already_in_library }))}
            </p>
            <ul style={{ margin: 0, paddingLeft: 'var(--space-4)' }}>
              {(result.sources || []).map((s) => (
                <li key={s.db}>
                  <strong>{BASES[s.db] || s.db}</strong>: {ESTADO_BASE[s.status] ? t(ESTADO_BASE[s.status]) : s.status}
                  {s.status === 'ok' ? t('library.search.sourceCounts', { returned: s.returned, verified: s.verified }) : s.message ? ` — ${s.message}` : ''}
                </li>
              ))}
            </ul>
            {result.status === 'failed' && <p role="alert" style={{ margin: 0, color: 'var(--error)' }}>{result.message}</p>}
          </div>
        )}
      </div>
    </form>
  );
}

function RecordRow({ record, busy, onCurate, onEdit, onUploadPdf, onAuthorProvided }) {
  const { t } = useTranslation();
  const meta = [record.year, record.journal].filter(Boolean).join(' · ');
  const estado = record.curation_status;
  return (
    <li style={{
      display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 'var(--space-3)',
      background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-md)', padding: 'var(--space-3) var(--space-4)',
    }}>
      <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ fontWeight: 500 }}>
          {record.title}
          {record.must_cite && <span className="badge badge-published" style={{ marginLeft: 8 }}>{t('library.record.mustCite')}</span>}
        </div>
        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
          {(record.authors || []).slice(0, 4).join(', ')}{(record.authors || []).length > 4 ? (' ' + t('library.record.etAl')) : ''}
        </div>
        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)', alignItems: 'center' }}>
          {meta && <span>{meta}</span>}
          <span>{t('library.record.doiLabel')} {record.doi ? <code>{record.doi}</code> : <em>{t('library.record.noDoi')}</em>}</span>
          <span>{t('library.record.baseLabel')} {record.source_db}</span>
          <VerificationBadge record={record} />
          {record.text_status === 'abstract_only' && (
            <span className="badge badge-pending" title={t('library.record.abstractOnlyTitle')}>{t('library.record.abstractOnly')}</span>
          )}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 'var(--space-1)', flexShrink: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
        {estado !== 'accepted' && (
          <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => onCurate(record, 'accepted', false)}
            aria-label={t('library.record.acceptAria', { title: record.title })}><Check size={14} /> {t('library.record.accept')}</button>
        )}
        {estado === 'accepted' && (
          <button className="btn btn-ghost btn-sm" disabled={busy} aria-pressed={record.must_cite}
            onClick={() => onCurate(record, 'accepted', !record.must_cite)}
            aria-label={t(record.must_cite ? 'library.record.unmarkAria' : 'library.record.markAria', { title: record.title })}>
            <Star size={14} /> {record.must_cite ? t('library.record.unmark') : t('library.record.mark')}
          </button>
        )}
        {estado !== 'discarded' && (
          <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => onCurate(record, 'discarded', false)}
            aria-label={t('library.record.discardAria', { title: record.title })}><X size={14} style={{ color: 'var(--error)' }} /> {t('library.record.discard')}</button>
        )}
        {estado === 'accepted' && record.text_status === 'abstract_only' && (
          <label className="btn btn-ghost btn-sm" style={{ cursor: busy ? 'not-allowed' : 'pointer' }}
            aria-label={t('library.record.uploadPdfAria', { title: record.title })}>
            <Upload size={14} /> {t('library.record.uploadPdf')}
            <input type="file" accept="application/pdf,.pdf" disabled={busy} style={{ display: 'none' }}
              onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) onUploadPdf(record, f); }} />
          </label>
        )}
        {estado === 'accepted' && !record.doi && (
          <button className="btn btn-ghost btn-sm" disabled={busy}
            onClick={() => onAuthorProvided(record, !record.author_provided)}
            aria-label={t(record.author_provided ? 'library.record.revokeAuthorProvidedAria' : 'library.record.declareAuthorProvidedAria', { title: record.title })}>
            {record.author_provided ? t('library.record.revokeAuthorProvided') : t('library.record.declareAuthorProvided')}
          </button>
        )}
        <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => onEdit(record)}
          aria-label={t('library.record.editAria', { title: record.title })}><Pencil size={14} /> {t('library.record.edit')}</button>
      </div>
    </li>
  );
}

export default function LibraryRecordsPanel() {
  const { t } = useTranslation();
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState('accepted');
  const [busyId, setBusyId] = useState(null);
  const [editing, setEditing] = useState(null);
  const [importing, setImporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await agentsApi.getLibraryRecords();
      setRecords(data.documents || []);
    } catch (err) {
      setError(mensajeDeCarga(err, translate('library.panel.loadError')));
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const counts = useMemo(() => {
    const c = { candidate: 0, accepted: 0, discarded: 0 };
    records.forEach((r) => { c[r.curation_status] = (c[r.curation_status] || 0) + 1; });
    return c;
  }, [records]);
  const visibles = records.filter((r) => r.curation_status === tab);
  const replace = (saved) => setRecords((rs) => rs.map((r) => (r.id === saved.id ? saved : r)));

  const curate = async (record, status, mustCite) => {
    setBusyId(record.id);
    try {
      const saved = await agentsApi.curateLibraryRecord(record.id, status, mustCite);
      replace(saved);
      if (status !== 'accepted') toast.success(t('library.panel.discarded'));
      else if (mustCite) toast.success(t('library.panel.markedMustCite'));
      else if (saved.fulltext === 'full_text') toast.success(t('library.panel.addedFullText'));
      else if (saved.text_status === 'abstract_only') toast.success(t('library.panel.addedAbstract'));
      else toast.success(t('library.panel.added'));
    } catch (err) {
      toast.error(errorDe(err, t('library.panel.updateError')));
    } finally {
      setBusyId(null);
    }
  };

  const authorProvided = async (record, declared) => {
    setBusyId(record.id);
    try {
      const saved = await agentsApi.declareLibraryRecordAuthorProvided(record.id, declared);
      replace(saved);
      toast.success(t(declared ? 'library.record.authorProvidedDone' : 'library.record.authorProvidedRevoked'));
    } catch (err) {
      toast.error(errorDe(err, t('library.record.authorProvidedError')));
    } finally {
      setBusyId(null);
    }
  };

  const uploadPdf = async (record, file) => {
    setBusyId(record.id);
    try {
      const res = await agentsApi.uploadLibraryDocument(file, undefined, undefined, undefined, record.id);
      replace(res.library_document);
      toast.success(t('library.panel.pdfIndexed'));
    } catch (err) {
      toast.error(errorDe(err, t('library.panel.pdfError')));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="config-section" style={{ marginBottom: 'var(--space-6)' }} aria-labelledby="library-records-title">
      <div className="config-section-header" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <BookOpen size={15} />
          <h3 id="library-records-title" style={{ margin: 0, fontSize: 'inherit', fontWeight: 600 }}>{t('library.panel.title')}</h3>
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => setImporting(true)}>
          <Upload size={14} /> {t('library.panel.importButton')}
        </button>
      </div>
      <div className="config-section-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <SearchForm onFound={() => { setTab('candidate'); load(); }} />
        <div role="group" aria-label={t('library.panel.statusAria')} style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          {PESTANAS.map((p) => (
            <button key={p.id} type="button" aria-pressed={tab === p.id}
              className={`btn btn-sm ${tab === p.id ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setTab(p.id)}>
              {t(p.labelKey)} ({counts[p.id] || 0})
            </button>
          ))}
        </div>
        <AsyncState
          loading={loading}
          error={error}
          isEmpty={visibles.length === 0}
          onRetry={load}
          loadingLabel={t('library.panel.loading')}
          empty={(
            <EmptyState
              icon={<BookOpen size={28} />}
              title={t(VACIOS[tab].titleKey)}
              description={t(VACIOS[tab].descriptionKey)}
            />
          )}
        >
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {visibles.map((r) => (
              <RecordRow key={r.id} record={r} busy={busyId === r.id} onCurate={curate} onEdit={setEditing} onUploadPdf={uploadPdf} onAuthorProvided={authorProvided} />
            ))}
          </ul>
        </AsyncState>
      </div>
      {editing && (
        <EditRecordModal record={editing} onClose={() => setEditing(null)}
          onSaved={(saved) => { replace(saved); setEditing(null); }} />
      )}
      {importing && <ImportModal onClose={() => setImporting(false)} onDone={load} />}
    </section>
  );
}
