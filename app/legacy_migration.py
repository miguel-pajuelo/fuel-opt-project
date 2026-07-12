from __future__ import annotations

import hmac
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

from app.paths import AppPaths
from app.user_config import UserConfig, load_user_config, save_user_config
from app.windows_credentials import (
    ORS_CREDENTIAL_TARGET,
    CredentialStore,
    CredentialStoreError,
    default_credential_store,
)


_PLACEHOLDERS = {"", "replace-me", "changeme"}


@dataclass(frozen=True)
class CredentialMigrationResult:
    status: str
    legacy_root: Path | None = None


def find_legacy_root(
    paths: AppPaths,
    *,
    explicit_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path | None:
    env = os.environ if environ is None else environ
    candidates: list[Path] = []
    if explicit_root is not None:
        candidates.append(Path(explicit_root))
    configured = env.get("FUELOPT_LEGACY_ROOT", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            paths.install_root,
            paths.install_root / "FuelOptApp",
            paths.resource_root,
        ]
    )

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen or resolved == paths.user_root.resolve():
            continue
        seen.add(resolved)
        if (resolved / ".env").is_file() or (resolved / "data" / "db" / "gas_stations.sqlite").is_file():
            return resolved
    return None


def read_dotenv_value(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        candidate, value = line.split("=", 1)
        if candidate.strip() == key:
            return value.strip().strip('"').strip("'")
    return None


def _usable_legacy_key(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    secret = value.strip()
    if secret.lower() in _PLACEHOLDERS or secret.startswith("<"):
        return None
    return secret


def migrate_legacy_ors_credential(
    paths: AppPaths,
    *,
    explicit_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    store: CredentialStore | None = None,
) -> CredentialMigrationResult:
    """Import ORS_API_KEY without modifying the legacy .env file.

    This operation is explicit rather than an import-time side effect. Callers
    may keep using the legacy value in memory if ``status`` is ``write_failed``.
    """

    active_store = store or default_credential_store()
    try:
        if active_store.read(ORS_CREDENTIAL_TARGET):
            return CredentialMigrationResult("already_present")
    except CredentialStoreError:
        return CredentialMigrationResult("store_unavailable")

    legacy_root = find_legacy_root(paths, explicit_root=explicit_root, environ=environ)
    if legacy_root is None:
        return CredentialMigrationResult("legacy_root_not_found")
    secret = _usable_legacy_key(read_dotenv_value(legacy_root / ".env", "ORS_API_KEY"))
    if not secret:
        return CredentialMigrationResult("legacy_key_not_found", legacy_root)

    try:
        active_store.write(ORS_CREDENTIAL_TARGET, secret)
        imported = active_store.read(ORS_CREDENTIAL_TARGET)
    except CredentialStoreError:
        return CredentialMigrationResult("write_failed", legacy_root)
    if not isinstance(imported, str) or not hmac.compare_digest(imported, secret):
        try:
            active_store.delete(ORS_CREDENTIAL_TARGET)
        except CredentialStoreError:
            pass
        return CredentialMigrationResult("verification_failed", legacy_root)

    try:
        config = load_user_config(paths.config_path)
        save_user_config(paths.config_path, replace(config, ors_credential_migrated=True))
    except Exception:
        try:
            active_store.delete(ORS_CREDENTIAL_TARGET)
        except CredentialStoreError:
            pass
        return CredentialMigrationResult("config_write_failed", legacy_root)
    return CredentialMigrationResult("migrated", legacy_root)
