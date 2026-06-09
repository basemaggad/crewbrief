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

Schema notes (document_chunks):
  document_version_id  NOT NULL — requires a document_versions row first
  chunk_index          ordinal position within the document (replaces "position")
  content_hash         md5 of chunk text — required NOT NULL
  chunk_type           "text" | "table" | "image"  (added by migration)
  image_path           nullable storage path for image-type chunks
"""
import hashlib
import logging

from app.core.config import settings
from app.db.supabase_client import get_supabase_admin
from app.services.pdf_service import extract_content
from app.services.chunking_service import chunk_content_items
from app.services.embedding_service import embed_texts
from app.services.claude_service import summarize_image

logger = logging.getLogger(__name__)

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
        "name":            filename,
        "filename":        filename,
        "document_type":   document_type,
        "revision":        revision or None,
        "aircraft_type":   aircraft_type or None,
        "storage_path":    storage_path,
        "status":          "processing",
        "organization_id": organization_id,
        "uploader_id":     uploader_id,
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
        "document_id":     doc_id,
        "organization_id": organization_id,
        "status":          "pending",
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

    # 0. Idempotency: clear any previous chunks and versions so a retry
    #    never duplicates rows. Chunks first (FK constraint).
    supabase.table("document_chunks").delete().eq("document_id", doc_id).execute()
    supabase.table("document_versions").delete().eq("document_id", doc_id).execute()

    # 1. Look up the document record so we can copy storage metadata into
    #    the new document_versions row.
    doc_res = supabase.table("documents").select(
        "filename, storage_path"
    ).eq("id", doc_id).single().execute()
    doc_meta = doc_res.data or {}

    # 2. Create a document_versions row.
    #    ingestion_status starts as 'processing'; we flip it to 'complete'
    #    at the end.  match_chunks filters dv.ingestion_status = 'complete',
    #    so in-progress ingestions are invisible to queries.
    version_res = supabase.table("document_versions").insert({
        "document_id":     doc_id,
        "organization_id": organization_id,
        "version_label":   "v1",
        "storage_path":    doc_meta.get("storage_path"),
        "file_name":       doc_meta.get("filename"),
        "file_size_bytes": len(file_bytes),
        "is_current":      True,
        "ingestion_status": "processing",
    }).execute()
    if not version_res.data:
        raise RuntimeError("Failed to create document_versions row")
    document_version_id = version_res.data[0]["id"]
    logger.info("Created document_version %s for doc %s", document_version_id[:8], doc_id[:8])

    # 3. Extract typed content (text, tables, images) from the PDF.
    logger.info("Extracting content from PDF (%d bytes)", len(file_bytes))
    content_items = extract_content(file_bytes)
    del file_bytes   # release the big buffer early

    logger.info(
        "Extracted %d items  (text=%d  table=%d  image=%d)",
        len(content_items),
        sum(1 for i in content_items if i["type"] == "text"),
        sum(1 for i in content_items if i["type"] == "table"),
        sum(1 for i in content_items if i["type"] == "image"),
    )

    # 4. Chunk
    chunks = chunk_content_items(content_items)
    if not chunks:
        raise RuntimeError("No extractable content in PDF")

    # 5. Process image chunks: upload bytes → Supabase storage, then
    #    summarize via Claude vision so we have embeddable text.
    max_page = 0
    for chunk in chunks:
        if chunk["page_end"] and chunk["page_end"] > max_page:
            max_page = chunk["page_end"]

        if chunk["type"] == "image" and chunk.get("image_bytes"):
            img_path = _upload_image(
                supabase, organization_id, doc_id,
                chunk["page_start"], chunk.get("position", 0),
                chunk["image_bytes"], chunk.get("image_ext") or "png",
            )
            logger.info("Summarizing image at %s", img_path)
            summary = summarize_image(chunk["image_bytes"], chunk.get("image_ext") or "png")
            chunk["content"]    = summary
            chunk["image_path"] = img_path
        else:
            chunk["image_path"] = None

        # Drop raw bytes — now in storage
        chunk.pop("image_bytes", None)
        chunk.pop("image_ext",   None)
        chunk.pop("image_idx",   None)

    # 6. Embed and insert in batches to cap peak memory.
    total = 0
    for i in range(0, len(chunks), CHUNK_INSERT_BATCH):
        batch = [c for c in chunks[i:i + CHUNK_INSERT_BATCH] if c["content"].strip()]
        if not batch:
            continue
        vectors = embed_texts([c["content"] for c in batch])
        rows = [
            {
                "document_id":         doc_id,
                "document_version_id": document_version_id,
                "organization_id":     organization_id,
                "content":             c["content"],
                "content_hash":        hashlib.md5(c["content"].encode()).hexdigest(),
                "chunk_index":         c["position"],       # "position" from chunker
                "page_start":          c["page_start"],
                "page_end":            c["page_end"],
                "embedding":           v,
                "chunk_type":          c["type"],
                "image_path":          c.get("image_path"),
            }
            for c, v in zip(batch, vectors)
        ]
        res = supabase.table("document_chunks").insert(rows).execute()
        if not res.data:
            raise RuntimeError(f"Chunk batch insert failed at offset {i}")
        total += len(res.data)

    logger.info("Inserted %d chunks for document %s", total, doc_id[:8])

    # 7. Flip version to complete and update document status.
    supabase.table("document_versions").update({
        "ingestion_status": "complete",
        "page_count":       max_page or None,
    }).eq("id", document_version_id).execute()

    supabase.table("documents").update({
        "status":      "ready",
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

    # Identify sessions that referenced this document — scoped to the org
    # so we don't scan the entire session_messages table across all tenants.
    sessions_res = (
        supabase.table("sessions")
        .select("id")
        .eq("organization_id", organization_id)
        .execute()
    )
    session_ids = [s["id"] for s in (sessions_res.data or [])]

    if session_ids:
        msgs_res = (
            supabase.table("session_messages")
            .select("session_id, citations")
            .in_("session_id", session_ids)
            .execute()
        )
        affected_sessions = set()
        for m in (msgs_res.data or []):
            for c in (m.get("citations") or []):
                if c.get("document_id") == doc_id:
                    affected_sessions.add(m["session_id"])
                    break

        for sid in affected_sessions:
            supabase.table("session_invalidations").insert({
                "session_id":    sid,
                "document_name": doc.data.get("name"),
                "revision":      doc.data.get("revision"),
                "message": (
                    "This document was removed or replaced. "
                    "Information from earlier in this session may no longer be current."
                ),
            }).execute()

    # Delete jobs, chunks (FK order), versions, then document row.
    supabase.table("ingestion_jobs").delete().eq("document_id", doc_id).execute()
    supabase.table("document_chunks").delete().eq("document_id", doc_id).execute()
    supabase.table("document_versions").delete().eq("document_id", doc_id).execute()
    supabase.table("documents").delete().eq("id", doc_id).execute()

    # Best-effort storage cleanup.
    if storage_path:
        try:
            supabase.storage.from_(settings.STORAGE_BUCKET).remove([storage_path])
        except Exception:
            pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _upload_image(
    supabase,
    organization_id: str,
    doc_id: str,
    page: int,
    idx: int,
    image_bytes: bytes,
    image_ext: str,
) -> str:
    img_path = f"{organization_id}/images/{doc_id}/p{page}_img{idx}.{image_ext}"
    supabase.storage.from_(settings.STORAGE_BUCKET).upload(
        path=img_path,
        file=image_bytes,
        file_options={"content-type": f"image/{image_ext}", "upsert": "true"},
    )
    return img_path
