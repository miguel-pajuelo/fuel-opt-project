from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings
import app.api.main as api_main
from app.data_sources.ballenoil import parse_station_detail
from app.data_sources.minetur import build_catalog_from_minetur, quality_report
from app.data_sources.public_access import (
    PUBLIC_ACCESS_LIKELY_RESTRICTED,
    PUBLIC_ACCESS_RESTRICTED,
    classify_public_access,
    filter_publicly_eligible_catalog,
    is_publicly_eligible,
)
from app.models import Coordinates, OptimizationInput, Price, Station
from app.optimizer.ranking import optimize_candidates, optimize_from_db, prefilter_candidates, prefilter_candidates_with_trace
from app.storage.database import (
    canonical_brand_counts,
    coverage_snapshot,
    get_candidates_with_price_in_bbox,
    list_brands,
    list_stations,
    price_status,
    raw_brand_label_counts,
    replace_catalog,
)
from app.storage.database import INDEPENDENT_BRAND_SENTINEL, _brand_filter_sql


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _json_payload(response):
    if isinstance(response, JSONResponse):
        return json.loads(response.body.decode("utf-8"))
    return response


def _cleanup_sqlite(db_path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(db_path) + suffix)
        if candidate.exists():
            candidate.unlink()


def _warning_codes(response: dict) -> set[str]:
    return {str(item.get("code")) for item in response.get("warnings", []) if isinstance(item, dict)}


def _warning_by_code(response: dict, code: str) -> dict:
    for item in response.get("warnings", []):
        if isinstance(item, dict) and item.get("code") == code:
            return item
    raise AssertionError(f"Warning not found: {code}. Response warnings: {response.get('warnings')}")


def _build_warning_test_db(db_path: Path, metadata: dict[str, object] | None = None) -> None:
    stations = [
        Station(
            station_id="w1",
            brand="BALLENOIL",
            name="Ballenoil Warning",
            address="Calle Uno",
            postal_code="28001",
            municipality="Madrid",
            province="Madrid",
            lat=40.4200,
            lon=-3.7000,
            source="TEST",
            brand_label_raw="BALLENOIL",
            brand_canonical="BALLENOIL",
            brand_group="BALLENOIL",
            brand_confidence=1.0,
        ),
        Station(
            station_id="w2",
            brand="REPSOL",
            name="Repsol Warning",
            address="Calle Dos",
            postal_code="28002",
            municipality="Madrid",
            province="Madrid",
            lat=40.4300,
            lon=-3.7100,
            source="TEST",
            brand_label_raw="REPSOL",
            brand_canonical="REPSOL",
            brand_group="REPSOL",
            brand_confidence=1.0,
        ),
        Station(
            station_id="w3",
            brand="UNKNOWN",
            name="Independent Warning",
            address="Calle Tres",
            postal_code="28003",
            municipality="Madrid",
            province="Madrid",
            lat=40.4250,
            lon=-3.7050,
            source="TEST",
            brand_label_raw="UNKNOWN",
            brand_canonical="UNKNOWN",
            brand_group="UNKNOWN",
            brand_confidence=0.0,
        ),
    ]
    prices = [
        Price("w1", "gasoleo_a", 1.50, "2026-04-22", "TEST"),
        Price("w2", "gasoleo_a", 1.45, "2026-04-22", "TEST"),
        Price("w1", "gasolina_98e10", 1.90, "2026-04-22", "TEST"),
    ]
    replace_catalog(db_path, stations, prices, metadata=metadata or {"source": "TEST"})


def _with_warning_db(test_name: str, callback, metadata: dict[str, object] | None = None) -> None:
    db_path = ROOT / "tests" / f".{test_name}.sqlite"
    _cleanup_sqlite(db_path)
    previous_settings = api_main.settings
    try:
        _build_warning_test_db(db_path, metadata=metadata)
        api_main.settings = Settings(db_path=db_path, ors_api_key=None)
        callback()
    finally:
        api_main.settings = previous_settings
        _cleanup_sqlite(db_path)


def _build_independent_brand_test_db(db_path: Path, include_independent: bool = True) -> None:
    stations = [
        Station(
            station_id="ib1",
            brand="BALLENOIL",
            name="Ballenoil Independent Fixture",
            address="Calle Filtro Uno",
            postal_code="28001",
            municipality="Madrid",
            province="Madrid",
            lat=40.4200,
            lon=-3.7000,
            source="TEST",
            brand_label_raw="BALLENOIL",
            brand_canonical="BALLENOIL",
            brand_group="BALLENOIL",
            brand_confidence=1.0,
        ),
    ]
    prices = [
        Price("ib1", "gasoleo_a", 1.80, "2026-04-22", "TEST"),
    ]
    if include_independent:
        stations.append(
            Station(
                station_id="ib2",
                brand="UNKNOWN",
                name="Independiente Fixture",
                address="Calle Filtro Dos",
                postal_code="28002",
                municipality="Madrid",
                province="Madrid",
                lat=40.4210,
                lon=-3.7010,
                source="TEST",
                brand_label_raw="ROTULO LOCAL",
                brand_canonical="UNKNOWN",
                brand_group="UNKNOWN",
                brand_confidence=0.5,
            )
        )
        prices.append(Price("ib2", "gasoleo_a", 1.20, "2026-04-22", "TEST"))
    replace_catalog(db_path, stations, prices, metadata={"source": "TEST"})


def _with_independent_brand_db(test_name: str, callback, include_independent: bool = True) -> None:
    db_path = ROOT / "tests" / f".{test_name}.sqlite"
    _cleanup_sqlite(db_path)
    previous_settings = api_main.settings
    try:
        _build_independent_brand_test_db(db_path, include_independent=include_independent)
        api_main.settings = Settings(db_path=db_path, ors_api_key=None)
        callback()
    finally:
        api_main.settings = previous_settings
        _cleanup_sqlite(db_path)


def _public_access_station(
    station_id: str,
    brand: str,
    price: float,
    *,
    lat: float = 40.3000,
    lon: float = -3.7300,
    address: str | None = None,
    municipality: str = "Getafe",
    raw: dict[str, object] | None = None,
    confidence: float = 1.0,
) -> tuple[Station, Price]:
    station = Station(
        station_id=station_id,
        brand=brand,
        name=f"{brand} Fixture",
        address=address or f"Calle {station_id}",
        postal_code="28001",
        municipality=municipality,
        province="Madrid",
        lat=lat,
        lon=lon,
        source="TEST",
        raw={"Tipo Venta": "P"} if raw is None else raw,
        brand_label_raw=brand,
        brand_canonical=brand,
        brand_group=brand,
        brand_confidence=confidence,
    )
    return station, Price(station_id, "gasoleo_a", price, "2026-04-22", "TEST")


def _build_public_access_test_db(db_path: Path) -> None:
    restricted_station, restricted_price = _public_access_station("13073", "ESTEBA RIVAS", 1.00)
    public_station, public_price = _public_access_station(
        "pa-public",
        "BALLENOIL",
        1.50,
        lat=40.3010,
        lon=-3.7310,
    )
    replace_catalog(
        db_path,
        [restricted_station, public_station],
        [restricted_price, public_price],
        metadata={"source": "TEST"},
    )


def _with_public_access_db(test_name: str, callback) -> None:
    db_path = ROOT / "tests" / f".{test_name}.sqlite"
    _cleanup_sqlite(db_path)
    previous_settings = api_main.settings
    try:
        _build_public_access_test_db(db_path)
        api_main.settings = Settings(db_path=db_path, ors_api_key=None)
        callback(db_path)
    finally:
        api_main.settings = previous_settings
        _cleanup_sqlite(db_path)


def test_public_access_classifies_esteba_rivas_likely_restricted() -> None:
    station, _ = _public_access_station("13073", "ESTEBA RIVAS", 1.00)
    decision = classify_public_access(station)
    _assert(decision.status == "likely_restricted", decision)
    _assert(not is_publicly_eligible(station), decision)


def test_tipo_venta_r_is_restricted() -> None:
    station, _ = _public_access_station("tipo-r", "PUBLIC TEST", 1.00, raw={"Tipo Venta": "R"})
    decision = classify_public_access(station)
    _assert(decision.status == "restricted", decision)
    _assert(not is_publicly_eligible(station), decision)


def test_tipo_venta_missing_empty_and_p_are_safe() -> None:
    missing, _ = _public_access_station("tipo-missing", "PUBLIC TEST", 1.00, raw={})
    empty, _ = _public_access_station("tipo-empty", "PUBLIC TEST", 1.00, raw={"Tipo Venta": "  "})
    public, _ = _public_access_station("tipo-p", "PUBLIC TEST", 1.00, raw={"Tipo Venta": " p "})
    restricted, _ = _public_access_station("tipo-r-space", "PUBLIC TEST", 1.00, raw={"Tipo Venta": " r "})

    _assert(is_publicly_eligible(missing), classify_public_access(missing))
    _assert(is_publicly_eligible(empty), classify_public_access(empty))
    _assert(classify_public_access(public).status == "public", classify_public_access(public))
    _assert(classify_public_access(restricted).status == "restricted", classify_public_access(restricted))


def test_esteba_rivas_label_fallback_is_scoped() -> None:
    unrelated, _ = _public_access_station(
        "other-esteba",
        "ESTEBA RIVAS",
        1.00,
        municipality="Madrid",
        address="Calle Sin Relacion",
    )
    getafe, _ = _public_access_station(
        "other-esteba-getafe",
        "ESTEBA RIVAS",
        1.00,
        municipality="Getafe",
        address="Calle Sin Relacion",
    )
    address_match, _ = _public_access_station(
        "other-esteba-address",
        "ESTEBA RIVAS",
        1.00,
        municipality="Madrid",
        address="Calle Eratostenes",
    )

    _assert(is_publicly_eligible(unrelated), classify_public_access(unrelated))
    _assert(classify_public_access(getafe).status == "likely_restricted", classify_public_access(getafe))
    _assert(classify_public_access(address_match).status == "likely_restricted", classify_public_access(address_match))


