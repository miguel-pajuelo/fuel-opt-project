from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.bootstrap import bootstrap_user_data, snapshot_timestamp
from app.models import Price, Station
from app.paths import resolve_app_paths
from app.storage.database import open_db_readonly, replace_catalog, sqlite_file_uri
from app.storage.publish import (
    checkpoint_sqlite,
    cleanup_sqlite_sidecars,
    copy_sqlite_database,
    publish_sqlite_candidate,
)
from app.storage.validation import CatalogValidationRules, validate_catalog_db


RULES = CatalogValidationRules(min_stations=1, min_prices=2, max_unknown_brand_ratio=1.0)


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _station() -> Station:
    return Station(
        station_id="1001",
        brand="REPSOL",
        name="Test station",
        address="Calle Uno",
        postal_code="28001",
        municipality="Madrid",
        province="Madrid",
        lat=40.4,
        lon=-3.7,
        source="TEST",
        brand_confidence=1.0,
    )


def _create_db(path: Path, timestamp: str, marker: str) -> None:
    station = _station()
    replace_catalog(
        path,
        [station],
        [
            Price(station.station_id, "gasoleo_a", 1.5, timestamp, "TEST"),
            Price(station.station_id, "gasolina_95", 1.6, timestamp, "TEST"),
        ],
        metadata={
            "source_fetched_at": timestamp,
            "built_at": timestamp,
            "refresh_status": "ok",
            "test_marker": marker,
        },
    )
    checkpoint_sqlite(path)
    cleanup_sqlite_sidecars(path)


def _marker(path: Path) -> str:
    with open_db_readonly(path) as conn:
        row = conn.execute("SELECT value FROM catalog_metadata WHERE key = 'test_marker'").fetchone()
    return str(row[0]) if row else ""


