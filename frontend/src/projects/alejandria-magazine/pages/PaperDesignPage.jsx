import React, { useCallback, useEffect, useRef, useState } from 'react';
import { LoadingState, ErrorState } from '../../../platform/components/ui/states';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Save, Loader, Columns2, Columns3, ImagePlus } from 'lucide-react';
import { articlesApi } from '../api/articles';
import toast from 'react-hot-toast';
import { PAPER_ACCENTS } from '../paperTheme';
import { tr, useT } from '../i18n/useT';

/**
 * Paper design studio: edit the text of the article and presentation with a live
 * preview of the final layout (SPEC-022 / T11.4).
 *
 * The preview is rendered **server-side** by the same function that produces the
 * published paper, so what you see here is what the PDF will be. The user never
 * writes CSS — every control picks from a closed allowlist that the backend
 * validates again on save.
 */

// Mirrors the allowlists in backend/app/modules/agents/adapters/paper_layout.py.
// The backend is the source of truth: anything it does not recognise falls back
// to the format preset, so a drift here degrades gracefully instead of breaking.
const FONTS = [
  { value: 'times', label: 'Times New Roman', preview: "'Times New Roman', serif" },
  { value: 'georgia', label: 'Georgia', preview: 'Georgia, serif' },
  { value: 'palatino', label: 'Palatino', preview: "'Palatino Linotype', serif" },
  { value: 'helvetica', label: 'Helvetica', preview: 'Helvetica, Arial, sans-serif' },
  { value: 'arial', label: 'Arial', preview: 'Arial, sans-serif' },
  { value: 'verdana', label: 'Verdana', preview: 'Verdana, sans-serif' },
];

// Espejo de «_THEME_ACCENTS» del backend: son los colores del **paper**, no de la
// interfaz. Ver el porqué en src/paperTheme.js.
const ACCENTS = PAPER_ACCENTS;

const FORMATS = [
  { value: 'apa', label: 'paperDesign.format.apa' },
  { value: 'ieee', label: 'paperDesign.format.ieee' },
  { value: 'acl', label: 'paperDesign.format.acl' },
  { value: 'vancouver', label: 'paperDesign.format.vancouver' },
  { value: 'chicago', label: 'paperDesign.format.chicago' },
  { value: 'nature', label: 'paperDesign.format.nature' },
];

const PREVIEW_DEBOUNCE_MS = 400;   // AC3 requires the repaint within 1 s of the last change

