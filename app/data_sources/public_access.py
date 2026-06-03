from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Iterable


PUBLIC_ACCESS_PUBLIC = "public"
PUBLIC_ACCESS_LIKELY_RESTRICTED = "likely_restricted"
PUBLIC_ACCESS_RESTRICTED = "restricted"
PUBLIC_ACCESS_UNKNOWN = "unknown"

RESTRICTED_PUBLIC_ACCESS_STATUSES = {
    PUBLIC_ACCESS_LIKELY_RESTRICTED,
    PUBLIC_ACCESS_RESTRICTED,
}


@dataclass(frozen=True)
class PublicAccessDecision:
    status: str
    reason: str
    confidence: float
    evidence: str = ""
    station_id: str | None = None
    brand_label_raw: str | None = None

    @property
    def eligible(self) -> bool:
        return self.status not in RESTRICTED_PUBLIC_ACCESS_STATUSES


CURATED_PUBLIC_ACCESS_RULES: dict[str, PublicAccessDecision] = {
    # --- Keep: strong evidence of controlled/non-public access ---
    "13073": PublicAccessDecision(
        status=PUBLIC_ACCESS_LIKELY_RESTRICTED,
        reason="reported_controlled_heavy_vehicle_access",
        confidence=0.9,
        evidence="Manual report and audit evidence indicate controlled/heavy-vehicle-oriented access.",
    ),
    # --- New: members-only cooperative pump (official page title: "PARA SOCIOS/AS") ---
    "9580": PublicAccessDecision(
        status=PUBLIC_ACCESS_RESTRICTED,
        reason="cooperative_members_only",
        confidence=0.95,
        evidence=(
            "Official Oleocampo page oleocampo.com/estacion-servicios-sociosas/ is titled "
            "'ESTACIÓN DE SERVICIOS PARA SOCIOS/AS'. Card reader required for access. "
            "No public or non-member sale evidence anywhere on the official page."
        ),
    ),
    # --- New: fleet-card-only lorry park (Andamur ProEurope/ProBon cards, plate-reader gate) ---
    "12013": PublicAccessDecision(
        status=PUBLIC_ACCESS_LIKELY_RESTRICTED,
        reason="associated_card_pricing",
        confidence=0.72,
        evidence=(
            "Andamur's entire business model is fleet fuel cards (ProEurope, ProBon). "
            "No evidence of walk-up cash or Visa/Mastercard payment at owned stations. "
            "Plate-reader-controlled lorry park with 24h security; fleet-services infrastructure. "
            "Registered tipo_venta=P in MINETUR but no public walk-up access documented."
        ),
    ),
    # --- New: taxi cooperative fuel pump (member-only fueling described on official site) ---
    "7797": PublicAccessDecision(
        status=PUBLIC_ACCESS_LIKELY_RESTRICTED,
        reason="cooperative_members_only",
        confidence=0.70,
        evidence=(
            "Taxi cooperative official site coopsancristobalgc.com describes fuel service as "
            "'suministro de combustible con condiciones ventajosas para los socios'. "
            "Primary function is taxi fleet fueling. Confidence 0.70 (not hard-restricted) "
            "because BP-branded station locator lists it publicly."
        ),
    ),
    # --- Removed (2026-05 audit): 2105 FROET-GAS Molina de Segura ---
    # FROET card is a discount/loyalty card, not an access gate. Station accepts any credit card
    # 24h. tipo_venta=P confirmed. No evidence of restricted walk-up access. Rule was wrong.
    #
    # --- Removed (2026-05 audit): 15460 ANDALUZA DE TRANSPORTES SCA Albolote ---
    # SCA (Sociedad Cooperativa Andaluza) is a worker cooperative running a petrol station open
    # to the general public. tipo_venta=P confirmed. No evidence of member-only access. Rule was wrong.
}

CURATED_PUBLIC_ACCESS_STATION_IDS = frozenset(CURATED_PUBLIC_ACCESS_RULES)


