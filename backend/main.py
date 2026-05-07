from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import documents, query, health

app = FastAPI(
    title="CrewBrief API",
    description="Aviation document Q&A backend for Royal Jordanian",
    version="0.1.0",
)

# CORS (Cross-Origin Resource Sharing) — allows the frontend
# running on a different domain (Vercel) to talk to this backend (Railway).
# Without this, browsers block the requests as a security measure.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tightened to specific Vercel URL after frontend is deployed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
app.include_router(query.router, prefix="/query", tags=["Query"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
