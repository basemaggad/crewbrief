# CrewBrief — Full Implementation & Deployment Guide

This guide takes you from the current codebase to a fully deployed,
job-queue-backed ingestion pipeline ready for live testing.

**Time required:** ~20 minutes  
**Who does what:** everything below happens in four places:
- Supabase SQL Editor (database migrations)
- GitHub (push code)
- Railway dashboard (deploy two services)
- Your browser (test)

---

## What you are deploying

```
Browser
  │  POST /documents/upload
  │  Returns immediately with status = PROCESSING
  │
API Service (Railway — already live)
  ├─ Streams PDF → temp file      (no memory spike)
  ├─ Uploads to Supabase Storage  (original PDF preserved)
  ├─ Creates documents row        (status = processing)
  ├─ Creates ingestion_jobs row   (status = pending)
  └─ Returns the document row ────────────────────────────────► Browser
                                                              (UI polls every 4s)
  Supabase DB ◄──────────────────── Worker Service (NEW on Railway)
     │                               ├─ Polls for pending jobs every 5s
     │  claim_ingestion_job()        ├─ Downloads PDF from Storage
     │  (FOR UPDATE SKIP LOCKED)     ├─ Extracts text page-by-page
     │                               ├─ Splits into ~1000-char chunks
     └──────────────────────────────►├─ Embeds each chunk
                                     ├─ Inserts chunks into document_chunks
                                     ├─ Sets document status = ready
                                     └─ Sets job status = done ──► UI flips to READY

On failure: retries up to 3×. After 3 failures a DB trigger sets
document.status = error automatically. The worker never re-queues a job
that is actively running — a heartbeat thread proves the worker is alive.
```

---

## Files in this release

### SQL — run in Supabase (in order)
| File | What it does |
|------|-------------|
| `backend/fixes_migration.sql` | Creates users + organizations tables, backfills profiles, trigger for new signups, raises Storage bucket limit to 500 MB |
| `backend/job_queue_migration.sql` | Creates ingestion_jobs table, claim_ingestion_job() RPC with heartbeat-aware stale detection, error-sync trigger |

### Backend — push to GitHub (Railway auto-deploys)
| File | What changed |
|------|-------------|
| `backend/worker.py` | **New.** Polling worker with heartbeat thread, interruptible idle wait, graceful shutdown |
| `backend/app/api/routes/documents.py` | Streaming upload (no memory spike), job queue enqueue, 500 MB limit |
| `backend/app/services/document_service.py` | Split into create_record / enqueue / process_from_storage / delete; idempotent retry (clears old chunks) |
| `backend/app/core/config.py` | Added MAX_UPLOAD_MB = 500 |

### Frontend — push to GitHub (Vercel auto-deploys)
| File | What changed |
|------|-------------|
| `frontend/src/pages/DocumentsPage.js` | Live status polling every 4s, dynamic fleet label, 500 MB hint text |
| `frontend/src/pages/ChatPage.js` | Removed broken /query/stream attempt (was 404ing on every message) |
| `frontend/src/components/Sidebar.js` | Refreshes session list on route change (new sessions appear without reload) |

---

## Step 1 — Run the database migrations

> **Do this before pushing any code.** The API and worker both depend on
> tables and functions that must exist before they start.

### 1a — Open Supabase SQL Editor
1. Go to your Supabase project dashboard
2. Click **SQL Editor** in the left sidebar
3. Click **+ New query**

### 1b — Run fixes_migration.sql FIRST

Paste the full contents of `backend/fixes_migration.sql` and click **Run**.

**Before the rest of the file runs, check Section 0 output:**
Look at the first result set (table names). Verify `users` appears. If it
does not, the rest of the file creates it. That is expected — continue.

**Expected final output:**
| label | n |
|-------|---|
| auth users | 1 (or however many accounts you have) |
| profile rows | same number |
| profiles missing org | 0 |

The last row **must be 0**. If it is not 0, re-run the file — it is
idempotent and will fix the gap.

### 1c — Run job_queue_migration.sql SECOND

Open a new query, paste `backend/job_queue_migration.sql`, click **Run**.

**Expected output:**
| column_name |
|-------------|
| last_heartbeat_at |

| routine_name |
|-------------|
| claim_ingestion_job |
| sync_document_error_status |

All three rows must appear. If either routine is missing, scroll up in
the results panel for an error message.

### 1d — Verify the storage bucket size limit

In the SQL Editor run:
```sql
select id, name, file_size_limit from storage.buckets where id = 'documents';
```

