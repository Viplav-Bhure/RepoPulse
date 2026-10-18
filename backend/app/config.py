"""
Application settings loaded from environment variables.

All variables are defined in Architecture section 41. The app fails on startup
if any required variable is missing -- pydantic-settings raises ValidationError
before the server accepts any request.

Add new variables here only when a task requires them. Do not invent names.
"""

from pathlib import Path
from typing import Annotated

from pydantic import StringConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to this file, not the working directory.
# backend/app/config.py -> .parent = backend/app -> .parent = backend
#                       -> .parent = repo root -> .env
_ENV_FILE = Path(__file__).parent.parent.parent / ".env"
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Settings(BaseSettings):
    # Required -- must be present in the environment or .env file.
    # Used from Phase 1 onward for session signing; declared now so the app
    # fails fast rather than silently starting with an insecure state.
    SESSION_SECRET: str
    DATABASE_URL: str
    GITHUB_CLIENT_ID: NonEmptyString
    GITHUB_CLIENT_SECRET: NonEmptyString
    GITHUB_PUBLIC_API_TOKEN: NonEmptyString
    FRONTEND_URL: NonEmptyString
    API_BASE_URL: NonEmptyString

    # Optional with defaults -- values from Architecture section 41 / limits.
    MAX_REPO_SIZE_MB: int = 50
    MAX_SOURCE_FILES: int = 1000
    ANALYSIS_TIMEOUT_SECONDS: int = 300

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        hide_input_in_errors=True,
        # Extra fields in .env that are not declared here are ignored.
        # This lets the full .env.example variables live in one file without
        # causing validation errors as later tasks declare them.
        extra="ignore",
    )


# Module-level singleton -- imported by the rest of the app.
# Raises pydantic.ValidationError on startup if a required setting is missing.
settings = Settings()
