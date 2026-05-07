from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime

# --- Document Models ---

class DocumentUploadResponse(BaseModel):
    document_id: UUID
    version_id: UUID
    message: str

class DocumentOut(BaseModel):
    id: UUID
    title: str
    doc_type: str
    aircraft_type: Optional[str]
    is_active: bool
    created_at: datetime

# --- Query Models ---

class QueryRequest(BaseModel):
    session_id: Optional[UUID] = None
    query: str
    document_ids: Optional[list[UUID]] = None

class CitationOut(BaseModel):
    document_title: str
    section_title: Optional[str]
    page_start: Optional[int]
    page_end: Optional[int]

class QueryResponse(BaseModel):
    session_id: UUID
    message_id: UUID
    answer: str
    citations: list[CitationOut]
    has_unresolved: bool

# --- Session Models ---

class SessionOut(BaseModel):
    id: UUID
    title: Optional[str]
    created_at: datetime

class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime
