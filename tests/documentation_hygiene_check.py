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
    "docs/README.md",
    "docs/INSTALLATION.md",
    "docs/USER_GUIDE.md",
    "docs/CONFIGURATION.md",
    "docs/TROUBLESHOOTING.md",
    "docs/DEVELOPMENT.md",
    "docs/ARCHITECTURE.md",
    "docs/RELEASING.md",
    "docs/PR2_RECONCILIATION.md",
    "docs/FINAL_REVIEW_BACKLOG.md",
    "docs/THIRD_PARTY_NOTICES.md",
    "docs/archive/README.md",
)
ARCHIVED_DOCUMENTS = (
    "docs/archive/AUDITORIA_PROYECTO.md",
    "docs/archive/DATABASE_ARTIFACT_POLICY.md",
    "docs/archive/SECRETS_AND_ENV.md",
    "docs/archive/SECURITY_HARDENING_H3_H6_H8.md",
    "docs/archive/SECURITY_SUPPLY_CHAIN_H4_H9.md",
    "docs/archive/TASK_REFRESH_COMMANDS.md",
)
REPOSITORY_URL = "https://github.com/miguel-pajuelo/fuel-opt-project"
BRAND_SOURCE_SHA256 = "0EF1C3988F4711352F4ABDF4A2EC1B3081E80A02F75FAE28A3B545A88DC82A16"


def _assert(condition: bool, message: str) -> None:
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
    for relative in CANONICAL_DOCUMENTS + ARCHIVED_DOCUMENTS:
        source = ROOT / relative
        text = _read(relative)
        for raw_target in link_pattern.findall(text):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, flags=re.IGNORECASE):
                continue
            file_part, separator, anchor = target.partition("#")
            destination = source if not file_part else (source.parent / file_part).resolve()
            _assert(destination.is_file(), f"Broken internal link in {relative}: {target}")
            if separator and anchor and destination.suffix.lower() == ".md":
                destination_text = destination.read_text(encoding="utf-8")
                _assert(anchor in _anchors(destination_text), f"Broken anchor in {relative}: {target}")


def _repository_text_files() -> list[Path]:
    allowed = {".md", ".py", ".html", ".js", ".css", ".txt", ".yml", ".yaml", ".cmd", ".ps1", ".iss", ".spec"}
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in allowed:
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith((".git/", "build/", "dist/", ".venv/", "static/vendor/", "data/")):
            continue
        files.append(path)
    return files