def test_curated_public_access_rules_are_likely_restricted() -> None:
    # Only 13073 remains in the curated likely-restricted set after 2026-05 audit.
    for station_id, label in (("13073", "ESTEBA RIVAS"),):
        station, _ = _public_access_station(station_id, label, 1.00)
        decision = classify_public_access(station)
        _assert(decision.status == "likely_restricted", decision)
        _assert(not is_publicly_eligible(station), decision)


def test_unknown_brand_not_excluded_by_default() -> None:
    station, _ = _public_access_station("unknown-public", "UNKNOWN", 1.00, confidence=0.0)
    _assert(is_publicly_eligible(station), classify_public_access(station))


def test_truck_stop_not_excluded_by_keyword_only() -> None:
    station, _ = _public_access_station("truck-public", "TRUCK STOP PUBLIC", 1.00)
    _assert(is_publicly_eligible(station), classify_public_access(station))


def test_coop_logistics_agro_keywords_not_excluded_by_default() -> None:
    for station_id, label in (
        ("coop-public", "COOPERATIVA PUBLICA"),
        ("logistics-public", "LOGISTICA PUBLICA"),
        ("agro-public", "AGRICOLA PUBLICA"),
    ):
        station, _ = _public_access_station(station_id, label, 1.00)
        _assert(is_publicly_eligible(station), classify_public_access(station))


def test_restricted_station_not_returned_by_candidate_query() -> None:
    def check(db_path: Path) -> None:
        candidates = get_candidates_with_price_in_bbox(
            db_path,
            "gasoleo_a",
            min_lat=40.29,
            max_lat=40.31,
            min_lon=-3.74,
            max_lon=-3.72,
        )
        _assert([station.station_id for station, _ in candidates] == ["pa-public"], candidates)
        stations = list_stations(db_path, limit=10)
        _assert([station.station_id for station in stations] == ["pa-public"], stations)

    _with_public_access_db("public_access_candidate_query", check)


def test_restricted_station_not_counted_in_brands() -> None:
    def check(db_path: Path) -> None:
        _assert(list_brands(db_path) == ["BALLENOIL"], list_brands(db_path))
        _assert(canonical_brand_counts(db_path) == {"BALLENOIL": 1}, canonical_brand_counts(db_path))
        raw_counts = raw_brand_label_counts(db_path, limit=10)
        _assert([item["label"] for item in raw_counts] == ["BALLENOIL"], raw_counts)
        brands_response = _json_payload(api_main.brands())
        returned_brands = {item["canonical"]: item["station_count"] for item in brands_response["brands"]}
        _assert(returned_brands == {"BALLENOIL": 1}, brands_response)

    _with_public_access_db("public_access_brand_counts", check)


def test_restricted_station_not_counted_in_coverage_snapshot() -> None:
    def check(db_path: Path) -> None:
        coverage = coverage_snapshot(db_path)
        _assert(coverage["fuel_counts"] == {"gasoleo_a": 1}, coverage)

    _with_public_access_db("public_access_coverage", check)


def test_restricted_station_cannot_appear_in_optimize_results() -> None:
    def check(db_path: Path) -> None:
        request = OptimizationInput(
            origin=Coordinates(40.3000, -3.7300),
            destination=Coordinates(40.3000, -3.7300),
            fuel_type="gasoleo_a",
            liters=30,
            radius_km=10,
            max_candidates=10,
        )
        results = optimize_from_db(db_path, request)
        station_ids = [result.station.station_id for result in results]
        _assert(station_ids == ["pa-public"], station_ids)

    _with_public_access_db("public_access_optimize_results", check)


def test_public_access_filter_reports_restricted_catalog_rows() -> None:
    restricted_station, restricted_price = _public_access_station("13073", "ESTEBA RIVAS", 1.00)
    public_station, public_price = _public_access_station("catalog-public", "BALLENOIL", 1.50)
    stations, prices, report = filter_publicly_eligible_catalog(
        [restricted_station, public_station],
        [restricted_price, public_price],
    )
    _assert([station.station_id for station in stations] == ["catalog-public"], stations)
    _assert([price.station_id for price in prices] == ["catalog-public"], prices)
    _assert(report["excluded_count"] == 1, report)
    _assert(report["examples"][0]["station_id"] == "13073", report)
    _assert(report["examples"][0]["status"] == "likely_restricted", report)
    _assert(report["examples"][0]["reason"] == "reported_controlled_heavy_vehicle_access", report)


def test_token_filtering() -> None:
    html = """
    <script>
      if (item["Direccion"].includes("CASTILLO ALTO")) {}
      if (item["Direccion"].includes("ALZIRA")) {}
      if (item["Direccion"].includes("ALBASANZ")) {}
    </script>
    """
    detail = parse_station_detail(html)
    tokens = detail["tokens"]
    _assert("ALBASANZ" in tokens, f"Station token missing: {tokens}")
    _assert("CASTILLO ALTO" not in tokens, f"Global token leaked: {tokens}")
    _assert("ALZIRA" not in tokens, f"Global token leaked: {tokens}")


def test_catalog_database_and_optimizer() -> None:
    items = [
        {
            "IDEESS": "1001",
            "Rotulo": "BALLENOIL",
            "Direccion": "Calle Uno",
            "C.P.": "28001",
            "Municipio": "Madrid",
            "Provincia": "Madrid",
            "Latitud": "40,4200",
            "Longitud (WGS84)": "-3,7000",
            "Precio Gasoleo A": "1,500",
            "Precio Gasolina 95 E5": "1,650",
        },
        {
            "IDEESS": "1002",
            "Rotulo": "REPSOL",
            "Direccion": "Calle Dos",
            "C.P.": "28002",
            "Municipio": "Madrid",
            "Provincia": "Madrid",
            "Latitud": "40,4300",
            "Longitud (WGS84)": "-3,7100",
            "Precio Gasoleo A": "1,450",
            "Precio Gasolina 95 E5": "1,700",
        },
    ]
    stations, prices = build_catalog_from_minetur(items)
    report = quality_report(stations, prices)
    _assert(report["stations"] == 2, report)
    _assert(report["station_count_known_brand"] == 2, report)
    _assert(report["station_count_unknown_brand"] == 0, report)
    _assert(report["brand_label_count_total"] == 2, report)
    _assert(report["canonical_brand_count"] == 2, report)
    _assert(report["fuel_counts"]["gasoleo_a"] == 2, report)

    db_path = ROOT / "tests" / ".web_pipeline_check.sqlite"
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(db_path) + suffix)
        if candidate.exists():
            candidate.unlink()
    try:
        replace_catalog(db_path, stations, prices, metadata={"source": "TEST"})
        status = price_status(db_path)
        _assert(status["stations"] == 2, status)
        _assert(status["station_count_known_brand"] == 2, status)
        _assert(status["station_count_unknown_brand"] == 0, status)
        _assert(status["brand_label_count_total"] == 2, status)
        _assert(status["canonical_brand_count"] == 2, status)
        _assert(list_brands(db_path) == ["BALLENOIL", "REPSOL"], list_brands(db_path))
        bbox_candidates = get_candidates_with_price_in_bbox(
            db_path,
            "gasoleo_a",
            min_lat=40.419,
            max_lat=40.421,
            min_lon=-3.701,
            max_lon=-3.699,
        )
        _assert([station.station_id for station, _ in bbox_candidates] == ["1001"], bbox_candidates)
        multi_brand_candidates = get_candidates_with_price_in_bbox(
            db_path,
            "gasoleo_a",
            min_lat=40.419,
            max_lat=40.431,
            min_lon=-3.711,
            max_lon=-3.699,
            brands=["REPSOL"],
        )
        _assert([station.station_id for station, _ in multi_brand_candidates] == ["1002"], multi_brand_candidates)
        request = OptimizationInput(
            origin=Coordinates(40.4168, -3.7038),
            destination=Coordinates(40.4168, -3.7038),
            fuel_type="gasoleo_a",
            liters=30,
            radius_km=10,
            max_candidates=10,
        )
        results = optimize_from_db(db_path, request)
        _assert(len(results) == 2, "Expected two optimization candidates.")
        _assert(results[0].total_cost_eur <= results[1].total_cost_eur, "Results are not sorted.")
        _assert("raw" not in results[0].station.public_dict(), "Public station payload leaked raw data.")
        previous_settings = api_main.settings
        api_main.settings = Settings(db_path=db_path, ors_api_key=None)
        try:
            brands_response = _json_payload(api_main.brands())
            returned_brands = {item["canonical"] for item in brands_response["brands"]}
            _assert(returned_brands == {"BALLENOIL", "REPSOL"}, brands_response)
            _assert(all("station_count" in item for item in brands_response["brands"]), brands_response)
            raw_response = api_main.brands_raw(limit=10, offset=0)
            raw_labels = {item["label"] for item in raw_response["items"]}
            _assert(raw_labels == {"BALLENOIL", "REPSOL"}, raw_response)
            catalog_response = api_main.catalog_status()
            _assert(catalog_response["station_count"] == 2, catalog_response)
            _assert(catalog_response["source"] == "TEST", catalog_response)
            health_response = api_main.health()
            _assert(health_response["status"] == "ok", health_response)
            _assert("catalog" not in health_response, health_response)
            response = api_main.optimize(
                api_main.OptimizeRequest(
                    origin_lat=40.4168,
                    origin_lon=-3.7038,
                    destination_lat=40.4168,
                    destination_lon=-3.7038,
                    fuel_type="gasoleo_a",
                    liters=30,
                    radius_km=10,
                    max_candidates=10,
                    result_limit=1,
                )
            )
            _assert(response["count"] == 2, response)
            _assert(response["returned"] == 1, response)
            _assert(response["limit"] == 1, response)
            _assert(len(response["items"]) == 1, response)
            _assert(response["search_policy"] == "economic", response)
            _assert("candidate_pool_size" in response["search"], response)
            _assert("effective_total_cost_eur" in response["best"], response)
            _assert("net_savings_vs_reference_eur" in response["best"], response)
            budget_response = api_main.optimize(
                api_main.OptimizeRequest(
                    origin_lat=40.4168,
                    origin_lon=-3.7038,
                    destination_lat=40.4168,
                    destination_lon=-3.7038,
                    fuel_type="gasoleo_a",
                    input_mode="budget",
                    budget_amount_eur=40,
                    radius_km=10,
                    max_candidates=10,
                    result_limit=2,
                )
            )
            _assert(budget_response["count"] == 2, budget_response)
            _assert(budget_response["best"]["input_mode"] == "budget", budget_response["best"])
            _assert(budget_response["best"]["budget_amount_eur"] == 40, budget_response["best"])
            _assert(budget_response["best"]["station"]["station_id"] == "1002", budget_response["best"])
            _assert(
                abs(budget_response["best"]["gross_refuel_liters"] - (40 / 1.45)) < 0.001,
                budget_response["best"],
            )
            filtered_response = api_main.optimize(
                api_main.OptimizeRequest(
                    origin_lat=40.4168,
                    origin_lon=-3.7038,
                    destination_lat=40.4168,
                    destination_lon=-3.7038,
                    fuel_type="gasoleo_a",
                    liters=30,
                    radius_km=10,
                    max_candidates=10,
                    brands=["REPSOL"],
                )
            )
            _assert(filtered_response["brand_filter"] == ["REPSOL"], filtered_response)
            _assert(filtered_response["count"] == 1, filtered_response)
            _assert(filtered_response["best"]["station"]["brand_canonical"] == "REPSOL", filtered_response)
        finally:
            api_main.settings = previous_settings
    finally:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(db_path) + suffix)
            if candidate.exists():
                candidate.unlink()


