from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.storage.database import catalog_status, database_health, price_status


@dataclass(frozen=True)
class CatalogValidationRules:
    min_stations: int = 8000
    min_prices: int = 20000
    max_unknown_brand_ratio: float = 0.50
    require_fuels: tuple[str, ...] = ("gasoleo_a", "gasolina_95")


@dataclass
class CatalogValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: dict[str, object] = field(default_factory=dict)


def validate_catalog_db(db_path: Path, rules: CatalogValidationRules | None = None) -> CatalogValidationResult:
    active_rules = rules or CatalogValidationRules()
    errors: list[str] = []
    warnings: list[str] = []

    try:
        database_health(db_path)
        status = catalog_status(db_path)
        prices = price_status(db_path)
    except Exception as exc:
        return CatalogValidationResult(ok=False, errors=[f"database_unreadable: {exc}"])

    station_count = int(status.get("station_count") or 0)
    catalog = status.get("catalog") if isinstance(status.get("catalog"), dict) else {}
    fuels = prices.get("fuels") if isinstance(prices.get("fuels"), dict) else {}
    price_count = int(
        status.get("price_count")
        or catalog.get("price_count")
        or sum(int((fuel_data or {}).get("count") or 0) for fuel_data in fuels.values())
        or 0
    )
    unknown_count = int(status.get("station_count_unknown_brand") or 0)
    unknown_ratio = unknown_count / station_count if station_count else 1.0

    if station_count < active_rules.min_stations:
        errors.append(f"station_count {station_count} < {active_rules.min_stations}")
    if price_count < active_rules.min_prices:
        errors.append(f"price_count {price_count} < {active_rules.min_prices}")
    if unknown_ratio > active_rules.max_unknown_brand_ratio:
        warnings.append(
            f"unknown_brand_ratio {unknown_ratio:.3f} > {active_rules.max_unknown_brand_ratio:.3f}"
        )

    for fuel in active_rules.require_fuels:
        fuel_count = int((fuels.get(fuel) or {}).get("count") or 0) if isinstance(fuels, dict) else 0
        if fuel_count <= 0:
            errors.append(f"missing fuel prices for {fuel}")

    return CatalogValidationResult(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        status={**status, "prices": prices},
    )
