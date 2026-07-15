from __future__ import annotations

import logging
import time
from typing import Any, NoReturn

import requests

from app.config import Settings, load_settings, require_ors_api_key
from app.models import Coordinates, Station


ORS_MATRIX_URL = "https://api.openrouteservice.org/v2/matrix/driving-car"
ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
ORS_GEOCODE_URL = "https://api.openrouteservice.org/geocode/search"
ORS_GEOCODE_AUTOCOMPLETE_URL = "https://api.openrouteservice.org/geocode/autocomplete"
ORS_REVERSE_GEOCODE_URL = "https://api.openrouteservice.org/geocode/reverse"

PUBLIC_GEOCODING_ERROR = "No se pudo consultar la ubicación en este momento."
PUBLIC_ROUTE_ERROR = "No se pudo calcular la ruta en este momento."
PUBLIC_ROUTING_SERVICE_ERROR = "El servicio de rutas no está disponible temporalmente."

logger = logging.getLogger("fuelopt.ors")


class ORSServiceError(RuntimeError):
    """Publicly safe ORS failure without provider request details or credentials."""

    def __init__(
        self,
        public_message: str,
        *,
        operation: str,
        failure_type: str,
        remote_status: int | None = None,
        configuration_error: bool = False,
    ) -> None:
        super().__init__(public_message)
        self.public_message = public_message
        self.operation = operation
        self.failure_type = failure_type
        self.remote_status = remote_status
        self.configuration_error = configuration_error


def _safe_remote_status(exc: BaseException) -> int | None:
    try:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return int(status) if status is not None else None
    except Exception:
        return None


def _raise_ors_failure(
    operation: str,
    exc: BaseException,
    public_message: str,
    *,
    failure_type: str | None = None,
    configuration_error: bool = False,
) -> NoReturn:
    safe_failure_type = failure_type or exc.__class__.__name__
    remote_status = _safe_remote_status(exc)
    logger.warning(
        "ors_operation_failed operation=%s failure_type=%s remote_status=%s",
        operation,
        safe_failure_type,
        remote_status if remote_status is not None else "none",
    )
    raise ORSServiceError(
        public_message,
        operation=operation,
        failure_type=safe_failure_type,
        remote_status=remote_status,
        configuration_error=configuration_error,
    ) from None


def _require_ors_key(settings: Settings, operation: str, public_message: str) -> str:
    try:
        return require_ors_api_key(settings)
    except RuntimeError as exc:
        _raise_ors_failure(
            operation,
            exc,
            public_message,
            failure_type="configuration",
            configuration_error=True,
        )


GEOCODE_LAYER_LABELS = {
    "venue": "Lugar",
    "address": "Dirección",
    "street": "Calle",
    "locality": "Ciudad",
    "localadmin": "Municipio",
    "county": "Provincia",
    "region": "Región",
    "country": "País",
}

