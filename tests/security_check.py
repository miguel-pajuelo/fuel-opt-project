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
from app.config import Settings


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


# ---------------------------------------------------------------------------
# H3 - proxy-aware rate-limit key
# ---------------------------------------------------------------------------
class _FakeClient:
    def __init__(self, host: str) -> None:
        self.host = host


class _FakeRequest:
    def __init__(self, host: str, xff: str | None = None) -> None:
        self.client = _FakeClient(host)
        self.headers = {} if xff is None else {"x-forwarded-for": xff}


def test_first_forwarded_ip_parsing() -> None:
    """H3: only well-formed IPs are accepted; left-most wins; ports tolerated."""
    assert api_main._first_forwarded_ip("203.0.113.7, 70.41.3.18") == "203.0.113.7"
    assert api_main._first_forwarded_ip("203.0.113.7:55555") == "203.0.113.7"
    assert api_main._first_forwarded_ip("garbage, also-bad") is None
    assert api_main._first_forwarded_ip("") is None


def test_client_identity_ignores_spoofed_xff_by_default(monkeypatch) -> None:
    """H3: in default/local mode a spoofed X-Forwarded-For is NOT trusted."""
    monkeypatch.setattr(api_main, "settings", Settings(trust_proxy_headers=False))
    ident = api_main._client_identity(_FakeRequest("10.0.0.9", xff="1.2.3.4"))
    assert ident == "10.0.0.9", "spoofed forwarded IP must be ignored without trust flag"


def test_client_identity_trusts_first_forwarded_ip_when_enabled(monkeypatch) -> None:
    """H3: with the trust flag on, identity is the first valid forwarded IP."""
    monkeypatch.setattr(api_main, "settings", Settings(trust_proxy_headers=True))
    ident = api_main._client_identity(_FakeRequest("10.0.0.9", xff="1.2.3.4, 5.6.7.8"))
    assert ident == "1.2.3.4"
    # No forwarded header -> fall back to the direct peer.
    assert api_main._client_identity(_FakeRequest("10.0.0.9", xff="")) == "10.0.0.9"


def test_proxy_trust_is_off_by_default() -> None:
    """H3: trusting forwarded headers must be opt-in."""
    assert Settings().trust_proxy_headers is False


# ---------------------------------------------------------------------------
# H6 - baseline security headers
# ---------------------------------------------------------------------------
def test_security_headers_baseline_defined() -> None:
    """H6: required baseline headers are present and no CSP is forced."""
    headers = api_main._SECURITY_HEADERS
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    # Geolocation must stay enabled for same-origin (the map uses it).
    assert "geolocation=(self)" in headers["Permissions-Policy"]
    # No strict CSP that would break Leaflet/CDN/inline handlers.
    assert "Content-Security-Policy" not in headers


def test_security_headers_present_on_response(monkeypatch) -> None:
    """H6 (functional): a representative route returns the baseline headers."""
    try:
        from fastapi.testclient import TestClient
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"TestClient unavailable (httpx not installed): {exc}")
    with TestClient(api_main.app) as client:
        resp = client.get("/health")
    for header, value in api_main._SECURITY_HEADERS.items():
        assert resp.headers.get(header) == value, f"missing/incorrect {header}"


# ---------------------------------------------------------------------------
# H8 - client IP logging / PII
# ---------------------------------------------------------------------------
def test_anonymize_ip_masks_host() -> None:
    """H8: IPs are coarsened (v4 -> /24, v6 -> /48); junk -> 'unknown'."""
    assert api_main._anonymize_ip("203.0.113.55") == "203.0.113.0"
    assert api_main._anonymize_ip("2001:db8:abcd:1234::1") == "2001:db8:abcd::"
    assert api_main._anonymize_ip("testclient") == "unknown"


def test_raw_ip_logging_is_off_by_default() -> None:
    """H8: raw client IP logging must be opt-in (PII off by default)."""
    assert Settings().log_client_ip is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
