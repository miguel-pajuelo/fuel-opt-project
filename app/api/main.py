from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from requests import RequestException

from app.config import load_settings
from app.config import PROJECT_ROOT
from app.api.warnings import build_optimize_warnings
from app.data_sources.brand_catalog import canonical_brand_id, ui_brand_catalog
from app.models import Coordinates, FUEL_FIELDS, OptimizationInput
from app.optimizer.ranking import HaversineEstimateProvider, optimize_from_db_with_context
from app.api.ui import STATIC_DIR, load_index_html
from app.routing.ors import ORSRouteProvider, geocode_address, geocode_candidates, reverse_geocode_coordinates
from app.storage.database import (
    INDEPENDENT_BRAND_SENTINEL,
    canonical_brand_counts,
    catalog_status as db_catalog_status,
    coverage_snapshot,
    database_health,
    list_stations,
    price_status,
    raw_brand_label_counts,
)


settings = load_settings()
app = FastAPI(title="Fuel Optimizer API", version="0.1.0")
_refresh_lock = threading.Lock()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

INDEPENDENT_BRAND_LABEL = "Independientes / sin marca"
INDEPENDENT_BRAND_HINT = "Incluye estaciones independientes o con rótulo no reconocido."


def _catalog_refresh_command(report_path: Path) -> list[str]:
    args = [
        "--source",
        "auto",
        "--write-report",
        str(report_path),
    ]
    if getattr(sys, "frozen", False):
        return [sys.executable, "--catalog-refresh-script", *args]
    return [sys.executable, str(PROJECT_ROOT / "scripts" / "refresh_catalog.py"), *args]


def _catalog_refresh_env() -> dict[str, str]:
    env = os.environ.copy()
    env["FUELOPT_PROJECT_ROOT"] = str(PROJECT_ROOT)
    if getattr(sys, "frozen", False):
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def _snapshot_fetched_at() -> str:
    try:
        payload = json.loads(settings.minetur_snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("fetched_at") or "")


def _catalog_status() -> dict[str, object]:
    status = db_catalog_status(settings.db_path)
    if not status.get("source_fetched_at"):
        fetched_at = _snapshot_fetched_at()
        if fetched_at:
            status["source_fetched_at"] = fetched_at
            catalog = status.get("catalog")
            if isinstance(catalog, dict):
                catalog["source_fetched_at"] = fetched_at
    return status


class OptimizeRequest(BaseModel):
    origin_address: str | None = None
    origin_lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    origin_lon: float | None = Field(default=None, ge=-180.0, le=180.0)
    destination_address: str | None = None
    destination_lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    destination_lon: float | None = Field(default=None, ge=-180.0, le=180.0)
    fuel_type: str = "gasoleo_a"
    input_mode: str = "liters"
    liters: float = Field(default=30.0, gt=0)
    budget_amount_eur: float | None = Field(default=None, gt=0)
    consumption_l_100km: float = Field(default=settings.default_consumption_l_100km, gt=0)
    radius_km: float = Field(default=settings.default_prefilter_radius_km, gt=0, le=500.0)
    preferred_search_radius_km: float | None = Field(
        default=None,
        gt=0,
        le=500.0,
        deprecated=True,
        description="Deprecated alias. Use local_search_radius_km instead.",
    )
    preferred_corridor_km: float | None = Field(
        default=None,
        gt=0,
        le=200.0,
        deprecated=True,
        description="Deprecated alias. Use corridor_radius_km instead.",
    )
    max_search_extent_km: float = Field(default=settings.max_search_extent_km, gt=0, le=800.0)
    economic_expansion_enabled: bool = True
    optimization_mode: str = Field(default=settings.default_optimization_mode)
    local_search_radius_km: float | None = Field(default=None, gt=0, le=500.0)
    corridor_radius_km: float | None = Field(default=None, gt=0, le=200.0)
    max_candidates: int = Field(default=settings.max_route_candidates, gt=0, le=250)
    result_limit: int = Field(default=20, gt=0, le=100)
    brand: str | None = None
    brands: list[str] | None = None
    use_ors: bool = False

    def effective_local_search_radius_km(self) -> float:
        return (
            self.local_search_radius_km
            if self.local_search_radius_km is not None
            else self.preferred_search_radius_km
            if self.preferred_search_radius_km is not None
            else settings.local_search_radius_km
        )

    def effective_corridor_radius_km(self) -> float:
        return (
            self.corridor_radius_km
            if self.corridor_radius_km is not None
            else self.preferred_corridor_km
            if self.preferred_corridor_km is not None
            else settings.corridor_radius_km
        )

    def deprecated_parameters_used(self) -> list[str]:
        used: list[str] = []
        if self.preferred_search_radius_km is not None:
            used.append("preferred_search_radius_km")
        if self.preferred_corridor_km is not None:
            used.append("preferred_corridor_km")
        return used


