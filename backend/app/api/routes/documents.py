"""
Documents endpoints:
- GET    /documents         list documents for the user's org
- POST   /documents/upload  upload a PDF, kicks off ingestion
- DELETE /documents/{id}    remove a document and mark sessions invalidated
"""
from typing import List
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException

from app.core.auth import get_current_user, CurrentUser
from app.db.supabase_client import get_supabase_admin
from app.services.document_service import ingest_document, delete_document

router = APIRouter()


@router.get("")
def list_documents(user: CurrentUser = Depends(get_current_user)):
    supabase = get_supabase_admin()
    res = supabase.table("documents").select(
        "id, name, filename, document_type, aircraft_type, revision, status, chunk_count, created_at"
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
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    contents = await file.read()
    if len(contents) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit")

    try:
        document = await ingest_document(
            file_bytes=contents,
            filename=file.filename,
            document_type=document_type,
            revision=revision,
            aircraft_type=aircraft_type,
            organization_id=user.organization_id,
            uploader_id=user.user_id,
        )
        return document
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{doc_id}")
def remove_document(doc_id: str, user: CurrentUser = Depends(get_current_user)):
    delete_document(doc_id, user.organization_id)
    return {"deleted": True, "id": doc_id}
