import React, { useEffect, useRef, useState } from 'react';
import { notificationRoute, projectNavItems } from '../navigation';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  GitBranch, Bot, Zap, FileText, Settings, Database,
  BookOpen, LogOut, Bell, ChevronDown,
  Newspaper, Code2, Megaphone, Ticket, Palette, Wand2,
  Shield, Users,
} from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { useProjectStore } from '../store/projectStore';
import api from '../api/client';
import RunningBar from '../components/RunningBar';
import toast from 'react-hot-toast';

const USE_CASE_ICON = {
  alejandria_magazine: <Newspaper size={16} />,
  desarrollo:          <Code2 size={16} />,
  marketing:           <Megaphone size={16} />,
  tiqueting:           <Ticket size={16} />,
  diseno:              <Palette size={16} />,
  custom:              <Wand2 size={16} />,
};

const USE_CASE_LABEL = {
  alejandria_magazine: 'Revista científica',
  desarrollo:          'Desarrollo de software',
  marketing:           'Marketing',
  tiqueting:           'Tiqueting',
  diseno:              'Diseño',
  custom:              'Proyecto custom',
};

const USE_CASE_COLOR = {
  alejandria_magazine: 'var(--brand)',
  desarrollo:          'var(--agent-format)',
  marketing:           'var(--agent-review)',
  tiqueting:           'var(--agent-research)',
  diseno:              'var(--agent-write)',
  custom:              'var(--neutral-60)',
};

//: Entradas del **builder**. «Artículos» ya no está aquí: la aporta el proyecto
//: (ver `platform/navigation.js`), porque el objeto que produce el pipeline se
//: llama artículo en AlejandrIA y otra cosa en cualquier otro proyecto.
const PLATFORM_NAV_ITEMS = [
  { to: '/dashboard/flow-designer', icon: <GitBranch size={17} />, label: 'Flow Designer', roles: ['admin', 'redactor'] },
  { to: '/dashboard/agents',        icon: <Bot size={17} />,        label: 'Agentes',       roles: ['admin', 'redactor'] },
  { to: '/dashboard/flows',         icon: <Zap size={17} />,        label: 'Flujos',        roles: ['admin', 'redactor'] },
  { to: '/dashboard/documents',     icon: <Database size={17} />,   label: 'Documentos',    roles: ['admin', 'redactor'] },
  { to: '/dashboard/users',         icon: <Users size={17} />,      label: 'Usuarios',      roles: ['admin'] },
];

//: Builder + proyecto, en el orden en que se leen: las vistas de consumo van
//: entre las de construcción y las de administración.
const navItems = () => {
  const items = [...PLATFORM_NAV_ITEMS];
  items.splice(3, 0, ...projectNavItems());
  return items;
};

