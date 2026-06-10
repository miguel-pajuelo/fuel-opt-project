"""H7 database-artifact guardrail (reporting-only, non-destructive).

The active catalog DB (data/db/gas_stations.sqlite) is intentionally tracked in
git so the local demo boots with zero configuration (see
docs/DATABASE_ARTIFACT_POLICY.md). This check does NOT delete, rewrite, or
modify the DB. It only reports its tracked status / size and fails on a very
conservative ceiling, to catch an accidentally committed oversized binary.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_REL = "data/db/gas_stations.sqlite"

# Soft threshold: print a warning (does not fail) above this.
SOFT_WARN_MB = 25.0
# Hard ceiling: only fail far above the expected ~20 MB, so normal refreshes
# never trip it but a catastrophic accidental commit (e.g. a WAL-bloated or
# wrong file) does.
HARD_FAIL_MB = 64.0


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _git(*args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True)
    except FileNotFoundError:
        return None


def _is_tracked() -> bool | None:
    result = _git("ls-files", DB_REL)
    if result is None or result.returncode == 128:
        return None
    return bool(result.stdout.strip())


def _is_modified() -> bool | None:
    result = _git("status", "--porcelain", "--", DB_REL)
    if result is None or result.returncode == 128:
        return None
    return bool(result.stdout.strip())


def test_db_artifact_report() -> None:
    path = ROOT / DB_REL
    exists = path.exists()
    size_mb = round(path.stat().st_size / 1048576, 2) if exists else None
    tracked = _is_tracked()
    modified = _is_modified()

    print(f"  db: {DB_REL}")
    print(f"  exists={exists} size_mb={size_mb} tracked={tracked} modified={modified}")

    if modified:
        print(
            "  WARNING: the tracked DB is modified in the working tree. Avoid "
            "committing it (large binary diff). The local refresh mutates it; "
            "commit it only on a deliberate dataset update."
        )
    if size_mb is not None and size_mb > SOFT_WARN_MB:
        print(
            f"  WARNING: DB size {size_mb} MB exceeds the soft threshold "
            f"{SOFT_WARN_MB} MB. Consider the migration path in "
            f"docs/DATABASE_ARTIFACT_POLICY.md."
        )

    # Conservative hard ceiling only.
    if exists:
        _assert(
            size_mb is not None and size_mb <= HARD_FAIL_MB,
            f"DB artifact {size_mb} MB exceeds the hard ceiling {HARD_FAIL_MB} MB; "
            "do not commit an oversized database binary.",
        )


def run() -> None:
    test_db_artifact_report()
    print("OK: database artifact checks passed")


if __name__ == "__main__":
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    run()
