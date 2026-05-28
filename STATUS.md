# CrewBrief Session Handoff — May 28, 2026

### What's working
- Frontend live at crewbrief-six.vercel.app
- Backend live at crewbrief-production.up.railway.app
- `/health` returns `{"status":"ok","service":"crewbrief-api"}`
- JWT auth working — ES256 JWKS verification via PyJWT
- CORS fully resolved — all preflights return 200
- Supabase permissions fixed — service_role granted on all tables
- Sessions and Documents endpoints both returning 200
- Full end-to-end request flow working (frontend → backend → Supabase)

### What's broken / in progress
- Document upload and ingestion pipeline not yet tested
- Sessions creation/query flow not yet tested beyond 200 response
- No documents in the library yet — UI shows empty state

### Next concrete step
Test the document upload flow — upload a sample PDF via the UI and confirm it appears in the library without error. Watch Railway Deploy Logs for any ingestion errors.

### Decisions made this session
- `allow_credentials=False` — correct for JWT Bearer auth, not cookie auth
- CORS origins hardcoded in main.py — removes env var indirection risk
- `GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role` — comprehensive grant, includes ALTER DEFAULT PRIVILEGES so future tables inherit the grant
- Documents table schema migrated to match code: renamed `title→name`, `doc_type→document_type`; added `filename`, `revision`, `status`, `chunk_count`, `uploader_id`

### Dead ends — don't retry
- CORS was never a Railway infrastructure issue — it was origin mismatch + `allow_credentials=True`
- The 400 preflights were partly browser cache and partly the wrong Vercel preview URL (crewbrief-git-main-...vercel.app instead of crewbrief-six.vercel.app)
- `allow_credentials=True` with specific origins caused silent preflight failures in this Starlette version
- Don't debug CORS from the backend side without curl first — always test the endpoint directly before touching config

### Files touched
- `backend/app/main.py` — CORS config fixed, debug print removed
- Supabase `documents` table — schema migrated via SQL Editor
- Supabase all tables — service_role grants applied