class RouteStopoverRequest(BaseModel):
    origin_lat: float = Field(ge=-90.0, le=90.0)
    origin_lon: float = Field(ge=-180.0, le=180.0)
    station_lat: float = Field(ge=-90.0, le=90.0)
    station_lon: float = Field(ge=-180.0, le=180.0)
    destination_lat: float = Field(ge=-90.0, le=90.0)
    destination_lon: float = Field(ge=-180.0, le=180.0)


def _reject_conflicting_radius_aliases(payload: OptimizeRequest) -> None:
    conflicts: list[str] = []
    if (
        payload.local_search_radius_km is not None
        and payload.preferred_search_radius_km is not None
        and payload.local_search_radius_km != payload.preferred_search_radius_km
    ):
        conflicts.append("local_search_radius_km/preferred_search_radius_km")
    if (
        payload.corridor_radius_km is not None
        and payload.preferred_corridor_km is not None
        and payload.corridor_radius_km != payload.preferred_corridor_km
    ):
        conflicts.append("corridor_radius_km/preferred_corridor_km")
    if conflicts:
        raise HTTPException(
            status_code=400,
            detail=f"Conflicting radius aliases: {', '.join(conflicts)}.",
        )


def _resolve_coordinates(address: str | None, lat: float | None, lon: float | None, label: str) -> Coordinates:
    if lat is not None and lon is not None:
        return Coordinates(lat=lat, lon=lon)
    if address:
        try:
            return geocode_address(address, settings=settings)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RequestException as exc:
            raise HTTPException(status_code=502, detail=f"Geocoding provider failed: {exc}") from exc
    raise HTTPException(status_code=400, detail=f"{label} requires address or lat/lon.")


def _selected_brands(payload: OptimizeRequest) -> list[str] | None:
    raw_values: list[str] = []
    if payload.brands:
        raw_values.extend(payload.brands)
    if payload.brand:
        raw_values.append(payload.brand)
    selected: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        brand = str(value or "").strip().upper()
        if brand and brand not in seen:
            selected.append(brand)
            seen.add(brand)
    if len(selected) > settings.max_brands_per_request:
        raise HTTPException(
            status_code=400,
            detail=f"Too many brands selected. Maximum is {settings.max_brands_per_request}.",
        )
    return selected or None


def _public_geometry(points: list[Coordinates]) -> list[dict[str, float]]:
    return [{"lat": point.lat, "lon": point.lon} for point in points]


@app.get("/geocode")
def geocode(
    q: str = Query(min_length=3),
    size: int = Query(default=5, ge=1, le=10),
    focus_lat: float | None = Query(default=None, ge=-90.0, le=90.0),
    focus_lon: float | None = Query(default=None, ge=-180.0, le=180.0),
) -> dict[str, Any]:
    try:
        return {
            "items": geocode_candidates(
                q,
                settings=settings,
                size=size,
                focus_lat=focus_lat,
                focus_lon=focus_lon,
            )
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Geocoding provider failed: {exc}") from exc


@app.get("/reverse-geocode")
def reverse_geocode(
    lat: float = Query(ge=-90.0, le=90.0),
    lon: float = Query(ge=-180.0, le=180.0),
) -> dict[str, Any]:
    try:
        item = reverse_geocode_coordinates(lat=lat, lon=lon, settings=settings)
        return {"item": item}
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Geocoding provider failed: {exc}") from exc


@app.post("/route/stopover")
def route_stopover(payload: RouteStopoverRequest) -> dict[str, Any]:
    origin = Coordinates(payload.origin_lat, payload.origin_lon)
    station = Coordinates(payload.station_lat, payload.station_lon)
    destination = Coordinates(payload.destination_lat, payload.destination_lon)
    try:
        provider = ORSRouteProvider(settings=settings)
        first_leg = provider.route_geometry(origin, station)
        second_leg = provider.route_geometry(station, destination)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Routing provider failed: {exc}") from exc
    return {
        "route_source": "openrouteservice_directions",
        "legs": [
            {"name": "origin_to_station", "geometry": _public_geometry(first_leg)},
            {"name": "station_to_destination", "geometry": _public_geometry(second_leg)},
        ],
        "waypoints": {
            "origin": _public_geometry([origin])[0],
            "station": _public_geometry([station])[0],
            "destination": _public_geometry([destination])[0],
        },
    }


@app.get("/", response_class=HTMLResponse)
def root() -> str:
    return load_index_html()


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        db_status = database_health(settings.db_path)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"status": "down", "database": "unavailable", "error": str(exc)},
        ) from exc
    return {"status": "ok", **db_status}


