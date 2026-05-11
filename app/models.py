from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


FUEL_FIELDS: dict[str, tuple[str, str]] = {
    "gasoleo_a": ("Precio Gasoleo A", "Gasoleo A"),
    "gasoleo_b": ("Precio Gasoleo B", "Gasoleo B"),
    "gasoleo_prem": ("Precio Gasoleo Premium", "Gasoleo Premium"),
    "gasolina_95": ("Precio Gasolina 95 E5", "Gasolina 95 E5"),
    "gasolina_98": ("Precio Gasolina 98 E5", "Gasolina 98 E5"),
    "gasolina_98e10": ("Precio Gasolina 98 E10", "Gasolina 98 E10"),
}


@dataclass(frozen=True)
class Station:
    station_id: str
    brand: str
    name: str
    address: str
    postal_code: str
    municipality: str
    province: str
    lat: float
    lon: float
    source: str
    active: bool = True
    last_seen_at: str | None = None
    raw: dict[str, Any] | None = None
    brand_label_raw: str = ""
    brand_canonical: str = ""
    brand_group: str = ""
    brand_confidence: float | None = None

    def __post_init__(self) -> None:
        if not self.brand_label_raw:
            object.__setattr__(self, "brand_label_raw", self.brand)
        if not self.brand_canonical:
            object.__setattr__(self, "brand_canonical", self.brand)
        if not self.brand_group:
            object.__setattr__(self, "brand_group", self.brand_canonical or self.brand)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def public_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("raw", None)
        return payload


@dataclass(frozen=True)
class Price:
    station_id: str
    fuel_type: str
    price_eur_l: float
    updated_at: str | None
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Warning:
    code: str
    severity: str
    title: str
    message: str
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.data is None:
            payload.pop("data", None)
        return payload


@dataclass(frozen=True)
class Coordinates:
    lat: float
    lon: float


@dataclass(frozen=True)
class OptimizationInput:
    origin: Coordinates
    destination: Coordinates
    fuel_type: str = "gasoleo_a"
    input_mode: str = "liters"
    liters: float = 30.0
    budget_amount_eur: float | None = None
    consumption_l_100km: float = 5.5
    radius_km: float = 40.0
    preferred_search_radius_km: float = 50.0
    preferred_corridor_km: float = 10.0
    max_search_extent_km: float = 150.0
    economic_expansion_enabled: bool = True
    optimization_mode: str = "economic"
    max_candidates: int = 75
    route_detour_factor: float = 1.25
    local_search_radius_km: float = 50.0
    corridor_radius_km: float = 10.0
    same_place_threshold_km: float = 1.0


@dataclass(frozen=True)
class CandidateResult:
    station: Station
    fuel_type: str
    price_eur_l: float
    distance_to_station_km: float
    distance_from_station_km: float
    direct_route_km: float
    route_via_station_km: float
    extra_detour_km: float
    total_detour_km: float
    liters_spent_on_route: float
    travel_cost_eur: float
    refuel_cost_eur: float
    total_cost_eur: float
    fuel_purchase_cost_eur: float
    extra_travel_cost_eur: float
    effective_total_cost_eur: float
    reference_cost_eur: float | None
    net_savings_vs_reference_eur: float | None
    budget_amount_eur: float | None
    gross_refuel_liters: float
    net_liters_vs_reference: float | None
    input_mode: str
    optimization_score_eur: float
    detour_penalty_eur: float
    optimization_mode: str
    why_selected: str
    net_liters: float
    net_km: float
    route_source: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["station"] = self.station.public_dict()
        return payload
