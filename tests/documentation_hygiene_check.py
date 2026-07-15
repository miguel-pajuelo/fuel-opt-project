from __future__ import annotations

import hashlib
import re
import subprocess
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_DOCUMENTS = (
    "README.md",
    "CHANGELOG.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "assets/README.md",
    "app/legacy_cli/README.md",
    "docs/README.md",
    "docs/INSTALLATION.md",
    "docs/USER_GUIDE.md",
    "docs/CONFIGURATION.md",
    "docs/TROUBLESHOOTING.md",
    "docs/DEVELOPMENT.md",
    "docs/ARCHITECTURE.md",
    "docs/RELEASING.md",
    "docs/DATA_SOURCES_AND_ATTRIBUTION.md",
    "docs/THIRD_PARTY_NOTICES.md",
)
REMOVED_INTERNAL_DOCUMENTS = (
    "docs/FINAL_REVIEW_BACKLOG.md",
    "docs/PR2_RECONCILIATION.md",
    "docs/archive/README.md",
    "docs/archive/AUDITORIA_PROYECTO.md",
    "docs/archive/DATABASE_ARTIFACT_POLICY.md",
    "docs/archive/SECRETS_AND_ENV.md",
    "docs/archive/SECURITY_HARDENING_H3_H6_H8.md",
    "docs/archive/SECURITY_SUPPLY_CHAIN_H4_H9.md",
    "docs/archive/TASK_REFRESH_COMMANDS.md",
)
REPOSITORY_URL = "https://github.com/miguel-pajuelo/fuel-opt-project"
LATEST_RELEASE_URL = f"{REPOSITORY_URL}/releases/latest"
BRAND_SOURCE_SHA256 = "0EF1C3988F4711352F4ABDF4A2EC1B3081E80A02F75FAE28A3B545A88DC82A16"
APACHE_LICENSE_SHA256 = "C71D239DF91726FC519C6EB72D318EC65820627232B2F796219E87DCF35D0AB4"
STATION_LOGOS_TREE_SHA256 = "6638980529C47A117CC7C1F2CF9F017C80AA4FF96E78C297547767941AE8BE94"


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _read(relative: str) -> str:
    path = ROOT / relative
    _assert(path.is_file(), f"Required documentation is missing: {relative}")
    return path.read_text(encoding="utf-8")


def _slug(heading: str) -> str:
    normalized = unicodedata.normalize("NFKD", heading.strip().lower())
    ascii_heading = "".join(char for char in normalized if not unicodedata.combining(char))
    ascii_heading = re.sub(r"[^a-z0-9 _-]", "", ascii_heading)
    return re.sub(r"[\s]+", "-", ascii_heading).strip("-")


def _anchors(markdown: str) -> set[str]:
    return {
        _slug(match.group(1))
        for match in re.finditer(r"^#{1,6}\s+(.+?)\s*$", markdown, flags=re.MULTILINE)
    }


def _check_internal_links() -> None:
    link_pattern = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
    for relative in CANONICAL_DOCUMENTS:
        source = ROOT / relative
        for raw_target in link_pattern.findall(_read(relative)):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, flags=re.IGNORECASE):
                continue
            file_part, separator, anchor = target.partition("#")
            destination = source if not file_part else (source.parent / file_part).resolve()
            _assert(destination.is_file(), f"Broken internal link in {relative}: {target}")
            if separator and anchor and destination.suffix.lower() == ".md":
                _assert(anchor in _anchors(destination.read_text(encoding="utf-8")), f"Broken anchor: {target}")


def _repository_text_files() -> list[Path]:
    allowed = {".md", ".py", ".html", ".js", ".css", ".txt", ".yml", ".yaml", ".cmd", ".ps1", ".iss", ".spec"}
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in allowed:
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith((".git/", "build/", "dist/", ".venv/", "static/vendor/", "data/")):
            continue
        files.append(path)
    return files


