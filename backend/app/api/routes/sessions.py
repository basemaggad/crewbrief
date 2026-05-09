"""
Sessions endpoints:
- GET    /sessions         list sessions for the user
- POST   /sessions         create a new session
- GET    /sessions/{id}    get session + messages + invalidations
- DELETE /sessions/{id}    delete a session and its messages
"""
from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_current_user, CurrentUser
from app.db.supabase_client import get_supabase_admin
from app.models.schemas import SessionCreate

router = APIRouter()


@router.get("")
def list_sessions(user: CurrentUser = Depends(get_current_user)):
    supabase = get_supabase_admin()
    res = supabase.table("sessions").select(
        "id, title, created_at, updated_at"
    ).eq("user_id", user.user_id).order("created_at", desc=True).execute()
    return res.data or []


@router.post("")
def create_session(payload: SessionCreate, user: CurrentUser = Depends(get_current_user)):
    supabase = get_supabase_admin()
    res = supabase.table("sessions").insert({
        "title": payload.title or "New briefing",
        "user_id": user.user_id,
        "organization_id": user.organization_id,
    }).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create session")
    return res.data[0]


@router.get("/{session_id}")
def get_session(session_id: str, user: CurrentUser = Depends(get_current_user)):
    supabase = get_supabase_admin()

    sess = supabase.table("sessions").select("*").eq("id", session_id).eq("user_id", user.user_id).single().execute()
    if not sess.data:
        raise HTTPException(status_code=404, detail="Session not found")

    msgs = supabase.table("session_messages").select(
        "id, role, content, citations, created_at"
    ).eq("session_id", session_id).order("created_at").execute()

    invs = supabase.table("session_invalidations").select(
        "document_name, revision, section, message"
    ).eq("session_id", session_id).execute()

    return {
        "session": sess.data,
        "messages": msgs.data or [],
        "invalidations": invs.data or [],
    }


@router.delete("/{session_id}")
def delete_session(session_id: str, user: CurrentUser = Depends(get_current_user)):
    supabase = get_supabase_admin()
    # Verify ownership
    sess = supabase.table("sessions").select("id").eq("id", session_id).eq("user_id", user.user_id).execute()
    if not sess.data:
        raise HTTPException(status_code=404, detail="Session not found")
    supabase.table("session_messages").delete().eq("session_id", session_id).execute()
    supabase.table("session_invalidations").delete().eq("session_id", session_id).execute()
    supabase.table("sessions").delete().eq("id", session_id).execute()
    return {"deleted": True, "id": session_id}