@app.get("/fuels")
def fuels() -> dict[str, Any]:
    return {
        "fuels": [
            {"key": key, "source_field": source_field, "label": label}
            for key, (source_field, label) in FUEL_FIELDS.items()
        ]
    }


@app.get("/brands")
def brands() -> dict[str, Any]:
    counts = canonical_brand_counts(settings.db_path)
    try:
        coverage = coverage_snapshot(settings.db_path)
    except Exception:
        coverage = {"independent_count": 0}
    independent_count = int(coverage.get("independent_count", 0) or 0)
    known_payload: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in ui_brand_catalog():
        canonical = str(item["canonical"])
        station_count = counts.get(canonical, 0)
        if station_count <= 0:
            continue
        payload = dict(item)
        payload["station_count"] = station_count
        known_payload.append(payload)
        seen.add(canonical)

    for canonical, station_count in sorted(counts.items()):
        if canonical in seen or canonical == "UNKNOWN" or station_count <= 0:
            continue
        known_payload.append(
            {
                "id": canonical_brand_id(canonical),
                "label": canonical.title(),
                "canonical": canonical,
                "station_count": station_count,
                "aliases": [canonical],
            }
        )

    known_payload.sort(key=lambda row: (-int(row["station_count"]), str(row["label"])))
    if independent_count > 0:
        known_payload.append(
            {
                "id": "independent",
                "label": INDEPENDENT_BRAND_LABEL,
                "canonical": INDEPENDENT_BRAND_SENTINEL,
                "station_count": independent_count,
                "aliases": [],
                "is_virtual": True,
                "hint": INDEPENDENT_BRAND_HINT,
            }
        )
    return {"brands": known_payload, "count": len(known_payload)}


@app.get("/brands/raw")
def brands_raw(
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    rows = raw_brand_label_counts(settings.db_path, limit=limit, offset=offset)
    return {"items": rows, "limit": limit, "offset": offset, "returned": len(rows)}


@app.get("/catalog/status")
def catalog_status() -> dict[str, object]:
    return _catalog_status()


@app.post("/catalog/refresh")
def refresh_catalog() -> dict[str, object]:
    if not _refresh_lock.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Catalog refresh already in progress.")
    try:
        report_path = PROJECT_ROOT / "data" / "reports" / "catalog_refresh_report.json"
        cmd = _catalog_refresh_command(report_path)
        try:
            completed = subprocess.run(
                cmd,
                cwd=PROJECT_ROOT,
                env=_catalog_refresh_env(),
                capture_output=True,
                text=True,
                timeout=900,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail="Catalog refresh timed out.") from exc

        report: dict[str, object] = {}
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                report = {}

        if completed.returncode == 2:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Catalog refresh failed validation.",
                    "refresh_status": report.get("refresh_status"),
                    "validation_status": report.get("validation_status"),
                    "validation_errors": report.get("validation_errors", []),
                    "validation_warnings": report.get("validation_warnings", []),
                },
            )

        if report.get("refresh_status") == "skipped":
            raise HTTPException(
                status_code=429,
                detail={
                    "message": "Catalog refresh already in progress.",
                    "refresh_status": report.get("refresh_status"),
                    "refresh_error": report.get("refresh_error"),
                },
            )

        if completed.returncode != 0:
            detail = report.get("refresh_error") or completed.stderr or completed.stdout or "Catalog refresh failed."
            raise HTTPException(status_code=502, detail=str(detail))

        status = _catalog_status()
        return {
            "refresh": report,
            "catalog": status,
            "returncode": completed.returncode,
        }
    finally:
        _refresh_lock.release()


@app.get("/prices/status")
def prices_status() -> dict[str, object]:
    return price_status(settings.db_path)


