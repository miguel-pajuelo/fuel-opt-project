"""Validate FuelOpt's generated VERSIONINFO source and built PE resources."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generate_version_info import COPYRIGHT_NOTICE, DEFAULT_VERSION, parse_version, render_version_info


EXPECTED_TEXT_FIELDS = {
    "FileDescription": "FuelOpt",
    "InternalName": "FuelOpt",
    "OriginalFilename": "FuelOpt.exe",
    "ProductName": "FuelOpt",
}
FORBIDDEN_VALUE_PATTERN = re.compile(
    r"(?:[A-Za-z]:\\Users\\|/Users/|OneDrive[\\/]Escritorio|TODO|TBD|PLACEHOLDER|FuelOpt Inc\.|FuelOpt LLC)",
    re.IGNORECASE,
)


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _decode(value: bytes | str) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


def _string_fields(pe: pefile.PE) -> dict[str, str]:
    result: dict[str, str] = {}
    for group in getattr(pe, "FileInfo", []):
        for entry in group:
            if _decode(entry.Key) != "StringFileInfo":
                continue
            for table in entry.StringTable:
                result.update({_decode(key): _decode(value) for key, value in table.entries.items()})
    return result


def _resource_ids(pe: pefile.PE) -> set[int]:
    directory = getattr(pe, "DIRECTORY_ENTRY_RESOURCE", None)
    if directory is None:
        return set()
    return {entry.id for entry in directory.entries if entry.id is not None}


def validate_source() -> None:
    version, numeric = parse_version(DEFAULT_VERSION)
    _assert(version == "0.1.2" and numeric == (0, 1, 2, 0), "default version mapping is invalid")
    content = render_version_info(DEFAULT_VERSION)
    for key, value in EXPECTED_TEXT_FIELDS.items():
        _assert(f"StringStruct(u'{key}', u'{value}')" in content, f"missing generated field: {key}")
    _assert("StringStruct(u'FileVersion', u'0.1.2')" in content, "text FileVersion is inconsistent")
    _assert("StringStruct(u'ProductVersion', u'0.1.2')" in content, "text ProductVersion is inconsistent")
    _assert(f"StringStruct(u'LegalCopyright', u'{COPYRIGHT_NOTICE}')" in content, "copyright holder is inconsistent")
    _assert("filevers=(0, 1, 2, 0)" in content, "numeric FileVersion is inconsistent")
    _assert("prodvers=(0, 1, 2, 0)" in content, "numeric ProductVersion is inconsistent")
    _assert("CompanyName" not in content, "CompanyName must be omitted until an identity is approved")
    _assert(not FORBIDDEN_VALUE_PATTERN.search(content), "generated VERSIONINFO contains unsafe text")
    for invalid in ("", "1", "1.2", "01.2.3", "1.2.3.4", "1.2.x", "65536.0.0"):
        try:
            parse_version(invalid)
        except ValueError:
            continue
        raise AssertionError(f"invalid version was accepted: {invalid!r}")


def validate_executable(executable: Path, expected_version: str) -> None:
    _assert(executable.is_file(), f"FuelOpt executable was not built: {executable}")
    text_version, numeric_version = parse_version(expected_version)
    pe = pefile.PE(str(executable), fast_load=False)
    try:
        resources = _resource_ids(pe)
        _assert(pefile.RESOURCE_TYPE["RT_VERSION"] in resources, "FuelOpt.exe has no RT_VERSION")
        _assert(pefile.RESOURCE_TYPE["RT_ICON"] in resources, "FuelOpt.exe has no RT_ICON")
        _assert(pefile.RESOURCE_TYPE["RT_GROUP_ICON"] in resources, "FuelOpt.exe has no RT_GROUP_ICON")
        fields = _string_fields(pe)
        for key, value in EXPECTED_TEXT_FIELDS.items():
            _assert(fields.get(key) == value, f"{key} mismatch: {fields.get(key)!r}")
        _assert(fields.get("FileVersion") == text_version, "FileVersion text mismatch")
        _assert(fields.get("ProductVersion") == text_version, "ProductVersion text mismatch")
        _assert(fields.get("LegalCopyright") == COPYRIGHT_NOTICE, "LegalCopyright mismatch")
        _assert("CompanyName" not in fields, "unapproved CompanyName is present")
        joined = "\n".join(f"{key}={value}" for key, value in fields.items())
        _assert(not FORBIDDEN_VALUE_PATTERN.search(joined), "VERSIONINFO contains unsafe text")
        fixed = pe.VS_FIXEDFILEINFO[0]
        actual_file = (
            fixed.FileVersionMS >> 16,
            fixed.FileVersionMS & 0xFFFF,
            fixed.FileVersionLS >> 16,
            fixed.FileVersionLS & 0xFFFF,
        )
        actual_product = (
            fixed.ProductVersionMS >> 16,
            fixed.ProductVersionMS & 0xFFFF,
            fixed.ProductVersionLS >> 16,
            fixed.ProductVersionLS & 0xFFFF,
        )
        _assert(actual_file == numeric_version, f"numeric FileVersion mismatch: {actual_file}")
        _assert(actual_product == numeric_version, f"numeric ProductVersion mismatch: {actual_product}")
    finally:
        pe.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--expected-version", default=DEFAULT_VERSION)
    args = parser.parse_args()
    _assert(args.source_only != (args.exe is not None), "choose exactly one of --source-only or --exe")
    validate_source()
    if args.exe is not None:
        validate_executable(args.exe.resolve(), args.expected_version)
        print(f"OK: VERSIONINFO and icon resources validated in {args.exe}")
    else:
        print("OK: VERSIONINFO source checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
