"""
RepoPulse FastAPI application.

Entry point: app/main.py
Run locally: uvicorn app.main:app --reload  (from backend/ with .venv active)
"""

from fastapi import FastAPI

from app.config import settings  # noqa: F401 -- imported to trigger fail-fast validation

app = FastAPI(
    title="RepoPulse API",
    description="Software-engineering intelligence for public GitHub repositories.",
    version="0.1.0",
)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    """Liveness check. Returns 200 when the process is up."""
    return {"status": "ok"}