@app.get("/stations")
def stations(
    brand: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    rows = list_stations(settings.db_path, brand=brand, limit=limit, offset=offset)
    return {"items": [row.public_dict() for row in rows], "limit": limit, "offset": offset}


@app.post("/optimize")
def optimize(payload: OptimizeRequest) -> dict[str, Any]:
    if payload.fuel_type not in FUEL_FIELDS:
        raise HTTPException(status_code=400, detail=f"Unsupported fuel_type: {payload.fuel_type}")
    input_mode = (payload.input_mode or "liters").strip().lower()
    if input_mode not in {"liters", "budget"}:
        raise HTTPException(status_code=400, detail="input_mode must be 'liters' or 'budget'.")
    if input_mode == "budget" and payload.budget_amount_eur is None:
        raise HTTPException(status_code=422, detail="budget_amount_eur is required when input_mode is 'budget'.")
    _reject_conflicting_radius_aliases(payload)
    selected_brands = _selected_brands(payload)
    origin = _resolve_coordinates(payload.origin_address, payload.origin_lat, payload.origin_lon, "origin")
    destination = _resolve_coordinates(
        payload.destination_address,
        payload.destination_lat,
        payload.destination_lon,
        "destination",
    )
    local_search_radius_km = payload.effective_local_search_radius_km()
    corridor_radius_km = payload.effective_corridor_radius_km()
    request = OptimizationInput(
        origin=origin,
        destination=destination,
        fuel_type=payload.fuel_type,
        input_mode=input_mode,
        liters=payload.liters,
        budget_amount_eur=payload.budget_amount_eur if input_mode == "budget" else None,
        consumption_l_100km=payload.consumption_l_100km,
        radius_km=payload.radius_km,
        preferred_search_radius_km=local_search_radius_km,
        preferred_corridor_km=corridor_radius_km,
        max_search_extent_km=payload.max_search_extent_km,
        economic_expansion_enabled=payload.economic_expansion_enabled,
        optimization_mode=payload.optimization_mode,
        max_candidates=payload.max_candidates,
        route_detour_factor=settings.route_detour_factor,
        local_search_radius_km=local_search_radius_km,
        corridor_radius_km=corridor_radius_km,
        same_place_threshold_km=settings.same_place_threshold_km,
    )
    try:
        route_provider = (
            ORSRouteProvider(settings=settings)
            if payload.use_ors
            else HaversineEstimateProvider(detour_factor=settings.route_detour_factor)
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        results, search_context = optimize_from_db_with_context(
            settings.db_path,
            request,
            brands=selected_brands,
            route_provider=route_provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    items = [item.to_dict() for item in results[:payload.result_limit]]
    deprecated_parameters = payload.deprecated_parameters_used()
    try:
        active_catalog_status = _catalog_status()
    except Exception:
        active_catalog_status = {}
    try:
        coverage = coverage_snapshot(settings.db_path)
    except Exception:
        coverage = {"fuel_counts": {}, "independent_count": 0}
    fuel_counts = coverage.get("fuel_counts") if isinstance(coverage.get("fuel_counts"), dict) else {}
    fuel_coverage_count = int(fuel_counts.get(payload.fuel_type, 0) or 0)
    independent_count = int(coverage.get("independent_count", 0) or 0)
    independent_included = INDEPENDENT_BRAND_SENTINEL in (selected_brands or [])
    warning_route_source = results[0].route_source if results else getattr(route_provider, "route_source", None)
    warnings_list = build_optimize_warnings(
        fuel_type=payload.fuel_type,
        selected_brands=selected_brands or [],
        catalog_status=active_catalog_status,
        fuel_coverage_count=fuel_coverage_count,
        independent_count=independent_count,
        search_context=search_context,
        route_source=warning_route_source,
        result_count=len(results),
        max_search_extent_km=payload.max_search_extent_km,
        deprecated_parameters=deprecated_parameters,
        independent_included=independent_included,
    )
    return {
        "route_source": results[0].route_source if results else None,
        "input_mode": input_mode,
        "budget_amount_eur": payload.budget_amount_eur if input_mode == "budget" else None,
        "search_policy": search_context.get("search_policy", "economic"),
        "optimization_mode": search_context.get("optimization_mode", payload.optimization_mode),
        "warnings": [warning.to_dict() for warning in warnings_list],
        "brand_filter": selected_brands or [],
        "search": search_context,
        "count": len(results),
        "returned": len(items),
        "limit": payload.result_limit,
        "best": results[0].to_dict() if results else None,
        "items": items,
    }
