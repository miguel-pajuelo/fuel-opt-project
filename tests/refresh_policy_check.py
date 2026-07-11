from __future__ import annotations

import inspect
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.storage.publish import cleanup_old_backups, publish_sqlite_candidate
from app.api import main as api_main
import fuelopt_launcher
from fuelopt_launcher import DEFAULT_HOST, LAN_HOST, resolve_bind_host
from scripts import refresh_catalog as refresh_catalog_script
from scripts import rebuild_station_catalog
from scripts.refresh_catalog import _publish_snapshot_candidate


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _sample_minetur_items() -> list[dict[str, str]]:
    return [
        {
            "IDEESS": "1001",
            "Rotulo": "REPSOL",
            "Direccion": "Calle Uno",
            "C.P.": "28001",
            "Municipio": "Madrid",
            "Provincia": "Madrid",
            "Latitud": "40,4200",
            "Longitud (WGS84)": "-3,7000",
            "Precio Gasoleo A": "1,500",
        }
    ]


def _create_sqlite(path: Path, value: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        conn.execute("INSERT INTO marker VALUES (?)", (value,))
        conn.commit()
    finally:
        conn.close()


def test_candidate_snapshot_does_not_replace_active_before_publish() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        active_snapshot = root / "minetur_snapshot.json"
        candidate_snapshot = root / "minetur_snapshot.next.json"
        active_snapshot.write_text(
            json.dumps({"source": "MINETUR", "fetched_at": "old", "items": []}),
            encoding="utf-8",
        )
        original_fetch = rebuild_station_catalog.fetch_minetur_items
        rebuild_station_catalog.fetch_minetur_items = _sample_minetur_items
        try:
            args = SimpleNamespace(
                source="minetur",
                snapshot=active_snapshot,
                prices_cache=root / "prices.json",
                ballenoil_cache=root / "ballenoil.txt",
                brands=None,
            )
            (stations, prices), source, warnings = rebuild_station_catalog.load_catalog(
                args,
                snapshot_write_path=candidate_snapshot,
            )
        finally:
            rebuild_station_catalog.fetch_minetur_items = original_fetch

        _assert(source == "MINETUR", source)
        _assert(warnings == [], warnings)
        _assert(len(stations) == 1, stations)
        _assert(len(prices) == 1, prices)
        _assert(json.loads(active_snapshot.read_text(encoding="utf-8"))["fetched_at"] == "old", "active snapshot changed early")
        _assert(candidate_snapshot.exists(), "candidate snapshot was not written")


def test_publish_snapshot_candidate_replaces_active_once_valid() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        active_snapshot = root / "minetur_snapshot.json"
        candidate_snapshot = root / "minetur_snapshot.next.json"
        active_snapshot.write_text('{"version": "old"}', encoding="utf-8")
        candidate_snapshot.write_text('{"version": "new"}', encoding="utf-8")

        replaced = _publish_snapshot_candidate(candidate_snapshot, active_snapshot)

        _assert(replaced is True, replaced)
        _assert(json.loads(active_snapshot.read_text(encoding="utf-8"))["version"] == "new", "active snapshot not replaced")
        _assert(not candidate_snapshot.exists(), "candidate snapshot should be consumed")


def test_zero_backup_retention_removes_previous_sqlite_copy() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        active_db = root / "gas_stations.sqlite"
        candidate_db = root / "gas_stations.next.sqlite"
        _create_sqlite(active_db, "old")
        _create_sqlite(candidate_db, "new")

        backup = publish_sqlite_candidate(candidate_db, active_db)
        removed = cleanup_old_backups(active_db, keep=0)

        _assert(active_db.exists(), "active DB missing after publish")
        _assert(backup is not None, "expected temporary backup")
        _assert(not backup.exists(), "backup should be removed with keep=0")
        _assert(backup in removed, removed)
        _assert(not candidate_db.exists(), "candidate DB should be consumed")


def _read_marker(path: Path) -> str:
    conn = sqlite3.connect(path)
    try:
        row = conn.execute("SELECT value FROM marker").fetchone()
        return str(row[0]) if row else ""
    finally:
        conn.close()


def test_failed_refresh_does_not_replace_active_db() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        active_db = root / "gas_stations.sqlite"
        active_snapshot = root / "minetur_snapshot.json"
        report_path = root / "catalog_refresh_report.json"
        lock_path = root / "catalog_refresh.lock"
        _create_sqlite(active_db, "old")
        active_snapshot.write_text('{"version": "old"}', encoding="utf-8")

        original_load_catalog = refresh_catalog_script.load_catalog
        original_argv = sys.argv[:]

        def fail_load_catalog(*_: object, **__: object):
            raise RuntimeError("planned refresh failure")

        refresh_catalog_script.load_catalog = fail_load_catalog
        sys.argv = [
            "refresh_catalog.py",
            "--db",
            str(active_db),
            "--snapshot",
            str(active_snapshot),
            "--write-report",
            str(report_path),
            "--lock-file",
            str(lock_path),
            "--source",
            "auto",
        ]
        try:
            returncode = refresh_catalog_script.main()
        finally:
            refresh_catalog_script.load_catalog = original_load_catalog
            sys.argv = original_argv

        _assert(returncode == 1, returncode)
        _assert(_read_marker(active_db) == "old", "active DB changed after failed refresh")
        _assert(json.loads(active_snapshot.read_text(encoding="utf-8"))["version"] == "old", "active snapshot changed")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        _assert(report["refresh_status"] == "failed", report)


def test_launcher_has_no_stale_startup_refresh_policy() -> None:
    _assert(not hasattr(fuelopt_launcher, "catalog_refresh_due"), "stale due helper should not exist")
    _assert(not hasattr(fuelopt_launcher, "should_start_refresh_worker"), "startup freshness trigger should not exist")
    _assert(not hasattr(fuelopt_launcher, "run_refresh_scheduler"), "separate launcher scheduler should not exist")


def test_launcher_startup_does_not_refresh_by_default() -> None:
    calls: list[str] = []
    originals = {
        "server_ready": fuelopt_launcher.server_ready,
        "start_server": fuelopt_launcher.start_server,
        "wait_for_server": fuelopt_launcher.wait_for_server,
        "start_refresh_worker": fuelopt_launcher.start_refresh_worker,
        "log": fuelopt_launcher.log,
    }
    try:
        fuelopt_launcher.server_ready = lambda _base_url: True
        fuelopt_launcher.start_server = lambda *_args, **_kwargs: calls.append("start_server")
        fuelopt_launcher.wait_for_server = lambda _base_url: True
        fuelopt_launcher.start_refresh_worker = lambda _base_url: calls.append("refresh")
        fuelopt_launcher.log = lambda _message: None
        result = fuelopt_launcher.run_launcher(
            SimpleNamespace(
                host=DEFAULT_HOST,
                port=8123,
                no_browser=True,
                browser_host=DEFAULT_HOST,
                no_refresh=False,
                refresh=False,
            )
        )
    finally:
        fuelopt_launcher.server_ready = originals["server_ready"]
        fuelopt_launcher.start_server = originals["start_server"]
        fuelopt_launcher.wait_for_server = originals["wait_for_server"]
        fuelopt_launcher.start_refresh_worker = originals["start_refresh_worker"]
        fuelopt_launcher.log = originals["log"]

    _assert(result == 0, result)
    _assert("refresh" not in calls, calls)


def test_explicit_launcher_refresh_remains_available() -> None:
    calls: list[str] = []
    originals = {
        "server_ready": fuelopt_launcher.server_ready,
        "start_refresh_worker": fuelopt_launcher.start_refresh_worker,
        "log": fuelopt_launcher.log,
    }
    try:
        fuelopt_launcher.server_ready = lambda _base_url: True
        fuelopt_launcher.start_refresh_worker = lambda base_url: calls.append(base_url)
        fuelopt_launcher.log = lambda _message: None
        result = fuelopt_launcher.run_launcher(
            SimpleNamespace(
                host=DEFAULT_HOST,
                port=8124,
                no_browser=True,
                browser_host=DEFAULT_HOST,
                no_refresh=False,
                refresh=True,
            )
        )
    finally:
        fuelopt_launcher.server_ready = originals["server_ready"]
        fuelopt_launcher.start_refresh_worker = originals["start_refresh_worker"]
        fuelopt_launcher.log = originals["log"]

    _assert(result == 0, result)
    _assert(calls == ["http://127.0.0.1:8124"], calls)


def test_web_process_has_no_automatic_refresh_scheduler() -> None:
    api_source = (ROOT / "app" / "api" / "main.py").read_text(encoding="utf-8")
    launcher = (ROOT / "fuelopt_launcher.py").read_text(encoding="utf-8")

    for forbidden in ("_catalog_refresh_scheduler_loop", "start_catalog_refresh_scheduler", "CATALOG_REFRESH_TIMEZONE"):
        _assert(forbidden not in api_source, f"automatic web scheduler remains: {forbidden}")
    _assert("--refresh-scheduler" not in launcher, "launcher scheduler CLI must not exist")


def test_request_paths_are_catalog_read_only() -> None:
    from app.api import main as api_main

    read_only_handlers = [
        api_main.health,
        api_main.fuels,
        api_main.brands,
        api_main.brands_raw,
        api_main.catalog_status,
        api_main.prices_status,
        api_main.stations,
        api_main.optimize,
        api_main.optimize_endpoint,
    ]
    forbidden = ("subprocess.run", "replace_catalog", "run_catalog_refresh_once", "refresh_catalog(")
    for handler in read_only_handlers:
        source = inspect.getsource(handler)
        for token in forbidden:
            _assert(token not in source, f"{handler.__name__} contains catalog write trigger {token}")


def test_stale_warning_policy_does_not_refresh() -> None:
    from app.api import warnings as api_warnings

    source = inspect.getsource(api_warnings.build_optimize_warnings)
    for token in ("subprocess.run", "replace_catalog", "refresh_catalog", "run_catalog_refresh_once"):
        _assert(token not in source, f"warning policy contains refresh trigger {token}")


def test_manual_refresh_endpoint_remains_distinct() -> None:
    source = inspect.getsource(api_main.refresh_catalog)
    runner_source = inspect.getsource(api_main._run_catalog_refresh_pipeline)
    _assert("_run_catalog_refresh_pipeline" in source, "manual refresh endpoint should use the shared refresh runner")
    _assert("subprocess.run" in runner_source, "shared refresh runner should still run the safe refresh command")
    _assert("_require_catalog_refresh_auth" in source or "Depends(_require_catalog_refresh_auth)" in source, "manual refresh should stay protected")


def test_manual_refresh_pipeline_prevents_concurrent_runs() -> None:
    acquired = api_main._refresh_lock.acquire(blocking=False)
    _assert(acquired, "test could not acquire refresh lock")
    try:
        result = api_main._run_catalog_refresh_pipeline()
    finally:
        api_main._refresh_lock.release()

    _assert(result.get("locked") is True, result)


def test_launcher_defaults_to_localhost() -> None:
    _assert(DEFAULT_HOST == "127.0.0.1", f"launcher default host should be localhost, got {DEFAULT_HOST}")
    _assert(resolve_bind_host(DEFAULT_HOST) == "127.0.0.1", "default bind host should stay local")


def test_launcher_lan_is_explicit() -> None:
    _assert(resolve_bind_host(DEFAULT_HOST, lan=True) == LAN_HOST, "explicit LAN mode should bind to 0.0.0.0")
    _assert(resolve_bind_host("192.168.1.10") == "192.168.1.10", "custom host should be preserved")


def _restore_env_var(name: str, original: str | None) -> None:
    if original is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = original


def test_launcher_lan_env_truthy_values() -> None:
    for value in ("1", "true", "yes", "on", "TRUE", "Yes"):
        original = os.environ.get("FUELOPT_ALLOW_LAN")
        try:
            os.environ["FUELOPT_ALLOW_LAN"] = value
            _assert(
                resolve_bind_host(DEFAULT_HOST) == LAN_HOST,
                f"FUELOPT_ALLOW_LAN={value!r} should enable LAN bind",
            )
        finally:
            _restore_env_var("FUELOPT_ALLOW_LAN", original)


def test_launcher_lan_env_falsy_values() -> None:
    for value in ("", "0", "false", "no", "off"):
        original = os.environ.get("FUELOPT_ALLOW_LAN")
        try:
            os.environ["FUELOPT_ALLOW_LAN"] = value
            _assert(
                resolve_bind_host(DEFAULT_HOST) == DEFAULT_HOST,
                f"FUELOPT_ALLOW_LAN={value!r} should keep localhost bind",
            )
        finally:
            _restore_env_var("FUELOPT_ALLOW_LAN", original)


def run() -> None:
    test_candidate_snapshot_does_not_replace_active_before_publish()
    test_publish_snapshot_candidate_replaces_active_once_valid()
    test_zero_backup_retention_removes_previous_sqlite_copy()
    test_failed_refresh_does_not_replace_active_db()
    test_launcher_has_no_stale_startup_refresh_policy()
    test_launcher_startup_does_not_refresh_by_default()
    test_explicit_launcher_refresh_remains_available()
    test_web_process_has_no_automatic_refresh_scheduler()
    test_request_paths_are_catalog_read_only()
    test_stale_warning_policy_does_not_refresh()
    test_manual_refresh_endpoint_remains_distinct()
    test_manual_refresh_pipeline_prevents_concurrent_runs()
    test_launcher_defaults_to_localhost()
    test_launcher_lan_is_explicit()
    test_launcher_lan_env_truthy_values()
    test_launcher_lan_env_falsy_values()
    print("OK: refresh retention checks passed")


if __name__ == "__main__":
    run()