def _distinct_nonempty(parts: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        text = str(part or "").strip()
        key = text.casefold()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _parse_geocode_candidates(payload: dict[str, Any], address: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for rank, feature in enumerate(payload.get("features") or []):
        coords = feature.get("geometry", {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        props = feature.get("properties") or {}
        label = props.get("label") or props.get("name") or address
        label_text = str(label)
        label_key = label_text.casefold()
        if label_key in seen_labels:
            continue
        seen_labels.add(label_key)
        layer = str(props.get("layer") or "")
        title = str(props.get("name") or props.get("street") or label_text)
        subtitle = ", ".join(
            _distinct_nonempty(
                [
                    props.get("street"),
                    props.get("locality") or props.get("localadmin"),
                    props.get("county"),
                    props.get("region"),
                    props.get("country"),
                ]
            )
        )
        candidates.append(
            {
                "label": label_text,
                "name": str(props.get("name") or label_text),
                "title": title,
                "subtitle": subtitle,
                "layer": layer,
                "layer_label": GEOCODE_LAYER_LABELS.get(layer, layer.title() or "Lugar"),
                "lat": float(coords[1]),
                "lon": float(coords[0]),
                "confidence": props.get("confidence"),
                "source": props.get("source"),
                "rank": rank,
            }
        )
    return candidates


def _request_geocode_candidates(
    address: str,
    url: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    try:
        response = requests.get(
            url,
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        return _parse_geocode_candidates(response.json(), address)
    except (
        requests.RequestException,
        OSError,
        AttributeError,
        IndexError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        _raise_ors_failure("geocode", exc, PUBLIC_GEOCODING_ERROR)


def geocode_candidates(
    address: str,
    settings: Settings | None = None,
    country: str = "ESP",
    size: int = 5,
    focus_lat: float | None = None,
    focus_lon: float | None = None,
) -> list[dict[str, Any]]:
    cfg = settings or load_settings()
    api_key = _require_ors_key(cfg, "geocode", PUBLIC_GEOCODING_ERROR)
    params: dict[str, Any] = {
        "api_key": api_key,
        "text": address,
        "boundary.country": country,
        "size": size,
        "lang": "es",
        "layers": "venue,address,street,locality,localadmin,county,region,country",
    }
    if focus_lat is not None and focus_lon is not None:
        params["focus.point.lat"] = focus_lat
        params["focus.point.lon"] = focus_lon
    return _request_geocode_candidates(address, ORS_GEOCODE_URL, params)


def geocode_candidates_autocomplete(
    address: str,
    settings: Settings | None = None,
    country: str = "ESP",
    size: int = 5,
    focus_lat: float | None = None,
    focus_lon: float | None = None,
) -> list[dict[str, Any]]:
    cfg = settings or load_settings()
    api_key = _require_ors_key(cfg, "geocode_autocomplete", PUBLIC_GEOCODING_ERROR)
    params: dict[str, Any] = {
        "api_key": api_key,
        "text": address,
        "boundary.country": country,
        "size": min(size, 10),
        "lang": "es",
        "layers": "venue,address,street,locality,localadmin,county,region,country",
    }
    if focus_lat is not None and focus_lon is not None:
        params["focus.point.lat"] = focus_lat
        params["focus.point.lon"] = focus_lon
    return _request_geocode_candidates(address, ORS_GEOCODE_AUTOCOMPLETE_URL, params)


def geocode_address(address: str, settings: Settings | None = None, country: str = "ESP") -> Coordinates:
    candidates = geocode_candidates(address, settings=settings, country=country, size=1)
    if not candidates:
        raise ValueError(f"No geocoding result for address: {address}")
    return Coordinates(lat=float(candidates[0]["lat"]), lon=float(candidates[0]["lon"]))


def reverse_geocode_coordinates(
    lat: float,
    lon: float,
    settings: Settings | None = None,
    size: int = 1,
) -> dict[str, Any] | None:
    cfg = settings or load_settings()
    api_key = _require_ors_key(cfg, "reverse_geocode", PUBLIC_GEOCODING_ERROR)
    params: dict[str, Any] = {
        "api_key": api_key,
        "point.lat": lat,
        "point.lon": lon,
        "size": size,
        "layers": "venue,address,street,locality,localadmin,county,region,country",
    }
    try:
        response = requests.get(
            ORS_REVERSE_GEOCODE_URL,
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        features = payload.get("features") or []
        if not features:
            return None
        feature = features[0]
        coords = feature.get("geometry", {}).get("coordinates") or []
        if len(coords) < 2:
            return None
        props = feature.get("properties") or {}
        label = props.get("label") or props.get("name")
        layer = str(props.get("layer") or "")
        title = str(props.get("name") or props.get("street") or label or "")
        subtitle = ", ".join(
            _distinct_nonempty(
                [
                    props.get("street"),
                    props.get("locality") or props.get("localadmin"),
                    props.get("county"),
                    props.get("region"),
                    props.get("country"),
                ]
            )
        )
        return {
            "label": str(label or title or f"{lat:.5f}, {lon:.5f}"),
            "name": str(props.get("name") or title or label or ""),
            "title": title or str(label or ""),
            "subtitle": subtitle,
            "layer": layer,
            "layer_label": GEOCODE_LAYER_LABELS.get(layer, layer.title() or "Lugar"),
            "lat": float(coords[1]),
            "lon": float(coords[0]),
            "source": props.get("source"),
        }
    except (
        requests.RequestException,
        OSError,
        AttributeError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
    ) as exc:
        _raise_ors_failure("reverse_geocode", exc, PUBLIC_GEOCODING_ERROR)


class ORSRouteProvider:
    route_source = "openrouteservice_matrix"

    def __init__(self, settings: Settings | None = None, timeout_sec: int = 30, retries: int = 2) -> None:
        self.settings = settings or load_settings()
        self.api_key = _require_ors_key(
            self.settings,
            "route_configuration",
            PUBLIC_ROUTING_SERVICE_ERROR,
        )
        self.timeout_sec = timeout_sec
        self.retries = retries

    def _matrix(
        self,
        sources: list[Coordinates],
        destinations: list[Coordinates],
    ) -> list[list[float | None]]:
        locations = [[coord.lon, coord.lat] for coord in sources + destinations]
        source_indices = list(range(len(sources)))
        destination_indices = list(range(len(sources), len(sources) + len(destinations)))
        payload: dict[str, Any] = {
            "locations": locations,
            "sources": source_indices,
            "destinations": destination_indices,
            "metrics": ["distance"],
            "units": "km",
        }
        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                response = requests.post(
                    ORS_MATRIX_URL,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_sec,
                )
                response.raise_for_status()
                matrix = response.json().get("distances")
                if not isinstance(matrix, list):
                    raise ValueError("ORS matrix response did not include distances.")
                return matrix
            except (
                requests.RequestException,
                OSError,
                AttributeError,
                IndexError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                last_error = exc
                if attempt == self.retries:
                    break
                time.sleep(2 * attempt)
        _raise_ors_failure(
            "matrix",
            last_error or RuntimeError("matrix request was not attempted"),
            PUBLIC_ROUTING_SERVICE_ERROR,
        )

    def distances_for_candidates(
        self,
        origin: Coordinates,
        destination: Coordinates,
        stations: list[Station],
    ) -> dict[str, tuple[float, float]]:
        station_coords = [Coordinates(station.lat, station.lon) for station in stations]
        if not station_coords:
            return {}
        outbound = self._matrix([origin], station_coords)[0]
        inbound = self._matrix(station_coords, [destination])
        result: dict[str, tuple[float, float]] = {}
        for idx, station in enumerate(stations):
            to_station = outbound[idx] if idx < len(outbound) else None
            from_station = inbound[idx][0] if idx < len(inbound) and inbound[idx] else None
            if to_station is None or from_station is None:
                continue
            result[station.station_id] = (float(to_station), float(from_station))
        return result

    def direct_distance_km(self, origin: Coordinates, destination: Coordinates) -> float:
        matrix = self._matrix([origin], [destination])
        if not matrix or not matrix[0] or matrix[0][0] is None:
            raise RuntimeError("ORS matrix did not return a direct origin-destination distance.")
        return float(matrix[0][0])

    def route_geometry(self, origin: Coordinates, destination: Coordinates) -> list[Coordinates]:
        payload = {
            "coordinates": [
                [origin.lon, origin.lat],
                [destination.lon, destination.lat],
            ]
        }
        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/geo+json, application/json",
        }
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                response = requests.post(
                    ORS_DIRECTIONS_URL,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_sec,
                )
                response.raise_for_status()
                features = response.json().get("features") or []
                if not features:
                    raise ValueError("ORS directions response did not include route features.")
                coordinates = features[0].get("geometry", {}).get("coordinates") or []
                route = [Coordinates(lat=float(lat), lon=float(lon)) for lon, lat in coordinates]
                if len(route) < 2:
                    raise ValueError("ORS directions response did not include a usable geometry.")
                return route
            except (
                requests.RequestException,
                OSError,
                AttributeError,
                IndexError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                last_error = exc
                if attempt == self.retries:
                    break
                time.sleep(2 * attempt)
        _raise_ors_failure(
            "directions",
            last_error or RuntimeError("directions request was not attempted"),
            PUBLIC_ROUTE_ERROR,
        )