def _check_repository_hygiene() -> None:
    analytics_name = "goat" + "counter"
    analytics_host = "gc" + ".zgo.at"
    retired_domain = "fuelopt" + ".es"
    railway_name = "rail" + "way"
    donation_names = ("ko" + "-fi", "buyme" + "acoffee")
    personal_patterns = (
        re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE),
        re.compile(r"/Users/", re.IGNORECASE),
        re.compile("One" + "Drive", re.IGNORECASE),
        re.compile(r"GAS\s+SCRAPING", re.IGNORECASE),
        re.compile(r"SIDE\s+PROJECTS", re.IGNORECASE),
    )
    retired_allowed = {"static/privacy.html", "tests/documentation_hygiene_check.py"}
    personal_allowed = {
        "tests/brand_assets_check.py",
        "tests/bundle_check.py",
        "tests/documentation_hygiene_check.py",
        "tests/secrets_check.py",
        "tests/version_info_check.py",
    }
    for path in _repository_text_files():
        relative = path.relative_to(ROOT).as_posix()
        lowered = path.read_text(encoding="utf-8", errors="replace").lower()
        if analytics_name in lowered:
            _assert(relative in retired_allowed, f"Retired analytics reference found in {relative}")
        _assert(analytics_host not in lowered, f"Retired analytics host found in {relative}")
        if retired_domain in lowered:
            _assert(relative in retired_allowed, f"Retired domain found in {relative}")
        if railway_name in lowered:
            _assert(relative in {"tests/documentation_hygiene_check.py", "tests/installer_check.py"}, f"Railway reference found in {relative}")
        _assert(not any(name in lowered for name in donation_names), f"Donation reference found in {relative}")
        if relative not in personal_allowed:
            for pattern in personal_patterns:
                _assert(not pattern.search(lowered), f"Personal path found in {relative}")


def _check_public_documentation() -> None:
    readme = _read("README.md")
    _assert(REPOSITORY_URL in readme and LATEST_RELEASE_URL in readme, "README release links are incorrect")
    for stale in ("pre-release", "primera versión", "blocker", "FINAL_REVIEW_BACKLOG", "PR2_RECONCILIATION", "0.1.1", "Unreleased"):
        _assert(stale.lower() not in readme.lower(), f"README contains internal or future wording: {stale}")

    changelog = _read("CHANGELOG.md")
    releasing = _read("docs/RELEASING.md")
    _assert("## [0.1.1] - Unreleased" in changelog, "CHANGELOG does not contain 0.1.1 Unreleased")
    _assert("## [0.1.0] - 2026-07-15" in changelog, "published 0.1.0 history is incorrect")
    _assert("0.1.1 — Unreleased" in releasing, "RELEASING does not identify the maintenance version")
    for relative in CANONICAL_DOCUMENTS:
        if relative not in {"CHANGELOG.md", "docs/RELEASING.md"}:
            text = _read(relative)
            _assert("0.1.1" not in text and "Unreleased" not in text, f"Future version leaked into {relative}")

    for removed in REMOVED_INTERNAL_DOCUMENTS:
        _assert(not (ROOT / removed).exists(), f"Internal documentation still exists: {removed}")

    combined = "\n".join(_read(relative) for relative in CANONICAL_DOCUMENTS)
    for stale in (
        "validación final en VM pendiente",
        "blocker de la primera release",
        "Patch 8B",
        "FR-047 no resuelve",
        "debe cerrarse como superseded",
    ):
        _assert(stale.lower() not in combined.lower(), f"Stale editorial wording remains: {stale}")

    installation = _read("docs/INSTALLATION.md")
    for term in ("Microsoft Defender SmartScreen", "SHA256SUMS.txt", "Más información", "Ejecutar de todas formas"):
        _assert(term in installation, f"SmartScreen guidance is missing: {term}")
    _assert("No desactives Microsoft Defender" in installation, "installation guide must not advise disabling Defender")
    _assert("No continúes" in installation and "checksum no coincide" in installation, "unsafe download warning is missing")

    for term in ("320 px", "zoom al 200 %", "Credenciales históricas de ORS", "permanece pendiente"):
        _assert(term in releasing, f"manual release validation was not migrated: {term}")
    _assert("no bloquea el código" in releasing.lower(), "FR-048 release impact is not documented")
    _assert("No registres su valor" in releasing, "private ORS rotation checklist must prohibit recording credentials")

    security = _read("SECURITY.md")
    for term in (
        "127.0.0.1",
        "0.0.0.0",
        "allowlist",
        "OpenAPI, Swagger y ReDoc",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "headers reenviados",
        "anonimizan la IP",
    ):
        _assert(term in security, f"canonical security hardening is missing: {term}")

    configuration = _read("docs/CONFIGURATION.md")
    _assert("predeterminada es `24h`" in configuration, "24h default is not documented")
    for term in ("FUELOPT_ALLOW_LAN", "FUELOPT_TRUST_PROXY_HEADERS", "FUELOPT_LOG_CLIENT_IP", "CORS_ORIGINS"):
        _assert(term in configuration, f"canonical network configuration is missing: {term}")
    for retired_variable in ("GMAIL_USER", "GMAIL_APP_PASSWORD", "FEEDBACK_RECIPIENT"):
        _assert(retired_variable not in configuration, f"Retired mail variable remains: {retired_variable}")

    data_sources = _read("docs/DATA_SOURCES_AND_ATTRIBUTION.md")
    _assert("MINETUR es la única fuente productiva" in data_sources, "MINETUR-only source is not explicit")
    _assert("criterios neutrales respecto a su marca" in data_sources, "brand-neutral treatment is missing")
    notices = _read("docs/THIRD_PARTY_NOTICES.md")
    for heading in (
        "## A. Componentes distribuidos en el bundle",
        "## B. Servicios externos utilizados en ejecución",
        "## C. Herramientas de desarrollo y compilación",
    ):
        _assert(heading in notices, f"Third-party category missing: {heading}")

    privacy = _read("static/privacy.html")
    for term in ("fuelopt:onboarding:v1:dismissed", "OpenRouteService", "OpenStreetMap", "Google Maps", "GitHub Issues", "MINETUR"):
        _assert(term in privacy, f"Privacy page is missing current behavior: {term}")
    how_it_works = _read("static/como-funciona.html")
    for term in ("MINETUR", "SQLite", "FastAPI", "127.0.0.1"):
        _assert(term in how_it_works, f"How-it-works page is missing: {term}")


