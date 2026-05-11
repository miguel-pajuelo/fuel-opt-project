from .scraper import *
# ---------------------------------------------------------------------------
# Distancias reales por carretera (OpenRouteService Matrix API)
# ---------------------------------------------------------------------------

def _ors_matrix(
    sources: List[tuple[float, float]],
    destinations: List[tuple[float, float]],
    session: requests.Session,
    retries: int = 3,
    backoff: float = 3.0,
) -> Optional[List[List[Optional[float]]]]:
    """
    Llama a la Matrix API de OpenRouteService para obtener distancias en km.

    ORS espera coordenadas en formato [lon, lat].
    Devuelve distances[i][j] en km, o None si falla.
    """
    api_key = os.getenv("ORS_API_KEY") or ORS_API_KEY
    if not api_key:
        raise ValueError(
            "Falta ORS_API_KEY en variables de entorno. Configúrala antes de calcular rutas."
        )

    # ORS espera [lon, lat]
    locations = [[lon, lat] for lat, lon in (sources + destinations)]
    src_indices = list(range(len(sources)))
    dst_indices = list(range(len(sources), len(sources) + len(destinations)))

    payload = {
        "locations":    locations,
        "sources":      src_indices,
        "destinations": dst_indices,
        "metrics":      ["distance"],
        "units":        "km",
    }
    headers = {
        "Authorization": api_key,
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }

    last_exc: Exception = RuntimeError("Sin intentos ORS")
    for attempt in range(1, retries + 1):
        try:
            r = session.post(ORS_MATRIX_URL, json=payload, headers=headers, timeout=TIMEOUT_HTTP)
            r.raise_for_status()
            data = r.json()
            matrix = data.get("distances")
            if not matrix:
                logger.warning("ORS Matrix respuesta sin 'distances' en intento %d", attempt)
                last_exc = ValueError("ORS sin campo 'distances'")
                time.sleep(backoff)
                continue
            return matrix  # ya viene en km
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            body = exc.response.text[:300] if exc.response is not None else ""
            logger.warning(
                "ORS Matrix HTTP %s en intento %d/%d: %s",
                status, attempt, retries, body,
            )
            last_exc = exc
            if status in (401, 403):
                raise ValueError(
                    f"ORS rechazó la API key (HTTP {status}). "
                    "Comprueba ORS_API_KEY."
                ) from exc
            if attempt == retries:
                break
            time.sleep(backoff * attempt)
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "ORS Matrix intento %d/%d falló (%s). Esperando %.0fs…",
                attempt, retries, exc, backoff * attempt,
            )
            time.sleep(backoff * attempt)

    logger.error("ORS Matrix agotó %d intentos. Último error: %s", retries, last_exc)
    return None

__all__ = [name for name in globals() if not name.startswith('__')]

