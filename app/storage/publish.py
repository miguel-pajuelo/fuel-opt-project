from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.storage.database import sqlite_file_uri


def sqlite_sidecars(db_path: Path) -> list[Path]:
    return [Path(str(db_path) + suffix) for suffix in ("-wal", "-shm")]


def cleanup_sqlite_sidecars(db_path: Path) -> None:
    for path in sqlite_sidecars(db_path):
        if path.exists():
            path.unlink()


def checkpoint_sqlite(db_path: Path) -> None:
    if not db_path.exists():
        return
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()
    finally:
        conn.close()


def copy_sqlite_database(
    source_path: Path,
    destination_path: Path,
    *,
    immutable_source: bool = False,
) -> None:
    """Create a consistent standalone copy, including committed WAL content."""
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if destination_path.exists():
        destination_path.unlink()
    cleanup_sqlite_sidecars(destination_path)
    source_uri = sqlite_file_uri(source_path, mode="ro", immutable=immutable_source)
    source = sqlite3.connect(source_uri, uri=True, timeout=30)
    destination = sqlite3.connect(destination_path, timeout=30)
    try:
        source.backup(destination)
        destination.commit()
    finally:
        destination.close()
        source.close()
    checkpoint_sqlite(destination_path)
    cleanup_sqlite_sidecars(destination_path)


def publish_sqlite_candidate(candidate_path: Path, active_path: Path, backup_path: Path | None = None) -> Path | None:
    if not candidate_path.exists():
        raise FileNotFoundError(candidate_path)

    backup = backup_path
    if backup is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        backup = active_path.with_name(f"{active_path.stem}.previous-{stamp}{active_path.suffix}")

    checkpoint_sqlite(candidate_path)
    cleanup_sqlite_sidecars(candidate_path)

    active_path.parent.mkdir(parents=True, exist_ok=True)
    if active_path.exists():
        checkpoint_sqlite(active_path)
        cleanup_sqlite_sidecars(active_path)
        if backup.exists():
            backup.unlink()
        copy_sqlite_database(active_path, backup)

    # os.replace keeps the old active database in place if Windows refuses the
    # swap (for example because another process still holds it open).
    os.replace(candidate_path, active_path)

    cleanup_sqlite_sidecars(active_path)
    return backup if backup.exists() else None


def cleanup_old_backups(active_path: Path, keep: int = 1) -> list[Path]:
    if keep < 0:
        keep = 0
    backups = sorted(
        active_path.parent.glob(f"{active_path.stem}.previous-*{active_path.suffix}"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    removed: list[Path] = []
    for backup in backups[keep:]:
        backup.unlink()
        removed.append(backup)
    return removed
