from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT_DIR = ROOT / "data" / "reports"

from app.config import load_settings
from app.storage.publish import cleanup_old_backups, cleanup_sqlite_sidecars, publish_sqlite_candidate
from app.storage.validation import CatalogValidationRules, validate_catalog_db
from scripts.rebuild_station_catalog import _build_metadata, load_catalog
from app.storage.database import replace_catalog


def parse_args() -> argparse.Namespace:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Refresh the active catalog through staging, validation and swap.")
    parser.add_argument("--db", type=Path, default=settings.db_path)
    parser.add_argument("--source", choices=("auto", "minetur", "snapshot", "prices-cache", "ballenoil-cache"), default="auto")
    parser.add_argument("--snapshot", type=Path, default=settings.minetur_snapshot_path)
    parser.add_argument("--prices-cache", type=Path, default=settings.ballenoil_prices_path)
    parser.add_argument("--ballenoil-cache", type=Path, default=settings.ballenoil_result_path)
    parser.add_argument("--brands", nargs="+", metavar="MARCA", default=None)
    parser.add_argument("--write-report", type=Path, default=REPORT_DIR / "catalog_refresh_report.json")
    parser.add_argument("--lock-file", type=Path, default=REPORT_DIR / "catalog_refresh.lock")
    parser.add_argument("--lock-ttl-sec", type=int, default=3 * 60 * 60)
    parser.add_argument("--min-stations", type=int, default=8000)
    parser.add_argument("--min-prices", type=int, default=20000)
    parser.add_argument("--max-unknown-brand-ratio", type=float, default=0.50)
    parser.add_argument("--backup-retention", type=int, default=0)
    return parser.parse_args()


def _write_report(path: Path | None, report: dict[str, object]) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


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
                raise RuntimeError(f"refresh already running or lock is fresh: {lock_path}")
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
    raise RuntimeError(f"could not acquire refresh lock: {lock_path}")


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


def _notify_if_failed(report: dict[str, object]) -> None:
    status = str(report.get("refresh_status", ""))
    if status in ("ok", "skipped", "running"):
        return
    webhook_url = os.getenv("ALERT_WEBHOOK_URL", "")
    if not webhook_url:
        return
    import urllib.request as _urllib
    payload = json.dumps({
        "text": (
            f"[FuelOpt] Refresco de catálogo: {status}. "
            f"Error: {report.get('refresh_error', 'sin detalle')}"
        )
    }).encode()
    try:
        req = _urllib.Request(webhook_url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        _urllib.urlopen(req, timeout=10)
    except Exception:
        pass


def _brand_coverage_report(stations: list, limit: int = 20) -> dict[str, object]:
    total = len(stations)
    known = sum(1 for station in stations if getattr(station, "brand_confidence", None) == 1.0)
    unresolved = Counter(
        (getattr(station, "brand_label_raw", "") or getattr(station, "brand", "") or "UNKNOWN").strip() or "UNKNOWN"
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


def main() -> int:
    args = parse_args()
    started_at = datetime.now(timezone.utc).isoformat()
    report: dict[str, object] = {
        "started_at": started_at,
        "finished_at": "",
        "refresh_status": "running",
        "active_db": str(args.db),
        "candidate_db": "",
        "source": args.source,
        "brands": args.brands or [],
    }

    try:
        _acquire_lock(args.lock_file, args.lock_ttl_sec)
    except RuntimeError as exc:
        report.update({"refresh_status": "skipped", "refresh_error": str(exc), "finished_at": datetime.now(timezone.utc).isoformat()})
        _write_report(args.write_report, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    candidate = _candidate_path(args.db)
    report["candidate_db"] = str(candidate)
    candidate_snapshot = _candidate_snapshot_path(args.snapshot)
    report["candidate_snapshot"] = str(candidate_snapshot)
    backup_path: Path | None = None

    try:
        if candidate.exists():
            candidate.unlink()
        cleanup_sqlite_sidecars(candidate)
        if candidate_snapshot.exists():
            candidate_snapshot.unlink()

        (stations, prices), source_label, warnings = load_catalog(args, snapshot_write_path=candidate_snapshot)
        metadata = _build_metadata(source_label, stations, prices, warnings, candidate_snapshot)
        replace_catalog(candidate, stations, prices, metadata=metadata)

        rules = CatalogValidationRules(
            min_stations=args.min_stations,
            min_prices=args.min_prices,
            max_unknown_brand_ratio=args.max_unknown_brand_ratio,
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
            return 2

        backup_path = publish_sqlite_candidate(candidate, args.db)
        snapshot_replaced = _publish_snapshot_candidate(candidate_snapshot, args.snapshot)
        removed_backups = cleanup_old_backups(args.db, keep=args.backup_retention)
        report.update(
            {
                "refresh_status": "ok",
                "backup_db": str(backup_path) if backup_path else "",
                "removed_backups": [str(path) for path in removed_backups],
                "snapshot_replaced": snapshot_replaced,
                "backup_retention": args.backup_retention,
            }
        )
        return 0
    except Exception as exc:
        report.update({"refresh_status": "failed", "refresh_error": str(exc)})
        return 1
    finally:
        if candidate.exists():
            candidate.unlink()
        cleanup_sqlite_sidecars(candidate)
        if candidate_snapshot.exists():
            candidate_snapshot.unlink()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        _write_report(args.write_report, report)
        _release_lock(args.lock_file)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        _notify_if_failed(report)


if __name__ == "__main__":
    raise SystemExit(main())
