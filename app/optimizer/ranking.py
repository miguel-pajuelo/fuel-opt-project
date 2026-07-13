from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path
from statistics import median
from typing import Any, Callable, Protocol

from app.models import (
    CandidateResult,
    Coordinates,
    FUEL_FIELDS,
    OptimizationInput,
    OptimizationMode,
    Station,
    validate_optimization_mode,
)
from app.storage.database import get_candidates_with_price, get_candidates_with_price_in_bbox


ECONOMIC_EPSILON_EUR = 0.10
BALANCED_ECONOMIC_WEIGHT = 0.5
BALANCED_DISTANCE_WEIGHT = 0.5


class RouteProvider(Protocol):
    route_source: str

    def distances_for_candidates(
        self,
        origin: Coordinates,
        destination: Coordinates,
        stations: list[Station],
    ) -> dict[str, tuple[float, float]]:
        """Return station_id -> (origin_to_station_km, station_to_destination_km)."""

    def direct_distance_km(self, origin: Coordinates, destination: Coordinates) -> float:
        """Return the baseline origin_to_destination route distance."""

    def route_geometry(self, origin: Coordinates, destination: Coordinates) -> list[Coordinates]:
        """Return origin-to-destination route geometry, if available."""


def haversine_km(a: Coordinates, b: Coordinates) -> float:
    radius_km = 6371.0088
    lat1 = math.radians(a.lat)
    lat2 = math.radians(b.lat)
    d_lat = lat2 - lat1
    d_lon = math.radians(b.lon - a.lon)
    sin_lat = math.sin(d_lat / 2.0)
    sin_lon = math.sin(d_lon / 2.0)
    h = sin_lat * sin_lat + math.cos(lat1) * math.cos(lat2) * sin_lon * sin_lon
    return 2.0 * radius_km * math.asin(math.sqrt(h))


class HaversineEstimateProvider:
    route_source = "haversine_estimate"

    def __init__(self, detour_factor: float = 1.25) -> None:
        self.detour_factor = detour_factor

    def distances_for_candidates(
        self,
        origin: Coordinates,
        destination: Coordinates,
        stations: list[Station],
    ) -> dict[str, tuple[float, float]]:
        distances: dict[str, tuple[float, float]] = {}
        for station in stations:
            station_coords = Coordinates(station.lat, station.lon)
            to_station = haversine_km(origin, station_coords) * self.detour_factor
            from_station = haversine_km(station_coords, destination) * self.detour_factor
            distances[station.station_id] = (to_station, from_station)
        return distances

    def direct_distance_km(self, origin: Coordinates, destination: Coordinates) -> float:
        return haversine_km(origin, destination) * self.detour_factor

    def route_geometry(self, origin: Coordinates, destination: Coordinates) -> list[Coordinates]:
        return _line_geometry(origin, destination)


def _prefilter_by_distance(
    origin: Coordinates,
    candidates: list[tuple[Station, float]],
    radius_km: float,
    max_candidates: int,
) -> list[tuple[Station, float, float]]:
    scored: list[tuple[Station, float, float]] = []
    for station, price in candidates:
        distance = haversine_km(origin, Coordinates(station.lat, station.lon))
        if distance <= radius_km:
            scored.append((station, price, distance))
    scored.sort(key=lambda row: (row[2], row[1], row[0].station_id))
    return scored[:max_candidates]


def _bounding_box(origin: Coordinates, radius_km: float) -> tuple[float, float, float, float]:
    lat_delta = radius_km / 111.32
    cos_lat = math.cos(math.radians(origin.lat))
    lon_delta = 180.0 if abs(cos_lat) < 1e-9 else radius_km / (111.32 * abs(cos_lat))
    min_lat = max(-90.0, origin.lat - lat_delta)
    max_lat = min(90.0, origin.lat + lat_delta)
    min_lon = origin.lon - lon_delta
    max_lon = origin.lon + lon_delta
    if min_lon < -180.0:
        min_lon += 360.0
    if max_lon > 180.0:
        max_lon -= 360.0
    return min_lat, max_lat, min_lon, max_lon


