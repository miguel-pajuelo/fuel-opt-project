"""Fail fast when the active build environment differs from pinned inputs."""
from __future__ import annotations

import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENT_RE = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^\s;]+)$")


def pinned_requirements() -> list[tuple[str, str]]:
    requirements: list[tuple[str, str]] = []
    for name in ("requirements-runtime.lock", "requirements-build.txt"):
        for raw_line in (ROOT / name).read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            match = REQUIREMENT_RE.fullmatch(line)
            if match is None:
                raise RuntimeError(f"unsupported build requirement: {line}")
            requirements.append((match.group(1), match.group(2)))
    return requirements


def main() -> int:
    errors: list[str] = []
    if sys.version_info[:3] != (3, 12, 10):
        errors.append(f"Python: installed {sys.version.split()[0]}, expected 3.12.10")
    for distribution, expected in pinned_requirements():
        try:
            installed = version(distribution)
        except PackageNotFoundError:
            errors.append(f"{distribution}: missing (expected {expected})")
            continue
        if installed != expected:
            errors.append(f"{distribution}: installed {installed}, expected {expected}")
    if errors:
        print("Build environment does not match pinned requirements:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("OK: build environment matches pinned requirements")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
