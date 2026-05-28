"""
Documents endpoints:
- GET    /documents         list documents for the user's org
- POST   /documents/upload  upload a PDF, enqueue ingestion, return immediately
- DELETE /documents/{id}    remove a document and invalidate affected sessions

Upload flow:
  1. Stream the file to a temp path (never loads the whole PDF into RAM).
  2. Upload the original PDF to Supabase Storage from the temp file.
  3. Delete the temp file.
  4. Create the `documents` row (status = 'processing').
  5. Create the `ingestion_jobs` row so the worker picks it up.
  6. Return the document row — the caller sees status='processing'
     and the UI polls until it flips to 'ready' or 'error'.
"""
import os
import uuid
import tempfile

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException

from app.core.auth import get_current_user, CurrentUser
from app.core.config import settings
from app.db.supabase_client import get_supabase_admin
from app.services.document_service import (
    create_document_record,
    enqueue_document,
    delete_document,
)

router = APIRouter()

READ_BLOCK = 1024 * 1024  # 1 MB per read


@router.get("")
def list_documents(user: CurrentUser = Depends(get_current_user)):
    supabase = get_supabase_admin()
    res = supabase.table("documents").select(
        "id, name, filename, document_type, aircraft_type, "
        "revision, status, chunk_count, created_at"
    ).eq("organization_id", user.organization_id).order("created_at", desc=True).execute()
    return res.data or []


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    revision: str = Form(""),
    aircraft_type: str = Form(""),
    user: CurrentUser = Depends(get_current_user),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024

    # ── Step 1: stream to temp file with size enforcement ──────────────────
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    size = 0
    try:
        while True:
            block = await file.read(READ_BLOCK)
            if not block:
                break
            size += len(block)
            if size > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds {settings.MAX_UPLOAD_MB} MB limit",
                )
            tmp.write(block)
        tmp.close()
    except HTTPException:
        tmp.close()
        _safe_unlink(tmp.name)
        raise
    except Exception as e:
        tmp.close()
        _safe_unlink(tmp.name)
        raise HTTPException(status_code=500, detail=f"Failed to receive upload: {e}")

    if size == 0:
        _safe_unlink(tmp.name)
        raise HTTPException(status_code=400, detail="Empty file")

    # ── Step 2: upload the original PDF to Supabase Storage ────────────────
    # We open the temp file as a stream so the SDK does not need to hold
    # the entire PDF in memory during the upload.
    storage_path = f"{user.organization_id}/{uuid.uuid4()}_{file.filename}"
    supabase = get_supabase_admin()
    try:
        with open(tmp.name, "rb") as f_obj:
            supabase.storage.from_(settings.STORAGE_BUCKET).upload(
                path=storage_path,
                file=f_obj,
                file_options={"content-type": "application/pdf"},
            )
    except Exception as e:
        _safe_unlink(tmp.name)
        raise HTTPException(status_code=500, detail=f"Storage upload failed: {e}")
    finally:
        # ── Step 3: temp file no longer needed ─────────────────────────────
        _safe_unlink(tmp.name)

    # ── Step 4: create the documents row ───────────────────────────────────
    try:
        document = create_document_record(
            filename=file.filename,
            document_type=document_type,
            revision=revision,
            aircraft_type=aircraft_type,
            organization_id=user.organization_id,
            uploader_id=user.user_id,
            storage_path=storage_path,
        )
    except Exception as e:
        # Storage object is orphaned here — acceptable; a cleanup job can
        # sweep storage for objects with no matching documents row.
        raise HTTPException(status_code=500, detail=f"Failed to create document: {e}")

    # ── Step 5: enqueue the ingestion job ──────────────────────────────────
    try:
        enqueue_document(document["id"], user.organization_id)
    except Exception as e:
        # Job creation failed — mark document as error so the UI doesn't
        # show it stuck in 'processing' forever.
        try:
            supabase.table("documents").update({
                "status": "error",
                "error_message": f"Failed to queue for processing: {e}",
            }).eq("id", document["id"]).execute()
            document["status"] = "error"
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to queue ingestion: {e}")

    # ── Step 6: return immediately ─────────────────────────────────────────
    # status = 'processing'; the worker flips it to 'ready' or 'error'.
    return document


@router.delete("/{doc_id}")
def remove_document(doc_id: str, user: CurrentUser = Depends(get_current_user)):
    delete_document(doc_id, user.organization_id)
    return {"deleted": True, "id": doc_id}


def _safe_unlink(path: str) -> None:
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except Exception:
        pass
