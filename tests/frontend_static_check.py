from __future__ import annotations

import re
import sys
from html import unescape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _html_attributes(tag: str) -> dict[str, str]:
    return {
        name: unescape(value)
        for name, _quote, value in re.findall(
            r"([\w:-]+)\s*=\s*([\"'])(.*?)\2",
            tag,
            flags=re.DOTALL,
        )
    }


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
        r"box\.innerHTML = `<button[\s\S]*\$\{error\.message\}",
        r"\.map\(f => `<option value=\"\$\{f\.key\}",
    ]
    for pattern in risky_patterns:
        _assert(not re.search(pattern, js), f"Unsafe dynamic HTML pattern found: {pattern}")
    required_safe_fragments = [
        "escapeHtml(error.message)",
        "escapeHtml(opt.key)",
        "escapeHtml(opt.label)",
        "const stationName = escapeHtml(station.name ||",
    ]
    for fragment in required_safe_fragments:
        _assert(fragment in js, f"Expected escaped fragment missing: {fragment}")


def test_optimization_mode_selector_is_native_and_accessible() -> None:
    html = _read("static/index.html")
    styles = _read("static/styles.css")
    decoded = unescape(html)
    radio_tags = [
        tag
        for tag in re.findall(r"<input\b[^>]*>", html, flags=re.IGNORECASE)
        if _html_attributes(tag).get("type") == "radio"
        and _html_attributes(tag).get("name") == "optimization_mode"
    ]
    _assert(len(radio_tags) == 3, f"Expected exactly three optimization radios, got {radio_tags}")
    radios = {_html_attributes(tag)["value"]: _html_attributes(tag) for tag in radio_tags}
    _assert(set(radios) == {"economic", "minimal_detour", "balanced"}, radios)
    _assert("checked" in radio_tags[0] and radios["economic"]["id"] == "optimization_mode_economic", radios)
    _assert(sum(" checked" in tag for tag in radio_tags) == 1, "Only economic may be selected by default.")
    _assert('<fieldset class="config-field optimization-mode-field span-2">' in html, "Optimization fieldset missing.")
    _assert("<legend class=\"label\">Objetivo de optimizaci&#243;n</legend>" in html, "Optimization legend missing.")
    for value, label in {
        "economic": "Más ahorro",
        "minimal_detour": "Menor desvío",
        "balanced": "Equilibrado",
    }.items():
        radio_id = radios[value]["id"]
        label_match = re.search(
            rf'<label\b[^>]*\bfor="{re.escape(radio_id)}"[^>]*>(.*?)</label>',
            html,
            flags=re.DOTALL,
        )
        _assert(label_match is not None, f"Missing associated label for {value}.")
        label_text = unescape(re.sub(r"<[^>]+>", " ", label_match.group(1)))
        _assert(label in " ".join(label_text.split()), f"Public label missing for {value}.")
    for description in (
        "Prioriza el mayor ahorro neto estimado, descontando el coste del desplazamiento.",
        "Prioriza la estación que exige menos distancia adicional.",
        "En búsquedas locales, prioriza la estación más cercana.",
        "Equilibra por igual el ahorro estimado y el desvío entre las opciones encontradas.",
    ):
        _assert(description in decoded, f"Optimization description missing: {description}")
    _assert('role="radio"' not in html, "Native radios must not duplicate ARIA radio semantics.")
    _assert('id="optimization_mode"' not in html, "Legacy optimization dropdown container remains.")
    _assert("optimization_mode_trigger" not in html, "Legacy optimization dropdown trigger remains.")
    _assert(".optimization-mode-option:has(input:checked)" in styles, "Selected radio card styling missing.")
    _assert(".optimization-mode-option:has(input:focus-visible)" in styles, "Visible keyboard focus styling missing.")
    legend_rule = re.search(r"\.optimization-mode-field > legend\s*\{(?P<body>[^}]*)\}", styles)
    _assert(legend_rule is not None, "Optimization legend style rule missing.")
    options_rule = re.search(r"\.optimization-mode-options\s*\{(?P<body>[^}]*)\}", styles)
    _assert(options_rule is not None, "Optimization options style rule missing.")
    _assert("margin-top: 15px" in options_rule.group("body"), "Optimization cards need visible separation from the legend.")


def test_optimization_mode_request_and_result_state_are_separate() -> None:
    js = _read("static/app.js")
    _assert("function getSelectedOptimizationMode()" in js, "Optimization radio reader missing.")
    _assert(
        "document.querySelector('input[name=\"optimization_mode\"]:checked')" in js,
        "Optimization mode must be read from the checked native radio.",
    )
    _assert("const requestedOptimizationMode = getSelectedOptimizationMode();" in js, "Mode must be captured once per request.")
    _assert("optimization_mode: requestedOptimizationMode" in js, "Payload must use the captured enum value.")
    _assert("getPddValue('optimization_mode')" not in js, "Legacy dropdown reader remains for optimization mode.")
    _assert("initPDD('optimization_mode')" not in js, "Legacy dropdown listener remains for optimization mode.")
    _assert("renderedOptimizationMode: null" in js, "Rendered result mode needs independent state.")
    _assert(
        "state.renderedOptimizationMode = requestedOptimizationMode;" in js,
        "Rendered mode must update only from a successful requested mode.",
    )
    _assert(
        js.index("const { data } = await requestOptimization(payload);")
        < js.index("state.renderedOptimizationMode = requestedOptimizationMode;"),
        "Rendered mode changed before a successful response.",
    )
    _assert("data.optimization_mode !== requestedOptimizationMode" in js, "Response mode mismatch must not be silently relabeled.")
    _assert("result_limit: 10" in js, "Result limit changed during selector integration.")
    _assert("remaining_fuel_liters" not in js, "Autonomy entered the frontend payload.")


def test_result_presentation_is_simplified_and_route_warning_is_plain() -> None:
    js = _read("static/app.js")
    styles = _read("static/styles.css")
    for removed_copy in (
        "Ordenado por:",
        "Por qué aparece aquí",
        "Fuente de ruta",
        "Ruta calculada con OpenRouteService",
        "Estimación mediante distancia geográfica",
    ):
        _assert(removed_copy not in js, f"Redundant result copy remains: {removed_copy}")
    _assert("why_selected" not in js, "Frontend must not render the backend why_selected field.")
    _assert("balanced_score" not in js, "Internal balanced score leaked into frontend code.")
    _assert("economic_rank" not in js and "distance_rank" not in js, "Internal ranks leaked into frontend code.")
    for removed_selector in (".result-mode-summary", ".why-selected", ".result-route-source"):
        _assert(removed_selector not in styles, f"Unused result style remains: {removed_selector}")
    _assert(js.count("Ruta estimada por distancia") == 1, "Approximate route title must appear exactly once.")
    _assert(
        js.count("El coste de ruta se ha calculado con una aproximación de distancia.") == 1,
        "Approximate route warning must use the approved plain-language copy exactly once.",
    )
    _assert("warning.code === 'using_haversine_estimate'" in js, "Approximate route copy must be limited to its structured warning.")


def test_optimize_loading_state_is_accessible_and_bounded() -> None:
    html = _read("static/index.html")
    js = _read("static/app.js")
    styles = _read("static/styles.css")
    decoded_html = unescape(html)
    _assert('id="submit" type="button" aria-busy="false"' in html, "Submit button needs an explicit idle aria-busy state.")
    _assert('class="primary-spinner" aria-hidden="true" hidden' in html, "Decorative submit spinner is missing.")
    _assert("data-submit-label" in html, "Submit label needs a stable update target.")
    _assert("Calcular mejor repostaje" in decoded_html, "Idle submit label changed unexpectedly.")
    for message in ("Buscando estaciones…", "Calculando recorridos…", "Ordenando alternativas…"):
        _assert(js.count(message) == 1, f"Loading message must exist exactly once: {message}")
    _assert("}, 1700);" in js, "Loading messages should advance every 1.7 seconds.")
    _assert("window.clearInterval(optimizeLoadingTimer)" in js, "Loading timer is not cleared.")
    _assert("if (state.optimizeInFlight) return;" in js, "Concurrent optimization requests are not guarded.")
    _assert("state.optimizeInFlight = true;" in js and "state.optimizeInFlight = false;" in js, "Request guard is not restored.")
    _assert("function setOptimizeLoadingState(isLoading)" in js, "Submit loading state helper missing.")
    _assert("button.setAttribute('aria-busy', String(isLoading))" in js, "Submit aria-busy is not synchronized.")
    _assert("Calculando mejor repostaje…" in js, "Busy submit label missing.")
    _assert("function renderOptimizeLoadingResult()" in js, "Result loading renderer missing.")
    _assert('class="result-loading-skeleton" aria-hidden="true"' in js, "Decorative result skeleton must be hidden from assistive technology.")
    _assert('role="status" aria-live="polite" data-optimize-loading-message' in js, "Result progress needs one polite live region.")
    _assert("resultElement.setAttribute('aria-busy', 'true')" in js, "Result panel does not enter aria-busy state.")
    optimize_region = js[js.index("async function optimize()") : js.index("initPDD('fuel_type')")]
    _assert("finally" in optimize_region, "Optimization cleanup must run in a finally block.")
    _assert("stopOptimizeLoadingMessages();" in optimize_region, "Optimization cleanup must stop its timer.")
    _assert("setOptimizeLoadingState(false);" in optimize_region, "Submit button is not restored after success or error.")
    _assert('role="alert"' in optimize_region, "Optimization errors need an accessible alert.")
    start_region = js[js.index("function startOptimizeLoadingMessages()") : js.index("function stopOptimizeLoadingMessages()")]
    _assert("$('status')" not in start_region, "Progress must not be duplicated below the submit button.")
    _assert(".result-loading-skeleton" in styles and ".primary-spinner" in styles, "Loading visuals are not styled.")
    _assert(".primary:focus-visible" in styles, "Submit button needs an explicit visible keyboard focus.")
    _assert("@media (prefers-reduced-motion: reduce)" in styles, "Reduced motion is not respected.")


