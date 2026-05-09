"""
Document ingestion pipeline.

Flow when a user uploads a PDF:
1. Save raw PDF to Supabase Storage.
2. Insert a row in `documents` with status='processing'.
3. Extract text page by page.
4. Split into overlapping chunks.
5. Embed each chunk.
6. Insert all chunks into `document_chunks` with embeddings.
7. Update document status to 'ready' and set chunk_count.

If anything fails, the document status is set to 'error'.
"""
import uuid
from typing import Optional

from app.core.config import settings
from app.db.supabase_client import get_supabase_admin
from app.services.pdf_service import extract_pages
from app.services.chunking_service import chunk_document
from app.services.embedding_service import embed_texts


async def ingest_document(
    file_bytes: bytes,
    filename: str,
    document_type: str,
    revision: str,
    aircraft_type: str,
    organization_id: str,
    uploader_id: str,
) -> dict:
    supabase = get_supabase_admin()

    # 1. Upload to storage
    storage_path = f"{organization_id}/{uuid.uuid4()}_{filename}"
    try:
        supabase.storage.from_(settings.STORAGE_BUCKET).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": "application/pdf"},
        )
    except Exception as e:
        # If bucket doesn't exist or upload fails, raise so the route can return 500
        raise RuntimeError(f"Storage upload failed: {e}")

    # 2. Insert document row
    doc_payload = {
        "name": filename,
        "filename": filename,
        "document_type": document_type,
        "revision": revision or None,
        "aircraft_type": aircraft_type or None,
        "storage_path": storage_path,
        "status": "processing",
        "organization_id": organization_id,
        "uploaded_by": uploader_id,
    }
    res = supabase.table("documents").insert(doc_payload).execute()
    if not res.data:
        raise RuntimeError("Failed to insert document row")
    document = res.data[0]
    doc_id = document["id"]

    try:
        # 3. Extract pages
        pages = extract_pages(file_bytes)

        # 4. Chunk
        chunks = chunk_document(pages)

        if not chunks:
            supabase.table("documents").update({
                "status": "error",
                "error_message": "No extractable text in PDF",
            }).eq("id", doc_id).execute()
            document["status"] = "error"
            return document

        # 5. Embed
        texts = [c["content"] for c in chunks]
        vectors = embed_texts(texts)

        # 6. Insert chunks (in batches to avoid huge payloads)
        BATCH = 50
        for i in range(0, len(chunks), BATCH):
            batch_chunks = chunks[i:i + BATCH]
            batch_vectors = vectors[i:i + BATCH]
            rows = []
            for c, v in zip(batch_chunks, batch_vectors):
                rows.append({
                    "document_id": doc_id,
                    "organization_id": organization_id,
                    "content": c["content"],
                    "page_start": c.get("page_start"),
                    "page_end": c.get("page_end"),
                    "position": c.get("position"),
                    "embedding": v,
                })
            supabase.table("document_chunks").insert(rows).execute()

        # 7. Mark ready
        supabase.table("documents").update({
            "status": "ready",
            "chunk_count": len(chunks),
        }).eq("id", doc_id).execute()

        document["status"] = "ready"
        document["chunk_count"] = len(chunks)
        return document

    except Exception as e:
        supabase.table("documents").update({
            "status": "error",
            "error_message": str(e)[:500],
        }).eq("id", doc_id).execute()
        document["status"] = "error"
        return document


def delete_document(doc_id: str, organization_id: str) -> None:
    supabase = get_supabase_admin()

    # Look up storage path & affected sessions before deleting
    doc = supabase.table("documents").select("*").eq("id", doc_id).eq("organization_id", organization_id).single().execute()
    if not doc.data:
        return

    storage_path = doc.data.get("storage_path")

    # Mark sessions that referenced any chunk of this document with invalidation metadata
    chunks = supabase.table("document_chunks").select("id").eq("document_id", doc_id).execute()
    chunk_ids = [c["id"] for c in (chunks.data or [])]
    if chunk_ids:
        # Find sessions whose messages cite these chunks
        # session_invalidations table records (session_id, document_name, revision, message)
        msgs = supabase.table("messages").select("session_id, citations").execute()
        affected_sessions = set()
        for m in (msgs.data or []):
            cits = m.get("citations") or []
            for c in cits:
                if c.get("chunk_id") in chunk_ids:
                    affected_sessions.add(m["session_id"])
                    break
        for sid in affected_sessions:
            supabase.table("session_invalidations").insert({
                "session_id": sid,
                "document_name": doc.data.get("name"),
                "revision": doc.data.get("revision"),
                "message": "This document was removed or replaced. Information from earlier in this session may no longer be current.",
            }).execute()

    # Delete chunks then document
    supabase.table("document_chunks").delete().eq("document_id", doc_id).execute()
    supabase.table("documents").delete().eq("id", doc_id).execute()

    # Delete from storage
    if storage_path:
        try:
            supabase.storage.from_(settings.STORAGE_BUCKET).remove([storage_path])
        except Exception:
            pass
