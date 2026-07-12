from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class AppPaths:
    """Resolved application, resource and per-user storage locations.

    Resolving paths is deliberately side-effect free. Directories are created
    only by the operation that needs to write to them.
    """

    install_root: Path
    resource_root: Path
    user_root: Path
    data_dir: Path
    db_dir: Path
    cache_dir: Path
    logs_dir: Path
    config_path: Path
    runtime_path: Path
    legacy_db_path: Path
    legacy_snapshot_path: Path
    legacy_env_path: Path
    user_db_path: Path
    user_snapshot_path: Path
    seed_db_path: Path
    seed_db_is_immutable: bool
    installed_snapshot_path: Path
    previous_db_path: Path
    candidate_db_path: Path
    bootstrap_lock_path: Path


def _default_resource_root(module_file: Path, frozen: bool) -> Path:
    if not frozen:
        return module_file.resolve().parents[1]

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root).resolve()
    return Path(sys.executable).resolve().parent


def resolve_app_paths(
    *,
    environ: Mapping[str, str] | None = None,
    module_file: Path | None = None,
    executable: Path | None = None,
    frozen: bool | None = None,
) -> AppPaths:
    env = os.environ if environ is None else environ
    source_file = Path(__file__) if module_file is None else Path(module_file)
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    exe = Path(sys.executable) if executable is None else Path(executable)

    configured_root = env.get("FUELOPT_PROJECT_ROOT", "").strip()
    resource_root = (
        Path(configured_root).expanduser().resolve()
        if configured_root
        else _default_resource_root(source_file, is_frozen)
    )
    install_root = exe.resolve().parent if is_frozen else resource_root

    configured_user_root = env.get("FUELOPT_USER_DATA_ROOT", "").strip()
    if configured_user_root:
        user_root = Path(configured_user_root).expanduser().resolve()
    else:
        local_app_data = env.get("LOCALAPPDATA", "").strip()
        base = Path(local_app_data).expanduser() if local_app_data else Path.home() / "AppData" / "Local"
        user_root = (base / "FuelOpt").resolve()

    data_dir = user_root / "data"
    db_dir = data_dir / "db"
    cache_dir = data_dir / "cache"
    legacy_data_dir = resource_root / "data"
    packaged_seed = resource_root / "resources" / "seed" / "gas_stations.seed.sqlite"
    packaged_snapshot = resource_root / "resources" / "snapshot" / "minetur_snapshot.json"
    legacy_db = legacy_data_dir / "db" / "gas_stations.sqlite"
    legacy_snapshot = legacy_data_dir / "cache" / "minetur_snapshot.json"
    user_db = db_dir / "gas_stations.sqlite"

    return AppPaths(
        install_root=install_root,
        resource_root=resource_root,
        user_root=user_root,
        data_dir=data_dir,
        db_dir=db_dir,
        cache_dir=cache_dir,
        logs_dir=user_root / "logs",
        config_path=user_root / "config.json",
        runtime_path=user_root / "runtime.json",
        legacy_db_path=legacy_db,
        legacy_snapshot_path=legacy_snapshot,
        legacy_env_path=resource_root / ".env",
        user_db_path=user_db,
        user_snapshot_path=cache_dir / "minetur_snapshot.json",
        seed_db_path=packaged_seed if packaged_seed.is_file() else legacy_db,
        seed_db_is_immutable=packaged_seed.is_file(),
        installed_snapshot_path=packaged_snapshot if packaged_snapshot.exists() else legacy_snapshot,
        previous_db_path=db_dir / "gas_stations.previous.sqlite",
        candidate_db_path=db_dir / "gas_stations.bootstrap.next.sqlite",
        bootstrap_lock_path=user_root / "bootstrap.lock",
    )


APP_PATHS = resolve_app_paths()
