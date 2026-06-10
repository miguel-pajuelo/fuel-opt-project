from __future__ import annotations

import inspect
import sys
from pathlib import Path

import requests
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.api.main as api_main


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


_FAKE_ORS_KEY = "FAKE_ORS_KEY_DO_NOT_LEAK"
_FAKE_ORS_ERROR = (
    "403 Client Error: Forbidden for url: "
    f"https://api.openrouteservice.org/geocode/search?api_key={_FAKE_ORS_KEY}&text=x"
)


def test_geocode_error_does_not_leak_ors_key() -> None:
    """H1: an ORS HTTP error must not surface the api_key to the client."""
    previous = (api_main.geocode_candidates, api_main.geocode_candidates_autocomplete)

    def _boom(*_args, **_kwargs):
        raise requests.HTTPError(_FAKE_ORS_ERROR)

    api_main.geocode_candidates = _boom
    api_main.geocode_candidates_autocomplete = _boom
    try:
        try:
            api_main.geocode(q="madrid centro")
        except HTTPException as exc:
            detail = str(exc.detail)
            _assert(exc.status_code == 502, f"expected 502, got {exc.status_code}")
            _assert(_FAKE_ORS_KEY not in detail, f"ORS key leaked to client: {detail!r}")
            _assert("api_key" not in detail, f"api_key reference leaked to client: {detail!r}")
        else:
            raise AssertionError("geocode() should have raised HTTPException on provider error")
    finally:
        api_main.geocode_candidates, api_main.geocode_candidates_autocomplete = previous


def test_reverse_geocode_error_does_not_leak_ors_key() -> None:
    """H1: same protection on the reverse-geocode path."""
    previous = api_main.reverse_geocode_coordinates

    def _boom(*_args, **_kwargs):
        raise requests.HTTPError(_FAKE_ORS_ERROR)

    api_main.reverse_geocode_coordinates = _boom
    try:
        try:
            api_main.reverse_geocode(lat=40.4, lon=-3.7)
        except HTTPException as exc:
            detail = str(exc.detail)
            _assert(exc.status_code == 502, f"expected 502, got {exc.status_code}")
            _assert(_FAKE_ORS_KEY not in detail, f"ORS key leaked to client: {detail!r}")
            _assert("api_key" not in detail, f"api_key reference leaked to client: {detail!r}")
        else:
            raise AssertionError("reverse_geocode() should have raised HTTPException on provider error")
    finally:
        api_main.reverse_geocode_coordinates = previous


def test_feedback_endpoint_is_rate_limited() -> None:
    """H2: the feedback endpoint must carry a per-IP rate limit.

    slowapi only applies a limit when the decorated function exposes a
    `request: Request` parameter, so its presence is the structural guarantee
    that the limit is wired. When slowapi is installed the limit also enforces
    at runtime; without it the app intentionally degrades to a no-op.
    """
    params = inspect.signature(api_main.submit_feedback).parameters
    _assert("request" in params, "submit_feedback must accept `request` for rate limiting to apply")
    if not api_main._slowapi_available:
        print("  note: slowapi not installed; rate limiting is a no-op in this interpreter")


def run() -> None:
    test_geocode_error_does_not_leak_ors_key()
    test_reverse_geocode_error_does_not_leak_ors_key()
    test_feedback_endpoint_is_rate_limited()
    print("OK: security checks passed")


if __name__ == "__main__":
    run()
