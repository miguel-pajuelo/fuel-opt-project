from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.storage.publish import cleanup_old_backups, publish_sqlite_candidate
from fuelopt_launcher import DEFAULT_HOST, LAN_HOST, catalog_refresh_due, resolve_bind_host
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


def test_launcher_skips_refresh_when_catalog_is_recent() -> None:
    now = datetime(2026, 4, 23, 12, 0, tzinfo=timezone.utc)
    due, reason = catalog_refresh_due(
        {
            "built_at": (now - timedelta(hours=3, minutes=59)).isoformat(),
            "station_count": 1,
        },
        now=now,
    )
    _assert(due is False, reason)


def test_launcher_refreshes_when_catalog_is_older_than_four_hours() -> None:
    now = datetime(2026, 4, 23, 12, 0, tzinfo=timezone.utc)
    due, reason = catalog_refresh_due(
        {
            "built_at": (now - timedelta(hours=4, seconds=1)).isoformat(),
            "station_count": 1,
        },
        now=now,
    )
    _assert(due is True, reason)


def test_launcher_refreshes_when_catalog_timestamp_is_missing() -> None:
    due, reason = catalog_refresh_due({"built_at": "", "station_count": 1})
    _assert(due is True, reason)


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
    test_launcher_skips_refresh_when_catalog_is_recent()
    test_launcher_refreshes_when_catalog_is_older_than_four_hours()
    test_launcher_refreshes_when_catalog_timestamp_is_missing()
    test_launcher_defaults_to_localhost()
    test_launcher_lan_is_explicit()
    test_launcher_lan_env_truthy_values()
    test_launcher_lan_env_falsy_values()
    print("OK: refresh retention checks passed")


if __name__ == "__main__":
    run()