export default function DashboardPage() {
  const { user, logout } = useAuthStore();
  const { activeProject } = useProjectStore();
  const navigate = useNavigate();
  const role = user?.role || 'lector';

  const [notifications, setNotifications] = useState([]);
  const [showNotifs, setShowNotifs] = useState(false);
  const notifRef = useRef(null);

  const fetchNotifications = async () => {
    try {
      const { data } = await api.get('/api/v1/notifications');
      setNotifications(data);
    // mejor-esfuerzo: el sondeo de notificaciones se repite solo; avisar en
    // cada vuelta sería más molesto que el propio fallo.
    } catch { /* silently ignore */ }
  };

  useEffect(() => {
    fetchNotifications();
    const id = setInterval(fetchNotifications, 30000);
    return () => clearInterval(id);
  }, []);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handler = (e) => { if (notifRef.current && !notifRef.current.contains(e.target)) setShowNotifs(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const unread = notifications.filter(n => !n.read).length;

  const handleNotifClick = async (n) => {
    if (!n.read) {
      try {
        await api.post(`/api/v1/notifications/${n.id}/read`);
        setNotifications(prev => prev.map(x => x.id === n.id ? { ...x, read: true } : x));
      // mejor-esfuerzo: marcar como leída es cosmético; si falla, la
      // navegación al artículo sigue siendo lo que la persona ha pedido.
      } catch { /* ignore */ }
    }
    const destino = n.article_id && notificationRoute(n.article_id);
    if (destino) {
      setShowNotifs(false);
      navigate(destino);
    }
  };

  const handleMarkAllRead = async () => {
    const unreadList = notifications.filter(n => !n.read);
    await Promise.allSettled(unreadList.map(n => api.post(`/api/v1/notifications/${n.id}/read`)));
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
  };

  const handleLogout = () => {
    const projectName = activeProject?.name;
    logout();
    toast.success('Sesión cerrada');
    navigate('/auth', projectName ? { state: { projectName } } : undefined);
  };

  const initials = user?.full_name
    ?.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase() || 'U';

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar">

        {/* Project header — top of sidebar */}
        {activeProject ? (() => {
          const color = USE_CASE_COLOR[activeProject.use_case_type] ?? 'var(--brand-primary)';
          const icon  = USE_CASE_ICON[activeProject.use_case_type]  ?? <BookOpen size={16} />;
          return (
            <button
              onClick={() => navigate('/projects')}
              title="Cambiar proyecto"
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                background: 'none', border: 'none', cursor: 'pointer',
                padding: '16px 16px 12px', width: '100%', textAlign: 'left',
                borderBottom: '1px solid var(--border-subtle)',
                marginBottom: 4,
              }}
            >
              {/* Icon badge */}
              <div style={{
                width: 34, height: 34, borderRadius: 10, flexShrink: 0,
                background: `color-mix(in srgb, ${color} 18%, transparent)`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color,
              }}>
                {icon}
              </div>
              {/* Name + app label */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  color: 'var(--text-primary)', fontWeight: 700, fontSize: '0.88rem',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {activeProject.name}
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem', marginTop: 1 }}>
                  {USE_CASE_LABEL[activeProject.use_case_type] ?? activeProject.use_case_type}
                </div>
              </div>
              <ChevronDown size={13} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
            </button>
          );
        })() : (
          <div className="sidebar-logo">
            <div className="sidebar-logo-icon">
              <img src="/ds/assets/logomark.svg" alt="Alexandria" />
            </div>
            <span className="sidebar-logo-text">
              Alej<span>andrIA</span>
            </span>
          </div>
        )}

        <nav className="sidebar-nav">
          <div className="nav-section-title">Workspace</div>
          {navItems().filter(item => item.roles.includes(role)).map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
            >
              {item.icon}
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <NavLink
            to="/dashboard/config"
            className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
          >
            <Settings size={17} />
            Configuración
          </NavLink>
          <button className="nav-item btn-ghost w-full" onClick={handleLogout}
            style={{ border: 'none', cursor: 'pointer', textAlign: 'left' }}>
            <LogOut size={17} />
            Cerrar sesión
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="main-content">
        {/* Topbar */}
        <header className="topbar">
          <span className="topbar-title" />
          <div className="flex items-center gap-3">
            <div className="relative" ref={notifRef}>
              <button className="btn btn-ghost btn-icon" style={{ position: 'relative' }}
                onClick={() => setShowNotifs(v => !v)}
                aria-label={`Notificaciones${unread ? ` (${unread} sin leer)` : ''}`}>
                <Bell size={18} />
                {unread > 0 && (
                  <span style={{
                    position: 'absolute', top: 3, right: 3,
                    background: 'var(--error)', color: 'var(--neutral-00)',
                    borderRadius: '50%', width: 16, height: 16,
                    fontSize: 10, fontWeight: 700,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    lineHeight: 1,
                  }}>{unread > 9 ? '9+' : unread}</span>
                )}
              </button>
              {showNotifs && (
                <div style={{
                  position: 'absolute', right: 0, top: 'calc(100% + 8px)',
                  width: 320, background: 'var(--bg-elevated)',
                  border: '1px solid var(--border-default)', borderRadius: 'var(--radius-lg)',
                  boxShadow: '0 8px 24px rgba(0,0,0,0.4)', zIndex: 200,
                  overflow: 'hidden',
                }}>
                  <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-default)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontWeight: 600, fontSize: 'var(--font-size-sm)' }}>Notificaciones {unread > 0 && <span style={{ color: 'var(--error)' }}>({unread} nuevas)</span>}</span>
                    {unread > 0 && (
                      <button onClick={handleMarkAllRead} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 11, color: 'var(--text-muted)', padding: 0 }} aria-label="Marcar todas como leídas">
                        Marcar todas
                      </button>
                    )}
                  </div>
                  <div style={{ maxHeight: 360, overflowY: 'auto' }}>
                    {notifications.length === 0 ? (
                      <div style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 'var(--font-size-sm)' }}>
                        Sin notificaciones
                      </div>
                    ) : notifications.map(n => (
                      <div key={n.id}
                        onClick={() => handleNotifClick(n)}
                        style={{
                          padding: '12px 16px',
                          cursor: n.article_id ? 'pointer' : 'default',
                          background: n.read ? 'transparent' : 'rgba(99,102,241,0.08)',
                          borderBottom: '1px solid var(--border-default)',
                          transition: 'background 0.15s',
                        }}>
                        <div style={{ fontWeight: n.read ? 400 : 600, fontSize: 'var(--font-size-sm)', marginBottom: 2 }}>
                          {!n.read && <span style={{ display: 'inline-block', width: 7, height: 7, borderRadius: '50%', background: 'var(--brand)', marginRight: 6, verticalAlign: 'middle' }} />}
                          {n.title}
                        </div>
                        <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>{n.message}</div>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
                          {new Date(n.created_at).toLocaleString('es-ES', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              <div className="avatar">{initials}</div>
              <div style={{ lineHeight: 1.3 }}>
                <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {user?.full_name}
                </div>
                <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-muted)' }}>
                  {user?.role === 'admin' && <Shield size={10} style={{ marginRight: 3 }} />}{user?.role}
                </div>
              </div>
            </div>
          </div>
        </header>

        {/* Page content */}
        <Outlet />
        {/* Vive aquí, por encima del Outlet, para que cambiar de pestaña no lo
            desmonte: ese es el punto de que sea persistente (T18.7). */}
        <RunningBar />
      </div>
    </div>
  );
}
