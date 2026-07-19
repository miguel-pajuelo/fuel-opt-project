"""Run a focused isolated smoke test against a built FuelOpt onedir bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _free_port() -> int:
    for port in range(8001, 8011):
        with socket.socket() as candidate:
            try:
                candidate.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise AssertionError("No free FuelOpt port is available in 8001-8010")


def _request(url: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(url, timeout=2) as response:
        return response.status, response.read()


def _wait_for_health(base_url: str, process: subprocess.Popen[bytes], timeout: float = 60) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"FuelOpt server exited before health check: {process.returncode}")
        try:
            status, payload = _request(base_url + "/health")
            if status == 200:
                return json.loads(payload.decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = exc
        time.sleep(0.25)
    raise AssertionError(f"FuelOpt health check timed out: {last_error}")


def validate_smoke(bundle: Path) -> None:
    source_bundle = bundle.resolve()
    _assert((source_bundle / "FuelOpt.exe").is_file(), f"Built executable is missing: {source_bundle}")
    source_seed = source_bundle / "_internal" / "resources" / "seed" / "gas_stations.seed.sqlite"
    _assert(source_seed.is_file(), "Packaged seed is missing")
    seed_hash = _sha256(source_seed)

    with tempfile.TemporaryDirectory(prefix="FuelOpt 8B espacio ñ ") as temp_name:
        temp_root = Path(temp_name)
        copied_bundle = temp_root / "Aplicación FuelOpt ñ"
        isolated_localappdata = temp_root / "Datos locales ñ"
        arbitrary_cwd = temp_root / "cwd distinto ñ"
        shutil.copytree(source_bundle, copied_bundle)
        isolated_localappdata.mkdir()
        arbitrary_cwd.mkdir()
        executable = copied_bundle / "FuelOpt.exe"
        port = _free_port()
        base_url = f"http://127.0.0.1:{port}"
        environment = os.environ.copy()
        environment["LOCALAPPDATA"] = str(isolated_localappdata)
        environment["FUELOPT_DIAGNOSTICS"] = "1"
        environment.pop("FUELOPT_PROJECT_ROOT", None)

        process = subprocess.Popen(
            [str(executable), "--server-only", "--host", "127.0.0.1", "--port", str(port)],
            cwd=arbitrary_cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            health = _wait_for_health(base_url, process)
            _assert(
                health.get("status") == "ok" and health.get("service") == "FuelOpt" and health.get("database") == "ok",
                f"Unexpected health identity: {health}",
            )
            status, frontend = _request(base_url + "/")
            _assert(status == 200 and b"FuelOpt" in frontend, "Frontend smoke request failed")
            media_request = urllib.request.Request(base_url + "/static/media/fuelopt-tutorial.mp4", method="HEAD")
            with urllib.request.urlopen(media_request, timeout=2) as media_response:
                _assert(media_response.status == 200, "Packaged tutorial video request failed")
                _assert(media_response.headers.get_content_type() == "video/mp4", "Tutorial video MIME type is not video/mp4")
            active_db = isolated_localappdata / "FuelOpt" / "data" / "db" / "gas_stations.sqlite"
            _assert(active_db.is_file(), "First-start bootstrap did not create the active database")
            shutdown = subprocess.run(
                [str(executable), "--shutdown-existing"],
                cwd=arbitrary_cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
            _assert(shutdown.returncode == 0, f"Cooperative shutdown command failed: {shutdown.returncode}")
            process.wait(timeout=30)
            _assert(process.returncode == 0, f"FuelOpt server shutdown returned {process.returncode}")
            _assert(not (isolated_localappdata / "FuelOpt" / "runtime.json").exists(), "Runtime record survived shutdown")
            _assert(not list(isolated_localappdata.rglob("*.lock")), "Lock survived isolated smoke test")
            _assert(_sha256(copied_bundle / "_internal" / "resources" / "seed" / "gas_stations.seed.sqlite") == seed_hash, "Packaged seed changed during smoke test")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    validate_smoke(args.bundle)
    print("OK: isolated Unicode-path bundle smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
