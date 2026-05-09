# CrewBrief Backend

FastAPI backend powering the CrewBrief aviation document Q&A system.

## What this backend does

When a pilot uploads a manual (PDF), the backend:
1. Stores it in Supabase Storage
2. Extracts text page by page
3. Splits the text into overlapping chunks
4. Embeds each chunk into a vector
5. Saves the chunks with their vectors in the database

When a pilot asks a question, the backend:
1. Embeds the question
2. Finds the most relevant chunks (cosine similarity)
3. Sends the question + relevant chunks to Claude
4. Returns the answer with citations
5. Saves the conversation in the session history

## API endpoints

| Method | Path | Description |
|---|---|---|
| GET    | `/health`              | Health check |
| GET    | `/documents`           | List documents in your org |
| POST   | `/documents/upload`    | Upload PDF (multipart form) |
| DELETE | `/documents/{id}`      | Remove document, mark sessions invalidated |
| GET    | `/sessions`            | List your sessions |
| POST   | `/sessions`            | Create a new session |
| GET    | `/sessions/{id}`       | Get session + messages + invalidations |
| DELETE | `/sessions/{id}`       | Delete session |
| POST   | `/query`               | Ask a question in a session |

All routes except `/health` require a Supabase JWT in the `Authorization: Bearer ...` header. The frontend handles this automatically.

## Project structure

```
backend/
  main.py                       — FastAPI entry point
  requirements.txt
  Procfile                      — Railway start command
  railway.toml                  — Railway build config
  supabase_migration.sql        — extra DB objects (RPC, indexes)
  .env.example                  — required env vars
  app/
    core/
      config.py                 — env settings
      auth.py                   — JWT verification
    db/
      supabase_client.py        — Supabase admin client
    models/
      schemas.py                — Pydantic request/response shapes
    services/
      pdf_service.py            — PDF text extraction
      chunking_service.py       — text splitting
      embedding_service.py      — vector generation (swappable provider)
      claude_service.py         — Claude API calls + system prompt
      document_service.py       — full ingestion pipeline
      query_service.py          — retrieval + answer generation
    api/
      routes/
        health.py
        documents.py
        sessions.py
        query.py
```

## Setup

### 1. Run the SQL migration in Supabase

Open Supabase → SQL Editor → paste the contents of `supabase_migration.sql` → Run.
This creates the `match_chunks` RPC and indexes used by retrieval. Safe to re-run.

### 2. Create a Supabase Storage bucket

In Supabase → Storage → create a bucket named `documents` (private).

### 3. Set Railway environment variables

In Railway dashboard, go to the backend service → Variables, add:

| Key | Where to find it |
|---|---|
| `SUPABASE_URL`               | `https://<project>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY`  | Supabase → Settings → API → `service_role` (secret) |
| `SUPABASE_ANON_KEY`          | Supabase → Settings → API → `anon public` |
| `SUPABASE_JWT_SECRET`        | Supabase → Settings → API → JWT Settings → JWT Secret |
| `ANTHROPIC_API_KEY`          | console.anthropic.com → Settings → API Keys |
| `FRONTEND_ORIGIN`            | `https://crewbrief-six.vercel.app` |
| `STORAGE_BUCKET`             | `documents` |

### 4. Push to GitHub

Railway auto-deploys from the `backend/` folder.

## Local development

```bash
cd backend
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env         # fill in values
uvicorn main:app --reload
```

API will be at `http://localhost:8000` with auto-generated docs at `/docs`.

## Embedding provider swap

The embedding layer lives in `app/services/embedding_service.py` and is intentionally isolated. Current implementation is a deterministic hash-based fallback (1024-dim) for the small initial scale. To swap to Voyage AI or another provider:

1. Replace `embed_texts()` and `embed_query()` to call the new provider.
2. Update `EMBEDDING_DIM` to match the new provider's dimension.
3. Update the vector dimension in `supabase_migration.sql` and re-run.
4. Re-embed existing documents (delete + re-upload, or write a backfill script).

No other files need to change — the rest of the system reads vectors via this single module.
