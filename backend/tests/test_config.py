"""Configuration tests -- Phase 0 Tests list (missing required env var fail-fast)."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_missing_required_env_var_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing required env var test from Phase 0 Tests list.

    Verifies Settings raises pydantic.ValidationError naming SESSION_SECRET
    when it is missing, while other required settings are supplied.
    """
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "SESSION_SECRET" in str(exc_info.value)
