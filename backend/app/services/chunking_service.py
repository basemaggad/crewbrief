"""
Chunking service — splits content items from pdf_service.extract_content()
into database-ready chunk records.

Routing:
  text  → split by characters with overlap (existing _split_text logic)
  table → one chunk per Markdown block (already row-limited by pdf_service)
  image → one chunk per image (bytes kept for document_service to upload + summarize)

Output keys per chunk:
  type          str              "text" | "table" | "image"
  content       str              prose / Markdown table / "" (image — filled later)
  page_start    int
  page_end      int
  position      int              ordinal within the document (0-indexed, for ordering)
  image_bytes   bytes | None
  image_ext     str   | None
  image_idx     int   | None
"""

from typing import List, Dict, Any, Optional
from app.core.config import settings


def chunk_content_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert the typed content list from pdf_service.extract_content() into
    flat chunk records ready for embedding and database insertion.
    """
    chunks: List[Dict[str, Any]] = []
    position = 0

    for item in items:
        t = item["type"]
        page = item["page"]

        if t == "text":
            for fragment in _split_text(item["content"]):
                chunks.append({
                    "type":        "text",
                    "content":     fragment,
                    "page_start":  page,
                    "page_end":    page,
                    "position":    position,
                    "image_bytes": None,
                    "image_ext":   None,
                    "image_idx":   None,
                })
                position += 1

        elif t == "table":
            # Already split to ≤25-row groups by pdf_service — keep as-is
            chunks.append({
                "type":        "table",
                "content":     item["content"],
                "page_start":  page,
                "page_end":    page,
                "position":    position,
                "image_bytes": None,
                "image_ext":   None,
                "image_idx":   None,
            })
            position += 1

        elif t == "image":
            # content is empty here; document_service fills it via vision LLM
            chunks.append({
                "type":        "image",
                "content":     "",
                "page_start":  page,
                "page_end":    page,
                "position":    position,
                "image_bytes": item.get("image_bytes"),
                "image_ext":   item.get("image_ext"),
                "image_idx":   item.get("image_idx"),
            })
            position += 1

    return chunks


# ── Text splitting ────────────────────────────────────────────────────────────

def _split_text(text: str) -> List[str]:
    """
    Split a text block into chunks of approximately CHUNK_SIZE characters
    with CHUNK_OVERLAP overlap. Tries to split on paragraph boundaries (\n\n),
    then sentence boundaries (\n), then hard-cuts at CHUNK_SIZE if needed.
    """
    chunk_size    = settings.CHUNK_SIZE     # default 1000 chars
    chunk_overlap = settings.CHUNK_OVERLAP  # default 150 chars
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # Try to find a paragraph break within the window
        split_pos = text.rfind("\n\n", start, end)
        if split_pos == -1 or split_pos <= start:
            # Fall back to line break
            split_pos = text.rfind("\n", start, end)
        if split_pos == -1 or split_pos <= start:
            # Hard cut
            split_pos = end

        chunk = text[start:split_pos].strip()
        if chunk:
            chunks.append(chunk)
        # Move forward, backing up by overlap so context bleeds into the next chunk
        start = max(split_pos - chunk_overlap, start + 1)

    return chunks


# ── Legacy shim ───────────────────────────────────────────────────────────────

def chunk_document(pages: List[tuple]) -> List[Dict[str, Any]]:
    """
    Deprecated — accepts the old (page_num, text) tuple list from extract_pages().
    Converts to content-item format then runs through chunk_content_items().
    Use chunk_content_items() directly for new code.
    """
    items = [
        {"type": "text", "content": text, "page": page_num,
         "image_bytes": None, "image_ext": None, "image_idx": None}
        for page_num, text in pages
    ]
    return chunk_content_items(items)