class _FixedRouteProvider:
    route_source = "fixed"

    def distances_for_candidates(self, origin, destination, stations):
        return {stations[0].station_id: (7.0, 5.0)}

    def direct_distance_km(self, origin, destination):
        return 10.0


def test_optimizer_charges_extra_detour_only() -> None:
    station = Station(
        station_id="s1",
        brand="TEST",
        name="Station",
        address="",
        postal_code="",
        municipality="",
        province="",
        lat=0.0,
        lon=0.0,
        source="TEST",
    )
    request = OptimizationInput(
        origin=Coordinates(0.0, 0.0),
        destination=Coordinates(0.0, 1.0),
        liters=10.0,
        consumption_l_100km=5.0,
    )
    result = optimize_candidates([(station, 2.0)], request, route_provider=_FixedRouteProvider())[0]
    _assert(result.route_via_station_km == 12.0, result.to_dict())
    _assert(result.direct_route_km == 10.0, result.to_dict())
    _assert(result.extra_detour_km == 2.0, result.to_dict())
    _assert(result.liters_spent_on_route == 0.1, result.to_dict())
    _assert(result.travel_cost_eur == 0.2, result.to_dict())


def test_prefilter_uses_route_corridor_for_trips() -> None:
    stations = [
        Station(
            station_id="near-route",
            brand="TEST",
            name="Near route",
            address="",
            postal_code="",
            municipality="",
            province="",
            lat=0.0,
            lon=0.5,
            source="TEST",
        ),
        Station(
            station_id="off-route",
            brand="TEST",
            name="Off route",
            address="",
            postal_code="",
            municipality="",
            province="",
            lat=0.25,
            lon=0.5,
            source="TEST",
        ),
    ]
    from app.models import Price

    prices = [
        Price("near-route", "gasoleo_a", 1.5, None, "TEST"),
        Price("off-route", "gasoleo_a", 1.0, None, "TEST"),
    ]
    db_path = ROOT / "tests" / ".corridor_check.sqlite"
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(db_path) + suffix)
        if candidate.exists():
            candidate.unlink()
    try:
        replace_catalog(db_path, stations, prices, metadata={"source": "TEST"})
        request = OptimizationInput(
            origin=Coordinates(0.0, 0.0),
            destination=Coordinates(0.0, 1.0),
            fuel_type="gasoleo_a",
            liters=30,
            max_candidates=10,
            corridor_radius_km=10,
            preferred_corridor_km=10,
            economic_expansion_enabled=False,
        )
        candidates = prefilter_candidates(db_path, request)
        _assert([station.station_id for station, _ in candidates] == ["near-route"], candidates)
    finally:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(db_path) + suffix)
            if candidate.exists():
                candidate.unlink()


def test_economic_expansion_can_include_cheap_outer_candidate() -> None:
    stations = [
        Station(
            station_id="near-route",
            brand="TEST",
            name="Near route",
            address="",
            postal_code="",
            municipality="",
            province="",
            lat=0.0,
            lon=0.5,
            source="TEST",
        ),
        Station(
            station_id="cheap-outer",
            brand="TEST",
            name="Cheap outer",
            address="",
            postal_code="",
            municipality="",
            province="",
            lat=0.15,
            lon=0.5,
            source="TEST",
        ),
    ]
    from app.models import Price

    prices = [
        Price("near-route", "gasoleo_a", 1.9, None, "TEST"),
        Price("cheap-outer", "gasoleo_a", 1.0, None, "TEST"),
    ]
    db_path = ROOT / "tests" / ".economic_expansion_check.sqlite"
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(db_path) + suffix)
        if candidate.exists():
            candidate.unlink()
    try:
        replace_catalog(db_path, stations, prices, metadata={"source": "TEST"})
        request = OptimizationInput(
            origin=Coordinates(0.0, 0.0),
            destination=Coordinates(0.0, 1.0),
            fuel_type="gasoleo_a",
            liters=50,
            max_candidates=10,
            preferred_corridor_km=10,
            max_search_extent_km=30,
            economic_expansion_enabled=True,
        )
        candidates = prefilter_candidates(db_path, request)
        _assert("cheap-outer" in {station.station_id for station, _ in candidates}, candidates)
    finally:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(db_path) + suffix)
            if candidate.exists():
                candidate.unlink()


def test_same_place_threshold_controls_search_shape() -> None:
    db_path = ROOT / "tests" / ".same_place_threshold.sqlite"
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(db_path) + suffix)
        if candidate.exists():
            candidate.unlink()
    try:
        station = Station(
            station_id="sp1",
            brand="BALLENOIL",
            name="Ballenoil Centro",
            address="Calle Test",
            postal_code="28000",
            municipality="Madrid",
            province="Madrid",
            lat=40.010,
            lon=-3.000,
            source="TEST",
            brand_label_raw="BALLENOIL",
            brand_canonical="BALLENOIL",
            brand_group="BALLENOIL",
            brand_confidence=1.0,
        )
        price = Price("sp1", "gasoleo_a", 1.40, "2026-04-22", "TEST")
        replace_catalog(db_path, [station], [price], metadata={"source": "TEST"})

        base_request = dict(
            origin=Coordinates(40.000, -3.000),
            destination=Coordinates(40.020, -3.000),
            fuel_type="gasoleo_a",
            liters=30,
            local_search_radius_km=5,
            corridor_radius_km=5,
            max_search_extent_km=10,
            max_candidates=10,
            economic_expansion_enabled=False,
        )
        _, local_trace = prefilter_candidates_with_trace(
            db_path,
            OptimizationInput(**base_request, same_place_threshold_km=3.0),
        )
        _, corridor_trace = prefilter_candidates_with_trace(
            db_path,
            OptimizationInput(**base_request, same_place_threshold_km=0.1),
        )
        _assert(local_trace["search_shape"] == "local_radius", local_trace)
        _assert(corridor_trace["search_shape"] == "route_corridor", corridor_trace)
    finally:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(db_path) + suffix)
            if candidate.exists():
                candidate.unlink()


def test_radius_aliases_are_deprecated_and_conflict_checked() -> None:
    search_field = api_main.OptimizeRequest.model_fields["preferred_search_radius_km"]
    corridor_field = api_main.OptimizeRequest.model_fields["preferred_corridor_km"]
    _assert(search_field.deprecated is not None, "preferred_search_radius_km should be marked deprecated.")
    _assert(corridor_field.deprecated is not None, "preferred_corridor_km should be marked deprecated.")

    legacy_payload = api_main.OptimizeRequest(preferred_search_radius_km=25, preferred_corridor_km=8)
    _assert(legacy_payload.effective_local_search_radius_km() == 25, "Legacy local radius alias not honored.")
    _assert(legacy_payload.effective_corridor_radius_km() == 8, "Legacy corridor radius alias not honored.")
    _assert(
        legacy_payload.deprecated_parameters_used() == ["preferred_search_radius_km", "preferred_corridor_km"],
        "Deprecated parameter usage not reported.",
    )

    conflicting_payload = api_main.OptimizeRequest(
        local_search_radius_km=25,
        preferred_search_radius_km=30,
    )
    try:
        api_main._reject_conflicting_radius_aliases(conflicting_payload)
    except HTTPException as exc:
        _assert(exc.status_code == 400, f"Unexpected status for conflicting aliases: {exc.status_code}")
    else:
        raise AssertionError("Expected conflicting radius aliases to be rejected.")


def test_address_without_ors_key_is_client_error() -> None:
    previous_settings = api_main.settings
    api_main.settings = Settings(db_path=ROOT / "tests" / ".missing.sqlite", ors_api_key=None)
    try:
        payload = api_main.OptimizeRequest(
            origin_address="Puerta del Sol, Madrid",
            destination_address="Puerta del Sol, Madrid",
            fuel_type="gasoleo_a",
            liters=30,
        )
        try:
            api_main.optimize(payload)
        except HTTPException as exc:
            _assert(exc.status_code == 400, f"Unexpected status: {exc.status_code}")
        else:
            raise AssertionError("Expected HTTPException for address geocoding without ORS_API_KEY.")
    finally:
        api_main.settings = previous_settings


def test_geocode_without_ors_key_is_client_error() -> None:
    previous_settings = api_main.settings
    api_main.settings = Settings(db_path=ROOT / "tests" / ".missing.sqlite", ors_api_key=None)
    try:
        try:
            api_main.geocode(q="Madrid")
        except HTTPException as exc:
            _assert(exc.status_code == 400, f"Unexpected status: {exc.status_code}")
        else:
            raise AssertionError("Expected HTTPException for geocoding without ORS_API_KEY.")
    finally:
        api_main.settings = previous_settings


