import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import toast from 'react-hot-toast';
import { useTranslation } from '../i18n';

export default function AuthPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState('login');
  const [form, setForm] = useState({ email: '', password: '', fullName: '' });
  const navigate = useNavigate();
  const location = useLocation();
  const { login, register, isLoading, error, clearError } = useAuthStore();

  // Project context injected via navigate('/auth', { state: { projectName } })
  const projectName = location.state?.projectName || null;

  const handleChange = (e) => {
    clearError();
    setForm(f => ({ ...f, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    let result;
    if (tab === 'login') {
      result = await login(form.email, form.password);
    } else {
      if (!form.fullName.trim()) { toast.error(t('auth.nameRequired')); return; }
      result = await register(form.email, form.password, form.fullName);
    }
    if (result.ok) {
      toast.success(tab === 'login' ? t('auth.welcomeBack') : t('auth.accountCreated'));
      const role = useAuthStore.getState().user?.role;
      navigate((role === 'lector' || role === 'publico') ? '/reader' : '/projects');
    } else {
      toast.error(result.error);
    }
  };

  return (
    <div className="auth-page">
      {/* Left branding panel */}
      <div className="auth-left">
        <div style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <div className="auth-brand-icon">
            <img src="/ds/assets/logomark.svg" alt="Alexandria" />
          </div>
          <h1 style={{ fontSize: 'var(--font-size-2xl)', textAlign: 'center', letterSpacing: '-0.03em' }}>
            {projectName ? (
              <>
                {projectName.split(' ').slice(0, -1).join(' ')}<br />
                <span style={{ color: 'var(--brand-primary)' }}>
                  {projectName.split(' ').slice(-1)[0]}
                </span>
              </>
            ) : (
              <>
                {t('auth.brandLine1')}<br />
                <span style={{ color: 'var(--brand-primary)' }}>{t('auth.brandLine2')}</span>
              </>
            )}
          </h1>
          <p className="auth-tagline">
            {projectName
              ? t('auth.taglineProject', { project: projectName })
              : t('auth.taglineDefault')}
          </p>
          <div className="auth-features">
            {[
              { text: t('auth.features.designer') },
              { text: t('auth.features.agents') },
              { text: t('auth.features.realtime') },
              { text: t('auth.features.rag') },
            ].map((f, i) => (
              <div className="auth-feature" key={i}>
                <div className="auth-feature-dot" />
                <span style={{ color: 'var(--text-muted)', fontSize: 'var(--font-size-xs)' }}>
                  {f.text}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right form panel */}
      <div className="auth-right">
        <div className="auth-form-box animate-fade-in">
          <div>
            <h2 style={{ fontSize: 'var(--font-size-xl)', marginBottom: 4 }}>
              {tab === 'login' ? t('auth.login') : t('auth.createAccount')}
            </h2>
            <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-muted)' }}>
              {tab === 'login'
                ? (projectName ? t('auth.subtitleProject', { project: projectName }) : t('auth.subtitleLogin'))
                : t('auth.subtitleRegister')}
            </p>
          </div>

          {/* Tabs */}
          <div className="tabs">
            <button className={`tab ${tab === 'login' ? 'active' : ''}`} onClick={() => { setTab('login'); clearError(); }}>
              {t('auth.login')}
            </button>
            <button className={`tab ${tab === 'register' ? 'active' : ''}`} onClick={() => { setTab('register'); clearError(); }}>
              {t('auth.register')}
            </button>
          </div>

          <form className="auth-form" onSubmit={handleSubmit}>
            {tab === 'register' && (
              <div className="input-group">
                <label className="input-label">{t('auth.fullName')}</label>
                <input
                  className="input"
                  type="text"
                  name="fullName"
                  placeholder={t('auth.fullNamePlaceholder')}
                  value={form.fullName}
                  onChange={handleChange}
                  required
                />
              </div>
            )}
            <div className="input-group">
              <label className="input-label">{t('auth.email')}</label>
              <input
                className="input"
                type="email"
                name="email"
                placeholder={t('auth.emailPlaceholder')}
                value={form.email}
                onChange={handleChange}
                required
              />
            </div>
            <div className="input-group">
              <label className="input-label">{t('auth.password')}</label>
              <input
                className="input"
                type="password"
                name="password"
                placeholder={tab === 'register' ? t('auth.passwordHint') : '••••••••'}
                value={form.password}
                onChange={handleChange}
                required
                minLength={6}
              />
            </div>

            {error && (
              <div style={{
                background: 'var(--status-error-bg)',
                border: '1px solid rgba(239,68,68,0.25)',
                borderRadius: 'var(--radius-md)',
                padding: '10px 14px',
                fontSize: 'var(--font-size-sm)',
                color: 'var(--status-error)',
              }}>
                {error}
              </div>
            )}

            <button className="btn btn-primary btn-lg w-full" type="submit" disabled={isLoading}>
              {isLoading ? (
                <><div className="spinner" style={{ borderTopColor: 'white' }} /> {t('auth.loading')}</>
              ) : (
                tab === 'login' ? t('auth.enter') : t('auth.createAccount')
              )}
            </button>
          </form>

          <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)', textAlign: 'center' }}>
            {tab === 'login' ? t('auth.noAccount') : t('auth.haveAccount')}
            <button
              onClick={() => { setTab(tab === 'login' ? 'register' : 'login'); clearError(); }}
              style={{ background: 'none', border: 'none', color: 'var(--brand-primary)', cursor: 'pointer', fontSize: 'inherit', fontWeight: 600 }}
            >
              {tab === 'login' ? t('auth.signUpLink') : t('auth.signInLink')}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
