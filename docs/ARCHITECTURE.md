# CrewBrief — Architecture Reference

_Last updated: 2026-06-14. Records technical decisions and growth planning. Not consumed at runtime — a project record alongside the operating instructions._

## Correction history
- Earlier versions stated the **Claude API** handled chunking and embedding. That was wrong — the Claude API has no embedding endpoint. What actually ran was a deterministic hash-based placeholder in `embedding_service.py`.
- A subsequent revision selected **Google Cloud `gemini-embedding-001`** (Vertex / "Gemini Enterprise Agent Platform") as the embedding provider. That choice was **blocked in practice** (see Embedding Provider — Decision) and has been replaced by a self-hosted model.
- The embedding provider is now **self-hosted** and keyless.

## Stack
| Component | Service | Rationale |
|---|---|---|
| Frontend | Vercel | Free for personal non-commercial use, auto-deploy from GitHub, global CDN |
| Backend | Railway | Always-on Python services, no serverless timeout risk, handles large manual processing |
| Database & Storage | Supabase | PostgreSQL + pgvector, file storage, and auth in one platform |
| Answer generation + vision | Anthropic Claude API | Contextual generation and citation grounding; image/diagram summarization. Commercial API terms — no training on inputs/outputs by default |
| Embedding | **Self-hosted `nomic-ai/nomic-embed-text-v1.5-Q` via fastembed (ONNX, CPU)** | Real semantic vectors with zero third-party exposure. Runs inside the Railway worker/API; no API, no key, no data leaves own infrastructure. Wrapped behind a provider adapter so it can be swapped in one file |

## AI provider abstraction
Two independent, separately swappable layers:
- **Answer generation (LLM):** Anthropic Claude (current). Adapter: `claude_service.py`. Future candidates: Gemini, OpenAI, Mistral, self-hosted.
- **Embedding:** Self-hosted nomic via fastembed (current). Adapter: `embedding_service.py`. Future candidates: Voyage AI, Cohere, Google — or a different local model.

Swapping either layer touches only its adapter file — `document_service.py` and `query_service.py` call stable signatures (`embed_texts`, `embed_query`, `generate_answer`) and never reference a vendor. For embeddings, the model name + dimension are hard-coded constants in `embedding_service.py` (deliberately not env-sourced), so a swap is a single-file edit plus a one-time re-embed and a Supabase column-dimension change to match.

All current LLM usage runs under Anthropic's commercial API terms (no training on inputs/outputs by default). **Embedding involves no third party at all.**

## Data privacy
- Documents stored in Supabase under the user's account.
- **Embedding runs locally** — chunk/query text is turned into vectors inside the Railway services; it is never sent to any embedding provider.
- Only relevant retrieved excerpts are sent to the Claude API per query (for answer generation); the full library is never transmitted in any single call.
- Text sent to Claude is the cleaned chunk body only — identifying metadata (operator, document, revision, section) is stored in separate DB columns, not concatenated into prompts or embedded text.
- Repeating per-page headers/footers (operator name, document codes, supplier markings) are stripped at ingestion before chunking/embedding — privacy plus embedding quality.
- PDF parsing for tables and images runs locally on the Railway worker (pdfplumber / PyMuPDF). Cloud parsing services (LlamaParse, hosted Unstructured) are not used. Any vision summarization of diagrams runs under Claude's no-train commercial terms.

**Trust surface:** the only external AI service touching document-derived text is the Claude API, and only for (a) answer generation from retrieved excerpts and (b) vision summaries of extracted diagrams. Embedding is fully in-house.

## Embedding Provider — Decision
**Decision (2026-06-14): Self-hosted `nomic-embed-text-v1.5-Q` (768-dim, Apache-2.0) via fastembed (ONNX, CPU), run inside the Railway worker/API.**

