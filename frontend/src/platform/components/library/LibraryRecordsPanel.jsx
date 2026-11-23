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

const PESTANAS = [
  { id: 'candidate', label: 'Candidatos' },
  { id: 'accepted', label: 'Biblioteca' },
  { id: 'discarded', label: 'Descartados' },
];

const VACIOS = {
  candidate: {
    title: 'Sin candidatos por revisar',
    description: 'Los candidatos verificados que proponga la búsqueda bibliográfica aparecerán aquí para que los aceptes o descartes.',
  },
  accepted: {
    title: 'La biblioteca no tiene fichas',
    description: 'Acepta un candidato o importa referencias en BibTeX o una lista de DOI.',
  },
  discarded: {
    title: 'Nada descartado',
    description: 'Los candidatos que descartes se quedan aquí por si cambias de idea.',
  },
};

const METODO = { doi_resolved: 'DOI resuelto', author_supplied: 'DOI aportado por la autora' };

function errorDe(err, fallback) {
  const detail = err?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

/** Estado de verificación: texto siempre (no solo color) para que no dependa de verlo. */
export function VerificationBadge({ record }) {
  if (!record.verified) {
    return <span className="badge badge-pending" title="Sin DOI verificado: solo sirve como contexto, no entra en Referencias">Sin verificar</span>;
  }
  return (
    <span className="badge badge-approved" title={record.verified_at ? `Verificado ${record.verified_at}` : undefined}>
      {METODO[record.verification_method] || 'Verificado'}
    </span>
  );
}

function EditRecordModal({ record, onClose, onSaved }) {
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
      toast.success('Ficha actualizada');
      onSaved(saved);
    } catch (err) {
      setError(errorDe(err, 'No se pudo guardar la ficha'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal onClose={onClose} title="Editar metadatos" panelStyle={{ maxWidth: 560 }}>
      <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <div className="input-group">
          <label className="input-label" htmlFor={`${uid}-title`}>Título</label>
          <input id={`${uid}-title`} className="input" value={form.title} onChange={set('title')} required />
        </div>
        <div className="input-group">
          <label className="input-label" htmlFor={`${uid}-authors`}>Autores (separados por punto y coma)</label>
          <input id={`${uid}-authors`} className="input" value={form.authors} onChange={set('authors')} />
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
          <div className="input-group" style={{ width: 110 }}>
            <label className="input-label" htmlFor={`${uid}-year`}>Año</label>
            <input id={`${uid}-year`} className="input" type="number" min="1000" max="2100" value={form.year} onChange={set('year')} />
          </div>
          <div className="input-group" style={{ flex: 1 }}>
            <label className="input-label" htmlFor={`${uid}-journal`}>Revista</label>
            <input id={`${uid}-journal`} className="input" value={form.journal} onChange={set('journal')} />
          </div>
        </div>
        <div className="input-group">
          <label className="input-label" htmlFor={`${uid}-doi`}>DOI</label>
          <input id={`${uid}-doi`} className="input" value={form.doi} onChange={set('doi')} placeholder="10.xxxx/xxxxx" aria-describedby={`${uid}-doi-help`} />
          <span id={`${uid}-doi-help`} style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
            Un DOI nuevo queda verificado como aportado por ti, con tu usuario y la fecha. Vaciarlo retira la verificación.
          </span>
        </div>
        {error && <div role="alert" style={{ color: 'var(--error)', fontSize: 'var(--font-size-sm)' }}>{error}</div>}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Cancelar</button>
          <button type="submit" className="btn btn-primary btn-sm" disabled={saving}>{saving ? 'Guardando…' : 'Guardar'}</button>
        </div>
      </form>
    </Modal>
  );
}

function ImportModal({ onClose, onDone }) {
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
      setError(errorDe(err, 'No se pudo importar'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal onClose={onClose} title="Importar referencias" panelStyle={{ maxWidth: 620 }}>
      {results ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <p role="status">{results.filter((r) => r.status === 'imported').length} de {results.length} importadas.</p>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', maxHeight: 280, overflow: 'auto' }}>
            {results.map((r) => (
              <li key={`${r.ref}-${r.document_id || r.status}`} style={{ fontSize: 'var(--font-size-sm)' }}>
                <strong>{r.ref}</strong>
                {' — '}
                {r.status === 'imported' ? (r.verified ? 'importada y verificada' : 'importada sin verificar') : r.status === 'duplicate' ? 'ya existía' : 'no importada'}
                {r.detail ? <span style={{ color: 'var(--text-muted)' }}> ({r.detail})</span> : null}
              </li>
            ))}
          </ul>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button type="button" className="btn btn-primary btn-sm" onClick={onClose}>Cerrar</button>
          </div>
        </div>
      ) : (
        <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <div role="group" aria-label="Formato de importación" style={{ display: 'flex', gap: 'var(--space-2)' }}>
            {[['bibtex', 'BibTeX'], ['dois', 'Lista de DOI']].map(([id, label]) => (
              <button key={id} type="button" aria-pressed={mode === id}
                className={`btn btn-sm ${mode === id ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => { setMode(id); setError(''); }}>
                {label}
              </button>
            ))}
          </div>
          <div className="input-group">
            <label className="input-label" htmlFor={`${uid}-text`}>
              {mode === 'bibtex' ? 'Contenido BibTeX' : 'DOI (uno por línea)'}
            </label>
            <textarea id={`${uid}-text`} className="input" rows={10} value={text} required
              onChange={(e) => setText(e.target.value)}
              placeholder={mode === 'bibtex' ? '@article{clave,\n  title = {…},\n  doi = {10.xxxx/xxxxx}\n}' : '10.1000/xyz123\nhttps://doi.org/10.1000/abc456'} />
          </div>
          <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', margin: 0 }}>
            Cada DOI se comprueba contra Crossref/OpenAlex. Lo que no se pueda verificar se importa «sin verificar» y no podrá citarse hasta que aportes el DOI.
          </p>
          {error && <div role="alert" style={{ color: 'var(--error)', fontSize: 'var(--font-size-sm)' }}>{error}</div>}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Cancelar</button>
            <button type="submit" className="btn btn-primary btn-sm" disabled={busy || !text.trim()}>{busy ? 'Importando…' : 'Importar'}</button>
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
const ESTADO_BASE = { ok: 'respondió', failed: 'falló', skipped: 'omitida' };

/** Búsqueda de literatura (T22.11 / AC12): la lanza la persona autora y solo crea candidatos verificados. */
function SearchForm({ onFound }) {
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
      setConfigError(mensajeDeCarga(err, 'No se pudo comprobar si la búsqueda está disponible'));
    }
  }, []);
  useEffect(() => { loadConfig(); }, [loadConfig]);

  if (configError) {
    return (
      <div role="alert" style={{ fontSize: 'var(--font-size-sm)', color: 'var(--error)' }}>
        {configError} <button type="button" className="btn btn-ghost btn-sm" onClick={loadConfig}>Reintentar</button>
      </div>
    );
  }
  if (!config) return <p role="status" style={{ margin: 0, fontSize: 'var(--font-size-sm)' }}>Comprobando la búsqueda bibliográfica…</p>;
  if (!config.enabled) {
    return (
      <p role="status" style={{ margin: 0, fontSize: 'var(--font-size-sm)', color: 'var(--text-muted)' }}>
        La búsqueda bibliográfica está desactivada ({config.message || 'descubrimiento desactivado'}). Puedes seguir
        usando las referencias ya importadas.
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
      setError(errorDe(err, 'No se pudo completar la búsqueda'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} aria-labelledby={`${uid}-title`}
      style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
      <strong id={`${uid}-title`} style={{ fontSize: 'var(--font-size-sm)' }}>Buscar referencias</strong>
      <div className="input-group">
        <label className="input-label" htmlFor={`${uid}-q`}>Consulta</label>
        <input id={`${uid}-q`} className="input" value={query} maxLength={300} required
          aria-describedby={`${uid}-help`} onChange={(e) => setQuery(e.target.value)}
          placeholder="p. ej. deep learning image recognition" />
        <span id={`${uid}-help`} style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
          La consulta se envía a las bases marcadas. No pegues texto de tu manuscrito. Solo se guardan
          como candidatos las referencias cuyo DOI se verifica.
        </span>
      </div>
      <fieldset style={{ border: 0, padding: 0, margin: 0, display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
        <legend style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>Bases</legend>
        {(config.sources || []).map((db) => (
          <label key={db} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 'var(--font-size-sm)' }}>
            <input type="checkbox" checked={active.includes(db)} onChange={() => toggle(db)} />
            {BASES[db] || db}
          </label>
        ))}
      </fieldset>
      <div>
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy || !query.trim() || active.length === 0}>
          <Search size={14} /> {busy ? 'Buscando…' : 'Buscar'}
        </button>
      </div>
      <div aria-live="polite">
        {busy && <p role="status" style={{ margin: 0 }}>Buscando y verificando referencias…</p>}
        {error && <div role="alert" style={{ color: 'var(--error)', fontSize: 'var(--font-size-sm)' }}>{error}</div>}
        {result && (
          <div style={{ fontSize: 'var(--font-size-sm)', display: 'flex', flexDirection: 'column', gap: 4 }}>
            <p style={{ margin: 0 }}>
              {result.new_candidates === 0 ? 'No hay candidatos verificados nuevos.' : `${result.new_candidates} candidato(s) nuevo(s) verificado(s) en «Candidatos».`}
              {result.already_in_library > 0 && ` ${result.already_in_library} ya estaban en la biblioteca.`}
            </p>
            <ul style={{ margin: 0, paddingLeft: 'var(--space-4)' }}>
              {(result.sources || []).map((s) => (
                <li key={s.db}>
                  <strong>{BASES[s.db] || s.db}</strong>: {ESTADO_BASE[s.status] || s.status}
                  {s.status === 'ok' ? ` — ${s.returned} devueltos, ${s.verified} verificados` : s.message ? ` — ${s.message}` : ''}
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

function RecordRow({ record, busy, onCurate, onEdit, onUploadPdf }) {
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
          {record.must_cite && <span className="badge badge-published" style={{ marginLeft: 8 }}>Imprescindible</span>}
        </div>
        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
          {(record.authors || []).slice(0, 4).join(', ')}{(record.authors || []).length > 4 ? ' et al.' : ''}
        </div>
        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)', alignItems: 'center' }}>
          {meta && <span>{meta}</span>}
          <span>DOI: {record.doi ? <code>{record.doi}</code> : <em>sin DOI</em>}</span>
          <span>Base: {record.source_db}</span>
          <VerificationBadge record={record} />
          {record.text_status === 'abstract_only' && (
            <span className="badge badge-pending" title="Solo hay el resumen de la base: sube el PDF para tener el texto completo">solo resumen</span>
          )}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 'var(--space-1)', flexShrink: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
        {estado !== 'accepted' && (
          <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => onCurate(record, 'accepted', false)}
            aria-label={`Aceptar ${record.title}`}><Check size={14} /> Aceptar</button>
        )}
        {estado === 'accepted' && (
          <button className="btn btn-ghost btn-sm" disabled={busy} aria-pressed={record.must_cite}
            onClick={() => onCurate(record, 'accepted', !record.must_cite)}
            aria-label={`${record.must_cite ? 'Quitar la marca imprescindible de' : 'Marcar como imprescindible'} ${record.title}`}>
            <Star size={14} /> {record.must_cite ? 'Quitar marca' : 'Imprescindible'}
          </button>
        )}
        {estado !== 'discarded' && (
          <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => onCurate(record, 'discarded', false)}
            aria-label={`Descartar ${record.title}`}><X size={14} style={{ color: 'var(--error)' }} /> Descartar</button>
        )}
        {estado === 'accepted' && record.text_status === 'abstract_only' && (
          <label className="btn btn-ghost btn-sm" style={{ cursor: busy ? 'not-allowed' : 'pointer' }}
            aria-label={`Subir el PDF de ${record.title}`}>
            <Upload size={14} /> Subir PDF
            <input type="file" accept="application/pdf,.pdf" disabled={busy} style={{ display: 'none' }}
              onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) onUploadPdf(record, f); }} />
          </label>
        )}
        <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => onEdit(record)}
          aria-label={`Editar metadatos de ${record.title}`}><Pencil size={14} /> Editar</button>
      </div>
    </li>
  );
}

export default function LibraryRecordsPanel() {
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
      setError(mensajeDeCarga(err, 'No se pudieron cargar las fichas bibliográficas'));
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
      if (status !== 'accepted') toast.success('Descartada');
      else if (mustCite) toast.success('Marcada como imprescindible');
      else if (saved.fulltext === 'full_text') toast.success('Añadida a la biblioteca con el texto completo');
      else if (saved.text_status === 'abstract_only') toast.success('Añadida a la biblioteca: solo resumen. Puedes subir el PDF.');
      else toast.success('Añadida a la biblioteca');
    } catch (err) {
      toast.error(errorDe(err, 'No se pudo actualizar la ficha'));
    } finally {
      setBusyId(null);
    }
  };

  const uploadPdf = async (record, file) => {
    setBusyId(record.id);
    try {
      const res = await agentsApi.uploadLibraryDocument(file, undefined, undefined, undefined, record.id);
      replace(res.library_document);
      toast.success('PDF indexado: la ficha tiene el texto completo');
    } catch (err) {
      toast.error(errorDe(err, 'No se pudo subir el PDF'));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="config-section" style={{ marginBottom: 'var(--space-6)' }} aria-labelledby="library-records-title">
      <div className="config-section-header" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <BookOpen size={15} />
          <h3 id="library-records-title" style={{ margin: 0, fontSize: 'inherit', fontWeight: 600 }}>Referencias bibliográficas</h3>
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => setImporting(true)}>
          <Upload size={14} /> Importar BibTeX / DOI
        </button>
      </div>
      <div className="config-section-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <SearchForm onFound={() => { setTab('candidate'); load(); }} />
        <div role="group" aria-label="Estado de las referencias" style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          {PESTANAS.map((p) => (
            <button key={p.id} type="button" aria-pressed={tab === p.id}
              className={`btn btn-sm ${tab === p.id ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setTab(p.id)}>
              {p.label} ({counts[p.id] || 0})
            </button>
          ))}
        </div>
        <AsyncState
          loading={loading}
          error={error}
          isEmpty={visibles.length === 0}
          onRetry={load}
          loadingLabel="Cargando las referencias…"
          empty={(
            <EmptyState
              icon={<BookOpen size={28} />}
              title={VACIOS[tab].title}
              description={VACIOS[tab].description}
            />
          )}
        >
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {visibles.map((r) => (
              <RecordRow key={r.id} record={r} busy={busyId === r.id} onCurate={curate} onEdit={setEditing} onUploadPdf={uploadPdf} />
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
