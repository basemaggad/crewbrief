"""
Chunking — splits document text into overlapping windows for embedding.

Strategy: try to break at paragraph boundaries; if a paragraph is bigger
than CHUNK_SIZE, fall back to sentence then character splits.
Overlap helps the model see context that would otherwise be cut at chunk
boundaries.
"""
from typing import List, Dict
from app.core.config import settings


def _split_text(text: str, size: int, overlap: int) -> List[str]:
    if not text:
        return []
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        # Try to end at a sentence boundary near `end`
        if end < n:
            window = text[start:end]
            for sep in ("\n\n", ". ", "\n", " "):
                idx = window.rfind(sep)
                if idx != -1 and idx > size * 0.5:
                    end = start + idx + len(sep)
                    break
        chunks.append(text[start:end].strip())
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


def chunk_document(pages: List[tuple]) -> List[Dict]:
    """
    Input: list of (page_number, page_text)
    Output: list of dicts: {content, page_start, page_end, position}
    """
    out: List[Dict] = []
    position = 0
    for page_num, text in pages:
        if not text or not text.strip():
            continue
        page_chunks = _split_text(text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
        for c in page_chunks:
            out.append({
                "content": c,
                "page_start": page_num,
                "page_end": page_num,
                "position": position,
            })
            position += 1
    return out