def classify_public_access(station_or_row: Any) -> PublicAccessDecision:
    station_id = _as_text(_get_value(station_or_row, "station_id"))
    raw = _get_raw(station_or_row)
    ideess = _as_text(_raw_get(raw, "IDEESS", "IdEstacionServicio", "ID Estacion Servicio"))
    label = _as_text(
        _get_value(station_or_row, "brand_label_raw")
        or _get_value(station_or_row, "brand_canonical")
        or _raw_get(raw, "Rotulo", "ROTULO")
    )
    municipality = _as_text(_get_value(station_or_row, "municipality") or _raw_get(raw, "Municipio"))
    address = _as_text(_get_value(station_or_row, "address") or _raw_get(raw, "Direccion"))
    tipo_venta = (_as_text(_raw_get(raw, "Tipo Venta", "TipoVenta")) or "").upper()

    if tipo_venta and tipo_venta != "P":
        return PublicAccessDecision(
            status=PUBLIC_ACCESS_RESTRICTED,
            reason="minetur_tipo_venta_not_public",
            confidence=1.0,
            evidence=f"MINETUR Tipo Venta={tipo_venta!r}.",
            station_id=station_id,
            brand_label_raw=label,
        )

    for candidate_id in (station_id, ideess):
        if candidate_id in CURATED_PUBLIC_ACCESS_RULES:
            return _with_identity(CURATED_PUBLIC_ACCESS_RULES[candidate_id], station_id, label)

    if (
        label
        and _normalize_label(label) == "ESTEBA RIVAS"
        and (_normalize_label(municipality or "") == "GETAFE" or "ERATOSTENES" in _normalize_label(address or ""))
    ):
        return _with_identity(CURATED_PUBLIC_ACCESS_RULES["13073"], station_id, label)

    if tipo_venta == "P":
        return PublicAccessDecision(
            status=PUBLIC_ACCESS_PUBLIC,
            reason="minetur_tipo_venta_public",
            confidence=0.8,
            evidence="MINETUR marks Tipo Venta as P.",
            station_id=station_id,
            brand_label_raw=label,
        )

    return PublicAccessDecision(
        status=PUBLIC_ACCESS_UNKNOWN,
        reason="no_restriction_evidence",
        confidence=0.0,
        station_id=station_id,
        brand_label_raw=label,
    )


def is_publicly_eligible(station_or_row: Any) -> bool:
    return classify_public_access(station_or_row).eligible


def filter_publicly_eligible_catalog(
    stations: Iterable[Any],
    prices: Iterable[Any],
) -> tuple[list[Any], list[Any], dict[str, Any]]:
    eligible_stations: list[Any] = []
    eligible_ids: set[str] = set()
    excluded: list[PublicAccessDecision] = []

    for station in stations:
        decision = classify_public_access(station)
        station_id = _as_text(_get_value(station, "station_id"))
        if decision.eligible:
            eligible_stations.append(station)
            if station_id:
                eligible_ids.add(station_id)
        else:
            excluded.append(decision)

    eligible_prices = [
        price
        for price in prices
        if _as_text(_get_value(price, "station_id")) in eligible_ids
    ]
    return eligible_stations, eligible_prices, public_access_exclusion_report(excluded)


def public_access_exclusion_report(
    excluded: Iterable[PublicAccessDecision],
    *,
    example_limit: int = 10,
) -> dict[str, Any]:
    decisions = list(excluded)
    return {
        "excluded_count": len(decisions),
        "examples": [
            {
                "station_id": decision.station_id,
                "label": decision.brand_label_raw,
                "status": decision.status,
                "reason": decision.reason,
            }
            for decision in decisions[:example_limit]
        ],
    }


def _with_identity(
    decision: PublicAccessDecision,
    station_id: str | None,
    label: str | None,
) -> PublicAccessDecision:
    return PublicAccessDecision(
        status=decision.status,
        reason=decision.reason,
        confidence=decision.confidence,
        evidence=decision.evidence,
        station_id=station_id,
        brand_label_raw=label,
    )


def _get_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    try:
        return value[key]
    except Exception:
        return getattr(value, key, None)


def _get_raw(value: Any) -> dict[str, Any]:
    raw = _get_value(value, "raw")
    if isinstance(raw, dict):
        return raw
    raw_json = _get_value(value, "raw_json")
    if isinstance(raw_json, dict):
        return raw_json
    if isinstance(raw_json, str) and raw_json.strip():
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _raw_get(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw:
            return raw[key]
    lowered = {str(key).lower(): value for key, value in raw.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value is not None:
            return value
    return None


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_label(value: str) -> str:
    return " ".join(value.upper().split())
