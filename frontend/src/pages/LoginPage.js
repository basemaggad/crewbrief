import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function LoginPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    const { error: err } = await signIn(email, password);
    setLoading(false);
    if (err) { setError(err.message); return; }
    navigate('/');
  }

  return (
    <div style={styles.root}>
      {/* Background grid */}
      <div style={styles.grid} />

      <div style={styles.panel}>
        {/* Header */}
        <div style={styles.header}>
          <div style={styles.logo}>CREWBRIEF</div>
          <div style={styles.subtitle}>ROYAL JORDANIAN · FLIGHT OPERATIONS</div>
          <div style={styles.divider} />
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} style={styles.form}>
          <label style={styles.label}>
            <span style={styles.labelText}>CREW ID / EMAIL</span>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              autoComplete="email"
              style={styles.input}
              placeholder="pilot@rj.com"
            />
          </label>

          <label style={styles.label}>
            <span style={styles.labelText}>PASSPHRASE</span>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              style={styles.input}
              placeholder="••••••••"
            />
          </label>

          {error && (
            <div style={styles.error}>
              ⚠ {error}
            </div>
          )}

          <button type="submit" disabled={loading} style={{
            ...styles.btn,
            opacity: loading ? 0.6 : 1,
            cursor: loading ? 'not-allowed' : 'pointer',
          }}>
            {loading ? 'AUTHENTICATING…' : 'ACCESS SYSTEM →'}
          </button>
        </form>

        <div style={styles.footer}>
          <span style={{ color: 'var(--text-dim)', fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
            AUTHORIZED PERSONNEL ONLY · RJ FLIGHT OPS
          </span>
        </div>
      </div>
    </div>
  );
}

const styles = {
  root: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'var(--bg)',
    position: 'relative',
    overflow: 'hidden',
  },
  grid: {
    position: 'absolute',
    inset: 0,
    backgroundImage: `
      linear-gradient(var(--border) 1px, transparent 1px),
      linear-gradient(90deg, var(--border) 1px, transparent 1px)
    `,
    backgroundSize: '48px 48px',
    opacity: 0.4,
  },
  panel: {
    position: 'relative',
    width: '100%',
    maxWidth: '400px',
    background: 'var(--bg-2)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)',
    padding: '40px',
    animation: 'fadeUp 0.4s ease forwards',
    boxShadow: '0 0 60px rgba(232,162,52,0.05)',
  },
  header: {
    marginBottom: '32px',
    textAlign: 'center',
  },
  logo: {
    fontFamily: 'var(--font-display)',
    fontSize: '36px',
    letterSpacing: '8px',
    color: 'var(--amber)',
    marginBottom: '6px',
  },
  subtitle: {
    fontFamily: 'var(--font-mono)',
    fontSize: '10px',
    letterSpacing: '2px',
    color: 'var(--text-dim)',
    marginBottom: '20px',
  },
  divider: {
    height: '1px',
    background: 'linear-gradient(90deg, transparent, var(--border-2), transparent)',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
  },
  label: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  labelText: {
    fontFamily: 'var(--font-mono)',
    fontSize: '10px',
    letterSpacing: '2px',
    color: 'var(--text-dim)',
  },
  input: {
    background: 'var(--bg)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius)',
    padding: '10px 14px',
    color: 'var(--text)',
    fontFamily: 'var(--font-mono)',
    fontSize: '13px',
    outline: 'none',
    transition: 'border-color 0.15s',
  },
  error: {
    background: 'var(--red-dim)',
    border: '1px solid var(--red)',
    borderRadius: 'var(--radius)',
    padding: '10px 14px',
    color: 'var(--red)',
    fontFamily: 'var(--font-mono)',
    fontSize: '12px',
  },
  btn: {
    background: 'var(--amber)',
    color: 'var(--bg)',
    border: 'none',
    borderRadius: 'var(--radius)',
    padding: '12px',
    fontFamily: 'var(--font-mono)',
    fontSize: '12px',
    fontWeight: '600',
    letterSpacing: '2px',
    transition: 'opacity 0.15s',
    marginTop: '4px',
  },
  footer: {
    marginTop: '28px',
    textAlign: 'center',
  },
};