**Why Google was dropped.** `gemini-embedding-001` was selected for its contractual no-training default, but it proved unreachable on this setup:
- Creating a service-account key is blocked by the org policy `iam.disableServiceAccountKeyCreation` (Google's "secure by default" enforcement on new orgs).
- The keyless alternative, Workload Identity Federation, requires the workload to present a Google-federatable OIDC token. Railway issues no such runtime token (its OIDC is for user login, not workload identity). Standing up a custom OIDC provider to mint JWTs would trade one secret (a key) for another (the IdP signing key) — disproportionate at Stage 1.

**Why self-hosted nomic.**
- **Keyless and free** — no provider account, no credentials, no per-call cost.
- **Maximum data governance** — document and query text never leave own infrastructure during embedding. This is the strongest posture and was the previously-documented fallback.
- **Right-sized quality** — nomic-embed-text-v1.5 is a strong, fully-open model (Apache-2.0; training data + code released). Competitive for English retrieval. Frontier hosted models (Voyage `voyage-3`, Google `gemini-embedding-001`) score marginally higher on RAG benchmarks, but at current scale (one A320 fleet, single user, English manuals) retrieval quality is not the bottleneck.
- **768-dim** matches the planned Supabase `vector(768)` column and pgvector index — no dimension headache. 8192-token context comfortably covers chunk sizes. The quantized `-Q` build is ~130 MB — light on Railway disk/RAM.

**Implementation.**
- `fastembed==0.8.0` (`TextEmbedding`). `passage_embed()` for stored chunks (applies nomic's `search_document:` prefix); `query_embed()` for questions (`search_query:` prefix). Matching prefixes is what makes retrieval accurate.
- Model name + dim are hard-coded in `embedding_service.py`; `scripts/predownload_model.py` (run by `railway.toml` buildCommand) bakes the model into the image at build time so it isn't re-downloaded each deploy. Cache: `<backend>/.fastembed_cache`.

**Revisit if:** retrieval precision becomes a real bottleneck or document volume grows substantially → benchmark current Voyage/Google models on the MTEB/BEIR leaderboard and swap the single adapter file (plus re-embed + column re-dimension).

## Dimensionality / pgvector note
The Supabase column dimension must match the model exactly. nomic outputs **768**, well within pgvector's ~2000-dim HNSW/IVFFlat index limit. `document_chunks.embedding` is `vector(768)` with a single ivfflat cosine index (`idx_chunks_embedding`). Switching providers later requires re-embedding the library and recreating the index — a planned one-time migration, not a blocker.

## Multi-tenancy
Every document, session, query, and user record carries an `organization_id` from day one. Inactive at single-user scale but ensures multi-org expansion needs no data-model rebuild.

## Cost structure
| Stage | Users | Est. monthly cost |
|---|---|---|
| Personal project | 1 | ~$8 |
| Small group | 10 | ~$25 |
| Department | 30 | ~$75 |
| Organization | 50 | ~$120 |
| Large org | 100 | ~$240 |

**Embeddings now cost $0 in API terms** (self-hosted; they consume Railway CPU/RAM instead). The matrix is driven by Claude answer generation (Sonnet at $3/$15 per M input/output tokens) plus infrastructure step-changes (Supabase Pro, Railway scaling). Prompt caching can trim the Claude line at higher query volume. Re-embedding the whole library on a provider switch is free (local compute).

## Tables & diagrams — ingestion strategy (roadmap)
Aviation manuals (FCOM, QRH, MEL/DDG) are table- and diagram-heavy. The pipeline routes content by type rather than flattening every page to prose:
- **Prose** → standard chunker.
- **Tables** → structure-aware extraction to Markdown (pdfplumber), headers/row-column relationships preserved. Large tables split by row groups with the header repeated. Claude reads Markdown tables natively; nomic embeds the Markdown.
- **Diagrams/images** → extract with PyMuPDF, summarize with **Claude vision** (in-ecosystem; the only external AI touching the image), embed the text summary with nomic, store the original image path in a Supabase column.

Schema additions (done): `document_chunks.chunk_type` (text|table|image) and `image_path` (nullable). Embedded content remains text only. Hybrid image-at-query-time (attach the original image to Claude for higher-fidelity answers) is optional per query. Phasing: tables first, diagrams second, hybrid last. Not required for Stage 1.

_Note: an earlier draft suggested Gemini Flash for vision. Google is out of the stack entirely now — vision uses Claude._

## Developer notes — cross-session invalidation
The LLM can't track which past sessions referenced which chunks; this is a backend responsibility:
- Each stored session records the chunk IDs (and doc/rev/section) used in its answer.
- On a new document version, ingestion diffs old vs new and lists deleted/modified chunks (recommended: section-level metadata diffing over raw chunk diffing).
- Affected sessions are flagged; on reopen, the backend injects an invalidation block into the system prompt so the LLM renders the ⛔ invalidated-reference notice.

## match_chunks note
Two overloaded `match_chunks` functions exist. The live query path (`query_service.py`) calls the **3-arg** version (`query_embedding, match_organization_id, match_count`) by argument names — it returns `chunk_type`/`image_path`. The 5-arg filtering version is effectively unused. Minor: the 3-arg version omits `section_title`, so citation section labels are empty on the RPC path — add `dc.section_title` to that function if wanted.

## Growth path
- **Stage 1 (current):** personal project, single user, A320 fleet, Royal Jordanian.
- **Stage 2:** multiple users, single org, role-based filtering active.
- **Stage 3:** multi-org with enforced data isolation via existing `organization_id` tagging.

## Operating instructions (carried forward)
- **No guessing on third-party UI or APIs** — search official docs first; if uncertain, say so or ask for a screenshot. Same for CLI commands, endpoints, config syntax, library APIs.
- **Brief learning descriptions** — explain each step, including debugging.
- **End-of-session handoff** — on "handoff"/"end session," produce the structured brief (under 400 words) defined in PROJECT_INSTRUCTIONS.md.
- **Start of session** — if a handoff brief is pasted or "fetch STATUS.md" is requested, load it first and confirm.
