from __future__ import annotations

import logging
import time
import unicodedata
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from app.data_sources.minetur import extract_ideess, get_any, to_float_es
from app.models import FUEL_FIELDS, Price, Station


logger = logging.getLogger(__name__)


def normalize_brand_label(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.upper().strip())
    return "".join(char for char in text if not unicodedata.combining(char))


class BrandAdapter(ABC):
    brand_name: str
    aliases: tuple[str, ...] = ()

    @abstractmethod
    def fetch(self, minetur_items: list[dict]) -> tuple[list[Station], list[Price]]:
        """
        Return (stations, prices) for this brand.

        Simple adapters filter the full MINETUR payload in memory; scraping
        adapters may ignore it. Implementations should return ([], []) when
        they cannot produce a catalog slice.
        """

    def needs_network(self) -> bool:
        return False


class MineturFilterAdapter(BrandAdapter):
    """
    Adapter for brands identified by one or more exact MINETUR Rotulo values.
    It performs no extra HTTP requests and scans minetur_items in memory.
    """

    def __init__(self, brand_name: str, rotulos: list[str]) -> None:
        self.brand_name = brand_name
        self._rotulos: frozenset[str] = frozenset(normalize_brand_label(r) for r in rotulos if r.strip())
        self.aliases = tuple(sorted(self._rotulos))

    def fetch(self, minetur_items: list[dict]) -> tuple[list[Station], list[Price]]:
        stations: list[Station] = []
        prices: list[Price] = []
        today = time.strftime("%Y-%m-%d")

        for item in minetur_items:
            rotulo_raw = get_any(item, "Rótulo", "Rotulo", "rotulo")
            brand_label_raw = rotulo_raw.upper().strip()
            if normalize_brand_label(brand_label_raw) not in self._rotulos:
                continue

            station_id = extract_ideess(item)
            lat = to_float_es(get_any(item, "Latitud", "lat", "latitud"))
            lon = to_float_es(get_any(item, "Longitud (WGS84)", "Longitud", "lon", "longitud"))
            if not station_id or lat is None or lon is None:
                continue

            address = get_any(item, "Dirección", "Direccion", "address")
            municipality = get_any(item, "Municipio", "Localidad")
            province = get_any(item, "Provincia")
            postal_code = get_any(item, "C.P.", "CP", "Código Postal", "Codigo Postal")
            name = f"{self.brand_name} {municipality}".strip() if municipality else self.brand_name

            stations.append(
                Station(
                    station_id=station_id,
                    brand=self.brand_name.upper(),
                    name=name,
                    address=address,
                    postal_code=postal_code,
                    municipality=municipality,
                    province=province,
                    lat=lat,
                    lon=lon,
                    source="MINETUR",
                    last_seen_at=today,
                    raw=item,
                    brand_label_raw=brand_label_raw,
                    brand_canonical=self.brand_name.upper(),
                    brand_group=self.brand_name.upper(),
                    brand_confidence=1.0,
                )
            )

            updated_at = get_any(item, "Fecha", "FechaActualizacion", "Fecha Actualizacion", "FechaActualización")
            for fuel_type, (source_field, _) in FUEL_FIELDS.items():
                price_val = to_float_es(item.get(source_field))
                if price_val is None:
                    continue
                prices.append(
                    Price(
                        station_id=station_id,
                        fuel_type=fuel_type,
                        price_eur_l=price_val,
                        updated_at=updated_at or None,
                        source="MINETUR",
                    )
                )

        logger.info("%s: %d stations, %d prices", self.brand_name, len(stations), len(prices))
        return stations, prices


class BrandRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, BrandAdapter] = {}

    def register(self, adapter: BrandAdapter) -> "BrandRegistry":
        key = adapter.brand_name.upper()
        if key in self._adapters:
            logger.warning("BrandRegistry: overwriting adapter for %s", key)
        self._adapters[key] = adapter
        return self

    def list_brands(self) -> list[str]:
        return sorted(self._adapters.keys())

    def adapters(self) -> list[BrandAdapter]:
        return [self._adapters[key] for key in sorted(self._adapters)]

    def fetch_all(
        self,
        minetur_items: list[dict],
        brands: Optional[list[str]] = None,
        max_network_workers: int = 4,
    ) -> tuple[list[Station], list[Price]]:
        targets = list(self._adapters.values())
        if brands is not None:
            brand_set = {brand.upper() for brand in brands}
            targets = [adapter for adapter in targets if adapter.brand_name.upper() in brand_set]

        if not targets:
            logger.warning("BrandRegistry.fetch_all: no adapters selected")
            return [], []

        all_stations: list[Station] = []
        all_prices: list[Price] = []
        local = [adapter for adapter in targets if not adapter.needs_network()]
        networked = [adapter for adapter in targets if adapter.needs_network()]

        for adapter in local:
            try:
                stations, prices = adapter.fetch(minetur_items)
                all_stations.extend(stations)
                all_prices.extend(prices)
            except Exception:
                logger.exception("Adapter %s (local) failed", adapter.brand_name)

        if networked:
            with ThreadPoolExecutor(max_workers=max_network_workers) as pool:
                futures = {pool.submit(adapter.fetch, minetur_items): adapter for adapter in networked}
                for future in as_completed(futures):
                    adapter = futures[future]
                    try:
                        stations, prices = future.result()
                        all_stations.extend(stations)
                        all_prices.extend(prices)
                    except Exception:
                        logger.exception("Adapter %s (network) failed", adapter.brand_name)

        logger.info(
            "BrandRegistry: total %d stations, %d prices from %d adapters",
            len(all_stations),
            len(all_prices),
            len(targets),
        )
        return all_stations, all_prices