`file_size_limit` should be `524288000` (500 MB).
If the `documents` bucket does not exist yet, the migration created it.
If it exists but shows a smaller limit, re-run Section 5 of
`fixes_migration.sql` alone.

> **Supabase plan note:** the bucket limit is only one layer. Your
> Supabase project plan also has an upload cap. The free tier does not
> support 500 MB uploads — verify in Dashboard → Settings → Storage.
> For the initial test, use a small PDF (a few MB) regardless of plan.

---

## Step 2 — Push code to GitHub

Copy each file from this release into your repo at **exactly** the path
shown, then commit and push to the `main` branch.

```
backend/worker.py
backend/job_queue_migration.sql
backend/fixes_migration.sql
backend/app/api/routes/documents.py
backend/app/services/document_service.py
backend/app/core/config.py
frontend/src/pages/DocumentsPage.js
frontend/src/pages/ChatPage.js
frontend/src/components/Sidebar.js
```

Once pushed:
- **Railway** redeploys the API service automatically (watch its deploy log)
- **Vercel** redeploys the frontend automatically

**Wait for both to go green before continuing.**

To confirm the API redeployed correctly:
```
curl https://crewbrief-production.up.railway.app/health
```
Should return `{"status":"ok","service":"crewbrief-api"}`.

---

## Step 3 — Create the worker service on Railway

The worker is a second Railway service pointing at the same GitHub repo.
It runs `python worker.py` instead of uvicorn.

### 3a — Create the service

1. Open your Railway project at railway.app
2. Click **+ New** in the top right
3. Choose **GitHub Repo**
4. Select `basemaggad/crewbrief`
5. Railway will begin auto-detecting settings — **stop it before it deploys**
   by clicking **Configure** immediately

### 3b — Set the root directory

1. Go to the service → **Settings** tab
2. Under **Build** → **Root Directory**, enter:
   ```
   backend
   ```
3. This tells Railway to install from `backend/requirements.txt`

### 3c — Set the start command

1. Still in **Settings**, under **Deploy** → **Start Command**
2. Replace whatever is there with:
   ```
   python worker.py
   ```

### 3d — Remove networking (critical)

The worker has no HTTP port — Railway's health check will mark it crashed
if a port is expected.

1. Go to **Settings** → **Networking**
2. If any port is listed under **Exposed Ports**, remove it
3. Make sure there is no health check path configured

### 3e — Copy environment variables

1. Go to your **API service** → **Variables** tab
2. Copy every variable listed there
3. Go to your new **worker service** → **Variables** tab
4. Add all of them:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_JWT_SECRET`
   - `ANTHROPIC_API_KEY`
   - `STORAGE_BUCKET` (if set — defaults to `documents` if absent)

### 3f — Deploy

1. Click **Deploy Now** on the worker service
2. Click **View Logs** → **Deploy Logs**

Wait for the build to finish (Railway installs requirements.txt).
Then switch to **Runtime Logs**.

**Healthy startup looks like this:**
```
============================================================
CrewBrief ingestion worker starting
  Storage bucket : documents
  Poll interval  : 5s
  Heartbeat      : every 30s
============================================================
2026-05-28 10:00:00  [INFO   ]  Worker alive — queue empty, polling…
```

The "queue empty" line repeats every 60 seconds. That is the worker
idling, waiting for an upload. If you see a traceback instead, go to
the Troubleshooting section below.

---

## Step 4 — Test the upload flow end-to-end

**Use a small PDF for this first test** — a few MB, not 500 MB. Confirm
the basic flow works before testing large files.

### 4a — Upload a document

1. Open `crewbrief-six.vercel.app` and log in
2. Go to the **Documents** page
3. Select a document type (e.g. FCOM), fill in a revision
4. Drop a PDF onto the upload zone or click to browse

The row should appear immediately with status **PROCESSING** and a
pulsing amber dot.

### 4b — Watch the worker logs

In Railway, open the worker service → **Runtime Logs**. Within 5 seconds
of the upload you should see:

```
Job a1b2c3d4…  doc=e5f6g7h8…  attempt 1/3
  ↓ Downloading rj-org-id/uuid_filename.pdf
  ✓ Downloaded 4,521,032 bytes — starting pipeline
  ✓ Pipeline complete — marking job done
