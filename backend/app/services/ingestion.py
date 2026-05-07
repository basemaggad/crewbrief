import hashlib
import re
from pypdf import PdfReader
from anthropic import Anthropic
from app.db.client import supabase_admin
from app.core.config import settings

anthropic = Anthropic(api_key=settings.anthropic_api_key)

def extract_text_from_pdf(file_bytes: bytes) -> list[dict]:
    """Extract text from each page of a PDF (Portable Document Format) file."""
    import io
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append({"page_number": i + 1, "text": text})
    return pages

def chunk_pages(pages: list[dict], chunk_size: int = 800, overlap: int = 100) -> list[dict]:
    """
    Split pages into overlapping chunks for embedding.
    Overlap ensures context is not lost at chunk boundaries —
    like ensuring a procedure step is never split across two pages
    without repeating the heading.
    """
    chunks = []
    chunk_index = 0
    current_text = ""
    current_page_start = None
    current_page_end = None

    for page in pages:
        page_num = page["page_number"]
        text = page["text"]

        if current_page_start is None:
            current_page_start = page_num

        current_text += f"\n{text}"
        current_page_end = page_num

        words = current_text.split()
        while len(words) >= chunk_size:
            chunk_words = words[:chunk_size]
            chunk_text = " ".join(chunk_words)
            section_title = extract_section_title(chunk_text)
            content_hash = hashlib.sha256(chunk_text.encode()).hexdigest()

            chunks.append({
                "chunk_index": chunk_index,
                "content": chunk_text,
                "section_title": section_title,
                "page_start": current_page_start,
                "page_end": current_page_end,
                "content_hash": content_hash,
                "token_count": len(chunk_words),
            })
            chunk_index += 1
            words = words[overlap:]
            current_text = " ".join(words)
            current_page_start = current_page_end

    if current_text.strip():
        chunk_text = current_text.strip()
        content_hash = hashlib.sha256(chunk_text.encode()).hexdigest()
        chunks.append({
            "chunk_index": chunk_index,
            "content": chunk_text,
            "section_title": extract_section_title(chunk_text),
            "page_start": current_page_start,
            "page_end": current_page_end,
            "content_hash": content_hash,
            "token_count": len(chunk_text.split()),
        })

    return chunks

def extract_section_title(text: str) -> str | None:
    """
    Attempt to detect a section heading at the start of a chunk.
    Looks for patterns like '3.4 Engine Start' or 'NORMAL PROCEDURES'.
    """
    lines = text.strip().split("\n")
    for line in lines[:5]:
        line = line.strip()
        if re.match(r"^[\d\.]+\s+[A-Z]", line) or (line.isupper() and len(line) > 4):
            return line[:120]
    return None

def embed_text(text: str) -> list[float]:
    """
    Generate a vector embedding for a chunk of text using Claude.
    A vector embedding (list of 1536 floating point numbers) represents
    the semantic meaning of the text — similar meaning = similar numbers.
    This is what makes semantic search possible.
    """
    response = anthropic.messages.create(
        model="claude-opus-4-5",
        max_tokens=1,
        messages=[{"role": "user", "content": text}],
        system="Return only a JSON array of 1536 floats representing the embedding. No other text.",
    )
    import json
    return json.loads(response.content[0].text)

def ingest_document(
    organization_id: str,
    document_id: str,
    version_id: str,
    file_bytes: bytes,
) -> int:
    """
    Full ingestion pipeline:
    1. Extract text from PDF
    2. Split into overlapping chunks
    3. Embed each chunk
    4. Store chunks in the database
    Returns the number of chunks created.
    """
    supabase_admin.table("document_versions").update(
        {"ingestion_status": "processing"}
    ).eq("id", version_id).execute()

    try:
        pages = extract_text_from_pdf(file_bytes)
        chunks = chunk_pages(pages)

        for chunk in chunks:
            embedding = embed_text(chunk["content"])
            supabase_admin.table("document_chunks").insert({
                "organization_id": organization_id,
                "document_id": document_id,
                "document_version_id": version_id,
                "chunk_index": chunk["chunk_index"],
                "section_title": chunk["section_title"],
                "page_start": chunk["page_start"],
                "page_end": chunk["page_end"],
                "content_hash": chunk["content_hash"],
                "content": chunk["content"],
                "token_count": chunk["token_count"],
                "embedding": embedding,
            }).execute()

        supabase_admin.table("document_versions").update(
            {"ingestion_status": "complete"}
        ).eq("id", version_id).execute()

        return len(chunks)

    except Exception as e:
        supabase_admin.table("document_versions").update(
            {"ingestion_status": "failed", "ingestion_error": str(e)}
        ).eq("id", version_id).execute()
        raise
