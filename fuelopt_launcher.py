from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


DEFAULT_HOST = "127.0.0.1"
LAN_HOST = "0.0.0.0"
DEFAULT_PORT = 8001
DEFAULT_BROWSER_HOST = "127.0.0.1"
HEALTH_TIMEOUT_SEC = 35
CATALOG_REFRESH_INTERVAL = timedelta(hours=4)


def _looks_like_project_root(path: Path) -> bool:
    return (
        (path / "app").is_dir()
        and (path / "static" / "index.html").is_file()
        and (path / "data").is_dir()
    )


def project_root() -> Path:
    env_root = os.getenv("FUELOPT_PROJECT_ROOT")
    if env_root:
        candidate = Path(env_root).resolve()
        if _looks_like_project_root(candidate):
            return candidate

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates = (
            exe_dir,
            exe_dir / "FuelOptApp",
            exe_dir.parent,
            exe_dir.parent / "FuelOptApp",
        )
        for candidate in candidates:
            if _looks_like_project_root(candidate):
                return candidate
        return exe_dir
    return Path(__file__).resolve().parent


ROOT = project_root()
REPORT_DIR = ROOT / "data" / "reports"
LOG_PATH = REPORT_DIR / "launcher.log"
LOGGER = logging.getLogger("fuelopt_launcher")


def configure_logging() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if LOGGER.handlers:
        return
    handler = RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def log(message: str) -> None:
    configure_logging()
    LOGGER.info(message)


def self_command(*args: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, str(Path(__file__).resolve()), *args]


