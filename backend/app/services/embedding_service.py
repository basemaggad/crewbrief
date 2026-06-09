"""
Embedding service — provider adapter.

This is the ONLY file that knows which embedding provider is in use. The
rest of the system (document_service.py, query_service.py) calls the three
stable functions below and never references a vendor:

    embed_texts(texts)  -> list[list[float]]   # ingestion (batch)
    embed_query(text)   -> list[float]          # query time (single)
    cosine_similarity(a, b) -> float            # in-memory fallback ranking

Current provider: SELF-HOSTED — no third party touches document text.
Model `nomic-ai/nomic-embed-text-v1.5-Q` (quantized, 768-dim, Apache-2.0),
run locally via fastembed's ONNX runtime (CPU, no PyTorch). Embeddings are
computed entirely inside our own Railway services, so no document or query
text ever leaves our infrastructure — the strongest data-governance posture
for the aviation manuals. Keyless by construction (no API credentials).

Why this model: 768-dim matches the Supabase document_chunks.embedding
vector(768) column and pgvector index exactly; 8192-token context comfortably
covers our chunk sizes; quantized build is ~130 MB (light on Railway disk/RAM).

nomic requires task-instruction prefixes. fastembed applies them for us:
  - passage_embed()  -> prepends "search_document:"  (stored chunks)
  - query_embed()    -> prepends "search_query:"     (user questions)
Matching document/query prefixes is what makes retrieval accurate.

TO SWAP PROVIDERS LATER (Voyage, Cohere, Google, ...):
  - Reimplement _embed_batch() against the new provider.
  - Keep the function signatures and EMBEDDING_DIM contract identical.
  - Update EMBEDDING_DIM + the Supabase vector() column dimension to match,
    then re-embed the library. Nothing else in the codebase changes.
"""
from typing import List
import os

from app.core.config import settings

# Self-hosted embedding model (ONNX via fastembed; no network, no credentials).
from fastembed import TextEmbedding

# Output vector size. MUST equal the Supabase `document_chunks.embedding`
# vector(N) column. nomic-embed-text-v1.5 outputs 768 by default, which stays
# within pgvector's 2000-dim HNSW/IVFFlat index limit.
EMBEDDING_DIM = settings.EMBEDDING_DIM  # 768

# Model files cache. Derived from this file's location so the build-time
# pre-download (scripts/predownload_model.py) and the runtime both resolve to
# the SAME directory (<backend>/.fastembed_cache -> /app/.fastembed_cache on
# Railway). Because Nixpacks copies the app dir into the run image, the model
# baked in at build time is already present at runtime — no per-deploy
# re-download. Override with FASTEMBED_CACHE_DIR if needed.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_DIR = os.environ.get("FASTEMBED_CACHE_DIR", os.path.join(_BACKEND_DIR, ".fastembed_cache"))

_model: "TextEmbedding | None" = None


def _get_model() -> "TextEmbedding":
    """Lazily load the ONNX embedding model once per process.

    Loaded on first embed call (not at import) so module import stays cheap
    and the worker/API boot quickly. The model is held in memory thereafter.
    """
    global _model
    if _model is None:
        _model = TextEmbedding(model_name=settings.EMBEDDING_MODEL, cache_dir=_CACHE_DIR)
    return _model


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a list of document chunks (ingestion path). Order preserved.

    Uses passage_embed(), which applies nomic's "search_document:" prefix.
    fastembed batches internally; output order matches input order.
    """
    if not texts:
        return []
    model = _get_model()
    return [vec.tolist() for vec in model.passage_embed(texts)]


def embed_query(text: str) -> List[float]:
    """Embed a single user question (query path).

    Uses query_embed(), which applies nomic's "search_query:" prefix.
    """
    model = _get_model()
    return next(iter(model.query_embed([text]))).tolist()


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """
    Used only by the in-memory retrieval fallback in query_service.py.
    Computes true cosine similarity (does not assume pre-normalised vectors).
    """
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(x * x for x in b) ** 0.5 or 1.0
    return dot / (na * nb)
