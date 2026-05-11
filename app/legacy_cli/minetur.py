from .ballenoil import *
# ---------------------------------------------------------------------------
# API MINETUR
# ---------------------------------------------------------------------------

class MiniturError(RuntimeError):
    """Se lanza cuando no se pueden obtener datos de MINETUR tras todos los reintentos."""


# Headers que imitan un navegador real. El error 10054 (Connection Reset) que
# devuelve MINETUR suele deberse a que el servidor IIS rechaza peticiones sin
# los headers mínimos de un navegador (especialmente User-Agent y Accept).
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    # Evita br para no depender de soporte Brotli del entorno.
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Referer": "https://geoportalgasolineras.es/",
    "Origin": "https://geoportalgasolineras.es",
}


def _parse_minetur_response(data: Any, attempt: int) -> Optional[List[Dict[str, Any]]]:
    """Valida y extrae la lista de estaciones del JSON de MINETUR."""
    if not isinstance(data, dict):
        logger.warning("MINETUR formato inesperado en intento %d", attempt)
        return None
    items = data.get("ListaEESSPrecio", [])
    if not items:
        logger.warning("MINETUR devolvió lista vacía en intento %d", attempt)
        return None
    return items


def _parse_geoportal_wfs_response(
    xml_bytes: bytes,
    attempt: int,
) -> Optional[List[Dict[str, Any]]]:
    """Convierte la respuesta WFS de Geoportal al formato esperado de MINETUR."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        logger.warning("Geoportal WFS XML inválido en intento %d", attempt)
        return None

    ns = {"ms": "http://mapserver.gis.umn.edu/mapserver"}
    features = root.findall(".//ms:estaciones_servicio", ns)
    if not features:
        logger.warning("Geoportal WFS sin features en intento %d", attempt)
        return None

    items: List[Dict[str, Any]] = []
    for feat in features:
        precio_raw = (feat.findtext("ms:Precio", "", ns) or "").strip()
        item = {
            "Rótulo": (feat.findtext("ms:Rotulo", "", ns) or "").strip(),
            "Dirección": (feat.findtext("ms:Direccion", "", ns) or "").strip(),
            "C.P.": (feat.findtext("ms:CPostal", "", ns) or "").strip(),
            "Municipio": (feat.findtext("ms:Localidad", "", ns) or "").strip(),
            "Latitud": (feat.findtext("ms:CoordenadaY_dec", "", ns) or "").strip(),
            "Longitud (WGS84)": (feat.findtext("ms:CoordenadaX_dec", "", ns) or "").strip(),
            # El WFS usado aquí está filtrado a Gasóleo A; no se deben simular
            # precios de otros combustibles con el mismo valor.
            "Precio Gasoleo A":       precio_raw,
            "Precio Gasoleo B":       "",
            "Precio Gasoleo Premium": "",
            "Precio Gasolina 95 E5":  "",
            "Precio Gasolina 98 E5":  "",
            "Precio Gasolina 98 E10": "",
        }
        if item["Dirección"]:
            items.append(item)

    if not items:
        logger.warning("Geoportal WFS devolvió 0 estaciones en intento %d", attempt)
        return None

    return items


def _fetch_geoportal_wfs_data(
    retries: int = 3,
    backoff: float = 4.0,
) -> List[Dict[str, Any]]:
    """Fallback de MINETUR usando WFS público de Geoportal (Gasóleo A)."""
    last_exc: Exception = RuntimeError("Sin intentos en Geoportal WFS")
    insecure_warning_disabled = False

    with requests.Session() as geo_session:
        geo_session.headers.update({
            "User-Agent": BROWSER_HEADERS["User-Agent"],
            "Accept": "application/xml, text/xml;q=0.9, */*;q=0.8",
            "Accept-Language": BROWSER_HEADERS["Accept-Language"],
            "Connection": "keep-alive",
            "Referer": BROWSER_HEADERS["Referer"],
            "Origin": BROWSER_HEADERS["Origin"],
        })

        for verify_tls in (True, False):
            for attempt in range(1, retries + 1):
                try:
                    if not verify_tls and not insecure_warning_disabled:
                        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                        insecure_warning_disabled = True

                    r = geo_session.get(
                        GEOPORTAL_WFS_GASOLEO_A_URL,
                        timeout=60,
                        verify=verify_tls,
                    )
                    r.raise_for_status()

                    items = _parse_geoportal_wfs_response(r.content, attempt)
                    if items is None:
                        last_exc = ValueError("Geoportal WFS sin datos válidos")
                        time.sleep(backoff)
                        continue

                    logger.info(
                        "Geoportal WFS: %d estaciones descargadas (intento %d, verify_tls=%s)",
                        len(items),
                        attempt,
                        verify_tls,
                    )
                    return items
                except requests.exceptions.SSLError as exc:
                    last_exc = exc
                    if verify_tls:
                        logger.warning(
                            "Geoportal WFS SSL falló con verificación. Reintentando sin verificar certificado."
                        )
                        break
                    wait = backoff * attempt
                    logger.warning(
                        "Geoportal WFS intento %d/%d falló (%s). Esperando %.0fs…",
                        attempt, retries, exc, wait,
                    )
                    time.sleep(wait)
                except requests.RequestException as exc:
                    last_exc = exc
                    wait = backoff * attempt
                    logger.warning(
                        "Geoportal WFS intento %d/%d falló (%s). Esperando %.0fs…",
                        attempt, retries, exc, wait,
                    )
                    time.sleep(wait)

    raise MiniturError(
        f"Fallback Geoportal WFS agotado tras {retries} intentos por modo TLS. "
        f"Último error: {last_exc}"
    ) from last_exc


def fetch_minetur_data(
    retries: int = 4,
    backoff: float = 5.0,
) -> List[Dict[str, Any]]:
    """
    Descarga el catálogo de estaciones de la CCAA de Madrid (código 13).

    El error ConnectionResetError(10054) que devuelve el servidor IIS de MINETUR
    ocurre cuando la petición no lleva los headers mínimos de un navegador real.
    Esta función:
      - Usa headers de Chrome para evitar el bloqueo.
      - Crea una sesión HTTP separada (dedicada) para no contaminar los headers
        del scraper principal.
      - Reintenta `retries` veces con espera lineal (no exponencial, para no
        esperar 81s si el servidor simplemente está ocupado).
      - Lanza MiniturError si todos los intentos fallan.
    """
    # Sesión dedicada para MINETUR con headers de navegador.
    # Se restringe Accept-Encoding a gzip/deflate para evitar respuestas
    # Brotli ("br") no decodificables en algunos entornos.
    minetur_session = requests.Session()
    minetur_session.headers.update(BROWSER_HEADERS)

    last_exc: Exception = RuntimeError("Sin intentos")

    for attempt in range(1, retries + 1):
        try:
            r = minetur_session.get(MINETUR_URL, timeout=TIMEOUT_HTTP)
            r.raise_for_status()
            try:
                data = r.json()
            except ValueError:
                # Fallback robusto ante respuestas con BOM/encoding raro.
                data = json.loads(r.content.decode("utf-8-sig", errors="replace"))
        except requests.RequestException as exc:
            last_exc = exc
            wait = backoff * attempt  # espera lineal: 5s, 10s, 15s, 20s
            logger.warning(
                "MINETUR intento %d/%d falló (%s). Esperando %.0fs…",
                attempt, retries, exc, wait,
            )
            time.sleep(wait)
            continue
        except (ValueError, json.JSONDecodeError) as exc:
            last_exc = exc
            logger.warning("MINETUR respuesta no-JSON en intento %d/%d", attempt, retries)
            time.sleep(backoff)
            continue

        items = _parse_minetur_response(data, attempt)
        if items is None:
            last_exc = ValueError("Lista vacía o formato inesperado")
            time.sleep(backoff)
            continue

        logger.info("MINETUR: %d estaciones descargadas (intento %d)", len(items), attempt)
        minetur_session.close()
        return items

    minetur_session.close()

    logger.warning(
        "MINETUR REST no disponible tras %d intentos. Activando fallback Geoportal WFS.",
        retries,
    )
    try:
        return _fetch_geoportal_wfs_data(retries=max(2, retries - 1), backoff=backoff)
    except MiniturError as fallback_exc:
        raise MiniturError(
            f"No se pudo obtener datos de MINETUR tras {retries} intentos. "
            f"Último error REST: {last_exc}. Error fallback: {fallback_exc}"
        ) from fallback_exc


def _fetch_minetur_fast(timeout: int = FAST_MINETUR_TIMEOUT_SEC) -> List[Dict[str, Any]]:
    """
    Intento rápido de refresco de MINETUR:
    - 1 intento
    - timeout corto
    - sin fallback largo
    """
    minetur_session = requests.Session()
    minetur_session.headers.update(BROWSER_HEADERS)
    try:
        r = minetur_session.get(MINETUR_URL, timeout=timeout)
        r.raise_for_status()
        try:
            data = r.json()
        except ValueError:
            data = json.loads(r.content.decode("utf-8-sig", errors="replace"))
        items = _parse_minetur_response(data, attempt=1)
        if items is None:
            raise MiniturError("MINETUR fast devolvió respuesta vacía o inválida")
        logger.info("MINETUR fast: %d estaciones descargadas", len(items))
        return items
    except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
        raise MiniturError(f"MINETUR fast falló: {exc}") from exc
    finally:
        minetur_session.close()


# ---------------------------------------------------------------------------
# Emparejamiento Ballenoil ↔ MINETUR
# ---------------------------------------------------------------------------

def match_station_to_minetur(
    station: Station,
    minetur_items: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Localiza el registro MINETUR correspondiente a una estación Ballenoil.

    Estrategia (en orden de preferencia):
    1. Token exacto en la dirección MINETUR (método que usa la propia web).
    2. Fuzzy match por dirección completa (fallback).
    """
    def _score_candidate(cand: Dict[str, Any]) -> float:
        if not station.address:
            return 0.0
        return _similar(station.address, cand["fuzzy_text"])

    index = _get_minetur_match_index(minetur_items)
    candidates = index["candidates"]
    if not candidates:
        return None

    station_ideess = str(getattr(station, "ideess", "") or "").strip()
    if station_ideess:
        by_ideess = index["by_ideess"]
        hit = by_ideess.get(station_ideess)
        if hit is not None:
            return hit["item"]

    # 1) Match por token(s)
    if station.match_tokens:
        tok_candidates: List[Dict[str, Any]] = []
        seen: set[int] = set()
        for tok in station.match_tokens:
            tok_norm = _norm(tok)
            if not tok_norm:
                continue
            cand_list = index["token_cache"].get(tok_norm)
            if cand_list is None:
                with index["token_lock"]:
                    cand_list = index["token_cache"].get(tok_norm)
                    if cand_list is None:
                        cand_list = [
                            c for c in candidates
                            if tok_norm in c["direccion_norm"]
                        ]
                        index["token_cache"][tok_norm] = cand_list
            for cand in cand_list:
                cand_id = id(cand["item"])
                if cand_id in seen:
                    continue
                seen.add(cand_id)
                tok_candidates.append(cand)

        if len(tok_candidates) > 1:
            if not station.address:
                logger.warning(
                    "Match ambiguo para '%s': %d candidatos por token y sin dirección.",
                    station.name, len(tok_candidates),
                )
                return None
            tok_candidates.sort(key=_score_candidate, reverse=True)
            best_score = _score_candidate(tok_candidates[0])
            second_score = _score_candidate(tok_candidates[1])
            if best_score >= 0.60 and best_score - second_score >= 0.04:
                return tok_candidates[0]["item"]
            logger.warning(
                "Match ambiguo para '%s': mejor score=%.2f, segundo=%.2f.",
                station.name, best_score, second_score,
            )
            return None
        if len(tok_candidates) == 1:
            return tok_candidates[0]["item"]
        # 0 candidatos por token continúa con fuzzy

    # 2) Fuzzy match por dirección
    if station.address:
        best = max(candidates, key=_score_candidate)
        best_score = _score_candidate(best)
        if best_score >= 0.55:
            logger.debug(
                "Fuzzy match para '%s': score=%.2f %s",
                station.name, best_score, best["direccion"],
            )
            return best["item"]
        logger.warning(
            "No se encontró match MINETUR para '%s' (mejor score=%.2f)",
            station.name, best_score,
        )

    return None