Job a1b2c3d4… completed ✓
```

### 4c — Confirm the UI updates

Back in the browser, within 4 seconds of the job completing the row
should flip to **READY** with a teal dot and a chunk count. You did not
need to refresh the page.

### 4d — Test a query (optional, first smoke test)

1. Go to the **Chat** page
2. Ask something related to the PDF you just uploaded
3. You should get an answer with citations listed below it

If the answer says "I don't have this information in your current
document library," that means retrieval found no matching chunks — check
that the document status is READY and that chunk_count > 0 in the
Documents page.

---

## Step 5 — Clean up documents stuck from before this deployment

Any documents uploaded before this release are stuck on PROCESSING
forever (the old background-task approach). Clean them up so the UI
shows an honest state.

In the Supabase SQL Editor:
```sql
-- See what's stuck
select id, name, status, created_at
from documents
where status = 'processing'
order by created_at;

-- Mark them all error
update documents
set status        = 'error',
    error_message = 'Stuck before job queue was introduced — re-upload to process'
where status = 'processing';
```

---

## Troubleshooting

### Worker crashes immediately on start

**`KeyError: 'SUPABASE_URL'` or `ValidationError`** — an environment
variable is missing or misnamed. Double-check every variable in Step 3e.
Variable names are case-sensitive.

**`ModuleNotFoundError: No module named 'app'`** — the root directory is
not set to `backend`. Fix in Settings → Build → Root Directory.

**`ModuleNotFoundError: No module named 'supabase'` or similar** — the
build did not install requirements. Check that `backend/requirements.txt`
is in the repo and Railway's root directory is `backend`.

### Document stays on PROCESSING after upload

**Worker healthy but job never appears in logs** — check the API deploy
log for errors during the upload request. The most likely cause is that
`ingestion_jobs` was not created (Step 1c missed or the RPC is missing).
Re-run `job_queue_migration.sql`.

**Worker logs show an error for the job** — read the error text at the
`[ERROR]` line. Common causes and fixes:

| Error | Fix |
|-------|-----|
| `Storage upload failed` | The `documents` bucket doesn't exist or the service_role key lacks storage permission. Re-run Section 5 of `fixes_migration.sql`. |
| `No extractable text in PDF` | The PDF is a scanned image — pypdf can't extract text. Try a digitally-authored PDF. |
| `Document X has no storage_path` | The API's storage upload failed before the job was created. Check the API logs for that request. |
| `403` from Supabase | A table is missing a service_role grant. Re-run the GRANT block at the bottom of `fixes_migration.sql`. |

### Document shows ERROR status in UI

Open Railway worker logs, search for the document ID (first 8 characters
are shown in the job log line). The `[ERROR]` entry has the full message.
After 3 failed attempts the document is marked error permanently — fix
the underlying issue, then re-upload the file.

### Job got stuck in PROCESSING in the DB

This should self-heal: the `claim_ingestion_job()` RPC resets any job
whose heartbeat is older than 2 minutes on the next poll cycle. If it
has not self-healed after 5 minutes, force it manually:

```sql
update ingestion_jobs
set status = 'pending', attempts = 0, started_at = null, last_heartbeat_at = null
where document_id = '<paste doc id here>';
```

### New sessions don't appear in the sidebar

This was a known bug — fixed. If you still see it, hard-refresh the
browser (Cmd/Ctrl + Shift + R) to ensure the new Sidebar.js is loaded.

---

## Performance expectations (placeholder embeddings)

The current `embedding_service.py` uses deterministic hash-based
embeddings as a placeholder. Benchmarked throughput: **~16 chunks/sec**.

At ~850 effective chars/chunk:

| Document | ~Pages | ~Chunks | Embedding time |
|----------|--------|---------|----------------|
| Short NOTAM | 5 | ~15 | < 1 second |
| Typical FCOM section | 100 | ~300 | ~20 seconds |
| Full FCOM | 1,000 | ~3,000 | ~3 minutes |
| Large manual set | 4,000 | ~12,000 | ~13 minutes |

The heartbeat keeps the worker alive for all of these. The real fix for
speed (and for answers that are semantically correct, not hash-based) is
replacing the placeholder with a real batched embedding API — Voyage AI
is the recommended provider for aviation RAG. That is the next major
technical milestone.

---

## Dead ends — do not retry

- **CORS** was never a Railway infra issue — it was origin mismatch +
  `allow_credentials=True`. Already fixed. Do not touch CORS config.
- **`/query/stream` endpoint** does not exist on the backend. The
  frontend used to try it first (404 on every message). Already removed.
- **`uploaded_by` column** — the documents table column is `uploader_id`.
  Already fixed in document_service.py.
- **BackgroundTasks for ingestion** — FastAPI's background tasks die on
  Railway redeploy. Replaced by the job queue. Do not revert.
- **`allow_credentials=True`** — causes silent preflight failures with
  specific origins in this Starlette version. It is False. Do not change.
