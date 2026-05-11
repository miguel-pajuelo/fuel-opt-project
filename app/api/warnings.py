from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models import Warning


STALE_PRICES_DAYS = 7
LOW_FUEL_COVERAGE_THRESHOLD = 1000
RESTRICTIVE_BRAND_THRESHOLD = 3
MAX_WARNINGS = 6

_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _limited_reasons(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)][:3]
    if isinstance(value, str) and value.strip():
        return [value][:3]
    return []


def _append_once(warnings: list[Warning], seen: set[str], warning: Warning) -> None:
    if warning.code in seen:
        return
    seen.add(warning.code)
    warnings.append(warning)


def build_optimize_warnings(
    *,
    fuel_type,
    selected_brands,
    catalog_status,
    fuel_coverage_count,
    independent_count,
    search_context,
    route_source,
    result_count,
    max_search_extent_km,
    deprecated_parameters,
    independent_included: bool = False,
) -> list[Warning]:
    warnings: list[Warning] = []
    seen: set[str] = set()
    catalog = catalog_status or {}
    search = search_context or {}
    brands = list(selected_brands or [])
    route_source_text = str(route_source or "")

    if "haversine" in route_source_text.lower():
        _append_once(
            warnings,
            seen,
            Warning(
                code="using_haversine_estimate",
                severity="info",
                title="Ruta estimada por distancia",
                message="El coste de ruta se ha calculado con una aproximación de distancia, no con ruta real ORS.",
                data={"route_source": route_source_text},
            ),
        )

    refresh_status = str(catalog.get("refresh_status") or "")
    if _truthy(catalog.get("degraded")) or (refresh_status and refresh_status != "ok"):
        _append_once(
            warnings,
            seen,
            Warning(
                code="catalog_degraded",
                severity="warning",
                title="Catálogo degradado",
                message="El catálogo activo indica datos degradados o refresco incompleto.",
                data={
                    "refresh_status": refresh_status,
                    "source": catalog.get("source"),
                    "degraded_reasons": _limited_reasons(catalog.get("degraded_reasons")),
                },
            ),
        )

    source = str(catalog.get("source") or "")
    if "catalog_degraded" not in seen and ("SNAPSHOT" in source.upper() or "CACHE" in source.upper()):
        _append_once(
            warnings,
            seen,
            Warning(
                code="catalog_snapshot_source",
                severity="info",
                title="Datos de snapshot o caché",
                message="La optimización usa una fuente local de snapshot o caché.",
                data={
                    "source": source,
                    "source_reference_date": catalog.get("source_reference_date"),
                },
            ),
        )

    reference_date = catalog.get("source_reference_date")
    parsed_reference = _parse_datetime(reference_date)
    if parsed_reference is not None:
        age_days = (datetime.now(timezone.utc) - parsed_reference).total_seconds() / 86400
        if age_days > STALE_PRICES_DAYS:
            _append_once(
                warnings,
                seen,
                Warning(
                    code="stale_reference_prices",
                    severity="warning",
                    title="Precios potencialmente antiguos",
                    message="La fecha de referencia de precios supera el umbral recomendado.",
                    data={
                        "source_reference_date": reference_date,
                        "age_days": int(age_days),
                        "threshold_days": STALE_PRICES_DAYS,
                    },
                ),
            )

    coverage_count = int(fuel_coverage_count or 0)
    if 0 < coverage_count < LOW_FUEL_COVERAGE_THRESHOLD:
        _append_once(
            warnings,
            seen,
            Warning(
                code="low_fuel_coverage",
                severity="warning",
                title="Baja cobertura del combustible",
                message="Hay pocas estaciones con precio disponible para el combustible seleccionado.",
                data={
                    "fuel_type": fuel_type,
                    "coverage_count": coverage_count,
                    "threshold": LOW_FUEL_COVERAGE_THRESHOLD,
                },
            ),
        )

    candidate_universe_size = int(search.get("candidate_universe_size") or 0)
    effective_extent = _as_float(search.get("effective_search_extent_km"))
    max_extent = _as_float(max_search_extent_km)
    if result_count == 0 and candidate_universe_size == 0:
        _append_once(
            warnings,
            seen,
            Warning(
                code="no_candidates_in_radius",
                severity="warning",
                title="Sin candidatos en el área explorada",
                message="No se han encontrado estaciones con precio válido para esta búsqueda.",
                data={
                    "fuel_type": fuel_type,
                    "effective_search_extent_km": effective_extent,
                    "max_search_extent_km": max_extent,
                },
            ),
        )

    if (
        "no_candidates_in_radius" not in seen
        and _truthy(search.get("economic_expansion_used"))
        and effective_extent is not None
        and max_extent is not None
    ):
        if abs(effective_extent - max_extent) <= max(0.001, max_extent * 0.001):
            _append_once(
                warnings,
                seen,
                Warning(
                    code="search_extent_limit_reached",
                    severity="warning" if result_count == 0 else "info",
                    title="Límite de búsqueda alcanzado",
                    message="La búsqueda económica llegó al límite máximo configurado.",
                    data={
                        "effective_search_extent_km": effective_extent,
                        "max_search_extent_km": max_extent,
                    },
                ),
            )

    if brands and result_count == 0:
        _append_once(
            warnings,
            seen,
            Warning(
                code="brand_filter_too_restrictive",
                severity="warning",
                title="Filtro de marca restrictivo",
                message="Los filtros de marca seleccionados no han devuelto resultados para esta búsqueda.",
                data={
                    "selected_brands_count": len(brands),
                    "selected_brands": brands[:10],
                },
            ),
        )
    elif brands and len(brands) < RESTRICTIVE_BRAND_THRESHOLD:
        _append_once(
            warnings,
            seen,
            Warning(
                code="brand_filter_too_restrictive",
                severity="info",
                title="Filtro de marca activo",
                message="La búsqueda está limitada a pocas marcas seleccionadas.",
                data={
                    "selected_brands_count": len(brands),
                    "selected_brands": brands[:10],
                },
            ),
        )

    independent_total = int(independent_count or 0)
    if brands and independent_total > 0 and not independent_included:
        _append_once(
            warnings,
            seen,
            Warning(
                code="independent_brands_excluded_or_hidden",
                severity="info",
                title="Marcas independientes fuera del filtro",
                message="Existen estaciones sin marca canónica fiable que pueden quedar fuera del filtro seleccionado.",
                data={
                    "selected_brands_count": len(brands),
                    "hidden_independent_count": independent_total,
                },
            ),
        )

    deprecated = list(deprecated_parameters or [])
    if deprecated:
        _append_once(
            warnings,
            seen,
            Warning(
                code="deprecated_parameters",
                severity="info",
                title="Parámetros obsoletos",
                message="La petición usa alias antiguos. Usa local_search_radius_km y corridor_radius_km.",
                data={"parameters": deprecated},
            ),
        )

    warnings.sort(key=lambda item: (_SEVERITY_ORDER.get(item.severity, 99), item.code))
    return warnings[:MAX_WARNINGS]
