from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.paths import APP_PATHS
from app.user_config import UserConfig, UserConfigError, load_user_config
from app.windows_credentials import resolve_ors_api_key

# PROJECT_ROOT remains the immutable code/resource root during Patch 2. Active
# database migration to APP_PATHS.user_db_path belongs to Patch 3.
PROJECT_ROOT = APP_PATHS.resource_root
DATA_DIR = APP_PATHS.data_dir
CACHE_DIR = APP_PATHS.cache_dir
DB_DIR = APP_PATHS.db_dir
DEFAULT_DB_PATH = APP_PATHS.user_db_path
DEFAULT_MINETUR_SNAPSHOT_PATH = APP_PATHS.user_snapshot_path
DEFAULT_ENV_PATH = APP_PATHS.legacy_env_path
USER_DATA_DIR = APP_PATHS.user_root
USER_CONFIG_PATH = APP_PATHS.config_path
USER_LOG_DIR = APP_PATHS.logs_dir


def load_dotenv(path: Path = DEFAULT_ENV_PATH) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    db_path: Path = DEFAULT_DB_PATH
    minetur_snapshot_path: Path = DEFAULT_MINETUR_SNAPSHOT_PATH
    ors_api_key: str | None = None
    default_consumption_l_100km: float = 5.5
    max_route_candidates: int = 75
    default_prefilter_radius_km: float = 40.0
    local_search_radius_km: float = 50.0
    corridor_radius_km: float = 10.0
    max_search_extent_km: float = 150.0
    default_optimization_mode: str = "economic"
    route_detour_factor: float = 1.25
    same_place_threshold_km: float = 1.0
    default_brand_filter: list[str] | None = None
    max_brands_per_request: int = 10
    admin_token: str | None = None
    enable_api_docs: bool = False
    # Only trust X-Forwarded-For when running behind a known/trusted reverse
    # proxy (e.g. a public PaaS edge). Off by default so local/untrusted
    # deployments cannot be fooled by spoofed forwarded headers.
    trust_proxy_headers: bool = False
    # Log the raw client IP in access logs. Off by default to avoid storing PII;
    # when off, a coarsely anonymized IP is logged instead.
    log_client_ip: bool = False
    refresh_interval: str = "4h"


def load_settings() -> Settings:
    load_dotenv()
    try:
        user_config = load_user_config(USER_CONFIG_PATH)
    except UserConfigError:
        # A corrupt user config is never overwritten implicitly. Patch 4 will
        # expose this state through --show-settings/--configure-refresh.
        user_config = UserConfig()
    return Settings(
        db_path=Path(os.getenv("GAS_DB_PATH", DEFAULT_DB_PATH)),
        minetur_snapshot_path=Path(os.getenv("MINETUR_SNAPSHOT_PATH", DEFAULT_MINETUR_SNAPSHOT_PATH)),
        ors_api_key=resolve_ors_api_key(),
        default_consumption_l_100km=float(os.getenv("CONSUMPTION_L_100KM", "5.5")),
        max_route_candidates=int(os.getenv("MAX_ROUTE_CANDIDATES", "75")),
        default_prefilter_radius_km=float(os.getenv("PREFILTER_RADIUS_KM", "40")),
        local_search_radius_km=float(os.getenv("LOCAL_SEARCH_RADIUS_KM", "50")),
        corridor_radius_km=float(os.getenv("CORRIDOR_RADIUS_KM", "10")),
        max_search_extent_km=float(os.getenv("MAX_SEARCH_EXTENT_KM", "150")),
        default_optimization_mode=os.getenv("OPTIMIZATION_MODE", "economic"),
        route_detour_factor=float(os.getenv("ROUTE_DETOUR_FACTOR", "1.25")),
        same_place_threshold_km=float(os.getenv("SAME_PLACE_THRESHOLD_KM", "1.0")),
        default_brand_filter=None,
        max_brands_per_request=int(os.getenv("MAX_BRANDS_PER_REQUEST", "10")),
        admin_token=os.getenv("FUELOPT_ADMIN_TOKEN"),
        enable_api_docs=env_flag("FUELOPT_ENABLE_API_DOCS", False),
        trust_proxy_headers=env_flag("FUELOPT_TRUST_PROXY_HEADERS", False),
        log_client_ip=env_flag("FUELOPT_LOG_CLIENT_IP", False),
        refresh_interval=user_config.refresh_interval,
    )


def require_ors_api_key(settings: Settings | None = None) -> str:
    cfg = settings or load_settings()
    if not cfg.ors_api_key:
        raise RuntimeError("ORS_API_KEY is required for geocoding or road-route matrices.")
    return cfg.ors_api_key
