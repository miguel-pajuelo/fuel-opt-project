"""Source checks for deterministic runtime inventory and complete legal texts."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generate_runtime_legal_inventory import generate, read_lock


EXPECTED_COMPONENTS = {
    "Python",
    "OpenSSL",
    "libffi",
    "SQLite",
    "bzip2",
    "XZ Utils liblzma",
    "zlib",
    "Microsoft Visual C++ Runtime and Universal CRT",
    "PyInstaller bootloader",
    "Leaflet",
    "requests",
    "certifi",
}
FORBIDDEN_RUNTIME = {
    "beautifulsoup4",
    "httpcore",
    "httpx",
    "pillow",
    "pyinstaller",
    "pytest",
    "setuptools",
    "soupsieve",
}
OFFICIAL_SOURCE_HASHES = {
    "BZIP2-1.0.8-LICENSE.txt": "67FC67381A47FE66F07B5F6705472D26314E6BCDF949F92C2CDDE64521BBFDCE",
    "LIBFFI-3.4.4-LICENSE.txt": "2C9C2ACB9743E6B007B91350475308AEE44691D96AA20EACEF8E199988C8C388",
    "OPENSSL-3.0.16-LICENSE.txt": "7D5450CB2D142651B8AFA315B5F238EFC805DAD827D91BA367D8516BC9D49E7A",
    "PYTHON-3.12.10-LICENSE.txt": "3B2F81FE21D181C499C59A256C8E1968455D6689D269AA85373BFB6AF41DA3BF",
    "XZ-5.2.5-COPYING.txt": "073060D5C1EE43EE909638ED7DBA5547161AB264F7859CFDDEF8A213EF6B67FE",
    "ZLIB-1.3.1-LICENSE.txt": "845EFC77857D485D91FB3E0B884AAA929368C717AE8186B66FE1ED2495753243",
}


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().lower()):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest().upper()


def test_runtime_lock_is_exact_and_separated() -> None:
    lock = read_lock()
    _assert(len(lock) == 25, f"Unexpected runtime lock size: {len(lock)}")
    _assert(not (set(lock) & FORBIDDEN_RUNTIME), f"Build/test dependency in runtime lock: {set(lock) & FORBIDDEN_RUNTIME}")
    _assert(all(version and "*" not in version for version in lock.values()), "Runtime lock is not exact")
    web = (ROOT / "requirements-web.txt").read_text(encoding="utf-8").lower()
    _assert("beautifulsoup4" not in web and "uvicorn[standard]" not in web, "Unused runtime extras remain enabled")
    for filename, expected in OFFICIAL_SOURCE_HASHES.items():
        actual = hashlib.sha256((ROOT / "legal" / "runtime" / filename).read_bytes()).hexdigest().upper()
        _assert(actual == expected, f"Official legal source changed: {filename}")
    notices = (ROOT / "docs" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8").lower()
    _assert("identidad visual" not in notices and "static/logos" not in notices, "Logo provenance entered legal notices")


def test_inventory_is_deterministic_and_complete() -> None:
    with tempfile.TemporaryDirectory(prefix="fuelopt-legal-a-") as first_raw, tempfile.TemporaryDirectory(
        prefix="fuelopt-legal-b-"
    ) as second_raw:
        first = Path(first_raw)
        second = Path(second_raw)
        first_inventory = generate(first)
        second_inventory = generate(second)
        _assert(_tree_hash(first) == _tree_hash(second), "Legal generator output is not deterministic")
        _assert(first_inventory == second_inventory, "Inventory JSON differs between runs")
        components = first_inventory["components"]
        _assert(len(components) == 35, f"Unexpected component count: {len(components)}")
        names = {str(component["name"]) for component in components}
        _assert(EXPECTED_COMPONENTS <= names, f"Required components missing: {EXPECTED_COMPONENTS - names}")
        lowered_names = {name.lower() for name in names}
        _assert(not (lowered_names & FORBIDDEN_RUNTIME), f"Build/test component inventoried: {lowered_names & FORBIDDEN_RUNTIME}")
        serialized = json.dumps(first_inventory, ensure_ascii=False)
        _assert("UNKNOWN" not in serialized and "NOASSERTION" not in serialized, "Unknown license in inventory")
        _assert("static/logos" not in serialized.lower(), "Station logos must not enter the legal inventory")
        for component in components:
            _assert(component["redistributed"] is True, component)
            _assert(component["license"], component)
            _assert(component["legal_paths"], component)
        requests = next(component for component in components if component["name"] == "requests")
        _assert(any(path.endswith("/NOTICE") for path in requests["notice_paths"]), "Requests NOTICE missing")
        certifi = next(component for component in components if component["name"] == "certifi")
        _assert(certifi["license"] == "MPL-2.0", certifi)
        _assert(certifi["source_code_url"].endswith("2026.06.17"), certifi)
        text_count = sum(1 for path in first.joinpath("third_party").rglob("*") if path.is_file())
        _assert(text_count == 37, f"Unexpected legal text count: {text_count}")


def run() -> None:
    test_runtime_lock_is_exact_and_separated()
    test_inventory_is_deterministic_and_complete()
    print("OK: deterministic runtime legal inventory checks passed (35 components, 37 texts)")


if __name__ == "__main__":
    run()
