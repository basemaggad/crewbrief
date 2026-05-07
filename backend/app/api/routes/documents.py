import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.db.client import supabase_admin
from app.services.ingestion import ingest_document
from app.models.schemas import DocumentUploadResponse, DocumentOut

router = APIRouter()

@router.get("/", response_model=list[DocumentOut])
def list_documents(organization_id: str):
    """Return all active documents for an organization."""
    result = supabase_admin.table("documents")\
        .select("*")\
        .eq("organization_id", organization_id)\
        .eq("is_active", True)\
        .execute()
    return result.data

@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    organization_id: str = Form(...),
    title: str = Form(...),
    doc_type: str = Form(...),
    version_label: str = Form(...),
    aircraft_type: str = Form(None),
    file: UploadFile = File(...),
):
    """
    Upload a new document or a new version of an existing document.
    Steps:
    1. Upload the PDF to Supabase Storage
    2. Create document and version records in the database
    3. Trigger the ingestion pipeline to chunk and embed the document
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    file_bytes = await file.read()
    document_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    storage_path = f"{organization_id}/{document_id}/{version_id}/{file.filename}"

    # Upload to Supabase Storage
    supabase_admin.storage.from_("documents").upload(
        path=storage_path,
        file=file_bytes,
        file_options={"content-type": "application/pdf"},
    )

    # Create document record
    supabase_admin.table("documents").insert({
        "id": document_id,
        "organization_id": organization_id,
        "title": title,
        "doc_type": doc_type,
        "aircraft_type": aircraft_type,
        "role_access": [],
    }).execute()

    # Create version record
    supabase_admin.table("document_versions").insert({
        "id": version_id,
        "document_id": document_id,
        "organization_id": organization_id,
        "version_label": version_label,
        "storage_path": storage_path,
        "file_name": file.filename,
        "file_size_bytes": len(file_bytes),
        "is_current": True,
        "ingestion_status": "pending",
    }).execute()

    # Run ingestion pipeline
    ingest_document(
        organization_id=organization_id,
        document_id=document_id,
        version_id=version_id,
        file_bytes=file_bytes,
    )

    return DocumentUploadResponse(
        document_id=document_id,
        version_id=version_id,
        message=f"Document ingested successfully.",
    )
