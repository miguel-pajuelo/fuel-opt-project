"""Generate the deterministic PyInstaller VERSIONINFO resource for FuelOpt."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


DEFAULT_VERSION = "0.1.2"
VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
COPYRIGHT_NOTICE = "Copyright © 2026 Miguel Pajuelo Gómez"


def parse_version(value: str) -> tuple[str, tuple[int, int, int, int]]:
    normalized = value.strip()
    match = VERSION_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError(f"Version must use MAJOR.MINOR.PATCH; received: {value!r}")
    components = tuple(int(part) for part in match.groups())
    if any(part > 65_535 for part in components):
        raise ValueError("Windows VERSIONINFO components must be between 0 and 65535")
    return normalized, (*components, 0)


def render_version_info(version: str) -> str:
    text_version, numeric_version = parse_version(version)
    numeric = ", ".join(str(part) for part in numeric_version)
    return f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({numeric}),
    prodvers=({numeric}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [
          StringStruct(u'FileDescription', u'FuelOpt'),
          StringStruct(u'FileVersion', u'{text_version}'),
          StringStruct(u'InternalName', u'FuelOpt'),
          StringStruct(u'LegalCopyright', u'{COPYRIGHT_NOTICE}'),
          StringStruct(u'OriginalFilename', u'FuelOpt.exe'),
          StringStruct(u'ProductName', u'FuelOpt'),
          StringStruct(u'ProductVersion', u'{text_version}'),
        ],
      )
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])]),
  ],
)
"""


def write_version_info(version: str, output: Path) -> None:
    content = render_version_info(version)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--resolve-default", action="store_true")
    mode.add_argument("--version")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.resolve_default:
        print(DEFAULT_VERSION)
        return 0
    if args.output is None:
        parser.error("--output is required with --version")
    try:
        write_version_info(args.version, args.output)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Generated VERSIONINFO {args.version} at {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
