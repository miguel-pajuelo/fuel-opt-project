from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


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
        os.replace(active_path, backup)

    try:
        os.replace(candidate_path, active_path)
    except Exception:
        if backup.exists() and not active_path.exists():
            os.replace(backup, active_path)
        raise

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
