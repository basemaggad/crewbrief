"""
Centralized configuration loaded from environment variables.
Railway sets these via the dashboard; local dev reads from .env.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_ANON_KEY: str
    SUPABASE_JWT_SECRET: str

    # Anthropic (answer generation + vision summarization)
    ANTHROPIC_API_KEY: str
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"

    # Embedding provider — Google Cloud (Gemini Enterprise Agent Platform)
    # Auth: set GOOGLE_APPLICATION_CREDENTIALS to the service-account JSON path
    # (read automatically by the Google SDK; not declared as a field here).
    # Empty string disables the provider at startup; a missing value would
    # previously crash the app on import — this default prevents that.
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_CLOUD_LOCATION: str = "us-central1"
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    # Output vector size. MUST match the Supabase document_chunks.embedding
    # vector(N) column. Kept <= 2000 so pgvector HNSW/IVFFlat can index it
    # (the model's 3072 default cannot be indexed).
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
