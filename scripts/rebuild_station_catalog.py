from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import load_settings
from app.data_sources.brand_catalog import DEFAULT_REGISTRY, NORMALIZATION_VERSION
from app.data_sources.minetur import (
    build_catalog_from_minetur,
    fetch_minetur_items,
    load_ballenoil_result_cache,
    load_minetur_snapshot,
    load_prices_cache_as_catalog,
    quality_report,
    save_minetur_snapshot,
)
from app.storage.database import replace_catalog


def parse_args() -> argparse.Namespace:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Rebuild the local station catalog SQLite database.")
    parser.add_argument("--db", type=Path, default=settings.db_path)
    parser.add_argument(
        "--source",
        choices=("auto", "minetur", "snapshot", "prices-cache", "ballenoil-cache"),
        default="auto",
        help="auto fetches MINETUR and falls back to local caches.",
    )
    parser.add_argument("--snapshot", type=Path, default=settings.minetur_snapshot_path)
    parser.add_argument("--prices-cache", type=Path, default=settings.ballenoil_prices_path)
    parser.add_argument("--ballenoil-cache", type=Path, default=settings.ballenoil_result_path)
    parser.add_argument("--write-report", type=Path, default=None)
    parser.add_argument(
        "--brands",
        nargs="+",
        metavar="MARCA",
        default=None,
        help=(
            "Filter by brand(s) when using a MINETUR source. "
            "Example: --brands Repsol Cepsa. "
            "Default: all brands from the raw MINETUR catalog."
        ),
    )
    return parser.parse_args()


def _build_minetur_catalog(items: list[dict], args: argparse.Namespace, source_label: str):
    if args.brands:
        stations, prices = DEFAULT_REGISTRY.fetch_all(items, brands=args.brands)
        source_label = f"{source_label}[{','.join(args.brands)}]"
    else:
        stations, prices = build_catalog_from_minetur(items)
    return (stations, prices), source_label


def load_catalog(args: argparse.Namespace, snapshot_write_path: Path | None = None):
    warnings: list[str] = []
    snapshot_target = args.snapshot if snapshot_write_path is None else snapshot_write_path
    if args.source in {"auto", "minetur"}:
        try:
            items = fetch_minetur_items()
            save_minetur_snapshot(snapshot_target, items)
        except Exception as exc:
            warnings.append(f"MINETUR fetch failed: {exc}")
            print(warnings[-1], file=sys.stderr)
            if args.source == "minetur":
                raise
            items = None

        if items is None and args.snapshot.exists():
            items = load_minetur_snapshot(args.snapshot)
            catalog, source_label = _build_minetur_catalog(items, args, "MINETUR_SNAPSHOT")
            return catalog, source_label, warnings

        if items is not None:
            catalog, source_label = _build_minetur_catalog(items, args, "MINETUR")
            return catalog, source_label, warnings

    if args.source in {"snapshot", "auto"} and args.snapshot.exists():
        items = load_minetur_snapshot(args.snapshot)
        catalog, source_label = _build_minetur_catalog(items, args, "MINETUR_SNAPSHOT")
        return catalog, source_label, warnings

    if args.source in {"prices-cache", "auto"} and args.prices_cache.exists():
        if args.source == "auto":
            warnings.append("Using PRICE_CACHE fallback; brand/address metadata is degraded.")
            print(warnings[-1], file=sys.stderr)
        return load_prices_cache_as_catalog(args.prices_cache), "PRICE_CACHE", warnings

    if args.source in {"ballenoil-cache", "auto"}:
        if args.source == "auto":
            warnings.append("Using BALLENOIL_CACHE fallback; catalog coverage is partial.")
            print(warnings[-1], file=sys.stderr)
        return load_ballenoil_result_cache(args.ballenoil_cache), "BALLENOIL_CACHE", warnings

    raise FileNotFoundError("No usable source found for station catalog rebuild.")


def _snapshot_date(snapshot_path: Path) -> str:
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if isinstance(payload, dict):
        return str(payload.get("fetched_at") or "")
    return ""


def _build_metadata(
    source: str,
    stations: list,
    prices: list,
    warnings: list[str],
    snapshot_path: Path,
) -> dict[str, object]:
    price_dates = sorted({price.updated_at for price in prices if price.updated_at})
    source_fetched_at = _snapshot_date(snapshot_path)
    snapshot_date = source_fetched_at if "SNAPSHOT" in source else ""
    reference_date = price_dates[-1] if price_dates else ""
    built_at = datetime.now(timezone.utc).isoformat()
    degraded_reasons = list(warnings)
    refresh_status = "degraded" if degraded_reasons else "ok"
    return {
        "dataset_mode": "web_canonical" if source.startswith("MINETUR[") else "raw_minetur",
        "dataset_version": "1",
        "built_at": built_at,
        "source": source,
        "source_fetch_started_at": "",
        "source_fetched_at": source_fetched_at,
        "source_fetch_completed_at": source_fetched_at or built_at,
        "source_reference_date": reference_date,
        "source_snapshot_date": snapshot_date,
        "normalization_version": NORMALIZATION_VERSION,
        "refresh_status": refresh_status,
        "refresh_error": " | ".join(degraded_reasons),
        "degraded": "true" if degraded_reasons else "false",
        "degraded_reasons": json.dumps(degraded_reasons, ensure_ascii=False),
        "record_count": len(stations),
    }


def main() -> int:
    args = parse_args()
    (stations, prices), source, warnings = load_catalog(args)
    metadata = _build_metadata(source, stations, prices, warnings, args.snapshot)
    replace_catalog(args.db, stations, prices, metadata=metadata)
    report = quality_report(stations, prices)
    report.update(metadata)
    report["source"] = source
    report["warnings"] = warnings
    report["db"] = str(args.db)
    if args.write_report:
        args.write_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
