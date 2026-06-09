"""
Centralized configuration loaded from environment variables.
Railway sets these via the dashboard; local dev reads from .env.

Embeddings are self-hosted (fastembed/ONNX, see embedding_service.py), so no
cloud embedding credentials are required — the model runs inside our own
services and no document text leaves our infrastructure.
"""
import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_ANON_KEY: str
    SUPABASE_JWT_SECRET: str

    # Anthropic (answer generation + vision summarization)
    ANTHROPIC_API_KEY: str
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"

    # Embedding provider — self-hosted via fastembed (ONNX, runs locally).
    # No credentials. The model files are cached on disk (baked into the
    # Railway image at build time by scripts/predownload_model.py).
    EMBEDDING_MODEL: str = "nomic-ai/nomic-embed-text-v1.5-Q"
    # Output vector size. MUST match the Supabase document_chunks.embedding
    # vector(N) column. nomic-embed-text-v1.5 outputs 768 by default, within
    # pgvector's 2000-dim HNSW/IVFFlat index limit.
    EMBEDDING_DIM: int = 768

    # CORS
    FRONTEND_ORIGIN: str = ""

    # Storage
    STORAGE_BUCKET: str = "documents"
    MAX_UPLOAD_MB: int = 500         # per-file PDF upload limit

    # Chunking
    CHUNK_SIZE: int = 1000           # characters per chunk (target)
    CHUNK_OVERLAP: int = 150         # characters of overlap between chunks
    MAX_CHUNKS_PER_QUERY: int = 8    # top-K retrieval per question

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
