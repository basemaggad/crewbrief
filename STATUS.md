# CrewBrief — Project Status

## What's working
- Frontend live at `crewbrief-six.vercel.app`
- Backend live at `crewbrief-production.up.railway.app`
- `/health` returns `{"status":"ok","service":"crewbrief-api"}`
- Supabase connected, tables correct, user exists (`basem.aggad@gmail.com`)
- `session_messages` table name fix applied throughout backend
- Railway public domain port set to 8080

## What's broken / in progress
- JWT auth failing: `"Invalid token: The specified alg value is not allowed"`
- Root cause: PyJWT fix commit ("Switch to PyJWT for proper JWKS verification") **failed to deploy**
- Failure reason: Railway dashboard has `buildCommand` = `uvicorn main:app --host 0.0.0.0 --port $PORT` which conflicts with `startCommand`
- Fix identified: clear the **Custom Build Command** field in Railway Settings dashboard — leave only Custom Start Command

## Next concrete step
- Clear Custom Build Command in Railway Settings (leave blank)
- Save → Railway will auto-redeploy
- Confirm new deployment is ACTIVE (commit message: "Switch to PyJWT for proper JWKS verification")
- Test auth by loading `crewbrief-six.vercel.app` — error should be gone

## Decisions made
- Using PyJWT with PyJWKClient for ES256 JWKS verification
- `auth.py` handles both HS256 (legacy) and ES256/RS256 (new Supabase asymmetric)
- New Supabase API keys: using `sb_publishable_...` format (not legacy JWT-based anon key)

## Dead ends — don't retry
- `python-jose` — does not support ES256 JWKS verification, replaced by PyJWT
- Looking for "Copy JWT" button on Supabase Auth → Users page — removed in current Supabase UI
- Railway `railway.toml` is clean — the conflict is in the **dashboard settings**, not the file

## Files touched
- `backend/app/core/auth.py` — rewritten for PyJWT JWKS verification
- `backend/requirements.txt` — switched to `PyJWT[crypto]==2.10.0`