def test_brand_loading_and_all_button_state_are_unambiguous() -> None:
    html = _read("static/index.html")
    js = _read("static/app.js")
    styles = _read("static/styles.css")
    decoded_html = unescape(html)
    brand_start = decoded_html.index('id="brand_checks"')
    brand_region = decoded_html[brand_start : decoded_html.index('class="side-footer"', brand_start)]
    _assert("Cargando marcas…" in brand_region, "Initial brand loading message missing.")
    _assert("0 estaciones" not in brand_region, "Brand loading state must not claim zero stations.")
    _assert('aria-busy="true"' in html[html.index('id="brand_checks"') : html.index('id="brand_checks"') + 100], "Brand list needs an initial busy state.")
    _assert('class="brand-loading-skeleton" aria-hidden="true"' in html, "Brand skeleton must be decorative.")
    _assert("function renderBrandsLoading()" in js, "Reusable brand loading renderer missing.")
    load_region = js[js.index("async function loadOptions()") : js.index("$('select_all_brands').addEventListener")]
    _assert(load_region.index("renderBrandsLoading();") < load_region.index("Promise.all"), "Brand loading state must appear before the existing requests.")
    _assert("container.setAttribute('aria-busy', 'false')" in js, "Brand busy state is not cleared after rendering.")
    _assert("$('select_all_brands').textContent = 'Todas';" in js, "All-brands button text must remain stable.")
    _assert("Todas excepto" not in js and "Todas excepto" not in decoded_html, "Dynamic all-except label remains.")
    _assert("classList.toggle('active', allSelected)" in js, "All-brands active state must mean every brand is selected.")
    _assert("setAttribute('aria-pressed', String(allSelected))" in js, "All-brands pressed state is ambiguous.")
    _assert("$('brand_checks').addEventListener('change'" in js, "Individual brand switches lost their handler.")
    _assert(".brand-loading" in styles and ".brand-loading-skeleton" in styles, "Brand loading state is not styled.")
    _assert(".link-button:focus-visible" in styles, "All-brands button needs an explicit visible keyboard focus.")


def test_frontend_has_no_visible_mojibake() -> None:
    js = _read("static/app.js")
    for token in ("Ã", "Â", "â‚¬", "Ă", "�"):
        _assert(token not in js, f"Visible mojibake token found in static/app.js: {token!r}")


def test_result_metrics_are_rendered_once() -> None:
    js = _read("static/app.js")
    _assert("const metrics = renderResultMetricRows(" in js, "Metrics template should be built once through the result metrics helper.")
    _assert('<div class="metrics result-metric-list">${metrics}</div>' in js, "Result metrics should be inserted directly.")
    _assert("querySelector('.metrics').innerHTML = metrics" not in js, "Dead metrics overwrite should not return.")


def test_budget_mode_result_metrics_use_liter_advantage() -> None:
    js = _read("static/app.js")
    _assert("selected.net_savings_vs_reference_eur || 0" not in js, "Budget mode must not render null savings as 0 euros.")
    _assert("function resultMainMetric(data, selected)" in js, "Result panel should choose the main metric by input mode.")
    _assert("resultInputMode(data, selected) === 'budget'" in js, "Budget result rendering should be explicit.")
    _assert("Combustible neto obtenido" not in js, "Budget mode must not use absolute net fuel as the primary headline.")
    _assert("Litros extra estimados" in js, "Budget mode should use the liter advantage as the primary metric.")
    _assert("formattedSignedLiters(selected.net_liters_vs_reference)" in js, "Budget primary value should use net_liters_vs_reference.")
    _assert("return amount > 0 ? fmtLiters(amount) : `-${fmtLiters(Math.abs(amount))}`;" in js, "Signed liter formatter should omit + for positive values and keep - for negative values.")
    _assert("Math.abs(amount) < 0.005" in js, "Signed liter formatter should show tiny deltas as 0.00 L.")
    _assert("fmtLiters(selected.net_liters)" in js, "Budget mode should still show absolute useful liters as a secondary row.")
    _assert("Litros comprados" in js, "Budget mode should show gross purchased liters.")
    _assert("Litros consumidos en desvío" not in js, "Budget mode should not show the redundant detour liters row.")
    _assert("Litros útiles estimados" in js, "Budget mode should show useful liters as a secondary row.")
    _assert("Coste efectivo estimado" not in js, "Budget mode should not show effective euros as a main row.")
    _assert("Ordenadas por litros útiles estimados" in js, "Budget alternatives should explain their ordering.")


def test_catalog_and_route_status_copy_present() -> None:
    html = _read("static/index.html")
    js = _read("static/app.js")
    _assert('id="refresh_status"' in html, "Refresh status field missing in HTML.")
    _assert("Precios actualizados" in html, "Price freshness chip should show updated price data label.")
    _assert("Precios descargados" not in html, "Old downloaded price copy should not remain in HTML.")
    _assert("Última actualización de precios" not in html, "Header should not claim an official price update date.")
    for removed_copy in ("Build:", "Precios de referencia:", "Datos de snapshot", "Catálogo: pendiente"):
        _assert(removed_copy not in html, f"Technical catalog copy should not be visible: {removed_copy}")
    _assert("catalog?.source_fetched_at" in js, "Visible refresh date should use source_fetched_at first.")
    _assert("catalog?.source_fetch_completed_at" in js, "Visible refresh date should fall back to source_fetch_completed_at.")
    _assert("catalog?.source_reference_date" not in js[js.find("function refreshTimestampValue"):js.find("function refreshTimestamp")], "Visible refresh date must not use source_reference_date.")
    _assert("catalog?.built_at" in js, "Visible refresh date may use built_at only as final fallback.")
    _assert("Catálogo degradado" not in html, "Degraded catalog copy should not be visible in HTML.")
    _assert("Catálogo degradado" not in js, "Degraded catalog copy should not be injected by frontend JS.")
    _assert("Actualizado" not in html, "Price status should not show a separate updated text label.")
    _assert("Snapshot" not in html and "Degradado" not in html, "Price status should not show technical state labels.")
    _assert("catalog_freshness_dot" in html, "Price freshness dot missing from HTML.")
    _assert("function catalogFreshnessClass" in js, "Catalog freshness color helper missing.")
    _assert("freshness-fresh" in js and "freshness-recent" in js and "freshness-stale" in js, "Freshness color classes should be assigned by JS.")
    _assert("Ruta estimada por distancia" in js, "Haversine route status copy missing.")
    _assert("Ruta calculada con OpenRouteService" not in js, "ORS must not add a technical route-source block.")
    _assert("emptyResultHtml" in js, "No-result helper missing.")


def test_header_has_no_support_chip_and_keeps_primary_actions() -> None:
    html = _read("static/index.html")
    js = _read("static/app.js")
    styles = _read("static/styles.css")

    combined = "\n".join([html, styles]).lower()
    removed_tokens = (
        "ko" + "-fi",
        "ko" + "-fi.com",
        "buyme" + "acoffee",
        "buy me a " + "coffee",
        "apoyar " + "fuelopt",
        "support" + "-chip",
    )
    for token in removed_tokens:
        _assert(token not in combined, f"Removed support component token remains: {token!r}")

    _assert('class="header-privacy-link"' in html, "Privacy link should be placed next to the FuelOpt wordmark.")
    _assert('class="wordmark__mark" src="/static/icons/fuelopt-48.png"' in html, "Header must display the approved FuelOpt mark.")
    _assert(".wordmark__mark" in styles, "Header brand mark CSS missing.")
    _assert(".header-privacy-link" in styles, "Header privacy link CSS missing.")
    _assert('href="/privacidad"' in html, "Privacy link should remain in the header.")
    _assert('href="/como-funciona"' in html, "How-it-works link should remain in the header.")
    issues_url = "https://github.com/miguel-pajuelo/fuel-opt-project/issues/new"
    _assert('class="feedback-chip"' in html, "Feedback action should remain in the header.")
    _assert(".feedback-chip" in styles, "Feedback action styling should remain available.")
    _assert(f'href="{issues_url}"' in html, "Feedback action must link directly to GitHub Issues.")
    _assert('target="_blank"' in html, "GitHub Issues link must open in a new tab.")
    _assert('rel="noopener noreferrer"' in html, "GitHub Issues link must isolate window.opener.")
    _assert('aria-label="Mándanos tu idea en GitHub (se abre en una pestaña nueva)"' in html, "GitHub Issues link needs an accessible external-link name.")
    _assert('<span class="feedback-chip__main">Mándanos tu idea</span>\n        </a>' in html, "GitHub Issues action must be a correctly closed anchor.")
    _assert(f'{issues_url}?' not in html, "GitHub Issues link must not include collected or personal query parameters.")

    removed_feedback_tokens = (
        "feedback_overlay",
        "feedback_email",
        "feedback_message",
        "feedback_submit",
        "feedback_success",
        "initFeedbackModal",
        "fetch('/feedback'",
        ".feedback-overlay",
        ".feedback-modal",
        ".feedback-field",
        ".feedback-input",
        ".feedback-submit",
    )
    combined_feedback = "\n".join([html, js, styles])
    for token in removed_feedback_tokens:
        _assert(token not in combined_feedback, f"Removed feedback form token remains: {token!r}")


