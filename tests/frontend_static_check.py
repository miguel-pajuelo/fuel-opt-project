from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_frontend_is_extracted() -> None:
    html = _read("static/index.html")
    _assert('href="/static/styles.css' in html, "index.html does not load static CSS.")
    _assert('src="/static/app.js' in html, "index.html does not load static JS.")
    _assert("<style>" not in html, "index.html should not embed CSS.")
    _assert("<script>\n" not in html, "index.html should not embed app JS.")


def test_dynamic_html_uses_escape_helper() -> None:
    js = _read("static/app.js")
    _assert("function escapeHtml" in js, "escapeHtml helper missing.")
    risky_patterns = [
        r"\$\('result'\)\.innerHTML = `[\s\S]*\$\{station\.name\}",
        r"\$\('result'\)\.innerHTML = `[\s\S]*\$\{selected\.why_selected\}",
        r"box\.innerHTML = `<button[\s\S]*\$\{error\.message\}",
        r"\.map\(f => `<option value=\"\$\{f\.key\}",
    ]
    for pattern in risky_patterns:
        _assert(not re.search(pattern, js), f"Unsafe dynamic HTML pattern found: {pattern}")
    required_safe_fragments = [
        "escapeHtml(error.message)",
        "escapeHtml(f.key)",
        "escapeHtml(f.label)",
        "const stationName = escapeHtml(station.name)",
        "const whySelected = escapeHtml(selected.why_selected",
    ]
    for fragment in required_safe_fragments:
        _assert(fragment in js, f"Expected escaped fragment missing: {fragment}")


def test_frontend_has_no_visible_mojibake() -> None:
    js = _read("static/app.js")
    for token in ("Ã", "Â", "â‚¬", "Ă", "�"):
        _assert(token not in js, f"Visible mojibake token found in static/app.js: {token!r}")


def test_result_metrics_are_rendered_once() -> None:
    js = _read("static/app.js")
    _assert("const metrics = isBudgetMode" in js, "Metrics template should be built once.")
    _assert('<div class="metrics">${metrics}</div>' in js, "Result metrics should be inserted directly.")
    _assert("querySelector('.metrics').innerHTML = metrics" not in js, "Dead metrics overwrite should not return.")


def test_catalog_and_route_status_copy_present() -> None:
    html = _read("static/index.html")
    js = _read("static/app.js")
    _assert('id="refresh_status"' in html, "Refresh status field missing in HTML.")
    _assert("Precios descargados" in html, "Header should show downloaded price data label.")
    _assert("Última actualización de precios" not in html, "Header should not claim an official price update date.")
    for removed_copy in ("Build:", "Precios de referencia:", "Datos de snapshot", "Catálogo: pendiente"):
        _assert(removed_copy not in html, f"Technical catalog copy should not be visible: {removed_copy}")
    _assert("catalog?.source_fetched_at" in js, "Visible refresh date should use source_fetched_at first.")
    _assert("catalog?.source_fetch_completed_at" in js, "Visible refresh date should fall back to source_fetch_completed_at.")
    _assert("catalog?.source_reference_date" not in js[js.find("function refreshTimestampValue"):js.find("function refreshTimestamp")], "Visible refresh date must not use source_reference_date.")
    _assert("catalog?.built_at" in js, "Visible refresh date may use built_at only as final fallback.")
    _assert("Catálogo degradado" not in js, "Degraded catalog copy should not be shown in the UI.")
    _assert("Ruta estimada por distancia" in js, "Haversine route status copy missing.")
    _assert("Ruta calculada con OpenRouteService" not in js, "ORS route note should not be shown in results.")
    _assert("emptyResultHtml" in js, "No-result helper missing.")


def test_app_js_renders_warnings() -> None:
    js = _read("static/app.js")
    _assert("function renderWarnings" in js, "renderWarnings helper missing.")
    _assert("result-warning--info" in js, "Info warning class missing from JS.")
    _assert("result-warning--warning" in js, "Warning class missing from JS.")
    _assert("result-warning--critical" in js, "Critical warning class missing from JS.")


def test_haversine_copy_appears_once() -> None:
    js = _read("static/app.js")
    _assert(
        js.count("Ruta estimada por distancia") == 1,
        "Haversine copy should appear once, only as structured warning.",
    )


def test_styles_warning_classes() -> None:
    styles = _read("static/styles.css")
    _assert(".result-warning" in styles, "Base warning class missing from CSS.")
    _assert(".result-warning--info" in styles, "Info warning class missing from CSS.")
    _assert(".result-warning--warning" in styles, "Warning class missing from CSS.")
    _assert(".result-warning--critical" in styles, "Critical warning class missing from CSS.")


def test_stale_price_warning_moves_to_price_metric() -> None:
    js = _read("static/app.js")
    styles = _read("static/styles.css")
    _assert("function priceMetricHtml" in js, "Price metric helper missing.")
    _assert("stale_reference_prices" in js, "Stale price warning should be handled in JS.")
    _assert("price-warning" in js, "Price warning marker missing from JS.")
    _assert("price-warning-icon" in js, "Triangular warning icon markup missing from JS.")
    _assert("Fecha oficial no disponible" in js, "Missing official date tooltip title missing.")
    _assert("MINETUR no informa una fecha oficial por precio. El cálculo usa los últimos datos descargados por FuelOpt." in js, "Missing official date tooltip copy missing.")
    _assert("Se recomienda refrescar los datos" not in js, "Stale price tooltip should not recommend refreshing.")
    _assert("catalog_degraded" in js, "Catalog degraded code should be filtered by JS.")
    _assert(".price-warning" in styles, "Price warning marker styles missing.")
    _assert(".price-warning-icon" in styles, "Triangular warning icon styles missing.")
    _assert("clip-path: polygon" in styles, "Warning icon should be triangular.")
    _assert(".price-warning-tooltip" in styles, "Price warning tooltip styles missing.")


def test_app_js_handles_virtual_brand() -> None:
    js = _read("static/app.js")
    styles = _read("static/styles.css")
    _assert("is_virtual" in js or "__INDEPENDENT__" in js, "Virtual brand handling missing from JS.")
    _assert("brand-check--virtual" in js, "Virtual brand class missing from JS.")
    _assert(".brand-check--virtual" in styles, "Virtual brand class missing from CSS.")
    _assert(".brand-hint" in styles, "Virtual brand hint style missing from CSS.")


def run() -> None:
    test_frontend_is_extracted()
    test_dynamic_html_uses_escape_helper()
    test_frontend_has_no_visible_mojibake()
    test_result_metrics_are_rendered_once()
    test_catalog_and_route_status_copy_present()
    test_app_js_renders_warnings()
    test_haversine_copy_appears_once()
    test_styles_warning_classes()
    test_stale_price_warning_moves_to_price_metric()
    test_app_js_handles_virtual_brand()
    print("OK: frontend static checks passed")


if __name__ == "__main__":
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    run()
