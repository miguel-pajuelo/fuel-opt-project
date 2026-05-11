from __future__ import annotations

import logging

from app.data_sources.adapters import BrandAdapter
from app.models import Price, Station


logger = logging.getLogger(__name__)


class BallenoilAdapter(BrandAdapter):
    """
    Wrapper around the legacy Ballenoil scraper.

    It uses the existing incremental caches and makes requests to ballenoil.es,
    so the registry treats it as a network adapter.
    """

    brand_name = "BALLENOIL"

    def needs_network(self) -> bool:
        return True

    def fetch(self, minetur_items: list[dict]) -> tuple[list[Station], list[Price]]:
        try:
            from app.data_sources.minetur import to_float_es
            from app.legacy_cli.scraper import scrape_ballenoil_diesel
            from app.models import FUEL_FIELDS
        except ImportError as exc:
            logger.error("BallenoilAdapter: legacy scraper not available: %s", exc)
            return [], []

        try:
            raw_records: list[dict] = scrape_ballenoil_diesel()
        except Exception:
            logger.exception("BallenoilAdapter: scrape_ballenoil_diesel failed")
            return [], []

        stations: list[Station] = []
        prices: list[Price] = []

        for record in raw_records:
            url = str(record.get("url") or "").strip()
            lat = to_float_es(record.get("latitud"))
            lon = to_float_es(record.get("longitud"))
            if not url or lat is None or lon is None:
                continue

            station_id = f"ballenoil:{url}"
            stations.append(
                Station(
                    station_id=station_id,
                    brand="BALLENOIL",
                    name=str(record.get("nombre") or "BALLENOIL").strip(),
                    address=str(record.get("ubicacion") or "").strip(),
                    postal_code="",
                    municipality="",
                    province="",
                    lat=lat,
                    lon=lon,
                    source="BALLENOIL_SCRAPER",
                    last_seen_at=None,
                    raw=record,
                    brand_label_raw="BALLENOIL",
                    brand_canonical="BALLENOIL",
                    brand_group="BALLENOIL",
                    brand_confidence=1.0,
                )
            )

            for fuel_type in FUEL_FIELDS:
                price_val = to_float_es(record.get(fuel_type))
                if price_val is None:
                    continue
                prices.append(
                    Price(
                        station_id=station_id,
                        fuel_type=fuel_type,
                        price_eur_l=price_val,
                        updated_at=None,
                        source="BALLENOIL_SCRAPER",
                    )
                )

        logger.info("BallenoilAdapter: %d stations, %d prices", len(stations), len(prices))
        return stations, prices
