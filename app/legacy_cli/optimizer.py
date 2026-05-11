from .routing import *
# ---------------------------------------------------------------------------
# Optimización multiobjetivo: Pareto + epsilon
# ---------------------------------------------------------------------------

def coste_100km(precio_eur_litro: float) -> float:
    """Coste de recorrer 100 km con el consumo configurado."""
    return round(precio_eur_litro * CONSUMPTION_L_PER_100KM, 4)


def print_comparative_table(fill_values, rows, title="TABLA COMPARATIVA — gasolinera ganadora por litros a repostar"):
    # headers = columnas (litros)
    headers = [f"{fv:.1f}" for fv in fill_values]
    ncols = len(headers)

    # ancho de la columna izquierda (labels)
    label_w = max(len(k) for k in rows.keys()) + 2

    # ancho fijo por columna (para cada fv), mirando TODAS las filas
    col_w = []
    for j in range(ncols):
        max_len = len(headers[j])
        for label in rows:
            max_len = max(max_len, len(rows[label][j]))
        col_w.append(max_len + 2)  # padding

    total_w = label_w + sum(col_w)

    def fmt(val: str, width: int, align: str):
        return f"{val:{align}{width}}"

    # qué filas van alineadas a la derecha (numéricas)
    right_rows = {"Litros", "€/L", "km total", "Coste viaje", "Repostaje", "TOTAL €", "km netos"}

    print("\n" + "=" * total_w)
    print(title.center(total_w))
    print("=" * total_w)

    # header row
    print(fmt("", label_w, "<"), end="")
    for j in range(ncols):
        print(fmt(headers[j], col_w[j], ">"), end="")
    print()
    print("-" * total_w)

    # body
    for label, values in rows.items():
        align = ">" if label in right_rows else "<"
        print(fmt(label, label_w, "<"), end="")
        for j, v in enumerate(values):
            print(fmt(v, col_w[j], align), end="")
        print()

        # separador visual después de Gasolinera y TOTAL
        if label in {"Gasolinera", "TOTAL €"}:
            print("-" * total_w)

    print("=" * total_w)


