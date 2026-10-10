"""
Application settings loaded from environment variables.

All variables are defined in Architecture section 41. The app fails on startup
if any required variable is missing -- pydantic-settings raises ValidationError
before the server accepts any request.

Add new variables here only when a task requires them. Do not invent names.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to this file, not the working directory.
# backend/app/config.py -> .parent = backend/app -> .parent = backend
#                       -> .parent = repo root -> .env
_ENV_FILE = Path(__file__).parent.parent.parent / ".env"


class Settings(BaseSettings):
    # Required -- must be present in the environment or .env file.
    # Used from Phase 1 onward for session signing; declared now so the app
    # fails fast rather than silently starting with an insecure state.
    SESSION_SECRET: str

    # Optional with defaults -- values from Architecture section 41 / limits.
    # Phase-specific variables (DATABASE_URL, GITHUB_*, OPENAI_*, etc.) are
    # added in the tasks that introduce them.
    MAX_REPO_SIZE_MB: int = 50
    MAX_SOURCE_FILES: int = 1000
    ANALYSIS_TIMEOUT_SECONDS: int = 300

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        # Extra fields in .env that are not declared here are ignored.
        # This lets the full .env.example variables live in one file without
        # causing validation errors as later tasks declare them.
        extra="ignore",
    )


# Module-level singleton -- imported by the rest of the app.
# Raises pydantic_settings.ValidationError on startup if SESSION_SECRET is missing.
settings = Settings()
