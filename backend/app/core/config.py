"""
Centralized configuration loaded from environment variables.
Railway sets these via the dashboard; local dev reads from .env.

Google Cloud credentials
------------------------
Railway has no persistent filesystem, so we can't pre-place a key file.
Instead, store the service-account JSON as a base64-encoded env var:

    GOOGLE_CREDENTIALS_B64=<base64 of the JSON key file>

The block at the bottom of this module decodes it and writes it to
/tmp/gcp_credentials.json, then sets GOOGLE_APPLICATION_CREDENTIALS so
the Google SDK picks it up automatically. Both the API and the worker
import config.py at startup, so the file is always ready before the SDK
is called.
"""
import base64
import logging
import os
import tempfile

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

    # Embedding provider â Google Cloud (Gemini Enterprise Agent Platform)
    # Auth: the block below writes GOOGLE_CREDENTIALS_B64 to a temp file and
    # sets GOOGLE_APPLICATION_CREDENTIALS; the SDK reads it automatically.
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_CLOUD_LOCATION: str = "us-central1"
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    # Output vector size. MUST match the Supabase document_chunks.embedding
    # vector(N) column. Kept <= 2000 so pgvector HNSW/IVFFlat can index it
    # (the model's 3072 default cannot be indexed).
    EMBEDDING_DIM: int = 768

    # Base64-encoded service-account JSON (set this on Railway).
    # Leave empty locally if GOOGLE_APPLICATION_CREDENTIALS already points
    # to a key file on disk.
    GOOGLE_CREDENTIALS_B64: str = ""

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

# ââ Write GCP credentials from env var ââââââââââââââââââââââââââââââââââââ
# Must run at import time so GOOGLE_APPLICATION_CREDENTIALS is set before
# any Google SDK import (e.g. vertexai in embedding_service.py).
if settings.GOOGLE_CREDENTIALS_B64 and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    try:
        creds_json = base64.b64decode(settings.GOOGLE_CREDENTIALS_B64).decode("utf-8")
        creds_path = os.path.join(tempfile.gettempdir(), "gcp_credentials.json")
        with open(creds_path, "w") as _f:
            _f.write(creds_json)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
        log.info("GCP credentials written to %s", creds_path)
    except Exception as _exc:
        log.error("Failed to write GCP credentials from GOOGLE_CREDENTIALS_B64: %s", _exc)