def test_first_opening_quick_help_is_accessible_and_non_blocking() -> None:
    html = _read("static/index.html")
    js = _read("static/app.js")
    styles = _read("static/styles.css")

    _assert('<dialog class="onboarding-dialog" id="quick_help_dialog"' in html, "Quick help should use a native dialog.")
    _assert('aria-labelledby="quick_help_title"' in html, "Quick help title must label the dialog.")
    _assert('aria-describedby="quick_help_intro"' in html, "Quick help introduction must describe the dialog.")
    _assert("Empieza a ahorrar con FuelOpt" in html, "Quick help title is missing.")
    for step in ("Elige el lugar", "Configura tu búsqueda", "Compara los resultados"):
        _assert(step in html, f"Quick help step is missing: {step}")
    _assert('id="quick_help_start"' in html and ">Empezar</button>" in html, "Quick help primary action is missing.")
    _assert('id="quick_help_trigger"' in html and "Ayuda rápida" in html, "Manual quick-help access is missing.")
    video_tag = re.search(r'<video\b(?P<attrs>[^>]*)id="quick_help_video"(?P<tail>[^>]*)>', html)
    _assert(video_tag, "Quick help promotional video is missing.")
    video_attrs = video_tag.group("attrs") + video_tag.group("tail")
    for required in ("autoplay", "muted", "loop", "controls", 'preload="auto"', "playsinline", 'poster="/static/icons/fuelopt-512.png"'):
        _assert(required in video_attrs, f"Quick help video attribute is missing: {required}")
    _assert('<source src="/static/media/fuelopt-tutorial.mp4" type="video/mp4">' in html, "Quick help video source is missing.")
    _assert('id="quick_help_video_fallback"' in html and "Abrir el vídeo directamente" in html, "Quick help video fallback is missing.")
    tutorial_video = ROOT / "static" / "media" / "fuelopt-tutorial.mp4"
    _assert(tutorial_video.is_file() and tutorial_video.stat().st_size > 0, "Tutorial video asset is missing or empty.")

    _assert("fuelopt:onboarding:v1:dismissed" in js, "Quick help storage key must be versioned.")
    _assert("window.localStorage.getItem(ONBOARDING_STORAGE_KEY)" in js, "Quick help should read its dismissed state.")
    _assert(
        "window.localStorage.setItem(ONBOARDING_STORAGE_KEY, installInstanceId || 'true')" in js,
        "Automatic dismissal should persist the install ID with the legacy true fallback.",
    )
    _assert(js.count("catch (_error)") >= 2, "Quick help storage access must tolerate failures.")
    _assert("if (!wasQuickHelpDismissed())" in js, "Quick help should only open automatically before dismissal.")
    _assert("openQuickHelp({ automatic: true })" in js, "First-opening quick help should be marked as automatic.")
    _assert("openQuickHelp({ opener: trigger })" in js, "Quick help should be manually reopenable.")
    _assert("if (openedAutomatically) rememberQuickHelpDismissal()" in js, "Only an automatic opening should persist dismissal.")
    _assert("dialog.addEventListener('cancel'" in js and "event.preventDefault()" in js, "Escape dismissal must be handled deliberately.")
    _assert("returnFocusTarget" in js and "focusTarget.focus()" in js, "Focus should return to the opening control.")
    _assert("closeButton.focus()" in js, "Focus should move into the dialog when it opens.")
    _assert("video.addEventListener('error'" in js, "Video load failures must reveal the fallback.")
    _assert("video.pause()" in js, "Closing quick help must pause the video.")
    _assert("video.currentTime = 0" in js, "Quick help must restart the video from the beginning.")
    _assert("video.muted = true" in js, "Quick help autoplay must begin muted.")
    _assert("const playPromise = video.play()" in js and "playPromise.catch" in js, "Quick help must handle blocked autoplay without errors.")
    _assert(".onboarding-dialog::backdrop" in styles, "Quick help needs a visually subdued backdrop.")
    _assert("width: min(95vw, 1200px)" in styles, "Desktop quick help must use the compact wide layout.")
    _assert("max-height: 90dvh" in styles, "Desktop quick help must remain inside the viewport.")
    _assert("overflow-x: hidden" in styles, "Quick help must prevent horizontal overflow.")
    _assert("aspect-ratio: 16 / 9" in styles and "object-fit: contain" in styles, "Quick help video must retain its full 16:9 frame.")
    _assert("grid-template-columns: minmax(0, 1.55fr) minmax(320px, .85fr)" in styles, "Desktop quick help must prioritize the video column.")
    _assert(
        ".tutorial-brand {\n  display: flex;\n  flex-direction: row;\n  align-items: center;\n  gap: 12px;" in styles,
        "Tutorial branding must form a compact horizontal heading.",
    )
    _assert("width: min(88%, 380px)" in styles and "justify-self: center" in styles, "Quick help action must use a centered controlled width.")
    _assert("padding-right: 72px" in styles, "Desktop quick-help title must reserve a safe area for the close button.")
    _assert("width: 44px" in styles and "height: 44px" in styles and "z-index: 10" in styles, "Quick-help close control must retain a safe accessible target.")
    _assert("font-size: 17px" in styles and "font-weight: 800" in styles, "Quick-help step headings need stronger visual hierarchy.")
    _assert("font-size: 14px" in styles and "font-weight: 600" in styles, "Quick-help step descriptions need improved readability.")
    _assert("body:has(.onboarding-dialog[open])" in styles, "The page must remain scroll-locked while quick help is open.")
    _assert('grid-template-areas:\n    "brand title"\n    "video intro"\n    "video steps"\n    "video action"' in styles, "Desktop quick help grid areas are missing.")
    _assert(".tutorial-main {\n  display: contents;" in styles, "Quick help title and brand must share the top grid row.")
    _assert(html.count('class="tutorial-brand"') == 1, "Quick help must render the brand only once.")
    _assert(html.index('class="tutorial-header"') < html.index('class="tutorial-main"'), "Quick help brand header must precede the two-column content.")
    _assert("max-height: 68dvh" in styles, "Tutorial video must retain a useful viewport-relative height limit.")
    _assert("@media (max-width: 800px)" in styles, "Quick help responsive breakpoint is missing.")
    _assert("width: min(94vw, 560px)" in styles and "max-height: 92dvh" in styles, "Mobile quick help sizing is missing.")
    dialog_rule = re.search(r"\.onboarding-dialog\s*\{(?P<body>[^}]*)\}", styles)
    _assert(dialog_rule and "font-family: inherit" in dialog_rule.group("body"), "Quick help must use the app typography.")
    primary_rule = re.search(r"\.onboarding-dialog__primary\s*\{(?P<body>[^}]*)\}", styles)
    _assert(primary_rule and "background: var(--gold)" in primary_rule.group("body"), "Quick help CTA must use the app gold treatment.")

    onboarding_start = js.find("(function initQuickHelp()")
    onboarding_end = js.find("let refreshMessageTimer", onboarding_start)
    map_start = js.find("const map = L.map")
    onboarding_js = js[onboarding_start:onboarding_end]
    _assert(0 <= onboarding_start < onboarding_end < map_start, "Quick help must initialize before map and data startup.")
    _assert("await " not in onboarding_js, "Opening quick help must not wait for startup work.")
    _assert("fetch(" not in onboarding_js and "loadOptions" not in onboarding_js, "Quick help must not issue or restart data requests.")
    _assert("Cargando marcas" in html and "renderBrandsLoading" in js, "Existing brand loading feedback must remain available behind quick help.")

    tutorial_html = html[html.find('<dialog class="onboarding-dialog"'):html.find("</dialog>")]
    for forbidden in ("API", "ORS", "Haversine", "base de datos", "backend", "algoritmo"):
        _assert(forbidden.lower() not in tutorial_html.lower(), f"Quick help contains a technical term: {forbidden}")


def test_quick_help_is_scoped_to_the_install_instance() -> None:
    html = _read("static/index.html")
    js = _read("static/app.js")
    launcher = _read("fuelopt_launcher.py")

    _assert(js.count("fuelopt:onboarding:v1:dismissed") == 1, "Onboarding must keep the existing storage key only.")
    _assert("window.location.hash" in js and "new URLSearchParams(fragment)" in js, "Install ID must come from the URL fragment.")
    _assert("window.history.replaceState" in js, "Install ID fragment must be removed from the address bar.")
    _assert("fragmentValues.delete(INSTALL_INSTANCE_FRAGMENT)" in js, "Consumed install ID must not remain in the fragment.")
    _assert("dismissedFor === installInstanceId" in js, "Dismissal must be scoped to the current install ID.")
    _assert("dismissedFor === 'true'" in js, "Source and no-ID contexts must retain the legacy fallback.")
    _assert("installInstanceId || 'true'" in js, "Dismissal write must retain the legacy fallback.")

    _assert("#fuelopt-install=" not in launcher, "Launcher fragment must use the shared constant, not a duplicated literal.")
    _assert("#{INSTALL_INSTANCE_FRAGMENT}={encoded}" in launcher, "Launcher must put the install ID in a fragment.")
    _assert("?fuelopt-install=" not in launcher, "Install ID must never be added to the query string.")
    _assert("browser opened url=" not in launcher, "Browser URL containing the install ID must not be logged.")
    _assert('UI_CACHE_REVISION = "tutorial-playback-v3"' in launcher, "Launcher needs a non-personal UI cache revision.")
    _assert("fuelopt-ui" in launcher, "Launcher must request the revised local UI URL.")
    _assert("/static/styles.css?v=tutorial-step-type-v8" in html, "Critical CSS needs the revised cache key.")
    _assert("/static/app.js?v=tutorial-playback-v3" in html, "Critical JS needs the revised cache key.")