def pareto_front(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Devuelve los items NO dominados (frontera de Pareto).

    A domina a B si:
      - A.coste_total <= B.coste_total
      - A.km_netos    >= B.km_netos
    con al menos una desigualdad estricta.

    Devuelve copias marcadas con item["pareto"] = True para no contaminar
    la lista de ranking original.
    """
    marked = [dict(item, pareto=True) for item in items]

    for i, a in enumerate(marked):
        for j, b in enumerate(marked):
            if i == j:
                continue
            # ¿domina b a a?
            if (
                b["coste_total"] <= a["coste_total"]
                and b["km_netos"] >= a["km_netos"]
                and (
                    b["coste_total"] < a["coste_total"]
                    or b["km_netos"] > a["km_netos"]
                )
            ):
                a["pareto"] = False
                break

    return [it for it in marked if it["pareto"]]


def epsilon_winner(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Regla epsilon sobre la lista completa de items:
      1. candidatos = items con coste_total <= min(coste_total) + EPSILON_EUR
      2. entre candidatos, maximiza km_netos
      3. desempate: menor d_total_km, luego menor coste_total
    """
    if not items:
        return None

    min_cost = min(it["coste_total"] for it in items)
    candidates = [it for it in items if it["coste_total"] <= min_cost + EPSILON_EUR]

    return max(
        candidates,
        key=lambda x: (
            x["km_netos"],
            -x["d_total_km"],
            -x["coste_total"],
        ),
    )
# ---------------------------------------------------------------------------
# Optimización: minimizar coste total (trayecto)
# ---------------------------------------------------------------------------

def find_optimal_station(
    stations: List[Dict[str, Any]],
    origin: tuple[float, float],
    destination: tuple[float, float],
    combustible_key: str = "gasoleo_a",
    l_fill: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    precio_campo = combustible_key  # clave del dict de precios en cada record

    valid = [
        s for s in stations
        if s.get(precio_campo) is not None
        and s.get("latitud") is not None
        and s.get("longitud") is not None
    ]
    if not valid:
        logger.error("No hay estaciones válidas con precio y coordenadas.")
        return None

    coords_stations = [(s["latitud"], s["longitud"]) for s in valid]
    ors_session = requests.Session()
    ors_session.headers.update({"User-Agent": USER_AGENT})

    with Spinner(f"Calculando rutas ida → gasolineras ({len(valid)})") as sp:
        matrix_ida = _ors_matrix(
            sources=[origin],
            destinations=coords_stations,
            session=ors_session,
        )
        sp.update(f"Calculando rutas ida → gasolineras ({len(valid)})")

    with Spinner(f"Calculando rutas vuelta ← gasolineras ({len(valid)})") as sp:
        matrix_vuelta = _ors_matrix(
            sources=coords_stations,
            destinations=[destination],
            session=ors_session,
        )
        sp.update(f"Calculando rutas vuelta ← gasolineras ({len(valid)})")

    ors_session.close()

    if matrix_ida is None or matrix_vuelta is None:
        logger.error("No se pudieron obtener las matrices de distancia.")
        return None

    # ── Pre-calcular métricas de trayecto (no dependen de L_FILL) ───────────
    enriched: List[Dict[str, Any]] = []
    for i, s in enumerate(valid):
        d_ida    = matrix_ida[0][i]
        d_vuelta = matrix_vuelta[i][0]
        if d_ida is None or d_vuelta is None:
            logger.warning("Sin ruta ORS para '%s', ignorada.", s["nombre"])
            continue
        # Añadimos una pequeña incertidumbre por tramo para compensar
        # la imprecisión inherente en las estimaciones de ruta de ORS.
        d_ida    += DISTANCE_UNCERTAINTY_KM
        d_vuelta += DISTANCE_UNCERTAINTY_KM
        d_total         = d_ida + d_vuelta
        litros_trayecto = (d_total / 100.0) * CONSUMPTION_L_PER_100KM
        precio          = s[precio_campo]
        enriched.append({
            **s,
            "d_ida_km":        d_ida,
            "d_vuelta_km":     d_vuelta,
            "d_total_km":      d_total,
            "litros_trayecto": litros_trayecto,
            "coste_viaje":     litros_trayecto * precio,
        })

    if not enriched:
        logger.error("ORS no devolvió rutas para ninguna estación.")
        return None

    # ── Helper: ranking completo para un L_FILL dado ─────────────────────────
    def _rank(fill: float) -> List[Dict[str, Any]]:
        results = []
        skipped = 0
        for e in enriched:
            litros_netos = fill - e["litros_trayecto"]
            if litros_netos <= 0:
                # El trayecto consume más (o igual) que los litros a repostar:
                # esta estación no es viable para este L_FILL.
                skipped += 1
                continue
            precio          = e[precio_campo]
            coste_repostaje = fill * precio
            coste_total     = e["coste_viaje"] + coste_repostaje
            km_netos        = litros_netos / CONSUMPTION_L_PER_100KM * 100
            results.append({
                **e,
                "l_fill":          fill,
                "coste_repostaje": coste_repostaje,
                "coste_total":     coste_total,
                "km_netos":        km_netos,
            })
        if skipped:
            logger.debug(
                "_rank(fill=%.1f L): %d estaciones descartadas por litros_trayecto >= fill.",
                fill, skipped,
            )
        return sorted(results, key=lambda x: x["coste_total"])

    # ── Modo escenarios (Enter) ───────────────────────────────────────────────
    if l_fill is None:
        fill_values: List[float] = []
        v = L_FILL_MIN
        while v <= L_FILL_MAX + 1e-9:
            fill_values.append(round(v, 1))
            v += L_FILL_STEP

        rows = {
            "Litros":      [],
            "Gasolinera":  [],
            "€/L":         [],
            "km total":    [],
            "Coste viaje": [],
            "Repostaje":   [],
            "TOTAL €":     [],
            "km netos":    [],
        }
        for fv in fill_values:
            ranked_fv = _rank(fv)
            if not ranked_fv:
                rows["Litros"].append(f"{fv:.1f}")
                rows["Gasolinera"].append("— INVIABLE —")
                rows["€/L"].append("—")
                rows["km total"].append("—")
                rows["Coste viaje"].append("—")
                rows["Repostaje"].append("—")
                rows["TOTAL €"].append("INVIABLE")
                rows["km netos"].append("—")
                continue
            w = ranked_fv[0]
            litros_netos = fv - w["litros_trayecto"]
            km_netos = round(litros_netos / CONSUMPTION_L_PER_100KM * 100, 1)
            rows["Litros"].append(f"{fv:.1f}")
            rows["Gasolinera"].append(w["nombre"][:22])
            rows["€/L"].append(f"{w[precio_campo]:.3f}")
            rows["km total"].append(f"{w['d_total_km']:.1f}")
            rows["Coste viaje"].append(f"{w['coste_viaje']:.2f} €")
            rows["Repostaje"].append(f"{w['coste_repostaje']:.2f} €")
            rows["TOTAL €"].append(f"{w['coste_total']:.2f} €")
            rows["km netos"].append(f"{km_netos:.1f} km")

        print_comparative_table(fill_values, rows)

        # Escenario central como l_fill para el ranking final
        # (buscamos el primero viable desde el centro)
        viable_fills = [fv for fv in fill_values if _rank(fv)]
        if not viable_fills:
            logger.error("Ningún escenario de litros es viable para las distancias calculadas.")
            print(
                "\n⚠️  ERROR: Ninguna gasolinera es viable con los litros del barrido "
                f"({L_FILL_MIN:.0f}–{L_FILL_MAX:.0f} L). "
                "El trayecto de ida+vuelta consume más combustible del que repostas.\n"
                "Aumenta los litros a repostar o elige un destino más cercano."
            )
            return None
        central_idx = len(viable_fills) // 2
        l_fill = viable_fills[central_idx]
        logger.info("Escenario central seleccionado: %.1f L", l_fill)

    # ── Ranking final (siempre se ejecuta, con l_fill definitivo) ────────────
    ranked      = _rank(l_fill)
    if not ranked:
        min_viable_l = min(
            (e["litros_trayecto"] for e in enriched),
            default=None,
        )
        msg = (
            f"\n⚠️  ERROR: Con {l_fill:.1f} L ninguna gasolinera es viable.\n"
            "  El trayecto de ida+vuelta consume más combustible del que repostas.\n"
        )
        if min_viable_l is not None:
            msg += (
                f"  La gasolinera más cercana necesita al menos "
                f"{min_viable_l:.2f} L para el trayecto.\n"
                f"  Debes repostar más de {min_viable_l:.2f} L para que salga a cuenta.\n"
            )
        print(msg)
        logger.error("Sin estaciones viables para l_fill=%.1f L.", l_fill)
        return None
    front       = pareto_front(ranked)
    front_keys = {
        (r.get("url"), r.get("coste_total"), r.get("km_netos"))
        for r in front
    }
    winner_cost = ranked[0]
    winner_eps  = epsilon_winner(ranked)

    # Layout fijo para evitar saltos de columna en consola.
    NAME_COL_W = 30

    def _fit_name(value: Any) -> str:
        return str(value or "")[:NAME_COL_W]

    top_header = (
        f"  {'Pos':<4} {'Nombre':<{NAME_COL_W}} {'€/L':>6}  {'km':>6}  "
        f"{'c.viaje':>9}  {'c.repo':>9}  {'c.total':>9}  {'km netos':>9}  {'Pareto':>6}"
    )
    top_row_fmt = (
        f"  {{pos:<4}} {{nombre:<{NAME_COL_W}}} {{precio:>6}}  {{km:>6}}  "
        f"{{c_viaje:>9}}  {{c_repo:>9}}  {{c_total:>9}}  {{km_netos:>9}}  {{pareto:>6}}"
    )

    pareto_header = (
        f"  {'Pos':<4} {'Nombre':<{NAME_COL_W}} {'€/L':>6}  {'km':>6}  "
        f"{'c.viaje':>9}  {'c.repo':>9}  {'c.total':>9}  {'km netos':>9}  {'Δ€/100km':>8}"
    )
    pareto_row_fmt = (
        f"  {{pos:<4}} {{nombre:<{NAME_COL_W}}} {{precio:>6}}  {{km:>6}}  "
        f"{{c_viaje:>9}}  {{c_repo:>9}}  {{c_total:>9}}  {{km_netos:>9}}  {{delta100:>8}}"
    )

    # ── Log Top 10 por coste_total ───────────────────────────────────────────
    separator = "  " + "-" * (len(top_header) - 2)
    logger.info("Top 10 por coste_total (L_FILL=%.1f L, combustible=%s):", l_fill, precio_campo)
    logger.info(top_header)
    logger.info(separator)
    for n, r in enumerate(ranked[:10], 1):
        pareto_flag = "✓" if (r.get("url"), r.get("coste_total"), r.get("km_netos")) in front_keys else " "
        row = top_row_fmt.format(
            pos=n,
            nombre=_fit_name(r["nombre"]),
            precio=f"{r[precio_campo]:.3f}",
            km=f"{r['d_total_km']:.1f}",
            c_viaje=f"{r['coste_viaje']:.4f}",
            c_repo=f"{r['coste_repostaje']:.4f}",
            c_total=f"{r['coste_total']:.4f}",
            km_netos=f"{r['km_netos']:.1f}",
            pareto=pareto_flag,
        )
        logger.info("%s", row)

    # ── Log Frontera de Pareto ───────────────────────────────────────────────
    front_sorted = sorted(front, key=lambda x: x["coste_total"])
    logger.info("\n\nFrontera de Pareto (%d estaciones):", len(front_sorted))

    referencia      = front_sorted[0]  # la de menor coste_total
    ref_precio      = referencia[precio_campo]
    ref_coste_100km = coste_100km(ref_precio)

    pareto_sep = "  " + "-" * (len(pareto_header) - 2)
    logger.info(pareto_header)
    logger.info(pareto_sep)

    for idx, r in enumerate(front_sorted):
        precio_r      = r[precio_campo]
        coste_100_r   = coste_100km(precio_r)
        diff_100km    = round(coste_100_r - ref_coste_100km, 4)

        row = pareto_row_fmt.format(
            pos="—",
            nombre=_fit_name(r["nombre"]),
            precio=f"{precio_r:.3f}",
            km=f"{r['d_total_km']:.1f}",
            c_viaje=f"{r['coste_viaje']:.4f}",
            c_repo=f"{r['coste_repostaje']:.4f}",
            c_total=f"{r['coste_total']:.4f}",
            km_netos=f"{r['km_netos']:.1f}",
            delta100=f"{diff_100km:.4f}",
        )
        logger.info("%s", row)

    # ── Log ganadores ────────────────────────────────────────────────────────
    logger.info(
        "Ganador por coste_total : %-30s %.3f €/L  %.4f €  %.1f km netos",
        winner_cost["nombre"], winner_cost[precio_campo],
        winner_cost["coste_total"], winner_cost["km_netos"],
    )
    logger.info(
        "Ganador por Pareto+eps  : %-30s %.3f €/L  %.4f €  %.1f km netos  (EPSILON=%.2f €)",
        winner_eps["nombre"], winner_eps[precio_campo],
        winner_eps["coste_total"], winner_eps["km_netos"], EPSILON_EUR,
    )

    return winner_cost, winner_eps


__all__ = [name for name in globals() if not name.startswith('__')]

