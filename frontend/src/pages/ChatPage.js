import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../lib/supabase';
import CitationBlock from '../components/CitationBlock';
import InvalidationBanner from '../components/InvalidationBanner';

const Icon = ({ d, size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);

const SEND = 'M22 2L11 13 M22 2L15 22 8 13 2 8z';
const STOP = 'M18 6H6v12h12z';

export default function ChatPage() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [session, setSession] = useState(null);
  const [invalidations, setInvalidations] = useState([]);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    if (sessionId) {
      loadSession(sessionId);
    } else {
      setSession(null);
      setMessages([]);
      setInvalidations([]);
    }
  }, [sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function loadSession(id) {
    setSessionLoading(true);
    try {
      const data = await api.sessions.get(id);
      setSession(data.session);
      setMessages(data.messages || []);
      setInvalidations(data.invalidations || []);
    } catch (e) {
      console.error('Failed to load session', e);
    } finally {
      setSessionLoading(false);
    }
  }

  async function ensureSession() {
    if (sessionId) return sessionId;
    const s = await api.sessions.create('New briefing');
    navigate(`/chat/${s.id}`, { replace: true });
    return s.id;
  }

  async function sendMessage(e) {
    e?.preventDefault();
    const q = input.trim();
    if (!q || loading) return;

    setInput('');
    setLoading(true);

    const userMsg = { id: Date.now(), role: 'user', content: q };
    const assistantMsg = { id: Date.now() + 1, role: 'assistant', content: '', streaming: true, citations: [] };

    setMessages(prev => [...prev, userMsg, assistantMsg]);

    try {
      const sid = await ensureSession();

      // Try streaming first, fall back to regular
      let usedStream = false;
      try {
        const res = await api.query.stream(sid, q);
        if (res.ok && res.headers.get('content-type')?.includes('text/event-stream')) {
          usedStream = true;
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          abortRef.current = reader;

          let buffer = '';
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            for (const line of lines) {
              if (!line.startsWith('data:')) continue;
              const raw = line.slice(5).trim();
              if (raw === '[DONE]') break;
              try {
                const chunk = JSON.parse(raw);
                setMessages(prev => prev.map(m =>
                  m.id === assistantMsg.id
                    ? {
                        ...m,
                        content: chunk.content !== undefined ? chunk.content : m.content + (chunk.delta || ''),
                        citations: chunk.citations || m.citations,
                        streaming: !chunk.done,
                      }
                    : m
                ));
              } catch (_) {}
            }
          }
        }
      } catch (_) {}

      if (!usedStream) {
        const data = await api.query.ask(sid, q);
        setMessages(prev => prev.map(m =>
          m.id === assistantMsg.id
            ? { ...m, content: data.answer, citations: data.citations || [], streaming: false }
            : m
        ));
      }

    } catch (err) {
      setMessages(prev => prev.map(m =>
        m.id === assistantMsg.id
          ? { ...m, content: `Error: ${err.message}`, streaming: false, error: true }
          : m
      ));
    } finally {
      setLoading(false);
      abortRef.current = null;
      inputRef.current?.focus();
    }
  }

  function stopStreaming() {
    abortRef.current?.cancel?.();
    setLoading(false);
    setMessages(prev => prev.map(m =>
      m.streaming ? { ...m, streaming: false } : m
    ));
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  // ── Empty state ────────────────────────────────────────────────────────────
  if (!sessionId) {
    return (
      <div style={styles.emptyRoot}>
        <div style={styles.emptyInner}>
          <div style={styles.emptyLogo}>CREWBRIEF</div>
          <p style={styles.emptyTagline}>Ask anything about your manuals, procedures, and notices.</p>
          <div style={styles.suggestGrid}>
            {SUGGESTIONS.map((s, i) => (
              <button
                key={i}
                style={{ ...styles.suggestCard, animationDelay: `${i * 0.06}s` }}
                onClick={() => { setInput(s); inputRef.current?.focus(); }}
              >
                <span style={styles.suggestIcon}>{s.icon || '→'}</span>
                <span>{s.text || s}</span>
              </button>
            ))}
          </div>

          {/* Inline input on empty state */}
          <div style={styles.emptyInputWrap}>
            <InputBar
              value={input}
              onChange={setInput}
              onSubmit={sendMessage}
              onKeyDown={handleKeyDown}
              loading={loading}
              onStop={stopStreaming}
              inputRef={inputRef}
            />
          </div>
        </div>
      </div>
    );
  }

  // ── Session view ───────────────────────────────────────────────────────────
  return (
    <div style={styles.root}>
      {/* Session header */}
      <div style={styles.topBar}>
        <div style={styles.sessionName}>
          <span style={styles.sessionDot} />
          <span>{session?.title || 'Briefing'}</span>
        </div>
        {invalidations.length > 0 && (
          <div style={styles.invalidBadge}>⛔ {invalidations.length} invalidated ref{invalidations.length > 1 ? 's' : ''}</div>
        )}
      </div>

      {/* Messages */}
      <div style={styles.messages}>
        {sessionLoading ? (
          <div style={styles.loadingSpinner}>
            <div style={styles.spinner} />
          </div>
        ) : (
          <>
            {invalidations.map((inv, i) => (
              <InvalidationBanner key={i} data={inv} />
            ))}
            {messages.map((msg, i) => (
              <Message key={msg.id || i} msg={msg} index={i} />
            ))}
          </>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={styles.inputArea}>
        <InputBar
          value={input}
          onChange={setInput}
          onSubmit={sendMessage}
          onKeyDown={handleKeyDown}
          loading={loading}
          onStop={stopStreaming}
          inputRef={inputRef}
        />
        <div style={styles.inputHint}>
          Enter to send · Shift+Enter for newline
        </div>
      </div>
    </div>
  );
}

// ── Message bubble ──────────────────────────────────────────────────────────
function Message({ msg, index }) {
  const isUser = msg.role === 'user';
  return (
    <div style={{
      ...styles.msgRow,
      justifyContent: isUser ? 'flex-end' : 'flex-start',
      animation: `fadeUp 0.25s ease ${Math.min(index, 6) * 0.04}s both`,
    }}>
      {!isUser && <div style={styles.avatar}>CB</div>}
      <div style={{
        ...styles.bubble,
        ...(isUser ? styles.bubbleUser : styles.bubbleAssistant),
        ...(msg.error ? styles.bubbleError : {}),
      }}>
        {msg.streaming && !msg.content ? (
          <ThinkingDots />
        ) : (
          <>
            <div style={styles.msgContent}>
              {formatContent(msg.content)}
            </div>
            {msg.streaming && <ThinkingDots inline />}
            {msg.citations?.length > 0 && (
              <div style={styles.citationsWrap}>
                {msg.citations.map((c, i) => (
                  <CitationBlock key={i} citation={c} />
                ))}
              </div>
            )}
          </>
        )}
      </div>
      {isUser && <div style={styles.avatarUser}>YOU</div>}
    </div>
  );
}

// ── Input bar ───────────────────────────────────────────────────────────────
function InputBar({ value, onChange, onSubmit, onKeyDown, loading, onStop, inputRef }) {
  return (
    <form onSubmit={onSubmit} style={styles.inputForm}>
      <textarea
        ref={inputRef}
        value={value}
        onChange={e => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        rows={1}
        placeholder="Ask about procedures, limitations, notices…"
        style={styles.textarea}
      />
      {loading ? (
        <button type="button" onClick={onStop} style={{ ...styles.sendBtn, background: 'var(--red)' }}>
          <Icon d={STOP} size={16} />
        </button>
      ) : (
        <button type="submit" disabled={!value.trim()} style={{
          ...styles.sendBtn,
          opacity: value.trim() ? 1 : 0.4,
          cursor: value.trim() ? 'pointer' : 'not-allowed',
        }}>
          <Icon d={SEND} size={16} />
        </button>
      )}
    </form>
  );
}

function ThinkingDots({ inline }) {
  return (
    <span style={{ display: 'inline-flex', gap: '4px', alignItems: 'center', marginLeft: inline ? '8px' : 0 }}>
      {[0, 1, 2].map(i => (
        <span key={i} style={{
          width: '5px', height: '5px',
          borderRadius: '50%',
          background: 'var(--amber)',
          animation: `pulse 1.2s ease ${i * 0.2}s infinite`,
          display: 'inline-block',
        }} />
      ))}
    </span>
  );
}

function formatContent(text) {
  if (!text) return null;
  // Basic markdown-ish rendering
  return text.split('\n').map((line, i) => {
    if (line.startsWith('# ')) return <h3 key={i} style={styles.h3}>{line.slice(2)}</h3>;
    if (line.startsWith('## ')) return <h4 key={i} style={styles.h4}>{line.slice(3)}</h4>;
    if (line.startsWith('- ') || line.startsWith('• ')) return (
      <div key={i} style={styles.listItem}>
        <span style={{ color: 'var(--amber)', marginRight: '8px' }}>·</span>
        {line.slice(2)}
      </div>
    );
    if (!line.trim()) return <div key={i} style={{ height: '8px' }} />;
    return <p key={i} style={{ marginBottom: '4px' }}>{line}</p>;
  });
}

const SUGGESTIONS = [
  { text: 'What are the A320 engine start limitations?', icon: '⚙' },
  { text: 'Summarize the latest NOTAM for OJAI', icon: '📋' },
  { text: 'What are the MEL conditions for dispatching with one pack inoperative?', icon: '✈' },
  { text: 'Show the approach minimums for RWY 26L at OJAI', icon: '📡' },
];

const styles = {
  root: {
    display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden',
  },
  topBar: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '12px 24px',
    borderBottom: '1px solid var(--border)',
    background: 'var(--bg-2)',
    flexShrink: 0,
    minHeight: '48px',
  },
  sessionName: {
    display: 'flex', alignItems: 'center', gap: '8px',
    fontFamily: 'var(--font-mono)', fontSize: '12px', letterSpacing: '1px',
    color: 'var(--text-2)',
  },
  sessionDot: {
    width: '6px', height: '6px', borderRadius: '50%',
    background: 'var(--teal)',
    animation: 'pulse 2s ease infinite',
  },
  invalidBadge: {
    fontFamily: 'var(--font-mono)', fontSize: '11px',
    color: 'var(--red)', background: 'var(--red-dim)',
    border: '1px solid var(--red)',
    borderRadius: 'var(--radius)', padding: '3px 10px',
  },
  messages: {
    flex: 1, overflowY: 'auto', padding: '24px',
    display: 'flex', flexDirection: 'column', gap: '16px',
  },
  loadingSpinner: {
    display: 'flex', justifyContent: 'center', padding: '40px',
  },
  spinner: {
    width: '24px', height: '24px',
    border: '2px solid var(--border-2)',
    borderTopColor: 'var(--amber)',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  msgRow: {
    display: 'flex', gap: '12px', alignItems: 'flex-end',
    maxWidth: '100%',
  },
  avatar: {
    width: '28px', height: '28px', borderRadius: 'var(--radius)',
    background: 'var(--amber)', color: 'var(--bg)',
    fontFamily: 'var(--font-mono)', fontSize: '9px', fontWeight: 600,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    flexShrink: 0, letterSpacing: '1px',
  },
  avatarUser: {
    width: '28px', height: '28px', borderRadius: 'var(--radius)',
    background: 'var(--surface-2)', color: 'var(--text-dim)',
    fontFamily: 'var(--font-mono)', fontSize: '9px', fontWeight: 600,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    flexShrink: 0, letterSpacing: '1px',
    border: '1px solid var(--border)',
  },
  bubble: {
    maxWidth: '72%', padding: '12px 16px',
    borderRadius: 'var(--radius-lg)', lineHeight: 1.65,
    fontSize: '14px',
  },
  bubbleUser: {
    background: 'var(--surface-2)', border: '1px solid var(--border)',
    color: 'var(--text)', borderBottomRightRadius: 2,
  },
  bubbleAssistant: {
    background: 'var(--surface)', border: '1px solid var(--border)',
    color: 'var(--text)', borderBottomLeftRadius: 2,
  },
  bubbleError: {
    background: 'var(--red-dim)', border: '1px solid var(--red)',
    color: 'var(--red)',
  },
  msgContent: { lineHeight: 1.7 },
  citationsWrap: {
    marginTop: '12px', paddingTop: '12px',
    borderTop: '1px solid var(--border)',
    display: 'flex', flexDirection: 'column', gap: '6px',
  },
  h3: {
    fontFamily: 'var(--font-mono)', fontSize: '13px', letterSpacing: '1px',
    color: 'var(--amber)', marginBottom: '8px', marginTop: '4px',
    textTransform: 'uppercase',
  },
  h4: {
    fontFamily: 'var(--font-sans)', fontSize: '13px', fontWeight: 600,
    color: 'var(--text)', marginBottom: '6px',
  },
  listItem: {
    display: 'flex', paddingLeft: '4px', marginBottom: '2px',
  },
  inputArea: {
    padding: '16px 24px 20px',
    borderTop: '1px solid var(--border)',
    background: 'var(--bg-2)',
    flexShrink: 0,
  },
  inputForm: {
    display: 'flex', gap: '10px', alignItems: 'flex-end',
  },
  textarea: {
    flex: 1, background: 'var(--surface)', border: '1px solid var(--border-2)',
    borderRadius: 'var(--radius-lg)', padding: '10px 14px',
    color: 'var(--text)', fontFamily: 'var(--font-sans)', fontSize: '14px',
    resize: 'none', outline: 'none', lineHeight: 1.5,
    maxHeight: '160px', overflowY: 'auto',
    transition: 'border-color 0.15s',
  },
  sendBtn: {
    background: 'var(--amber)', border: 'none',
    borderRadius: 'var(--radius-lg)', width: '40px', height: '40px',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    color: 'var(--bg)', cursor: 'pointer', flexShrink: 0,
    transition: 'opacity 0.15s',
  },
  inputHint: {
    fontFamily: 'var(--font-mono)', fontSize: '10px',
    color: 'var(--text-dim)', letterSpacing: '0.5px',
    marginTop: '6px', paddingLeft: '2px',
  },
  // Empty state
  emptyRoot: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    height: '100vh', padding: '24px',
  },
  emptyInner: {
    width: '100%', maxWidth: '640px', textAlign: 'center',
  },
  emptyLogo: {
    fontFamily: 'var(--font-display)', fontSize: '48px', letterSpacing: '10px',
    color: 'var(--amber)', marginBottom: '12px',
  },
  emptyTagline: {
    color: 'var(--text-2)', fontSize: '15px', marginBottom: '32px',
  },
  suggestGrid: {
    display: 'grid', gridTemplateColumns: '1fr 1fr',
    gap: '10px', marginBottom: '28px',
  },
  suggestCard: {
    display: 'flex', alignItems: 'flex-start', gap: '10px',
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)', padding: '12px 14px',
    color: 'var(--text-2)', cursor: 'pointer', textAlign: 'left',
    fontSize: '13px', lineHeight: 1.4, fontFamily: 'var(--font-sans)',
    transition: 'border-color 0.15s, color 0.15s',
    animation: 'fadeUp 0.3s ease both',
  },
  suggestIcon: {
    fontSize: '16px', flexShrink: 0, marginTop: '1px',
  },
  emptyInputWrap: {
    background: 'var(--bg-2)', borderRadius: 'var(--radius-lg)',
    padding: '16px',
    border: '1px solid var(--border)',
  },
};
