from .minetur import *
# ---------------------------------------------------------------------------
# función principal
# ---------------------------------------------------------------------------

def scrape_ballenoil_diesel(
    max_pages: int = 50,
    polite_sleep: float = 0.3,
    max_workers: int = DEFAULT_DETAIL_MAX_WORKERS,
) -> List[Dict[str, Any]]:
    """
    Devuelve una lista de todas las estaciones Ballenoil de España
    con su precio de Gasóleo A (€/litro), coordenadas y URL.
    """
    today = _today_str()
    cached_result = _read_cached_data(OUTPUT_PATH)
    previous_snapshot: List[Dict[str, Any]] = []
    if cached_result is not None:
        _, cached_data = cached_result
        if isinstance(cached_data, list):
            previous_snapshot = cached_data
        if cached_result[0] == today and not _is_final_snapshot_degraded(cached_data, None):
            logger.info(
                "Caché final de hoy encontrada (%d estaciones). Warm start sin requests.",
                len(cached_data),
            )
            return cached_data

    previous_by_url = {
        rec["url"]: rec
        for rec in previous_snapshot
        if isinstance(rec, dict) and rec.get("url")
    }

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    # 1) Recorre las páginas del listado (solo cuando no hay warm cache de hoy)
    stations: List[Station] = []
    seen_urls: set[str] = set()

    try:
        with Spinner("Obteniendo listado") as sp:
            for page in range(1, max_pages + 1):
                url = (
                    BASE_LIST_URL
                    if page == 1
                    else f"{BASE_LIST_URL}?_page={page}&sort=post_title"
                )
                try:
                    html = fetch_html(session, url)
                except requests.RequestException as exc:
                    logger.error("No se pudo descargar la página %d: %s", page, exc)
                    break

                page_stations = parse_station_index(html, BASE_LIST_URL)
                new = [s for s in page_stations if s.url not in seen_urls]
                if not new:
                    break

                stations.extend(new)
                for s in new:
                    seen_urls.add(s.url)

                sp.update(f"Obteniendo listado ({len(stations)} gasolineras encontradas)")
                if polite_sleep > 0:
                    time.sleep(polite_sleep)
            sp.update(f"Obteniendo listado ({len(stations)} gasolineras encontradas)")
    finally:
        session.close()

    if not stations:
        if previous_snapshot:
            logger.warning("No se obtuvo listado actual. Usando último snapshot disponible.")
            return previous_snapshot
        logger.error("No se obtuvo listado de estaciones y no hay caché previa.")
        return []

    now_ts = _now_ts()
    mapping_cache = _load_mapping_cache()
    mapping_by_url = mapping_cache.get("stations")
    if not isinstance(mapping_by_url, dict):
        mapping_by_url = {}
        mapping_cache["stations"] = mapping_by_url

    by_url_station = {st.url: st for st in stations}
    pending_detail: List[Station] = []
    pending_match_urls: set[str] = set()

    # 2) Reconciliación con caché estable por URL
    for st in stations:
        entry_raw = mapping_by_url.get(st.url)
        if not isinstance(entry_raw, dict):
            entry_raw = {}
        entry = _normalize_station_mapping_entry(st.url, st.name, entry_raw)
        entry["name"] = st.name
        entry["nombre"] = st.name
        entry["url"] = st.url
        entry["last_seen"] = now_ts

        st.address = entry.get("location") or None
        st.match_tokens = entry.get("match_tokens") or []
        setattr(st, "ideess", entry.get("ideess"))

        needs_detail_refresh = (
            not st.address
            or not st.match_tokens
            or now_ts - _safe_int(entry.get("last_detail_refresh", 0)) >= DETAIL_TTL_SEC
        )
        if needs_detail_refresh:
            pending_detail.append(st)

        ideess = str(entry.get("ideess") or "").strip()
        last_match_attempt = _safe_int(entry.get("last_match_attempt", 0))
        if not ideess and now_ts - last_match_attempt >= NO_IDEESS_RETRY_SEC:
            pending_match_urls.add(st.url)

        mapping_by_url[st.url] = entry

    logger.info(
        "Total: %d | Detalle en caché: %d | Detalle a refrescar: %d",
        len(stations),
        len(stations) - len(pending_detail),
        len(pending_detail),
    )

    # 3) Scrape incremental de fichas estables
    if pending_detail:
        worker_local = threading.local()

        def _get_worker_session() -> requests.Session:
            s = getattr(worker_local, "session", None)
            if s is None:
                s = requests.Session()
                s.headers.update({"User-Agent": USER_AGENT})
                worker_local.session = s
            return s

        def _process_detail(st: Station) -> Optional[Dict[str, Any]]:
            try:
                html = fetch_html(_get_worker_session(), st.url, retries=2, backoff=1.5)
            except requests.RequestException as exc:
                logger.warning("Error descargando ficha de '%s': %s", st.name, exc)
                return None
            detail = parse_station_detail(html)
            return {
                "url": st.url,
                "address": detail.get("address"),
                "tokens": detail.get("tokens") or [],
            }

        refreshed = 0
        with Spinner(f"Refrescando fichas ({len(pending_detail)} pendientes)") as sp:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_process_detail, st): st.url for st in pending_detail}
                done = 0
                for future in as_completed(futures):
                    url = futures[future]
                    st = by_url_station[url]
                    entry = mapping_by_url[url]
                    done += 1
                    try:
                        detail = future.result()
                    except Exception as exc:
                        logger.error("Error inesperado refrescando '%s': %s", st.name, exc)
                        detail = None

                    if detail:
                        new_address = str(detail.get("address") or "").strip()
                        new_tokens = [str(t).strip() for t in detail.get("tokens", []) if str(t).strip()]
                        if new_address:
                            entry["location"] = new_address
                            entry["ubicacion"] = new_address
                            st.address = new_address
                        if new_tokens:
                            entry["match_tokens"] = new_tokens
                            entry["tokens"] = list(new_tokens)
                            st.match_tokens = new_tokens
                        entry["last_detail_refresh"] = now_ts
                        entry["fail_count"] = max(0, _safe_int(entry.get("fail_count", 0)) - 1)
                        refreshed += 1
                    else:
                        entry["fail_count"] = _safe_int(entry.get("fail_count", 0)) + 1

                    mapping_by_url[url] = entry
                    sp.update(f"Refrescando fichas ({done}/{len(pending_detail)})")
            sp.update(f"Refrescando fichas ({len(pending_detail)}/{len(pending_detail)})")
        logger.info("Fichas refrescadas correctamente: %d/%d", refreshed, len(pending_detail))

    # 4) Precios volátiles: usar caché y refrescar rápido cuando sea posible
    old_prices_cache = _load_prices_cache()
    prices_cache = old_prices_cache
    prices_by_ideess = old_prices_cache.get("precios_por_ideess", {})
    if not isinstance(prices_by_ideess, dict):
        prices_by_ideess = {}

    missing_ideess_or_price_urls: set[str] = set()
    for st in stations:
        entry = mapping_by_url.get(st.url, {})
        ideess = str(entry.get("ideess") or "").strip()
        if not ideess:
            missing_ideess_or_price_urls.add(st.url)
            continue
        if ideess not in prices_by_ideess:
            missing_ideess_or_price_urls.add(st.url)

    need_matching_refresh = bool(pending_match_urls or missing_ideess_or_price_urls)
    minetur_items: Optional[List[Dict[str, Any]]] = None

    if _is_prices_snapshot_usable(old_prices_cache):
        checked_at = _safe_int(old_prices_cache.get("checked_at", 0))
        cache_fresh = now_ts - checked_at <= PRICES_REFRESH_TTL_SEC
        if cache_fresh and not need_matching_refresh:
            logger.info("Usando caché de precios fresca (%d registros).", len(prices_by_ideess))
        else:
            try:
                minetur_items = _fetch_minetur_fast()
                candidate_cache = _build_prices_snapshot(minetur_items)
                if _is_prices_snapshot_degraded(candidate_cache, old_prices_cache):
                    logger.warning(
                        "Refresco rápido de precios degradado. Se conserva la caché previa."
                    )
                    prices_cache = old_prices_cache
                else:
                    prices_cache = candidate_cache
                    _save_prices_cache(prices_cache)
                    logger.info(
                        "Caché de precios actualizada en modo rápido (%d registros).",
                        len(candidate_cache.get("precios_por_ideess", {})),
                    )
            except MiniturError as exc:
                logger.warning("Refresco rápido MINETUR falló (%s). Usando última caché buena.", exc)
                prices_cache = old_prices_cache
    else:
        try:
            minetur_items = fetch_minetur_data()
        except MiniturError as exc:
            logger.error("No se pudo refrescar MINETUR: %s", exc)
            if not _is_prices_snapshot_usable(old_prices_cache):
                raise
            prices_cache = old_prices_cache
        else:
            candidate_cache = _build_prices_snapshot(minetur_items)
            if _is_prices_snapshot_degraded(candidate_cache, old_prices_cache):
                logger.warning(
                    "Snapshot de precios online degradado. Se conserva caché previa."
                )
                prices_cache = old_prices_cache
            else:
                prices_cache = candidate_cache
                _save_prices_cache(prices_cache)
                logger.info(
                    "Caché de precios reconstruida (%d registros).",
                    len(candidate_cache.get("precios_por_ideess", {})),
                )

    prices_by_ideess = prices_cache.get("precios_por_ideess", {})
    if not isinstance(prices_by_ideess, dict):
        prices_by_ideess = {}

    if minetur_items:
        _get_minetur_match_index(minetur_items)

    def _fill_from_price_entry(record: Dict[str, Any], price_entry: Dict[str, Any]) -> None:
        for key in COMBUSTIBLES:
            record[key] = to_float_es(price_entry.get(key))
        record["latitud"] = to_float_es(_get_any(price_entry, "latitud", "lat", "Latitud"))
        record["longitud"] = to_float_es(
            _get_any(price_entry, "longitud", "lon", "Longitud (WGS84)")
        )

    def _fill_from_minetur_item(record: Dict[str, Any], item: Dict[str, Any]) -> None:
        for key, (campo_minetur, _) in COMBUSTIBLES.items():
            record[key] = to_float_es(item.get(campo_minetur))
        record["latitud"] = to_float_es(_get_any(item, "Latitud"))
        record["longitud"] = to_float_es(_get_any(item, "Longitud (WGS84)"))

    final_records: List[Dict[str, Any]] = []

    # 5) Construcción final incremental, preservando último registro válido por URL
    for st in stations:
        entry = mapping_by_url.get(st.url, {})
        ideess = str(entry.get("ideess") or "").strip()
        record: Dict[str, Any] = {
            "nombre": st.name,
            "ubicacion": entry.get("location") or st.address,
            **{k: None for k in COMBUSTIBLES},
            "latitud": None,
            "longitud": None,
            "url": st.url,
        }

        if ideess and ideess in prices_by_ideess:
            _fill_from_price_entry(record, prices_by_ideess[ideess])
        else:
            should_try_match = (
                minetur_items is not None
                and (
                    st.url in pending_match_urls
                    or st.url in missing_ideess_or_price_urls
                    or not ideess
                )
            )
            if should_try_match:
                setattr(st, "ideess", ideess or None)
                st.address = record.get("ubicacion")
                st.match_tokens = entry.get("match_tokens") or []
                match = match_station_to_minetur(st, minetur_items)
                entry["last_match_attempt"] = now_ts
                entry["last_match_attempt_ts"] = now_ts
                if match:
                    new_ideess = _extract_ideess(match)
                    if new_ideess:
                        entry["ideess"] = new_ideess
                        setattr(st, "ideess", new_ideess)
                        if new_ideess in prices_by_ideess:
                            _fill_from_price_entry(record, prices_by_ideess[new_ideess])
                    if not _record_has_any_price(record):
                        _fill_from_minetur_item(record, match)
                    entry["fail_count"] = max(0, _safe_int(entry.get("fail_count", 0)) - 1)
                else:
                    entry["fail_count"] = _safe_int(entry.get("fail_count", 0)) + 1
                mapping_by_url[st.url] = entry

        if not _record_has_any_price(record):
            prev = previous_by_url.get(st.url)
            if prev and _record_has_any_price(prev):
                merged = dict(prev)
                merged["nombre"] = st.name
                merged["url"] = st.url
                if record.get("ubicacion"):
                    merged["ubicacion"] = record["ubicacion"]
                for key in COMBUSTIBLES:
                    if record.get(key) is not None:
                        merged[key] = record[key]
                if record.get("latitud") is not None:
                    merged["latitud"] = record["latitud"]
                if record.get("longitud") is not None:
                    merged["longitud"] = record["longitud"]
                record = merged

        final_records.append(record)

    _save_mapping_cache(mapping_cache)

    if _is_final_snapshot_degraded(final_records, previous_snapshot if previous_snapshot else None):
        if previous_snapshot:
            logger.warning(
                "Snapshot nuevo degradado. Se conserva el último snapshot válido (%d estaciones).",
                len(previous_snapshot),
            )
            return previous_snapshot
        logger.warning("Snapshot generado degradado y sin snapshot previo válido.")

    return final_records


