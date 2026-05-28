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

    # Anthropic
    ANTHROPIC_API_KEY: str
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
    # NOTE: embeddings currently use a deterministic local placeholder
    # (embedding_service.py), so this value is unused until a real
    # embedding provider is wired in. Kept for forward-compatibility.
    EMBEDDING_MODEL: str = "claude-3-haiku-20240307"

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
