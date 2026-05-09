"""
CrewBrief API — FastAPI backend for Royal Jordanian flight ops Q&A.
Entry point: registers middleware and route modules.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes import documents, query, sessions, health

app = FastAPI(
    title="CrewBrief API",
    description="Aviation document Q&A backend for Royal Jordanian",
    version="0.2.0",
)

# CORS — allows the Vercel frontend to call this Railway backend.
# In production, replace "*" with the specific frontend origin.
allowed_origins = [settings.FRONTEND_ORIGIN] if settings.FRONTEND_ORIGIN else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins + ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(health.router,    prefix="/health",    tags=["Health"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
app.include_router(sessions.router,  prefix="/sessions",  tags=["Sessions"])
app.include_router(query.router,     prefix="/query",     tags=["Query"])


@app.get("/")
def root():
    return {"service": "crewbrief-api", "status": "operational"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
