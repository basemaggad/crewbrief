"""
Pre-download the embedding model at build time.

Run by railway.toml's [build] buildCommand AFTER pip install. fastembed
fetches the model from Hugging Face into <backend>/.fastembed_cache, which
Nixpacks copies into the runtime image — so the model is already present at
runtime and is NOT re-downloaded on every container start.

The cache directory is computed the same way as embedding_service.py
(relative to the backend dir / overridable via FASTEMBED_CACHE_DIR), so build
and runtime always agree on the path.

Kept dependency-light on purpose: it imports only fastembed + os, NOT the app
config, so it runs during the build even if app env vars aren't present yet.
"""
import os

from fastembed import TextEmbedding

MODEL = os.environ.get("EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v1.5-Q")

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.environ.get("FASTEMBED_CACHE_DIR", os.path.join(_BACKEND_DIR, ".fastembed_cache"))


def main() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    print(f"[predownload] fetching '{MODEL}' into '{CACHE_DIR}' ...")
    # Constructing TextEmbedding downloads + extracts the model files.
    TextEmbedding(model_name=MODEL, cache_dir=CACHE_DIR)
    print("[predownload] done.")


if __name__ == "__main__":
    main()
