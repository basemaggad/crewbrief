"""
Embedding service — provider adapter.

This is the ONLY file that knows which embedding provider is in use. The
rest of the system (document_service.py, query_service.py) calls the three
stable functions below and never references a vendor:

    embed_texts(texts)  -> list[list[float]]   # ingestion (batch)
    embed_query(text)   -> list[float]          # query time (single)
    cosine_similarity(a, b) -> float            # in-memory fallback ranking

Current provider: Google Cloud — Gemini Enterprise Agent Platform
(formerly Vertex AI), model `gemini-embedding-001`. Google does not use
customer data to train its foundation models by default.

TO SWAP PROVIDERS LATER (Voyage, Cohere, self-hosted, ...):
  - Reimplement _embed_batch() against the new provider.
  - Keep the function signatures and EMBEDDING_DIM contract identical.
  - Update EMBEDDING_DIM + the Supabase vector() column dimension to match,
    then re-embed the library. Nothing else in the codebase changes.

VERIFY BEFORE DEPLOY: the platform was rebranded recently. Confirm the
import path and method names below against the current Google Cloud
"Get text embeddings" documentation; the SDK surface is the most likely
thing to have shifted.
"""
from typing import List
import math

from app.core.config import settings

# --- Provider SDK (Google Cloud / Gemini Enterprise Agent Platform) ----------
# Auth comes from the service-account JSON pointed to by the
# GOOGLE_APPLICATION_CREDENTIALS environment variable, plus project/location.
import vertexai
from vertexai.language_models import TextEmbeddingModel, TextEmbeddingInput

# Output vector size. MUST equal the Supabase `document_chunks.embedding`
# vector(N) column. 768 chosen to stay within pgvector's 2000-dim index
# limit (the model's 3072 default cannot be indexed by HNSW/IVFFlat).
EMBEDDING_DIM = settings.EMBEDDING_DIM  # e.g. 768

# Google caps each request at 250 inputs / 20,000 tokens. Keep batches well
# under that; 100 is a safe, simple default.
_MAX_BATCH = 100

_model: TextEmbeddingModel | None = None


def _get_model() -> TextEmbeddingModel:
    """Lazily initialise the Vertex client and load the embedding model once."""
    global _model
    if _model is None:
        vertexai.init(
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        )
        _model = TextEmbeddingModel.from_pretrained(settings.EMBEDDING_MODEL)
    return _model


def _embed_batch(texts: List[str], task_type: str) -> List[List[float]]:
    """
    Embed up to _MAX_BATCH texts in a single request.
    task_type tunes the vector for its use:
      - 'RETRIEVAL_DOCUMENT' for stored chunks
      - 'RETRIEVAL_QUERY'    for user questions
    Matching query/document task types improves retrieval accuracy.
    """
    model = _get_model()
    inputs = [TextEmbeddingInput(text=t, task_type=task_type) for t in texts]
    results = model.get_embeddings(inputs, output_dimensionality=EMBEDDING_DIM)
    return [r.values for r in results]


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a list of document chunks (ingestion path). Order preserved."""
    out: List[List[float]] = []
    for i in range(0, len(texts), _MAX_BATCH):
        batch = texts[i:i + _MAX_BATCH]
        out.extend(_embed_batch(batch, task_type="RETRIEVAL_DOCUMENT"))
    return out


def embed_query(text: str) -> List[float]:
    """Embed a single user question (query path)."""
    return _embed_batch([text], task_type="RETRIEVAL_QUERY")[0]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """
    Used only by the in-memory retrieval fallback in query_service.py.
    Computes true cosine similarity (does not assume pre-normalised vectors).
    """
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)
