from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(os.getenv("FUELOPT_PROJECT_ROOT") or Path(__file__).resolve().parents[1]).resolve()
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
DB_DIR = DATA_DIR / "db"
DEFAULT_DB_PATH = DB_DIR / "gas_stations.sqlite"
DEFAULT_MINETUR_SNAPSHOT_PATH = CACHE_DIR / "minetur_snapshot.json"
DEFAULT_BALLENOIL_RESULT_PATH = CACHE_DIR / "ballenoil_espana_combustible.txt"
DEFAULT_BALLENOIL_PRICES_PATH = CACHE_DIR / "ballenoil_precios.json"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


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
    ballenoil_result_path: Path = DEFAULT_BALLENOIL_RESULT_PATH
    ballenoil_prices_path: Path = DEFAULT_BALLENOIL_PRICES_PATH
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


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        db_path=Path(os.getenv("GAS_DB_PATH", DEFAULT_DB_PATH)),
        minetur_snapshot_path=Path(os.getenv("MINETUR_SNAPSHOT_PATH", DEFAULT_MINETUR_SNAPSHOT_PATH)),
        ballenoil_result_path=Path(os.getenv("BALLENOIL_RESULT_PATH", DEFAULT_BALLENOIL_RESULT_PATH)),
        ballenoil_prices_path=Path(os.getenv("BALLENOIL_PRICES_PATH", DEFAULT_BALLENOIL_PRICES_PATH)),
        ors_api_key=os.getenv("ORS_API_KEY"),
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
    )


def require_ors_api_key(settings: Settings | None = None) -> str:
    cfg = settings or load_settings()
    if not cfg.ors_api_key:
        raise RuntimeError("ORS_API_KEY is required for geocoding or road-route matrices.")
    return cfg.ors_api_key