def test_sidebar_and_floating_search_layout() -> None:
    html = _read("static/index.html")
    styles = _read("static/styles.css")
    js = _read("static/app.js")
    combined = "\n".join([html, styles, js])
    _assert("config_sidebar" in html, "Left configuration sidebar should exist.")
    controls_rule = re.search(r"\.controls\s*\{(?P<body>[^}]*)\}", styles)
    _assert(controls_rule and "padding-right: 12px" in controls_rule.group("body"), "Scrollable sidebar content needs clearance from its scrollbar.")
    _assert(controls_rule and "overflow-x: hidden" in controls_rule.group("body"), "Sidebar clearance must not introduce horizontal scrolling.")
    _assert("floating-sidebar" in html, "Sidebar should use the compact floating visual treatment.")
    _assert("Llena tu depósito" in html, "Sidebar headline should match the target visual direction.")
    _assert("Ahorra en cada repostaje" not in html, "Temporary sidebar headline should not remain.")
    _assert("Salida" not in html[html.find('id="config_sidebar"'):html.find('class="stage')], "Sidebar should not contain a route origin block.")
    _assert("sidebar_toggle" not in html, "Sidebar toggle should not exist in map-first UI.")
    _assert("refresh_catalog" not in html, "Manual catalog refresh button should not exist in the UI.")
    _assert("refresh-button" not in combined, "Manual refresh button styling should not remain.")
    _assert("/catalog/refresh" not in js, "Frontend JS must not call the manual catalog refresh endpoint.")
    _assert("forceCatalogRefresh" not in js, "Manual refresh handler should be removed.")
    _assert('href="/docs"' not in html and ">Docs<" not in html, "Docs should not be linked from the frontend header.")
    _assert('href="/health"' not in html and ">Health<" not in html, "Health should not be linked from the frontend header.")
    _assert('href="/privacidad"' in html, "Privacy link should remain in the header.")
    _assert("floating-search" in html, "Floating top search bar missing.")
    _assert("route-search-bar" in html, "Route search bar structure missing.")
    _assert("route-input-slot" in html, "Search input should live inside the active route point.")
    search_html = html[html.find('class="map-top'):html.find('id="route_status"')]
    _assert("return_to_origin" in search_html, "Return-to-origin toggle should be inside the floating search UI.")
    _assert("price-chip" in html, "Discreet price freshness chip missing.")
    _assert("return_to_origin" in html, "Return-to-origin toggle missing.")
    _assert("return-toggle-compact" in html, "Return-to-origin toggle should be integrated with the search bar.")
    _assert("destination_block" in html, "Destination block should still exist for one-way trips.")
    _assert("syncReturnMode" in js, "Return mode synchronizer missing.")
    _assert("setActive(same ? 'origin' : 'destination')" in js, "Return mode should switch active search point.")


def test_app_js_renders_warnings() -> None:
    js = _read("static/app.js")
    _assert("function renderWarnings" in js, "renderWarnings helper missing.")
    _assert("result-warning--info" in js, "Info warning class missing from JS.")
    _assert("result-warning--warning" in js, "Warning class missing from JS.")
    _assert("result-warning--critical" in js, "Critical warning class missing from JS.")
    _assert("warningByCode(warnings, 'brand_filter_too_restrictive')" in js, "Brand filter warning should drive duplicate warning suppression.")
    _assert("hiddenCodes.add('independent_brands_excluded_or_hidden')" in js, "Independent brand warning should be hidden when brand filter warning is visible.")


