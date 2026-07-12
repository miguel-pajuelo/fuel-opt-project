from __future__ import annotations

import json
import os
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.bootstrap import bootstrap_if_managed
from app.config import Settings, load_settings
from app.paths import APP_PATHS
from app.storage.database import replace_catalog
from app.storage.publish import cleanup_old_backups, cleanup_sqlite_sidecars, publish_sqlite_candidate
from app.storage.validation import CatalogValidationRules, validate_catalog_db
from scripts.rebuild_station_catalog import _build_metadata, load_catalog


EXIT_OK = 0
EXIT_ALREADY_RUNNING = 3
EXIT_SOURCE_FAILED = 4
EXIT_VALIDATION_FAILED = 5
EXIT_DATA_FAILED = 6


@dataclass(frozen=True)
class RefreshRequest:
    db: Path
    source: str
    snapshot: Path
    prices_cache: Path
    ballenoil_cache: Path
    brands: tuple[str, ...] = ()
    report_path: Path | None = None
    lock_path: Path | None = None
    lock_ttl_sec: int = 3 * 60 * 60
    min_stations: int = 8000
    min_prices: int = 20000
    max_unknown_brand_ratio: float = 0.50
    backup_retention: int = 1

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        *,
        source: str = "auto",
        report_path: Path | None = None,
    ) -> "RefreshRequest":
        cfg = settings or load_settings()
        return cls(
            db=cfg.db_path,
            source=source,
            snapshot=cfg.minetur_snapshot_path,
            prices_cache=cfg.ballenoil_prices_path,
            ballenoil_cache=cfg.ballenoil_result_path,
            report_path=report_path or APP_PATHS.logs_dir / "catalog_refresh_report.json",
            lock_path=APP_PATHS.logs_dir / "catalog_refresh.lock",
        )


@dataclass(frozen=True)
class RefreshResult:
    exit_code: int
    report: dict[str, object]


def _write_report(path: Path | None, report: dict[str, object]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate = path.with_name(f".{path.name}.next")
    try:
        candidate.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(candidate, path)
    finally:
        if candidate.exists():
            candidate.unlink()


def _acquire_lock(lock_path: Path, ttl_sec: int) -> None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        now = time.time()
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                payload = json.loads(lock_path.read_text(encoding="utf-8"))
                started = float(payload.get("started_epoch") or 0.0)
            except (OSError, json.JSONDecodeError, ValueError):
                started = lock_path.stat().st_mtime
            if now - started < ttl_sec:
                raise RuntimeError("refresh already running")
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "pid": os.getpid(),
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "started_epoch": now,
                },
                handle,
                ensure_ascii=False,
                indent=2,
            )
        return
    raise RuntimeError("could not acquire refresh lock")


def _release_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


def _candidate_path(active_db: Path) -> Path:
    return active_db.with_name(f"{active_db.stem}.next{active_db.suffix}")


def _candidate_snapshot_path(active_snapshot: Path) -> Path:
    return active_snapshot.with_name(f"{active_snapshot.stem}.next{active_snapshot.suffix}")


def _publish_snapshot_candidate(candidate_snapshot: Path, active_snapshot: Path) -> bool:
    if not candidate_snapshot.exists():
        return False
    active_snapshot.parent.mkdir(parents=True, exist_ok=True)
    os.replace(candidate_snapshot, active_snapshot)
    return True


def _brand_coverage_report(stations: list, limit: int = 20) -> dict[str, object]:
    total = len(stations)
    known = sum(1 for station in stations if getattr(station, "brand_confidence", None) == 1.0)
    unresolved = Counter(
        (getattr(station, "brand_label_raw", "") or getattr(station, "brand", "") or "UNKNOWN").strip()
        or "UNKNOWN"
        for station in stations
        if getattr(station, "brand_confidence", None) != 1.0
    )
    return {
        "brand_coverage_ratio": round(known / total, 4) if total else 0.0,
        "station_count_known_brand": known,
        "station_count_unknown_brand": total - known,
        "top_unresolved_brand_labels": [
            {"label": label, "station_count": count}
            for label, count in unresolved.most_common(limit)
        ],
    }


