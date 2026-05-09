"""
Pydantic schemas for request and response bodies.
These define the shapes of data that flow between frontend and backend.
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


# ── Documents ────────────────────────────────────────────────────────────────
class DocumentOut(BaseModel):
    id: str
    name: str
    filename: Optional[str] = None
    document_type: Optional[str] = None
    aircraft_type: Optional[str] = None
    revision: Optional[str] = None
    status: str = "pending"
    chunk_count: Optional[int] = None
    created_at: Optional[datetime] = None


# ── Sessions ─────────────────────────────────────────────────────────────────
class SessionCreate(BaseModel):
    title: Optional[str] = "New briefing"


class SessionOut(BaseModel):
    id: str
    title: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MessageOut(BaseModel):
    id: str
    role: str  # "user" | "assistant"
    content: str
    citations: Optional[List[dict]] = None
    created_at: Optional[datetime] = None


class InvalidationOut(BaseModel):
    document_name: str
    revision: Optional[str] = None
    section: Optional[str] = None
    message: Optional[str] = None


class SessionDetail(BaseModel):
    session: SessionOut
    messages: List[MessageOut]
    invalidations: List[InvalidationOut] = []


# ── Query ────────────────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    session_id: str
    question: str


class Citation(BaseModel):
    document_name: str
    section: Optional[str] = None
    revision: Optional[str] = None
    excerpt: Optional[str] = None
    chunk_id: Optional[str] = None


class QueryResponse(BaseModel):
    answer: str
    citations: List[Citation] = []
