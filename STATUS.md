# CrewBrief Session Handoff — May 28, 2026

## What's working
- Frontend live at crewbrief-six.vercel.app
- Backend live at crewbrief-production.up.railway.app
- `/health` returns `{"status":"ok","service":"crewbrief-api"}`
- JWT auth working — ES256 JWKS verification via PyJWT
- CORS fully resolved — all preflights return 200
- Supabase permissions fixed — service_role granted on all tables
- Sessions and Documents endpoints both returning 200
- Full end-to-end request flow working (frontend → backend → Supabase)

## What was built this session
All code is written, tested (compile-checked), and ready to deploy.
Not yet pushed to GitHub or live. See IMPLEMENTATION_GUIDE.md for
the exact deploy sequence.

### Bug fixes (all frontend + backend)
- **Auth 403 on every request** — `auth.py` looked up `users.organization_id` but the
  `users` profile table likely doesn't exist. `fixes_migration.sql` creates it,
  backfills profiles for existing auth users, and adds a trigger for new signups.
- **`uploaded_by` column mismatch** — `document_service.py` was inserting `uploaded_by`
  but the migrated schema column is `uploader_id`. Fixed.
- **Broken `/query/stream`** — `ChatPage.js` attempted streaming first, hit a 404
  (no such endpoint), then fell back to `/query`. Wasted one round-trip per message.
  Removed — calls `/query` directly.
- **Sidebar doesn't show new sessions** — `Sidebar.js` loaded sessions once on
  mount. A session created from the chat empty-state never appeared. Fixed to
  reload on route change.
- **Fleet label hardcoded "A320 fleet"** — `DocumentsPage.js` now derives the label
  from the actual `aircraft_type` values across documents.
- **Document UI stuck on PROCESSING** — no polling. Now polls every 4s whenever
  any document has status `processing`.

### Architecture: job queue for document ingestion
Replaced FastAPI `BackgroundTasks` (dies on Railway redeploy) with a proper
Supabase-backed job queue:

| Component | Change |
|-----------|--------|
| `documents.py` (route) | Streams PDF → temp file → Storage; creates document row + job row; returns immediately |
| `document_service.py` | Split: `create_document_record` + `enqueue_document` + `process_from_storage` + `delete_document` |
| `worker.py` | **New.** Separate Railway service; polls `ingestion_jobs`; retries up to 3×; heartbeat thread |
| `config.py` | `MAX_UPLOAD_MB = 500` |
| `job_queue_migration.sql` | `ingestion_jobs` table; `claim_ingestion_job()` RPC; error-sync trigger |
| `fixes_migration.sql` | `users` + `organizations` tables; Storage bucket 500 MB limit |

### Key reliability properties of the job queue
- **`FOR UPDATE SKIP LOCKED`** in `claim_ingestion_job()` — safe for multiple
  parallel workers, no double-processing
- **Heartbeat thread** — stamps `last_heartbeat_at` every 30s while a job runs;
  stale threshold is 2 min so a legitimately long job is never re-queued mid-flight
- **Idempotent retries** — `process_from_storage()` deletes existing chunks before
  inserting, so a retried job never duplicates vectors
- **Error-sync trigger** — `sync_document_error_status` propagates terminal
  `error` from the job row to the parent document automatically; the worker
  no longer touches the documents table on failure
- **Interruptible idle wait** — `threading.Event.wait()` instead of `time.sleep`;
  worker acknowledges Railway SIGTERM instantly when idle

## Next concrete steps (in order)

### 1. Deploy (follow IMPLEMENTATION_GUIDE.md)
1. Supabase SQL Editor → run `fixes_migration.sql` → verify 0 profiles missing org
2. Supabase SQL Editor → run `job_queue_migration.sql` → verify both routines appear
3. Push all code files to GitHub → wait for Railway + Vercel deploys
4. Railway → create worker service (root=`backend`, start=`python worker.py`,
   no port, copy all env vars from API service)
5. Test upload: drop a small PDF → watch worker logs → confirm UI flips to READY

### 2. First real test (after deploy)
- Upload a small aviation PDF (a few MB)
- Confirm status flips PROCESSING → READY in the UI without a page refresh
- Ask a question in Chat that the document can answer
- Verify a citation appears below the response

### 3. Clean up stuck documents
Any documents from before this deploy are stuck on PROCESSING. Run the
cleanup SQL in IMPLEMENTATION_GUIDE.md Step 5.

### 4. Next major milestone — real embeddings
The current `embedding_service.py` uses deterministic hash-based
placeholder embeddings at ~16 chunks/sec. Two consequences:
  - Large PDFs take minutes to ingest (tolerable with the heartbeat)
  - Query answers are retrieved by hash similarity, not semantic meaning
    (fundamentally broken for real use)

Replace with a real batched embedding API. Voyage AI (voyage-3) is the
recommended provider for aviation RAG — 1B tokens/min throughput would
reduce a 3-minute embed to under 1 second and make retrieval semantically
correct.

## Decisions made
- `allow_credentials=False` — correct for JWT Bearer auth, not cookie auth. Do not change.
- CORS origins hardcoded in `main.py` — removes env var indirection risk. Do not change.
- `BackgroundTasks` removed — dies on Railway redeploy. Job queue is permanent.
- Page cap NOT added — silently truncating an aircraft manual is the wrong failure
  mode. Heartbeat handles long-running jobs safely. Cap only if a real embedding
  API is still too slow after integration.
- Error propagation via DB trigger, not worker code — single source of truth,
  works regardless of which code path fails the job.

## Dead ends — do not retry
- CORS: never a Railway infra issue — origin mismatch + `allow_credentials=True`.
- `/query/stream` endpoint does not exist. Do not add it unless streaming is
  explicitly built in the backend query route.
- `uploaded_by` column name — it is `uploader_id`. Already fixed.
- `BackgroundTasks` for ingestion — replaced. Do not revert.
- `allow_credentials=True` — silent preflight failures in this Starlette version.
- CORS debugging from the backend without curl first.
- `001_initial_schema.sql` in the repo is a directory-tree dump, not SQL. The
  real live schema was set up via SQL Editor. Don't trust that file.

## Files changed this session

### New files
- `backend/worker.py`
- `backend/job_queue_migration.sql`
- `backend/fixes_migration.sql`
- `backend/IMPLEMENTATION_GUIDE.md`
- `STATUS.md` (this file)

### Updated backend
- `backend/app/api/routes/documents.py`
- `backend/app/services/document_service.py`
- `backend/app/core/config.py`

### Updated frontend
- `frontend/src/pages/DocumentsPage.js`
- `frontend/src/pages/ChatPage.js`
- `frontend/src/components/Sidebar.js`

### Unchanged (reference)
- `backend/main.py` — CORS hardcoded, routes registered
- `backend/app/core/auth.py` — ES256 JWKS via PyJWT
- `backend/app/api/routes/sessions.py`
- `backend/app/api/routes/query.py`
- `backend/app/services/query_service.py`
- `backend/app/services/claude_service.py`
- `backend/app/services/embedding_service.py` — placeholder, to be replaced
- `backend/app/services/pdf_service.py`
- `backend/app/services/chunking_service.py`