def _validation_is_degraded(validation_status: dict[str, object]) -> bool:
    catalog = validation_status.get("catalog")
    catalog_status = catalog if isinstance(catalog, dict) else {}
    refresh_status = str(catalog_status.get("refresh_status") or validation_status.get("refresh_status") or "").lower()
    degraded = str(catalog_status.get("degraded") or validation_status.get("degraded") or "").lower()
    return refresh_status == "degraded" or degraded in {"1", "true", "yes", "on"}


def run_catalog_refresh(request: RefreshRequest) -> RefreshResult:
    started_at = datetime.now(timezone.utc).isoformat()
    report: dict[str, object] = {
        "started_at": started_at,
        "finished_at": "",
        "refresh_status": "running",
        "active_db": str(request.db),
        "candidate_db": "",
        "source": request.source,
        "brands": list(request.brands),
    }
    lock_path = request.lock_path or APP_PATHS.logs_dir / "catalog_refresh.lock"
    try:
        _acquire_lock(lock_path, request.lock_ttl_sec)
    except RuntimeError as exc:
        report.update(
            {
                "refresh_status": "skipped",
                "refresh_error": str(exc),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _write_report(request.report_path, report)
        return RefreshResult(EXIT_ALREADY_RUNNING, report)

    candidate = _candidate_path(request.db)
    candidate_snapshot = _candidate_snapshot_path(request.snapshot)
    report["candidate_db"] = str(candidate)
    report["candidate_snapshot"] = str(candidate_snapshot)
    exit_code = EXIT_DATA_FAILED
    try:
        bootstrap_if_managed(request.db, request.snapshot)
        if candidate.exists():
            candidate.unlink()
        cleanup_sqlite_sidecars(candidate)
        if candidate_snapshot.exists():
            candidate_snapshot.unlink()

        class _Args:
            source = request.source
            snapshot = request.snapshot
            prices_cache = request.prices_cache
            ballenoil_cache = request.ballenoil_cache
            brands = list(request.brands) or None

        try:
            (stations, prices), source_label, warnings = load_catalog(
                _Args,
                snapshot_write_path=candidate_snapshot,
            )
        except Exception as exc:
            report.update({"refresh_status": "failed", "refresh_error": str(exc)})
            exit_code = EXIT_SOURCE_FAILED
            return RefreshResult(exit_code, report)

        metadata_snapshot = candidate_snapshot if candidate_snapshot.exists() else request.snapshot
        metadata = _build_metadata(source_label, stations, prices, warnings, metadata_snapshot)
        replace_catalog(candidate, stations, prices, metadata=metadata)
        rules = CatalogValidationRules(
            min_stations=request.min_stations,
            min_prices=request.min_prices,
            max_unknown_brand_ratio=request.max_unknown_brand_ratio,
        )
        validation = validate_catalog_db(candidate, rules)
        report.update(
            {
                "source": source_label,
                "warnings": warnings,
                "validation_ok": validation.ok,
                "validation_errors": validation.errors,
                "validation_warnings": validation.warnings,
                "validation_status": validation.status,
                **_brand_coverage_report(stations),
            }
        )
        if not validation.ok:
            report["refresh_status"] = "failed_validation"
            exit_code = EXIT_VALIDATION_FAILED
            return RefreshResult(exit_code, report)

        backup_path = publish_sqlite_candidate(candidate, request.db)
        snapshot_replaced = _publish_snapshot_candidate(candidate_snapshot, request.snapshot)
        removed_backups = cleanup_old_backups(request.db, keep=request.backup_retention)
        refresh_status = "degraded" if _validation_is_degraded(validation.status) else "ok"
        report.update(
            {
                "refresh_status": refresh_status,
                "backup_db": str(backup_path) if backup_path else "",
                "removed_backups": [str(path) for path in removed_backups],
                "snapshot_replaced": snapshot_replaced,
                "backup_retention": request.backup_retention,
            }
        )
        exit_code = EXIT_OK
        return RefreshResult(exit_code, report)
    except Exception as exc:
        report.update({"refresh_status": "failed", "refresh_error": str(exc)})
        exit_code = EXIT_DATA_FAILED
        return RefreshResult(exit_code, report)
    finally:
        if candidate.exists():
            candidate.unlink()
        cleanup_sqlite_sidecars(candidate)
        if candidate_snapshot.exists():
            candidate_snapshot.unlink()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        _write_report(request.report_path, report)
        _release_lock(lock_path)