export default function PaperDesignPage() {
  const { t } = useT();
  const { id } = useParams();
  const navigate = useNavigate();

  const [draft, setDraft] = useState(null);      // {title, abstract, body, scientific_format, theme}
  const [html, setHtml] = useState('');
  const [loading, setLoading] = useState(true);
  const [rendering, setRendering] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [previewKey, setPreviewKey] = useState(0);

  // Guards against an out-of-order response overwriting a newer preview.
  const requestSeq = useRef(0);

  useEffect(() => {
    articlesApi.get(id)
      .then(a => {
        setDraft({
          title: a.title || '',
          abstract: a.abstract || '',
          body: a.body || '',
          scientific_format: (a.scientific_format && a.scientific_format !== 'none')
            ? a.scientific_format : 'apa',
          theme: a.theme || {},
        });
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [id]);

  const renderPreview = useCallback(async (current) => {
    const seq = ++requestSeq.current;
    setRendering(true);
    try {
      const out = await articlesApi.previewPaper(id, current);
      if (seq === requestSeq.current) {   // ignore stale responses
        setHtml(out);
        setPreviewKey(k => k + 1);
      }
    } catch {
      if (seq === requestSeq.current) toast.error(tr('paperDesign.previewError'));
    } finally {
      if (seq === requestSeq.current) setRendering(false);
    }
  }, [id]);

  // Debounced repaint: one request after the user stops typing / clicking.
  useEffect(() => {
    if (!draft) return undefined;
    const timer = setTimeout(() => renderPreview(draft), PREVIEW_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [draft, renderPreview]);

  const update = (patch) => {
    setDraft(d => ({ ...d, ...patch }));
    setDirty(true);
  };
  const updateTheme = (patch) => {
    setDraft(d => ({ ...d, theme: { ...d.theme, ...patch } }));
    setDirty(true);
  };

  const handleInsertImage = async (file) => {
    if (!file) return;
    try {
      const asset = await articlesApi.uploadAsset(id, file);
      // Append the reference at the end of the body; the preview picks it up on
      // the next debounce tick, so the figure shows up without a manual step.
      update({ body: `${draft.body}\n\n${asset.markdown}\n` });
      toast.success(tr('paperDesign.figureInserted'));
    } catch (e) {
      const detail = e?.response?.data?.detail;
      toast.error(detail || tr('paperDesign.figureError'));
    }
  };

  // «Volver» va a un destino explícito y no a «navigate(-1)» (BUG-005): la vista
  // previa es un iframe que se repinta con cada edición, y cada repintado puede
  // dejar una entrada en el historial de sesión. «-1» se comía esa entrada en el
  // primer clic y solo el segundo salía de la página.
  const handleBack = () => {
    if (dirty && !globalThis.confirm(t('paperDesign.unsavedConfirm'))) return;
    navigate(`/dashboard/articles/${id}`);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await articlesApi.update(id, {
        title: draft.title,
        abstract: draft.abstract,
        body: draft.body,
        scientific_format: draft.scientific_format,
        theme: draft.theme,
      });
      setDirty(false);
      toast.success(tr('paperDesign.saved'));
    } catch {
      toast.error(tr('paperDesign.saveError'));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="page-body"><LoadingState label={t('paperDesign.loading')} /></div>;
  }

  if (error || !draft) {
    return (
      <div className="page-body">
        <ErrorState
          title={t('paperDesign.loadErrorTitle')}
          description={t('paperDesign.loadErrorDescription')}
          onRetry={() => globalThis.location.reload()}
          retryLabel={t('paperDesign.retry')}
        />
      </div>
    );
  }

  const columns = draft.theme.columns;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 'var(--space-4)',
        padding: 'var(--space-3) var(--space-5)', borderBottom: '1px solid var(--border-default)',
        background: 'var(--bg-surface)', flex: 'none',
      }}>
        <button className="btn btn-ghost btn-sm" onClick={handleBack} aria-label={t('common.back')}>
          <ArrowLeft size={15} /> {t('common.back')}
        </button>
        <strong style={{ flex: 1 }}>{t('paperDesign.title')}</strong>
        {rendering && (
          <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
            <Loader size={12} style={{ animation: 'spin 1s linear infinite', verticalAlign: 'middle' }} />
            {' '}{t('paperDesign.updatingPreview')}
          </span>
        )}
        <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving || !dirty}>
          <Save size={15} /> {saving ? t('paperDesign.saving') : dirty ? t('paperDesign.save') : t('paperDesign.savedState')}
        </button>
      </div>

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        {/* ── Controls + text ─────────────────────────────────────────── */}
        <div style={{
          width: 380, flex: 'none', overflowY: 'auto', padding: 'var(--space-5)',
          borderRight: '1px solid var(--border-default)', background: 'var(--bg-surface)',
          display: 'flex', flexDirection: 'column', gap: 'var(--space-5)',
        }}>
          <section>
            <h4 style={{ margin: '0 0 var(--space-3)' }}>{t('paperDesign.citationFormat')}</h4>
            <select
              className="input" style={{ width: '100%' }}
              value={draft.scientific_format}
              onChange={e => update({ scientific_format: e.target.value })}
              aria-label={t('paperDesign.citationFormat')}
            >
              {FORMATS.map(f => <option key={f.value} value={f.value}>{t(f.label)}</option>)}
            </select>
          </section>

          <section>
            <h4 style={{ margin: '0 0 var(--space-3)' }}>{t('paperDesign.typography')}</h4>
            <select
              className="input" style={{ width: '100%' }}
              value={draft.theme.font || ''}
              onChange={e => updateTheme({ font: e.target.value || undefined })}
              aria-label={t('paperDesign.typography')}
            >
              <option value="">{t('paperDesign.formatDefault')}</option>
              {FONTS.map(f => (
                <option key={f.value} value={f.value} style={{ fontFamily: f.preview }}>{f.label}</option>
              ))}
            </select>
          </section>

          <section>
            <h4 style={{ margin: '0 0 var(--space-3)' }}>{t('paperDesign.accentColor')}</h4>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {ACCENTS.map(a => {
                const active = (draft.theme.accent_color || 'ink') === a.value;
                return (
                  <button
                    key={a.value}
                    onClick={() => updateTheme({ accent_color: a.value })}
                    title={t(`paperDesign.accent.${a.value}`)}
                    aria-label={t('paperDesign.accentAria', { name: t(`paperDesign.accent.${a.value}`) })}
                    aria-pressed={active}
                    style={{
                      width: 30, height: 30, borderRadius: '50%', background: a.hex,
                      border: active ? '3px solid var(--brand-primary)' : '1px solid var(--border-default)',
                      cursor: 'pointer', padding: 0,
                    }}
                  />
                );
              })}
            </div>
          </section>

          <section>
            <h4 style={{ margin: '0 0 var(--space-3)' }}>{t('paperDesign.columns')}</h4>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                className={`btn btn-sm ${columns === 1 ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => updateTheme({ columns: 1 })} aria-pressed={columns === 1}
              >
                <Columns2 size={14} /> {t('paperDesign.columnsOne')}
              </button>
              <button
                className={`btn btn-sm ${columns === 2 ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => updateTheme({ columns: 2 })} aria-pressed={columns === 2}
              >
                <Columns3 size={14} /> {t('paperDesign.columnsTwo')}
              </button>
              <button
                className={`btn btn-sm ${!columns ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => updateTheme({ columns: undefined })} aria-pressed={!columns}
              >
                {t('paperDesign.columnsAuto')}
              </button>
            </div>
            <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', marginTop: 6 }}>
              {t('paperDesign.columnsAutoHint')}
            </p>
          </section>

          <section>
            <h4 style={{ margin: '0 0 var(--space-3)' }}>{t('paperDesign.figures')}</h4>
            <label className="btn btn-ghost btn-sm" style={{ cursor: 'pointer' }}>
              <ImagePlus size={14} /> {t('paperDesign.insertImage')}
              <input
                type="file"
                accept=".png,.jpg,.jpeg,.gif,.webp"
                style={{ display: 'none' }}
                onChange={e => { handleInsertImage(e.target.files?.[0]); e.target.value = ''; }}
                aria-label={t('paperDesign.insertImageAria')}
              />
            </label>
            <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', marginTop: 6 }}>
              {t('paperDesign.figuresHintBefore')}
              {' '}<code>![pie](asset:…)</code>{t('paperDesign.figuresHintAfter')}
            </p>
          </section>

          <section>
            <h4 style={{ margin: '0 0 var(--space-3)' }}>{t('paperDesign.content')}</h4>
            <label style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>{t('paperDesign.fieldTitle')}</label>
            <input
              className="input" style={{ width: '100%', marginBottom: 'var(--space-3)' }}
              value={draft.title} onChange={e => update({ title: e.target.value })}
              aria-label={t('paperDesign.titleAria')}
            />
            <label style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>{t('paperDesign.abstract')}</label>
            <textarea
              className="input" rows={4} style={{ width: '100%', marginBottom: 'var(--space-3)' }}
              value={draft.abstract} onChange={e => update({ abstract: e.target.value })}
              aria-label={t('paperDesign.abstract')}
            />
            <label style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>{t('paperDesign.body')}</label>
            <textarea
              className="input" rows={14}
              style={{ width: '100%', fontFamily: 'var(--font-mono)', fontSize: 'var(--font-size-xs)' }}
              value={draft.body} onChange={e => update({ body: e.target.value })}
              aria-label={t('paperDesign.bodyAria')}
            />
          </section>
        </div>

        {/* ── Live preview ────────────────────────────────────────────── */}
        <div style={{ flex: 1, minWidth: 0, background: 'var(--bg-canvas)' }}>
          <iframe
            // Cada previa es un iframe nuevo: la primera navegación de un iframe
            // recién creado sustituye a about:blank y no añade entrada al historial,
            // mientras que cambiar «srcdoc» de uno ya cargado sí la añade (BUG-005).
            key={previewKey}
            title={t('paperDesign.previewTitle')}
            srcDoc={html}
            // Static HTML+CSS only: no scripts, no same-origin (T2.2).
            sandbox=""
            style={{ width: '100%', height: '100%', border: 'none', background: 'var(--paper-surface)' }}
          />
        </div>
      </div>
    </div>
  );
}
