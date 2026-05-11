import os
import re
import time
import json
import math
import logging
import sys
import tempfile
import threading
import unicodedata
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urljoin

import requests
import urllib3
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

BASE_LIST_URL = "https://www.ballenoil.es/gasolineras/locations/"
MINETUR_URL = (
    "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/"
    "PreciosCarburantes/EstacionesTerrestres/"
)
GEOPORTAL_WFS_GASOLEO_A_URL = (
    "https://geoportalgasolineras.es/cgi-bin/mapserv?"
    "tipoCarburante=4&SERVICE=WFS&VERSION=1.1.0&REQUEST=GetFeature&"
    "TYPENAME=estaciones_servicio"
)
USER_AGENT = "Mozilla/5.0 (compatible; ballenoil-scraper/1.0; +https://www.ballenoil.es/)"
OUTPUT_PATH = os.path.join("data", "cache", "ballenoil_espana_combustible.txt")
MAPPING_CACHE_PATH = os.path.join("data", "cache", "ballenoil_mapping.json")
PRICES_CACHE_PATH = os.path.join("data", "cache", "ballenoil_precios.json")
DETAIL_TTL_SEC = 7 * 24 * 3600
NO_IDEESS_RETRY_SEC = 12 * 3600
PRICES_REFRESH_TTL_SEC = 6 * 3600
FAST_MINETUR_TIMEOUT_SEC = 8

# Mapa: clave interna -> (nombre MINETUR, etiqueta display)
COMBUSTIBLES: Dict[str, tuple[str, str]] = {
    "gasoleo_a":    ("Precio Gasoleo A",       "Gasóleo A (Diésel)"),
    "gasoleo_b":    ("Precio Gasoleo B",        "Gasóleo B"),
    "gasoleo_prem": ("Precio Gasoleo Premium",  "Gasóleo Premium"),
    "gasolina_95":  ("Precio Gasolina 95 E5",   "Gasolina 95 E5"),
    "gasolina_98":  ("Precio Gasolina 98 E5",   "Gasolina 98 E5"),
    "gasolina_98e10": ("Precio Gasolina 98 E10","Gasolina 98 E10"),
}

CONSUMPTION_L_PER_100KM = 5.5
L_FILL_MIN      =  5.0   # litros mínimos del barrido automático
L_FILL_MAX      = 55.0   # litros máximos del barrido automático
L_FILL_STEP     = 10.0   # paso del barrido

EPSILON_EUR = 2.0   # margen de coste para la regla epsilon

# Incertidumbre añadida a cada tramo (ida + vuelta) para compensar
# que las estimaciones de ruta de ORS no son exactas.
DISTANCE_UNCERTAINTY_KM = 0.75   # km por tramo (ajustable)

ORS_API_KEY = os.getenv("ORS_API_KEY")
ORS_MATRIX_URL = "https://api.openrouteservice.org/v2/matrix/driving-car"
TIMEOUT_HTTP = 30  # segundos; usado en todas las peticiones HTTP

# Tokens que aparecen en todas las fichas Ballenoil por el JavaScript global de
# la página. Si se usan para emparejar, muchos puntos acaban asignados al mismo
# IDEESS y a las mismas coordenadas.
GLOBAL_MATCH_TOKEN_BLOCKLIST = {
    "CASTILLO ALTO",
    "ALZIRA",
}

STREET_KEYWORDS = (
    "Calle",
    "Avenida",
    "Avda",
    "Av.",
    "C/",
    "Carretera",
    "Ctra",
    "Polígono",
    "Plaza",
    "Paseo",
    "Camino",
    "Ronda",
)

PRICE_SNAPSHOT_MIN_COUNT_RATIO = 0.55
PRICE_SNAPSHOT_MIN_COUNT_FLOOR = 50
try:
    DEFAULT_DETAIL_MAX_WORKERS = max(1, min(16, int(os.getenv("BALLENOIL_MAX_WORKERS", "6"))))
except ValueError:
    DEFAULT_DETAIL_MAX_WORKERS = 6

# Captura tokens del JS inline con el patron real:
#   item["Direccion"].includes("ALBASANZ")
#   item['Direccion'].includes('ESCOFINA')
# Tolera espacios/saltos de linea y diferencias de mayusculas/minusculas.
# ---------------------------------------------------------------------------
# Spinner de terminal (progress feedback sin alterar las tablas finales)
# ---------------------------------------------------------------------------

