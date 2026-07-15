"""Release-readiness checks for licensing and catalog provenance."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data_sources.minetur import build_catalog_from_minetur
from app.storage.database import list_stations, replace_catalog
from scripts import rebuild_station_catalog


REMOVED_BALLENOIL_CACHES = (
    "data/cache/ballenoil_espana_combustible.txt",
    "data/cache/ballenoil_mapping.json",
    "data/cache/ballenoil_precios.json",
)


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _sample_ballenoil_from_minetur() -> dict[str, str]:
    return {
        "IDEESS": "release-legal-1",
        "Rotulo": "BALLENOIL",
        "Direccion": "Calle de prueba",
        "C.P.": "28001",
        "Municipio": "Madrid",
        "Provincia": "Madrid",
        "Latitud": "40,4200",
        "Longitud (WGS84)": "-3,7000",
        "Precio Gasoleo A": "1,500",
    }


def test_seed_provenance_and_integrity() -> None:
    provenance_path = ROOT / "data" / "SEED_PROVENANCE.json"
    _assert(provenance_path.is_file(), "Seed provenance metadata is missing")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    _assert("MINETUR" in provenance.get("source_name", ""), provenance)
    _assert(provenance.get("source_url"), "MINETUR source URL is missing")
    _assert(provenance.get("source_url") == "https://geoportalgasolineras.es/", provenance.get("source_url"))
    _assert(
        provenance.get("reuse_terms_url")
        == "https://sede.serviciosmin.gob.es/es-ES/Paginas/aviso.aspx#Reutilizacion",
        provenance.get("reuse_terms_url"),
    )
    _assert(provenance.get("retrieved_at"), "Seed retrieval date is missing")
    _assert(provenance.get("independent_ballenoil_source_included") is False, provenance)

    seed_records = provenance.get("seed_files")
    _assert(isinstance(seed_records, list) and len(seed_records) == 2, seed_records)
    for record in seed_records:
        path = ROOT / record["path"]
        _assert(path.is_file(), f"Declared seed input is missing: {record['path']}")
        _assert(_sha256(path) == record["sha256"], f"Seed hash mismatch: {record['path']}")

    snapshot = json.loads((ROOT / "data" / "cache" / "minetur_snapshot.json").read_text(encoding="utf-8"))
    _assert(provenance["retrieved_at"] == snapshot.get("fetched_at"), "Seed retrieval date does not match snapshot")
    attribution = (ROOT / "docs" / "DATA_SOURCES_AND_ATTRIBUTION.md").read_text(encoding="utf-8")
    for required in (provenance["source_url"], provenance["reuse_terms_url"], provenance["retrieved_at"], "SQLite"):
        _assert(required in attribution, f"Data attribution is missing: {required}")

    database_path = ROOT / "data" / "db" / "gas_stations.sqlite"
    sidecars = [Path(f"{database_path}{suffix}") for suffix in ("-wal", "-shm")]
    sidecar_state_before = {path: (path.exists(), path.stat().st_size if path.exists() else None) for path in sidecars}
    uri = f"file:{database_path.resolve().as_posix()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        _assert(connection.execute("PRAGMA quick_check").fetchone() == ("ok",), "Seed quick_check failed")
        _assert(connection.execute("PRAGMA integrity_check").fetchone() == ("ok",), "Seed integrity_check failed")
        _assert(connection.execute("SELECT COUNT(*) FROM stations").fetchone()[0] > 0, "Seed is empty")
        sources = {row[0] for row in connection.execute("SELECT DISTINCT source FROM stations")}
        _assert(sources == {"MINETUR"}, f"Unexpected seed station sources: {sources}")
        metadata = dict(connection.execute("SELECT key, value FROM catalog_metadata"))
        _assert(str(metadata.get("source", "")).startswith("MINETUR"), metadata.get("source"))
        _assert(metadata.get("dataset_version") == provenance.get("sqlite_schema_version"), metadata)
    finally:
        connection.close()
    sidecar_state_after = {path: (path.exists(), path.stat().st_size if path.exists() else None) for path in sidecars}
    _assert(sidecar_state_after == sidecar_state_before, "Read-only seed check changed SQLite sidecars")


def test_productive_refresh_is_minetur_only() -> None:
    for relative in REMOVED_BALLENOIL_CACHES:
        _assert(not (ROOT / relative).exists(), f"Retired Ballenoil cache remains: {relative}")

    rebuild_source = (ROOT / "scripts" / "rebuild_station_catalog.py").read_text(encoding="utf-8").lower()
    refresh_source = (ROOT / "app" / "catalog" / "refresh_service.py").read_text(encoding="utf-8").lower()
    config_source = (ROOT / "app" / "config.py").read_text(encoding="utf-8").lower()
    for source in (rebuild_source, refresh_source, config_source):
        _assert("ballenoil_result" not in source and "ballenoil_prices" not in source, "Ballenoil cache is active")
    _assert("load_prices_cache_as_catalog" not in rebuild_source, "Legacy price-cache fallback is active")
    _assert("load_ballenoil_result_cache" not in rebuild_source, "Ballenoil adapter is active")

    with tempfile.TemporaryDirectory() as temporary:
        snapshot = Path(temporary) / "minetur_snapshot.json"
        snapshot.write_text(
            json.dumps({"source": "MINETUR", "fetched_at": "2026-01-01T00:00:00+0000", "items": [_sample_ballenoil_from_minetur()]}),
            encoding="utf-8",
        )
        args = SimpleNamespace(source="snapshot", snapshot=snapshot, brands=None)
        (stations, prices), source, warnings = rebuild_station_catalog.load_catalog(args)
        _assert(source == "MINETUR_SNAPSHOT" and warnings == [], (source, warnings))
        _assert(len(stations) == 1 and len(prices) == 1, (stations, prices))
        _assert(stations[0].source == "MINETUR" and stations[0].brand == "BALLENOIL", stations[0])
        for relative in REMOVED_BALLENOIL_CACHES:
            _assert(not (ROOT / relative).exists(), f"Refresh recreated retired cache: {relative}")


def test_ballenoil_brand_from_minetur_remains_public() -> None:
    stations, prices = build_catalog_from_minetur([_sample_ballenoil_from_minetur()])
    _assert(len(stations) == 1 and stations[0].source == "MINETUR", stations)
    _assert(stations[0].brand == "BALLENOIL", stations[0])
    with tempfile.TemporaryDirectory() as temporary:
        database_path = Path(temporary) / "catalog.sqlite"
        replace_catalog(database_path, stations, prices, metadata={"source": "MINETUR"})
        visible = list_stations(database_path, brand="BALLENOIL")
        _assert([station.station_id for station in visible] == ["release-legal-1"], visible)


def test_spec_declares_legal_and_provenance_files() -> None:
    spec = (ROOT / "FuelOpt.spec").read_text(encoding="utf-8")
    for declaration in (
        'ROOT / "LICENSE"',
        'ROOT / "NOTICE"',
        'ROOT / "docs" / "DATA_SOURCES_AND_ATTRIBUTION.md"',
        'ROOT / "docs" / "THIRD_PARTY_NOTICES.md"',
        'ROOT / "data" / "SEED_PROVENANCE.json"',
    ):
        _assert(declaration in spec, f"Bundle declaration missing: {declaration}")
    for cache_name in REMOVED_BALLENOIL_CACHES:
        _assert(Path(cache_name).name not in spec, f"Retired cache is bundled: {cache_name}")


def run() -> None:
    test_seed_provenance_and_integrity()
    test_productive_refresh_is_minetur_only()
    test_ballenoil_brand_from_minetur_remains_public()
    test_spec_declares_legal_and_provenance_files()
    print("OK: release licensing, provenance, and MINETUR-only checks passed")


if __name__ == "__main__":
    run()
