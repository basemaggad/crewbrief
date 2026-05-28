"""
Document service — three distinct responsibilities:

  create_document_record()   Inserts the `documents` row with
                              status='processing' and returns it. Called
                              synchronously inside the upload request handler.

  enqueue_document()         Inserts the `ingestion_jobs` row so the
                              separate worker process picks it up. Called
                              right after create_document_record().

  process_from_storage()     The actual ingestion pipeline. Called by the
                              worker; it receives the raw PDF bytes already
                              downloaded from storage and runs:
                              extract → chunk → embed → insert → mark ready.

  delete_document()          Removes a document, its chunks, its storage
                              object, and invalidates any sessions that
                              cited it.
"""
import os
import uuid

from app.core.config import settings
from app.db.supabase_client import get_supabase_admin
from app.services.pdf_service import extract_pages
from app.services.chunking_service import chunk_document
from app.services.embedding_service import embed_texts

CHUNK_INSERT_BATCH = 50


# ── Upload path (called from the request handler) ──────────────────────────

def create_document_record(
    filename: str,
    document_type: str,
    revision: str,
    aircraft_type: str,
    organization_id: str,
    uploader_id: str,
    storage_path: str,
) -> dict:
    """
    Insert the documents row and return it.
    storage_path must already be confirmed uploaded before calling this.
    """
    supabase = get_supabase_admin()
    res = supabase.table("documents").insert({
        "name": filename,
        "filename": filename,
        "document_type": document_type,
        "revision": revision or None,
        "aircraft_type": aircraft_type or None,
        "storage_path": storage_path,
        "status": "processing",
        "organization_id": organization_id,
        "uploader_id": uploader_id,
    }).execute()
    if not res.data:
        raise RuntimeError("Failed to insert document row")
    return res.data[0]


def enqueue_document(doc_id: str, organization_id: str) -> dict:
    """
    Create an ingestion_jobs row so the worker picks up the extraction
    pipeline. Returns the job row.
    """
    supabase = get_supabase_admin()
    res = supabase.table("ingestion_jobs").insert({
        "document_id": doc_id,
        "organization_id": organization_id,
        "status": "pending",
    }).execute()
    if not res.data:
        raise RuntimeError("Failed to create ingestion job")
    return res.data[0]


# ── Worker path (called from worker.py) ────────────────────────────────────

def process_from_storage(
    doc_id: str,
    file_bytes: bytes,
    organization_id: str,
) -> None:
    """
    Run the full ingestion pipeline on raw PDF bytes that the worker
    already downloaded from Supabase Storage.

    On success: document.status = 'ready', document.chunk_count = N
    On failure: raises — the worker is responsible for marking the job/
                document as error.
    """
    supabase = get_supabase_admin()

    # 0. Idempotency: clear any chunks left behind by a previous failed or
    #    partial run of this same document, so a retry never duplicates rows.
    supabase.table("document_chunks").delete().eq("document_id", doc_id).execute()

    # 1. Extract text page by page, then release the big buffer.
    pages = extract_pages(file_bytes)
    del file_bytes

    # 2. Chunk
    chunks = chunk_document(pages)
    if not chunks:
        raise RuntimeError("No extractable text in PDF")

    # 3. Embed + insert in batches to cap peak memory on large documents.
    total = 0
    for i in range(0, len(chunks), CHUNK_INSERT_BATCH):
        batch = chunks[i:i + CHUNK_INSERT_BATCH]
        vectors = embed_texts([c["content"] for c in batch])
        rows = [{
            "document_id": doc_id,
            "organization_id": organization_id,
            "content": c["content"],
            "page_start": c.get("page_start"),
            "page_end": c.get("page_end"),
            "position": c.get("position"),
            "embedding": v,
        } for c, v in zip(batch, vectors)]
        supabase.table("document_chunks").insert(rows).execute()
        total += len(rows)

    # 4. Mark ready
    supabase.table("documents").update({
        "status": "ready",
        "chunk_count": total,
    }).eq("id", doc_id).execute()


# ── Delete path ─────────────────────────────────────────────────────────────

def delete_document(doc_id: str, organization_id: str) -> None:
    supabase = get_supabase_admin()

    doc = supabase.table("documents").select("*").eq(
        "id", doc_id
    ).eq("organization_id", organization_id).single().execute()
    if not doc.data:
        return

    storage_path = doc.data.get("storage_path")

    # Identify sessions that referenced this document via citations.
    chunks = supabase.table("document_chunks").select("id").eq("document_id", doc_id).execute()
    chunk_ids = {c["id"] for c in (chunks.data or [])}
    if chunk_ids:
        msgs = supabase.table("session_messages").select("session_id, citations").execute()
        affected_sessions = set()
        for m in (msgs.data or []):
            for c in (m.get("citations") or []):
                if c.get("chunk_id") in chunk_ids:
                    affected_sessions.add(m["session_id"])
                    break
        for sid in affected_sessions:
            supabase.table("session_invalidations").insert({
                "session_id": sid,
                "document_name": doc.data.get("name"),
                "revision": doc.data.get("revision"),
                "message": (
                    "This document was removed or replaced. "
                    "Information from earlier in this session may no longer be current."
                ),
            }).execute()

    # Delete any pending/processing jobs for this document.
    supabase.table("ingestion_jobs").delete().eq("document_id", doc_id).execute()

    # Delete chunks then the document row.
    supabase.table("document_chunks").delete().eq("document_id", doc_id).execute()
    supabase.table("documents").delete().eq("id", doc_id).execute()

    # Best-effort storage cleanup.
    if storage_path:
        try:
            supabase.storage.from_(settings.STORAGE_BUCKET).remove([storage_path])
        except Exception:
            pass
