import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation, useParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { api } from '../lib/supabase';

const Icon = ({ d, size = 16, color = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);

const ICONS = {
  chat: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
  docs: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M16 13H8 M16 17H8 M10 9H8',
  plus: 'M12 5v14 M5 12h14',
  menu: 'M3 12h18 M3 6h18 M3 18h18',
  logout: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4 M16 17l5-5-5-5 M21 12H9',
  trash: 'M3 6h18 M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2',
  chevron: 'M15 18l-6-6 6-6',
};

export default function Sidebar({ collapsed, onToggle }) {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [sessions, setSessions] = useState([]);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    loadSessions();
  }, []);

  async function loadSessions() {
    try {
      const data = await api.sessions.list();
      setSessions(data || []);
    } catch (e) {
      console.error('Failed to load sessions', e);
    }
  }

  async function newSession() {
    setCreating(true);
    try {
      const s = await api.sessions.create('New briefing');
      setSessions(prev => [s, ...prev]);
      navigate(`/chat/${s.id}`);
    } catch (e) {
      console.error('Failed to create session', e);
    } finally {
      setCreating(false);
    }
  }

  async function deleteSession(e, id) {
    e.stopPropagation();
    try {
      await api.sessions.delete(id);
      setSessions(prev => prev.filter(s => s.id !== id));
      if (location.pathname.includes(id)) navigate('/chat');
    } catch (err) {
      console.error(err);
    }
  }

  const onDocs = location.pathname === '/documents';
  const onChat = location.pathname.startsWith('/chat');
  const activeSession = location.pathname.split('/chat/')[1];

  return (
    <aside style={{
      ...styles.sidebar,
      width: collapsed ? '56px' : '240px',
      transition: 'width 0.2s ease',
    }}>
      {/* Logo row */}
      <div style={styles.logoRow}>
        {!collapsed && (
          <div style={styles.logo}>
            <span style={styles.logoText}>CREWBRIEF</span>
            <span style={styles.logoSub}>RJ FLIGHT OPS</span>
          </div>
        )}
        <button style={styles.iconBtn} onClick={onToggle} title="Toggle sidebar">
          <Icon d={ICONS.menu} size={18} />
        </button>
      </div>

      <div style={styles.divider} />

      {/* Nav */}
      <nav style={styles.nav}>
        <NavItem
          icon={ICONS.chat}
          label="Chat"
          active={onChat}
          collapsed={collapsed}
          onClick={() => navigate('/chat')}
        />
        <NavItem
          icon={ICONS.docs}
          label="Documents"
          active={onDocs}
          collapsed={collapsed}
          onClick={() => navigate('/documents')}
        />
      </nav>

      {/* New session */}
      {onChat && (
        <>
          <div style={styles.divider} />
          <div style={{ padding: collapsed ? '8px 10px' : '8px 12px' }}>
            <button
              style={{
                ...styles.newBtn,
                justifyContent: collapsed ? 'center' : 'flex-start',
                opacity: creating ? 0.6 : 1,
              }}
              onClick={newSession}
              disabled={creating}
            >
              <Icon d={ICONS.plus} size={15} />
              {!collapsed && <span>New briefing</span>}
            </button>
          </div>

          {/* Session list */}
          {!collapsed && (
            <div style={styles.sessions}>
              {sessions.map((s, i) => (
                <div
                  key={s.id}
                  style={{
                    ...styles.sessionItem,
                    background: activeSession === s.id ? 'var(--surface)' : 'transparent',
                    borderColor: activeSession === s.id ? 'var(--border-2)' : 'transparent',
                    animation: `slideIn 0.2s ease ${i * 0.03}s both`,
                  }}
                  onClick={() => navigate(`/chat/${s.id}`)}
                >
                  <span style={styles.sessionTitle}>
                    {s.title || 'Untitled briefing'}
                  </span>
                  <button
                    style={styles.deleteBtn}
                    onClick={(e) => deleteSession(e, s.id)}
                    title="Delete session"
                  >
                    <Icon d={ICONS.trash} size={13} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      <div style={styles.spacer} />

      {/* User / logout */}
      <div style={styles.divider} />
      <div style={{
        ...styles.userRow,
        padding: collapsed ? '12px 10px' : '12px 16px',
        justifyContent: collapsed ? 'center' : 'space-between',
      }}>
        {!collapsed && (
          <div style={styles.userInfo}>
            <div style={styles.userEmail}>{user?.email?.split('@')[0]}</div>
            <div style={styles.userRole}>Pilot</div>
          </div>
        )}
        <button
          style={styles.iconBtn}
          onClick={signOut}
          title="Sign out"
        >
          <Icon d={ICONS.logout} size={16} />
        </button>
      </div>
    </aside>
  );
}

function NavItem({ icon, label, active, collapsed, onClick }) {
  return (
    <button
      style={{
        ...styles.navItem,
        background: active ? 'var(--surface)' : 'transparent',
        color: active ? 'var(--amber)' : 'var(--text-2)',
        borderColor: active ? 'var(--amber-dim)' : 'transparent',
        justifyContent: collapsed ? 'center' : 'flex-start',
        padding: collapsed ? '10px' : '9px 12px',
      }}
      onClick={onClick}
    >
      <Icon d={icon} size={16} color={active ? 'var(--amber)' : 'currentColor'} />
      {!collapsed && <span style={{ marginLeft: '10px', fontSize: '13px' }}>{label}</span>}
    </button>
  );
}

const styles = {
  sidebar: {
    position: 'fixed',
    top: 0, left: 0, bottom: 0,
    background: 'var(--bg-2)',
    borderRight: '1px solid var(--border)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    zIndex: 100,
  },
  logoRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '16px 12px',
    minHeight: '56px',
  },
  logo: {
    display: 'flex',
    flexDirection: 'column',
  },
  logoText: {
    fontFamily: 'var(--font-display)',
    fontSize: '20px',
    letterSpacing: '4px',
    color: 'var(--amber)',
    lineHeight: 1,
  },
  logoSub: {
    fontFamily: 'var(--font-mono)',
    fontSize: '9px',
    letterSpacing: '1.5px',
    color: 'var(--text-dim)',
    marginTop: '2px',
  },
  divider: {
    height: '1px',
    background: 'var(--border)',
    flexShrink: 0,
  },
  nav: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    padding: '8px',
  },
  navItem: {
    display: 'flex',
    alignItems: 'center',
    width: '100%',
    border: '1px solid',
    borderRadius: 'var(--radius)',
    cursor: 'pointer',
    fontFamily: 'var(--font-sans)',
    transition: 'all 0.15s',
  },
  newBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    width: '100%',
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius)',
    color: 'var(--text-2)',
    padding: '7px 10px',
    cursor: 'pointer',
    fontFamily: 'var(--font-mono)',
    fontSize: '11px',
    letterSpacing: '1px',
    transition: 'all 0.15s',
  },
  sessions: {
    flex: 1,
    overflowY: 'auto',
    padding: '4px 8px',
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  sessionItem: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '7px 10px',
    borderRadius: 'var(--radius)',
    border: '1px solid',
    cursor: 'pointer',
    transition: 'all 0.15s',
  },
  sessionTitle: {
    fontSize: '12px',
    color: 'var(--text-2)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    flex: 1,
  },
  deleteBtn: {
    background: 'none',
    border: 'none',
    color: 'var(--text-dim)',
    cursor: 'pointer',
    padding: '2px',
    opacity: 0,
    transition: 'opacity 0.15s',
    flexShrink: 0,
    display: 'flex',
    alignItems: 'center',
  },
  spacer: { flex: 1 },
  userRow: {
    display: 'flex',
    alignItems: 'center',
  },
  userInfo: {
    overflow: 'hidden',
  },
  userEmail: {
    fontSize: '13px',
    fontWeight: 500,
    color: 'var(--text)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  userRole: {
    fontFamily: 'var(--font-mono)',
    fontSize: '10px',
    color: 'var(--text-dim)',
    letterSpacing: '1px',
  },
  iconBtn: {
    background: 'none',
    border: 'none',
    color: 'var(--text-dim)',
    cursor: 'pointer',
    padding: '6px',
    borderRadius: 'var(--radius)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'color 0.15s',
    flexShrink: 0,
  },
};
