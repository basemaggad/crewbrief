"""
Supabase client factory.
- get_supabase_admin: uses the service role key, bypasses RLS.
  Used for server-side operations like inserting chunks.
- The frontend uses the anon key directly, so we don't need a user-scoped
  client here for now; the JWT already gives us the user's identity.
"""
from supabase import create_client, Client
from app.core.config import settings

_admin: Client | None = None


def get_supabase_admin() -> Client:
    global _admin
    if _admin is None:
        _admin = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    return _admin
