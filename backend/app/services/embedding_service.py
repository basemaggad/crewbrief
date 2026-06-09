"""
Embedding service — provider adapter.

This is the ONLY file that knows which embedding provider is in use. The
rest of the system (document_service.py, query_service.py) calls the three
stable functions below and never references a vendor:

    embed_texts(texts)  -> list[list[float]]   # ingestion (batch)
    embed_query(text)   -> list[float]          # query time (single)
    cosine_similarity(a, b) -> float            # in-memory fallback ranking

Current provider: Google Cloud — Gemini Enterprise Agent Platform
(formerly Vertex AI), model `gemini-embedding-001`, accessed through the
Google Gen AI SDK (`google-genai`). Google does not use customer data to
train its foundation models by default.

SDK note (2026-06): the legacy `vertexai.language_models` SDK is removed by
Google after 2026-06-24. This adapter uses the replacement Google Gen AI
SDK (`from google import genai`) with `vertexai=True`, which targets the
same gemini-embedding-001 model on the same aiplatform.googleapis.com
endpoint. Auth is unchanged (Application Default Credentials via the
GOOGLE_APPLICATION_CREDENTIALS service-account JSON).

TO SWAP PROVIDERS LATER (Voyage, Cohere, self-hosted, ...):
  - Reimplement _embed_batch() against the new provider.
  - Keep the function signatures and EMBEDDING_DIM contract identical.
  - Update EMBEDDING_DIM + the Supabase vector() column dimension to match,
    then re-embed the library. Nothing else in the codebase changes.
"""
from typing import List
import math

from app.core.config import settings

# --- Provider SDK (Google Gen AI SDK -> Gemini Enterprise Agent Platform) -----
# Auth comes from the service-account JSON pointed to by the
# GOOGLE_APPLICATION_CREDENTIALS environment variable (Application Default
# Credentials), plus project/location passed to the client below.
from google import genai
from google.genai.types import EmbedContentConfig

# Output vector size. MUST equal the Supabase `document_chunks.embedding`
# vector(N) column. 768 chosen to stay within pgvector's 2000-dim index
# limit (the model's 3072 default cannot be indexed by HNSW/IVFFlat).
EMBEDDING_DIM = settings.EMBEDDING_DIM  # e.g. 768

# Google caps each request at 250 inputs / 20,000 tokens. Keep batches well
# under that; 100 is a safe, simple default.
_MAX_BATCH = 100

_client: "genai.Client | None" = None


def _get_client() -> "genai.Client":
    """Lazily initialise the Google Gen AI client once.

    vertexai=True routes calls to the Gemini Enterprise Agent Platform
    (aiplatform.googleapis.com) using the project/location and the
    service-account credentials from GOOGLE_APPLICATION_CREDENTIALS.
    """
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True,
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        )
    return _client


def _embed_batch(texts: List[str], task_type: str) -> List[List[float]]:
    """
    Embed up to _MAX_BATCH texts in a single request.
    task_type tunes the vector for its use:
      - 'RETRIEVAL_DOCUMENT' for stored chunks
      - 'RETRIEVAL_QUERY'    for user questions
    Matching query/document task types improves retrieval accuracy.
    """
    client = _get_client()
    response = client.models.embed_content(
        model=settings.EMBEDDING_MODEL,
        contents=texts,
        config=EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=EMBEDDING_DIM,
        ),
    )
    # response.embeddings preserves input order; each item has .values
    return [e.values for e in response.embeddings]


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
