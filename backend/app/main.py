"""
RepoPulse FastAPI application.

Entry point: app/main.py
Run locally: uvicorn app.main:app --reload  (from backend/ with .venv active)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.csrf import frontend_origin
from app.auth.routes import router as auth_router
from app.config import settings  # noqa: F401 -- imported to trigger fail-fast validation
from app.logging import configure_logging

configure_logging()

app = FastAPI(
    title="RepoPulse API",
    description="Software-engineering intelligence for public GitHub repositories.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin(settings.FRONTEND_URL)],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(auth_router)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    """Liveness check. Returns 200 when the process is up."""
    return {"status": "ok"}
