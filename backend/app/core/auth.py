"""
Auth — verifies Supabase JWTs using PyJWT.

Supports both Supabase JWT formats:
  1. Legacy HS256 (symmetric, signed with SUPABASE_JWT_SECRET)
  2. New asymmetric (ES256/RS256, signed with private key, verified via JWKS)

Uses PyJWT's PyJWKClient to fetch and cache the public keys from
<project>/auth/v1/.well-known/jwks.json automatically.

Reference: https://supabase.com/docs/guides/auth/jwts
"""
from typing import Optional, Dict, Any
from functools import lru_cache

import jwt as pyjwt
from jwt import PyJWKClient

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.db.supabase_client import get_supabase_admin

bearer_scheme = HTTPBearer(auto_error=False)


def _jwks_url() -> str:
    base = settings.SUPABASE_URL.rstrip("/")
    return f"{base}/auth/v1/.well-known/jwks.json"


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    """Cached JWKS client — fetches and caches public keys automatically."""
    return PyJWKClient(_jwks_url(), cache_keys=True, lifespan=600)


def _verify_token(token: str) -> Dict[str, Any]:
    """Verify the JWT and return its claims dict. Raises HTTPException(401) on failure."""
    try:
        header = pyjwt.get_unverified_header(token)
    except pyjwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Malformed token header: {e}",
        )

    alg = (header.get("alg") or "").upper()

    # ── Legacy HS256 ────────────────────────────────────────────────────────
    if alg == "HS256":
        try:
            return pyjwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
                options={"verify_aud": False},
            )
        except pyjwt.PyJWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid HS256 token: {e}",
            )

    # ── Asymmetric ES256 / RS256 / EdDSA ───────────────────────────────────
    if alg in ("ES256", "RS256", "EDDSA"):
        try:
            signing_key = _jwks_client().get_signing_key_from_jwt(token)
            return pyjwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                audience="authenticated",
                options={"verify_aud": False},
            )
        except pyjwt.PyJWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid {alg} token: {e}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Could not verify {alg} token: {e}",
            )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"Unsupported token algorithm: {alg}",
    )


# ── FastAPI dependency ──────────────────────────────────────────────────────
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
    payload = _verify_token(token)

    user_id = payload.get("sub")
    email = payload.get("email", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing user id")

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
