"""Validate the self-contained PyInstaller onedir output without reading .env."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader


TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".md", ".txt", ".xml"}
FORBIDDEN_PARTS = {".env", ".env.local", ".git", "__pycache__", ".pytest_cache", "tests"}
FORBIDDEN_SUFFIXES = ("-wal", "-shm", ".log", ".next.sqlite")
PERSONAL_PATH_PATTERNS = (
    re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE),
    re.compile(r"/Users/", re.IGNORECASE),
    re.compile(r"OneDrive[\\/]Escritorio", re.IGNORECASE),
)
SECRET_PATTERNS = (
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[0-9A-Za-z]{20,}\b"),
    re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
)


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _internal_root(bundle: Path) -> Path:
    internal = bundle / "_internal"
    return internal if internal.is_dir() else bundle


def _validate_seed(path: Path) -> None:
    _assert(path.is_file(), f"Packaged seed is missing: {path}")
    uri = f"file:{path.resolve().as_posix()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        _assert(connection.execute("PRAGMA quick_check").fetchone() == ("ok",), "Seed quick_check failed.")
        count = connection.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
        _assert(count > 0, "Packaged seed contains no stations.")
    finally:
        connection.close()
    _assert(not Path(f"{path}-wal").exists(), "Seed validation created a WAL sidecar.")
    _assert(not Path(f"{path}-shm").exists(), "Seed validation created an SHM sidecar.")


def validate_bundle(bundle: Path) -> None:
    bundle = bundle.resolve()
    internal = _internal_root(bundle)
    required = (
        bundle / "FuelOpt.exe",
        internal / "static" / "index.html",
        internal / "static" / "app.js",
        internal / "static" / "styles.css",
        internal / "static" / "favicon.ico",
        internal / "static" / "icons" / "fuelopt-32.png",
        internal / "static" / "icons" / "fuelopt-180.png",
        internal / "static" / "vendor" / "leaflet" / "leaflet.js",
        internal / "static" / "vendor" / "leaflet" / "leaflet.css",
        internal / "static" / "vendor" / "leaflet" / "LICENSE",
        internal / "resources" / "snapshot" / "minetur_snapshot.json",
        internal / "resources" / "seed" / "SEED_PROVENANCE.json",
        internal / "licenses" / "LICENSE",
        internal / "licenses" / "NOTICE",
        internal / "licenses" / "DATA_SOURCES_AND_ATTRIBUTION.md",
        internal / "licenses" / "THIRD_PARTY_NOTICES.md",
        internal / "licenses" / "THIRD_PARTY_COMPONENTS.json",
    )
    for path in required:
        _assert(path.is_file(), f"Required onedir resource is missing: {path.relative_to(bundle)}")

    seed = internal / "resources" / "seed" / "gas_stations.seed.sqlite"
    _validate_seed(seed)
    provenance = json.loads(
        (internal / "resources" / "seed" / "SEED_PROVENANCE.json").read_text(encoding="utf-8")
    )
    _assert("MINETUR" in provenance.get("source_name", ""), "Packaged provenance source is not MINETUR.")
    _assert(provenance.get("independent_ballenoil_source_included") is False, "Packaged provenance enables Ballenoil.")
    packaged_seed_files = {
        "gas_stations.sqlite": seed,
        "minetur_snapshot.json": internal / "resources" / "snapshot" / "minetur_snapshot.json",
    }
    for record in provenance.get("seed_files", []):
        packaged = packaged_seed_files.get(Path(record.get("path", "")).name)
        _assert(packaged is not None and packaged.is_file(), f"Unknown packaged provenance record: {record}")
        digest = hashlib.sha256(packaged.read_bytes()).hexdigest().upper()
        _assert(digest == record.get("sha256"), f"Packaged provenance hash mismatch: {record.get('path')}")

    license_text = (internal / "licenses" / "LICENSE").read_text(encoding="utf-8")
    _assert("Apache License" in license_text and "Version 2.0, January 2004" in license_text, "Apache LICENSE is invalid.")
    notice = (internal / "licenses" / "NOTICE").read_text(encoding="utf-8")
    _assert("Copyright 2026 Miguel Pajuelo" in notice, "Packaged NOTICE has the wrong holder.")
    attribution = (internal / "licenses" / "DATA_SOURCES_AND_ATTRIBUTION.md").read_text(encoding="utf-8")
    _assert("MINETUR" in attribution and "Reutilizaci" in attribution, "Packaged data attribution is incomplete.")
    _assert(any(internal.rglob("cacert.pem")), "Certifi CA bundle is missing.")
    _assert(any(internal.glob("slowapi-*.dist-info")), "SlowAPI metadata/license is missing.")
    notices = (internal / "licenses" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    _assert(notices.strip(), "THIRD_PARTY_NOTICES.md is empty.")
    for heading in (
        "## A. Componentes distribuidos en el bundle",
        "## B. Servicios externos utilizados en ejecución",
        "## C. Herramientas de desarrollo y compilación",
    ):
        _assert(heading in notices, f"Third-party notices section is missing: {heading}")

    inventory_path = internal / "licenses" / "THIRD_PARTY_COMPONENTS.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    components = inventory.get("components")
    _assert(isinstance(components, list) and len(components) == 35, "Runtime component inventory is incomplete.")
    serialized_inventory = json.dumps(inventory, ensure_ascii=False)
    _assert("UNKNOWN" not in serialized_inventory and "NOASSERTION" not in serialized_inventory, "Unknown license in bundle inventory.")
    _assert("static/logos" not in serialized_inventory.lower(), "Station logos entered the legal inventory.")
    component_names = {str(component.get("name")) for component in components}
    for required_component in ("Python", "OpenSSL", "requests", "certifi", "Leaflet", "PyInstaller bootloader"):
        _assert(required_component in component_names, f"Runtime component missing from inventory: {required_component}")
    for component in components:
        _assert(component.get("license"), f"Component license is empty: {component}")
        legal_paths = component.get("legal_paths")
        _assert(isinstance(legal_paths, list) and legal_paths, f"Component has no legal text: {component}")
        for relative in legal_paths:
            _assert((internal / relative).is_file(), f"Declared legal text is missing: {relative}")
    requests_component = next(component for component in components if component.get("name") == "requests")
    _assert(any(str(path).endswith("/NOTICE") for path in requests_component.get("notice_paths", [])), "Requests NOTICE missing.")
    certifi_component = next(component for component in components if component.get("name") == "certifi")
    _assert(certifi_component.get("license") == "MPL-2.0", "certifi license is incorrect.")
    _assert(str(certifi_component.get("source_code_url", "")).endswith("2026.06.17"), "certifi source URL is not exact.")

    archive = CArchiveReader(str(bundle / "FuelOpt.exe")).open_embedded_archive("PYZ.pyz")
    frozen_modules = set(archive.toc)
    for component in components:
        for import_name in component.get("import_names", []):
            _assert(
                import_name in frozen_modules or any(name.startswith(f"{import_name}.") for name in frozen_modules),
                f"Inventoried Python package is absent from the frozen module graph: {component.get('name')}",
            )
    for forbidden_module in ("_pytest", "bs4", "httpcore", "httpx", "pytest", "setuptools", "soupsieve"):
        _assert(
            forbidden_module not in frozen_modules
            and not any(name.startswith(f"{forbidden_module}.") for name in frozen_modules),
            f"Build/test module was frozen: {forbidden_module}",
        )
    for native_runtime in (
        "python312.dll",
        "libcrypto-3.dll",
        "libssl-3.dll",
        "libffi-8.dll",
        "sqlite3.dll",
        "VCRUNTIME140.dll",
        "VCRUNTIME140_1.dll",
        "ucrtbase.dll",
    ):
        _assert((internal / native_runtime).is_file(), f"Native runtime component is missing: {native_runtime}")
    for forbidden_document in ("FINAL_REVIEW_BACKLOG.md", "AUDITORIA_PROYECTO.md"):
        _assert(not any(internal.rglob(forbidden_document)), f"Internal document was bundled: {forbidden_document}")
    _assert(not (internal / "data").exists(), "Developer cache data must not be bundled.")
    _assert(not (internal / "assets").exists(), "Brand source and build-only assets must not be bundled.")
    for optional_runtime in ("bs4", "httpcore", "httpx", "httptools", "pytest", "setuptools", "soupsieve", "watchfiles", "websockets"):
        _assert(not (internal / optional_runtime).exists(), f"Unused optional runtime was bundled: {optional_runtime}")

    violations: list[str] = []
    for path in bundle.rglob("*"):
        relative = path.relative_to(bundle)
        lowered_parts = {part.lower() for part in relative.parts}
        if lowered_parts & FORBIDDEN_PARTS:
            violations.append(f"forbidden path: {relative}")
            continue
        if path.is_file() and path.name.lower().endswith(FORBIDDEN_SUFFIXES):
            violations.append(f"mutable artifact: {relative}")
            continue
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 5_000_000:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in PERSONAL_PATH_PATTERNS):
            violations.append(f"personal absolute path: {relative}")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            violations.append(f"secret-shaped value: {relative}")
    _assert(not violations, "Unsafe bundle content:\n  " + "\n  ".join(violations))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    validate_bundle(args.bundle)
    print("OK: PyInstaller onedir bundle checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