def _geometry_bounding_box(points: list[Coordinates], buffer_km: float) -> tuple[float, float, float, float]:
    if not points:
        raise ValueError("Route geometry cannot be empty.")
    min_lat_raw = min(point.lat for point in points)
    max_lat_raw = max(point.lat for point in points)
    min_lon_raw = min(point.lon for point in points)
    max_lon_raw = max(point.lon for point in points)
    lat_delta = buffer_km / 111.32
    max_abs_lat = max(abs(min_lat_raw), abs(max_lat_raw))
    cos_lat = math.cos(math.radians(max_abs_lat))
    lon_delta = 180.0 if abs(cos_lat) < 1e-9 else buffer_km / (111.32 * abs(cos_lat))
    return (
        max(-90.0, min_lat_raw - lat_delta),
        min(90.0, max_lat_raw + lat_delta),
        max(-180.0, min_lon_raw - lon_delta),
        min(180.0, max_lon_raw + lon_delta),
    )


def _line_geometry(origin: Coordinates, destination: Coordinates, max_step_km: float = 5.0) -> list[Coordinates]:
    distance = max(haversine_km(origin, destination), 0.001)
    steps = max(1, math.ceil(distance / max_step_km))
    return [
        Coordinates(
            lat=origin.lat + (destination.lat - origin.lat) * idx / steps,
            lon=origin.lon + (destination.lon - origin.lon) * idx / steps,
        )
        for idx in range(steps + 1)
    ]


def _project_xy(point: Coordinates, ref_lat: float) -> tuple[float, float]:
    x = point.lon * 111.32 * math.cos(math.radians(ref_lat))
    y = point.lat * 111.32
    return x, y


def _point_segment_distance_km(point: Coordinates, start: Coordinates, end: Coordinates) -> float:
    ref_lat = (point.lat + start.lat + end.lat) / 3.0
    px, py = _project_xy(point, ref_lat)
    ax, ay = _project_xy(start, ref_lat)
    bx, by = _project_xy(end, ref_lat)
    dx = bx - ax
    dy = by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    cx = ax + t * dx
    cy = ay + t * dy
    return math.hypot(px - cx, py - cy)


def _distance_to_geometry_km(point: Coordinates, geometry: list[Coordinates]) -> float:
    if len(geometry) == 1:
        return haversine_km(point, geometry[0])
    return min(
        _point_segment_distance_km(point, geometry[idx], geometry[idx + 1])
        for idx in range(len(geometry) - 1)
    )


def _prefilter_by_corridor(
    geometry: list[Coordinates],
    candidates: list[tuple[Station, float]],
    corridor_radius_km: float,
    max_candidates: int,
) -> list[tuple[Station, float, float]]:
    scored: list[tuple[Station, float, float]] = []
    for station, price in candidates:
        distance = _distance_to_geometry_km(Coordinates(station.lat, station.lon), geometry)
        if distance <= corridor_radius_km:
            scored.append((station, price, distance))
    scored.sort(key=lambda row: (row[2], row[1], row[0].station_id))
    return scored[:max_candidates]


def _same_place(origin: Coordinates, destination: Coordinates, threshold_km: float = 1.0) -> bool:
    return haversine_km(origin, destination) <= threshold_km


def _optimization_mode(request: OptimizationInput) -> OptimizationMode:
    return validate_optimization_mode(request.optimization_mode)


def _reference_price(prices: list[float]) -> float:
    return float(median(prices)) if prices else 1.6


def _cost_per_km(request: OptimizationInput, reference_price_eur_l: float) -> float:
    return request.consumption_l_100km / 100.0 * reference_price_eur_l


def _is_budget_mode(request: OptimizationInput) -> bool:
    return request.input_mode == "budget"


def _candidate_gross_liters(request: OptimizationInput, price_eur_l: float) -> float:
    if _is_budget_mode(request):
        budget = request.budget_amount_eur or 0.0
        return budget / price_eur_l if price_eur_l > 0 else 0.0
    return request.liters


def _candidate_purchase_cost(request: OptimizationInput, price_eur_l: float) -> float:
    if _is_budget_mode(request):
        return float(request.budget_amount_eur or 0.0)
    return request.liters * price_eur_l


