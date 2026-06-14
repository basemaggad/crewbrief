# CrewBrief Session Handoff — June 14, 2026

## What's working
- Frontend live (Vercel) — crewbrief-six.vercel.app
- Backend API + Worker live (Railway) — `crewbrief` and `determined-caring`, both Online, latest deploy successful
- Supabase schema, storage, auth, job-queue ingestion pipeline (claim_ingestion_job RPC, heartbeat, retries)
- **Embeddings are now real and self-hosted** (see Decisions) — deployed and building green
- Answer generation: Anthropic Claude API (`ANTHROPIC_API_KEY` set on both services — required at boot)

## Embedding stack (NEW — replaces the old Google plan)
- **Provider: SELF-HOSTED. No external embedding API, no key.** Model runs inside the Railway services.
- Model: **`nomic-ai/nomic-embed-text-v1.5-Q`** (quantized, 768-dim, Apache-2.0) via **fastembed** (ONNX, CPU, no PyTorch).
- Model name + dimension are **hard-coded** in `embedding_service.py` (and `scripts/predownload_model.py`), NOT read from env, so a stray deploy variable can't override them.
- Model is **baked into the image at build time** (`scripts/predownload_model.py` run by `railway.toml` buildCommand) → no per-deploy re-download. Cache: `<backend>/.fastembed_cache`.
- `passage_embed()` for chunks (`search_document:` prefix) / `query_embed()` for questions (`search_query:` prefix).
- Supabase `document_chunks.embedding` column = **`vector(768)`** with a single ivfflat cosine index (`idx_chunks_embedding`). Migration applied 2026-06-14.

## What's broken / in progress
- **End-to-end test not yet run** — need to upload a PDF and confirm PROCESSING → ready with chunk_count > 0 and a cited answer. This is the only remaining verification.
- **Orphan document** — "OM-A 8.1.7 fuel policy.pdf" stuck in `processing` since 2026-06-09 with no ingestion job, no version, 0 chunks. Harmless but should be deleted for a clean documents list.

## Next concrete step
Upload a small/sample PDF via the frontend → watch document_chunks fill with 768-dim vectors → confirm document reaches `ready` → ask a question and verify the citation.

## Decisions made (do not re-debate)
- **Embedding provider = self-hosted nomic via fastembed.** Google Cloud (gemini-embedding-001) was the prior plan but **service-account key creation is blocked by the org policy `iam.disableServiceAccountKeyCreation`**, and Workload Identity Federation is not practical on Railway (Railway issues no Google-federatable workload OIDC token). Self-hosted is keyless, costs nothing, and keeps all document text inside own infra — the strongest data-governance posture and the previously-documented fallback.
- **The `vertexai` Python SDK is dead** (Google removed `vertexai.language_models` after 2026-06-24). Its short-lived replacement `google-genai` was also dropped when we went self-hosted. `requirements.txt` now pins `fastembed==0.8.0`; no google packages remain.
- **EMBEDDING_DIM = 768** unchanged from the original plan (nomic outputs 768 by default), so the Supabase column dimension plan held — only a 1536→768 correction was needed (the column had been left at 1536).
- **Claude API has NO embedding endpoint** — it handles answer generation + image/diagram vision summaries only. (Unchanged.)
- **Only one API key in the system: `ANTHROPIC_API_KEY`.** Embeddings are keyless.

## Dead ends (don't retry)
- Google Cloud embeddings / service-account keys — blocked by org policy. WIF on Railway — not feasible.
- Stale Railway `EMBEDDING_MODEL` env var (junk value `Uhqqz1vtciDYUh1r9kID`) — it overrode the model name and broke the build predownload. Fixed by hard-coding the model in code; the leftover var is now ignored (`Settings(extra="ignore")`). Don't reintroduce an env-sourced model name.
- `/query/stream` endpoint — does not exist; don't add without building it.
- `BackgroundTasks` for ingestion — replaced by job queue; do not revert.
- `allow_credentials=True` in CORS — silent preflight failures; keep False.
- `001_initial_schema.sql` — directory dump, not SQL; ignore.
- `backend/app/services/ingestion.py` and `retrieval.py` — dead files (retrieval.py still calls match_chunks but is imported by nothing live); safe to delete.

## Open notes (not blockers)
- Two overloaded `match_chunks` functions exist. The live query path (`query_service.py`) calls the **3-arg** version (returns `chunk_type`/`image_path`) by argument names; the 5-arg version is effectively unused. Minor: the 3-arg version does not return `section_title`, so the citation "section" field is empty on the RPC path — add `dc.section_title` to that function if section labels are wanted.

## Files touched this session
- `backend/app/services/embedding_service.py` — rewritten to fastembed + nomic; model/dim hard-coded
- `backend/app/core/config.py` — removed all GCP settings + credential block + embedding env settings
- `backend/requirements.txt` — `fastembed==0.8.0` (dropped google packages)
- `backend/scripts/predownload_model.py` — new; build-time model bake
- `backend/railway.toml` — buildCommand for predownload
- `backend/.gitignore` — `.fastembed_cache/`
- Supabase — `document_chunks.embedding` → `vector(768)`, single ivfflat index