class Spinner:
    """
    Spinner de una sola línea que rota ◴◷◶◵ con contador de segundos.
    Uso:
        with Spinner("Obteniendo listado") as sp:
            ... trabajo ...
            sp.update("Obteniendo listado (47 gasolineras encontradas)")
        # Al salir del contexto imprime la línea final con ✓
    """
    _FRAMES = ["◴", "◷", "◶", "◵"]

    def __init__(self, msg: str, interval: float = 0.25):
        self._msg      = msg
        self._interval = interval
        self._running  = False
        self._thread   = None
        self._start    = None
        self._lock     = threading.Lock()

    def update(self, msg: str) -> None:
        with self._lock:
            self._msg = msg

    def _spin(self) -> None:
        frame_idx = 0
        while self._running:
            elapsed = int(time.time() - self._start)
            frame   = self._FRAMES[frame_idx % len(self._FRAMES)]
            with self._lock:
                msg = self._msg
            line = f"\r{frame} {elapsed}s {msg}   "
            sys.stderr.write(line)
            sys.stderr.flush()
            frame_idx += 1
            time.sleep(self._interval)

    def __enter__(self):
        self._running = True
        self._start   = time.time()
        self._thread  = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._running = False
        self._thread.join()
        elapsed = int(time.time() - self._start)
        with self._lock:
            msg = self._msg
        # Borra la línea del spinner y escribe el resultado final con ✓
        sys.stderr.write(f"\r✓ {msg}  ({elapsed}s)\n")
        sys.stderr.flush()


