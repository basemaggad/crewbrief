CrewBrief Session Handoff — May 28, 2026
What's working

Frontend live at crewbrief-six.vercel.app
Backend live at crewbrief-production.up.railway.app
/health returns {"status":"ok","service":"crewbrief-api"}
Supabase connected, tables correct, user exists (basem.aggad@gmail.com)
JWT auth fixed — ES256 JWKS verification working via PyJWT
Railway build command conflict resolved — Custom Build Command cleared in dashboard

What's broken / in progress

CORS preflight failing — sessions and documents returning 400 on OPTIONS requests
Backend returns {"detail":"Missing authorization header"} on actual requests
Root cause not yet confirmed — need to see response headers on the preflight request

Next concrete step

In browser DevTools → Network tab → click the documents preflight row (type: Preflight, status: 400)
Click Headers tab → copy the Response Headers section
Paste here so we can see what CORS headers the backend is returning
Fix will likely be in main.py CORS config or a middleware ordering issue

Decisions made this session

DocumentsPage.js updated to wait for authLoading before calling API
STATUS.md created at repo root for cross-session continuity
Project instructions updated with handoff format and "no guessing" rule
PyJWT with PyJWKClient confirmed as correct approach for ES256

Dead ends — don't retry

python-jose — does not support ES256, replaced
Looking for "Copy JWT" on Supabase Auth → Users page — removed from UI
Railway railway.toml was clean — conflict was in dashboard Settings, not the file
CORS is not a frontend issue — main.py config and FRONTEND_ORIGIN variable are both correct

Files touched

backend/app/core/auth.py — rewritten for PyJWT JWKS verification
backend/requirements.txt — switched to PyJWT[crypto]==2.10.0
frontend/src/pages/DocumentsPage.js — wait for authLoading before API call
STATUS.md — created at repo root
