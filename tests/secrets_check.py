"""H5 secrets-hygiene checks.

Offline, deterministic, and safe: this script NEVER reads the real .env. It
only verifies that .env stays untracked/ignored, that .env.example holds
placeholders (not real secrets), and that packaging does not ship .env.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _git(*args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=str(ROOT), capture_output=True, text=True
        )
    except FileNotFoundError:
        return None


# Keys whose values must never be real in a committed template.
SENSITIVE_KEYS = {
    "ORS_API_KEY",
    "FUELOPT_ADMIN_TOKEN",
    "GMAIL_USER",
    "GMAIL_APP_PASSWORD",
    "FEEDBACK_RECIPIENT",
    "ALERT_WEBHOOK_URL",
    "CORS_ORIGINS",
}

# A value is an acceptable placeholder if it is empty or obviously not real.
_PLACEHOLDER_RE = re.compile(
    r"^(|replace-me|replace-me@example\.com|changeme|your[-_].*|<.*>|.*example.*)$",
    re.IGNORECASE,
)

# Patterns that look like genuine leaked secrets.
_REAL_SECRET_PATTERNS = [
    (re.compile(r"eyJ[A-Za-z0-9_-]{10,}"), "JWT-like token"),
    (re.compile(r"AIza[0-9A-Za-z_-]{20,}"), "Google API key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"gh[pousr]_[0-9A-Za-z]{20,}"), "GitHub token"),
    (re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"), "Slack token"),
]

REQUIRED_EXAMPLE_KEYS = [
    "ORS_API_KEY",
    "FUELOPT_ADMIN_TOKEN",
    "GMAIL_USER",
    "GMAIL_APP_PASSWORD",
    "CORS_ORIGINS",
    "ALERT_WEBHOOK_URL",
    "FUELOPT_ALLOW_LAN",
    "FUELOPT_TRUST_PROXY_HEADERS",
    "FUELOPT_LOG_CLIENT_IP",
]


def _example_pairs() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in _read(".env.example").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        pairs.append((key.strip(), value.strip()))
    return pairs


def test_env_not_tracked() -> None:
    result = _git("ls-files", ".env")
    if result is None:
        print("  note: git unavailable; skipping .env tracked check")
        return
    if result.returncode != 0:
        print("  note: not a git repository; skipping .env tracked check")
        return
    _assert(result.stdout.strip() == "", f".env must not be tracked by git: {result.stdout!r}")


def test_env_is_ignored() -> None:
    result = _git("check-ignore", ".env")
    if result is None or result.returncode == 128:
        print("  note: git unavailable/not a repo; skipping .env ignore check")
        return
    _assert(
        result.returncode == 0 and result.stdout.strip().endswith(".env"),
        ".env must be ignored by .gitignore.",
    )


def test_env_example_has_required_keys() -> None:
    keys = {key for key, _ in _example_pairs()}
    for required in REQUIRED_EXAMPLE_KEYS:
        _assert(required in keys, f".env.example is missing required key: {required}")


def test_env_example_has_no_real_secrets() -> None:
    text = _read(".env.example")
    for pattern, label in _REAL_SECRET_PATTERNS:
        match = pattern.search(text)
        _assert(match is None, f".env.example contains a {label}-shaped value; use a placeholder.")
    for key, value in _example_pairs():
        if key in SENSITIVE_KEYS:
            _assert(
                _PLACEHOLDER_RE.fullmatch(value) is not None,
                f".env.example value for {key} looks real; use an empty or placeholder value.",
            )


def test_packaging_does_not_ship_env() -> None:
    pkg = _read("scripts/package_release.cmd")
    # The real .env must never be a copy source (only .env.example may be copied).
    for line in re.findall(r"^\s*copy\b[^\n]*", pkg, re.IGNORECASE | re.MULTILINE):
        neutral = line.replace(".env.example", "").replace(".env.local", "")
        _assert(".env" not in neutral, f"package_release.cmd appears to copy the real .env: {line.strip()}")
    # Defense in depth: directory copies explicitly exclude .env.
    _assert(
        "/XF" in pkg and '".env"' in pkg,
        "package_release.cmd should exclude .env from robocopy via /XF.",
    )


def run() -> None:
    test_env_not_tracked()
    test_env_is_ignored()
    test_env_example_has_required_keys()
    test_env_example_has_no_real_secrets()
    test_packaging_does_not_ship_env()
    print("OK: secrets hygiene checks passed")


if __name__ == "__main__":
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    run()