TOKEN_INCLUDE_RE = re.compile(
    r"""
    item
    \s*\[\s*(['"])direcci[oó]n\1\s*\]
    \s*\.\s*includes\s*\(\s*
    (?P<token>
      "(?:\\.|[^"\\])*"
      |
      '(?:\\.|[^'\\])*'
    )
    \s*\)
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)


@dataclass
class Station:
    name: str
    url: str
    address: Optional[str] = None
    match_tokens: List[str] = field(default_factory=list)  # puede haber >1


# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------

def _strip_accents(s: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(ch)
    )


def _norm(s: str) -> str:
    s = _strip_accents(s or "").upper()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _get_any(item: Dict[str, Any], *keys: str) -> str:
    """Obtiene el primer valor no vacío para una lista de claves alternativas."""
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _now_ts() -> int:
    return int(time.time())


def _today_str() -> str:
    return time.strftime("%Y-%m-%d")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _atomic_write_text(path: str, content: str) -> None:
    """Escribe texto de forma atómica (tmp + replace)."""
    dirpath = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(dirpath, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_cache_", suffix=".tmp", dir=dirpath, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _atomic_write_json(path: str, obj: Any) -> None:
    _atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))


def _load_json_file(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _save_json_file(path: str, obj: Dict[str, Any]) -> None:
    _atomic_write_json(path, obj)


def _record_has_any_price(record: Dict[str, Any]) -> bool:
    for key in COMBUSTIBLES:
        if record.get(key) is not None:
            return True
    return False


def _record_is_routable(record: Dict[str, Any]) -> bool:
    if not _record_has_any_price(record):
        return False
    return record.get("latitud") is not None and record.get("longitud") is not None


def _quality_metrics(records: List[Dict[str, Any]]) -> Dict[str, int]:
    total = 0
    with_price = 0
    routable = 0
    missing_critical = 0
    for rec in records:
        if not isinstance(rec, dict):
            continue
        total += 1
        if not rec.get("url") or not rec.get("nombre"):
            missing_critical += 1
        if _record_has_any_price(rec):
            with_price += 1
        if _record_is_routable(rec):
            routable += 1
    return {
        "total": total,
        "with_price": with_price,
        "routable": routable,
        "missing_critical": missing_critical,
    }


def _is_prices_snapshot_usable(cache: Optional[Dict[str, Any]]) -> bool:
    if not cache or not isinstance(cache, dict):
        return False
    prices = cache.get("precios_por_ideess")
    if not isinstance(prices, dict) or not prices:
        return False
    for price in prices.values():
        if not isinstance(price, dict):
            continue
        if any(price.get(k) is not None for k in COMBUSTIBLES):
            return True
    return False


def _is_prices_snapshot_degraded(
    new_cache: Dict[str, Any],
    old_cache: Optional[Dict[str, Any]],
) -> bool:
    new_prices = new_cache.get("precios_por_ideess")
    if not isinstance(new_prices, dict) or not new_prices:
        return True

    if _is_prices_snapshot_usable(old_cache):
        old_prices = old_cache.get("precios_por_ideess", {})
        prev_count = len(old_prices)
        new_count = len(new_prices)
        threshold = max(
            PRICE_SNAPSHOT_MIN_COUNT_FLOOR,
            math.floor(prev_count * PRICE_SNAPSHOT_MIN_COUNT_RATIO),
        )
        if new_count < threshold:
            logger.warning(
                "Snapshot de precios degradado: %d estaciones nuevas frente a %d previas "
                "(umbral=%d, ratio=%.2f).",
                new_count,
                prev_count,
                threshold,
                PRICE_SNAPSHOT_MIN_COUNT_RATIO,
            )
            return True

    for ideess, price in new_prices.items():
        if not ideess or not isinstance(price, dict):
            return True
    return False


def _is_final_snapshot_degraded(
    new_data: List[Dict[str, Any]],
    old_data: Optional[List[Dict[str, Any]]],
) -> bool:
    if not isinstance(new_data, list) or not new_data:
        return True

    new_m = _quality_metrics(new_data)
    if new_m["missing_critical"] > 0:
        return True
    if new_m["with_price"] == 0:
        return True

    if old_data:
        old_m = _quality_metrics(old_data)
        prev_routable = old_m["routable"]
        if prev_routable > 0:
            threshold = max(20, math.floor(prev_routable * 0.60))
            if new_m["routable"] < threshold:
                return True
    return False


def _extract_ideess(item: Dict[str, Any]) -> Optional[str]:
    if not isinstance(item, dict):
        return None

    candidate_keys = (
        "IDEESS",
        "IDEESS ",
        "IDESS",
        "ID EESS",
        "ideess",
        "idess",
    )
    for key in candidate_keys:
        if key not in item:
            continue
        value = str(item.get(key) or "").strip()
        if value:
            return value

    for key, value in item.items():
        key_norm = re.sub(r"[^A-Z0-9]", "", _strip_accents(str(key)).upper())
        if key_norm not in {"IDEESS", "IDESS", "IDEES"}:
            continue
        text = str(value or "").strip()
        if text:
            return text
    return None


def _normalize_station_mapping_entry(url: str, name: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    tokens_raw = raw.get("match_tokens")
    if not isinstance(tokens_raw, list):
        tokens_raw = raw.get("tokens")
    tokens: List[str] = []
    if isinstance(tokens_raw, list):
        for token in tokens_raw:
            text = str(token).strip()
            if text:
                tokens.append(text)

    location = _get_any(raw, "location", "ubicacion")
    final_name = _get_any(raw, "name", "nombre") or name
    ideess = str(raw.get("ideess") or "").strip() or None

    last_match_attempt = _safe_int(
        raw.get("last_match_attempt", raw.get("last_match_attempt_ts", 0))
    )
    return {
        "url": url,
        "name": final_name,
        "nombre": final_name,
        "location": location,
        "ubicacion": location,
        "match_tokens": tokens,
        "tokens": list(tokens),
        "ideess": ideess,
        "last_seen": _safe_int(raw.get("last_seen", raw.get("last_seen_ts", 0))),
        "last_detail_refresh": _safe_int(raw.get("last_detail_refresh", 0)),
        "last_match_attempt": last_match_attempt,
        "last_match_attempt_ts": last_match_attempt,
        "fail_count": _safe_int(raw.get("fail_count", 0)),
    }


def _load_mapping_cache() -> Dict[str, Any]:
    raw = _load_json_file(MAPPING_CACHE_PATH)
    result: Dict[str, Any] = {
        "_meta": {"version": 2, "updated_at": 0},
        "stations": {},
    }
    if not raw:
        return result

    source_entries: Dict[str, Any]
    if isinstance(raw.get("stations"), dict):
        source_entries = raw["stations"]
    else:
        source_entries = {
            k: v for k, v in raw.items()
            if isinstance(k, str) and k.startswith("http") and isinstance(v, dict)
        }

    normalized: Dict[str, Dict[str, Any]] = {}
    for url, entry in source_entries.items():
        normalized[url] = _normalize_station_mapping_entry(url, _get_any(entry, "name", "nombre"), entry)

    meta = raw.get("_meta")
    if not isinstance(meta, dict):
        meta = {}
    result["_meta"] = {
        "version": _safe_int(meta.get("version", 2), 2),
        "updated_at": _safe_int(meta.get("updated_at", raw.get("_scrape_ts", 0))),
    }
    result["stations"] = normalized
    return result


def _save_mapping_cache(cache: Dict[str, Any]) -> None:
    stations = cache.get("stations")
    if not isinstance(stations, dict):
        stations = {}

    now_ts = _now_ts()
    payload: Dict[str, Any] = {
        "_scrape_date": _today_str(),
        "_scrape_ts": now_ts,
        "_meta": {
            "version": 2,
            "updated_at": now_ts,
        },
    }

    for url in sorted(stations):
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        entry = stations[url]
        if not isinstance(entry, dict):
            continue
        normalized = _normalize_station_mapping_entry(url, _get_any(entry, "name", "nombre"), entry)
        payload[url] = normalized

    _save_json_file(MAPPING_CACHE_PATH, payload)


def _normalize_price_entry(raw: Dict[str, Any]) -> Dict[str, Any]:
    entry: Dict[str, Any] = {}
    lat = to_float_es(_get_any(raw, "latitud", "lat", "Latitud"))
    lon = to_float_es(_get_any(raw, "longitud", "lon", "Longitud (WGS84)"))
    entry["latitud"] = lat
    entry["longitud"] = lon
    entry["lat"] = lat
    entry["lon"] = lon
    for key, (campo_minetur, _) in COMBUSTIBLES.items():
        entry[key] = to_float_es(raw.get(key) if key in raw else raw.get(campo_minetur))
    return entry


def _load_prices_cache() -> Dict[str, Any]:
    raw = _load_json_file(PRICES_CACHE_PATH)
    normalized: Dict[str, Any] = {
        "source_fecha": None,
        "checked_at": 0,
        "precios_por_ideess": {},
    }
    if not raw:
        return normalized

    normalized["source_fecha"] = raw.get("source_fecha") or raw.get("minetur_fecha")
    normalized["checked_at"] = _safe_int(raw.get("checked_at", raw.get("_checked_at", 0)))

    prices = raw.get("precios_por_ideess")
    if not isinstance(prices, dict):
        prices = raw.get("precios")
    if isinstance(prices, dict):
        clean: Dict[str, Dict[str, Any]] = {}
        for ideess, price in prices.items():
            ideess_txt = str(ideess).strip()
            if not ideess_txt or not isinstance(price, dict):
                continue
            clean[ideess_txt] = _normalize_price_entry(price)
        normalized["precios_por_ideess"] = clean
    return normalized


def _save_prices_cache(cache: Dict[str, Any]) -> None:
    prices = cache.get("precios_por_ideess")
    if not isinstance(prices, dict):
        prices = {}

    checked_at = _safe_int(cache.get("checked_at", _now_ts()))
    source_fecha = cache.get("source_fecha") or _today_str()
    payload = {
        "source_fecha": source_fecha,
        "minetur_fecha": source_fecha,
        "checked_at": checked_at,
        "_checked_at": checked_at,
        "precios_por_ideess": prices,
        "precios": prices,  # compatibilidad con snapshots antiguos
    }
    _save_json_file(PRICES_CACHE_PATH, payload)


def _build_prices_snapshot(
    minetur_items: List[Dict[str, Any]],
    source_fecha: Optional[str] = None,
) -> Dict[str, Any]:
    prices: Dict[str, Dict[str, Any]] = {}
    detected_source_fecha = source_fecha
    for item in minetur_items:
        if detected_source_fecha is None:
            detected_source_fecha = _get_any(
                item,
                "Fecha",
                "FechaActualizacion",
                "Fecha Actualizacion",
                "FechaActualización",
            ) or None
        ideess = _extract_ideess(item)
        if not ideess:
            continue
        prices[ideess] = _normalize_price_entry(item)

    return {
        "source_fecha": detected_source_fecha or _today_str(),
        "checked_at": _now_ts(),
        "precios_por_ideess": prices,
    }


# ---------------------------------------------------------------------------
# Conversión numérica robusta
# ---------------------------------------------------------------------------

def to_float_es(num_str: Any) -> Optional[float]:
    """
    Convierte cadenas numéricas en formato español o anglosajón a float.

    Casos que maneja:
      "1,249"   -> 1.249   (precio con coma decimal española)
      "1.249"   -> 1.249   (precio con punto decimal)
      "1.249,5" -> 1249.5  (miles con punto, decimal con coma)
      "40,123456" -> 40.123456  (coordenada española)
      "40.123456" -> 40.123456  (coordenada anglosajona)
    """
    if not num_str:
        return None
    s = str(num_str).strip()
    if not s:
        return None

    has_dot = "." in s
    has_comma = "," in s

    if has_dot and has_comma:
        # Formato europeo con separador de miles: "1.249,50"  1249.50
        # El punto va antes de la coma punto=miles, coma=decimal
        if s.index(".") < s.index(","):
            s = s.replace(".", "").replace(",", ".")
        else:
            # Caso raro "1,249.50" (anglosajón): elimina coma de miles
            s = s.replace(",", "")
    elif has_comma and not has_dot:
        # Coma como decimal: "1,249" 1.249
        s = s.replace(",", ".")
    # Si solo tiene punto (o ninguno), ya es formato Python válido.

    try:
        return float(s)
    except ValueError:
        logger.warning("No se pudo convertir a float: %r", num_str)
        return None


__all__ = [name for name in globals() if not name.startswith('__')]

