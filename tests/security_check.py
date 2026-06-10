from __future__ import annotations

import inspect
import logging
import sys
from pathlib import Path

import pytest
import requests
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.api.main as api_main


# A fake ORS error message carrying everything that must never reach a client
# response *or* the server logs: the secret value, the `api_key` parameter name
# and the raw OpenRouteService URL.
_FAKE_ORS_KEY = "SECRET123"
_FAKE_ORS_ERROR = (
    "403 Client Error: Forbidden for url: "
    f"https://api.openrouteservice.org/geocode/search?api_key={_FAKE_ORS_KEY}&text=x"
)
_SENSITIVE_TOKENS = (_FAKE_ORS_KEY, "api_key", "openrouteservice.org")


def _boom(*_args, **_kwargs):
    raise requests.HTTPError(_FAKE_ORS_ERROR)


def test_geocode_error_does_not_leak_ors_key(monkeypatch, caplog) -> None:
    """H1: an ORS HTTP error must not surface secrets to the client or the logs."""
    monkeypatch.setattr(api_main, "geocode_candidates", _boom)
    monkeypatch.setattr(api_main, "geocode_candidates_autocomplete", _boom)

    with caplog.at_level(logging.WARNING, logger="fuelopt.api"):
        with pytest.raises(HTTPException) as excinfo:
            api_main.geocode(q="madrid centro")

    exc = excinfo.value
    assert exc.status_code == 502
    assert str(exc.detail) == "Geocoding provider unavailable."

    detail = str(exc.detail)
    for token in _SENSITIVE_TOKENS:
        assert token not in detail, f"client response leaked {token!r}: {detail!r}"
        assert token not in caplog.text, f"server log leaked {token!r}: {caplog.text!r}"

    # The log must still tell us which path failed.
    assert "geocode_provider_error" in caplog.text


def test_reverse_geocode_error_does_not_leak_ors_key(monkeypatch, caplog) -> None:
    """H1: same protection on the reverse-geocode path (client + logs)."""
    monkeypatch.setattr(api_main, "reverse_geocode_coordinates", _boom)

    with caplog.at_level(logging.WARNING, logger="fuelopt.api"):
        with pytest.raises(HTTPException) as excinfo:
            api_main.reverse_geocode(lat=40.4, lon=-3.7)

    exc = excinfo.value
    assert exc.status_code == 502
    assert str(exc.detail) == "Geocoding provider unavailable."

    detail = str(exc.detail)
    for token in _SENSITIVE_TOKENS:
        assert token not in detail, f"client response leaked {token!r}: {detail!r}"
        assert token not in caplog.text, f"server log leaked {token!r}: {caplog.text!r}"

    assert "reverse_geocode_provider_error" in caplog.text


def test_feedback_endpoint_has_rate_limit_marker() -> None:
    """H2 (structural): slowapi only wires a limit when the endpoint exposes a
    `request: Request` parameter. This is a static guarantee that the decorator
    is in place; it does NOT prove runtime enforcement (see the functional test).
    """
    params = inspect.signature(api_main.submit_feedback).parameters
    assert "request" in params, "submit_feedback must accept `request` for rate limiting to apply"


class _FakeSMTP:
    """No-op SMTP stand-in so the functional test never sends real email."""

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def __enter__(self) -> "_FakeSMTP":
        return self

    def __exit__(self, *_args) -> bool:
        return False

    def ehlo(self, *_args, **_kwargs) -> None:
        pass

    def starttls(self, *_args, **_kwargs) -> None:
        pass

    def login(self, *_args, **_kwargs) -> None:
        pass

    def sendmail(self, *_args, **_kwargs) -> None:
        pass


@pytest.mark.skipif(
    not api_main._slowapi_available,
    reason="slowapi not installed: limiter is a no-op, runtime 429 cannot be enforced",
)
def test_feedback_rate_limit_enforced_returns_429(monkeypatch) -> None:
    """H2 (functional): exceeding 5/minute on /feedback must yield a 429.

    Only runs when slowapi is actually installed; otherwise it is skipped (never
    falsely passed). Email sending is stubbed so no SMTP traffic occurs.
    """
    try:
        from fastapi.testclient import TestClient
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"TestClient unavailable (httpx not installed): {exc}")

    monkeypatch.setenv("GMAIL_USER", "test@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "dummy-not-a-real-secret")
    monkeypatch.setenv("FEEDBACK_RECIPIENT", "test@example.com")
    monkeypatch.setattr("smtplib.SMTP", _FakeSMTP)

    client = TestClient(api_main.app)
    statuses = [
        client.post(
            "/feedback",
            json={"email": "user@example.com", "message": "functional rate-limit probe"},
        ).status_code
        for _ in range(7)
    ]
    assert 429 in statuses, f"expected a 429 after exceeding 5/minute, got {statuses}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
