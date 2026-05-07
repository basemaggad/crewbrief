from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def health_check():
    """
    Simple health check endpoint.
    Railway uses this to confirm the backend is running.
    Like a transponder squawk — just confirming we're alive and on frequency.
    """
    return {"status": "ok", "service": "crewbrief-backend"}
