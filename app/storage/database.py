from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.data_sources.brand_catalog import NORMALIZATION_VERSION
from app.data_sources.public_access import (
    CURATED_PUBLIC_ACCESS_STATION_IDS,
    is_publicly_eligible,
)
from app.models import Price, Station


INDEPENDENT_BRAND_SENTINEL = "__INDEPENDENT__"


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS stations (
    station_id TEXT PRIMARY KEY,
    brand TEXT NOT NULL,
    brand_label_raw TEXT NOT NULL DEFAULT '',
    brand_canonical TEXT NOT NULL DEFAULT '',
    brand_group TEXT NOT NULL DEFAULT '',
    brand_confidence REAL,
    name TEXT NOT NULL,
    address TEXT NOT NULL DEFAULT '',
    postal_code TEXT NOT NULL DEFAULT '',
    municipality TEXT NOT NULL DEFAULT '',
    province TEXT NOT NULL DEFAULT '',
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    source TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    last_seen_at TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS prices (
    station_id TEXT NOT NULL,
    fuel_type TEXT NOT NULL,
    price_eur_l REAL NOT NULL,
    updated_at TEXT,
    source TEXT NOT NULL,
    PRIMARY KEY (station_id, fuel_type),
    FOREIGN KEY (station_id) REFERENCES stations(station_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS catalog_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stations_brand ON stations(brand);
CREATE INDEX IF NOT EXISTS idx_stations_lat_lon ON stations(lat, lon);
CREATE INDEX IF NOT EXISTS idx_prices_fuel ON prices(fuel_type, price_eur_l);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def open_db(db_path: Path):
    conn = connect(db_path)
    try:
        yield conn
        if conn.in_transaction:
            conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    with open_db(db_path) as conn:
        conn.executescript(SCHEMA)
        existing_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(stations)").fetchall()
        }
        migrations = {
            "brand_label_raw": "ALTER TABLE stations ADD COLUMN brand_label_raw TEXT NOT NULL DEFAULT ''",
            "brand_canonical": "ALTER TABLE stations ADD COLUMN brand_canonical TEXT NOT NULL DEFAULT ''",
            "brand_group": "ALTER TABLE stations ADD COLUMN brand_group TEXT NOT NULL DEFAULT ''",
            "brand_confidence": "ALTER TABLE stations ADD COLUMN brand_confidence REAL",
        }
        for column, sql in migrations.items():
            if column not in existing_columns:
                conn.execute(sql)
        conn.execute(
            "UPDATE stations SET brand_label_raw = brand WHERE brand_label_raw = ''"
        )
        conn.execute(
            "UPDATE stations SET brand_canonical = brand WHERE brand_canonical = ''"
        )
        conn.execute(
            "UPDATE stations SET brand_group = brand_canonical WHERE brand_group = ''"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stations_brand_canonical ON stations(brand_canonical)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stations_brand_label_raw ON stations(brand_label_raw)")


def _catalog_metadata(stations: list[Station], prices: list[Price]) -> dict[str, object]:
    total = len(stations)
    known_brand = sum(1 for station in stations if station.brand_confidence == 1.0)
    unknown_brand = total - known_brand
    brand_labels = {station.brand_label_raw for station in stations if station.brand_label_raw}
    known_brand_labels = {label for label in brand_labels if label != "UNKNOWN"}
    canonical_brands = {
        station.brand_canonical
        for station in stations
        if station.brand_canonical != "UNKNOWN" and station.brand_confidence == 1.0
    }
    with_address = sum(1 for station in stations if station.address)
    with_municipality = sum(1 for station in stations if station.municipality)
    with_province = sum(1 for station in stations if station.province)
    sources = sorted({station.source for station in stations})
    price_dates = sorted({price.updated_at for price in prices if price.updated_at})
    degraded_reasons: list[str] = []
    if total == 0:
        degraded_reasons.append("empty_catalog")
    if total and unknown_brand / total > 0.5:
        degraded_reasons.append("brand_metadata_missing")
    if total and with_address / total < 0.5:
        degraded_reasons.append("address_metadata_missing")
    return {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "dataset_mode": "web_canonical",
        "dataset_version": "1",
        "normalization_version": NORMALIZATION_VERSION,
        "refresh_status": "degraded" if degraded_reasons else "ok",
        "refresh_error": "",
        "record_count": total,
        "source_fetched_at": "",
        "source_reference_date": price_dates[-1] if price_dates else "",
        "station_count": total,
        "price_count": len(prices),
        "station_count_known_brand": known_brand,
        "station_count_unknown_brand": unknown_brand,
        "brand_label_count_total": len(brand_labels),
        "brand_label_count_known": len(known_brand_labels),
        "canonical_brand_count": len(canonical_brands),
        "address_count": with_address,
        "municipality_count": with_municipality,
        "province_count": with_province,
        "sources": json.dumps(sources, ensure_ascii=False),
        "oldest_price_update": price_dates[0] if price_dates else "",
        "newest_price_update": price_dates[-1] if price_dates else "",
        "degraded": "true" if degraded_reasons else "false",
        "degraded_reasons": json.dumps(degraded_reasons, ensure_ascii=False),
    }


def _metadata_reasons(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item)]
    return []


def _normalize_catalog_metadata(metadata: dict[str, object]) -> dict[str, object]:
    normalized = dict(metadata)
    refresh_status = str(normalized.get("refresh_status") or "")
    degraded_reasons = _metadata_reasons(normalized.get("degraded_reasons"))
    refresh_error = str(normalized.get("refresh_error") or "")
    if refresh_status == "degraded" and refresh_error and not degraded_reasons:
        degraded_reasons.append(refresh_error)
    is_degraded = refresh_status == "degraded" or bool(degraded_reasons)
    normalized["degraded"] = "true" if is_degraded else "false"
    normalized["degraded_reasons"] = json.dumps(degraded_reasons, ensure_ascii=False)
    if is_degraded and refresh_status in {"", "ok"}:
        normalized["refresh_status"] = "degraded"
    return normalized


def replace_catalog(
    db_path: Path,
    stations: Iterable[Station],
    prices: Iterable[Price],
    metadata: dict[str, object] | None = None,
) -> None:
    init_db(db_path)
    station_rows = list(stations)
    price_rows = list(prices)
    known_station_ids = {station.station_id for station in station_rows}
    price_rows = [price for price in price_rows if price.station_id in known_station_ids]
    with open_db(db_path) as conn:
        conn.execute("DELETE FROM prices")
        conn.execute("DELETE FROM stations")
        conn.execute("DELETE FROM catalog_metadata")
        conn.executemany(
            """
            INSERT INTO stations (
                station_id, brand, brand_label_raw, brand_canonical, brand_group,
                brand_confidence, name, address, postal_code, municipality,
                province, lat, lon, source, active, last_seen_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    station.station_id,
                    station.brand,
                    station.brand_label_raw,
                    station.brand_canonical,
                    station.brand_group,
                    station.brand_confidence,
                    station.name,
                    station.address,
                    station.postal_code,
                    station.municipality,
                    station.province,
                    station.lat,
                    station.lon,
                    station.source,
                    1 if station.active else 0,
                    station.last_seen_at,
                    json.dumps(station.raw or {}, ensure_ascii=False),
                )
                for station in station_rows
            ],
        )
        conn.executemany(
            """
            INSERT INTO prices (station_id, fuel_type, price_eur_l, updated_at, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    price.station_id,
                    price.fuel_type,
                    price.price_eur_l,
                    price.updated_at,
                    price.source,
                )
                for price in price_rows
            ],
        )
        merged_metadata = _normalize_catalog_metadata(
            {
                **_catalog_metadata(station_rows, price_rows),
                **(metadata or {}),
            }
        )
        conn.executemany(
            "INSERT INTO catalog_metadata (key, value) VALUES (?, ?)",
            [(key, str(value)) for key, value in merged_metadata.items()],
        )


def row_to_station(row: sqlite3.Row) -> Station:
    keys = set(row.keys())
    raw_text = row["raw_json"] if "raw_json" in row.keys() else "{}"
    try:
        raw = json.loads(raw_text or "{}")
    except json.JSONDecodeError:
        raw = {}
    brand = row["brand"]
    brand_canonical = row["brand_canonical"] if "brand_canonical" in keys and row["brand_canonical"] else brand
    brand_label_raw = row["brand_label_raw"] if "brand_label_raw" in keys and row["brand_label_raw"] else brand
    brand_group = row["brand_group"] if "brand_group" in keys and row["brand_group"] else brand_canonical
    brand_confidence = row["brand_confidence"] if "brand_confidence" in keys else None
    return Station(
        station_id=row["station_id"],
        brand=brand_canonical,
        name=row["name"],
        address=row["address"],
        postal_code=row["postal_code"],
        municipality=row["municipality"],
        province=row["province"],
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        source=row["source"],
        active=bool(row["active"]),
        last_seen_at=row["last_seen_at"],
        raw=raw,
        brand_label_raw=brand_label_raw,
        brand_canonical=brand_canonical,
        brand_group=brand_group,
        brand_confidence=brand_confidence,
    )


def _eligible_station_from_row(row: sqlite3.Row) -> Station | None:
    station = row_to_station(row)
    return station if is_publicly_eligible(station) else None


def _curated_public_access_exclusion_sql(alias: str, params: list[object]) -> str:
    if not CURATED_PUBLIC_ACCESS_STATION_IDS:
        return ""
    excluded_ids = sorted(CURATED_PUBLIC_ACCESS_STATION_IDS)
    params.extend(excluded_ids)
    placeholders = ", ".join("?" for _ in excluded_ids)
    return f" AND {alias}.station_id NOT IN ({placeholders})"


def list_stations(db_path: Path, brand: str | None = None, limit: int = 100, offset: int = 0) -> list[Station]:
    sql = "SELECT * FROM stations WHERE active = 1"
    params: list[object] = []
    if brand:
        sql += " AND brand_canonical = ?"
        params.append(brand.upper())
    sql += _curated_public_access_exclusion_sql("stations", params)
    sql += " ORDER BY brand_canonical, municipality, name"
    with open_db(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    stations = [station for row in rows if (station := _eligible_station_from_row(row)) is not None]
    return stations[offset : offset + limit]


def list_brands(db_path: Path) -> list[str]:
    with open_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM stations
            WHERE active = 1
              AND brand_canonical <> ''
              AND brand_canonical <> 'UNKNOWN'
              AND COALESCE(brand_confidence, 0) >= 1.0
            ORDER BY brand_canonical
            """
        ).fetchall()
    brands = {
        row["brand_canonical"]
        for row in rows
        if row["brand_canonical"] and is_publicly_eligible(row_to_station(row))
    }
    return sorted(brands)


def canonical_brand_counts(db_path: Path) -> dict[str, int]:
    with open_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM stations
            WHERE active = 1
              AND brand_canonical <> ''
              AND brand_canonical <> 'UNKNOWN'
              AND COALESCE(brand_confidence, 0) >= 1.0
            """
        ).fetchall()
    counts: dict[str, int] = {}
    for row in rows:
        if not is_publicly_eligible(row_to_station(row)):
            continue
        brand = row["brand_canonical"]
        counts[brand] = counts.get(brand, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def raw_brand_label_counts(db_path: Path, limit: int = 500, offset: int = 0) -> list[dict[str, object]]:
    with open_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM stations
            WHERE active = 1
            """,
        ).fetchall()
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        if not is_publicly_eligible(row_to_station(row)):
            continue
        key = (row["brand_label_raw"], row["brand_canonical"])
        counts[key] = counts.get(key, 0) + 1
    items = sorted(counts.items(), key=lambda item: (-item[1], item[0][0]))
    return [
        {
            "label": label,
            "canonical": canonical,
            "station_count": station_count,
        }
        for (label, canonical), station_count in items[offset : offset + limit]
    ]


def database_health(db_path: Path) -> dict[str, object]:
    expected_tables = {"stations", "prices", "catalog_metadata"}
    with open_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name IN ('stations', 'prices', 'catalog_metadata')
            """
        ).fetchall()
    tables = {row["name"] for row in rows}
    missing = sorted(expected_tables - tables)
    if missing:
        raise RuntimeError(f"Missing database tables: {', '.join(missing)}")
    return {"database": "ok", "tables": sorted(tables)}


def _normalize_brand_filters(brands: str | Iterable[str] | None) -> list[str]:
    if brands is None:
        return []
    if isinstance(brands, str):
        raw_values = [brands]
    else:
        raw_values = list(brands)
    normalized: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        brand = str(value or "").strip().upper()
        if brand and brand not in seen:
            normalized.append(brand)
            seen.add(brand)
    return normalized


def _independent_predicate_sql() -> str:
    return "(s.brand_canonical = 'UNKNOWN' OR s.brand_confidence IS NULL OR s.brand_confidence < 1.0)"


def _brand_filter_sql(brands: str | Iterable[str] | None, params: list[object]) -> str:
    selected = _normalize_brand_filters(brands)
    if not selected:
        return ""
    real_brands = [brand for brand in selected if brand != INDEPENDENT_BRAND_SENTINEL]
    include_independent = INDEPENDENT_BRAND_SENTINEL in selected
    clauses: list[str] = []
    if real_brands:
        params.extend(real_brands)
        placeholders = ", ".join("?" for _ in real_brands)
        clauses.append(f"s.brand_canonical IN ({placeholders})")
    if include_independent:
        clauses.append(_independent_predicate_sql())
    if clauses:
        return f" AND ({' OR '.join(clauses)})"
    return " AND 0 = 1"


def _brand_exclusion_sql(excluded_brands: str | Iterable[str] | None, params: list[object]) -> str:
    excluded = _normalize_brand_filters(excluded_brands)
    if not excluded:
        return ""
    real_brands = [brand for brand in excluded if brand != INDEPENDENT_BRAND_SENTINEL]
    clauses: list[str] = []
    if real_brands:
        brand_clauses: list[str] = []
        for brand in real_brands:
            brand_clauses.append(
                """
                (
                    s.brand_canonical = ?
                    OR s.brand_group = ?
                    OR s.brand_label_raw = ?
                    OR s.brand_canonical LIKE ?
                    OR s.brand_group LIKE ?
                    OR s.brand_label_raw LIKE ?
                    OR s.brand_canonical LIKE ?
                    OR s.brand_group LIKE ?
                    OR s.brand_label_raw LIKE ?
                )
                """
            )
            params.extend([
                brand,
                brand,
                brand,
                f"{brand} %",
                f"{brand} %",
                f"{brand} %",
                f"% {brand}%",
                f"% {brand}%",
                f"% {brand}%",
            ])
        clauses.append(f"NOT ({' OR '.join(brand_clauses)})")
    if INDEPENDENT_BRAND_SENTINEL in excluded:
        clauses.append(f"NOT {_independent_predicate_sql()}")
    return f" AND {' AND '.join(clauses)}" if clauses else ""


def get_candidates_with_price(
    db_path: Path,
    fuel_type: str,
    brand: str | None = None,
    brands: Iterable[str] | None = None,
    excluded_brands: Iterable[str] | None = None,
    limit: int | None = None,
) -> list[tuple[Station, float]]:
    sql = """
        SELECT s.*, p.price_eur_l
        FROM stations s
        JOIN prices p ON p.station_id = s.station_id
        WHERE s.active = 1 AND p.fuel_type = ?
    """
    params: list[object] = [fuel_type]
    sql += _curated_public_access_exclusion_sql("s", params)
    sql += _brand_filter_sql(brands if brands is not None else brand, params)
    sql += _brand_exclusion_sql(excluded_brands, params)
    sql += " ORDER BY p.price_eur_l ASC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    with open_db(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    candidates: list[tuple[Station, float]] = []
    for row in rows:
        station = _eligible_station_from_row(row)
        if station is not None:
            candidates.append((station, float(row["price_eur_l"])))
    return candidates


def get_candidates_with_price_in_bbox(
    db_path: Path,
    fuel_type: str,
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    brand: str | None = None,
    brands: Iterable[str] | None = None,
    excluded_brands: Iterable[str] | None = None,
) -> list[tuple[Station, float]]:
    sql = """
        SELECT s.*, p.price_eur_l
        FROM stations s
        JOIN prices p ON p.station_id = s.station_id
        WHERE s.active = 1
          AND p.fuel_type = ?
          AND s.lat BETWEEN ? AND ?
    """
    params: list[object] = [fuel_type, min_lat, max_lat]
    if min_lon <= max_lon:
        sql += " AND s.lon BETWEEN ? AND ?"
        params.extend([min_lon, max_lon])
    else:
        sql += " AND (s.lon >= ? OR s.lon <= ?)"
        params.extend([min_lon, max_lon])
    sql += _curated_public_access_exclusion_sql("s", params)
    sql += _brand_filter_sql(brands if brands is not None else brand, params)
    sql += _brand_exclusion_sql(excluded_brands, params)
    sql += " ORDER BY p.price_eur_l ASC"
    with open_db(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    candidates: list[tuple[Station, float]] = []
    for row in rows:
        station = _eligible_station_from_row(row)
        if station is not None:
            candidates.append((station, float(row["price_eur_l"])))
    return candidates


def _parse_metadata_value(key: str, value: str) -> Any:
    numeric_keys = {
        "station_count",
        "price_count",
        "station_count_known_brand",
        "station_count_unknown_brand",
        "brand_label_count_total",
        "brand_label_count_known",
        "canonical_brand_count",
        "address_count",
        "municipality_count",
        "province_count",
        "record_count",
    }
    if key in numeric_keys:
        return int(value)
    if key in {"sources", "degraded_reasons"}:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    if key == "degraded":
        return value == "true"
    return value


def catalog_status(db_path: Path) -> dict[str, object]:
    with open_db(db_path) as conn:
        station_count = conn.execute("SELECT COUNT(*) FROM stations WHERE active = 1").fetchone()[0]
        station_count_unknown_brand = conn.execute(
            """
            SELECT COUNT(*)
            FROM stations
            WHERE active = 1 AND COALESCE(brand_confidence, 0) < 1.0
            """
        ).fetchone()[0]
        brand_label_count_total = conn.execute(
            "SELECT COUNT(DISTINCT brand_label_raw) FROM stations WHERE active = 1"
        ).fetchone()[0]
        brand_label_count_known = conn.execute(
            """
            SELECT COUNT(DISTINCT brand_label_raw)
            FROM stations
            WHERE active = 1 AND brand_label_raw <> 'UNKNOWN'
            """
        ).fetchone()[0]
        canonical_brand_count = conn.execute(
            """
            SELECT COUNT(DISTINCT brand_canonical)
            FROM stations
            WHERE active = 1
              AND brand_canonical <> 'UNKNOWN'
              AND COALESCE(brand_confidence, 0) >= 1.0
            """
        ).fetchone()[0]
        metadata_rows = conn.execute("SELECT key, value FROM catalog_metadata").fetchall()
    metadata = {row["key"]: _parse_metadata_value(row["key"], row["value"]) for row in metadata_rows}
    station_count_unknown_brand = int(station_count_unknown_brand)
    station_count = int(station_count)
    refresh_status = str(metadata.get("refresh_status", ""))
    degraded_reasons = metadata.get("degraded_reasons", [])
    if not isinstance(degraded_reasons, list):
        degraded_reasons = _metadata_reasons(degraded_reasons)
    refresh_error = str(metadata.get("refresh_error", ""))
    if refresh_status == "degraded" and refresh_error and not degraded_reasons:
        degraded_reasons = [refresh_error]
    degraded = bool(degraded_reasons) or refresh_status == "degraded" or bool(metadata.get("degraded", False))
    status = {
        "dataset_mode": metadata.get("dataset_mode", "unknown"),
        "dataset_version": metadata.get("dataset_version", ""),
        "built_at": metadata.get("built_at", ""),
        "source": metadata.get("source", ""),
        "source_fetch_started_at": metadata.get("source_fetch_started_at", ""),
        "source_fetched_at": metadata.get("source_fetched_at", ""),
        "source_fetch_completed_at": metadata.get("source_fetch_completed_at", ""),
        "source_reference_date": metadata.get("source_reference_date", ""),
        "source_snapshot_date": metadata.get("source_snapshot_date", ""),
        "normalization_version": metadata.get("normalization_version", ""),
        "refresh_status": refresh_status,
        "refresh_error": refresh_error,
        "degraded": degraded,
        "degraded_reasons": degraded_reasons,
        "station_count": station_count,
        "station_count_known_brand": station_count - station_count_unknown_brand,
        "station_count_unknown_brand": station_count_unknown_brand,
        "brand_label_count_total": int(brand_label_count_total),
        "brand_label_count_known": int(brand_label_count_known),
        "canonical_brand_count": int(canonical_brand_count),
        "catalog": metadata,
    }
    return status


def price_status(db_path: Path) -> dict[str, object]:
    with open_db(db_path) as conn:
        fuel_rows = conn.execute(
            """
            SELECT fuel_type, COUNT(*) AS count, MIN(updated_at) AS oldest, MAX(updated_at) AS newest
            FROM prices
            GROUP BY fuel_type
            ORDER BY fuel_type
            """
        ).fetchall()
    status = catalog_status(db_path)
    return {
        "stations": status["station_count"],
        "station_count_known_brand": status["station_count_known_brand"],
        "station_count_unknown_brand": status["station_count_unknown_brand"],
        "brand_label_count_total": status["brand_label_count_total"],
        "brand_label_count_known": status["brand_label_count_known"],
        "canonical_brand_count": status["canonical_brand_count"],
        "catalog": status["catalog"],
        "fuels": {
            row["fuel_type"]: {
                "count": row["count"],
                "oldest_update": row["oldest"],
                "newest_update": row["newest"],
            }
            for row in fuel_rows
        },
    }


def coverage_snapshot(db_path: Path) -> dict[str, object]:
    try:
        with open_db(db_path) as conn:
            price_rows = conn.execute(
                """
                SELECT s.*, p.fuel_type
                FROM prices p
                JOIN stations s ON s.station_id = p.station_id
                WHERE s.active = 1
                ORDER BY p.fuel_type
                """
            ).fetchall()
            independent_rows = conn.execute(
                f"""
                SELECT *
                FROM stations s
                WHERE active = 1
                  AND {_independent_predicate_sql()}
                """
            ).fetchall()
    except sqlite3.Error:
        return {"fuel_counts": {}, "independent_count": 0}
    fuel_counts: dict[str, int] = {}
    for row in price_rows:
        if not is_publicly_eligible(row_to_station(row)):
            continue
        fuel_type = row["fuel_type"]
        fuel_counts[fuel_type] = fuel_counts.get(fuel_type, 0) + 1
    independent_count = sum(
        1 for row in independent_rows if is_publicly_eligible(row_to_station(row))
    )
    return {
        "fuel_counts": dict(sorted(fuel_counts.items())),
        "independent_count": independent_count,
    }
