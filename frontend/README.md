# CrewBrief Frontend

React SPA for the CrewBrief aviation document Q&A system.

## Setup

```bash
npm install
cp .env.example .env.local
# Fill in your Supabase URL, anon key, and Railway backend URL
npm start
```

## Environment Variables

| Variable | Description |
|---|---|
| `REACT_APP_SUPABASE_URL` | Your Supabase project URL |
| `REACT_APP_SUPABASE_ANON_KEY` | Supabase anon/public key |
| `REACT_APP_API_URL` | Railway backend URL (e.g. `https://crewbrief-production.up.railway.app`) |

## Deploy to Vercel

1. Push this folder to `basemaggad/crewbrief` under `/frontend`
2. In Vercel → New Project → import repo → set root directory to `frontend`
3. Add the three environment variables above
4. Deploy

`vercel.json` handles SPA client-side routing automatically.

## Structure

```
src/
  lib/supabase.js       — Supabase client + Railway API helpers
  context/AuthContext   — Auth state via Supabase session
  pages/
    LoginPage           — Email/password auth
    AppShell            — Layout shell with sidebar
    ChatPage            — Q&A chat interface with session routing
    DocumentsPage       — Upload + manage manuals
  components/
    Sidebar             — Navigation + session list
    CitationBlock       — Expandable source citation
    InvalidationBanner  — §4 invalidated reference warning
```

## API Contract (Railway backend expected)

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/documents` | GET | List documents |
| `/documents/upload` | POST (multipart) | Upload PDF |
| `/documents/:id` | DELETE | Remove document |
| `/sessions` | GET | List sessions |
| `/sessions` | POST | Create session |
| `/sessions/:id` | GET | Get session + messages + invalidations |
| `/sessions/:id` | DELETE | Delete session |
| `/query` | POST | Ask question (JSON response) |
| `/query/stream` | POST | Ask question (SSE stream, optional) |
