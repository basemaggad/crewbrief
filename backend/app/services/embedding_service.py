"""
Embedding service.

Abstracted behind a single function so the underlying provider can be
swapped (Voyage AI, OpenAI, etc.) by changing this file only — per the
architecture plan in CrewBrief — Architecture Reference.

Anthropic doesn't currently expose a dedicated embedding endpoint, so
for the initial scale we use a deterministic fallback embedding based on
hashing tokens. This is intentionally simple and serves as a placeholder
that will be replaced with a real embedding API call. The query service
uses cosine similarity over these vectors.

When ready to switch:
- Plug Voyage AI into embed_texts() and adjust the dimension.
- The DB schema's vector column dimension must match.
"""
from typing import List
import hashlib
import math


EMBEDDING_DIM = 1024  # must match the vector(N) column in Supabase pgvector


def _hash_token(token: str, dim: int) -> List[float]:
    """Stable pseudo-random direction for a token, length 1."""
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    # Expand digest to dim floats deterministically.
    out = []
    seed = int.from_bytes(digest[:8], "big")
    for i in range(dim):
        # Linear congruential step
        seed = (seed * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        out.append(((seed >> 33) / float(1 << 31)) - 1.0)  # in [-1, 1)
    norm = math.sqrt(sum(x * x for x in out)) or 1.0
    return [x / norm for x in out]


def _embed_one(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    tokens = [t.lower() for t in text.split() if t.strip()]
    if not tokens:
        return [0.0] * dim
    acc = [0.0] * dim
    for tok in tokens[:512]:  # cap for speed
        v = _hash_token(tok, dim)
        for i in range(dim):
            acc[i] += v[i]
    norm = math.sqrt(sum(x * x for x in acc)) or 1.0
    return [x / norm for x in acc]


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Returns one embedding per input string."""
    return [_embed_one(t) for t in texts]


def embed_query(text: str) -> List[float]:
    return _embed_one(text)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))  # both already L2-normalized
