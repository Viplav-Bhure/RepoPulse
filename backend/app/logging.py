"""Redact credentials and sensitive request data before log records are emitted."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

_SENSITIVE_NAME = (
    r"(?:[A-Za-z0-9_-]*[_-])?(?:access[_-]?token|session[_-]?token|token|cookie|set[_-]?cookie|"
    r"authorization|code|authorization[_-]?code|state|verifier|code[_-]?verifier|"
    r"client[_-]?secret|session[_-]?secret|secret[_-]?key|api[_-]?key|"
    r"x[_-]?api[_-]?key)"
)
_SENSITIVE_ASSIGNMENT = re.compile(
    rf"(?i)([\"']?\b{_SENSITIVE_NAME}\b[\"']?\s*[:=]\s*)"
    r'("[^"]*"|\'[^\']*\'|[^&\s,;]+)'
)
_SENSITIVE_HEADER = re.compile(
    r"(?im)(\b(?:authorization|cookie|set-cookie)\b\s*:\s*)[^\r\n]*"
)
_SENSITIVE_QUERY = re.compile(rf"(?i)([?&]{_SENSITIVE_NAME}=)[^&#\s\"']*")
_KNOWN_COOKIE = re.compile(
    r"(?i)\b(repopulse_session|repopulse_oauth_state)\s*=\s*[^;\s,]+"
)
_BEARER_TOKEN = re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+")
_REDACTED = "<redacted>"
_REDACTED_HEADER = "<redacted header>"
_STANDARD_RECORD_FIELDS = logging.LogRecord("", 0, "", 0, "", (), None).__dict__


def _normalized_name(name: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _sensitive_key(name: object) -> bool:
    normalized = _normalized_name(name)
    return any(
        normalized.endswith(suffix)
        for suffix in {
            "accesstoken",
            "authorization",
            "authorizationcode",
            "apikey",
            "clientsecret",
            "code",
            "codeverifier",
            "cookie",
            "githubclientsecret",
            "openaiapikey",
            "sessioncookie",
            "sessionsecret",
            "sessiontoken",
            "setcookie",
            "state",
            "token",
            "verifier",
            "xapikey",
        }
    )


def redact_sensitive_data(value: Any) -> Any:
    """Redact known credential fields while retaining unrelated event context."""
    if isinstance(value, str):
        value = _SENSITIVE_ASSIGNMENT.sub(rf"\1{_REDACTED}", value)
        value = _SENSITIVE_HEADER.sub(rf"\1{_REDACTED_HEADER}", value)
        value = _SENSITIVE_QUERY.sub(rf"\1{_REDACTED}", value)
        value = _KNOWN_COOKIE.sub(rf"\1={_REDACTED}", value)
        return _BEARER_TOKEN.sub(rf"\1 {_REDACTED}", value)
    if isinstance(value, Mapping):
        return {
            key: _REDACTED if _sensitive_key(key) else redact_sensitive_data(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, set):
        return {redact_sensitive_data(item) for item in value}
    if isinstance(value, BaseException):
        return f"{type(value).__name__}: {redact_sensitive_data(str(value))}"
    return value


class SensitiveDataFilter(logging.Filter):
    """Sanitize a log record before any configured handler formats it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.args = redact_sensitive_data(record.args)
        message = record.getMessage()
        if record.exc_info and record.exc_info[1] is not None:
            error = record.exc_info[1]
            message = f"{message} ({type(error).__name__}: {error})"

        record.msg = redact_sensitive_data(message)
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        if record.stack_info is not None:
            record.stack_info = redact_sensitive_data(record.stack_info)

        for name, value in tuple(record.__dict__.items()):
            if name not in _STANDARD_RECORD_FIELDS:
                record.__dict__[name] = (
                    _REDACTED if _sensitive_key(name) else redact_sensitive_data(value)
                )
        return True


_configured = False


def configure_logging() -> None:
    """Redact records at creation so app and Uvicorn access logs are covered."""
    global _configured
    if _configured:
        return

    previous_factory = logging.getLogRecordFactory()
    sensitive_filter = SensitiveDataFilter()

    def safe_record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = previous_factory(*args, **kwargs)
        sensitive_filter.filter(record)
        return record

    logging.setLogRecordFactory(safe_record_factory)
    for logger_name in (
        "app",
        "app.auth.routes",
        "app.auth.session",
        "uvicorn.access",
    ):
        logging.getLogger(logger_name).addFilter(sensitive_filter)
    for handler in logging.getLogger().handlers:
        handler.addFilter(sensitive_filter)
    _configured = True
