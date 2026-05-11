from .optimizer import *
def _parse_coordinates_input(raw: str) -> tuple[float, float]:
    partes = [p.strip().replace(",", ".") for p in raw.replace(";", ",").split(",")]
    if len(partes) != 2:
        raise ValueError("se esperaban dos coordenadas")
    lat, lon = float(partes[0]), float(partes[1])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("coordenadas fuera de rango")
    return lat, lon


def _pedir_coordenadas(prompt_nombre: str) -> tuple[float, float]:
    while True:
        raw = input(f"\n{prompt_nombre} — introduce lat,lon (ej: 40.4366,-3.7277): ").strip()
        try:
            return _parse_coordinates_input(raw)
        except (ValueError, IndexError):
            print("  Formato incorrecto. Usa dos números separados por coma, ej: 40.4366,-3.7277")


def _pedir_destino(origin: tuple[float, float]) -> tuple[float, float]:
    print("\nUbicación de LLEGADA (destino al que vuelves tras repostar).")
    raw_dest = input("  Pulsa Enter para usar la misma que la salida, o introduce lat,lon: ").strip()
    if raw_dest == "":
        print(f"  → Usando la misma ubicación de salida: {origin}")
        return origin
    try:
        return _parse_coordinates_input(raw_dest)
    except (ValueError, IndexError):
        print("  Formato incorrecto. Se usará la misma ubicación de salida.")
        return origin


def _print_winner(
    winner: Dict[str, Any],
    title: str,
    precio_campo: str,
    label_sel: str,
) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)
    print(f"  Nombre            : {winner['nombre']}")
    print(f"  Ubicación         : {winner['ubicacion']}")
    print(f"  {label_sel:<17}: {winner[precio_campo]:.3f} €/L")
    print(f"  Distancia ida     : {winner['d_ida_km']:.2f} km")
    print(f"  Distancia vuelta  : {winner['d_vuelta_km']:.2f} km")
    print(f"  Distancia total   : {winner['d_total_km']:.2f} km")
    print(f"  Litros trayecto   : {winner['litros_trayecto']:.3f} L")
    print(f"  Coste viaje       : {winner['coste_viaje']:.4f} €")
    print(f"  ─────────────────────────────────────")
    print(f"  Litros repostados : {winner['l_fill']:.2f} L")
    print(
        f"  Litros netos      : {winner['l_fill'] - winner['litros_trayecto']:.3f} L"
        f"  →  {winner['km_netos']:.1f} km netos"
    )
    print(f"  Coste repostaje   : {winner['coste_repostaje']:.4f} €")
    print(f"  ─────────────────────────────────────")
    print(f"  COSTE TOTAL       : {winner['coste_total']:.4f} €")
    print(f"  KM NETOS          : {winner['km_netos']:.1f} km")
    print(f"  URL               : {winner['url']}")
    print("=" * 60)


def run_cli() -> None:
    # scrape_ballenoil_diesel ya gestiona la caché por estación internamente.
    # Siempre se llama; ella decide qué hay que scrapear y qué reutilizar.
    data = scrape_ballenoil_diesel()
    _write_cached_data(OUTPUT_PATH, data)

    # ── Elección de combustible ──────────────────────────────────────────────
    print("\n¿Qué tipo de combustible quieres usar?")
    opciones = list(COMBUSTIBLES.items())
    for i, (key, (_, label)) in enumerate(opciones, 1):
        disponible = any(s.get(key) is not None for s in data)
        sufijo = "" if disponible else "  (sin datos)"
        print(f"  {i}) {label}{sufijo}")
    while True:
        raw_comb = input(f"Elige [1-{len(opciones)}]: ").strip()
        try:
            idx_comb = int(raw_comb) - 1
            if 0 <= idx_comb < len(opciones):
                precio_campo_sel, (_, label_sel) = opciones[idx_comb]
                break
        except ValueError:
            pass
        print(f"  Opción inválida, introduce un número entre 1 y {len(opciones)}.")
    print(f"  → Combustible seleccionado: {label_sel}")

    # ── Input coordenadas de salida ──────────────────────────────────────────
    origin = _pedir_coordenadas("Ubicación de SALIDA")
    destination = _pedir_destino(origin)

    # ── Input litros a repostar ──────────────────────────────────────────────
    raw_fill = input(
        f"\n¿Cuántos litros quieres repostar? "
        f"[Enter para ver escenarios de {L_FILL_MIN:.0f} a {L_FILL_MAX:.0f} L "
        f"en pasos de {L_FILL_STEP:.0f} L]: "
    ).strip()

    l_fill_input: Optional[float] = None
    if raw_fill:
        try:
            l_fill_input = float(raw_fill.replace(",", "."))
            if l_fill_input <= 0:
                raise ValueError("debe ser positivo")
        except ValueError as exc:
            print(f"Valor inválido ({exc}). Se mostrarán escenarios automáticos.")
            l_fill_input = None

    # ── Optimización ─────────────────────────────────────────────────────────
    logger.info(
        "Calculando rutas y costes | combustible=%s | origen=%s | destino=%s…",
        label_sel, origin, destination,
    )
    winner_cost: Optional[Dict[str, Any]] = None
    winner_eps: Optional[Dict[str, Any]] = None
    result = find_optimal_station(
        data,
        origin=origin,
        destination=destination,
        combustible_key=precio_campo_sel,
        l_fill=l_fill_input,
    )
    if result is None:
        print("\nNo se pudo determinar la gasolinera óptima.")
    else:
        winner_cost, winner_eps = result

    # ── Resultado final ───────────────────────────────────────────────────────
    if winner_cost is not None and winner_eps is not None:
        if winner_cost != winner_eps:
            _print_winner(winner_cost, "ÓPTIMA por menor coste_total", precio_campo_sel, label_sel)
            _print_winner(
                winner_eps,
                f"ÓPTIMA por Pareto+eps  (EPSILON={EPSILON_EUR:.2f} €)",
                precio_campo_sel,
                label_sel,
            )
        else:
            _print_winner(
                winner_eps,
                "ÓPTIMA TOTAL (MENOR COSTO € + PARETO)",
                precio_campo_sel,
                label_sel,
            )

    else:
        print("\nNo se pudo determinar la gasolinera óptima.")

__all__ = [name for name in globals() if not name.startswith('__')]
