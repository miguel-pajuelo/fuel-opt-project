from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.catalog.refresh_service import RefreshRequest, _publish_snapshot_candidate, run_catalog_refresh
from app.config import load_settings
from app.paths import APP_PATHS


def parse_args() -> argparse.Namespace:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Refresh the active catalog through staging, validation and swap.")
    parser.add_argument("--db", type=Path, default=settings.db_path)
    parser.add_argument("--source", choices=("auto", "minetur", "snapshot", "prices-cache", "ballenoil-cache"), default="auto")
    parser.add_argument("--snapshot", type=Path, default=settings.minetur_snapshot_path)
    parser.add_argument("--prices-cache", type=Path, default=settings.ballenoil_prices_path)
    parser.add_argument("--ballenoil-cache", type=Path, default=settings.ballenoil_result_path)
    parser.add_argument("--brands", nargs="+", metavar="MARCA", default=None)
    parser.add_argument("--write-report", type=Path, default=APP_PATHS.logs_dir / "catalog_refresh_report.json")
    parser.add_argument("--lock-file", type=Path, default=APP_PATHS.logs_dir / "catalog_refresh.lock")
    parser.add_argument("--lock-ttl-sec", type=int, default=3 * 60 * 60)
    parser.add_argument("--min-stations", type=int, default=8000)
    parser.add_argument("--min-prices", type=int, default=20000)
    parser.add_argument("--max-unknown-brand-ratio", type=float, default=0.50)
    parser.add_argument("--backup-retention", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_catalog_refresh(
        RefreshRequest(
            db=args.db,
            source=args.source,
            snapshot=args.snapshot,
            prices_cache=args.prices_cache,
            ballenoil_cache=args.ballenoil_cache,
            brands=tuple(args.brands or ()),
            report_path=args.write_report,
            lock_path=args.lock_file,
            lock_ttl_sec=args.lock_ttl_sec,
            min_stations=args.min_stations,
            min_prices=args.min_prices,
            max_unknown_brand_ratio=args.max_unknown_brand_ratio,
            backup_retention=args.backup_retention,
        )
    )
    print(json.dumps(result.report, ensure_ascii=False, indent=2))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