def test_geocode_endpoint_accepts_size_15_and_autocomplete_param() -> None:
    """Ensure the server's geocode_endpoint allows size=15 (what the JS sends).
    If le drops below 15 the browser gets a 422 with a list detail and shows
    'No se pudo buscar el lugar'.  Autocomplete stays enabled by default, with
    geocode/search as the server-side fallback."""
    import inspect

    sig = inspect.signature(api_main.geocode_endpoint)
    size_param = sig.parameters["size"]
    metadata = size_param.default.metadata if hasattr(size_param.default, "metadata") else []
    le_values = [m.le for m in metadata if hasattr(m, "le")]
    _assert(le_values and le_values[0] >= 15, (
        f"geocode_endpoint 'size' must accept at least 15 (JS sends size=15); "
        f"found le={le_values}"
    ))
    autocomplete_param = sig.parameters.get("autocomplete")
    _assert(autocomplete_param is not None, "geocode_endpoint must expose the autocomplete query parameter.")
    _assert(
        getattr(autocomplete_param.default, "default", None) is True,
        "geocode_endpoint autocomplete must default to true.",
    )

    helper_sig = inspect.signature(api_main.geocode)
    helper_autocomplete = helper_sig.parameters.get("autocomplete")
    _assert(helper_autocomplete is not None, "geocode helper must accept autocomplete.")
    _assert(helper_autocomplete.default is True, "geocode helper autocomplete must default to true.")


def test_geocode_autocomplete_falls_back_to_search() -> None:
    original_autocomplete = api_main.geocode_candidates_autocomplete
    original_search = api_main.geocode_candidates
    fallback_item = {"label": "Madrid", "title": "Madrid", "lat": 40.4168, "lon": -3.7038}

    try:
        for autocomplete_result in ("error", "empty"):
            calls: list[tuple[str, int | None]] = []

            def fake_autocomplete(*args, **kwargs):
                calls.append(("autocomplete", kwargs.get("size")))
                if autocomplete_result == "error":
                    raise RuntimeError("autocomplete unavailable")
                return []

            def fake_search(*args, **kwargs):
                calls.append(("search", kwargs.get("size")))
                return [fallback_item]

            api_main.geocode_candidates_autocomplete = fake_autocomplete
            api_main.geocode_candidates = fake_search
            result = api_main.geocode(q="Madrid", size=15, autocomplete=True)

            _assert(result == {"items": [fallback_item]}, result)
            _assert(calls == [("autocomplete", 15), ("search", 15)], calls)
    finally:
        api_main.geocode_candidates_autocomplete = original_autocomplete
        api_main.geocode_candidates = original_search


def test_geocode_precise_query_variants_prefer_fast_relevant_searches() -> None:
    variants = api_main._geocode_query_variants("Travesia de Antonio Nebrija, 4")
    normalized = [api_main._normalize_geocode_query(value) for value in variants]

    _assert(normalized[0] == "travesia antonio nebrija", variants)
    _assert("travesia de antonio nebrija" in normalized, variants)
    _assert("travesia antonio nebrija" in normalized, variants)
    _assert("trv. antonio nebrija" in normalized, variants)
    _assert(normalized[-1] == "travesia de antonio nebrija, 4", variants)


def test_stopover_route_endpoint_returns_two_legs() -> None:
    original_provider = api_main.ORSRouteProvider

    class FixedGeometryProvider:
        def __init__(self, settings=None):
            self.settings = settings

        def route_geometry(self, origin, destination):
            return [
                origin,
                Coordinates(
                    lat=(origin.lat + destination.lat) / 2,
                    lon=(origin.lon + destination.lon) / 2,
                ),
                destination,
            ]

    api_main.ORSRouteProvider = FixedGeometryProvider
    try:
        payload = api_main.RouteStopoverRequest(
            origin_lat=40.0,
            origin_lon=-3.0,
            station_lat=40.5,
            station_lon=-3.5,
            destination_lat=41.0,
            destination_lon=-4.0,
        )
        result = api_main.route_stopover(payload)
    finally:
        api_main.ORSRouteProvider = original_provider

    _assert(result["route_source"] == "openrouteservice_directions", result)
    _assert([leg["name"] for leg in result["legs"]] == ["origin_to_station", "station_to_destination"], result)
    _assert(len(result["legs"][0]["geometry"]) == 3, result)
    _assert(len(result["legs"][1]["geometry"]) == 3, result)


def test_home_ui_uses_map_search_without_coordinate_fields() -> None:
    html = api_main.root()
    app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
    frontend = "\n".join([html, app_js, styles])
    _assert("map_search" in html, "Map search input missing from home UI.")
    _assert("refresh_catalog" not in html, "Manual catalog refresh button should not be exposed in the UI.")
    _assert("/static/styles.css" in html, "Home UI should load extracted CSS.")
    _assert("/static/app.js" in html, "Home UI should load extracted JS.")
    _assert("Precios actualizados:" in frontend, "Price freshness timestamp missing from frontend.")
    _assert("Precios descargados:" not in frontend, "Old downloaded price copy should not remain.")
    _assert("Última actualización de precios:" not in frontend, "Header should not claim an official price update date.")
    _assert("Actualizado correctamente:" not in frontend, "Header should not show local refresh as price freshness.")
    _assert("Actualizado" not in html, "Price chip should not show a separate updated text label.")
    _assert("Snapshot" not in html and "Degradado" not in html, "Price chip should not show technical state labels.")
    _assert("source_fetched_at" in frontend, "Visible price timestamp should use source_fetched_at.")
    _assert("source_fetch_completed_at" in frontend, "Visible price timestamp should fall back to source_fetch_completed_at.")
    _assert("/catalog/refresh" not in app_js, "Frontend JS must not call the manual catalog refresh endpoint.")
    _assert("loadCatalogStatus" in frontend, "Home UI should load catalog refresh status.")
    _assert("catalog_freshness_dot" in html, "Catalog freshness indicator missing from home UI.")
    _assert("catalogFreshnessClass" in app_js, "Catalog freshness color helper missing from frontend.")
    _assert("freshness-fresh" in frontend, "Same-day freshness color class missing.")
    _assert("freshness-recent" in frontend, "Recent freshness color class missing.")
    _assert("freshness-stale" in frontend, "Stale freshness color class missing.")
    _assert("Catálogo degradado" not in frontend, "Degraded catalog copy should not be visible in frontend.")
    _assert("brand_checks" in html, "Brand checkbox grid missing from home UI.")
    _assert("consumption_l_100km" in html, "Average consumption input missing from home UI.")
    _assert("parsePositiveDecimal('consumption_l_100km')" in frontend, "Average consumption input should be validated before optimize.")
    _assert("consumption_l_100km: consumption" in frontend, "Optimize payload should use the custom average consumption value.")
    _assert("consumption_l_100km: 5.5" not in frontend, "Optimize payload should not hardcode average consumption.")
    _assert('name="brand_filter"' in frontend, "Brand checkbox inputs missing from home UI.")
    _assert("leaflet" in html.lower(), "Leaflet map assets missing from home UI.")
    _assert("Latitud" not in html, "Visible latitude field leaked into home UI.")
    _assert("Longitud" not in html, "Visible longitude field leaked into home UI.")
    _assert("Con ORS API Key" not in html, "Old ORS explainer copy leaked into home UI.")
    _assert("Autom" not in html, "Old automatic search copy leaked into home UI.")
    _assert("Llena tu depósito sin vaciar tu cartera" in html, "Target sidebar headline missing from home UI.")
    _assert("Ahorra en cada repostaje" not in html, "Temporary sidebar headline should not remain.")
    _assert("station-pin" in frontend, "Station map pin styling missing from home UI.")
    _assert("config_sidebar" in html, "Left configuration sidebar missing from home UI.")
    sidebar_html = html[html.find('id="config_sidebar"'):html.find('class="stage')]
    _assert("Salida" not in sidebar_html, "Sidebar should not include a duplicated route origin block.")
    _assert("sidebar_toggle" not in html, "Sidebar collapse toggle should not exist in map-first UI.")
    _assert(".sidebar-toggle::before" not in frontend, "Old sidebar toggle styling should not remain.")
    _assert("sidebar-collapsed" not in frontend, "Old sidebar collapsed layout should not remain.")
    _assert("floating-search" in html, "Floating top search structure missing from home UI.")
    _assert("route-search-bar" in html, "Route search bar missing from home UI.")
    _assert("floating-sidebar" in html, "Compact sidebar visual structure missing from home UI.")
    _assert("route-input-slot" in html, "Search input should be integrated into the active route point.")
    search_html = html[html.find('class="map-top'):html.find('id="route_status"')]
    _assert("return_to_origin" in search_html, "Return-to-origin toggle should live inside the top search UI.")
    _assert("return-toggle-compact" in html, "Return-to-origin toggle should be integrated into search UI.")
    _assert("syncReturnMode" in app_js, "Return-to-origin behavior should remain wired in JS.")
    _assert("map.invalidateSize" in frontend, "Map should still be able to resize after layout updates.")
    _assert("mapCenterForStation" in frontend, "Station selection should compute an offset map center.")
    _assert("focusStation(station" in frontend, "Station selection should pan smoothly to the selected station.")
    _assert("selectedStation" in frontend, "Selected station state should be tracked.")
    _assert("L.featureGroup(layers).getBounds()" not in frontend, "Selecting result stations should not zoom aggressively with result fitBounds.")
    _assert("route_status" in html, "Route status indicator missing from map UI.")
    _assert("fetch('/route/stopover'" in frontend, "Selected station route should call the stopover route endpoint.")
    _assert("drawStopoverRoute" in frontend, "Map should draw the selected route geometry.")
    _assert("L.polyline" in frontend, "Map should render route legs as polylines.")
    _assert("state.routeKey === key" in frontend, "Map should avoid recalculating unchanged stopover routes.")
    _assert("origin_to_station" in frontend or "/route/stopover" in frontend, "Route should model origin-station-destination legs.")
    _assert("toggle_alternatives" in frontend, "Alternatives toggle missing from result UI.")
    _assert("alternatives_panel" in frontend, "Alternatives panel missing from result UI.")
    _assert("max-height .28s ease" in frontend, "Alternatives accordion should animate height.")
    _assert('aria-hidden="${String(!alternativesOpen)}"' in frontend, "Alternatives accordion should expose hidden state.")
    _assert("panel.setAttribute('aria-hidden', String(!isOpen))" in frontend, "Alternatives accordion should update hidden state.")
    _assert("data-result-index" in frontend, "Alternative result rows should be selectable.")
    _assert("brand-toggle" in frontend, "Brand rows should use right-aligned toggles.")
    _assert("brand-copy" in frontend, "Brand rows should include label and subtitle copy.")
    _assert("select_all_brands" in html, "Brand selector should expose an all-brands button.")
    _assert('class="link-button active" type="button" aria-pressed="true">Todas' in html, "All-brands button should start active.")
    _assert('name="brand_filter" value="${escapeHtml(brand.canonical)}" checked' in frontend, "Brand inputs should start checked.")
    _assert("input.checked = shouldSelectAll" in frontend, "All-brands button should toggle every brand input.")
    _assert("allBrandsSelected" in frontend, "Brand filter state should track whether every brand is selected.")
    _assert("selectedBrands().length > 10" in frontend, "Frontend should block more than 10 selected brands.")
    _assert("excludedBrands" in frontend, "Frontend should model all-except brand filtering.")
    _assert("payload.excluded_brands = excluded" in frontend, "Optimize payload should support brand exclusions.")
    _assert("Pulsa Todas para incluirlas todas." not in html, "Brand limit should not show explanatory copy.")
    _assert("shouldFilterByBrands" in frontend, "Optimize payload should omit brands when all brands are selected.")
    _assert("overflow: hidden" in frontend, "Desktop page should be constrained to the viewport.")
    _assert("url.searchParams.set('size', '15')" in frontend, "Map search should request 15 candidates for reranking.")
    _assert("rerankSuggestions" in frontend, "Map search should locally rerank suggestions.")
    _assert("ranked[Number(button.dataset.idx)]" in frontend, "Suggestion clicks should resolve from the reranked list.")
    _assert("geocodeErrorMessage" in frontend, "Map search should handle structured backend errors explicitly.")
    _assert("isLegacySizeValidationError" in frontend, "Map search should detect legacy size=10 validation errors.")
    _assert("url.searchParams.set('size', '10')" in frontend, "Map search should retry size=10 against legacy geocode endpoints.")
    _assert("new AbortController()" in frontend, "Map search should cancel stale autocomplete requests.")
    _assert("searchRequestId" in frontend, "Map search should ignore stale autocomplete responses.")
    _assert("SEARCH_TIMEOUT_MS" in frontend, "Map search should not stay indefinitely in loading state.")
    _assert("streetType(str)" in frontend, "Map search reranking should account for Spanish street-type precision.")
    _assert("clearTimeout(searchTimer);\n      searchPlaces();" in frontend, "Search button should cancel pending debounce before searching.")
    _assert("function dismissSearchSuggestions()" in frontend, "Map search should dismiss open suggestions on outside clicks.")
    _assert(
        "map.on('click', () =>" in frontend or "map.on('click', (event) =>" in frontend,
        "Map clicks should close open search suggestions.",
    )
    _assert("syncPointUI(state.active)" in frontend, "Dismissing suggestions should restore the active point display.")
    _assert("$('map_search').blur()" in frontend, "Dismissing suggestions should blur the search input.")
    _assert('id="result" class="result" data-empty="true"></section>' in html, "Initial result card should be hidden.")
    _assert("Sin cálculo" not in html, "Initial no-result copy leaked into home UI.")