def creation_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def managed_env() -> dict[str, str]:
    env = os.environ.copy()
    env["FUELOPT_PROJECT_ROOT"] = str(ROOT)
    if getattr(sys, "frozen", False):
        # One-file PyInstaller children must unpack their own runtime directory.
        # Otherwise the short-lived launcher can remove _MEI files still needed
        # by the long-lived server or refresh process.
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def request_json(method: str, url: str, timeout: int = 10) -> dict[str, Any]:
    request = urllib.request.Request(url, method=method)
    if method.upper() == "POST":
        request.add_header("Content-Type", "application/json")
        data = b"{}"
    else:
        data = None
    with urllib.request.urlopen(request, data=data, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def parse_catalog_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def catalog_refresh_due(status: dict[str, Any], now: datetime | None = None) -> tuple[bool, str]:
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    built_at = parse_catalog_timestamp(status.get("built_at"))
    station_count = int(status.get("station_count") or 0)
    if station_count <= 0:
        return True, "catalog has no stations"
    if built_at is None:
        return True, "catalog built_at is missing or invalid"
    age = current_time - built_at
    if age >= CATALOG_REFRESH_INTERVAL:
        return True, f"catalog is stale age_seconds={int(age.total_seconds())}"
    remaining = CATALOG_REFRESH_INTERVAL - age
    return False, f"catalog is fresh remaining_seconds={int(remaining.total_seconds())}"


def should_start_refresh_worker(base_url: str) -> bool:
    try:
        status = request_json("GET", f"{base_url}/catalog/status", timeout=10)
    except Exception as exc:
        log(f"catalog freshness check failed, refresh will run: {exc}")
        return True
    due, reason = catalog_refresh_due(status)
    if due:
        log(f"catalog refresh due: {reason}")
        return True
    log(f"catalog refresh skipped: {reason}")
    return False


def server_ready(base_url: str) -> bool:
    try:
        payload = request_json("GET", f"{base_url}/health", timeout=3)
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False
    return payload.get("status") == "ok"


def wait_for_server(base_url: str, timeout_sec: int = HEALTH_TIMEOUT_SEC) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if server_ready(base_url):
            return True
        time.sleep(0.5)
    return False


def start_server(host: str, port: int) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    log_file = (REPORT_DIR / "launcher_server.log").open("a", encoding="utf-8")
    subprocess.Popen(
        self_command("--server-only", "--host", host, "--port", str(port)),
        cwd=ROOT,
        env=managed_env(),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creation_flags(),
    )
    log(f"server process requested host={host} port={port}")


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
    except OSError:
        return DEFAULT_BROWSER_HOST


def browser_base_url(browser_host: str, port: int) -> str:
    host = lan_ip() if browser_host == "lan" else browser_host
    return f"http://{host}:{port}"


def allow_lan_from_env() -> bool:
    value = os.getenv("FUELOPT_ALLOW_LAN", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def resolve_bind_host(requested_host: str, lan: bool = False) -> str:
    if requested_host != DEFAULT_HOST:
        return requested_host
    if lan or allow_lan_from_env():
        return LAN_HOST
    return requested_host


def refresh_worker(base_url: str) -> int:
    log("background refresh started")
    try:
        payload = request_json("POST", f"{base_url}/catalog/refresh", timeout=1800)
    except Exception as exc:
        log(f"background refresh failed: {exc}")
        return 1
    refresh = payload.get("refresh") if isinstance(payload, dict) else {}
    status = refresh.get("refresh_status") if isinstance(refresh, dict) else payload.get("returncode")
    log(f"background refresh finished status={status}")
    return 0


def start_refresh_worker(base_url: str) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    log_file = (REPORT_DIR / "launcher_refresh.log").open("a", encoding="utf-8")
    subprocess.Popen(
        self_command("--refresh-only", "--base-url", base_url),
        cwd=ROOT,
        env=managed_env(),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creation_flags(),
    )
    log("background refresh process requested")


def run_server(host: str, port: int) -> int:
    os.environ["FUELOPT_PROJECT_ROOT"] = str(ROOT)
    os.chdir(ROOT)
    import uvicorn
    from app.api.main import app

    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


def run_launcher(args: argparse.Namespace) -> int:
    os.environ["FUELOPT_PROJECT_ROOT"] = str(ROOT)
    base_url = f"http://127.0.0.1:{args.port}"
    if not server_ready(base_url):
        start_server(args.host, args.port)
        if not wait_for_server(base_url):
            log("server did not become healthy before timeout")
            return 1
    else:
        log("existing server is already healthy")

    if not args.no_browser:
        url = browser_base_url(args.browser_host, args.port)
        webbrowser.open(url)
        log(f"browser opened url={url}")

    if not args.no_refresh and should_start_refresh_worker(base_url):
        start_refresh_worker(base_url)

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FuelOpt local launcher.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Server bind host. Defaults to localhost.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port.")
    parser.add_argument(
        "--browser-host",
        default=DEFAULT_BROWSER_HOST,
        help="Host opened in the browser. Use 'lan' to open this machine's LAN IP.",
    )
    parser.add_argument("--lan", action="store_true", help="Allow LAN access by binding the server to 0.0.0.0.")
    parser.add_argument("--no-browser", action="store_true", help="Start server without opening the browser.")
    parser.add_argument("--no-refresh", action="store_true", help="Do not request a background data refresh.")
    parser.add_argument("--server-only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--refresh-only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--base-url", default=f"http://127.0.0.1:{DEFAULT_PORT}", help=argparse.SUPPRESS)
    args = parser.parse_args()
    lan_enabled = args.lan or allow_lan_from_env()
    args.host = resolve_bind_host(args.host, lan=args.lan)
    if lan_enabled and args.browser_host == DEFAULT_BROWSER_HOST:
        args.browser_host = "lan"
    return args


def main() -> int:
    if "--catalog-refresh-script" in sys.argv:
        marker_index = sys.argv.index("--catalog-refresh-script")
        sys.argv = [sys.argv[0], *sys.argv[marker_index + 1:]]
        from scripts.refresh_catalog import main as refresh_catalog_main

        return refresh_catalog_main()

    args = parse_args()
    if args.server_only:
        return run_server(args.host, args.port)
    if args.refresh_only:
        return refresh_worker(args.base_url)
    return run_launcher(args)


if __name__ == "__main__":
    raise SystemExit(main())
