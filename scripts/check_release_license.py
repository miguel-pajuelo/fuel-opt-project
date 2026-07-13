"""Enforce the LICENSE gate used by local checks and GitHub Actions."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER_PATTERN = re.compile(
    r"\b(?:TODO|TBD|CHOOSE\s+LICENSE|LICENSE\s+PENDING)\b",
    re.IGNORECASE,
)


def validate_license(path: Path) -> list[str]:
    if not path.exists():
        return ["LICENSE does not exist"]
    if not path.is_file():
        return ["LICENSE is not a regular file"]
    content = path.read_text(encoding="utf-8", errors="replace")
    if not content.strip():
        return ["LICENSE is empty"]
    placeholders = sorted({match.group(0) for match in PLACEHOLDER_PATTERN.finditer(content)})
    if placeholders:
        return ["LICENSE contains placeholder text: " + ", ".join(placeholders)]
    return []


def evaluate_gate(mode: str, path: Path) -> tuple[bool, bool, list[str]]:
    if mode not in {"dry-run", "tag"}:
        raise ValueError(f"Unsupported release mode: {mode}")
    problems = validate_license(path)
    approved = not problems
    blocks_execution = bool(problems) and mode == "tag"
    return approved, blocks_execution, problems


def write_github_output(path: Path | None, approved: bool) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"license-approved={'true' if approved else 'false'}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("dry-run", "tag"), required=True)
    parser.add_argument("--license", type=Path, default=ROOT / "LICENSE")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    approved, blocks_execution, problems = evaluate_gate(args.mode, args.license)
    write_github_output(args.github_output, approved)
    if approved:
        print(f"LICENSE gate passed: {args.license}")
        return 0

    detail = "; ".join(problems)
    if blocks_execution:
        print(f"ERROR: tag publication is blocked: {detail}")
        return 1
    print(f"NOTICE: dry-run is allowed, but publication remains blocked: {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