def test_health_unavailable_db_is_503() -> None:
    previous_settings = api_main.settings
    api_main.settings = Settings(db_path=ROOT / "tests", ors_api_key=None)
    try:
        try:
            api_main.health()
        except HTTPException as exc:
            _assert(exc.status_code == 503, f"Unexpected status: {exc.status_code}")
        else:
            raise AssertionError("Expected HTTPException 503 for unavailable database.")
    finally:
        api_main.settings = previous_settings


def test_optimize_warnings_have_structured_shape() -> None:
    def check() -> None:
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_a",
                liters=30,
                use_ors=False,
            )
        )
        _assert("warnings" in response, response)
        _assert(isinstance(response["warnings"], list), response["warnings"])
        for item in response["warnings"]:
            _assert(isinstance(item, dict), item)
            _assert(item.get("code"), item)
            _assert(item.get("severity") in {"info", "warning", "critical"}, item)
            _assert(item.get("title"), item)
            _assert(item.get("message"), item)

    _with_warning_db("warnings_shape", check)


def test_low_fuel_coverage_warning_for_rare_fuel() -> None:
    def check() -> None:
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasolina_98e10",
                liters=20,
                use_ors=False,
            )
        )
        warning = _warning_by_code(response, "low_fuel_coverage")
        _assert(warning["data"]["fuel_type"] == "gasolina_98e10", warning)
        _assert(warning["data"]["coverage_count"] == 1, warning)

    _with_warning_db("low_fuel_coverage", check)


def test_brand_filter_warning_when_zero_results() -> None:
    def check() -> None:
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_a",
                liters=30,
                brands=["NOPE"],
                use_ors=False,
            )
        )
        _assert(response["count"] == 0, response)
        warning = _warning_by_code(response, "brand_filter_too_restrictive")
        _assert(warning["severity"] == "warning", warning)
        _assert(warning["data"]["selected_brands"] == ["NOPE"], warning)

    _with_warning_db("brand_filter_zero", check)


def test_haversine_warning_when_use_ors_false() -> None:
    def check() -> None:
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_a",
                liters=30,
                use_ors=False,
            )
        )
        warning = _warning_by_code(response, "using_haversine_estimate")
        _assert(warning["severity"] == "info", warning)
        _assert(warning["data"]["route_source"] == "haversine_estimate", warning)

    _with_warning_db("haversine_warning", check)


def test_deprecated_parameters_emitted_as_structured_warning() -> None:
    def check() -> None:
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_a",
                liters=30,
                preferred_search_radius_km=25,
                use_ors=False,
            )
        )
        warning = _warning_by_code(response, "deprecated_parameters")
        _assert("preferred_search_radius_km" in warning["data"]["parameters"], warning)

    _with_warning_db("deprecated_warning", check)


def test_catalog_degraded_warning_propagates() -> None:
    def check() -> None:
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_a",
                liters=30,
                use_ors=False,
            )
        )
        warning = _warning_by_code(response, "catalog_degraded")
        _assert(warning["severity"] == "warning", warning)
        _assert(warning["data"]["refresh_status"] == "degraded", warning)

    _with_warning_db(
        "catalog_degraded_warning",
        check,
        metadata={
            "source": "MINETUR_SNAPSHOT",
            "refresh_status": "degraded",
            "degraded": "true",
            "degraded_reasons": '["fixture degraded"]',
        },
    )


def test_independent_brands_excluded_warning() -> None:
    def check() -> None:
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_a",
                liters=30,
                brands=["BALLENOIL"],
                use_ors=False,
            )
        )
        warning = _warning_by_code(response, "independent_brands_excluded_or_hidden")
        _assert(warning["data"]["hidden_independent_count"] >= 1, warning)

    _with_warning_db("independent_brands_warning", check)


def test_catalog_snapshot_warning_only_when_not_degraded() -> None:
    def check_snapshot() -> None:
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_a",
                liters=30,
                use_ors=False,
            )
        )
        _assert("catalog_snapshot_source" in _warning_codes(response), response["warnings"])

    _with_warning_db(
        "catalog_snapshot_warning",
        check_snapshot,
        metadata={
            "source": "MINETUR_SNAPSHOT",
            "refresh_status": "ok",
            "degraded": "false",
            "source_reference_date": "2026-04-22T00:00:00+00:00",
        },
    )

    def check_degraded_snapshot() -> None:
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_a",
                liters=30,
                use_ors=False,
            )
        )
        codes = _warning_codes(response)
        _assert("catalog_degraded" in codes, response["warnings"])
        _assert("catalog_snapshot_source" not in codes, response["warnings"])

    _with_warning_db(
        "catalog_degraded_snapshot_warning",
        check_degraded_snapshot,
        metadata={
            "source": "MINETUR_SNAPSHOT",
            "refresh_status": "degraded",
            "degraded": "true",
            "degraded_reasons": '["fixture degraded"]',
            "source_reference_date": "2026-04-22T00:00:00+00:00",
        },
    )


def test_stale_reference_prices_warning() -> None:
    def check() -> None:
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_a",
                liters=30,
                use_ors=False,
            )
        )
        warning = _warning_by_code(response, "stale_reference_prices")
        _assert(warning["data"]["age_days"] >= 365, warning)
        _assert(warning["data"]["threshold_days"] == 7, warning)

    _with_warning_db(
        "stale_reference_prices_warning",
        check,
        metadata={
            "source": "TEST",
            "refresh_status": "ok",
            "degraded": "false",
            "source_reference_date": "2024-01-01T00:00:00+00:00",
        },
    )


def test_no_candidates_excludes_extent_limit_warning() -> None:
    def check() -> None:
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_b",
                liters=30,
                use_ors=False,
            )
        )
        _assert(response["count"] == 0, response)
        codes = _warning_codes(response)
        _assert("no_candidates_in_radius" in codes, response["warnings"])
        _assert("search_extent_limit_reached" not in codes, response["warnings"])

    _with_warning_db("no_candidates_without_extent_limit", check)


def test_haversine_copy_not_duplicated() -> None:
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    _assert(js.count("Ruta estimada por distancia") == 1, "Haversine copy should appear once.")


def _is_independent_station(station: dict) -> bool:
    return (
        station.get("brand_canonical") == "UNKNOWN"
        or station.get("brand_confidence") is None
        or float(station.get("brand_confidence") or 0) < 1.0
    )


def test_brands_endpoint_includes_virtual_independent() -> None:
    def check() -> None:
        response = _json_payload(api_main.brands())
        items = response["brands"]
        virtual = [item for item in items if item.get("canonical") == INDEPENDENT_BRAND_SENTINEL]
        _assert(len(virtual) == 1, items)
        _assert(virtual[0]["is_virtual"] is True, virtual[0])
        _assert(virtual[0]["station_count"] >= 1, virtual[0])
        _assert(items[-1]["canonical"] == INDEPENDENT_BRAND_SENTINEL, items)

    _with_independent_brand_db("brands_virtual_independent", check)


def test_brands_endpoint_omits_virtual_when_no_independents() -> None:
    def check() -> None:
        response = _json_payload(api_main.brands())
        canonicals = [item.get("canonical") for item in response["brands"]]
        _assert(INDEPENDENT_BRAND_SENTINEL not in canonicals, response)

    _with_independent_brand_db("brands_without_virtual_independent", check, include_independent=False)


