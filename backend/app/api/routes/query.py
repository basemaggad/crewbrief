import uuid
from fastapi import APIRouter, HTTPException
from app.db.client import supabase_admin
from app.services.retrieval import retrieve_chunks, generate_answer
from app.models.schemas import QueryRequest, QueryResponse, CitationOut

router = APIRouter()

@router.post("/", response_model=QueryResponse)
def ask_question(request: QueryRequest, organization_id: str):
    """
    Main Q&A endpoint. Accepts a question and returns a grounded answer
    with citations, or logs it as unresolved if the documents don't cover it.
    """
    # Create or retrieve session
    if request.session_id:
        session_id = str(request.session_id)
    else:
        session_id = str(uuid.uuid4())
        supabase_admin.table("sessions").insert({
            "id": session_id,
            "organization_id": organization_id,
            "user_id": organization_id,  # temporary until auth is wired
            "title": request.query[:60],
        }).execute()

    # Retrieve conversation history for multi-turn context
    history_result = supabase_admin.table("session_messages")\
        .select("role, content")\
        .eq("session_id", session_id)\
        .order("created_at")\
        .execute()

    conversation_history = [
        {"role": m["role"], "content": m["content"]}
        for m in (history_result.data or [])
    ]

    # Retrieve relevant document chunks
    doc_ids = [str(d) for d in request.document_ids] if request.document_ids else None
    chunks = retrieve_chunks(
        query=request.query,
        organization_id=organization_id,
        document_ids=doc_ids,
    )

    # Generate answer
    answer, has_unresolved = generate_answer(
        query=request.query,
        chunks=chunks,
        conversation_history=conversation_history,
    )

    # Store user message
    user_message_id = str(uuid.uuid4())
    supabase_admin.table("session_messages").insert({
        "id": user_message_id,
        "session_id": session_id,
        "organization_id": organization_id,
        "role": "user",
        "content": request.query,
    }).execute()

    # Store assistant message
    assistant_message_id = str(uuid.uuid4())
    supabase_admin.table("session_messages").insert({
        "id": assistant_message_id,
        "session_id": session_id,
        "organization_id": organization_id,
        "role": "assistant",
        "content": answer,
    }).execute()

    # Record which chunks were used (for invalidation tracking)
    for chunk in chunks:
        supabase_admin.table("session_chunks").insert({
            "session_message_id": assistant_message_id,
            "session_id": session_id,
            "organization_id": organization_id,
            "chunk_id": chunk["chunk_id"],
            "document_id": chunk["document_id"],
            "document_version_id": chunk["document_version_id"],
            "section_title": chunk.get("section_title"),
        }).execute()

    # Log unresolved question if applicable
    if has_unresolved:
        supabase_admin.table("unresolved_questions").insert({
            "organization_id": organization_id,
            "session_id": session_id,
            "query_text": request.query,
        }).execute()

    # Build citations from chunks
    citations = []
    seen = set()
    for chunk in chunks:
        key = chunk.get("section_title") or chunk["document_id"]
        if key not in seen:
            seen.add(key)
            citations.append(CitationOut(
                document_title=chunk["document_id"],
                section_title=chunk.get("section_title"),
                page_start=chunk.get("page_start"),
                page_end=chunk.get("page_end"),
            ))

    return QueryResponse(
        session_id=uuid.UUID(session_id),
        message_id=uuid.UUID(assistant_message_id),
        answer=answer,
        citations=citations,
        has_unresolved=has_unresolved,
    )
