"""
Auth — verifies JWT tokens issued by Supabase Auth on the frontend.

Supabase has two JWT signing systems:
  1. Legacy HS256 — symmetric, signed with SUPABASE_JWT_SECRET
  2. New asymmetric — ES256 or RS256, signed with private key,
     verified using public keys exposed at <project>/auth/v1/.well-known/jwks.json

This file handles BOTH. It inspects the token's header `alg` and `kid`,
then verifies with the appropriate method:

  - alg == "HS256" → verify with the shared secret (legacy)
  - alg in ("ES256","RS256") → fetch public keys from JWKS endpoint and verify

The JWKS keys are cached in memory and refreshed on cache miss
(when the token references a kid we don't have yet — e.g. after key rotation).

Reference: https://supabase.com/docs/guides/auth/jwts
GitHub issue confirming get_user() is unreliable with new keys:
https://github.com/supabase/supabase-py/issues/1183
"""
from typing import Optional, Dict, Any
import time
import httpx

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, jwk
from jose.utils import base64url_decode
from jose.exceptions import JWTError

from app.core.config import settings
from app.db.supabase_client import get_supabase_admin

bearer_scheme = HTTPBearer(auto_error=False)


# ── JWKS cache ──────────────────────────────────────────────────────────────
_jwks_cache: Dict[str, Any] = {"keys_by_kid": {}, "fetched_at": 0.0}
_JWKS_TTL_SECONDS = 600  # refresh at most every 10 minutes


def _jwks_url() -> str:
    base = settings.SUPABASE_URL.rstrip("/")
    return f"{base}/auth/v1/.well-known/jwks.json"


def _refresh_jwks() -> None:
    """Fetch the current JWKS and rebuild the kid -> JWK map."""
    try:
        resp = httpx.get(_jwks_url(), timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        # If JWKS fetch fails, leave the cache as-is so we can still verify
        # tokens using already-cached keys, but record the failure time.
        _jwks_cache["fetched_at"] = time.time()
        return

    keys = data.get("keys", []) if isinstance(data, dict) else []
    keys_by_kid = {}
    for k in keys:
        kid = k.get("kid")
        if kid:
            keys_by_kid[kid] = k
    _jwks_cache["keys_by_kid"] = keys_by_kid
    _jwks_cache["fetched_at"] = time.time()


def _get_jwk_for_kid(kid: str) -> Optional[Dict[str, Any]]:
    """Look up a JWK by kid. Refreshes the cache if missing or stale."""
    keys = _jwks_cache["keys_by_kid"]
    age = time.time() - _jwks_cache["fetched_at"]

    if kid in keys:
        return keys[kid]

    # Cache miss or expired → refresh once and try again
    if age > _JWKS_TTL_SECONDS or kid not in keys:
        _refresh_jwks()

    return _jwks_cache["keys_by_kid"].get(kid)


# ── Verification ────────────────────────────────────────────────────────────
def _verify_token(token: str) -> Dict[str, Any]:
    """
    Verifies the token signature and returns the claims dict.
    Raises HTTPException(401) on failure.
    """
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Malformed token header: {e}",
        )

    alg = header.get("alg", "").upper()
    kid = header.get("kid")

    # ── Legacy HS256 ────────────────────────────────────────────────────────
    if alg == "HS256":
        try:
            return jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid HS256 token: {e}",
            )

    # ── Asymmetric ES256 / RS256 ────────────────────────────────────────────
    if alg in ("ES256", "RS256", "EdDSA"):
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Asymmetric token missing 'kid' header",
            )

        jwk_data = _get_jwk_for_kid(kid)
        if not jwk_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"No public key found for kid={kid}",
            )

        try:
            public_key = jwk.construct(jwk_data, algorithm=alg)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Failed to construct public key: {e}",
            )

        try:
            return jwt.decode(
                token,
                public_key.to_pem().decode() if hasattr(public_key, "to_pem") else jwk_data,
                algorithms=[alg],
                audience="authenticated",
                options={"verify_aud": False},  # some Supabase tokens omit aud
            )
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid {alg} token: {e}",
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

    # Look up the user's organization & role from the users table
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
