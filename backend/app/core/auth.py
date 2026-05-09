"""
Auth — verifies JWT tokens issued by Supabase Auth on the frontend.
Every protected route uses Depends(get_current_user) to require a valid token
and to extract the user's ID + organization_id from it.
"""
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError

from app.core.config import settings
from app.db.supabase_client import get_supabase_admin

bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser:
    def __init__(self, user_id: str, email: str, organization_id: str, role: str = "pilot"):
        self.user_id = user_id
        self.email = email
        self.organization_id = organization_id
        self.role = role


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> CurrentUser:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )

    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )

    user_id = payload.get("sub")
    email = payload.get("email", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing user id")

    # Look up the user's organization & role from the users table.
    # The users table is keyed on the auth user id.
    supabase = get_supabase_admin()
    res = supabase.table("users").select("organization_id, role").eq("id", user_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=403, detail="User profile not found")

    return CurrentUser(
        user_id=user_id,
        email=email,
        organization_id=res.data["organization_id"],
        role=res.data.get("role", "pilot"),
    )
