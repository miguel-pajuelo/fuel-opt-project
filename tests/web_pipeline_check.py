from __future__ import annotations

import sys
from pathlib import Path

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings
import app.api.main as api_main
from app.data_sources.ballenoil import parse_station_detail
from app.data_sources.minetur import build_catalog_from_minetur, quality_report
from app.models import Coordinates, OptimizationInput, Price, Station
from app.optimizer.ranking import optimize_candidates, optimize_from_db, prefilter_candidates, prefilter_candidates_with_trace
from app.storage.database import get_candidates_with_price_in_bbox, list_brands, price_status, replace_catalog
from app.storage.database import INDEPENDENT_BRAND_SENTINEL, _brand_filter_sql


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


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
            brands_response = api_main.brands()
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
    _assert("refresh_catalog" in html, "Catalog refresh button missing from header.")
    _assert("/static/styles.css" in html, "Home UI should load extracted CSS.")
    _assert("/static/app.js" in html, "Home UI should load extracted JS.")
    _assert("Precios descargados:" in frontend, "Downloaded price timestamp missing from frontend.")
    _assert("Última actualización de precios:" not in frontend, "Header should not claim an official price update date.")
    _assert("Actualizado correctamente:" not in frontend, "Header should not show local refresh as price freshness.")
    _assert("source_fetched_at" in frontend, "Visible price timestamp should use source_fetched_at.")
    _assert("source_fetch_completed_at" in frontend, "Visible price timestamp should fall back to source_fetch_completed_at.")
    _assert("fetch('/catalog/refresh', { method: 'POST' })" in frontend, "Catalog refresh button should call the refresh endpoint.")
    _assert("loadCatalogStatus" in frontend, "Home UI should load catalog refresh status.")
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
    _assert("station-pin" in frontend, "Station map pin styling missing from home UI.")
    _assert("sidebar_toggle" in html, "Sidebar collapse toggle missing from home UI.")
    _assert(".sidebar-toggle::before" in frontend, "Sidebar toggle should use a directional chevron.")
    _assert("<span></span>" not in html, "Sidebar toggle should not use hamburger bars.")
    _assert("sidebar-collapsed" in frontend, "Desktop sidebar collapsed state missing from UI.")
    _assert("setSidebarCollapsed(true)" in frontend, "Sidebar should collapse automatically after results render.")
    _assert("map.invalidateSize" in frontend, "Map should resize after sidebar transitions.")
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
    _assert('aria-hidden="${String(!keepAlternativesOpen)}"' in frontend, "Alternatives accordion should expose hidden state.")
    _assert("panel.setAttribute('aria-hidden', String(open))" in frontend, "Alternatives accordion should update hidden state.")
    _assert("data-result-index" in frontend, "Alternative result rows should be selectable.")
    _assert("brand-toggle" in frontend, "Brand rows should use right-aligned toggles.")
    _assert("brand-copy" in frontend, "Brand rows should include label and subtitle copy.")
    _assert("select_all_brands" in html, "Brand selector should expose an all-brands button.")
    _assert('class="link-button active" type="button" aria-pressed="true">Todas' in html, "All-brands button should start active.")
    _assert('name="brand_filter" value="${escapeHtml(brand.canonical)}" checked' in frontend, "Brand inputs should start checked.")
    _assert("input.checked = shouldSelectAll" in frontend, "All-brands button should toggle every brand input.")
    _assert("allBrandsSelected" in frontend, "Brand filter state should track whether every brand is selected.")
    _assert("selectedBrands().length > 10" in frontend, "Frontend should block more than 10 selected brands.")
    _assert("Pulsa Todas para incluirlas todas." not in html, "Brand limit should not show explanatory copy.")
    _assert("shouldFilterByBrands" in frontend, "Optimize payload should omit brands when all brands are selected.")
    _assert("overflow: hidden" in frontend, "Desktop page should be constrained to the viewport.")
    _assert("url.searchParams.set('size', '10')" in frontend, "Map search should request the maximum result count.")
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
        response = api_main.brands()
        items = response["brands"]
        virtual = [item for item in items if item.get("canonical") == INDEPENDENT_BRAND_SENTINEL]
        _assert(len(virtual) == 1, items)
        _assert(virtual[0]["is_virtual"] is True, virtual[0])
        _assert(virtual[0]["station_count"] >= 1, virtual[0])
        _assert(items[-1]["canonical"] == INDEPENDENT_BRAND_SENTINEL, items)

    _with_independent_brand_db("brands_virtual_independent", check)


def test_brands_endpoint_omits_virtual_when_no_independents() -> None:
    def check() -> None:
        response = api_main.brands()
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


def run() -> None:
    test_token_filtering()
    test_catalog_database_and_optimizer()
    test_optimizer_charges_extra_detour_only()
    test_prefilter_uses_route_corridor_for_trips()
    test_economic_expansion_can_include_cheap_outer_candidate()
    test_same_place_threshold_controls_search_shape()
    test_radius_aliases_are_deprecated_and_conflict_checked()
    test_address_without_ors_key_is_client_error()
    test_geocode_without_ors_key_is_client_error()
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
    test_optimize_with_virtual_only_returns_independents()
    test_optimize_with_real_and_virtual_returns_both()
    test_independent_warning_suppressed_when_virtual_included()
    test_brand_filter_sql_with_only_virtual_returns_independent_clause()
    print("OK: web pipeline checks passed")


if __name__ == "__main__":
    run()
