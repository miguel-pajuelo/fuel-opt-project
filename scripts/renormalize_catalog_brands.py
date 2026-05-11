from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import load_settings
from app.data_sources.brand_catalog import NORMALIZATION_VERSION, canonicalize_brand_label
from app.storage.database import connect


def parse_args() -> argparse.Namespace:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Reapply the current brand registry to the active catalog.")
    parser.add_argument("--db", type=Path, default=settings.db_path)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _metadata_counts(conn) -> dict[str, object]:
    station_count = int(conn.execute("SELECT COUNT(*) FROM stations WHERE active = 1").fetchone()[0])
    unknown = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM stations
            WHERE active = 1 AND COALESCE(brand_confidence, 0) < 1.0
            """
        ).fetchone()[0]
    )
    brand_label_count_total = int(
        conn.execute("SELECT COUNT(DISTINCT brand_label_raw) FROM stations WHERE active = 1").fetchone()[0]
    )
    brand_label_count_known = int(
        conn.execute(
            """
            SELECT COUNT(DISTINCT brand_label_raw)
            FROM stations
            WHERE active = 1 AND brand_label_raw <> 'UNKNOWN'
            """
        ).fetchone()[0]
    )
    canonical_brand_count = int(
        conn.execute(
            """
            SELECT COUNT(DISTINCT brand_canonical)
            FROM stations
            WHERE active = 1
              AND brand_canonical <> 'UNKNOWN'
              AND COALESCE(brand_confidence, 0) >= 1.0
            """
        ).fetchone()[0]
    )
    return {
        "normalization_version": NORMALIZATION_VERSION,
        "station_count_known_brand": station_count - unknown,
        "station_count_unknown_brand": unknown,
        "brand_label_count_total": brand_label_count_total,
        "brand_label_count_known": brand_label_count_known,
        "canonical_brand_count": canonical_brand_count,
    }


def _upsert_metadata(conn, metadata: dict[str, object]) -> None:
    conn.executemany(
        """
        INSERT INTO catalog_metadata (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        [(key, str(value)) for key, value in metadata.items()],
    )


def main() -> int:
    args = parse_args()
    conn = connect(args.db)
    try:
        rows = conn.execute(
            """
            SELECT station_id, brand, brand_label_raw, brand_canonical, brand_group, brand_confidence
            FROM stations
            """
        ).fetchall()
        updates: list[tuple[str, str, str, float, str]] = []
        for row in rows:
            raw_label = row["brand_label_raw"] or row["brand"] or ""
            canonical, group, confidence = canonicalize_brand_label(raw_label)
            if (
                canonical != row["brand_canonical"]
                or group != row["brand_group"]
                or confidence != row["brand_confidence"]
                or canonical != row["brand"]
            ):
                updates.append((canonical, canonical, group, confidence, row["station_id"]))

        before = _metadata_counts(conn)
        if not args.dry_run:
            conn.executemany(
                """
                UPDATE stations
                SET brand = ?,
                    brand_canonical = ?,
                    brand_group = ?,
                    brand_confidence = ?
                WHERE station_id = ?
                """,
                updates,
            )
            after = _metadata_counts(conn)
            _upsert_metadata(conn, after)
            conn.commit()
        else:
            after = before

        print(
            json.dumps(
                {
                    "db": str(args.db),
                    "dry_run": args.dry_run,
                    "station_rows": len(rows),
                    "updated_rows": len(updates),
                    "before": before,
                    "after": after,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