def test_optimize_without_filter_includes_independents() -> None:
    def check() -> None:
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_a",
                liters=30,
                use_ors=False,
            )
        )
        stations = [item["station"] for item in response["items"]]
        _assert(response["brand_filter"] == [], response)
        _assert(any(_is_independent_station(station) for station in stations), stations)

    _with_independent_brand_db("optimize_no_filter_independents", check)


def test_optimize_with_real_brand_only_excludes_independents() -> None:
    def check() -> None:
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_a",
                liters=30,
                brands=["BALLENOIL"],
                use_ors=False,
            )
        )
        stations = [item["station"] for item in response["items"]]
        _assert(stations, response)
        _assert(not any(_is_independent_station(station) for station in stations), stations)
        _assert("independent_brands_excluded_or_hidden" in _warning_codes(response), response["warnings"])

    _with_independent_brand_db("optimize_real_brand_excludes_independents", check)


def test_optimize_with_excluded_brand_keeps_all_except_that_brand() -> None:
    def check() -> None:
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_a",
                liters=30,
                excluded_brands=["BALLENOIL"],
                use_ors=False,
            )
        )
        stations = [item["station"] for item in response["items"]]
        _assert(response["brand_filter"] == [], response)
        _assert(response["brand_exclusions"] == ["BALLENOIL"], response)
        _assert(stations, response)
        _assert(not any(station.get("brand_canonical") == "BALLENOIL" for station in stations), stations)
        _assert(any(_is_independent_station(station) for station in stations), stations)

    _with_independent_brand_db("optimize_excluded_brand", check)


def test_optimize_excluded_alcampo_removes_best_and_items() -> None:
    db_path = ROOT / "tests" / ".optimize_excluded_alcampo.sqlite"
    _cleanup_sqlite(db_path)
    previous_settings = api_main.settings
    try:
        stations = [
            Station(
                station_id="alc1",
                brand="ALCAMPO",
                name="ALCAMPO Alcorcon",
                address="Calle Alcampo",
                postal_code="28922",
                municipality="Alcorcon",
                province="Madrid",
                lat=40.3500,
                lon=-3.8200,
                source="TEST",
                brand_label_raw="ALCAMPO",
                brand_canonical="ALCAMPO",
                brand_group="ALCAMPO",
                brand_confidence=1.0,
            ),
            Station(
                station_id="alc2",
                brand="ALCAMPO FUENLABRADA",
                name="ALCAMPO FUENLABRADA",
                address="Calle Variante",
                postal_code="28942",
                municipality="Fuenlabrada",
                province="Madrid",
                lat=40.2850,
                lon=-3.7950,
                source="TEST",
                brand_label_raw="ALCAMPO FUENLABRADA",
                brand_canonical="ALCAMPO FUENLABRADA",
                brand_group="ALCAMPO FUENLABRADA",
                brand_confidence=0.5,
            ),
            Station(
                station_id="rep1",
                brand="REPSOL",
                name="REPSOL Alcorcon",
                address="Calle Repsol",
                postal_code="28922",
                municipality="Alcorcon",
                province="Madrid",
                lat=40.3510,
                lon=-3.8210,
                source="TEST",
                brand_label_raw="REPSOL",
                brand_canonical="REPSOL",
                brand_group="REPSOL",
                brand_confidence=1.0,
            ),
        ]
        prices = [
            Price("alc1", "gasoleo_a", 1.10, "2026-04-22", "TEST"),
            Price("alc2", "gasoleo_a", 1.05, "2026-04-22", "TEST"),
            Price("rep1", "gasoleo_a", 1.70, "2026-04-22", "TEST"),
        ]
        replace_catalog(db_path, stations, prices, metadata={"source": "TEST"})
        api_main.settings = Settings(db_path=db_path, ors_api_key=None)
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_a",
                liters=30,
                excluded_brands=["Alcampo"],
                use_ors=False,
                result_limit=10,
            )
        )
        stations_payload = [item["station"] for item in response["items"]]
        _assert(response["brand_exclusions"] == ["ALCAMPO"], response)
        _assert(response["best"]["station"]["brand_canonical"] == "REPSOL", response)
        _assert(stations_payload, response)
        for station in stations_payload:
            combined = " ".join(
                str(station.get(key) or "")
                for key in ("name", "brand", "brand_canonical", "brand_label_raw", "brand_group")
            ).upper()
            _assert("ALCAMPO" not in combined, stations_payload)
    finally:
        api_main.settings = previous_settings
        _cleanup_sqlite(db_path)


def test_optimize_inclusive_brands_returns_only_selected_brands() -> None:
    db_path = ROOT / "tests" / ".optimize_inclusive_brands.sqlite"
    _cleanup_sqlite(db_path)
    previous_settings = api_main.settings
    try:
        stations = [
            Station(
                station_id="rep1",
                brand="REPSOL",
                name="REPSOL Madrid",
                address="Calle Repsol",
                postal_code="28001",
                municipality="Madrid",
                province="Madrid",
                lat=40.4168,
                lon=-3.7038,
                source="TEST",
                brand_label_raw="REPSOL",
                brand_canonical="REPSOL",
                brand_group="REPSOL",
                brand_confidence=1.0,
            ),
            Station(
                station_id="cep1",
                brand="CEPSA",
                name="CEPSA Madrid",
                address="Calle Cepsa",
                postal_code="28002",
                municipality="Madrid",
                province="Madrid",
                lat=40.4178,
                lon=-3.7048,
                source="TEST",
                brand_label_raw="CEPSA",
                brand_canonical="CEPSA",
                brand_group="CEPSA",
                brand_confidence=1.0,
            ),
            Station(
                station_id="alc1",
                brand="ALCAMPO",
                name="ALCAMPO Madrid",
                address="Calle Alcampo",
                postal_code="28003",
                municipality="Madrid",
                province="Madrid",
                lat=40.4188,
                lon=-3.7058,
                source="TEST",
                brand_label_raw="ALCAMPO",
                brand_canonical="ALCAMPO",
                brand_group="ALCAMPO",
                brand_confidence=1.0,
            ),
        ]
        prices = [
            Price("rep1", "gasoleo_a", 1.60, "2026-04-22", "TEST"),
            Price("cep1", "gasoleo_a", 1.62, "2026-04-22", "TEST"),
            Price("alc1", "gasoleo_a", 1.10, "2026-04-22", "TEST"),
        ]
        replace_catalog(db_path, stations, prices, metadata={"source": "TEST"})
        api_main.settings = Settings(db_path=db_path, ors_api_key=None)
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_a",
                liters=30,
                brands=["REPSOL", "CEPSA"],
                use_ors=False,
                result_limit=10,
            )
        )
        stations_payload = [item["station"] for item in response["items"]]
        _assert(response["brand_filter"] == ["REPSOL", "CEPSA"], response)
        _assert(stations_payload, response)
        for station in stations_payload:
            _assert(station.get("brand_canonical") in {"REPSOL", "CEPSA"}, stations_payload)
    finally:
        api_main.settings = previous_settings
        _cleanup_sqlite(db_path)


def test_optimize_rejects_inclusive_and_excluded_brands_together() -> None:
    try:
        api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_a",
                liters=30,
                brands=["REPSOL"],
                excluded_brands=["ALCAMPO"],
                use_ors=False,
            )
        )
    except HTTPException as exc:
        _assert(exc.status_code == 400, exc)
        _assert("No combines brands con excluded_brands" in str(exc.detail), exc.detail)
    else:
        raise AssertionError("Expected HTTPException when brands and excluded_brands are combined.")


def test_optimize_with_virtual_only_returns_independents() -> None:
    def check() -> None:
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_a",
                liters=30,
                brands=[INDEPENDENT_BRAND_SENTINEL],
                use_ors=False,
            )
        )
        stations = [item["station"] for item in response["items"]]
        _assert(stations, response)
        _assert(all(_is_independent_station(station) for station in stations), stations)
        _assert("independent_brands_excluded_or_hidden" not in _warning_codes(response), response["warnings"])

    _with_independent_brand_db("optimize_virtual_only_independents", check)


def test_optimize_with_real_and_virtual_returns_both() -> None:
    def check() -> None:
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_a",
                liters=30,
                brands=["BALLENOIL", INDEPENDENT_BRAND_SENTINEL],
                use_ors=False,
            )
        )
        stations = [item["station"] for item in response["items"]]
        _assert(any(station.get("brand_canonical") == "BALLENOIL" for station in stations), stations)
        _assert(any(_is_independent_station(station) for station in stations), stations)
        _assert("independent_brands_excluded_or_hidden" not in _warning_codes(response), response["warnings"])

    _with_independent_brand_db("optimize_real_and_virtual_independents", check)


def test_independent_warning_suppressed_when_virtual_included() -> None:
    def check() -> None:
        response = api_main.optimize(
            api_main.OptimizeRequest(
                origin_lat=40.4168,
                origin_lon=-3.7038,
                destination_lat=40.4168,
                destination_lon=-3.7038,
                fuel_type="gasoleo_a",
                liters=30,
                brands=["BALLENOIL", INDEPENDENT_BRAND_SENTINEL],
                use_ors=False,
            )
        )
        _assert("independent_brands_excluded_or_hidden" not in _warning_codes(response), response["warnings"])

    _with_independent_brand_db("independent_warning_suppressed", check)


def test_brand_filter_sql_with_only_virtual_returns_independent_clause() -> None:
    params: list[object] = []
    clause = _brand_filter_sql([INDEPENDENT_BRAND_SENTINEL], params)
    _assert("brand_canonical = 'UNKNOWN'" in clause, clause)
    _assert("brand_confidence IS NULL" in clause, clause)
    _assert("brand_confidence < 1.0" in clause, clause)
    _assert(params == [], params)