def _empty_record(st: Station) -> Dict[str, Any]:
    return {
        "nombre": st.name,
        "ubicacion": None,
        **{k: None for k in COMBUSTIBLES},
        "latitud": None,
        "longitud": None,
        "url": st.url,
    }

def _read_cached_data(path: str) -> Optional[tuple[str, List[Dict[str, Any]]]]:
    """
    Lee el fichero TXT y devuelve (fecha_str, datos) si existe y es válido.
    El formato esperado es:
        # SCRAPE_DATE: 2025-01-31
        [ ... json ... ]
    Devuelve None si el fichero no existe, está vacío o es ilegible.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
            rest = f.read()
    except (FileNotFoundError, OSError):
        return None

    m = re.match(r"^#\s*SCRAPE_DATE:\s*(\d{4}-\d{2}-\d{2})$", first_line)
    if not m:
        return None

    date_str = m.group(1)
    try:
        data = json.loads(rest)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None

    clean = [rec for rec in data if isinstance(rec, dict)]
    if not clean:
        return None
    return date_str, clean


def _write_cached_data(path: str, data: List[Dict[str, Any]]) -> None:
    """
    Escribe el fichero TXT con encabezado de fecha y JSON ordenado por precio.
    """
    existing = _read_cached_data(path)
    old_data = existing[1] if existing is not None else None
    data_clean = [rec for rec in data if isinstance(rec, dict)]

    if _is_final_snapshot_degraded(data_clean, old_data):
        if old_data:
            logger.warning(
                "Snapshot final degradado (%d registros). Se conserva caché previa de '%s'.",
                len(data_clean),
                path,
            )
            return
        logger.warning(
            "Snapshot final degradado y sin caché previa válida. No se escribirá '%s'.",
            path,
        )
        return

    today = _today_str()
    data_sorted = sorted(
        data_clean,
        key=lambda x: (x.get("gasoleo_a") is None, x.get("gasoleo_a") or 0),
    )
    content = f"# SCRAPE_DATE: {today}\n" + json.dumps(data_sorted, ensure_ascii=False, indent=2)
    _atomic_write_text(path, content)
    logger.info("Datos guardados en '%s' (%d estaciones)", path, len(data_sorted))

__all__ = [name for name in globals() if not name.startswith('__')]

