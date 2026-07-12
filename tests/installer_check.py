"""Static safety checks for the per-user Inno Setup installer."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "installer" / "FuelOpt.iss"
BUILD_SCRIPT = ROOT / "scripts" / "build_installer.cmd"
APP_ID = "{0EA78328-E3EB-48EF-A92C-B87491202B14}"


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def app_id(text: str) -> str:
    match = re.search(r"^AppId=\{(\{[0-9A-F-]+\})$", text, flags=re.MULTILINE | re.IGNORECASE)
    if not match:
        raise AssertionError("fixed AppId is missing")
    return match.group(1).upper()


def run() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    lowered = text.lower()
    build = BUILD_SCRIPT.read_text(encoding="utf-8")

    _assert(app_id(text) == APP_ID, app_id(text))
    _assert("#ifndef appversion" in lowered and '/dappversion=' in build.lower(), "AppVersion must be build-parametrized")
    _assert("privilegesrequired=lowest" in lowered, "installer must not request elevation")
    _assert(r"defaultdirname={localappdata}\programs\{#appname}" in lowered, "installer must be per-user")
    _assert("usepreviousappdir=yes" in lowered, "updates must reuse the prior installation")
    _assert(r'source: "..\dist\fuelopt\*"' in lowered, "installer must consume only the audited onedir bundle")
    _assert("recursesubdirs" in lowered and "createallsubdirs" in lowered, "onedir resources must be recursive")
    _assert("[installdelete]" in lowered, "upgrades must remove stale onedir internals")
    _assert(r'name: "{app}\_internal"' in lowered, "upgrade cleanup must be limited to _internal")
    _assert(r'name: "{app}\*"' not in lowered, "upgrade cleanup must not wipe the installation directory")
    _assert("setupiconfile={#appiconsource}" in lowered, "approved ICO wiring is missing")
    _assert(r"uninstalldisplayicon={app}\{#appexename}" in lowered, "uninstall icon is missing")
    _assert(lowered.count('iconfilename: "{app}\\{#appexename}"') == 2, "shortcut icons are incomplete")
    _assert("desktopicon" in lowered and "flags: unchecked" in lowered, "desktop shortcut must be optional")
    _assert("{autoprograms}" in lowered, "Start menu shortcut is missing")

    shutdown = lowered.index("function initializeuninstall")
    remove_task = lowered.index("--remove-refresh-task", shutdown)
    remove_data = lowered.index("deltree(userdatapath", remove_task)
    _assert(shutdown < remove_task < remove_data, "uninstall ordering is unsafe")
    _assert("--shutdown-existing" in lowered, "updates and uninstall must close FuelOpt cooperatively")
    _assert("removedatasilently" in lowered and "{param:removedata|0}" in lowered, "silent data removal is not explicit")
    _assert("preserving fuelopt user data" in lowered, "data must be preserved by default")
    _assert("removeuserdat" in lowered and "checked := removedatasilently" in lowered, "visible data-removal opt-in is missing")

    _assert("{param:refresh|__absent__}" in lowered, "missing /REFRESH must be distinguishable")
    _assert("rejected invalid /refresh parameter" in lowered and "result := false" in lowered, "invalid /REFRESH must abort visibly")
    _assert("getpreviousdata('refreshinterval', '4h')" in lowered, "updates must retain the chosen interval")
    _assert("registerpreviousdata" in lowered, "refresh selection is not persisted")
    _assert("selectedvalueindex := refreshindexfrominterval" in lowered, "refresh selection must drive the page")
    for interval in ("1h", "2h", "4h", "8h", "12h", "24h", "on_open", "manual"):
        _assert(re.search(rf"result\s*:=\s*'{re.escape(interval)}'", lowered), f"missing interval: {interval}")
    _assert("refresh4h=every 4 hours (recommended)" in lowered, "English recommended default missing")
    _assert("spanish.refresh4h=" in lowered and "english.refresh4h=" in lowered, "bilingual refresh UI missing")
    _assert("spanish.removeuserdata=" in lowered and "english.removeuserdata=" in lowered, "bilingual uninstall UI missing")

    scheduler = (ROOT / "app" / "windows_scheduler.py").read_text(encoding="utf-8").lower()
    _assert('task_name = "fuelopt catalog refresh"' in scheduler, "task name changed")
    _assert("run_refresh_catalog.cmd" in scheduler and "unrecognized task" in scheduler, "legacy migration is not restricted")
    _assert("--refresh-direct --silent" in (ROOT / "fuelopt_launcher.py").read_text(encoding="utf-8"), "task command is not direct")

    forbidden = (".env", "ors_api_key", "gmail_app_password", "fuelopt_admin_token", "railway", ".git")
    for token in forbidden:
        _assert(token not in lowered, f"installer references forbidden content: {token}")

    _assert("bundle_check.py --bundle dist\\fuelopt" in build.lower(), "installer build must audit the bundle first")
    _assert("installer\\fuelopt.iss" in build.lower(), "installer build does not compile the expected script")
    _assert((ROOT / "dist" / "FuelOpt" / "FuelOpt.exe").is_file(), "audited onedir bundle is missing")
    print("OK: Inno Setup installer safety checks passed")


if __name__ == "__main__":
    run()
