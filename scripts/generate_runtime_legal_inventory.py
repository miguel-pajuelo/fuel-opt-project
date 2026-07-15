"""Generate deterministic runtime component and license inventory without network access."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import re
import shutil
import sqlite3
import ssl
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements-runtime.lock"
DEFAULT_OUTPUT = ROOT / "build" / "legal-runtime"
LEGAL_SOURCE = ROOT / "legal" / "runtime"
FORBIDDEN_LICENSE_VALUES = {"", "UNKNOWN", "NOASSERTION"}
UTF8_BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class PackagePolicy:
    spdx: str
    project_url: str


PACKAGE_POLICIES: dict[str, PackagePolicy] = {
    "annotated-doc": PackagePolicy("MIT", "https://github.com/fastapi/annotated-doc"),
    "annotated-types": PackagePolicy("MIT", "https://github.com/annotated-types/annotated-types"),
    "anyio": PackagePolicy("MIT", "https://github.com/agronholm/anyio"),
    "certifi": PackagePolicy("MPL-2.0", "https://github.com/certifi/python-certifi/tree/2026.06.17"),
    "charset-normalizer": PackagePolicy("MIT", "https://github.com/jawah/charset_normalizer"),
    "click": PackagePolicy("BSD-3-Clause", "https://github.com/pallets/click"),
    "colorama": PackagePolicy("BSD-3-Clause", "https://github.com/tartley/colorama"),
    "deprecated": PackagePolicy("MIT", "https://github.com/tantale/deprecated"),
    "fastapi": PackagePolicy("MIT", "https://github.com/fastapi/fastapi"),
    "h11": PackagePolicy("MIT", "https://github.com/python-hyper/h11"),
    "idna": PackagePolicy("BSD-3-Clause", "https://github.com/kjd/idna"),
    "limits": PackagePolicy("MIT", "https://github.com/alisaifee/limits"),
    "packaging": PackagePolicy("Apache-2.0 OR BSD-2-Clause", "https://github.com/pypa/packaging"),
    "pydantic": PackagePolicy("MIT", "https://github.com/pydantic/pydantic"),
    "pydantic-core": PackagePolicy("MIT", "https://github.com/pydantic/pydantic-core"),
    "python-dotenv": PackagePolicy("BSD-3-Clause", "https://github.com/theskumar/python-dotenv"),
    "pyyaml": PackagePolicy("MIT", "https://github.com/yaml/pyyaml"),
    "requests": PackagePolicy("Apache-2.0", "https://github.com/psf/requests"),
    "slowapi": PackagePolicy("MIT", "https://github.com/laurentS/slowapi"),
    "starlette": PackagePolicy("BSD-3-Clause", "https://github.com/Kludex/starlette"),
    "typing-extensions": PackagePolicy("PSF-2.0", "https://github.com/python/typing_extensions"),
    "typing-inspection": PackagePolicy("MIT", "https://github.com/pydantic/typing-inspection"),
    "urllib3": PackagePolicy("MIT", "https://github.com/urllib3/urllib3"),
    "uvicorn": PackagePolicy("BSD-3-Clause", "https://github.com/Kludex/uvicorn"),
    "wrapt": PackagePolicy("BSD-2-Clause", "https://github.com/GrahamDumpleton/wrapt"),
}

PACKAGE_IMPORTS = {
    "annotated-doc": ["annotated_doc"],
    "annotated-types": ["annotated_types"],
    "anyio": ["anyio"],
    "certifi": ["certifi"],
    "charset-normalizer": ["charset_normalizer"],
    "click": ["click"],
    "colorama": ["colorama"],
    "deprecated": ["deprecated"],
    "fastapi": ["fastapi"],
    "h11": ["h11"],
    "idna": ["idna"],
    "limits": ["limits"],
    "packaging": ["packaging"],
    "pydantic": ["pydantic"],
    "pydantic-core": ["pydantic_core"],
    "python-dotenv": ["dotenv"],
    "pyyaml": ["yaml"],
    "requests": ["requests"],
    "slowapi": ["slowapi"],
    "starlette": ["starlette"],
    "typing-extensions": ["typing_extensions"],
    "typing-inspection": ["typing_inspection"],
    "urllib3": ["urllib3"],
    "uvicorn": ["uvicorn"],
    "wrapt": ["wrapt"],
}


CORE_COMPONENTS = (
    {
        "name": "Python",
        "version": "3.12.10",
        "license": "PSF-2.0",
        "type": "Python runtime",
        "project_url": "https://www.python.org/downloads/release/python-31210/",
        "source_file": "PYTHON-3.12.10-LICENSE.txt",
    },
    {
        "name": "OpenSSL",
        "version": "3.0.16",
        "license": "Apache-2.0",
        "type": "DLL/runtime",
        "project_url": "https://github.com/openssl/openssl/tree/openssl-3.0.16",
        "source_file": "OPENSSL-3.0.16-LICENSE.txt",
    },
    {
        "name": "libffi",
        "version": "3.4.4",
        "license": "MIT",
        "type": "DLL/runtime",
        "project_url": "https://github.com/libffi/libffi/tree/v3.4.4",
        "source_file": "LIBFFI-3.4.4-LICENSE.txt",
    },
    {
        "name": "SQLite",
        "version": "3.49.1",
        "license": "blessing",
        "type": "DLL/runtime",
        "project_url": "https://www.sqlite.org/releaselog/3_49_1.html",
        "source_file": "SQLITE-3.49.1-NOTICE.txt",
    },
    {
        "name": "bzip2",
        "version": "1.0.8",
        "license": "bzip2-1.0.6",
        "type": "Python runtime component",
        "project_url": "https://github.com/python/cpython-source-deps/tree/bzip2-1.0.8",
        "source_file": "BZIP2-1.0.8-LICENSE.txt",
    },
    {
        "name": "XZ Utils liblzma",
        "version": "5.2.5",
        "license": "LicenseRef-XZ-Public-Domain",
        "type": "Python runtime component",
        "project_url": "https://github.com/python/cpython-source-deps/tree/xz-5.2.5",
        "source_file": "XZ-5.2.5-COPYING.txt",
    },
    {
        "name": "zlib",
        "version": "1.3.1",
        "license": "Zlib",
        "type": "Python runtime component",
        "project_url": "https://github.com/python/cpython-source-deps/tree/zlib-1.3.1",
        "source_file": "ZLIB-1.3.1-LICENSE.txt",
    },
    {
        "name": "Microsoft Visual C++ Runtime and Universal CRT",
        "version": "14.42.34438 / 10.0.26100.1742",
        "license": "LicenseRef-Microsoft-Redistributable",
        "type": "DLL/runtime",
        "project_url": "https://learn.microsoft.com/visualstudio/releases/2022/redistribution",
        "source_file": "MICROSOFT-RUNTIME-REDISTRIBUTION.txt",
    },
)


def canonical_name(value: str) -> str:
    return re.sub(r"[-_.\s]+", "-", value).strip("-").lower()


def read_lock() -> dict[str, str]:
    result: dict[str, str] = {}
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.count("==") != 1:
            raise ValueError(f"Runtime lock entry is not exact: {line}")
        name, version = line.split("==", 1)
        key = canonical_name(name)
        if key in result:
            raise ValueError(f"Duplicate runtime lock entry: {name}")
        result[key] = version
    if set(result) != set(PACKAGE_POLICIES):
        missing = sorted(set(PACKAGE_POLICIES) - set(result))
        extra = sorted(set(result) - set(PACKAGE_POLICIES))
        raise ValueError(f"Runtime lock/policy mismatch; missing={missing}, extra={extra}")
    return result


def legal_files(distribution: metadata.Distribution) -> list[Path]:
    dist_info = Path(distribution._path)  # importlib exposes no public dist-info path API.
    candidates = []
    for path in sorted(dist_info.rglob("*"), key=lambda item: item.as_posix().lower()):
        if not path.is_file():
            continue
        lowered = path.name.lower()
        if lowered.startswith(("license", "licence", "copying", "notice", "authors")):
            candidates.append(path)
    return candidates


def safe_filename(path: Path, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", path.name).strip("-") or "LICENSE.txt"
    candidate = base
    index = 2
    while candidate.lower() in used:
        candidate = f"{path.stem}-{index}{path.suffix}"
        index += 1
    used.add(candidate.lower())
    return candidate


def canonical_legal_bytes(raw: bytes) -> bytes:
    """Return platform-independent bytes without changing legal text content."""
    if raw.startswith(UTF8_BOM):
        raw = raw[len(UTF8_BOM) :]
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def legal_text_sha256(path: Path) -> str:
    return hashlib.sha256(canonical_legal_bytes(path.read_bytes())).hexdigest().upper()


def copy_text(source: Path, destination: Path) -> None:
    raw = canonical_legal_bytes(source.read_bytes())
    raw.decode("utf-8", errors="strict")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)


def package_components(output: Path, lock: dict[str, str]) -> list[dict[str, object]]:
    components: list[dict[str, object]] = []
    for name in sorted(lock):
        expected = lock[name]
        distribution = metadata.distribution(name)
        actual_name = distribution.metadata["Name"]
        if distribution.version != expected:
            raise RuntimeError(f"{actual_name} version mismatch: expected {expected}, found {distribution.version}")
        sources = legal_files(distribution)
        if not sources:
            raise RuntimeError(f"No complete legal text found in installed metadata for {actual_name} {expected}")
        destination_dir = output / "third_party" / name
        used: set[str] = set()
        paths: list[str] = []
        notices: list[str] = []
        for source in sources:
            destination = destination_dir / safe_filename(source, used)
            copy_text(source, destination)
            relative = Path("licenses") / "third_party" / name / destination.name
            relative_text = relative.as_posix()
            paths.append(relative_text)
            if source.name.lower().startswith("notice"):
                notices.append(relative_text)
        policy = PACKAGE_POLICIES[name]
        components.append(
            {
                "name": actual_name,
                "version": expected,
                "license": policy.spdx,
                "type": "Python package",
                "project_url": policy.project_url,
                "redistributed": True,
                "legal_paths": sorted(paths),
                "notice_paths": sorted(notices),
                "source_code_url": policy.project_url if name == "certifi" else None,
                "import_names": PACKAGE_IMPORTS[name],
            }
        )
    return components


def core_components(output: Path) -> list[dict[str, object]]:
    components: list[dict[str, object]] = []
    for item in CORE_COMPONENTS:
        source = LEGAL_SOURCE / str(item["source_file"])
        if not source.is_file() or source.stat().st_size == 0:
            raise RuntimeError(f"Required official runtime legal text is missing: {source}")
        slug = canonical_name(str(item["name"]))
        destination = output / "third_party" / slug / source.name
        copy_text(source, destination)
        components.append(
            {
                "name": item["name"],
                "version": item["version"],
                "license": item["license"],
                "type": item["type"],
                "project_url": item["project_url"],
                "redistributed": True,
                "legal_paths": [(Path("licenses") / "third_party" / slug / source.name).as_posix()],
                "notice_paths": [],
                "source_code_url": None,
                "import_names": [],
            }
        )

    pyinstaller = metadata.distribution("pyinstaller")
    if pyinstaller.version != "6.19.0":
        raise RuntimeError(f"PyInstaller version mismatch: expected 6.19.0, found {pyinstaller.version}")
    pyinstaller_sources = legal_files(pyinstaller)
    if not pyinstaller_sources:
        raise RuntimeError("PyInstaller bootloader legal texts are missing")
    paths: list[str] = []
    used: set[str] = set()
    destination_dir = output / "third_party" / "pyinstaller-bootloader"
    for source in pyinstaller_sources:
        destination = destination_dir / safe_filename(source, used)
        copy_text(source, destination)
        paths.append((Path("licenses") / "third_party" / "pyinstaller-bootloader" / destination.name).as_posix())
    components.append(
        {
            "name": "PyInstaller bootloader",
            "version": "6.19.0",
            "license": "GPL-2.0-or-later WITH Bootloader-exception",
            "type": "embedded bootloader",
            "project_url": "https://github.com/pyinstaller/pyinstaller/tree/v6.19.0",
            "redistributed": True,
            "legal_paths": sorted(paths),
            "notice_paths": [],
            "source_code_url": None,
            "import_names": [],
        }
    )

    leaflet_source = ROOT / "static" / "vendor" / "leaflet" / "LICENSE"
    if not leaflet_source.is_file():
        raise RuntimeError("Leaflet license is missing")
    components.append(
        {
            "name": "Leaflet",
            "version": "1.9.4",
            "license": "BSD-2-Clause",
            "type": "JavaScript",
            "project_url": "https://github.com/Leaflet/Leaflet/tree/v1.9.4",
            "redistributed": True,
            "legal_paths": ["static/vendor/leaflet/LICENSE"],
            "notice_paths": [],
            "source_code_url": None,
            "import_names": [],
        }
    )
    return components


def validate_inventory(components: list[dict[str, object]], output: Path) -> None:
    identities: set[tuple[str, str]] = set()
    for component in components:
        identity = (str(component["name"]).lower(), str(component["version"]))
        if identity in identities:
            raise RuntimeError(f"Duplicate component: {identity}")
        identities.add(identity)
        if str(component["license"]).upper() in FORBIDDEN_LICENSE_VALUES:
            raise RuntimeError(f"Unknown license: {component['name']}")
        legal_paths = component.get("legal_paths")
        if not isinstance(legal_paths, list) or not legal_paths:
            raise RuntimeError(f"No legal path: {component['name']}")
        for relative in legal_paths:
            if str(relative).startswith("static/"):
                path = ROOT / str(relative)
            else:
                path = output / str(relative).removeprefix("licenses/")
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError(f"Missing declared legal text for {component['name']}: {relative}")


def generate(output: Path) -> dict[str, object]:
    if sys.version_info[:3] != (3, 12, 10):
        raise RuntimeError(f"Legal inventory requires CPython 3.12.10, found {sys.version.split()[0]}")
    if ssl.OPENSSL_VERSION_INFO[:4] != (3, 0, 0, 16):
        raise RuntimeError(f"Legal inventory requires OpenSSL 3.0.16, found {ssl.OPENSSL_VERSION}")
    if sqlite3.sqlite_version != "3.49.1":
        raise RuntimeError(f"Legal inventory requires SQLite 3.49.1, found {sqlite3.sqlite_version}")
    lock = read_lock()
    if output.exists():
        shutil.rmtree(output)
    (output / "third_party").mkdir(parents=True)
    components = package_components(output, lock) + core_components(output)
    components.sort(key=lambda item: (str(item["name"]).lower(), str(item["version"])))
    validate_inventory(components, output)
    inventory = {
        "schema_version": 1,
        "target": "FuelOpt Windows x64 / CPython 3.12.10",
        "components": components,
    }
    inventory_path = output / "THIRD_PARTY_COMPONENTS.json"
    inventory_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return inventory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    inventory = generate(args.output.resolve())
    texts = sum(1 for path in (args.output / "third_party").rglob("*") if path.is_file())
    print(f"OK: generated {len(inventory['components'])} runtime components and {texts} legal texts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
