"""Health check endpoint — used by Railway and frontend probes."""
from fastapi import APIRouter

router = APIRouter()


@router.get("")
def health():
    return {"status": "ok", "service": "crewbrief-api"}
