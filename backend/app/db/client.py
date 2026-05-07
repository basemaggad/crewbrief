from supabase import create_client, Client
from app.core.config import settings

def get_supabase_client() -> Client:
    """Standard client — respects Row Level Security (RLS).
    Used for user-facing queries where access rules must apply."""
    return create_client(settings.supabase_url, settings.supabase_anon_key)

def get_supabase_admin_client() -> Client:
    """Admin client — bypasses RLS.
    Used only by the backend for ingestion and system tasks."""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)

supabase: Client = get_supabase_client()
supabase_admin: Client = get_supabase_admin_client()