def _check_repository_state() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True, shell=False
    ).stdout.splitlines()
    _assert(not any(path.startswith(("build/", "dist/")) for path in tracked), "Generated build output is tracked")
    _assert("TRADEMARKS.md" not in tracked and not (ROOT / "TRADEMARKS.md").exists(), "TRADEMARKS.md must not exist")

    license_path = ROOT / "LICENSE"
    normalized_license = license_path.read_bytes().replace(b"\r\n", b"\n")
    _assert(hashlib.sha256(normalized_license).hexdigest().upper() == APACHE_LICENSE_SHA256, "LICENSE changed")
    notice = _read("NOTICE")
    notice_ascii = unicodedata.normalize("NFKD", notice).encode("ascii", "ignore").decode("ascii")
    _assert("Copyright 2026 Miguel Pajuelo Gomez" in notice_ascii, "NOTICE holder changed")

    station_logos = ROOT / "static" / "logos"
    digest = hashlib.sha256()
    for path in sorted(station_logos.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(station_logos).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    _assert(digest.hexdigest().upper() == STATION_LOGOS_TREE_SHA256, "Station logo tree changed")

    public_paths = [ROOT / "README.md", ROOT / "CHANGELOG.md", *sorted((ROOT / "docs").rglob("*.md"))]
    public_paths.extend(sorted((ROOT / "static").glob("*.html")))
    public_text = "\n".join(path.read_text(encoding="utf-8", errors="replace").lower() for path in public_paths)
    _assert("static/logos" not in public_text, "Station logo provenance was documented")
    for phrase in ("permisos de los logos", "procedencia de los logos", "licencia de los logos"):
        _assert(phrase not in public_text, "Station logo permissions or provenance were documented")

    source = ROOT / "assets/source/fuelopt-icon-approved.png"
    _assert(hashlib.sha256(source.read_bytes()).hexdigest().upper() == BRAND_SOURCE_SHA256, "Brand source changed")
    _assert(not list((ROOT / "assets").rglob("*.svg")), "Unapproved vector asset exists")


def run() -> None:
    for relative in CANONICAL_DOCUMENTS:
        _read(relative)
    _check_internal_links()
    _check_repository_hygiene()
    _check_public_documentation()
    _check_repository_state()
    print("OK: documentation hygiene checks passed")


if __name__ == "__main__":
    run()