_MATCH_INDEX_LOCK = threading.Lock()
_MATCH_INDEX_STATE: Dict[str, Any] = {
    "signature": None,
    "index": None,
}


def _build_minetur_match_index(minetur_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    candidates: List[Dict[str, Any]] = []
    by_ideess: Dict[str, Dict[str, Any]] = {}

    for item in minetur_items:
        if _get_any(item, "Rótulo").upper() != "BALLENOIL":
            continue
        direccion = _get_any(item, "Dirección", "dirección")
        cp = _get_any(item, "C.P.")
        municipio = _get_any(item, "Municipio")
        fuzzy_text = f"{direccion} {cp} {municipio}".strip()
        cand = {
            "item": item,
            "ideess": _extract_ideess(item),
            "direccion": direccion,
            "direccion_norm": _norm(direccion),
            "fuzzy_text": fuzzy_text,
        }
        candidates.append(cand)
        if cand["ideess"]:
            by_ideess[cand["ideess"]] = cand

    if not candidates:
        logger.warning("No se encontraron estaciones BALLENOIL en MINETUR")

    return {
        "candidates": candidates,
        "by_ideess": by_ideess,
        "token_cache": {},
        "token_lock": threading.Lock(),
    }


def _minetur_items_signature(minetur_items: List[Dict[str, Any]]) -> Tuple[Tuple[str, str, str, str], ...]:
    return tuple(
        (
            _extract_ideess(item) or "",
            _get_any(item, "Rótulo").upper(),
            _norm(_get_any(item, "Dirección", "dirección")),
            _get_any(item, "C.P."),
        )
        for item in minetur_items
    )


def _get_minetur_match_index(minetur_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    signature = _minetur_items_signature(minetur_items)

    state = _MATCH_INDEX_STATE
    if state["signature"] == signature and state["index"] is not None:
        return state["index"]

    with _MATCH_INDEX_LOCK:
        if state["signature"] == signature and state["index"] is not None:
            return state["index"]
        index = _build_minetur_match_index(minetur_items)
        state["signature"] = signature
        state["index"] = index
        return index


__all__ = [name for name in globals() if not name.startswith('__')]