def test_haversine_copy_appears_once() -> None:
    js = _read("static/app.js")
    _assert(
        js.count("Ruta estimada por distancia") == 1,
        "Haversine copy should appear once, only as structured warning.",
    )
    _assert(
        js.count("El coste de ruta se ha calculado con una aproximación de distancia.") == 1,
        "Plain-language approximate route message should appear once.",
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
    _assert("metric-value-row--price" in js, "Price metric value and warning icon should render in a dedicated row.")
    _assert("warning-triangle" in js, "Reusable warning triangle markup missing from JS.")
    _assert("warning-triangle__svg" in js, "Warning triangle should use inline SVG.")
    _assert("<polygon" in js and "warning-triangle__shape" in js, "Warning triangle SVG polygon is missing.")
    _assert("warning-triangle__bar" in js and "warning-triangle__dot" in js, "Warning triangle exclamation mark is missing.")
    _assert("⚠️" not in js and "⚠" not in js, "Warning triangle must not use emoji.")
    _assert("⚠" not in js, "Price warning must not use the native warning emoji.")
    _assert("Fecha oficial no disponible" in js, "Missing official date tooltip title missing.")
    _assert("MINETUR no informa una fecha oficial por precio. El cálculo usa los últimos datos descargados por FuelOpt." in js, "Missing official date tooltip copy missing.")
    _assert("Se recomienda refrescar los datos" not in js, "Stale price tooltip should not recommend refreshing.")
    _assert("catalog_degraded" in js, "Catalog degraded code should be filtered by JS.")
    _assert(".price-warning" in styles, "Price warning marker styles missing.")
    _assert(".metric-value-row" in styles, "Price metric value row styles missing.")
    _assert(".metric-value-row--price" in styles, "Price metric value row modifier styles missing.")
    _assert(".warning-triangle" in styles, "Triangular warning icon styles missing.")
    _assert(".warning-triangle__svg" in styles, "Triangular warning SVG styles missing.")
    _assert(".warning-triangle__shape" in styles, "Triangular warning shape styles missing.")
    _assert(".warning-triangle__bar" in styles and ".warning-triangle__dot" in styles, "Warning SVG mark styles missing.")
    _assert(".warning-triangle::before" not in styles and ".warning-triangle::after" not in styles, "Warning triangle should not use pseudo-elements.")
    _assert(".price-warning-icon::before" not in styles and ".price-warning-icon::after" not in styles, "Legacy warning icon pseudo-elements should be removed.")
    _assert("z-index: -1" not in styles and "z-index: -2" not in styles, "Warning triangle must not use negative z-index.")
    _assert("⚠️" not in styles and "⚠" not in styles, "Warning triangle styles must not rely on emoji.")
    _assert("⚠" not in styles, "Warning triangle styles must not rely on a native warning emoji.")
    _assert(".price-warning-tooltip" in styles, "Price warning tooltip styles missing.")
    metrics_rule = re.search(r"\.metrics\s*\{(?P<body>[^}]*)\}", styles)
    _assert(metrics_rule and "overflow: visible" in metrics_rule.group("body"), "Metrics grid should not clip the price warning tooltip.")
    metric_rule = re.search(r"\.metric\s*\{(?P<body>[^}]*)\}", styles)
    _assert(metric_rule and "overflow: visible" in metric_rule.group("body"), "Metric cards should not clip warning tooltips.")
    price_metric_rule = re.search(r"\.metric--price\s*\{(?P<body>[^}]*)\}", styles)
    _assert(price_metric_rule and "z-index" in price_metric_rule.group("body"), "Price metric should stack above sibling cards while showing its tooltip.")
    tooltip_rule = re.search(r"\.price-warning-tooltip\s*\{(?P<body>[^}]*)\}", styles)
    _assert(tooltip_rule and "z-index: 200" in tooltip_rule.group("body"), "Price warning tooltip should stack above metric cards.")
    _assert(tooltip_rule and "top: calc(100% + 8px)" in tooltip_rule.group("body"), "Price warning tooltip should open below the warning icon.")
    _assert(tooltip_rule and "right: 0" in tooltip_rule.group("body"), "Price warning tooltip should open inward from the right edge of the price row.")
    _assert(tooltip_rule and "left: auto" in tooltip_rule.group("body"), "Price warning tooltip should not force a left anchor that can overflow right.")
    price_warning_rule = re.search(r"\.price-warning,\s*\n\.metric-value-row--price \.price-warning\s*\{(?P<body>[^}]*)\}", styles)
    _assert(price_warning_rule and "overflow: visible" in price_warning_rule.group("body"), "Price warning must allow the tooltip to overflow visibly.")


def test_app_js_handles_virtual_brand() -> None:
    js = _read("static/app.js")
    styles = _read("static/styles.css")
    _assert("is_virtual" in js or "__INDEPENDENT__" in js, "Virtual brand handling missing from JS.")
    _assert("brand-check--virtual" in js, "Virtual brand class missing from JS.")
    _assert(".brand-check--virtual" in styles, "Virtual brand class missing from CSS.")
    _assert(".brand-hint" in styles, "Virtual brand hint style missing from CSS.")
    _assert("function excludedBrands" in js, "excludedBrands helper missing for all-except brand filtering.")
    _assert("payload.excluded_brands = excluded" in js, "Optimize payload should support brand exclusions.")


def test_map_has_user_location_control() -> None:
    js = _read("static/app.js")
    styles = _read("static/styles.css")
    _assert("function initUserLocationControl" in js, "User location Leaflet control missing.")
    _assert("navigator.geolocation.getCurrentPosition" in js, "User location control should use browser geolocation on click.")
    _assert("renderUserLocation" in js, "User location marker rendering missing.")
    _assert("userLocationMarker" in js, "User location marker should be tracked and reused.")
    _assert("userLocationAccuracyCircle" in js, "User location accuracy circle should be tracked and reused.")
    _assert("const lat = Number(coords.latitude)" in js, "User location should use latitude returned by Geolocation API.")
    _assert("const lon = Number(coords.longitude)" in js, "User location should use longitude returned by Geolocation API.")
    _assert("const accuracy = Number(coords.accuracy)" in js, "User location should use accuracy returned by Geolocation API.")
    _assert("function focusUserLocation" in js, "User location focus helper missing.")
    _assert("USER_LOCATION_MIN_GOOD_ACCURACY_ZOOM" in js, "User location fallback zoom constant missing.")
    _assert("USER_LOCATION_MAX_ZOOM" in js, "User location maximum zoom constant missing.")
    _assert("USER_LOCATION_PADDING" in js, "User location fit padding constant missing.")
    _assert("L.latLng(latLng).toBounds(accuracy * 2)" in js, "User location should derive bounds from the accuracy radius without a temporary map layer.")
    _assert("map.fitBounds(bounds" in js, "User location should fit the whole accuracy circle.")
    _assert("padding: USER_LOCATION_PADDING" in js, "User location fit should use padding.")
    _assert("maxZoom: Math.min(maxZoom, USER_LOCATION_MAX_ZOOM)" in js, "User location fit should cap maximum zoom.")
    _assert("map.getMaxZoom" in js, "User location zoom should respect the map maximum zoom.")
    _assert("map.flyTo(latLng, Math.min(maxZoom, USER_LOCATION_MIN_GOOD_ACCURACY_ZOOM)" in js, "User location without accuracy should still focus the map.")
    _assert("enableHighAccuracy: true" in js, "Geolocation should request high accuracy.")
    _assert("maximumAge: 0" in js, "Geolocation should not reuse cached positions.")
    _assert("FuelOpt geolocation result" in js, "Geolocation debug log missing.")
    _assert("fallback_used: false" in js, "Geolocation logs should state no fallback was used.")
    _assert("Ubicación aproximada: precisión baja." in js, "Low accuracy location warning missing.")
    _assert("Permiso de ubicación denegado." in js, "Geolocation permission error copy missing.")
    _assert("Tu navegador no soporta geolocalización." in js, "Unsupported geolocation copy missing.")
    _assert(".user-location-control" in styles, "User location control styles missing.")
    _assert(".user-location-button" in styles, "User location button styles missing.")


def test_map_controls_share_layout_anchor() -> None:
    styles = _read("static/styles.css")
    _assert("--map-control-left" in styles, "Map controls should share a left anchor variable.")
    _assert("--map-control-size" in styles, "Map controls should share a size variable.")
    _assert("--map-control-gap" in styles, "Map controls should share a vertical gap variable.")
    _assert("left: var(--map-control-left)" in styles, "Leaflet controls should use the shared left anchor.")
    _assert("bottom: var(--map-control-bottom)" in styles, "Leaflet controls should use the shared bottom anchor.")
    control_column = re.search(r"\.leaflet-bottom\.leaflet-left\s*\{(?P<body>[^}]*)\}", styles)
    _assert(control_column, "Leaflet bottom-left controls should define a shared column.")
    column_body = control_column.group("body")
    _assert("display: flex" in column_body, "Map controls should be laid out as one column.")
    _assert("flex-direction: column" in column_body, "Geolocation should appear above zoom in the shared column.")
    _assert("gap: var(--map-control-gap)" in column_body, "Map control column should use the shared gap.")
    _assert("background: transparent" in column_body, "Shared map control wrapper should not paint a visible background.")
    _assert("box-shadow: none" in column_body, "Shared map control wrapper should not add a visible capsule shadow.")
    margin_reset = re.search(r"\.leaflet-bottom\.leaflet-left \.leaflet-control\s*\{(?P<body>[^}]*)\}", styles)
    _assert(margin_reset and "margin: 0" in margin_reset.group("body"), "Leaflet control margins should be reset in the shared column.")
    zoom_rule = re.search(r"\.leaflet-left \.leaflet-control-zoom\s*\{(?P<body>[^}]*)\}", styles)
    _assert(zoom_rule, "Zoom control should have a dedicated visual rule.")
    zoom_body = zoom_rule.group("body")
    _assert("background: var(--paper-strong)" in zoom_body, "Zoom control should paint its own solid surface.")
    _assert("overflow: hidden" in zoom_body, "Zoom control should clip its joined buttons cleanly.")
    _assert(".leaflet-touch .leaflet-bar a,\n.leaflet-bar a" in styles, "Zoom buttons should override Leaflet touch sizing.")
    _assert("margin-left: 6px" not in styles, "Map controls should not use a separate lateral offset.")
    _assert("margin-bottom: 220px" not in styles, "User location should not be hand-positioned above zoom.")
    _assert("width: var(--map-control-size)" in styles, "Map controls should align to the shared visual width.")


def test_sidebar_dropdown_stacks_above_brands() -> None:
    styles = _read("static/styles.css")

    open_field_rule = re.search(r"\.config-field:has\(\.pdd\.is-open\)\s*\{(?P<body>[^}]*)\}", styles)
    _assert(open_field_rule, "Open dropdown field should create a local stacking context.")
    _assert("z-index: 80" in open_field_rule.group("body"), "Open dropdown field should stack above brand rows.")

    open_dropdown_rule = re.search(r"\.pdd\.is-open\s*\{(?P<body>[^}]*)\}", styles)
    _assert(open_dropdown_rule, "Open custom dropdown rule missing.")
    _assert("z-index: 90" in open_dropdown_rule.group("body"), "Open custom dropdown should stack above sidebar content.")

    menu_rule = re.search(r"\.pdd-menu\s*\{(?P<body>[^}]*)\}", styles)
    _assert(menu_rule, "Custom dropdown menu rule missing.")
    menu_body = menu_rule.group("body")
    _assert("z-index: 200" in menu_body, "Dropdown menu should have a high local z-index.")
    _assert("visibility: hidden" in menu_body, "Closed dropdown menu should be hidden without relying on zero height.")
    _assert("max-height: 260px" in menu_body, "Dropdown menu should keep a bounded scroll height.")

    controls_open_rule = re.search(r"\.controls:has\(\.pdd\.is-open\)\s*\{(?P<body>[^}]*)\}", styles)
    _assert(controls_open_rule, "Controls should allow an open dropdown to overflow visibly.")
    controls_open_body = controls_open_rule.group("body")
    _assert("overflow: visible" in controls_open_body, "Controls should not clip an open dropdown.")
    _assert("z-index: 20" in controls_open_body, "Controls should stack above the sidebar footer while a dropdown is open.")

    brand_section_rule = re.search(r"\.brand-section\s*\{(?P<body>[^}]*)\}", styles)
    _assert(brand_section_rule, "Brand section stacking rule missing.")
    _assert("z-index: 1" in brand_section_rule.group("body"), "Brand section should stay below open dropdowns.")

    brand_grid_rule = re.search(r"\.brand-grid\s*\{(?P<body>[^}]*)\}", styles)
    _assert(brand_grid_rule, "Brand grid rule missing.")
    _assert("z-index" not in brand_grid_rule.group("body"), "Brand grid should not create a high stacking context.")

    brand_check_rule = re.search(r"\.brand-check\s*\{(?P<body>[^}]*)\}", styles)
    _assert(brand_check_rule, "Brand check rule missing.")
    _assert("z-index" not in brand_check_rule.group("body"), "Brand rows should not stack above open dropdowns.")
    _assert(
        ".pdd.is-open > .pdd-menu" in styles and "visibility: visible" in styles,
        "Open dropdown menu should be made visible with a direct-child rule.",
    )


def test_result_panel_layout_and_alternatives_state() -> None:
    js = _read("static/app.js")
    styles = _read("static/styles.css")
    _assert("--result-panel-top" in styles, "Result panel should define a top offset below the search bar.")
    _assert("--result-panel-bottom" in styles, "Result panel should reserve viewport bottom space.")
    result_rule = re.search(r"\.result\s*\{(?P<body>[^}]*)\}", styles)
    _assert(result_rule, "Result panel style rule missing.")
    result_body = result_rule.group("body")
    _assert("bottom: var(--result-panel-bottom)" in result_body, "Result panel should be anchored to the viewport bottom.")
    _assert("top: auto" in result_body, "Result panel should grow upward from its bottom anchor.")
    _assert("top: var(--result-panel-top)" not in result_body, "Result panel should not use a fixed top as its primary anchor.")
    _assert("max-height: calc(100svh - var(--result-panel-top) - var(--result-panel-bottom))" in result_body, "Result panel should cap height within viewport.")
    _assert("overflow-y: auto" in result_body, "Result panel should use internal vertical scroll for long content.")
    _assert("overflow-x: hidden" in result_body, "Result panel should prevent horizontal overflow.")
    _assert("overscroll-behavior: contain" in result_body, "Result panel scroll should be contained.")
    _assert(".result,\n.result *" in styles and "box-sizing: border-box" in styles, "Result panel children should use border-box sizing.")
    _assert(".result-panel--expanded" in styles, "Expanded result panel state class missing.")
    _assert(".result-panel--collapsed" in styles, "Collapsed result panel state class missing.")
    _assert("function setResultAlternativesState" in js, "Alternatives state sync helper missing.")
    _assert("Coste total estimado" in js, "Result panel should promote effective cost as the main metric.")
    _assert("Mejor opción encontrada" not in js, "Result panel should not show the old redundant headline.")
    _assert("Otras alternativas" in js, "Alternatives section header should use the updated copy.")
    _assert("function renderSelectedStationSummary" in js, "Selected station summary helper missing.")
    _assert("stationLogoHtml(station)" in js, "Selected station summary should render the station logo.")
    _assert("brandLogoFor(" in js and "BRAND_LOGO_FALLBACK" in js, "Result panel should reuse brand logo mapping with fallback.")
    _assert("data-open-maps" in js, "Selected station should include the Maps button hook.")
    _assert("Abrir en Maps" in js, "Selected station Maps button copy is missing.")
    _assert(".station-maps-button" in styles, "Selected station Maps button styling is missing.")
    _assert("function hasValidCoords(place)" in js, "Maps helper should validate coordinates.")
    _assert("function formatMapsPlace(place)" in js, "Maps helper should format coordinates or text fallback.")
    _assert("function buildGoogleMapsDirectionsUrl" in js, "Maps button should build full directions URLs.")
    _assert("google.com/maps/dir" in js, "Maps button should generate a Google Maps directions URL.")
    _assert("travelmode=driving" in js, "Maps URL should request driving directions.")
    _assert("waypoints" in js, "Maps route should use the selected station as a waypoint when possible.")
    _assert("returnToOrigin ? originPlace" in js, "Maps route should support origin-station-origin trips.")
    _assert("encodeURIComponent(value)" in js, "Maps route params should be URL encoded.")
    _assert("data-maps-url" in js, "Maps button should store the generated route URL.")
    _assert("window.open(mapsUrl, '_blank', 'noopener,noreferrer')" in js, "Maps button should open safely in a new tab.")
    _assert("function renderAlternativesList" in js, "Compact alternatives list helper missing.")
    _assert("function renderAlternativesList(alternatives, isBudgetMode)" in js, "Alternatives list should render compact result rows.")
    _assert(".filter(({ index }) => index !== selectedIndex)" in js, "The main result must not be repeated among alternatives.")
    _assert("const visibleAlternatives = alternatives.slice(0, 2)" in js, "The next two alternatives must be visible by default.")
    _assert("const additionalAlternatives = alternatives.slice(2)" in js, "Only later alternatives should be expandable.")
    _assert("Ver más alternativas" in js and "Ver menos alternativas" in js, "Additional alternatives need a clear opener.")
    _assert("const alternativesScrollTop = panel?.scrollTop || 0" in js, "Expanded alternative click should preserve internal scroll position.")
    _assert("restoredPanel.scrollTop = alternativesScrollTop" in js, "Alternative scroll position should be restored after rerender.")
    _assert(".ranking--preview" in styles, "Visible alternative rows need a permanent preview region.")
    _assert(".alternatives-more-toggle" in styles, "Additional alternatives opener styling is missing.")
    _assert("classList.toggle('result-panel--expanded', isOpen)" in js, "Expanded state should be toggled by alternatives helper.")
    _assert("classList.toggle('result-panel--collapsed', !isOpen)" in js, "Collapsed state should be toggled by alternatives helper.")
    _assert("function renderResult(data, selectedIndex = 0, keepAlternativesOpen = false)" in js, "Alternatives should be closed by default in renderResult.")
    _assert("renderResult(data, 0, false)" in js, "Optimization should render alternatives collapsed initially.")
    _assert("const alternativesOpen = additionalAlternatives.length > 0 && keepAlternativesOpen" in js, "Only additional alternatives should be expandable.")
    _assert("panel.classList.toggle('collapsed', !isOpen)" in js, "Alternatives list should collapse without leaving a placeholder.")
    ranking_rule = re.search(r"\.ranking\s*\{(?P<body>[^}]*)\}", styles)
    _assert(ranking_rule, "Alternatives ranking style rule missing.")
    ranking_body = ranking_rule.group("body")
    _assert("min-height: 0" in ranking_body, "Alternatives list should allow flex shrinking to cap its own height.")
    _assert("overflow-y: auto" in ranking_body, "Alternatives list should scroll vertically when long.")
    _assert("overflow-x: hidden" in ranking_body, "Alternatives list should not create a horizontal scrollbar.")
    rank_rule = re.search(r"\.rank\s*\{(?P<body>[^}]*)\}", styles)
    _assert(rank_rule and "min-width: 0" in rank_rule.group("body"), "Alternative rows should be allowed to shrink within the panel.")


def test_route_fit_uses_visible_map_area() -> None:
    js = _read("static/app.js")

    # Core function exists
    _assert("function fitRouteToUsableViewport" in js, "Route fitting should use fitRouteToUsableViewport helper.")

    # getBoundingClientRect is used inside (within the implementation block)
    fit_start = js.find("function fitRouteToUsableViewport")
    fit_region = js[fit_start:fit_start + 3000] if fit_start != -1 else ""
    padding_start = js.find("function routeVisiblePadding")
    padding_region = js[padding_start:padding_start + 3000] if padding_start != -1 else ""
    _assert(
        "getBoundingClientRect" in padding_region,
        "getBoundingClientRect should be used inside routeVisiblePadding (called by fitRouteToUsableViewport).",
    )

    # Correct fitBounds padding keys
    _assert("paddingTopLeft: [padding.left, padding.top]" in js, "Route fit should use asymmetric top-left padding.")
    _assert("paddingBottomRight: [padding.right, padding.bottom]" in js, "Route fit should use asymmetric bottom-right padding.")

    # Overlay selectors referenced near the padding function
    _assert("config_sidebar" in padding_region, "Route padding should reference the left sidebar.")
    _assert("result" in padding_region, "Route padding should reference the result panel.")

    # Double-rAF call site exists
    _assert(
        "requestAnimationFrame(() => requestAnimationFrame(() => fitRouteToUsableViewport" in js,
        "At least one fitRouteToUsableViewport call site should use double-rAF for post-render accuracy.",
    )

    # maxZoom capped at ≤ 16
    import re as _re
    zoom_matches = _re.findall(r"maxZoom\s*:\s*(\d+)", js)
    _assert(
        any(int(z) <= 16 for z in zoom_matches),
        "fitBounds call should set maxZoom ≤ 16.",
    )

    # Bounds include all three route points
    _assert("extendBoundsWithPoint(bounds, state.origin)" in js, "Route bounds should include the origin point.")
    _assert("extendBoundsWithPoint(bounds, state.selectedStation)" in js, "Route bounds should include the selected station.")
    _assert("extendBoundsWithPoint(bounds, state.destination)" in js, "Route bounds should include the destination point.")

    # Refit on alternatives toggle and on window resize
    _assert("refitVisibleRoute(320)" in js, "Alternatives expand/collapse should re-fit after the panel transition.")
    _assert("window.addEventListener('resize', scheduleMapViewportRefresh)" in js, "Window resize should refresh route fitting.")

    # Competing station pan must not be present alongside an optimized route fit
    _assert("scheduleStationFocus(station, 0)" not in js, "Station panning should not compete with optimized route fitting.")


def test_route_layer_cleared_before_async_fetch() -> None:
    js = _read("static/app.js")

    # 1. The helper function exists
    _assert(
        "function clearCurrentRouteLayer" in js,
        "clearCurrentRouteLayer helper is missing from app.js.",
    )

    # 2. The helper is called synchronously BEFORE the async refreshSelectedRoute
    #    inside the renderResult canDrawRoute branch.
    #    We check that clearCurrentRouteLayer() appears before refreshSelectedRoute
    #    in the relevant code block.
    can_draw_block_start = js.find("if (canDrawRoute)")
    _assert(can_draw_block_start != -1, "canDrawRoute branch missing from renderResult.")
    can_draw_block = js[can_draw_block_start:can_draw_block_start + 400]
    clear_pos = can_draw_block.find("clearCurrentRouteLayer()")
    fetch_pos = can_draw_block.find("refreshSelectedRoute(")
    _assert(
        clear_pos != -1,
        "clearCurrentRouteLayer() must be called in the canDrawRoute branch.",
    )
    _assert(
        fetch_pos != -1,
        "refreshSelectedRoute() must be called in the canDrawRoute branch.",
    )
    _assert(
        clear_pos < fetch_pos,
        "clearCurrentRouteLayer() must appear before refreshSelectedRoute() in the canDrawRoute branch.",
    )

    # 3. A request sequencing variable exists (state.routeRequestId is used)
    _assert(
        "routeRequestId" in js,
        "Route request sequencing variable (routeRequestId) is missing.",
    )

    # 4. The stale-response guard exists in the async path
    _assert(
        "requestId !== state.routeRequestId" in js,
        "Stale response guard (requestId !== state.routeRequestId) missing from route async path.",
    )

    # 5. Regression: fitRouteToUsableViewport still present (previous session)
    _assert(
        "function fitRouteToUsableViewport" in js,
        "fitRouteToUsableViewport regression: function has been removed.",
    )


def test_search_input_no_length_reset() -> None:
    """Verify there is no length-7/8 condition that can clear the search input."""
    js = _read("static/app.js")
    html = _read("static/index.html")

    # 1. No maxlength="7" or maxLength = 7 / maxLength: 7 anywhere
    _assert(
        'maxlength="7"' not in html and 'maxlength="7"' not in js,
        'map_search must not have maxlength="7".',
    )
    _assert(
        "maxLength = 7" not in js and "maxLength: 7" not in js,
        "maxLength must not be set to 7 in app.js.",
    )

    # 2. No bare "> 7" or ">= 8" near a .value = '' assignment (within 3 lines)
    lines = js.splitlines()
    for i, line in enumerate(lines):
        has_len_check = re.search(r">\s*7\b|>=\s*8\b", line)
        if not has_len_check:
            continue
        context = "\n".join(lines[max(0, i - 3):i + 4])
        _assert(
            ".value = ''" not in context and '.value = ""' not in context,
            f"Suspicious length-7/8 check near a .value='' clear at line {i + 1}: {line.strip()!r}",
        )

    # 3. #map_search is a single static node in index.html; no createElement('input') near 'map_search'
    _assert(
        html.count('id="map_search"') == 1,
        "#map_search must appear exactly once in index.html.",
    )
    create_input_pattern = re.search(r"createElement\(['\"]input['\"].*map_search|map_search.*createElement\(['\"]input['\"]", js)
    _assert(
        create_input_pattern is None,
        "app.js must not dynamically recreate the #map_search input node.",
    )

    # 4. isTyping guard exists in app.js
    _assert(
        "isTyping" in js,
        "isTyping guard must be present in app.js to protect the search input value during typing.",
    )
    _assert(
        "isTyping = true" in js,
        "isTyping must be set to true on input events.",
    )
    _assert(
        "isTyping = false" in js,
        "isTyping must be reset to false when a place is selected or the active point changes.",
    )


def test_emerald_gold_palette_applied() -> None:
    """Verifies the restrained premium gold palette is applied to key sidebar components."""
    styles = _read("static/styles.css")
    html = _read("static/index.html")
    js = _read("static/app.js")

    # 1. The UI gold is explicitly tied to the optimized route gold used in app.js.
    _assert("--emerald" in styles, "CSS variable --emerald (verde esmeralda) must be defined in :root.")
    _assert("'#9f7a3a'" in js or '"#9f7a3a"' in js, "Route polyline gold #9f7a3a must be present in app.js.")
    _assert("--route-gold: #9f7a3a" in styles, "CSS must expose the route gold as --route-gold.")
    _assert("--gold: var(--route-gold)" in styles, "UI --gold must derive from --route-gold.")
    _assert("--gold-hover: #87632b" in styles, "Gold hover must be a darker route-gold derivative.")
    _assert("--gold-soft: rgba(159, 122, 58, 0.18)" in styles, "Gold-soft translucent fill must derive from route gold.")
    _assert("--gold-border: rgba(159, 122, 58, 0.48)" in styles, "Gold border token must derive from route gold.")
    _assert("--panel: #FBF7EF" in styles, "Sidebar panel token must use #FBF7EF.")

    # 2. CTA .primary uses the premium gold token, not emerald, green, or plain black.
    primary_rule = re.search(r"\.primary\s*\{(?P<body>[^}]*)\}", styles)
    _assert(primary_rule, ".primary rule missing from CSS.")
    primary_body = primary_rule.group("body")
    _assert("var(--gold)" in primary_body, ".primary CTA button must use --gold background.")
    _assert("var(--emerald)" not in primary_body, ".primary CTA button must not use --emerald background.")
    _assert("var(--green)" not in primary_body, ".primary CTA button must not use green background.")
    _assert("var(--night)" not in primary_body, ".primary CTA button must not use plain --night background.")
    _assert("#FFF8EA" in primary_body or "#FBF7EF" in primary_body, ".primary CTA text must use a light panel color.")

    primary_hover_rule = re.search(r"\.primary:hover\s*\{(?P<body>[^}]*)\}", styles)
    _assert(primary_hover_rule, ".primary:hover rule missing from CSS.")
    _assert("var(--gold-hover)" in primary_hover_rule.group("body"), ".primary:hover must use --gold-hover.")

    # 3. Litros/Euros selector: active state uses a translucent gold fill, not solid gold.
    amount_active_rule = re.search(r"\.amount-mode-option\.active\s*\{(?P<body>[^}]*)\}", styles)
    _assert(amount_active_rule, ".amount-mode-option.active rule missing.")
    amount_active_body = amount_active_rule.group("body")
    _assert(
        "var(--gold-soft)" in amount_active_body,
        "Litros/Euros selector active state must use --gold-soft translucent fill.",
    )
    _assert(
        "var(--gold-border)" in amount_active_body,
        "Litros/Euros selector active state must use --gold-border.",
    )
    _assert(
        "var(--gold-2)" not in amount_active_body and "var(--night)" not in amount_active_body and "var(--emerald)" not in amount_active_body,
        "Litros/Euros selector active state must not use solid gold, --night, or --emerald.",
    )

    # 4. "Todas" button active state uses solid premium gold + light text.
    link_active_rule = re.search(r"\.link-button\.active\s*\{(?P<body>[^}]*)\}", styles)
    _assert(link_active_rule, ".link-button.active rule missing.")
    link_active_body = link_active_rule.group("body")
    _assert("var(--gold)" in link_active_body, "'Todas' active state must use --gold background.")
    _assert("#FFF8EA" in link_active_body or "#FBF7EF" in link_active_body, "'Todas' active state must use light text.")
    _assert("var(--emerald)" not in link_active_body, "'Todas' active state must not use --emerald.")
    _assert("var(--night)" not in link_active_body, "'Todas' active state must not use plain --night.")

    # 5. "Regreso al origen" switch (.slider) must NOT use --emerald — stays dark/black
    switch_slider_rule = re.search(r"\.switch input:checked \+ \.slider\s*\{(?P<body>[^}]*)\}", styles)
    _assert(switch_slider_rule, ".switch input:checked + .slider rule missing.")
    _assert(
        "var(--emerald)" not in switch_slider_rule.group("body"),
        "'Regreso al origen' switch (.slider) must NOT use --emerald; it must stay dark so the search bar is not recolored.",
    )

    # 6. Brand toggles in the sidebar are discrete (not emerald, not distracting)
    brand_toggle_rule = re.search(
        r"\.brand-check input:checked \+ \.brand-toggle\s*\{(?P<body>[^}]*)\}", styles
    )
    _assert(brand_toggle_rule, ".brand-check input:checked + .brand-toggle rule missing.")
    _assert(
        "var(--emerald)" not in brand_toggle_rule.group("body"),
        "Brand toggles must not use --emerald (should be a discrete neutral tone).",
    )

    # 7. No "->" text arrow in CTA button
    _assert("-&gt;" not in html, "CTA button must not use the text '->' arrow in index.html (use → instead).")
    _assert(
        "primary-arrow" not in js or "->" not in js,
        "CTA arrow must not be injected as '->' from app.js.",
    )

    # 8. Consumo medio shows l/100km unit in parentheses
    _assert(
        "(l/100km)" in html,
        "Consumo medio field must display '(l/100km)' unit in index.html.",
    )

    # 9. No brand logo asset paths added in this phase
    _assert("/static/brands/" not in js, "No brand image asset folder (/static/brands/) should be referenced in app.js.")
    _assert("/static/brands/" not in html, "No brand image asset folder (/static/brands/) should be referenced in index.html.")

    # 10. Manual refresh UI should not be reintroduced while adjusting color theory.
    _assert("refresh_catalog" not in html, "Manual refresh UI should not be reintroduced in index.html.")


def test_brand_logos_implemented() -> None:
    """Verifies brand logo infrastructure is present and correct."""
    js = _read("static/app.js")
    styles = _read("static/styles.css")

    # 1. BRAND_LOGOS map exists with local paths only
    _assert("BRAND_LOGOS" in js, "BRAND_LOGOS map must exist in app.js.")
    _assert("/static/logos/" in js, "Brand logo paths must reference /static/logos/ local folder.")
    _assert(
        "http://" not in js[js.find("BRAND_LOGOS"):js.find("BRAND_LOGOS") + 2000],
        "Brand logos must use local paths only, no external http:// URLs.",
    )
    _assert(
        "https://" not in js[js.find("BRAND_LOGOS"):js.find("BRAND_LOGOS") + 2000],
        "Brand logos must use local paths only, no external https:// URLs.",
    )

    # 2. brandLogoFor helper exists
    _assert("function brandLogoFor" in js, "brandLogoFor helper function must exist in app.js.")

    # 3. Generic fallback defined
    _assert(
        "BRAND_LOGO_FALLBACK" in js,
        "BRAND_LOGO_FALLBACK constant must exist for brands without specific logos.",
    )
    _assert(
        "generic-station" in js,
        "Generic station fallback logo must be referenced in app.js.",
    )

    # 4. __INDEPENDENT__ / unknown brands use fallback (brandLogoFor returns fallback for unknown)
    _assert(
        "BRAND_LOGOS[canonical]" in js or "BRAND_LOGOS[" in js,
        "brandLogoFor must look up BRAND_LOGOS by canonical key.",
    )
    _assert("normalizeBrandLogoKey" in js, "brandLogoFor should normalize brand variants before falling back.")
    _assert("brand.brand_canonical" in js, "brandLogoFor should inspect station brand_canonical.")
    _assert("normalized.startsWith(`${normalizedKey} `)" in js, "Brand logo resolver should match prefixed variants such as BEROIL VILLANUBLA.")
    _assert("const logoSrc = brandLogoFor(station)" in js, "Result station logo should pass the full station object.")

    # 5. renderBrands includes <img element
    render_start = js.find("function renderBrands")
    render_region = js[render_start:render_start + 2000] if render_start != -1 else ""
    _assert(
        "<img " in render_region,
        "renderBrands must include an <img element for brand logos.",
    )
    _assert(
        "onerror" in render_region,
        "renderBrands img must have an onerror fallback handler.",
    )
    _assert(
        "loading=\"lazy\"" in render_region or "loading='lazy'" in render_region,
        "renderBrands img must use lazy loading.",
    )

    # 6. CSS class for logo exists
    _assert(".brand-logo" in styles, "CSS class .brand-logo must be defined in styles.css.")
    _assert(".brand-logo-frame" in styles, "CSS class .brand-logo-frame must be defined in styles.css.")
    _assert(
        "object-fit: contain" in styles,
        "Brand logo must use object-fit: contain to avoid distortion.",
    )

    # 7. Brand-check grid updated for logo column (3 columns)
    brand_check_rule = re.search(r"\.brand-check\s*\{(?P<body>[^}]*)\}", styles)
    _assert(brand_check_rule, ".brand-check rule missing from CSS.")
    brand_check_body = brand_check_rule.group("body")
    _assert(
        "30px" in brand_check_body or "28px" in brand_check_body or "32px" in brand_check_body,
        ".brand-check grid must include a fixed-width column for the logo.",
    )

    # 8. Key brand logos referenced
    for brand in (
        "REPSOL", "CEPSA", "GALP", "BALLENOIL", "PLENERGY", "PETROPRIX", "BP", "SHELL",
        "EROSKI", "ESCLATOIL", "PETROCAT", "BEROIL", "GASEXPRESS", "HAM", "ALCAMPO",
        "MEROIL", "AGLA",
    ):
        _assert(
            brand in js,
            f"BRAND_LOGOS must include {brand}.",
        )
    for logo_name in ("repsol", "cepsa", "galp", "ballenoil", "plenergy", "petroprix", "shell"):
        logo_path = f"/static/logos/{logo_name}.png"
        _assert(logo_path in js, f"BRAND_LOGOS must use the provided PNG asset for {logo_name}.")
        _assert((ROOT / "static" / "logos" / f"{logo_name}.png").exists(), f"{logo_name}.png must exist.")
    provided_logo_paths = (
        "/static/logos/eroski.svg",
        "/static/logos/esclat.png",
        "/static/logos/petrocat.jpg",
        "/static/logos/beroil.jpg",
        "/static/logos/gasexpress.jpg",
        "/static/logos/ham.png",
        "/static/logos/alcampo.png",
        "/static/logos/meroil.jpg",
        "/static/logos/agla.jpg",
        "/static/logos/bp.png",
    )
    for logo_path in provided_logo_paths:
        _assert(logo_path in js, f"BRAND_LOGOS must use the provided asset {logo_path}.")
        _assert((ROOT / logo_path.lstrip("/")).exists(), f"{logo_path} must exist.")

    # 9. Generic station SVG file exists
    generic_path = ROOT / "static" / "logos" / "generic-station.svg"
    _assert(generic_path.exists(), "generic-station.svg fallback file must exist.")

    # 10. No external logo CDN URLs in runtime code
    runtime_logo_pattern = re.search(
        r"(wikimedia\.org|worldvectorlogo|cdnlogo|shields\.io)[^\"']*\.(svg|png)",
        js,
    )
    _assert(
        runtime_logo_pattern is None,
        "No external logo CDN URLs should appear in app.js runtime code.",
    )


def test_external_leaflet_has_sri() -> None:
    """H4: any Leaflet asset still loaded from a CDN must carry an SRI
    integrity hash and crossorigin. Locally vendored Leaflet is also accepted
    (those tags are same-origin and exempt from the SRI requirement)."""
    html = _read("static/index.html")
    _assert("leaflet" in html.lower(), "Leaflet does not appear to be loaded by index.html.")
    _assert(
        'href="/static/vendor/leaflet/leaflet.css?v=1.9.4"' in html,
        "The installed frontend must load its vendored Leaflet stylesheet.",
    )
    _assert(
        'src="/static/vendor/leaflet/leaflet.js?v=1.9.4"' in html,
        "The installed frontend must load its vendored Leaflet script.",
    )
    _assert("unpkg.com/leaflet" not in html, "Leaflet must not depend on a CDN in the desktop build.")
    for relative in (
        "static/vendor/leaflet/leaflet.css",
        "static/vendor/leaflet/leaflet.js",
        "static/vendor/leaflet/LICENSE",
        "static/vendor/leaflet/images/marker-icon.png",
        "static/vendor/leaflet/images/marker-shadow.png",
    ):
        _assert((ROOT / relative).is_file(), f"Vendored Leaflet asset is missing: {relative}")
    tag_re = re.compile(r"<(?:link|script)\b[^>]*leaflet[^>]*>", re.IGNORECASE)
    external_re = re.compile(r'(?:href|src)\s*=\s*"(?:https?:)?//', re.IGNORECASE)
    for tag in tag_re.findall(html):
        if external_re.search(tag):
            _assert(
                "integrity=" in tag and "sha" in tag,
                f"External Leaflet tag must include an SRI integrity hash: {tag}",
            )
            _assert(
                "crossorigin" in tag,
                f"External Leaflet tag must include crossorigin for SRI to apply: {tag}",
            )


def test_no_unauthorized_analytics_or_retired_domains() -> None:
    files = ("static/index.html", "static/app.js", "static/robots.txt")
    combined = "\n".join((ROOT / relative).read_text(encoding="utf-8").lower() for relative in files)
    forbidden = (
        "goat" + "counter",
        "gc" + ".zgo.at",
        "fuelopt" + ".es",
        "ko" + "-fi",
        "buyme" + "acoffee",
    )
    for value in forbidden:
        _assert(value not in combined, f"Retired or unauthorized frontend integration found: {value}")
    html = (ROOT / "static/index.html").read_text(encoding="utf-8")
    external_script = re.compile(r"<script\b[^>]*\bsrc\s*=\s*['\"](?:https?:)?//", re.IGNORECASE)
    _assert(not external_script.search(html), "Frontend must not load unauthorized external scripts")


def test_public_privacy_and_how_it_works_match_current_frontend() -> None:
    privacy = _read("static/privacy.html")
    how_it_works = _read("static/como-funciona.html")

    for term in (
        "fuelopt:onboarding:v1:dismissed",
        "OpenRouteService",
        "OpenStreetMap",
        "Google Maps",
        "GitHub Issues",
    ):
        _assert(term in privacy, f"Privacy page is missing the current integration: {term}")
    _assert("ya no utiliza SMTP" in privacy, "Privacy page must not describe mail feedback as active")
    _assert("formulario de feedback" not in privacy.lower(), "Retired feedback form remains in privacy copy")

    for term in (
        "M&aacute;s ahorro",
        "Menor desv&iacute;o",
        "Equilibrado",
        "result_limit",
        "OpenRouteService",
        "Haversine",
        "FastAPI",
        "SQLite",
    ):
        _assert(term in how_it_works, f"How-it-works page is missing current behavior: {term}")
    _assert(
        "remaining_fuel_liters" not in how_it_works,
        "How-it-works page must not present unimplemented autonomy fields",
    )
    for retired in ("GMAIL_USER", "GMAIL_APP_PASSWORD", "FEEDBACK_RECIPIENT", "fuelopt" + ".es"):
        _assert(retired not in privacy and retired not in how_it_works, f"Retired public reference remains: {retired}")


def test_map_attribution_uses_official_osm_and_ors_credits() -> None:
    js = _read("static/app.js")
    _assert(
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png" in js,
        "Leaflet must use the official OpenStreetMap tile URL without subdomains",
    )
    _assert("https://www.openstreetmap.org/copyright" in js, "OpenStreetMap copyright link is missing")
    _assert("OpenStreetMap contributors" in js, "OpenStreetMap attribution is missing")
    _assert("https://openrouteservice.org/" in js and "openrouteservice.org" in js, "ORS attribution is missing")
    _assert("by HeiGIT" in js, "HeiGIT attribution is missing")
    _assert("Fuente de ruta" not in js, "Technical route-source blocks must not return to result cards")


def run() -> None:
    test_frontend_is_extracted()
    test_external_leaflet_has_sri()
    test_no_unauthorized_analytics_or_retired_domains()
    test_public_privacy_and_how_it_works_match_current_frontend()
    test_map_attribution_uses_official_osm_and_ors_credits()
    test_dynamic_html_uses_escape_helper()
    test_optimization_mode_selector_is_native_and_accessible()
    test_optimization_mode_request_and_result_state_are_separate()
    test_result_presentation_is_simplified_and_route_warning_is_plain()
    test_optimize_loading_state_is_accessible_and_bounded()
    test_brand_loading_and_all_button_state_are_unambiguous()
    test_frontend_has_no_visible_mojibake()
    test_result_metrics_are_rendered_once()
    test_catalog_and_route_status_copy_present()
    test_header_has_no_support_chip_and_keeps_primary_actions()
    test_first_opening_quick_help_is_accessible_and_non_blocking()
    test_quick_help_is_scoped_to_the_install_instance()
    test_sidebar_and_floating_search_layout()
    test_app_js_renders_warnings()
    test_haversine_copy_appears_once()
    test_styles_warning_classes()
    test_stale_price_warning_moves_to_price_metric()
    test_app_js_handles_virtual_brand()
    test_map_has_user_location_control()
    test_map_controls_share_layout_anchor()
    test_sidebar_dropdown_stacks_above_brands()
    test_result_panel_layout_and_alternatives_state()
    test_route_fit_uses_visible_map_area()
    test_route_layer_cleared_before_async_fetch()
    test_search_input_no_length_reset()
    test_emerald_gold_palette_applied()
    test_brand_logos_implemented()
    print("OK: frontend static checks passed")


if __name__ == "__main__":
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    run()