def _check_hygiene() -> None:
    analytics_name = "goat" + "counter"
    analytics_host = "gc" + ".zgo.at"
    retired_domain = "fuelopt" + ".es"
    donation_names = ("ko" + "-fi", "buyme" + "acoffee")
    personal_patterns = (
        re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE),
        re.compile(r"/Users/", re.IGNORECASE),
        re.compile(r"One" + r"Drive", re.IGNORECASE),
        re.compile(r"GAS" + r"\s+SCRAPING", re.IGNORECASE),
        re.compile(r"SIDE" + r"\s+PROJECTS", re.IGNORECASE),
    )
    railway_name = "rail" + "way"
    railway_allowed = {
        *ARCHIVED_DOCUMENTS,
        "docs/archive/README.md",
        "docs/PR2_RECONCILIATION.md",
        "tests/documentation_hygiene_check.py",
        "tests/installer_check.py",
    }
    retired_reference_allowed = {
        "docs/PR2_RECONCILIATION.md",
        "static/privacy.html",
        "tests/documentation_hygiene_check.py",
    }
    personal_pattern_allowed = {
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
            _assert(relative in retired_reference_allowed, f"Retired analytics name found in {relative}")
        _assert(analytics_host not in lowered, f"Retired analytics host found in {relative}")
        if retired_domain in lowered:
            _assert(relative in retired_reference_allowed, f"Retired public domain found in {relative}")
        for donation_name in donation_names:
            _assert(donation_name not in lowered, f"Donation reference found in {relative}")
        if relative not in personal_pattern_allowed:
            for pattern in personal_patterns:
                _assert(not pattern.search(lowered), f"Personal path found in {relative}")
        if railway_name in lowered:
            _assert(relative in railway_allowed, f"Active Railway reference found in {relative}")


def _check_backlog() -> None:
    backlog = _read("docs/FINAL_REVIEW_BACKLOG.md")
    for number in range(1, 49):
        identifier = f"FR-{number:03d}"
        _assert(identifier in backlog, f"Backlog item missing: {identifier}")
    required_terms = (
        "BLOCKER DE RELEASE",
        "OBLIGATORIO ANTES DE PUBLICACIÓN",
        "RECOMENDADO",
        "MEJORA FUTURA",
        "RIESGO ACEPTADO",
        "pendiente",
        "en curso",
        "validado",
        "riesgo aceptado",
        "descartado",
    )
    for term in required_terms:
        _assert(term in backlog, f"Backlog vocabulary missing: {term}")
    for number in (2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 22, 33, 34, 38, 43):
        row = next((line for line in backlog.splitlines() if line.startswith(f"| **FR-{number:03d}")), "")
        _assert("BLOCKER DE RELEASE" in row and "; sí;" in row, f"Required blocker is not classified correctly: FR-{number:03d}")
    fr047 = next(line for line in backlog.splitlines() if line.startswith("| **FR-047"))
    _assert("OBLIGATORIO ANTES DE PUBLICACIÓN" in fr047 and "; sí;" in fr047, "FR-047 must block release without changing its category")
    fr001 = next(line for line in backlog.splitlines() if line.startswith("| **FR-001"))
    fr037 = next(line for line in backlog.splitlines() if line.startswith("| **FR-037"))
    _assert("validado" in fr001, "FR-001 must remain validated")
    _assert("en curso" in fr037, "FR-037 must remain in progress")
    fr048 = next(line for line in backlog.splitlines() if line.startswith("| **FR-048"))
    _assert("320 px" in fr048 and "no; P2; pendiente" in fr048, "FR-048 mobile overflow is not tracked correctly")


def _check_pr2_reconciliation() -> None:
    reconciliation = _read("docs/PR2_RECONCILIATION.md")
    for heading in (
        "## A. Recuperado",
        "## B. Ya existía de forma equivalente",
        "## C. Pospuesto a 0.2.0",
        "## D. Descartado",
    ):
        _assert(heading in reconciliation, f"PR #2 reconciliation category missing: {heading}")
    for mode in ("economic", "minimal_detour", "balanced"):
        _assert(mode in reconciliation, f"Optimization mode missing from PR #2 reconciliation: {mode}")
    _assert("remaining_fuel_liters" in reconciliation and "0.2.0" in reconciliation, "Autonomy deferral is missing")


def _check_public_explanations() -> None:
    privacy = _read("static/privacy.html")
    for term in (
        "fuelopt:onboarding:v1:dismissed",
        "OpenRouteService",
        "OpenStreetMap",
        "Google Maps",
        "GitHub Issues",
        "Windows Credential Manager",
        "MINETUR",
    ):
        _assert(term in privacy, f"Privacy page is missing current behavior: {term}")
    _assert("Ballenoil" not in privacy, "Privacy page must describe the official catalog neutrally.")
    _assert("ya no utiliza SMTP" in privacy, "Privacy page must describe SMTP as removed")

    how_it_works = _read("static/como-funciona.html")
    for section in (
        "Qu&eacute; hace FuelOpt",
        "C&oacute;mo indicar un lugar",
        "Datos de la b&uacute;squeda",
        "Modos de optimizaci&oacute;n",
        "C&oacute;mo se calcula el coste real",
        "C&oacute;mo se calculan las rutas",
        "C&oacute;mo se ordenan las alternativas",
        "De d&oacute;nde proceden los precios",
        "Qu&eacute; ocurre dentro de la aplicaci&oacute;n",
        "Privacidad y servicios externos",
        "L&iacute;mites y supuestos",
    ):
        _assert(section in how_it_works, f"How-it-works section is missing: {section}")
    for term in ("Ministerio de Industria y Turismo", "MINETUR", "SQLite", "base de datos", "FastAPI", "127.0.0.1"):
        _assert(term in how_it_works, f"How-it-works technical explanation is missing: {term}")
    _assert("Ballenoil" not in how_it_works, "Public how-it-works page must not highlight an individual brand.")

    security = _read("SECURITY.md")
    _assert("GitHub Issues se reserva" in security, "SECURITY must define the public Issues boundary")
    _assert("canal privado de seguridad de GitHub" in security, "SECURITY must direct sensitive reports to GitHub private security")

    configuration = _read("docs/CONFIGURATION.md")
    for retired_variable in ("GMAIL_USER", "GMAIL_APP_PASSWORD", "FEEDBACK_RECIPIENT"):
        _assert(retired_variable not in configuration, f"Retired mail variable remains active: {retired_variable}")

    backlog = _read("docs/FINAL_REVIEW_BACKLOG.md")
    fr022 = next(line for line in backlog.splitlines() if line.startswith("| **FR-022"))
    fr048 = next(line for line in backlog.splitlines() if line.startswith("| **FR-048"))
    _assert("validado" in fr022 and "Resuelto mediante" in fr022, "FR-022 must be resolved through GitHub Issues")
    _assert("pendiente" in fr048, "FR-048 must remain pending")


def _check_repository_state() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True, shell=False
    ).stdout.splitlines()
    _assert(not any(path.startswith(("build/", "dist/")) for path in tracked), "Generated build output is tracked")
    _assert(not any((ROOT / name).exists() for name in ("LICENSE", "LICENSE.md", "LICENSE.txt")), "A project license was selected without approval")
    source = ROOT / "assets/source/fuelopt-icon-approved.png"
    _assert(source.is_file(), "Approved brand source is missing")
    _assert(hashlib.sha256(source.read_bytes()).hexdigest().upper() == BRAND_SOURCE_SHA256, "Approved brand source hash changed")
    _assert(not list((ROOT / "assets").rglob("*.svg")), "An unapproved vector asset exists")