def _estimated_extra_km(
    request: OptimizationInput,
    station: Station,
    spatial_metric_km: float,
    is_local_search: bool,
) -> float:
    if is_local_search:
        distance = haversine_km(request.origin, Coordinates(station.lat, station.lon))
        return distance * 2.0 * request.route_detour_factor
    return spatial_metric_km * 2.0 * request.route_detour_factor


def _approx_score(
    request: OptimizationInput,
    station: Station,
    price: float,
    spatial_metric_km: float,
    reference_price_eur_l: float,
    is_local_search: bool,
) -> float:
    extra_km = _estimated_extra_km(request, station, spatial_metric_km, is_local_search)
    detour_cost = extra_km * _cost_per_km(request, reference_price_eur_l)
    if _is_budget_mode(request):
        gross_liters = _candidate_gross_liters(request, price)
        liters_spent = extra_km / 100.0 * request.consumption_l_100km
        return -(gross_liters - liters_spent)
    return price * request.liters + detour_cost


def _select_profiled_pool(
    scored: list[tuple[Station, float, float]],
    request: OptimizationInput,
    is_local_search: bool,
) -> list[tuple[Station, float]]:
    if not scored:
        return []
    reference_price = _reference_price([price for _, price, _ in scored])
    by_distance = sorted(scored, key=lambda row: (row[2], row[1], row[0].station_id))
    by_price = sorted(scored, key=lambda row: (row[1], row[2], row[0].station_id))
    by_score = sorted(
        scored,
        key=lambda row: (
            _approx_score(request, row[0], row[1], row[2], reference_price, is_local_search),
            row[2],
            row[1],
            row[0].station_id,
        ),
    )
    quota = max(5, request.max_candidates // 3)
    selected: dict[str, tuple[Station, float]] = {}
    for group in (by_distance[:quota], by_price[:quota], by_score):
        for station, price, _ in group:
            selected.setdefault(station.station_id, (station, price))
            if len(selected) >= request.max_candidates:
                return list(selected.values())
    return list(selected.values())


def _expansion_thresholds(preferred_km: float, max_extent_km: float, enabled: bool) -> list[float]:
    if not enabled:
        return [preferred_km]
    thresholds = [preferred_km]
    current = preferred_km
    while current < max_extent_km:
        current = min(max_extent_km, current * 2.0)
        if current > thresholds[-1]:
            thresholds.append(current)
        else:
            break
    return thresholds


def _economically_expand_pool(
    scored: list[tuple[Station, float, float]],
    request: OptimizationInput,
    preferred_extent_km: float,
    max_extent_km: float,
    is_local_search: bool,
) -> tuple[list[tuple[Station, float]], dict[str, Any]]:
    if not scored:
        return [], {
            "search_policy": "economic",
            "candidate_universe_size": 0,
            "candidate_pool_size": 0,
            "economic_expansion_used": False,
            "effective_search_extent_km": preferred_extent_km,
            "expansion_steps": [],
            "fallback_used": False,
        }

    reference_price = _reference_price([price for _, price, _ in scored])
    min_price = min(price for _, price, _ in scored)
    best_cost_so_far: float | None = None
    final_extent = preferred_extent_km
    final_subset: list[tuple[Station, float, float]] = []
    steps: list[dict[str, Any]] = []

    for extent in _expansion_thresholds(
        preferred_extent_km,
        max(preferred_extent_km, max_extent_km),
        request.economic_expansion_enabled,
    ):
        subset = [row for row in scored if row[2] <= extent]
        if not subset:
            steps.append({"extent_km": extent, "candidate_count": 0, "expanded": True})
            continue
        best_in_subset = min(
            _approx_score(request, station, price, metric, reference_price, is_local_search)
            for station, price, metric in subset
        )
        if best_cost_so_far is None or best_in_subset < best_cost_so_far:
            best_cost_so_far = best_in_subset
            final_extent = extent
            final_subset = subset

        next_min_extra_km = 0.0 if is_local_search else extent * 2.0 * request.route_detour_factor
        if is_local_search:
            next_min_extra_km = extent * 2.0 * request.route_detour_factor
        if _is_budget_mode(request):
            optimistic_next_cost = -_candidate_gross_liters(request, min_price) + (
                next_min_extra_km / 100.0 * request.consumption_l_100km
            )
        else:
            optimistic_next_cost = min_price * request.liters + next_min_extra_km * _cost_per_km(
                request,
                reference_price,
            )
        should_stop = (
            best_cost_so_far is not None
            and request.economic_expansion_enabled
            and optimistic_next_cost >= best_cost_so_far - ECONOMIC_EPSILON_EUR
        )
        steps.append(
            {
                "extent_km": extent,
                "candidate_count": len(subset),
                "best_approx_score_eur": round(best_in_subset, 4),
                "optimistic_next_cost_eur": round(optimistic_next_cost, 4),
                "stop": should_stop,
            }
        )
        if should_stop:
            break

    pool = _select_profiled_pool(final_subset, request, is_local_search)
    trace = {
        "search_policy": "economic",
        "optimization_mode": _optimization_mode(request),
        "candidate_universe_size": len(scored),
        "candidate_pool_size": len(pool),
        "economic_expansion_used": final_extent > preferred_extent_km,
        "effective_search_extent_km": round(final_extent, 3),
        "expansion_steps": steps,
        "fallback_used": False,
    }
    return pool, trace


def _radial_candidates(
    db_path: Path,
    request: OptimizationInput,
    radius_km: float,
    brand: str | None,
    brands: list[str] | None,
    excluded_brands: list[str] | None,
) -> tuple[list[tuple[Station, float]], dict[str, Any]]:
    max_extent = max(radius_km, request.max_search_extent_km)
    min_lat, max_lat, min_lon, max_lon = _bounding_box(request.origin, max_extent)
    candidates = get_candidates_with_price_in_bbox(
        db_path,
        request.fuel_type,
        min_lat,
        max_lat,
        min_lon,
        max_lon,
        brand=brand,
        brands=brands,
        excluded_brands=excluded_brands,
    )
    scored = [
        (station, price, haversine_km(request.origin, Coordinates(station.lat, station.lon)))
        for station, price in candidates
    ]
    pool, trace = _economically_expand_pool(scored, request, radius_km, max_extent, is_local_search=True)
    trace["search_shape"] = "local_radius"
    trace["preferred_search_radius_km"] = radius_km
    return pool, trace


def _corridor_candidates(
    db_path: Path,
    request: OptimizationInput,
    brand: str | None,
    brands: list[str] | None,
    excluded_brands: list[str] | None,
    route_geometry: list[Coordinates] | None,
) -> tuple[list[tuple[Station, float]], dict[str, Any]]:
    geometry = route_geometry or _line_geometry(request.origin, request.destination)
    preferred = request.preferred_corridor_km or request.corridor_radius_km
    max_extent = max(preferred, request.max_search_extent_km)
    min_lat, max_lat, min_lon, max_lon = _geometry_bounding_box(geometry, max_extent)
    bbox_candidates = get_candidates_with_price_in_bbox(
        db_path,
        request.fuel_type,
        min_lat,
        max_lat,
        min_lon,
        max_lon,
        brand=brand,
        brands=brands,
        excluded_brands=excluded_brands,
    )
    scored = [
        (station, price, _distance_to_geometry_km(Coordinates(station.lat, station.lon), geometry))
        for station, price in bbox_candidates
    ]
    pool, trace = _economically_expand_pool(scored, request, preferred, max_extent, is_local_search=False)
    trace["search_shape"] = "route_corridor"
    trace["preferred_corridor_km"] = preferred
    return pool, trace


def prefilter_candidates(
    db_path: Path,
    request: OptimizationInput,
    brand: str | None = None,
    brands: list[str] | None = None,
    excluded_brands: list[str] | None = None,
    route_geometry: list[Coordinates] | None = None,
) -> list[tuple[Station, float]]:
    candidates, _ = prefilter_candidates_with_trace(
        db_path,
        request,
        brand=brand,
        brands=brands,
        excluded_brands=excluded_brands,
        route_geometry=route_geometry,
    )
    return candidates


def prefilter_candidates_with_trace(
    db_path: Path,
    request: OptimizationInput,
    brand: str | None = None,
    brands: list[str] | None = None,
    excluded_brands: list[str] | None = None,
    route_geometry: list[Coordinates] | None = None,
) -> tuple[list[tuple[Station, float]], dict[str, Any]]:
    if request.fuel_type not in FUEL_FIELDS:
        raise ValueError(f"Unsupported fuel_type: {request.fuel_type}")

    if _same_place(request.origin, request.destination, request.same_place_threshold_km):
        preferred = request.preferred_search_radius_km or request.local_search_radius_km
        candidates, trace = _radial_candidates(
            db_path,
            request,
            radius_km=preferred,
            brand=brand,
            brands=brands,
            excluded_brands=excluded_brands,
        )
    else:
        candidates, trace = _corridor_candidates(
            db_path,
            request,
            brand=brand,
            brands=brands,
            excluded_brands=excluded_brands,
            route_geometry=route_geometry,
        )

    if not candidates:
        all_candidates = get_candidates_with_price(
            db_path,
            request.fuel_type,
            brand=brand,
            brands=brands,
            excluded_brands=excluded_brands,
        )
        if not all_candidates:
            trace["fallback_used"] = True
            trace["candidate_universe_size"] = 0
            trace["candidate_pool_size"] = 0
            return [], trace
        if _same_place(request.origin, request.destination, request.same_place_threshold_km):
            selected = [
                (station, price, haversine_km(request.origin, Coordinates(station.lat, station.lon)))
                for station, price in all_candidates
            ]
        else:
            geometry = route_geometry or _line_geometry(request.origin, request.destination)
            selected = [
                (station, price, _distance_to_geometry_km(Coordinates(station.lat, station.lon), geometry))
                for station, price in all_candidates
            ]
        selected.sort(key=lambda row: (row[2], row[1], row[0].station_id))
        pool = _select_profiled_pool(
            selected,
            request,
            _same_place(request.origin, request.destination, request.same_place_threshold_km),
        )
        trace["fallback_used"] = True
        trace["candidate_universe_size"] = len(all_candidates)
        trace["candidate_pool_size"] = len(pool)
        return pool, trace

    return candidates[:request.max_candidates], trace


def _economic_semantic_key(item: CandidateResult) -> tuple[float]:
    primary = -item.net_liters if item.input_mode == "budget" else item.optimization_score_eur
    return (primary,)


def _economic_rank_key(item: CandidateResult) -> tuple[float, float, float, str]:
    economic = _economic_semantic_key(item)
    return (
        economic[0],
        item.total_detour_km,
        item.price_eur_l,
        item.station.station_id,
    )


def _distance_semantic_key(
    item: CandidateResult,
    *,
    is_local_search: bool,
) -> tuple[float]:
    distance_metric = item.distance_to_station_km if is_local_search else item.extra_detour_km
    return (distance_metric,)


def _minimal_detour_rank_key(
    item: CandidateResult,
    *,
    is_local_search: bool,
) -> tuple[float, float, float, float, str]:
    distance = _distance_semantic_key(item, is_local_search=is_local_search)
    economic = _economic_rank_key(item)
    return (distance[0], economic[0], economic[1], economic[2], economic[3])


def _normalized_position(position: int, candidate_count: int) -> float:
    if candidate_count == 1:
        return 0.0
    return position / (candidate_count - 1)


def _competition_normalized_ranks(
    results: list[CandidateResult],
    *,
    semantic_key: Callable[[CandidateResult], tuple[float, ...]],
    stable_key: Callable[[CandidateResult], tuple[Any, ...]],
) -> dict[int, float]:
    """Assign the first position of each tied group, then normalize it."""
    ordered = sorted(results, key=stable_key)
    candidate_count = len(ordered)
    ranks: dict[int, float] = {}
    previous_key: tuple[float, ...] | None = None
    group_position = 0
    for position, item in enumerate(ordered):
        item_key = semantic_key(item)
        if previous_key is None or item_key != previous_key:
            group_position = position
            previous_key = item_key
        ranks[id(item)] = _normalized_position(group_position, candidate_count)
    return ranks


def _balanced_rank_components(
    results: list[CandidateResult],
    request: OptimizationInput,
) -> dict[int, tuple[float, float, float]]:
    is_local_search = _same_place(
        request.origin,
        request.destination,
        request.same_place_threshold_km,
    )

    def distance_semantic_key(item: CandidateResult) -> tuple[float]:
        return _distance_semantic_key(item, is_local_search=is_local_search)

    def distance_stable_key(item: CandidateResult) -> tuple[float, float, float, float, str]:
        return _minimal_detour_rank_key(item, is_local_search=is_local_search)

    economic_ranks = _competition_normalized_ranks(
        results,
        semantic_key=_economic_semantic_key,
        stable_key=_economic_rank_key,
    )
    distance_ranks = _competition_normalized_ranks(
        results,
        semantic_key=distance_semantic_key,
        stable_key=distance_stable_key,
    )
    return {
        id(item): (
            economic_ranks[id(item)],
            distance_ranks[id(item)],
            BALANCED_ECONOMIC_WEIGHT * economic_ranks[id(item)]
            + BALANCED_DISTANCE_WEIGHT * distance_ranks[id(item)],
        )
        for item in results
    }


def _rank_results(results: list[CandidateResult], request: OptimizationInput) -> list[CandidateResult]:
    mode = _optimization_mode(request)
    if mode == "economic":
        return sorted(results, key=_economic_rank_key)

    is_local_search = _same_place(
        request.origin,
        request.destination,
        request.same_place_threshold_km,
    )
    def distance_key(item: CandidateResult) -> tuple[float, float, float, float, str]:
        return _minimal_detour_rank_key(item, is_local_search=is_local_search)
    if mode == "minimal_detour":
        return sorted(results, key=distance_key)

    components = _balanced_rank_components(results, request)
    return sorted(
        results,
        key=lambda item: (
            components[id(item)][2],
            components[id(item)][0],
            components[id(item)][1],
            item.station.station_id,
        ),
    )


def optimize_candidates(
    candidates: list[tuple[Station, float]],
    request: OptimizationInput,
    route_provider: RouteProvider | None = None,
) -> list[CandidateResult]:
    provider = route_provider or HaversineEstimateProvider(detour_factor=request.route_detour_factor)
    station_list = [station for station, _ in candidates]
    price_by_station = {station.station_id: price for station, price in candidates}
    reference_price = _reference_price(list(price_by_station.values()))
    distances = provider.distances_for_candidates(request.origin, request.destination, station_list)
    direct_route_km = provider.direct_distance_km(request.origin, request.destination)

    results: list[CandidateResult] = []
    for station in station_list:
        if station.station_id not in distances:
            continue
        price = price_by_station[station.station_id]
        if price <= 0:
            continue
        to_station, from_station = distances[station.station_id]
        route_via_station = to_station + from_station
        extra_detour = max(0.0, route_via_station - direct_route_km)
        liters_spent = extra_detour / 100.0 * request.consumption_l_100km
        gross_refuel_liters = _candidate_gross_liters(request, price)
        net_liters = gross_refuel_liters - liters_spent
        if net_liters <= 0:
            continue
        travel_cost = liters_spent * reference_price
        refuel_cost = _candidate_purchase_cost(request, price)
        detour_penalty = 0.0
        effective_total = refuel_cost + travel_cost
        if _is_budget_mode(request):
            optimization_score = -net_liters
        else:
            optimization_score = effective_total
        results.append(
            CandidateResult(
                station=station,
                fuel_type=request.fuel_type,
                price_eur_l=price,
                distance_to_station_km=to_station,
                distance_from_station_km=from_station,
                direct_route_km=direct_route_km,
                route_via_station_km=route_via_station,
                extra_detour_km=extra_detour,
                total_detour_km=extra_detour,
                liters_spent_on_route=liters_spent,
                travel_cost_eur=travel_cost,
                refuel_cost_eur=refuel_cost,
                total_cost_eur=effective_total,
                fuel_purchase_cost_eur=refuel_cost,
                extra_travel_cost_eur=travel_cost,
                effective_total_cost_eur=effective_total,
                reference_cost_eur=None,
                net_savings_vs_reference_eur=None,
                budget_amount_eur=request.budget_amount_eur if _is_budget_mode(request) else None,
                gross_refuel_liters=gross_refuel_liters,
                net_liters_vs_reference=None,
                input_mode=request.input_mode,
                optimization_score_eur=optimization_score,
                detour_penalty_eur=detour_penalty,
                optimization_mode=_optimization_mode(request),
                why_selected="",
                net_liters=net_liters,
                net_km=net_liters / request.consumption_l_100km * 100.0,
                route_source=provider.route_source,
            )
        )
    return _annotate_results(_rank_results(results, request), request)


def _annotate_results(
    results: list[CandidateResult],
    request: OptimizationInput,
) -> list[CandidateResult]:
    if not results:
        return []
    reference = min(results, key=lambda item: (item.extra_detour_km, item.effective_total_cost_eur))
    reference_cost = reference.effective_total_cost_eur
    reference_net_liters = reference.net_liters
    is_budget = results[0].input_mode == "budget"
    is_local_search = _same_place(
        request.origin,
        request.destination,
        request.same_place_threshold_km,
    )
    annotated: list[CandidateResult] = []
    for item in results:
        savings = reference_cost - item.effective_total_cost_eur
        liters_delta = item.net_liters - reference_net_liters
        why = _why_selected(item, is_local_search=is_local_search)
        annotated.append(
            replace(
                item,
                reference_cost_eur=reference_cost,
                net_savings_vs_reference_eur=None if is_budget else savings,
                net_liters_vs_reference=liters_delta if is_budget else None,
                why_selected=why,
            )
        )
    return annotated


def _why_selected(item: CandidateResult, *, is_local_search: bool) -> str:
    if item.optimization_mode == "economic":
        if item.input_mode == "budget":
            return (
                "Prioriza la mayor cantidad neta estimada de combustible después de considerar "
                "el desplazamiento."
            )
        return (
            "Prioriza el menor coste total estimado después de considerar el desplazamiento."
        )
    if item.optimization_mode == "minimal_detour":
        if is_local_search:
            return (
                "Prioriza la estación más cercana estimada; el resultado económico se utiliza "
                "para desempatar."
            )
        return (
            "Prioriza el menor desvío adicional estimado; el resultado económico se utiliza "
            "para desempatar."
        )
    if item.optimization_mode == "balanced":
        return (
            "Busca un compromiso entre el resultado económico estimado y el desvío entre las "
            "opciones encontradas. Ambos criterios tienen el mismo peso en la ordenación."
        )
    raise ValueError(f"Unsupported optimization mode: {item.optimization_mode}")


def optimize_from_db(
    db_path: Path,
    request: OptimizationInput,
    brand: str | None = None,
    brands: list[str] | None = None,
    excluded_brands: list[str] | None = None,
    route_provider: RouteProvider | None = None,
) -> list[CandidateResult]:
    results, _ = optimize_from_db_with_context(
        db_path,
        request,
        brand=brand,
        brands=brands,
        excluded_brands=excluded_brands,
        route_provider=route_provider,
    )
    return results


def optimize_from_db_with_context(
    db_path: Path,
    request: OptimizationInput,
    brand: str | None = None,
    brands: list[str] | None = None,
    excluded_brands: list[str] | None = None,
    route_provider: RouteProvider | None = None,
) -> tuple[list[CandidateResult], dict[str, Any]]:
    route_geometry = None
    if route_provider is not None and not _same_place(request.origin, request.destination, request.same_place_threshold_km):
        geometry_getter = getattr(route_provider, "route_geometry", None)
        if callable(geometry_getter):
            route_geometry = geometry_getter(request.origin, request.destination)
    candidates, trace = prefilter_candidates_with_trace(
        db_path,
        request,
        brand=brand,
        brands=brands,
        excluded_brands=excluded_brands,
        route_geometry=route_geometry,
    )
    results = optimize_candidates(candidates, request, route_provider=route_provider)
    best = results[0] if results else None
    trace.update(
        {
            "best_result_outside_preferred_zone": bool(best and trace.get("economic_expansion_used")),
            "result_count": len(results),
        }
    )
    return results, trace
