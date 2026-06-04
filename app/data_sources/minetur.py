from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import unicodedata
from pathlib import Path
from typing import Any

import requests

from app.models import FUEL_FIELDS, Price, Station


MINETUR_URL = (
    "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/"
    "PreciosCarburantes/EstacionesTerrestres/"
)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Referer": "https://geoportalgasolineras.es/",
    "Origin": "https://geoportalgasolineras.es",
}


def strip_accents(value: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(ch)
    )


def normalize_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", strip_accents(value or "").upper())


def get_any(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    wanted = {normalize_key(k) for k in keys}
    for key, value in item.items():
        if normalize_key(str(key)) not in wanted:
            continue
        text = str(value or "").strip()
        if text:
            return text
    return ""


def to_float_es(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("\u00a0", "").replace(" ", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def extract_ideess(item: dict[str, Any]) -> str | None:
    for key in ("IDEESS", "IDEESS ", "IDESS", "ID EESS", "ideess", "idess"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    for key, value in item.items():
        if normalize_key(str(key)) in {"IDEESS", "IDESS", "IDEES"}:
            text = str(value or "").strip()
            if text:
                return text
    return None


def parse_minetur_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("ListaEESSPrecio")
    if not isinstance(items, list) or not items:
        raise ValueError("MINETUR response does not contain ListaEESSPrecio.")
    return [item for item in items if isinstance(item, dict)]


def _fetch_minetur_items_with_curl(timeout_sec: int) -> list[dict[str, Any]]:
    curl_path = shutil.which("curl.exe") or shutil.which("curl")
    if not curl_path:
        raise RuntimeError("curl is not available for MINETUR fallback.")
    command = [
        curl_path,
        "--fail",
        "--silent",
        "--show-error",
        "--location",
        "--compressed",
        "--max-time",
        str(timeout_sec),
        "-A",
        BROWSER_HEADERS["User-Agent"],
        "-H",
        f"Accept: {BROWSER_HEADERS['Accept']}",
        MINETUR_URL,
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        check=False,
        timeout=timeout_sec + 10,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"curl exited with {completed.returncode}: {stderr}")
    payload = json.loads(completed.stdout.decode("utf-8-sig", errors="replace"))
    return parse_minetur_payload(payload)


def fetch_minetur_items(timeout_sec: int = 30, retries: int = 4, backoff_sec: float = 4.0) -> list[dict[str, Any]]:
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)
    last_error: Exception | None = None
    try:
        for attempt in range(1, retries + 1):
            try:
                response = session.get(MINETUR_URL, timeout=timeout_sec)
                response.raise_for_status()
                try:
                    payload = response.json()
                except ValueError:
                    payload = json.loads(response.content.decode("utf-8-sig", errors="replace"))
                return parse_minetur_payload(payload)
            except requests.exceptions.SSLError as exc:
                last_error = exc
                break
            except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt == retries:
                    break
                time.sleep(backoff_sec * attempt)
    finally:
        session.close()
    try:
        return _fetch_minetur_items_with_curl(timeout_sec)
    except Exception as curl_error:
        raise RuntimeError(
            f"Could not fetch MINETUR data with requests or curl fallback. "
            f"requests_error={last_error}; curl_error={curl_error}"
        ) from curl_error


def save_minetur_snapshot(path: Path, items: list[dict[str, Any]]) -> None:
    payload = {
        "source": "MINETUR",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "items": items,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_minetur_snapshot(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return [item for item in payload["items"] if isinstance(item, dict)]
    if isinstance(payload, dict):
        return parse_minetur_payload(payload)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise ValueError(f"Unsupported MINETUR snapshot format: {path}")


def station_from_minetur_item(item: dict[str, Any]) -> Station | None:
    station_id = extract_ideess(item)
    lat = to_float_es(get_any(item, "Latitud", "lat", "latitud"))
    lon = to_float_es(get_any(item, "Longitud (WGS84)", "Longitud", "lon", "longitud"))
    if not station_id or lat is None or lon is None:
        return None
    brand_label_raw = (get_any(item, "Rótulo", "Rotulo", "rotulo") or "UNKNOWN").upper().strip()
    from app.data_sources.brand_catalog import canonicalize_brand_label

    brand_canonical, brand_group, brand_confidence = canonicalize_brand_label(brand_label_raw)
    address = get_any(item, "Dirección", "Direccion", "address")
    municipality = get_any(item, "Municipio", "Localidad")
    province = get_any(item, "Provincia")
    postal_code = get_any(item, "C.P.", "CP", "Codigo Postal", "Código Postal")
    name = f"{brand_canonical} {municipality}".strip() if municipality else brand_canonical
    return Station(
        station_id=station_id,
        brand=brand_canonical,
        name=name,
        address=address,
        postal_code=postal_code,
        municipality=municipality,
        province=province,
        lat=lat,
        lon=lon,
        source="MINETUR",
        last_seen_at=time.strftime("%Y-%m-%d"),
        raw=item,
        brand_label_raw=brand_label_raw,
        brand_canonical=brand_canonical,
        brand_group=brand_group,
        brand_confidence=brand_confidence,
    )


def prices_from_minetur_item(item: dict[str, Any], station_id: str | None = None) -> list[Price]:
    sid = station_id or extract_ideess(item)
    if not sid:
        return []
    updated_at = get_any(item, "Fecha", "FechaActualizacion", "Fecha Actualizacion", "FechaActualización") or None
    prices: list[Price] = []
    for fuel_type, (source_field, _) in FUEL_FIELDS.items():
        price = to_float_es(item.get(source_field))
        if price is None:
            continue
        prices.append(
            Price(
                station_id=sid,
                fuel_type=fuel_type,
                price_eur_l=price,
                updated_at=updated_at,
                source="MINETUR",
            )
        )
    return prices


def build_catalog_from_minetur(items: list[dict[str, Any]]) -> tuple[list[Station], list[Price]]:
    stations_by_id: dict[str, Station] = {}
    prices: list[Price] = []
    for item in items:
        station = station_from_minetur_item(item)
        if station is None:
            continue
        stations_by_id[station.station_id] = station
        prices.extend(prices_from_minetur_item(item, station.station_id))
    return list(stations_by_id.values()), prices


def load_ballenoil_result_cache(path: Path) -> tuple[list[Station], list[Price]]:
    raw = path.read_text(encoding="utf-8")
    first_newline = raw.find("\n")
    body = raw[first_newline + 1:] if first_newline >= 0 else raw
    rows = json.loads(body)
    if not isinstance(rows, list):
        raise ValueError(f"Ballenoil result cache is not a list: {path}")
    parsed_rows: list[tuple[dict[str, Any], float, float, str]] = []
    coord_counts: dict[tuple[float, float], int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        lat = to_float_es(row.get("latitud"))
        lon = to_float_es(row.get("longitud"))
        url = str(row.get("url") or "").strip()
        if not url or lat is None or lon is None:
            continue
        coord_key = (round(lat, 6), round(lon, 6))
        coord_counts[coord_key] = coord_counts.get(coord_key, 0) + 1
        parsed_rows.append((row, lat, lon, url))

    suspicious_coords = {
        coord for coord, count in coord_counts.items()
        if count > 10
    }

    stations: list[Station] = []
    prices: list[Price] = []
    for row, lat, lon, url in parsed_rows:
        coord_key = (round(lat, 6), round(lon, 6))
        if coord_key in suspicious_coords:
            continue
        station_id = f"ballenoil:{url}"
        station = Station(
            station_id=station_id,
            brand="BALLENOIL",
            name=str(row.get("nombre") or "BALLENOIL").strip(),
            address=str(row.get("ubicacion") or "").strip(),
            postal_code="",
            municipality="",
            province="",
            lat=lat,
            lon=lon,
            source="BALLENOIL_CACHE",
            last_seen_at=None,
            raw=row,
            brand_label_raw="BALLENOIL",
            brand_canonical="BALLENOIL",
            brand_group="BALLENOIL",
            brand_confidence=1.0,
        )
        stations.append(station)
        for fuel_type in FUEL_FIELDS:
            price = to_float_es(row.get(fuel_type))
            if price is None:
                continue
            prices.append(
                Price(
                    station_id=station_id,
                    fuel_type=fuel_type,
                    price_eur_l=price,
                    updated_at=None,
                    source="BALLENOIL_CACHE",
                )
            )
    return stations, prices


def load_prices_cache_as_catalog(path: Path) -> tuple[list[Station], list[Price]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    prices_by_id = payload.get("precios_por_ideess") or payload.get("precios") or {}
    if not isinstance(prices_by_id, dict):
        raise ValueError(f"Unsupported prices cache format: {path}")
    updated_at = payload.get("source_fecha") or payload.get("minetur_fecha")
    stations: list[Station] = []
    prices: list[Price] = []
    for station_id, row in prices_by_id.items():
        if not isinstance(row, dict):
            continue
        sid = str(station_id).strip()
        lat = to_float_es(row.get("lat") or row.get("latitud"))
        lon = to_float_es(row.get("lon") or row.get("longitud"))
        if not sid or lat is None or lon is None:
            continue
        stations.append(
            Station(
                station_id=sid,
                brand="UNKNOWN",
                name=f"EESS {sid}",
                address="",
                postal_code="",
                municipality="",
                province="",
                lat=lat,
                lon=lon,
                source="PRICE_CACHE",
                last_seen_at=updated_at,
                raw=row,
                brand_label_raw="UNKNOWN",
                brand_canonical="UNKNOWN",
                brand_group="UNKNOWN",
                brand_confidence=0.0,
            )
        )
        for fuel_type in FUEL_FIELDS:
            price = to_float_es(row.get(fuel_type))
            if price is None:
                continue
            prices.append(
                Price(
                    station_id=sid,
                    fuel_type=fuel_type,
                    price_eur_l=price,
                    updated_at=updated_at,
                    source="PRICE_CACHE",
                )
            )
    return stations, prices


def quality_report(stations: list[Station], prices: list[Price]) -> dict[str, Any]:
    duplicate_coords: dict[tuple[float, float], int] = {}
    for station in stations:
        key = (round(station.lat, 6), round(station.lon, 6))
        duplicate_coords[key] = duplicate_coords.get(key, 0) + 1
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
    degraded_reasons: list[str] = []
    if total == 0:
        degraded_reasons.append("empty_catalog")
    if total and unknown_brand / total > 0.5:
        degraded_reasons.append("brand_metadata_missing")
    if total and with_address / total < 0.5:
        degraded_reasons.append("address_metadata_missing")
    return {
        "stations": total,
        "prices": len(prices),
        "station_count_known_brand": known_brand,
        "station_count_unknown_brand": unknown_brand,
        "brand_label_count_total": len(brand_labels),
        "brand_label_count_known": len(known_brand_labels),
        "canonical_brand_count": len(canonical_brands),
        "address_count": with_address,
        "municipality_count": with_municipality,
        "province_count": with_province,
        "degraded": bool(degraded_reasons),
        "degraded_reasons": degraded_reasons,
        "duplicate_coordinate_groups": sum(1 for count in duplicate_coords.values() if count > 1),
        "max_coordinate_duplicates": max(duplicate_coords.values(), default=0),
        "fuel_counts": {
            fuel_type: sum(1 for price in prices if price.fuel_type == fuel_type)
            for fuel_type in FUEL_FIELDS
        },
    }
