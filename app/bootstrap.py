from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.data_sources.brand_catalog import NORMALIZATION_VERSION
from app.data_sources.minetur import build_catalog_from_minetur, load_minetur_snapshot
from app.legacy_migration import find_legacy_root
from app.paths import APP_PATHS, AppPaths
from app.storage.database import open_db_readonly, replace_catalog
from app.storage.publish import (
    checkpoint_sqlite,
    cleanup_sqlite_sidecars,
    copy_sqlite_database,
    publish_sqlite_candidate,
)
from app.storage.validation import CatalogValidationRules, validate_catalog_db


class BootstrapError(RuntimeError):
    pass


@dataclass(frozen=True)
class BootstrapResult:
    database_action: str
    database_source: str
    snapshot_action: str
    logs_action: str
    active_db: Path


def _parse_timestamp(value: object) -> datetime | None:
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


def database_timestamp(path: Path) -> datetime | None:
    if not path.is_file():
        return None
    try:
        with open_db_readonly(path) as conn:
            rows = conn.execute(
                "SELECT key, value FROM catalog_metadata WHERE key IN ('source_fetched_at', 'built_at')"
            ).fetchall()
    except Exception:
        return None
    metadata = {str(row["key"]): row["value"] for row in rows}
    return _parse_timestamp(metadata.get("source_fetched_at")) or _parse_timestamp(metadata.get("built_at"))


def _database_is_valid(
    path: Path,
    rules: CatalogValidationRules,
    *,
    immutable: bool = False,
) -> bool:
    if not path.is_file():
        return False
    return validate_catalog_db(path, rules, readonly=True, immutable=immutable).ok


def _immutable_seed_is_ready(paths: AppPaths) -> bool:
    if not paths.seed_db_is_immutable or not paths.seed_db_path.is_file():
        return False
    associated_files = [
        Path(str(paths.seed_db_path) + suffix)
        for suffix in ("-wal", "-shm", "-journal")
    ]
    return not any(path.exists() for path in associated_files)


def _snapshot_payload(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list) or not payload["items"]:
        return None
    return payload


def snapshot_timestamp(path: Path) -> datetime | None:
    payload = _snapshot_payload(path)
    return _parse_timestamp(payload.get("fetched_at")) if payload else None


def _atomic_copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    candidate = destination.with_name(f".{destination.name}.bootstrap.next")
    try:
        with source.open("rb") as source_handle, candidate.open("wb") as candidate_handle:
            shutil.copyfileobj(source_handle, candidate_handle)
            candidate_handle.flush()
            os.fsync(candidate_handle.fileno())
        os.replace(candidate, destination)
    finally:
        if candidate.exists():
            candidate.unlink()


