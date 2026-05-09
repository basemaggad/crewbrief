"""
Query endpoint:
- POST /query  ask a question against the user's document library

The endpoint:
1. Saves the user's question as a message
2. Runs the retrieval + Claude pipeline
3. Saves the assistant's answer with citations
4. Returns the answer and citations
"""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime

from app.core.auth import get_current_user, CurrentUser
from app.db.supabase_client import get_supabase_admin
from app.models.schemas import QueryRequest, QueryResponse
from app.services.query_service import answer_question

router = APIRouter()


@router.post("", response_model=QueryResponse)
def ask(payload: QueryRequest, user: CurrentUser = Depends(get_current_user)):
    supabase = get_supabase_admin()

    # Verify session belongs to this user
    sess = supabase.table("sessions").select("id, title").eq(
        "id", payload.session_id
    ).eq("user_id", user.user_id).single().execute()
    if not sess.data:
        raise HTTPException(status_code=404, detail="Session not found")

    # Save user message
    supabase.table("messages").insert({
        "session_id": payload.session_id,
        "role": "user",
        "content": payload.question,
    }).execute()

    # Run retrieval + Claude
    try:
        result = answer_question(payload.question, user.organization_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

    # Save assistant message with citations
    supabase.table("messages").insert({
        "session_id": payload.session_id,
        "role": "assistant",
        "content": result["answer"],
        "citations": result["citations"],
    }).execute()

    # Auto-title the session from the first question if it's still default
    if (sess.data.get("title") or "").lower() in {"new briefing", "untitled briefing", ""}:
        title = payload.question.strip()[:60]
        if len(payload.question) > 60:
            title += "…"
        supabase.table("sessions").update({
            "title": title,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", payload.session_id).execute()
    else:
        supabase.table("sessions").update({
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", payload.session_id).execute()

    return QueryResponse(answer=result["answer"], citations=result["citations"])
