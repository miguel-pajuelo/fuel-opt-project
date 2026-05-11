from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data_sources.adapters import BrandRegistry, MineturFilterAdapter
from app.data_sources.brand_catalog import NORMALIZATION_VERSION, canonicalize_brand_label


SAMPLE_ITEMS = [
    {
        "IDEESS": "1001",
        "Rotulo": "REPSOL",
        "Latitud": "40,416775",
        "Longitud (WGS84)": "-3,703790",
        "Direccion": "CALLE GRAN VIA 1",
        "Municipio": "MADRID",
        "Provincia": "MADRID",
        "C.P.": "28013",
        "Precio Gasoleo A": "1,599",
        "Precio Gasolina 95 E5": "1,699",
    },
    {
        "IDEESS": "1002",
        "Rotulo": "CEPSA",
        "Latitud": "40,453305",
        "Longitud (WGS84)": "-3,688627",
        "Direccion": "AVENIDA DE AMERICA 5",
        "Municipio": "MADRID",
        "Provincia": "MADRID",
        "C.P.": "28028",
        "Precio Gasoleo A": "1,579",
    },
    {
        "IDEESS": "1003",
        "Rotulo": "CAMPSA",
        "Latitud": "40,400000",
        "Longitud (WGS84)": "-3,700000",
        "Direccion": "CALLE TOLEDO 10",
        "Municipio": "MADRID",
        "Provincia": "MADRID",
        "C.P.": "28005",
        "Precio Gasoleo A": "1,589",
    },
]


def test_filter_single_rotulo() -> None:
    adapter = MineturFilterAdapter("Cepsa", ["CEPSA"])
    stations, _ = adapter.fetch(SAMPLE_ITEMS)
    assert len(stations) == 1
    assert stations[0].station_id == "1002"
    assert stations[0].brand == "CEPSA"
    assert stations[0].brand_label_raw == "CEPSA"
    assert stations[0].brand_canonical == "CEPSA"


def test_filter_multi_rotulo() -> None:
    adapter = MineturFilterAdapter("Repsol", ["REPSOL", "CAMPSA"])
    stations, _ = adapter.fetch(SAMPLE_ITEMS)
    assert len(stations) == 2
    assert all(station.brand == "REPSOL" for station in stations)
    assert {station.brand_label_raw for station in stations} == {"REPSOL", "CAMPSA"}
    assert all(station.brand_canonical == "REPSOL" for station in stations)


def test_prices_parsed() -> None:
    adapter = MineturFilterAdapter("Repsol", ["REPSOL"])
    stations, prices = adapter.fetch(SAMPLE_ITEMS)
    assert len(stations) == 1
    fuel_types = {price.fuel_type for price in prices}
    assert "gasoleo_a" in fuel_types
    assert "gasolina_95" in fuel_types
    repsol_gasoleo = next(price for price in prices if price.fuel_type == "gasoleo_a")
    assert abs(repsol_gasoleo.price_eur_l - 1.599) < 1e-6


def test_registry_fetch_all() -> None:
    registry = BrandRegistry()
    registry.register(MineturFilterAdapter("Repsol", ["REPSOL", "CAMPSA"]))
    registry.register(MineturFilterAdapter("Cepsa", ["CEPSA"]))
    stations, _ = registry.fetch_all(SAMPLE_ITEMS)
    assert len(stations) == 3
    assert {station.brand for station in stations} == {"REPSOL", "CEPSA"}


def test_registry_fetch_filtered() -> None:
    registry = BrandRegistry()
    registry.register(MineturFilterAdapter("Repsol", ["REPSOL", "CAMPSA"]))
    registry.register(MineturFilterAdapter("Cepsa", ["CEPSA"]))
    stations, _ = registry.fetch_all(SAMPLE_ITEMS, brands=["Cepsa"])
    assert len(stations) == 1
    assert all(station.brand == "CEPSA" for station in stations)


def test_adapter_no_network() -> None:
    adapter = MineturFilterAdapter("Repsol", ["REPSOL"])
    assert adapter.needs_network() is False


def test_missing_coords_skipped() -> None:
    bad_item = {"IDEESS": "9999", "Rotulo": "REPSOL"}
    adapter = MineturFilterAdapter("Repsol", ["REPSOL"])
    stations, prices = adapter.fetch([bad_item])
    assert stations == []
    assert prices == []


def test_brand_registry_v3_canonicalizes_long_tail_labels() -> None:
    assert NORMALIZATION_VERSION == "brand-registry-v3"
    assert canonicalize_brand_label("ESCLATOIL") == ("ESCLATOIL", "ESCLATOIL", 1.0)
    assert canonicalize_brand_label("ALIARA ENERGÍA") == ("ALIARA ENERGIA", "ALIARA ENERGIA", 1.0)
    assert canonicalize_brand_label("PETROLIS INDEPENDENTS - PETRO7") == ("PETROLIS", "PETROLIS", 1.0)
    assert canonicalize_brand_label("SIN ROTULO") == ("UNKNOWN", "UNKNOWN", 0.0)


def run() -> None:
    test_filter_single_rotulo()
    test_filter_multi_rotulo()
    test_prices_parsed()
    test_registry_fetch_all()
    test_registry_fetch_filtered()
    test_adapter_no_network()
    test_missing_coords_skipped()
    test_brand_registry_v3_canonicalizes_long_tail_labels()
    print("OK: adapter checks passed")


if __name__ == "__main__":
    run()