def _select_newer_snapshot(paths: AppPaths, legacy_root: Path | None) -> tuple[str, Path | None]:
    candidates: list[tuple[str, Path]] = [("installed", paths.installed_snapshot_path)]
    if legacy_root is not None:
        legacy_snapshot = legacy_root / "data" / "cache" / "minetur_snapshot.json"
        if legacy_snapshot.resolve() != paths.installed_snapshot_path.resolve():
            candidates.append(("legacy", legacy_snapshot))

    valid_candidates = [
        (label, path, snapshot_timestamp(path))
        for label, path in candidates
        if _snapshot_payload(path) is not None
    ]
    if not valid_candidates:
        return "snapshot_unavailable", None
    valid_candidates.sort(
        key=lambda item: item[2] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    label, source, source_time = valid_candidates[0]
    active_time = snapshot_timestamp(paths.user_snapshot_path)
    if _snapshot_payload(paths.user_snapshot_path) is not None and (
        source_time is None or (active_time is not None and active_time >= source_time)
    ):
        return "snapshot_kept", paths.user_snapshot_path
    _atomic_copy_file(source, paths.user_snapshot_path)
    return f"snapshot_copied_{label}", paths.user_snapshot_path


def _rebuild_candidate_from_snapshot(
    snapshot_path: Path,
    candidate_path: Path,
) -> None:
    items = load_minetur_snapshot(snapshot_path)
    stations, prices = build_catalog_from_minetur(items)
    payload = _snapshot_payload(snapshot_path) or {}
    fetched_at = str(payload.get("fetched_at") or "")
    replace_catalog(
        candidate_path,
        stations,
        prices,
        metadata={
            "dataset_mode": "raw_minetur",
            "dataset_version": "1",
            "normalization_version": NORMALIZATION_VERSION,
            "source": "MINETUR_SNAPSHOT",
            "source_fetched_at": fetched_at,
            "source_fetch_completed_at": fetched_at,
            "source_snapshot_date": fetched_at,
            "refresh_status": "ok",
            "refresh_error": "",
            "degraded": "false",
            "degraded_reasons": "[]",
        },
    )
    checkpoint_sqlite(candidate_path)
    cleanup_sqlite_sidecars(candidate_path)


def _prepare_database_candidate(
    source: Path,
    candidate: Path,
    rules: CatalogValidationRules,
    *,
    immutable_source: bool = False,
) -> None:
    copy_sqlite_database(source, candidate, immutable_source=immutable_source)
    validation = validate_catalog_db(candidate, rules, readonly=True, immutable=True)
    if not validation.ok:
        raise BootstrapError(f"database candidate failed validation: {validation.errors}")


def _publish_bootstrap_candidate(paths: AppPaths) -> None:
    publish_sqlite_candidate(paths.candidate_db_path, paths.user_db_path, backup_path=paths.previous_db_path)


def _archive_legacy_logs(paths: AppPaths, legacy_root: Path | None) -> str:
    if legacy_root is None:
        return "logs_unavailable"
    source_dir = legacy_root / "data" / "reports"
    if not source_dir.is_dir():
        return "logs_unavailable"
    source_key = hashlib.sha256(str(source_dir.resolve()).encode("utf-8")).hexdigest()[:12]
    marker = paths.logs_dir / f".legacy-import-{source_key}.complete"
    if marker.exists():
        return "logs_already_imported"
    files = [path for path in source_dir.iterdir() if path.is_file()]
    if not files:
        return "logs_unavailable"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = paths.logs_dir / f"legacy-import-{stamp}"
    destination.mkdir(parents=True, exist_ok=False)
    for source in files:
        shutil.copy2(source, destination / source.name)
    marker.write_text("complete\n", encoding="utf-8")
    return "logs_imported"


@contextmanager
def _bootstrap_lock(paths: AppPaths, timeout_seconds: float = 10.0):
    paths.user_root.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(paths.bootstrap_lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise BootstrapError(f"timed out waiting for bootstrap lock: {paths.bootstrap_lock_path}")
            time.sleep(0.1)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()}\n")
        yield
    finally:
        try:
            paths.bootstrap_lock_path.unlink()
        except FileNotFoundError:
            pass


def bootstrap_user_data(
    paths: AppPaths = APP_PATHS,
    *,
    explicit_legacy_root: Path | None = None,
    environ: dict[str, str] | None = None,
    rules: CatalogValidationRules | None = None,
) -> BootstrapResult:
    active_rules = rules or CatalogValidationRules()
    with _bootstrap_lock(paths):
        paths.db_dir.mkdir(parents=True, exist_ok=True)
        paths.cache_dir.mkdir(parents=True, exist_ok=True)
        paths.logs_dir.mkdir(parents=True, exist_ok=True)
        legacy_root = find_legacy_root(
            paths,
            explicit_root=explicit_legacy_root,
            environ=environ,
        )
        snapshot_action, usable_snapshot = _select_newer_snapshot(paths, legacy_root)

        active_valid = _database_is_valid(paths.user_db_path, active_rules)
        action = "database_kept"
        source_label = "active"

        external_legacy_db: Path | None = None
        if legacy_root is not None and legacy_root.resolve() != paths.resource_root.resolve():
            candidate = legacy_root / "data" / "db" / "gas_stations.sqlite"
            if _database_is_valid(candidate, active_rules):
                external_legacy_db = candidate

        if active_valid and external_legacy_db is not None:
            active_time = database_timestamp(paths.user_db_path)
            legacy_time = database_timestamp(external_legacy_db)
            if legacy_time is not None and (active_time is None or legacy_time > active_time):
                _prepare_database_candidate(
                    external_legacy_db,
                    paths.candidate_db_path,
                    active_rules,
                    immutable_source=False,
                )
                _publish_bootstrap_candidate(paths)
                action = "database_migrated_newer_legacy"
                source_label = "legacy"
        elif not active_valid:
            source: Path | None = None
            immutable_source = False
            if external_legacy_db is not None:
                source = external_legacy_db
                source_label = "legacy"
            seed_is_ready = not paths.seed_db_is_immutable or _immutable_seed_is_ready(paths)
            if source is None and seed_is_ready and _database_is_valid(
                paths.seed_db_path,
                active_rules,
                immutable=paths.seed_db_is_immutable,
            ):
                source = paths.seed_db_path
                source_label = "seed"
                immutable_source = paths.seed_db_is_immutable

            if source is not None:
                _prepare_database_candidate(
                    source,
                    paths.candidate_db_path,
                    active_rules,
                    immutable_source=immutable_source,
                )
                _publish_bootstrap_candidate(paths)
                action = f"database_initialized_{source_label}"
            elif usable_snapshot is not None:
                _rebuild_candidate_from_snapshot(usable_snapshot, paths.candidate_db_path)
                validation = validate_catalog_db(
                    paths.candidate_db_path,
                    active_rules,
                    readonly=True,
                    immutable=True,
                )
                if not validation.ok:
                    raise BootstrapError(f"snapshot rebuild failed validation: {validation.errors}")
                _publish_bootstrap_candidate(paths)
                action = "database_rebuilt_snapshot"
                source_label = "snapshot"
            else:
                raise BootstrapError("no valid active database, seed, legacy database or snapshot")

        if not _database_is_valid(paths.user_db_path, active_rules):
            raise BootstrapError("active database is invalid after bootstrap")
        logs_action = _archive_legacy_logs(paths, legacy_root)
        return BootstrapResult(
            database_action=action,
            database_source=source_label,
            snapshot_action=snapshot_action,
            logs_action=logs_action,
            active_db=paths.user_db_path,
        )


def is_managed_user_path(path: Path, managed_path: Path) -> bool:
    return path.expanduser().resolve() == managed_path.resolve()


def bootstrap_if_managed(
    db_path: Path,
    snapshot_path: Path,
    paths: AppPaths = APP_PATHS,
) -> BootstrapResult | None:
    if not (
        is_managed_user_path(db_path, paths.user_db_path)
        or is_managed_user_path(snapshot_path, paths.user_snapshot_path)
    ):
        return None
    return bootstrap_user_data(paths)
