import React, { useEffect, useState } from 'react';
import { AsyncState, EmptyState } from '../../../platform/components/ui/states';
import { useNavigate } from 'react-router-dom';
import { FileText, Clock, CheckCircle, AlertCircle, Search, Pencil, Trash2, User } from 'lucide-react';
import { useArticleStore } from '../store/articleStore';
import { useAuthStore } from '../../../platform/store/authStore';
import toast from 'react-hot-toast';
import { useT } from '../i18n/useT';

const TABS = ['all', 'draft', 'pending', 'human_review', 'approved', 'published'];

const STATUS_MAP = {
  draft: { label: 'articles.status.draft', cls: 'badge-draft', icon: <Clock size={10} /> },
  in_review: { label: 'articles.status.in_review', cls: 'badge-pending', icon: <AlertCircle size={10} /> },
  approved: { label: 'articles.status.approved', cls: 'badge-approved', icon: <CheckCircle size={10} /> },
  published: { label: 'articles.status.published', cls: 'badge-published', icon: <CheckCircle size={10} /> },
  rejected: { label: 'articles.status.rejected', cls: 'badge-error', icon: <AlertCircle size={10} /> },
  requires_human_review: { label: 'articles.status.requires_human_review', cls: 'badge-pending', icon: <AlertCircle size={10} /> },
};

const TAB_FILTER = {
  all: null,
  draft: 'draft',
  pending: 'in_review',
  human_review: 'requires_human_review',
  approved: 'approved',
  published: 'published',
};

export default function ArticlesPage() {
  const { t } = useT();
  const navigate = useNavigate();
  const { articles, fetchArticles, updateArticle, deleteArticle, isLoading, error } = useArticleStore();
  const { user } = useAuthStore();
  const [tab, setTab] = useState('all');
  const [search, setSearch] = useState('');
  const [editingId, setEditingId] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [deletingId, setDeletingId] = useState(null);

  useEffect(() => { fetchArticles(); }, []);

  const filtered = articles.filter(a => {
    const statusMatch = !TAB_FILTER[tab] || a.status === TAB_FILTER[tab];
    const searchMatch = !search || a.title.toLowerCase().includes(search.toLowerCase());
    return statusMatch && searchMatch;
  });

  const startEdit = (e, article) => {
    e.stopPropagation();
    setEditingId(article.id);
    setEditTitle(article.title);
  };

  const confirmEdit = async (e, id) => {
    e.stopPropagation();
    if (!editTitle.trim()) return;
    try {
      await updateArticle(id, { title: editTitle.trim() });
      toast.success(t('articles.titleUpdated'));
    } catch { toast.error(t('articles.updateError')); }
    setEditingId(null);
  };

  const handleDelete = async (e, id, title) => {
    e.stopPropagation();
    if (!globalThis.confirm(t('articles.deleteConfirm', { title }))) return;
    setDeletingId(id);
    try {
      await deleteArticle(id);
      toast.success(t('articles.deleted'));
    } catch { toast.error(t('articles.deleteError')); }
    finally { setDeletingId(null); }
  };

  return (
    <div className="page-body">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-6)' }}>
        <div>
          <h2 style={{ marginBottom: 4 }}>{t('articles.title')}</h2>
          <p style={{ fontSize: 'var(--font-size-sm)' }}>{t('articles.total', { count: articles.length })}</p>
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)', marginBottom: 'var(--space-5)', flexWrap: 'wrap' }}>
        <div className="tabs">
          {TABS.map(id => (
            <button key={id} className={`tab ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>{t(`articles.tabs.${id}`)}</button>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, maxWidth: 300 }}>
          <Search size={15} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
          <input className="input" style={{ padding: '6px 10px' }}
            placeholder={t('articles.search')}
            value={search} onChange={e => setSearch(e.target.value)} />
        </div>
      </div>

      <AsyncState
        loading={isLoading}
        error={error}
        isEmpty={filtered.length === 0}
        onRetry={() => fetchArticles()}
        loadingLabel={t('articles.loading')}
        empty={(
          <EmptyState
            icon={<FileText size={28} />}
            title={articles.length === 0 ? t('articles.emptyTitle') : t('articles.noMatchTitle')}
            description={articles.length === 0
              ? t('articles.emptyDescription')
              : t('articles.noMatchDescription')}
          />
        )}
      >
        {(
        <div className="article-grid">
          {filtered.map(article => {
            const st = STATUS_MAP[article.status] || STATUS_MAP.draft;
            const isEditing = editingId === article.id;
            const isDeleting = deletingId === article.id;
            return (
              <div key={article.id} className="article-card"
                onClick={() => !isEditing && navigate(`/dashboard/articles/${article.id}`)}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
                  {isEditing ? (
                    <input
                      className="input"
                      style={{ flex: 1, padding: '4px 8px', fontSize: 'var(--font-size-sm)' }}
                      value={editTitle}
                      autoFocus
                      onClick={e => e.stopPropagation()}
                      onChange={e => setEditTitle(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') confirmEdit(e, article.id);
                        if (e.key === 'Escape') { e.stopPropagation(); setEditingId(null); }
                      }}
                    />
                  ) : (
                    <div className="article-card-title">{article.title}</div>
                  )}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
                    {isEditing ? (
                      <button
                        className="btn btn-primary btn-sm"
                        style={{ padding: '3px 10px', fontSize: 'var(--font-size-xs)' }}
                        onClick={e => confirmEdit(e, article.id)}
                        aria-label={t('articles.confirmEdit')}
                      >
                        {t('articles.save')}
                      </button>
                    ) : (
                      <button
                        className="btn btn-ghost btn-sm btn-icon"
                        onClick={e => startEdit(e, article)}
                        aria-label={t('articles.editTitle')}
                        title={t('articles.editTitle')}
                      >
                        <Pencil size={13} style={{ color: 'var(--text-muted)' }} />
                      </button>
                    )}
                    <button
                      className="btn btn-ghost btn-sm btn-icon"
                      onClick={e => handleDelete(e, article.id, article.title)}
                      disabled={isDeleting}
                      aria-label={t('articles.delete')}
                      title={t('articles.delete')}
                    >
                      <Trash2 size={13} style={{ color: 'var(--error)' }} />
                    </button>
                    <span className={`badge ${st.cls}`}>
                      {st.icon} {t(st.label)}
                    </span>
                  </div>
                </div>
                <div className="article-card-meta">
                  <Clock size={11} />
                  {new Date(article.created_at).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' })}
                  {article.author_name && (
                    <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                      <User size={10} />
                      {article.author_name}
                    </span>
                  )}
                  {article.scientific_format && article.scientific_format !== 'none' && (
                    <span style={{ background: 'var(--bg-elevated)', padding: '1px 6px', borderRadius: 'var(--radius-full)', fontSize: 10 }}>
                      {article.scientific_format.toUpperCase()}
                    </span>
                  )}
                </div>
                {article.body && !isEditing && (
                  <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {article.body.replace(/[#*`]/g, '').trim()}
                  </p>
                )}
              </div>
            );
          })}
        </div>
        )}
      </AsyncState>
    </div>
  );
}
