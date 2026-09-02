"""Tests for GET /health.

These tests use FastAPI'\''s TestClient (backed by httpx) so they run without
a real Supabase connection.  The Supabase client import at module level is
patched via monkeypatch / environment variables set before import time to
prevent ``ValidationError`` from missing env vars.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _mock_supabase_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject fake env vars so Settings() does not raise during tests."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


@pytest.fixture()
def client(_mock_supabase_env: None) -> TestClient:  # noqa: ARG001
    """Return a TestClient with the Supabase probe stubbed out."""
    # Stub out the Supabase create_client so we do not hit the network.
    import unittest.mock as mock

    with (
        mock.patch("app.db.supabase_client.create_client") as mock_create,
        mock.patch("app.db.supabase_client.probe_connection") as mock_probe,
    ):
        mock_create.return_value = mock.MagicMock()
        mock_probe.return_value = None

        # Import app *after* patching so the module-level create_client call
        # is intercepted.
        from app.main import app  # noqa: PLC0415

        return TestClient(app)


def test_health_returns_200(client: TestClient) -> None:
    """GET /health must respond with HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_body(client: TestClient) -> None:
    """GET /health body must be {\"status\": \"ok\"}."""
    response = client.get("/health")
    assert response.json() == {"status": "ok"}


def test_health_content_type(client: TestClient) -> None:
    """GET /health must return JSON content-type."""
    response = client.get("/health")
    assert "application/json" in response.headers["content-type"]
