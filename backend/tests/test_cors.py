"""CORS policy tests for browser requests to the API."""

from fastapi.testclient import TestClient


def test_cors_preflight_allows_only_configured_frontend_origin(
    client: TestClient,
) -> None:
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }

    allowed = client.options("/auth/logout", headers=headers)

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert allowed.headers["access-control-allow-methods"] == "GET, POST"
    allowed_headers = allowed.headers["access-control-allow-headers"].lower()
    assert "content-type" in allowed_headers
    assert "authorization" not in allowed_headers
    assert allowed.headers["access-control-allow-origin"] != "*"

    headers["Origin"] = "https://untrusted.example.test"
    rejected = client.options("/auth/logout", headers=headers)

    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers
    assert "*" not in rejected.headers.get("access-control-allow-origin", "")