def _snapshot(path: Path, fetched_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "source": "MINETUR",
                "fetched_at": fetched_at,
                "items": [
                    {
                        "IDEESS": "1001",
                        "Rótulo": "REPSOL",
                        "Dirección": "Calle Uno",
                        "C.P.": "28001",
                        "Municipio": "Madrid",
                        "Provincia": "Madrid",
                        "Latitud": "40,4000",
                        "Longitud (WGS84)": "-3,7000",
                        "Precio Gasoleo A": "1,500",
                        "Precio Gasolina 95 E5": "1,600",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _paths(base: Path):
    resource = base / "installed"
    user = base / "user"
    (resource / "resources" / "seed").mkdir(parents=True, exist_ok=True)
    (resource / "resources" / "snapshot").mkdir(parents=True, exist_ok=True)
    # Installed resources exist before AppPaths is resolved. Individual tests
    # may populate this placeholder with a valid seed or leave it invalid to
    # exercise snapshot reconstruction.
    (resource / "resources" / "seed" / "gas_stations.seed.sqlite").touch()
    return resolve_app_paths(
        environ={"FUELOPT_PROJECT_ROOT": str(resource), "FUELOPT_USER_DATA_ROOT": str(user)},
        module_file=resource / "app" / "paths.py",
        frozen=False,
    )


def test_first_run_copies_seed_without_mutating_it() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(Path(tmp) / "ruta con espacios # porcentaje % y á")
        _create_db(paths.seed_db_path, "2026-01-01T00:00:00+00:00", "seed")
        _snapshot(paths.installed_snapshot_path, "2026-01-01T00:00:00+00:00")
        before_hash = hashlib.sha256(paths.seed_db_path.read_bytes()).hexdigest()

        result = bootstrap_user_data(paths, environ={}, rules=RULES)

        _assert(result.database_action == "database_initialized_seed", result)
        _assert(_marker(paths.user_db_path) == "seed", "seed was not copied")
        _assert(validate_catalog_db(paths.user_db_path, RULES, readonly=True).ok, "active database invalid")
        _assert(hashlib.sha256(paths.seed_db_path.read_bytes()).hexdigest() == before_hash, "seed was modified")
        _assert(not Path(str(paths.seed_db_path) + "-wal").exists(), "seed WAL was created")
        _assert(not Path(str(paths.seed_db_path) + "-shm").exists(), "seed SHM was created")


def test_immutable_seed_copy_uses_encoded_windows_safe_uri() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "FuelOpt # 100% á"
        source = root / "seed data" / "gas stations.sqlite"
        destination = root / "user data" / "active.sqlite"
        _create_db(source, "2026-01-01T00:00:00+00:00", "immutable-seed")
        uri = sqlite_file_uri(source, mode="ro", immutable=True)

        copy_sqlite_database(source, destination, immutable_source=True)

        _assert("mode=ro&immutable=1" in uri, uri)
        _assert("%20" in uri and "%23" in uri and "%25" in uri, uri)
        _assert(_marker(destination) == "immutable-seed", "encoded immutable seed copy failed")
        _assert(not Path(str(source) + "-wal").exists(), "immutable copy created source WAL")
        _assert(not Path(str(source) + "-shm").exists(), "immutable copy created source SHM")


def test_normal_copy_reads_committed_legacy_wal() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "legacy.sqlite"
        destination = root / "migrated.sqlite"
        source.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(source)
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA wal_autocheckpoint = 0")
            connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
            connection.execute("INSERT INTO marker VALUES ('committed-in-wal')")
            connection.commit()
            wal_path = Path(str(source) + "-wal")
            _assert(wal_path.exists() and wal_path.stat().st_size > 0, "test did not retain a WAL")

            copy_sqlite_database(source, destination)
        finally:
            connection.close()

        copied = sqlite3.connect(destination)
        try:
            value = copied.execute("SELECT value FROM marker").fetchone()[0]
        finally:
            copied.close()
        _assert(value == "committed-in-wal", "normal legacy copy ignored committed WAL content")


def test_project_root_database_fallback_is_not_marked_immutable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        resource = base / "legacy project"
        legacy_db = resource / "data" / "db" / "gas_stations.sqlite"
        _create_db(legacy_db, "2026-01-01T00:00:00+00:00", "project-root")
        paths = resolve_app_paths(
            environ={"FUELOPT_PROJECT_ROOT": str(resource), "FUELOPT_USER_DATA_ROOT": str(base / "user")},
            module_file=resource / "app" / "paths.py",
            frozen=False,
        )
        _assert(paths.seed_db_path == legacy_db, paths)
        _assert(paths.seed_db_is_immutable is False, "PROJECT_ROOT/data/db must remain WAL-aware")


def test_packaged_seed_with_sidecar_falls_back_to_snapshot() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(Path(tmp))
        _create_db(paths.seed_db_path, "2026-01-01T00:00:00+00:00", "unsafe-seed")
        _snapshot(paths.installed_snapshot_path, "2026-02-01T00:00:00+00:00")
        seed_wal = Path(str(paths.seed_db_path) + "-wal")
        seed_wal.write_bytes(b"unexpected installed sidecar")

        result = bootstrap_user_data(paths, environ={}, rules=RULES)

        _assert(result.database_action == "database_rebuilt_snapshot", result)
        _assert(seed_wal.read_bytes() == b"unexpected installed sidecar", "bootstrap modified seed sidecar")


def test_valid_active_database_is_never_replaced_by_seed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(Path(tmp))
        _create_db(paths.seed_db_path, "2026-12-01T00:00:00+00:00", "newer-seed")
        _create_db(paths.user_db_path, "2026-06-01T00:00:00+00:00", "active")
        _snapshot(paths.installed_snapshot_path, "2026-12-01T00:00:00+00:00")

        result = bootstrap_user_data(paths, environ={}, rules=RULES)

        _assert(result.database_action == "database_kept", result)
        _assert(_marker(paths.user_db_path) == "active", "newer seed overwrote active database")
        _assert(not paths.previous_db_path.exists(), "keeping active should not create a backup")


def test_newer_external_legacy_database_replaces_active_with_backup() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        paths = _paths(base)
        _create_db(paths.seed_db_path, "2025-01-01T00:00:00+00:00", "seed")
        _snapshot(paths.installed_snapshot_path, "2025-01-01T00:00:00+00:00")
        _create_db(paths.user_db_path, "2026-01-01T00:00:00+00:00", "active-old")
        legacy = base / "legacy"
        legacy_db = legacy / "data" / "db" / "gas_stations.sqlite"
        _create_db(legacy_db, "2026-02-01T00:00:00+00:00", "legacy-new")

        result = bootstrap_user_data(paths, explicit_legacy_root=legacy, environ={}, rules=RULES)

        _assert(result.database_action == "database_migrated_newer_legacy", result)
        _assert(_marker(paths.user_db_path) == "legacy-new", "newer legacy database was not selected")
        _assert(_marker(paths.previous_db_path) == "active-old", "last active database was not backed up")


def test_older_external_legacy_database_does_not_replace_active() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        paths = _paths(base)
        _create_db(paths.seed_db_path, "2025-01-01T00:00:00+00:00", "seed")
        _snapshot(paths.installed_snapshot_path, "2025-01-01T00:00:00+00:00")
        _create_db(paths.user_db_path, "2026-03-01T00:00:00+00:00", "active-new")
        legacy = base / "legacy"
        _create_db(legacy / "data" / "db" / "gas_stations.sqlite", "2026-02-01T00:00:00+00:00", "legacy-old")

        result = bootstrap_user_data(paths, explicit_legacy_root=legacy, environ={}, rules=RULES)

        _assert(result.database_action == "database_kept", result)
        _assert(_marker(paths.user_db_path) == "active-new", "older legacy database replaced active")


def test_missing_database_is_rebuilt_offline_from_snapshot() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(Path(tmp))
        _snapshot(paths.installed_snapshot_path, "2026-04-01T00:00:00+00:00")

        result = bootstrap_user_data(paths, environ={}, rules=RULES)

        _assert(result.database_action == "database_rebuilt_snapshot", result)
        _assert(result.database_source == "snapshot", result)
        _assert(validate_catalog_db(paths.user_db_path, RULES, readonly=True).ok, "offline rebuild invalid")


def test_newer_user_snapshot_is_not_overwritten() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(Path(tmp))
        _create_db(paths.seed_db_path, "2026-01-01T00:00:00+00:00", "seed")
        _snapshot(paths.installed_snapshot_path, "2026-01-01T00:00:00+00:00")
        _snapshot(paths.user_snapshot_path, "2026-05-01T00:00:00+00:00")

        result = bootstrap_user_data(paths, environ={}, rules=RULES)

        _assert(result.snapshot_action == "snapshot_kept", result)
        timestamp = snapshot_timestamp(paths.user_snapshot_path)
        _assert(timestamp is not None and timestamp.month == 5, timestamp)


def test_legacy_logs_are_copied_once_without_overwrite() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        paths = _paths(base)
        _create_db(paths.seed_db_path, "2026-01-01T00:00:00+00:00", "seed")
        _snapshot(paths.installed_snapshot_path, "2026-01-01T00:00:00+00:00")
        legacy = base / "legacy"
        legacy.mkdir(parents=True)
        (legacy / ".env").write_text("# legacy root marker\n", encoding="utf-8")
        reports = legacy / "data" / "reports"
        reports.mkdir(parents=True)
        (reports / "launcher.log").write_text("legacy log\n", encoding="utf-8")

        first = bootstrap_user_data(paths, explicit_legacy_root=legacy, environ={}, rules=RULES)
        second = bootstrap_user_data(paths, explicit_legacy_root=legacy, environ={}, rules=RULES)

        _assert(first.logs_action == "logs_imported", first)
        _assert(second.logs_action == "logs_already_imported", second)
        copies = list(paths.logs_dir.glob("legacy-import-*/launcher.log"))
        _assert(len(copies) == 1 and copies[0].read_text(encoding="utf-8") == "legacy log\n", copies)


def test_failed_atomic_replace_preserves_active_database() -> None:
    from app.storage import publish as publish_module

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        active = root / "active.sqlite"
        candidate = root / "candidate.sqlite"
        backup = root / "previous.sqlite"
        _create_db(active, "2026-01-01T00:00:00+00:00", "active")
        _create_db(candidate, "2026-02-01T00:00:00+00:00", "candidate")
        original_replace = publish_module.os.replace

        def fail_candidate_swap(source: Path, destination: Path) -> None:
            if Path(source) == candidate and Path(destination) == active:
                raise PermissionError("simulated Windows lock")
            original_replace(source, destination)

        publish_module.os.replace = fail_candidate_swap
        try:
            try:
                publish_sqlite_candidate(candidate, active, backup_path=backup)
            except PermissionError:
                pass
            else:
                raise AssertionError("simulated swap failure should propagate")
        finally:
            publish_module.os.replace = original_replace

        _assert(_marker(active) == "active", "active database was lost after swap failure")
        _assert(_marker(backup) == "active", "recoverable backup was not created")
        _assert(_marker(candidate) == "candidate", "candidate should remain for diagnostics")


def run() -> None:
    test_first_run_copies_seed_without_mutating_it()
    test_immutable_seed_copy_uses_encoded_windows_safe_uri()
    test_normal_copy_reads_committed_legacy_wal()
    test_project_root_database_fallback_is_not_marked_immutable()
    test_packaged_seed_with_sidecar_falls_back_to_snapshot()
    test_valid_active_database_is_never_replaced_by_seed()
    test_newer_external_legacy_database_replaces_active_with_backup()
    test_older_external_legacy_database_does_not_replace_active()
    test_missing_database_is_rebuilt_offline_from_snapshot()
    test_newer_user_snapshot_is_not_overwritten()
    test_legacy_logs_are_copied_once_without_overwrite()
    test_failed_atomic_replace_preserves_active_database()
    print("OK: bootstrap and user-data migration checks passed")


if __name__ == "__main__":
    run()
