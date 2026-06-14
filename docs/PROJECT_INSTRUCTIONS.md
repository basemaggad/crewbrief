# CrewBrief — Development Project Instructions

_Last updated: 2026-06-14_

## What this project is
CrewBrief is an aviation document Q&A system for Royal Jordanian A320 fleet pilots. Pilots ask natural-language questions; the system answers strictly from uploaded aviation manuals, with citations. This Claude.ai project is the **development workspace** — not the production app.

## Current stack
| Component | Service |
|---|---|
| Frontend | Vercel (`crewbrief-six.vercel.app`) |
| Backend | Railway — FastAPI API service (`crewbrief`) + Python worker service (`determined-caring`) |
| Database & Storage | Supabase (PostgreSQL + pgvector + file storage + auth) |
| Answer generation + image vision | Anthropic Claude API (`claude-sonnet-4-20250514`) |
| Embedding | **Self-hosted — `nomic-ai/nomic-embed-text-v1.5-Q` (768-dim, Apache-2.0) via fastembed (ONNX, CPU). Runs inside the Railway services. Keyless — no external API.** |
| Repository | GitHub (`basemaggad/crewbrief`) |

## Key decisions — do not re-debate
- **Embedding provider: self-hosted `nomic-embed-text-v1.5-Q` via fastembed.** Google Cloud (`gemini-embedding-001`) was the prior plan but is **abandoned**: service-account key creation is blocked by the org policy `iam.disableServiceAccountKeyCreation`, and Workload Identity Federation isn't practical on Railway (it issues no Google-federatable workload OIDC token). Self-hosted is keyless, free, and keeps all document text inside own infrastructure — the strongest data-governance posture and the previously-documented fallback.
- **`embedding_service.py` is the single-file provider swap point.** Function signatures (`embed_texts`, `embed_query`, `cosine_similarity`) must be preserved. The model name + dimension are **hard-coded in `embedding_service.py`** (not read from env) so a stray `EMBEDDING_MODEL` deploy variable can never override the provider.
- **EMBEDDING_DIM = 768.** nomic outputs 768 by default — within pgvector's ~2000-dim HNSW/IVFFlat limit. The Supabase `document_chunks.embedding` column is `vector(768)` (migrated 2026-06-14 from a stale `vector(1536)`).
- **Claude API has NO embedding endpoint.** It handles answer generation and image/diagram vision summaries only. Earlier docs that named it (or "Anthropic Claude API") as the embedding provider were wrong.
- **`ANTHROPIC_API_KEY` is the only API key in the system.** Embeddings are keyless. It is required at boot (no default) on **both** Railway services.
- **The `vertexai` Python SDK is dead** (Google removed `vertexai.language_models` after 2026-06-24). A brief interim migration to `google-genai` was also dropped when we went self-hosted. No Google packages remain in `requirements.txt`.
- **Header/footer stripping** lives in `pdf_service.py` — strips operator/supplier banners from page text before chunking and embedding.
- **Metadata separation** — chunk `content` = body text only; document name, revision, operator, section live in separate DB columns. Identifying metadata never enters the embedded text.

## ⚠️ Critical data rule — applies every session
This Claude.ai project runs under **consumer terms**. Real Royal Jordanian operational documents must **never** be uploaded here — only sample, public, or redacted files. The production app is where real documents are handled. (Self-hosted embeddings further mean that, in production, document text never leaves your own infrastructure during embedding.)

## Development rules

**1. No guessing on third-party UIs or APIs.**
Never describe menu paths, button locations, API endpoints, CLI commands, or library method signatures from memory — these change frequently and training data is often stale. Always search official docs first. If uncertain: say so explicitly, or ask the user for a screenshot. Applies to: Supabase, Railway, Vercel, GitHub, Google Cloud, Python packages, and any other tool.

**2. Brief step descriptions.**
This is a learning environment. Provide a brief explanation of each step taken, including debugging — even when the fix is obvious.

**3. Start of session.**
If the user pastes a handoff brief or says "fetch STATUS.md" — read it before doing anything else, then confirm you've read it.

**4. End of session / "handoff" command.**
Produce a structured brief (under 400 words, actionable items only) in this format:

```
## CrewBrief Session Handoff — [date]

### What's working
### What's broken / in progress
### Next concrete step
### Decisions made this session
### Dead ends (don't retry)
### Files touched
```

## Current build state (Stage 1 — personal project, single user)

**Live and working:**
- Frontend (Vercel) ✓
- Backend API + Worker (Railway) — both Online, latest deploy successful ✓
- Job-queue ingestion pipeline (claim_ingestion_job RPC, heartbeat, retries) ✓
- Supabase schema, storage, auth ✓
- **Self-hosted embeddings deployed** — model baked into the image at build, building green ✓
- `document_chunks.embedding` = `vector(768)` with ivfflat cosine index ✓
- `ANTHROPIC_API_KEY` set on both services ✓

**Pending:**
- **End-to-end test** — upload a PDF, confirm PROCESSING → ready with chunk_count > 0 and a cited answer. Only remaining verification for Stage 1.
- **Clean up** the orphan "OM-A 8.1.7 fuel policy.pdf" document (stuck `processing`, no job, 0 chunks).

## Dead ends — do not retry
- Google Cloud embeddings / service-account keys — blocked by org policy `iam.disableServiceAccountKeyCreation`. WIF on Railway — not feasible (no workload OIDC token).
- Stale Railway `EMBEDDING_MODEL` env var (value `Uhqqz1vtciDYUh1r9kID`) — overrode the model and broke the build predownload. Model is now hard-coded; the leftover var is ignored (`Settings(extra="ignore")`). Don't reintroduce an env-sourced model name.
- `/query/stream` endpoint — does not exist; don't add without building it.
- `BackgroundTasks` for ingestion — replaced by job queue; do not revert.
- `allow_credentials=True` in CORS — silent preflight failures; keep `False`.
- `001_initial_schema.sql` — directory dump, not SQL; ignore.
- `backend/app/services/ingestion.py` and `retrieval.py` — dead files; safe to delete.

## Architecture reference
Full technical record, provider rationale, embedding decision, cost matrix, and roadmap are in `docs/ARCHITECTURE.md`. Check it before re-deriving any technical decision.