def test_moeve_compound_label_included_in_cepsa_filter() -> None:
    """A station ingested with raw label 'MOEVE VILANOVA' and canonical CEPSA must be
    returned by get_candidates_with_price_in_bbox when brands=['CEPSA']."""
    db_path = ROOT / "tests" / ".moeve_compound_filter.sqlite"
    _cleanup_sqlite(db_path)
    try:
        station = Station(
            station_id="mc1",
            brand="CEPSA",
            name="Moeve Vilanova",
            address="CARRER TEST 1",
            postal_code="08800",
            municipality="VILANOVA I LA GELTRU",
            province="BARCELONA",
            lat=41.22,
            lon=1.72,
            source="TEST",
            last_seen_at="2026-01-01",
            brand_label_raw="MOEVE VILANOVA",
            brand_canonical="CEPSA",
            brand_group="CEPSA",
            brand_confidence=1.0,
        )
        price = Price("mc1", "gasoleo_a", 1.45, "2026-01-01", "TEST")
        replace_catalog(db_path, [station], [price])
        results = get_candidates_with_price_in_bbox(
            db_path,
            fuel_type="gasoleo_a",
            min_lat=40.0, max_lat=42.5,
            min_lon=0.5, max_lon=3.0,
            brands=["CEPSA"],
        )
        _assert(len(results) == 1, f"Expected 1 result for CEPSA filter, got {len(results)}")
        station_out, price_out = results[0]
        _assert(station_out.brand_label_raw == "MOEVE VILANOVA", station_out.brand_label_raw)
        _assert(station_out.brand_canonical == "CEPSA", station_out.brand_canonical)
        _assert(abs(price_out - 1.45) < 1e-6, price_out)
    finally:
        _cleanup_sqlite(db_path)


def test_known_brand_token_label_included_in_brand_filter() -> None:
    db_path = ROOT / "tests" / ".brand_token_filter.sqlite"
    _cleanup_sqlite(db_path)
    try:
        stations, prices = build_catalog_from_minetur([
            {
                "IDEESS": "bt1",
                "Rotulo": "AREA SERVICIO REPSOL NORTE",
                "Direccion": "CALLE TEST 1",
                "C.P.": "28001",
                "Municipio": "MADRID",
                "Provincia": "MADRID",
                "Latitud": "40,4168",
                "Longitud (WGS84)": "-3,7038",
                "Precio Gasoleo A": "1,500",
            }
        ])
        replace_catalog(db_path, stations, prices)
        results = get_candidates_with_price_in_bbox(
            db_path,
            fuel_type="gasoleo_a",
            min_lat=40.0,
            max_lat=41.0,
            min_lon=-4.0,
            max_lon=-3.0,
            brands=["REPSOL"],
        )
        _assert(len(results) == 1, f"Expected 1 result for REPSOL token label, got {len(results)}")
        station_out, _price_out = results[0]
        _assert(station_out.brand_label_raw == "AREA SERVICIO REPSOL NORTE", station_out.brand_label_raw)
        _assert(station_out.brand_canonical == "REPSOL", station_out.brand_canonical)
        _assert(station_out.brand_confidence == 1.0, station_out.brand_confidence)
    finally:
        _cleanup_sqlite(db_path)


def test_targeted_brand_family_labels_included_in_brand_filter() -> None:
    db_path = ROOT / "tests" / ".targeted_brand_family_filter.sqlite"
    _cleanup_sqlite(db_path)
    try:
        stations, prices = build_catalog_from_minetur([
            {
                "IDEESS": "tf1",
                "Rotulo": "AN ENERGETICOS - TAFALLA",
                "Direccion": "CALLE TEST 1",
                "C.P.": "31300",
                "Municipio": "TAFALLA",
                "Provincia": "NAVARRA",
                "Latitud": "42,5266",
                "Longitud (WGS84)": "-1,6745",
                "Precio Gasoleo A": "1,500",
            },
            {
                "IDEESS": "tf2",
                "Rotulo": '"BP"BEGUR',
                "Direccion": "CALLE TEST 2",
                "C.P.": "17255",
                "Municipio": "BEGUR",
                "Provincia": "GIRONA",
                "Latitud": "41,9535",
                "Longitud (WGS84)": "3,2070",
                "Precio Gasoleo A": "1,600",
            },
            {
                "IDEESS": "tf3",
                "Rotulo": "BP A42 CABANAS MD",
                "Direccion": "CALLE TEST 3",
                "C.P.": "28905",
                "Municipio": "GETAFE",
                "Provincia": "MADRID",
                "Latitud": "40,3083",
                "Longitud (WGS84)": "-3,7320",
                "Precio Gasoleo A": "1,550",
            },
        ])
        replace_catalog(db_path, stations, prices)
        an_results = get_candidates_with_price_in_bbox(
            db_path,
            fuel_type="gasoleo_a",
            min_lat=42.0,
            max_lat=43.0,
            min_lon=-2.0,
            max_lon=-1.0,
            brands=["AN ENERGETICOS"],
        )
        bp_results = get_candidates_with_price_in_bbox(
            db_path,
            fuel_type="gasoleo_a",
            min_lat=41.0,
            max_lat=42.5,
            min_lon=2.5,
            max_lon=3.5,
            brands=["BP"],
        )
        bp_prefix_results = get_candidates_with_price_in_bbox(
            db_path,
            fuel_type="gasoleo_a",
            min_lat=40.0,
            max_lat=40.6,
            min_lon=-4.0,
            max_lon=-3.5,
            brands=["BP"],
        )
        _assert(len(an_results) == 1, f"Expected 1 result for AN ENERGETICOS, got {len(an_results)}")
        _assert(len(bp_results) == 1, f"Expected 1 result for BP quoted prefix, got {len(bp_results)}")
        _assert(len(bp_prefix_results) == 1, f"Expected 1 result for BP prefix, got {len(bp_prefix_results)}")
        an_station, _an_price = an_results[0]
        bp_station, _bp_price = bp_results[0]
        bp_prefix_station, _bp_prefix_price = bp_prefix_results[0]
        _assert(an_station.brand_label_raw == "AN ENERGETICOS - TAFALLA", an_station.brand_label_raw)
        _assert(an_station.brand_canonical == "AN ENERGETICOS", an_station.brand_canonical)
        _assert(an_station.brand_confidence == 1.0, an_station.brand_confidence)
        _assert(bp_station.brand_label_raw == '"BP"BEGUR', bp_station.brand_label_raw)
        _assert(bp_station.brand_canonical == "BP", bp_station.brand_canonical)
        _assert(bp_station.brand_confidence == 1.0, bp_station.brand_confidence)
        _assert(bp_prefix_station.brand_label_raw == "BP A42 CABANAS MD", bp_prefix_station.brand_label_raw)
        _assert(bp_prefix_station.brand_canonical == "BP", bp_prefix_station.brand_canonical)
        _assert(bp_prefix_station.brand_confidence == 1.0, bp_prefix_station.brand_confidence)
    finally:
        _cleanup_sqlite(db_path)


def test_renormalize_dry_run_detects_compound_cepsa_moeve_rows() -> None:
    """Dry-run of renormalize must find compound CEPSA/MOEVE rows but NOT modify the DB."""
    from app.data_sources.brand_catalog import canonicalize_brand_label
    from app.storage.database import connect

    db_path = ROOT / "tests" / ".renorm_dryrun.sqlite"
    _cleanup_sqlite(db_path)
    try:
        # Build a DB with one compound MOEVE station at confidence=0.5 (pre-fix state)
        compound_station = Station(
            station_id="rn1",
            brand="SUTULLENA-CEPSA",
            name="Test Sutullena",
            address="Calle Test",
            postal_code="11001",
            municipality="CADIZ",
            province="CADIZ",
            lat=36.5,
            lon=-6.3,
            source="TEST",
            last_seen_at="2026-01-01",
            brand_label_raw="SUTULLENA-CEPSA",
            brand_canonical="SUTULLENA-CEPSA",
            brand_group="SUTULLENA-CEPSA",
            brand_confidence=0.5,
        )
        replace_catalog(db_path, [compound_station], [])

        # Simulate dry-run: find rows that would change
        conn = connect(db_path)
        try:
            rows = conn.execute(
                "SELECT station_id, brand, brand_label_raw, brand_canonical, brand_confidence FROM stations"
            ).fetchall()
        finally:
            conn.close()

        would_update = []
        for row in rows:
            raw_label = row["brand_label_raw"] or row["brand"] or ""
            canonical, group, confidence = canonicalize_brand_label(raw_label)
            if canonical != row["brand_canonical"] or confidence != row["brand_confidence"]:
                would_update.append(row["station_id"])

        _assert(len(would_update) == 1, f"Expected 1 row to update, got {len(would_update)}: {would_update}")
        _assert("rn1" in would_update, would_update)

        # DB must be unchanged (dry-run)
        conn2 = connect(db_path)
        try:
            still_raw = conn2.execute(
                "SELECT brand_canonical, brand_confidence FROM stations WHERE station_id = 'rn1'"
            ).fetchone()
        finally:
            conn2.close()
        _assert(still_raw["brand_canonical"] == "SUTULLENA-CEPSA", still_raw["brand_canonical"])
        _assert(still_raw["brand_confidence"] == 0.5, still_raw["brand_confidence"])
    finally:
        _cleanup_sqlite(db_path)