def run() -> None:
    for relative in CANONICAL_DOCUMENTS + ARCHIVED_DOCUMENTS:
        _read(relative)
    readme = _read("README.md")
    _assert(REPOSITORY_URL in readme, "README repository URL is incorrect")
    _assert("pre-release" in readme.lower(), "README must state pre-release status")
    _assert("se publicarán en GitHub Releases cuando la primera versión sea aprobada" in readme, "README release wording is missing")
    _assert("## [0.1.0] - Unreleased" in _read("CHANGELOG.md"), "CHANGELOG must keep 0.1.0 Unreleased")
    security = _read("SECURITY.md").lower()
    _assert("no existen versiones públicas soportadas" in security, "SECURITY must not claim supported public versions")
    for relative in ARCHIVED_DOCUMENTS:
        archived = _read(relative)
        for field in ("Estado: SUPERSEDED", "Fecha de archivo", "Documento canónico sustituto", "Motivo", "Valor histórico", "Advertencia"):
            _assert(field in archived, f"Archive header field missing in {relative}: {field}")
    notices = _read("docs/THIRD_PARTY_NOTICES.md")
    for heading in (
        "## A. Componentes distribuidos en el bundle",
        "## B. Servicios externos utilizados en ejecución",
        "## C. Herramientas de desarrollo y compilación",
    ):
        _assert(heading in notices, f"Third-party category missing: {heading}")
    _check_internal_links()
    _check_hygiene()
    _check_backlog()
    _check_pr2_reconciliation()
    _check_public_explanations()
    _check_repository_state()
    print("OK: documentation hygiene checks passed")


if __name__ == "__main__":
    run()
