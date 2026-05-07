import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.REACT_APP_SUPABASE_URL;
const supabaseAnonKey = process.env.REACT_APP_SUPABASE_ANON_KEY;

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

// ── API helpers (Railway backend) ──────────────────────────────────────────
const API_URL = process.env.REACT_APP_API_URL || 'https://crewbrief-production.up.railway.app';

async function apiFetch(path, options = {}) {
  const session = await supabase.auth.getSession();
  const token = session?.data?.session?.access_token;

  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'API error');
  }

  return res.json();
}

// Documents
export const api = {
  health: () => apiFetch('/health'),

  documents: {
    list: () => apiFetch('/documents'),
    upload: (formData) =>
      apiFetch('/documents/upload', { method: 'POST', body: formData }),
    delete: (id) =>
      apiFetch(`/documents/${id}`, { method: 'DELETE' }),
  },

  sessions: {
    list: () => apiFetch('/sessions'),
    get: (id) => apiFetch(`/sessions/${id}`),
    create: (title) =>
      apiFetch('/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
      }),
    delete: (id) => apiFetch(`/sessions/${id}`, { method: 'DELETE' }),
  },

  query: {
    ask: (sessionId, question) =>
      apiFetch('/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, question }),
      }),
    // streaming version — returns raw response for caller to handle SSE
    stream: async (sessionId, question) => {
      const session = await supabase.auth.getSession();
      const token = session?.data?.session?.access_token;
      return fetch(`${API_URL}/query/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ session_id: sessionId, question }),
      });
    },
  },
};