def test_renormalize_apply_fixes_compound_cepsa_moeve_brands() -> None:
    """Applying renormalize to a temp DB must upgrade compound CEPSA/MOEVE rows to canonical=CEPSA."""
    import importlib
    import sys as _sys

    db_path = ROOT / "tests" / ".renorm_apply.sqlite"
    _cleanup_sqlite(db_path)
    try:
        stations = [
            Station(
                station_id="ra1",
                brand="GRUPO CACHO - MOEVE",
                name="Grupo Cacho",
                address="Calle Cacho",
                postal_code="28001",
                municipality="MADRID",
                province="MADRID",
                lat=40.4,
                lon=-3.7,
                source="TEST",
                last_seen_at="2026-01-01",
                brand_label_raw="GRUPO CACHO - MOEVE",
                brand_canonical="GRUPO CACHO - MOEVE",
                brand_group="GRUPO CACHO - MOEVE",
                brand_confidence=0.5,
            ),
            Station(
                station_id="ra2",
                brand="REPSOL",
                name="Repsol OK",
                address="Calle Repsol",
                postal_code="28002",
                municipality="MADRID",
                province="MADRID",
                lat=40.41,
                lon=-3.71,
                source="TEST",
                last_seen_at="2026-01-01",
                brand_label_raw="REPSOL",
                brand_canonical="REPSOL",
                brand_group="REPSOL",
                brand_confidence=1.0,
            ),
        ]
        replace_catalog(db_path, stations, [])

        # Run the renormalize script in apply mode via its main() logic
        scripts_path = str(ROOT / "scripts")
        if scripts_path not in _sys.path:
            _sys.path.insert(0, scripts_path)
        renorm = importlib.import_module("renormalize_catalog_brands")
        _saved_argv = _sys.argv[:]
        _sys.argv = ["renormalize_catalog_brands.py", "--db", str(db_path)]
        try:
            returncode = renorm.main()
        finally:
            _sys.argv = _saved_argv

        _assert(returncode == 0, f"renormalize exited with {returncode}")

        # ra1 must now be canonical=CEPSA, confidence=1.0
        from app.storage.database import connect
        conn = connect(db_path)
        try:
            ra1 = conn.execute(
                "SELECT brand_canonical, brand_confidence FROM stations WHERE station_id = 'ra1'"
            ).fetchone()
            ra2 = conn.execute(
                "SELECT brand_canonical, brand_confidence FROM stations WHERE station_id = 'ra2'"
            ).fetchone()
        finally:
            conn.close()

        _assert(ra1["brand_canonical"] == "CEPSA", f"ra1 canonical={ra1['brand_canonical']!r}")
        _assert(ra1["brand_confidence"] == 1.0, f"ra1 confidence={ra1['brand_confidence']}")
        # ra2 (REPSOL) must be unchanged
        _assert(ra2["brand_canonical"] == "REPSOL", f"ra2 canonical={ra2['brand_canonical']!r}")
    finally:
        _cleanup_sqlite(db_path)


def test_public_access_oleocampo_members_only_restricted() -> None:
    """Station 9580 (Oleocampo) must be excluded: official site is 'PARA SOCIOS/AS'."""
    station, _ = _public_access_station("9580", "OLEOCAMPO, S.COOP.AND. DE 2\xba GRADO", 1.00)
    decision = classify_public_access(station)
    _assert(decision.status == PUBLIC_ACCESS_RESTRICTED, f"expected restricted, got {decision.status}")
    _assert(decision.reason == "cooperative_members_only", f"expected cooperative_members_only, got {decision.reason}")
    _assert(not decision.eligible, "Oleocampo must not be eligible")


def test_public_access_andamur_pamplona_likely_restricted() -> None:
    """Station 12013 (Andamur Pamplona) must be excluded: fleet-card-only infrastructure."""
    station, _ = _public_access_station("12013", 'ANDAMUR "PAMPLONA"', 1.00)
    decision = classify_public_access(station)
    _assert(decision.status == PUBLIC_ACCESS_LIKELY_RESTRICTED, f"expected likely_restricted, got {decision.status}")
    _assert(decision.reason == "associated_card_pricing", f"expected associated_card_pricing, got {decision.reason}")
    _assert(not decision.eligible, "Andamur Pamplona must not be eligible")


def test_public_access_bp_cooperativa_taxis_likely_restricted() -> None:
    """Station 7797 (BP Cooperativa Taxis S. Cristóbal) must be excluded: taxi-member fuel."""
    station, _ = _public_access_station("7797", "BP COOPERATIVA TAXIS S. CRISTOBAL", 1.00)
    decision = classify_public_access(station)
    _assert(decision.status == PUBLIC_ACCESS_LIKELY_RESTRICTED, f"expected likely_restricted, got {decision.status}")
    _assert(decision.reason == "cooperative_members_only", f"expected cooperative_members_only, got {decision.reason}")
    _assert(not decision.eligible, "BP Cooperativa Taxis must not be eligible")


def test_public_access_froet_2105_is_public_eligible() -> None:
    """Station 2105 (FROET-GAS Molina de Segura) must be public-eligible after rule removal."""
    station, _ = _public_access_station("2105", "FROET-GAS", 1.00)
    decision = classify_public_access(station)
    _assert(decision.eligible, f"FROET-GAS 2105 must be eligible (card=discount only, not access gate); got {decision}")


def test_public_access_andaluza_15460_is_public_eligible() -> None:
    """Station 15460 (Andaluza de Transportes SCA) must be public-eligible after rule removal."""
    station, _ = _public_access_station("15460", "ANDALUZA DE TRANSPORTES SCA", 1.00)
    decision = classify_public_access(station)
    _assert(decision.eligible, f"Andaluza de Transportes SCA 15460 must be eligible (venta al público en general); got {decision}")


def test_public_access_truck_stops_not_blocked_by_keyword() -> None:
    """TRUCK STOP stations are publicly accessible; must not be blocked by keyword."""
    for sid, label in [
        ("9738", "TRUCK STOP EL EJIDO S.L."),
        ("9740", "TRUCK STOP DALIAS"),
        ("9742", "TRUCK STOP DEL PONIENTE"),
    ]:
        station, _ = _public_access_station(sid, label, 1.00)
        decision = classify_public_access(station)
        _assert(decision.eligible, f"TRUCK STOP {sid} must be public-eligible; got {decision}")


def test_public_access_fuel_truck_not_blocked_by_keyword() -> None:
    """FUEL TRUCK stations are open to all vehicles; must not be blocked."""
    for sid, label in [("12271", "FUEL TRUCK"), ("14946", "FUEL TRUCK")]:
        station, _ = _public_access_station(sid, label, 1.00)
        decision = classify_public_access(station)
        _assert(decision.eligible, f"FUEL TRUCK {sid} must be public-eligible; got {decision}")


def test_public_access_agricultural_cooperative_not_blocked_by_keyword() -> None:
    """Agricultural cooperative stations are public by default (Law 34/1998); no keyword blocking."""
    station, _ = _public_access_station("9364", "AGROTER SAT  N\xba1936", 1.00)
    decision = classify_public_access(station)
    _assert(decision.eligible, f"AGROTER SAT must be public-eligible unless curated; got {decision}")


def test_public_access_valcor_cooperative_not_blocked_by_keyword() -> None:
    """VALCOR consumer cooperative stations must not be excluded."""
    for sid in ("10113", "10116"):
        station, _ = _public_access_station(sid, "VALCOR SOCIEDAD COOPERATIVA ASTURIANA", 1.00)
        decision = classify_public_access(station)
        _assert(decision.eligible, f"VALCOR {sid} must be public-eligible; got {decision}")


def run() -> None:
    test_public_access_classifies_esteba_rivas_likely_restricted()
    test_tipo_venta_r_is_restricted()
    test_tipo_venta_missing_empty_and_p_are_safe()
    test_esteba_rivas_label_fallback_is_scoped()
    test_curated_public_access_rules_are_likely_restricted()
    test_unknown_brand_not_excluded_by_default()
    test_truck_stop_not_excluded_by_keyword_only()
    test_coop_logistics_agro_keywords_not_excluded_by_default()
    test_restricted_station_not_returned_by_candidate_query()
    test_restricted_station_not_counted_in_brands()
    test_restricted_station_not_counted_in_coverage_snapshot()
    test_restricted_station_cannot_appear_in_optimize_results()
    test_public_access_filter_reports_restricted_catalog_rows()
    test_public_access_oleocampo_members_only_restricted()
    test_public_access_andamur_pamplona_likely_restricted()
    test_public_access_bp_cooperativa_taxis_likely_restricted()
    test_public_access_froet_2105_is_public_eligible()
    test_public_access_andaluza_15460_is_public_eligible()
    test_public_access_truck_stops_not_blocked_by_keyword()
    test_public_access_fuel_truck_not_blocked_by_keyword()
    test_public_access_agricultural_cooperative_not_blocked_by_keyword()
    test_public_access_valcor_cooperative_not_blocked_by_keyword()
    test_token_filtering()
    test_catalog_database_and_optimizer()
    test_optimizer_charges_extra_detour_only()
    test_prefilter_uses_route_corridor_for_trips()
    test_economic_expansion_can_include_cheap_outer_candidate()
    test_same_place_threshold_controls_search_shape()
    test_radius_aliases_are_deprecated_and_conflict_checked()
    test_address_without_ors_key_is_client_error()
    test_geocode_without_ors_key_is_client_error()
    test_geocode_endpoint_accepts_size_15_and_autocomplete_param()
    test_geocode_autocomplete_falls_back_to_search()
    test_geocode_precise_query_variants_prefer_fast_relevant_searches()
    test_stopover_route_endpoint_returns_two_legs()
    test_home_ui_uses_map_search_without_coordinate_fields()
    test_health_unavailable_db_is_503()
    test_optimize_warnings_have_structured_shape()
    test_low_fuel_coverage_warning_for_rare_fuel()
    test_brand_filter_warning_when_zero_results()
    test_haversine_warning_when_use_ors_false()
    test_deprecated_parameters_emitted_as_structured_warning()
    test_catalog_degraded_warning_propagates()
    test_independent_brands_excluded_warning()
    test_catalog_snapshot_warning_only_when_not_degraded()
    test_stale_reference_prices_warning()
    test_no_candidates_excludes_extent_limit_warning()
    test_haversine_copy_not_duplicated()
    test_brands_endpoint_includes_virtual_independent()
    test_brands_endpoint_omits_virtual_when_no_independents()
    test_optimize_without_filter_includes_independents()
    test_optimize_with_real_brand_only_excludes_independents()
    test_optimize_with_excluded_brand_keeps_all_except_that_brand()
    test_optimize_excluded_alcampo_removes_best_and_items()
    test_optimize_inclusive_brands_returns_only_selected_brands()
    test_optimize_rejects_inclusive_and_excluded_brands_together()
    test_optimize_with_virtual_only_returns_independents()
    test_optimize_with_real_and_virtual_returns_both()
    test_independent_warning_suppressed_when_virtual_included()
    test_brand_filter_sql_with_only_virtual_returns_independent_clause()
    test_moeve_compound_label_included_in_cepsa_filter()
    test_known_brand_token_label_included_in_brand_filter()
    test_targeted_brand_family_labels_included_in_brand_filter()
    test_renormalize_dry_run_detects_compound_cepsa_moeve_rows()
    test_renormalize_apply_fixes_compound_cepsa_moeve_brands()
    print("OK: web pipeline checks passed")


if __name__ == "__main__":
    run()
